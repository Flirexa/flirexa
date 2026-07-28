from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_landing_emits_first_party_analytics_contract():
    js = (ROOT / "landing" / "app.v2.js").read_text(encoding="utf-8")

    assert "'/api/visit'" in js
    assert "'/api/heartbeat'" in js
    assert "'/api/copy-install'" in js
    assert "document.referrer" in js
    assert "sessionStorage.setItem('flx_analytics_sid'" in js
    assert "navigator.sendBeacon" in js
    assert "localStorage.setItem('flx-theme'" not in js


def test_privacy_copy_matches_current_storage_and_analytics():
    privacy = (ROOT / "landing" / "privacy.html").read_text(encoding="utf-8")

    assert privacy.count("flirexa_lang") == 6
    assert privacy.count("sessionStorage") == 6
    assert "vpnm-lang" not in privacy
    assert "does not use cookies, analytics scripts" not in privacy
