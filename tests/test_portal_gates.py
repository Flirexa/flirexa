"""Per-operator client-portal feature gates (portal_gates helper).

A `portal_no_*` deny-flag in the operator's license HIDES that capability in
their portal. No flag → everything ON (backward compatible). A license read
error must fail OPEN so a hiccup never disables a capability for everyone.
"""
from src.modules.license import portal_gates as pg


def _info(features):
    """Minimal stand-in for LicenseInfo.has_feature."""
    return type("I", (), {"has_feature": lambda self, f: f in features})()


class TestPortalGates:
    def test_no_flags_everything_on(self):
        g = pg.portal_gates(_info([]))
        assert g == {"config_download": True, "qr": True}

    def test_config_download_denied(self):
        g = pg.portal_gates(_info(["portal_no_config_download"]))
        assert g["config_download"] is False
        assert g["qr"] is True

    def test_qr_denied(self):
        g = pg.portal_gates(_info(["portal_no_qr"]))
        assert g["qr"] is False
        assert g["config_download"] is True

    def test_both_denied(self):
        g = pg.portal_gates(_info(["portal_no_config_download", "portal_no_qr"]))
        assert g == {"config_download": False, "qr": False}

    def test_unrelated_feature_ignored(self):
        g = pg.portal_gates(_info(["app_integration", "multi_server"]))
        assert g == {"config_download": True, "qr": True}

    def test_has_feature_raises_fails_open_per_flag(self):
        boom = type("I", (), {"has_feature": lambda self, f: (_ for _ in ()).throw(RuntimeError())})()
        # a per-flag read error is treated as "not denied" → capability stays ON
        assert pg.portal_gates(boom) == {"config_download": True, "qr": True}

    def test_no_license_manager_fails_open(self, monkeypatch):
        # get_license_manager blowing up must yield everything-ON, not a crash.
        monkeypatch.setattr(
            "src.modules.license.manager.get_license_manager",
            lambda: (_ for _ in ()).throw(RuntimeError("no license")),
        )
        assert pg.portal_gates() == {"config_download": True, "qr": True}

    def test_is_gated_reflects_flag(self, monkeypatch):
        monkeypatch.setattr(pg, "portal_gates",
                            lambda *a, **k: {"config_download": False, "qr": True})
        assert pg.is_gated("config_download") is True
        assert pg.is_gated("qr") is False
        # unknown capability defaults to NOT gated (available)
        assert pg.is_gated("nonexistent") is False
