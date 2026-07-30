"""Contracts for the extracted Enterprise branding routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.routes import system, system_branding


def test_shared_system_module_only_mounts_the_branding_router():
    source = Path("src/api/routes/system.py").read_text(encoding="utf-8")

    assert "router.include_router(system_branding.router)" in source
    assert "class BrandingUpdateRequest" not in source
    assert "def upload_branding_logo" not in source
    assert "set_branding(" not in source


def test_branding_route_contract_is_preserved():
    # FastAPI 0.139 keeps included routers as lazy _IncludedRouter objects
    # instead of eagerly flattening them into ``router.routes``. Name-based
    # resolution exercises the supported API and works on both layouts.
    assert str(system.router.url_path_for("get_branding_settings")) == "/branding"
    assert str(system.router.url_path_for("update_branding_settings")) == "/branding"
    assert str(system.router.url_path_for("upload_branding_logo")) == "/branding/logo"

    methods_by_path = {}
    for route in system_branding.router.routes:
        methods_by_path.setdefault(route.path, set()).update(route.methods)
    assert {"GET", "POST"}.issubset(methods_by_path["/branding"])
    assert "POST" in methods_by_path["/branding/logo"]


def test_legal_content_validators_preserve_safe_urls_and_reject_javascript():
    payload = system_branding.BrandingUpdateRequest(
        branding_privacy_url="/privacy",
        branding_terms_url="https://vpn.example/terms",
        branding_privacy_text="Plain operator policy",
    )
    assert payload.branding_privacy_url == "/privacy"

    with pytest.raises(ValidationError):
        system_branding.BrandingUpdateRequest(
            branding_privacy_url="javascript:alert(1)",
        )


def test_legal_text_rejects_nul_bytes():
    with pytest.raises(ValidationError):
        system_branding.BrandingUpdateRequest(
            branding_terms_text="terms\x00hidden",
        )
