from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "src/web/frontend/src/design2/screens/D2DnsProtection.vue"
LOCALES = ("en", "ru", "de", "fr", "es")


def _private_screen_source():
    source = SCREEN.read_text(encoding="utf-8")
    if "FLIREXA_COMMERCIAL_STUB = True" in source:
        pytest.skip("commercial design2 implementation is intentionally private")
    return source


def test_dns_protection_uses_localized_design2_surface():
    source = _private_screen_source()

    assert "useI18n" in source
    assert "d2confirm" in source
    assert "dnsProtection.heroTitle" in source
    assert "dnsProtection.modes.${profile.mode}.${field}" in source
    assert "watch(locale, syncShell)" in source
    assert "background:var(--accent-soft)" not in source
    assert "color-mix" not in source


def test_dns_protection_mobile_layout_has_no_overlap_hacks():
    source = _private_screen_source()

    assert "@media(max-width:680px)" in source
    assert "grid-template-columns:38px minmax(0,1fr)" in source
    assert ".dns-section-head{align-items:flex-start;flex-direction:column" in source
    assert "margin-left:-56px" not in source
    assert "position:absolute;right:38px" not in source
    assert "if (!confirm(" not in source


def test_dns_protection_is_translated_for_every_admin_locale():
    for locale in LOCALES:
        source = (ROOT / f"src/web/frontend/src/i18n/locales/{locale}.js").read_text(encoding="utf-8")
        assert "dnsProtection:" in source, locale
        assert "heroTitle:" in source, locale
        assert "ads_trackers_malware:" in source, locale
        assert "policyApplyFailed:" in source, locale
