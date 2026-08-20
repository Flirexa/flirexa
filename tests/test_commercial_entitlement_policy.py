"""Regression tests for paid-feature boundaries exposed by the public API."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.api.middleware.license_gate import feature_required_detail
from src.api.routes.servers import _enforce_server_creation_entitlement
from src.api.routes.system import (
    PaymentSettingsUpdate,
    _APP_INTEGRATION_SETTING_FIELDS,
)
from src.modules.payment_settings_commercial import PAID_SETTING_FIELDS
from src.modules.license.manager import LicenseInfo, LicenseType


def _license(kind: LicenseType, *, max_servers: int, features=()):
    return LicenseInfo(
        type=kind,
        max_clients=100,
        max_servers=max_servers,
        features=list(features),
    )


def _blocked(call, feature: str, tier: str):
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == 403
    assert exc.value.detail["license_feature_required"] == feature
    assert exc.value.detail["upgrade_tier"] == tier
    assert exc.value.detail["upgrade_url"].endswith("#pricing")


def test_upgrade_payload_uses_current_public_plan_names():
    assert feature_required_detail("promo_codes")["upgrade_tier"] == "starter"
    assert feature_required_detail("payments")["upgrade_tier"] == "business"
    assert feature_required_detail("dns_protection")["upgrade_tier"] == "business"
    assert feature_required_detail("dns_policy_advanced")["upgrade_tier"] == "enterprise"
    assert feature_required_detail("app_integration")["upgrade_tier"] == "enterprise"
    assert feature_required_detail("white_label_basic")["upgrade_tier"] == "enterprise"


def test_business_cannot_infer_appearance_or_app_entitlements():
    info = _license(LicenseType.BUSINESS, max_servers=10, features=("multi_server",))
    for feature in ("white_label", "white_label_basic", "android_app", "app_integration", "dns_policy_advanced"):
        assert info.has_feature(feature) is False


def test_explicit_legacy_business_flags_remain_grandfathered():
    info = _license(
        LicenseType.BUSINESS,
        max_servers=10,
        features=("multi_server", "white_label_basic", "android_app"),
    )
    assert info.has_feature("white_label") is True
    assert info.has_feature("app_integration") is True
    assert info.has_feature("corporate_vpn") is False
    assert info.has_feature("manager_rbac") is False


def test_design2_locks_enterprise_appearance_and_apps_with_common_prompt():
    source = Path("src/web/frontend/src/design2/screens/D2Settings.vue").read_text(encoding="utf-8")
    assert "feature: 'white_label', tier: 'enterprise'" in source
    assert "feature: 'app_integration', tier: 'enterprise'" in source
    assert "flirexa:upgrade-required" in source


def test_free_allows_one_local_wireguard_and_one_local_amneziawg():
    info = _license(LicenseType.FREE, max_servers=2, features=("wireguard", "amneziawg"))
    _enforce_server_creation_entitlement(
        info, current_count=0, same_type_count=0,
        server_type="wireguard", is_remote=False,
    )
    _enforce_server_creation_entitlement(
        info, current_count=1, same_type_count=0,
        server_type="amneziawg", is_remote=False,
    )


def test_free_cannot_add_remote_duplicate_or_proxy_server():
    info = _license(LicenseType.FREE, max_servers=2, features=("wireguard", "amneziawg"))
    _blocked(
        lambda: _enforce_server_creation_entitlement(
            info, current_count=0, same_type_count=0,
            server_type="wireguard", is_remote=True,
        ),
        "multi_server", "business",
    )
    _blocked(
        lambda: _enforce_server_creation_entitlement(
            info, current_count=1, same_type_count=1,
            server_type="wireguard", is_remote=False,
        ),
        "multi_server", "business",
    )
    _blocked(
        lambda: _enforce_server_creation_entitlement(
            info, current_count=1, same_type_count=0,
            server_type="hysteria2", is_remote=False,
        ),
        "proxy_protocols", "starter",
    )


def test_signed_starter_and_business_server_limits_are_authoritative():
    starter = _license(
        LicenseType.STARTER,
        max_servers=1,
        features=("proxy_protocols",),
    )
    _blocked(
        lambda: _enforce_server_creation_entitlement(
            starter, current_count=1, same_type_count=0,
            server_type="hysteria2", is_remote=False,
        ),
        "multi_server", "business",
    )

    business = _license(
        LicenseType.BUSINESS,
        max_servers=10,
        features=("proxy_protocols", "multi_server"),
    )
    _enforce_server_creation_entitlement(
        business, current_count=9, same_type_count=8,
        server_type="hysteria2", is_remote=True,
    )
    _blocked(
        lambda: _enforce_server_creation_entitlement(
            business, current_count=10, same_type_count=8,
            server_type="hysteria2", is_remote=True,
        ),
        "multi_server", "enterprise",
    )


def test_payment_settings_split_nowpayments_from_business_providers():
    free_payload = PaymentSettingsUpdate(nowpayments_api_key="np", nowpayments_sandbox=True)
    assert not (free_payload.model_fields_set & PAID_SETTING_FIELDS)

    for field in (
        "cryptopay_api_token", "paypal_client_id", "stripe_secret_key",
        "payme_merchant_id", "mollie_api_key", "razorpay_key_id",
    ):
        assert field in PAID_SETTING_FIELDS


def test_unknown_payment_provider_is_not_treated_as_free():
    from src.api.routes.payments import _require_paid_provider

    info = _license(LicenseType.FREE, max_servers=2, features=("nowpayments",))
    manager = type("Manager", (), {"get_license_info": lambda self: info})()
    with patch(
        "src.modules.license.manager.get_license_manager",
        return_value=manager,
    ):
        _require_paid_provider("nowpayments")
        _require_paid_provider("mock")
        _blocked(
            lambda: _require_paid_provider("future-card-plugin"),
            "payments", "business",
        )


def test_push_integration_settings_are_all_enterprise_fields():
    assert {
        "fcm_server_key", "app_integration_enabled", "push_enabled", "app_name"
    } == _APP_INTEGRATION_SETTING_FIELDS


def test_operator_feature_resolution_fails_closed():
    from src.api.routes.client_portal import _operator_has_feature

    with patch(
        "src.modules.license.manager.get_license_manager",
        side_effect=RuntimeError("license cache unavailable"),
    ):
        assert _operator_has_feature("payments") is False


def test_portal_promo_decoration_cannot_hide_duration_or_block_checkout_load():
    source = Path(
        "src/web/client-portal/src/views/PaymentModal.vue"
    ).read_text(encoding="utf-8")

    duration_pos = source.index("{{ $t('pay.duration') }}")
    duration_wrapper = source[source.rfind("<div", 0, duration_pos):duration_pos]
    assert "operatorFeatures.promo_codes" not in duration_wrapper

    promo_pos = source.index('class="fx-payment-field"', duration_pos)
    promo_block = source[source.rfind("<div", duration_pos, promo_pos):promo_pos + 80]
    assert 'v-if="operatorFeatures.promo_codes"' in promo_block

    # Plans/providers are the purchase-critical Promise.all. The optional
    # feature request is deliberately made afterwards under its own try/catch.
    promise_block = source[source.index("const [plansRes"):source.index("plans.value =")]
    assert "getFeatures" not in promise_block
