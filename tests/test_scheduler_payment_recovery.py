from datetime import datetime, timedelta, timezone

from src.api import scheduler
from src.api.routes import client_portal
from src.modules.payment.base import PaymentStatus
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.subscription_models import (
    ClientPortalPayment,
    ClientUser,
    PaymentMethod,
)


def _payment(
    db,
    suffix: str,
    *,
    updated_minutes_ago: int,
    expires_minutes_from_now: int = 30,
) -> ClientPortalPayment:
    user = ClientUser(
        username=f"recovery-{suffix}",
        email=f"recovery-{suffix}@example.test",
        password_hash="test-only",
    )
    db.add(user)
    db.flush()
    now = datetime.now(timezone.utc)
    row = ClientPortalPayment(
        user_id=user.id,
        invoice_id=f"invoice-{suffix}",
        amount_usd=10.0,
        payment_method=PaymentMethod.NOWPAYMENTS,
        subscription_tier="basic",
        duration_days=30,
        provider_name="nowpayments",
        provider_invoice_id=f"provider-{suffix}",
        status="pending",
        created_at=now - timedelta(minutes=30),
        updated_at=now - timedelta(minutes=updated_minutes_ago),
        expires_at=now + timedelta(minutes=expires_minutes_from_now),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class _PendingProvider:
    def __init__(self):
        self.calls: list[str] = []

    async def check_payment(self, provider_invoice_id: str):
        self.calls.append(provider_invoice_id)
        return PaymentStatus.PENDING


def test_pending_recovery_uses_a_small_oldest_first_batch(db_session, monkeypatch):
    rows = [
        _payment(db_session, "oldest", updated_minutes_ago=30),
        _payment(db_session, "middle", updated_minutes_ago=25),
        _payment(db_session, "newest", updated_minutes_ago=20),
    ]
    provider = _PendingProvider()
    monkeypatch.setattr(client_portal, "nowpayments_provider", provider)
    monkeypatch.setattr(scheduler, "_PENDING_PAYMENT_RECOVERY_BATCH", 2)
    monkeypatch.setattr(
        scheduler, "_PENDING_PAYMENT_RECOVERY_RETRY_SECONDS", 600
    )
    original_updated_at = [row.updated_at for row in rows]

    scheduler._try_recover_pending_payments(db_session)

    assert provider.calls == ["provider-oldest", "provider-middle"]
    db_session.expire_all()
    assert db_session.get(ClientPortalPayment, rows[0].id).updated_at > original_updated_at[0]
    assert db_session.get(ClientPortalPayment, rows[1].id).updated_at > original_updated_at[1]
    assert db_session.get(ClientPortalPayment, rows[2].id).updated_at == original_updated_at[2]


def test_pending_recovery_persists_provider_backoff(db_session, monkeypatch):
    _payment(db_session, "backoff", updated_minutes_ago=30)
    provider = _PendingProvider()
    monkeypatch.setattr(client_portal, "nowpayments_provider", provider)
    monkeypatch.setattr(scheduler, "_PENDING_PAYMENT_RECOVERY_BATCH", 3)
    monkeypatch.setattr(
        scheduler, "_PENDING_PAYMENT_RECOVERY_RETRY_SECONDS", 600
    )

    scheduler._try_recover_pending_payments(db_session)
    scheduler._try_recover_pending_payments(db_session)

    assert provider.calls == ["provider-backoff"]


def test_pending_recovery_uses_idempotent_completion_path(db_session, monkeypatch):
    row = _payment(db_session, "paid", updated_minutes_ago=30)
    completed: list[str] = []

    class _PaidProvider:
        async def check_payment(self, provider_invoice_id: str):
            return PaymentStatus.COMPLETED

    def _complete(self, invoice_id: str, sync_wg: bool = True):
        completed.append(invoice_id)
        return True

    monkeypatch.setattr(client_portal, "nowpayments_provider", _PaidProvider())
    monkeypatch.setattr(SubscriptionManager, "complete_payment", _complete)
    monkeypatch.setattr(scheduler, "_PENDING_PAYMENT_RECOVERY_BATCH", 3)
    monkeypatch.setattr(
        scheduler, "_PENDING_PAYMENT_RECOVERY_RETRY_SECONDS", 600
    )

    scheduler._try_recover_pending_payments(db_session)

    assert completed == [row.invoice_id]


def test_expiry_waits_for_recovery_grace_and_is_bounded(db_session, monkeypatch):
    old = _payment(
        db_session,
        "expired-old",
        updated_minutes_ago=30,
        expires_minutes_from_now=-30,
    )
    recent = _payment(
        db_session,
        "expired-recent",
        updated_minutes_ago=30,
        expires_minutes_from_now=-5,
    )
    second_old = _payment(
        db_session,
        "expired-second",
        updated_minutes_ago=30,
        expires_minutes_from_now=-20,
    )
    monkeypatch.setattr(scheduler, "_PENDING_PAYMENT_EXPIRY_GRACE_SECONDS", 900)
    monkeypatch.setattr(scheduler, "_STALE_PAYMENT_EXPIRY_BATCH", 1)

    assert scheduler._expire_stale_pending_payments(db_session) == 1
    db_session.expire_all()
    assert db_session.get(ClientPortalPayment, old.id).status == "expired"
    assert db_session.get(ClientPortalPayment, second_old.id).status == "pending"
    assert db_session.get(ClientPortalPayment, recent.id).status == "pending"
