"""Money-safety regressions for the Business+ client account balance."""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest

from src.modules.subscription import client_balance as client_balance_module

if getattr(client_balance_module, "FLIREXA_COMMERCIAL_STUB", False):
    pytest.skip(
        "Client account balance is exercised by the private commercial overlay",
        allow_module_level=True,
    )

from src.modules.subscription.client_balance import (
    BalanceError,
    adjust_balance,
    get_balance_snapshot,
    purchase_subscription,
    usd_to_minor,
)
from src.modules.subscription.subscription_manager import SubscriptionManager
from src.modules.subscription.subscription_models import (
    ClientBalanceTransaction,
    ClientPortalPayment,
    ClientUser,
    PaymentMethod,
    SubscriptionStatus,
)


def _user(db_session, tag: str) -> ClientUser:
    suffix = uuid.uuid4().hex[:8]
    user = ClientUser(
        email=f"balance-{tag}-{suffix}@test.invalid",
        username=f"balance_{tag}_{suffix}",
        password_hash="test-only",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _manager_with_plans(db_session) -> SubscriptionManager:
    manager = SubscriptionManager(db_session)
    manager.create_default_plans()
    return manager


def test_usd_to_minor_uses_decimal_rounding_not_binary_float():
    assert usd_to_minor("1.99") == 199
    assert usd_to_minor(Decimal("0.105")) == 11
    with pytest.raises(BalanceError):
        usd_to_minor("NaN")


def test_verified_topup_credits_exactly_once(db_session):
    user = _user(db_session, "topup")
    manager = _manager_with_plans(db_session)
    payment = manager.create_payment(
        user_id=user.id,
        amount_usd=25.00,
        payment_method=PaymentMethod.PAYPAL,
        subscription_tier=None,
        duration_days=None,
        invoice_id=f"TOP-{uuid.uuid4().hex}",
        provider_name="paypal",
        purpose="balance_topup",
        balance_credit_minor=2500,
    )

    assert manager.complete_payment(payment.invoice_id, tx_hash="CAPTURE-1", sync_wg=False)
    assert manager.complete_payment(payment.invoice_id, tx_hash="CAPTURE-1", sync_wg=False)

    snapshot = get_balance_snapshot(db_session, user.id)
    assert snapshot["available_minor"] == 2500
    rows = db_session.query(ClientBalanceTransaction).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].amount_minor == 2500
    assert rows[0].transaction_type == "topup"


def test_topup_rejects_local_amount_mismatch(db_session):
    user = _user(db_session, "mismatch")
    manager = _manager_with_plans(db_session)
    payment = manager.create_payment(
        user_id=user.id,
        amount_usd=10.00,
        payment_method=PaymentMethod.USD,
        subscription_tier=None,
        duration_days=None,
        invoice_id=f"TOP-{uuid.uuid4().hex}",
        provider_name="test",
        purpose="balance_topup",
        balance_credit_minor=999,
    )

    with pytest.raises(BalanceError):
        manager.complete_payment(payment.invoice_id, sync_wg=False)
    db_session.rollback()
    assert get_balance_snapshot(db_session, user.id)["available_minor"] == 0
    assert manager.get_payment_by_invoice(payment.invoice_id).status == "pending"


def test_balance_purchase_is_atomic_and_idempotent(db_session):
    user = _user(db_session, "purchase")
    manager = _manager_with_plans(db_session)
    manager.ensure_subscription(user.id)
    adjust_balance(
        db_session,
        user_id=user.id,
        amount_minor=5000,
        reason="Test credit",
        actor_id="test-admin",
        idempotency_key="seed-purchase",
    )
    db_session.commit()

    request_id = str(uuid.uuid4())
    payment = purchase_subscription(
        db_session,
        manager,
        user_id=user.id,
        amount_minor=1999,
        subscription_tier="basic",
        duration_days=30,
        request_id=request_id,
    )
    first_expiry = manager.get_subscription(user.id)._aware_expiry()
    repeated = purchase_subscription(
        db_session,
        manager,
        user_id=user.id,
        amount_minor=1999,
        subscription_tier="basic",
        duration_days=30,
        request_id=request_id,
    )

    assert repeated.invoice_id == payment.invoice_id
    assert get_balance_snapshot(db_session, user.id)["available_minor"] == 3001
    sub = manager.get_subscription(user.id)
    assert sub.tier == "basic"
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub._aware_expiry() == first_expiry
    debit_rows = db_session.query(ClientBalanceTransaction).filter_by(
        user_id=user.id,
        transaction_type="subscription_purchase",
    ).all()
    assert len(debit_rows) == 1
    assert debit_rows[0].amount_minor == -1999


def test_insufficient_balance_does_not_mutate_subscription_or_ledger(db_session):
    user = _user(db_session, "insufficient")
    manager = _manager_with_plans(db_session)
    free_sub = manager.ensure_subscription(user.id)

    with pytest.raises(BalanceError, match="Insufficient"):
        purchase_subscription(
            db_session,
            manager,
            user_id=user.id,
            amount_minor=100,
            subscription_tier="basic",
            duration_days=30,
            request_id=str(uuid.uuid4()),
        )
    db_session.rollback()

    db_session.refresh(free_sub)
    assert free_sub.tier == "free"
    assert db_session.query(ClientBalanceTransaction).filter_by(user_id=user.id).count() == 0
    assert db_session.query(ClientPortalPayment).filter_by(user_id=user.id).count() == 0


def test_admin_adjustment_is_idempotent_and_cannot_go_negative(db_session):
    user = _user(db_session, "adjust")
    key = str(uuid.uuid4())
    adjust_balance(
        db_session,
        user_id=user.id,
        amount_minor=1200,
        reason="Manual credit",
        actor_id="1",
        idempotency_key=key,
    )
    db_session.commit()
    adjust_balance(
        db_session,
        user_id=user.id,
        amount_minor=1200,
        reason="Repeated request",
        actor_id="1",
        idempotency_key=key,
    )
    db_session.commit()

    assert get_balance_snapshot(db_session, user.id)["available_minor"] == 1200
    assert db_session.query(ClientBalanceTransaction).filter_by(user_id=user.id).count() == 1

    with pytest.raises(BalanceError, match="negative"):
        adjust_balance(
            db_session,
            user_id=user.id,
            amount_minor=-1201,
            reason="Invalid debit",
            actor_id="1",
            idempotency_key=str(uuid.uuid4()),
        )
    db_session.rollback()
    assert get_balance_snapshot(db_session, user.id)["available_minor"] == 1200
