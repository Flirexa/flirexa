"""Paid-license compatibility contracts for protected runtime migrations.

These tests intentionally model both current signed feature lists and the
small marker sets carried by older lifetime keys.  Moving implementation files
or changing their packaging must never silently remove a capability that an
existing Business or Enterprise licence already covered.
"""

from src.modules.license.manager import LICENSE_TIERS, LicenseInfo, LicenseType


BUSINESS_FEATURES = {
    "wireguard",
    "amneziawg",
    "proxy_protocols",
    "client_portal",
    "telegram_bots",
    "telegram_client_bot",
    "nowpayments",
    "payments",
    "multi_server",
    "mikrotik_adapter",
    "traffic_rules",
    "android_app",
    "white_label_basic",
    "auto_backup",
    "promo_codes",
    "auto_renewal",
}

ENTERPRISE_ONLY_FEATURES = {
    "white_label",
    "corporate_vpn",
    "manager_rbac",
    "app_integration",
}


def _info(license_type: LicenseType, features: list[str]) -> LicenseInfo:
    tier = LICENSE_TIERS[license_type]
    return LicenseInfo(
        type=license_type,
        max_clients=tier["max_clients"],
        max_servers=tier["max_servers"],
        features=features,
    )


def test_current_business_fallback_keeps_every_sold_capability_and_limit():
    tier = LICENSE_TIERS[LicenseType.BUSINESS]

    assert set(tier["features"]) == BUSINESS_FEATURES
    assert tier["max_clients"] == 2_000
    assert tier["max_servers"] == 10


def test_current_enterprise_fallback_is_a_strict_business_superset():
    tier = LICENSE_TIERS[LicenseType.ENTERPRISE]
    features = set(tier["features"])

    assert BUSINESS_FEATURES <= features
    assert ENTERPRISE_ONLY_FEATURES <= features
    assert tier["max_clients"] >= 999_999
    assert tier["max_servers"] >= 999_999


def test_legacy_business_markers_still_unlock_current_business_bundle():
    # Representative feature set from keys issued before the canonical names
    # were consolidated.  Aliases may grant new names only within the same
    # purchased tier.
    info = _info(
        LicenseType.BUSINESS,
        [
            "wireguard",
            "amneziawg",
            "extra_protocols",
            "client_portal",
            "telegram_admin_bot",
            "client_tg_bot",
            "multi_server",
        ],
    )

    assert all(info.has_feature(feature) for feature in BUSINESS_FEATURES)
    assert not any(info.has_feature(feature) for feature in ENTERPRISE_ONLY_FEATURES)


def test_legacy_enterprise_marker_keeps_later_enterprise_capabilities():
    info = _info(
        LicenseType.ENTERPRISE,
        [
            "wireguard",
            "amneziawg",
            "extra_protocols",
            "client_portal",
            "telegram_admin_bot",
            "client_tg_bot",
            "multi_server",
            "white_label",
        ],
    )

    expected = BUSINESS_FEATURES | ENTERPRISE_ONLY_FEATURES
    assert all(info.has_feature(feature) for feature in expected)
