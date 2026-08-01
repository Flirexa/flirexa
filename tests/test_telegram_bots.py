"""Regression tests for the admin/client Telegram bot business boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone

import pytest

from src.api.routes import bots as bot_routes
from src.bots.admin_bot import AdminBot
from src.bots.client_bot import ClientBot
from src.bots import client_bot as client_bot_module
from src.modules.notifications import NotificationService
from src.modules.subscription.subscription_models import (
    ClientPortalPayment,
    ClientUser,
    ClientUserClients,
    DeviceSlot,
    PaymentMethod,
    SubscriptionPlan,
)
from src.database.models import Client, PushNotification, Server


FAKE_BOT_TOKEN = "123456789" + ":" + ("a" * 35)
ALT_FAKE_BOT_TOKEN = "987654321" + ":" + ("B" * 35)


class _Query:
    def __init__(self):
        self.edit_message_text = AsyncMock()
        self.message = SimpleNamespace(reply_text=AsyncMock())
        self.from_user = SimpleNamespace(id=1001)


class _CryptoPay:
    def __init__(self):
        self.created = None

    async def create_invoice(self, **kwargs):
        self.created = kwargs
        return {
            "invoice_id": "700001",
            "payment_url": "https://t.me/CryptoBot?start=invoice_700001",
            "amount_crypto": kwargs["amount_usd"],
        }


def _portal_user(db_session, *, telegram_id="1001", username="alice"):
    user = ClientUser(
        email=f"{username}@example.test",
        password_hash="telegram-auth-no-password",
        telegram_id=telegram_id,
        username=username,
        is_active=True,
        is_banned=False,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_client_bot_creates_real_provider_invoice_with_bound_metadata(db_session):
    user = _portal_user(db_session)
    plan = SubscriptionPlan(
        tier="premium",
        name="Premium",
        max_devices=5,
        price_monthly_usd=12.0,
        price_quarterly_usd=30.0,
        price_yearly_usd=99.0,
        is_active=True,
        is_visible=True,
    )
    db_session.add(plan)
    db_session.commit()

    bot = ClientBot(FAKE_BOT_TOKEN)
    provider = _CryptoPay()
    bot._cryptopay = provider
    query = _Query()
    context = SimpleNamespace(user_data={})
    core = SimpleNamespace(db=db_session)

    await bot._create_payment(
        query, core, user, plan.id, 30, "usdt", "en", context
    )

    payment = db_session.query(ClientPortalPayment).filter_by(invoice_id="700001").one()
    assert payment.user_id == user.id
    assert payment.provider_name == "cryptopay"
    assert payment.amount_usd == 12.0
    assert provider.created["metadata"]["user_id"] == user.id
    assert provider.created["metadata"]["duration_days"] == 30


@pytest.mark.asyncio
async def test_client_bot_fails_closed_when_payment_provider_is_missing(
    db_session, monkeypatch
):
    user = _portal_user(db_session)
    plan = SubscriptionPlan(
        tier="premium", name="Premium", max_devices=2,
        price_monthly_usd=10.0, is_active=True, is_visible=True,
    )
    db_session.add(plan)
    db_session.commit()
    monkeypatch.delenv("CRYPTOPAY_API_TOKEN", raising=False)
    monkeypatch.delenv("CLIENT_BOT_PAYMENT_TEST_MODE", raising=False)

    bot = ClientBot(FAKE_BOT_TOKEN)
    query = _Query()
    await bot._create_payment(
        query, SimpleNamespace(db=db_session), user, plan.id, 30,
        "usdt", "en", SimpleNamespace(user_data={}),
    )

    assert db_session.query(ClientPortalPayment).count() == 0
    assert "temporarily unavailable" in query.edit_message_text.await_args.args[0]


@pytest.mark.asyncio
async def test_payment_status_is_scoped_to_telegram_account(db_session):
    owner = _portal_user(db_session, telegram_id="1001", username="owner")
    attacker = _portal_user(db_session, telegram_id="2002", username="attacker")
    payment = ClientPortalPayment(
        user_id=owner.id,
        invoice_id="812345",
        amount_usd=20.0,
        payment_method=PaymentMethod.USDT_TRC20,
        subscription_tier="premium",
        duration_days=30,
        provider_name="cryptopay",
        status="pending",
    )
    db_session.add(payment)
    db_session.commit()

    bot = ClientBot(FAKE_BOT_TOKEN)
    query = _Query()
    await bot._check_payment_status(
        query, SimpleNamespace(db=db_session), attacker, "812345", "en"
    )

    assert query.edit_message_text.await_args.args[0] == "Payment not found."
    assert payment.status == "pending"


@pytest.mark.asyncio
async def test_expired_invoice_is_closed_without_contacting_provider(db_session):
    user = _portal_user(db_session)
    payment = ClientPortalPayment(
        user_id=user.id,
        invoice_id="812346",
        amount_usd=20.0,
        payment_method=PaymentMethod.USDT_TRC20,
        subscription_tier="premium",
        duration_days=30,
        provider_name="cryptopay",
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(payment)
    db_session.commit()

    bot = ClientBot(FAKE_BOT_TOKEN)
    query = _Query()
    await bot._check_payment_status(
        query, SimpleNamespace(db=db_session), user, "812346", "en"
    )

    assert payment.status == "expired"
    assert "Payment expired" in query.edit_message_text.await_args.args[0]


@pytest.mark.asyncio
async def test_banned_portal_account_is_blocked_in_client_bot(db_session):
    user = _portal_user(db_session)
    user.is_banned = True
    db_session.commit()
    telegram_user = SimpleNamespace(
        id=1001,
        username="alice",
        first_name="Alice",
        last_name=None,
        language_code="en",
    )
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=telegram_user, message=message)
    bot = ClientBot(FAKE_BOT_TOKEN)

    assert await bot._reject_if_blocked(
        SimpleNamespace(db=db_session), update, "en"
    ) is True
    assert message.reply_text.await_args.args[0] == bot.t("blocked", "en")


def test_admin_callbacks_use_compact_ids_and_confirm_destructive_action():
    bot = AdminBot(FAKE_BOT_TOKEN, [1001])
    keyboard = bot.get_client_menu_keyboard(987654, True)
    callback_values = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "delete_ask_987654" in callback_values
    assert "disable_987654" in callback_values
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_values)


def test_admin_bot_exposes_current_operational_sections():
    bot = AdminBot(FAKE_BOT_TOKEN, [1001])
    callbacks = {
        button.callback_data
        for row in bot.get_main_menu_keyboard().inline_keyboard
        for button in row
    }
    assert {"menu_online", "menu_business", "menu_system"} <= callbacks
    business = {
        button.callback_data
        for row in bot.get_business_menu_keyboard().inline_keyboard
        for button in row
    }
    assert {
        "biz_users", "biz_payments", "biz_support", "biz_promos",
        "biz_tariffs", "biz_broadcast",
    } <= business
    system = {
        button.callback_data
        for row in bot.get_system_menu_keyboard().inline_keyboard
        for button in row
    }
    assert {
        "sys_health", "sys_license", "sys_backups", "sys_updates",
        "sys_audit", "sys_traffic_rules",
    } <= system
    assert all(
        len(value.encode("utf-8")) <= 64
        for value in callbacks | business | system if value
    )


def test_client_bot_collapses_multi_region_slot_to_one_active_device(db_session):
    user = _portal_user(db_session)
    servers = [
        Server(
            name=f"region-{suffix}", endpoint=f"{suffix}.example.test:51820",
            public_key=char * 44, private_key=char.lower() * 44,
            address_pool_ipv4=f"10.66.{index}.0/24",
        )
        for index, (suffix, char) in enumerate((("a", "A"), ("b", "B")), 10)
    ]
    db_session.add_all(servers)
    db_session.flush()
    slot = DeviceSlot(
        client_user_id=user.id,
        label="Alice phone",
        public_key="K" * 44,
        private_key="k" * 44,
        active_server_id=servers[1].id,
    )
    db_session.add(slot)
    db_session.flush()
    peers = [
        Client(
            name=f"alice-{index}", server_id=server.id,
            public_key="P" * 43 + str(index), private_key="p" * 44,
            ipv4=f"10.66.{10 + index}.2", ip_index=2,
            enabled=index == 1,
        )
        for index, server in enumerate(servers)
    ]
    db_session.add_all(peers)
    db_session.flush()
    db_session.add_all([
        ClientUserClients(
            client_user_id=user.id, client_id=peer.id, slot_id=slot.id,
        )
        for peer in peers
    ])
    db_session.commit()

    bot = ClientBot(FAKE_BOT_TOKEN)
    devices = bot.get_user_clients(SimpleNamespace(db=db_session), 1001)

    assert [device.id for device in devices] == [peers[1].id]
    assert bot._device_label(devices[0]) == "Alice phone"
    assert bot._device_count(SimpleNamespace(db=db_session), user.id) == 1


def test_broadcast_notification_read_receipt_hides_only_for_that_user(db_session):
    from src.api.routes.client_portal import get_notifications, mark_notification_read

    owner = _portal_user(db_session, telegram_id="1001", username="notice-owner")
    other = _portal_user(db_session, telegram_id="2002", username="notice-other")
    notice = PushNotification(
        user_id=None, title="Maintenance", message="Tonight", is_read=False,
    )
    db_session.add(notice)
    db_session.commit()
    db_session.refresh(notice)

    assert [item["id"] for item in get_notifications(owner.id, db_session)] == [notice.id]
    mark_notification_read(notice.id, owner.id, db_session)

    assert get_notifications(owner.id, db_session) == []
    assert [item["id"] for item in get_notifications(other.id, db_session)] == [notice.id]


@pytest.mark.asyncio
async def test_safe_edit_ignores_not_modified_without_duplicate(monkeypatch):
    from telegram.error import BadRequest

    bot = AdminBot(FAKE_BOT_TOKEN, [1001])
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified")),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    await bot.safe_edit(query, "same")
    query.message.reply_text.assert_not_awaited()


def test_notification_tokens_come_from_env_and_dynamic_html_is_escaped(
    db_session, monkeypatch
):
    monkeypatch.setenv("ADMIN_BOT_TOKEN", FAKE_BOT_TOKEN)
    monkeypatch.setenv("ADMIN_BOT_ALLOWED_USERS", "1001,1002")
    sent = {}
    service = NotificationService(db_session)

    def capture(token, chat_id, text, parse_mode="HTML"):
        sent.update(token=token, chat_id=chat_id, text=text)
        return True

    monkeypatch.setattr(service, "_send_telegram", capture)
    service.notify_admin_new_user("<b>mallory</b>", "x&y@example.test")

    assert sent["chat_id"] == "1001"
    assert sent["token"].startswith("123456789:")
    assert "&lt;b&gt;mallory&lt;/b&gt;" in sent["text"]
    assert "x&amp;y@example.test" in sent["text"]


def test_payment_notification_guides_new_customer_to_add_device(
    db_session, monkeypatch
):
    user = _portal_user(db_session)
    monkeypatch.setenv("CLIENT_BOT_TOKEN", FAKE_BOT_TOKEN)
    sent = {}
    service = NotificationService(db_session)
    monkeypatch.setattr(
        service,
        "_send_telegram",
        lambda token, chat_id, text, parse_mode="HTML": sent.update(text=text) or True,
    )

    assert service.notify_user_payment_confirmed(
        user.id, "Business", 365, "2027-08-01"
    ) is None
    assert "Use Add Device" in sent["text"]
    assert "Use /config" not in sent["text"]


def test_bot_log_redaction_covers_current_and_unknown_tokens(monkeypatch):
    monkeypatch.setenv("ADMIN_BOT_TOKEN", FAKE_BOT_TOKEN)
    line = f"request token={FAKE_BOT_TOKEN} other={ALT_FAKE_BOT_TOKEN}"
    redacted = bot_routes._redact_log_line(line)
    assert "123456789:" not in redacted
    assert "987654321:" not in redacted
    assert redacted.count("[REDACTED_BOT_TOKEN]") == 2


def test_bot_tokens_reject_trailing_newline_injection(monkeypatch):
    from fastapi import HTTPException
    from src.modules import client_bot_admin

    injected = f"{FAKE_BOT_TOKEN}\nEVIL=value"
    with pytest.raises(HTTPException, match="Invalid admin bot token"):
        bot_routes.update_bot_config(
            bot_routes.BotConfigRequest(admin_bot_token=injected),
            SimpleNamespace(),
        )

    monkeypatch.setattr(
        client_bot_admin, "_require_client_bot_entitlement", lambda: None
    )
    with pytest.raises(HTTPException, match="Invalid client bot token"):
        client_bot_admin.prepare_client_config(
            SimpleNamespace(
                client_bot_token=injected,
                client_bot_enabled=None,
            ),
            bot_routes.mask_token,
        )


def test_client_bot_locales_keep_identical_contract():
    from src.bots.locales.de import MESSAGES as de
    from src.bots.locales.en import MESSAGES as en
    from src.bots.locales.es import MESSAGES as es
    from src.bots.locales.fr import MESSAGES as fr
    from src.bots.locales.ru import MESSAGES as ru

    for messages in (de, es, fr, ru):
        assert set(messages) == set(en)


def test_design2_bot_form_does_not_submit_paid_fields_unconditionally():
    from pathlib import Path

    source = Path("src/web/frontend/src/design2/screens/D2Bots.vue").read_text()
    assert "const payload = {}" in source
    assert "cfg.value?.client_bot_available" in source
    assert "botsApi.getLogs" in source


def test_client_bot_displays_custom_checkout_prices_instead_of_legacy_monthly():
    bot = ClientBot(FAKE_BOT_TOKEN)
    plan = SimpleNamespace(
        pricing_tiers=[
            {"days": 365, "price_usd": 199, "label": "1 year"},
            {"days": 36500, "price_usd": 699, "label": "Lifetime"},
        ],
        price_monthly_usd=12,
        price_quarterly_usd=30,
        price_yearly_usd=99,
    )

    options = bot._plan_price_options(plan, "en")
    assert options == [
        (365, 199.0, "$199.00 · 1 year"),
        (36500, 699.0, "$699.00 · Lifetime"),
    ]
    assert "$12.00" not in bot._plan_price_summary(plan, "en")


def test_client_bot_escapes_dynamic_legacy_markdown():
    bot = ClientBot(FAKE_BOT_TOKEN)
    assert bot._md("Business_Plan [2026]") == r"Business\_Plan \[2026]"


def test_client_bot_runtime_entitlement_fails_closed(monkeypatch):
    from src.modules.license import manager as license_manager

    monkeypatch.setattr(
        license_manager,
        "get_license_manager",
        lambda: SimpleNamespace(has_feature=lambda feature: feature == "telegram_client_bot"),
    )
    assert client_bot_module._has_client_bot_entitlement() is True

    monkeypatch.setattr(
        license_manager,
        "get_license_manager",
        lambda: SimpleNamespace(has_feature=lambda feature: False),
    )
    assert client_bot_module._has_client_bot_entitlement() is False

    monkeypatch.setattr(
        license_manager,
        "get_license_manager",
        lambda: (_ for _ in ()).throw(RuntimeError("license unavailable")),
    )
    assert client_bot_module._has_client_bot_entitlement() is False


@pytest.mark.asyncio
async def test_restart_all_skips_unconfigured_services_and_audits_restarts(
    db_session, monkeypatch
):
    from src.modules import client_bot_admin

    monkeypatch.setenv(
        "ADMIN_BOT_TOKEN", FAKE_BOT_TOKEN
    )
    monkeypatch.setenv("ADMIN_BOT_ALLOWED_USERS", "1001")
    monkeypatch.setenv(
        "CLIENT_BOT_TOKEN", ALT_FAKE_BOT_TOKEN
    )
    monkeypatch.setenv("CLIENT_BOT_ENABLED", "true")
    calls = []
    monkeypatch.setattr(
        bot_routes,
        "control_service",
        lambda service, action: calls.append((service, action)) or True,
    )
    monkeypatch.setattr(
        client_bot_admin,
        "restart_client_if_entitled",
        lambda control: control("vpnmanager-client-bot", "restart"),
    )

    result = await bot_routes.restart_all_bots(db_session)

    assert result == {"admin_bot": "restarted", "client_bot": "restarted"}
    assert calls == [
        ("vpnmanager-admin-bot", "restart"),
        ("vpnmanager-client-bot", "restart"),
    ]
    assert db_session.query(bot_routes.AuditLog).filter_by(
        target_type="telegram_bot"
    ).count() == 2
