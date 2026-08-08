"""Regression contracts for the paid-customer UI feedback fixed in 2.2.68."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.routes.system_branding import BrandingUpdateRequest
from src.modules.branding import BRANDING_DEFAULTS


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_design2_server_cards_consume_the_server_clients_envelope():
    source = _read("src/web/frontend/src/design2/screens/D2Servers.vue")
    assert "Array.isArray(data?.clients)" in source
    assert "c.ipv4 || c.ip_address" in source
    assert "c.traffic_used_rx" in source


def test_design2_server_migration_and_key_export_keep_legacy_safety_contract():
    source = _read("src/web/frontend/src/design2/screens/D2Servers.vue")
    assert "s.agent_mode !== 'mikrotik'" in source
    assert "kp.data.awg_params" in source
    assert "copyText(kp.data.private_key)" in source
    assert "x.public_key === mig.source.public_key" in source
    assert "sync_to_remote: mig.syncRemote" in source
    assert "remove_from_old: mig.keepSource ? false : mig.removeSource" in source
    assert "keep_on_source: mig.keepSource" in source
    assert "payload.client_ids" in source


def test_design2_add_server_cards_keep_dark_theme_text_color():
    source = _read("src/web/frontend/src/design2/screens/D2Servers.vue")
    card_style = source[source.index("function cardStyle"):source.index("function setCategory")]
    assert "color: 'var(--text)'" in card_style


def test_design2_add_and_discover_server_support_explicit_ssh_private_keys():
    source = _read("src/web/frontend/src/design2/screens/D2Servers.vue")

    assert "ns.ssh_auth_method === 'private_key'" in source
    assert 'v-model="ns.ssh_private_key"' in source
    assert 'v-model="disc.form.ssh_private_key"' in source
    assert "ssh_auth_method: 'password'" in source
    assert "p.ssh_private_key = p.ssh_private_key?.trim()" in source
    assert "delete p.ssh_password" in source
    assert "delete p.ssh_auth_method" in source
    assert "serversApi.discover(payload)" in source
    assert "ns.value.ssh_private_key = ''" in source
    assert "disc.form.ssh_private_key = ''" in source


def test_paid_panels_hide_donation_automatically():
    app = _read("src/web/frontend/src/App.vue")
    shell = _read("src/web/frontend/src/design2/shell/D2Shell.vue")
    navbar = _read("src/web/frontend/src/components/Navbar.vue")

    new_branch = app[app.index('v-else-if="design.isNew"'):app.index("<!-- Legacy variant")]
    assert "DonateModal" not in new_branch
    assert ':show-donate="showLegacyDonate"' in app
    assert 'v-if="showLegacyDonate" v-model="donateOpen"' in app
    assert "setTimeout(() => { donateOpen.value = true }" not in app
    assert "license.loaded && !license.isPaid" in app

    assert "license.loaded && !license.isPaid" in shell
    assert 'v-if="showDonate" @click="donate"' in shell
    assert 'v-if="showDonate" class="topbar-donate-pill"' in navbar


def test_enterprise_attribution_toggle_also_controls_admin_github_link():
    shell = _read("src/web/frontend/src/design2/shell/D2Shell.vue")
    store = _read("src/web/frontend/src/stores/branding.js")
    assert 'v-if="showProjectAttribution" href="https://github.com/Flirexa/flirexa"' in shell
    assert "branding.poweredBy !== false" in shell
    assert "data.branding_powered_by" in store


def test_customer_legal_pages_accept_safe_urls_and_plain_text():
    branding_source = _read("src/modules/branding.py")
    if "FLIREXA_COMMERCIAL_STUB = True" not in branding_source:
        assert "branding_privacy_url" in BRANDING_DEFAULTS
        assert "branding_terms_url" in BRANDING_DEFAULTS
        assert "branding_privacy_text" in BRANDING_DEFAULTS
        assert "branding_terms_text" in BRANDING_DEFAULTS
    payload = BrandingUpdateRequest(
        branding_privacy_url="https://vpn.example/privacy",
        branding_terms_url="/legal/terms",
        branding_privacy_text="We collect only account and service data.\n\nContact us for deletion.",
        branding_terms_text="Use the service lawfully.",
    )
    assert payload.branding_terms_url == "/legal/terms"
    assert "Contact us" in payload.branding_privacy_text

    with pytest.raises(ValidationError):
        BrandingUpdateRequest(branding_terms_url="javascript:alert(1)")

    with pytest.raises(ValidationError):
        BrandingUpdateRequest(branding_terms_url="//malicious.example/terms")

    with pytest.raises(ValidationError):
        BrandingUpdateRequest(branding_privacy_text="invalid\x00text")

    for component in (
        "src/web/client-portal/src/views/Login.vue",
        "src/web/client-portal/src/views/Register.vue",
        "src/web/client-portal/src/components/Layout.vue",
    ):
        source = _read(component)
        assert "legalDocumentHref('terms')" in source
        assert "legalDocumentHref('privacy')" in source

    settings = _read("src/web/frontend/src/design2/screens/D2Settings.vue")
    assert 'v-model="brand.privacy_text"' in settings
    assert 'v-model="brand.terms_text"' in settings
    assert "branding_privacy_text: brand.privacy_text" in settings
    assert "branding_terms_text: brand.terms_text" in settings


def test_customer_portal_applies_the_complete_brand_colour_before_mount():
    branding = _read("src/web/client-portal/src/branding.js")
    main = _read("src/web/client-portal/src/main.js")
    app = _read("src/web/client-portal/src/App.vue")
    for token in (
        "--accent-50",
        "--accent-900",
        "--accent-fg",
        "--vxy-primary",
        "--bs-primary-rgb",
    ):
        assert token in branding
    assert "data.branding_primary_color" in branding
    assert "applyPortalBranding(data)" in main
    assert main.index("applyPortalBranding(data)") < main.index("app.mount('#app')")
    assert "applyPortalBranding(data)" in app


def test_branding_preview_switches_between_admin_and_customer_surfaces():
    settings = _read("src/web/frontend/src/design2/screens/D2Settings.vue")
    preview = _read("src/web/frontend/src/design2/ui/D2BrandingPreview.vue")

    assert "import D2BrandingPreview" in settings
    assert '<D2BrandingPreview :brand="brand" />' in settings
    if "FLIREXA_COMMERCIAL_STUB = True" in preview:
        assert "white_label_basic" in preview
        return
    assert "const previewMode = ref('client')" in preview
    assert "previewMode === 'admin'" in preview
    assert "previewMode === 'client'" in preview
    assert ':data-preview-mode="previewMode"' in preview
    assert "brand.value.customer_logo_url || brand.value.logo_url" in preview
    assert "brand.value.brand_name || brand.value.customer_app_name" in preview
    assert "clientMetaLinks" in preview
    assert "privacy_url || brand.value.privacy_text" in preview
    assert "terms_url || brand.value.terms_text" in preview
    assert "support_url || brand.value.support_email" in preview
    assert "--bp-accent-fg" in preview
    assert "<iframe" not in preview
    assert "v-html" not in preview


def test_design2_license_actions_execute_real_recovery_and_validation_flows():
    settings = _read("src/web/frontend/src/design2/screens/D2Settings.vue")

    assert 'v-model="license.replayCode"' in settings
    assert "systemApi.replayLicense({ activation_code: activationCode })" in settings
    assert "systemApi.triggerLicenseCheck()" in settings
    assert "licServer.last_check !== previousCheck" in settings
    assert "Expected briefly when an in-band licence rotation restarts services" in settings
    assert ":disabled=\"busy.refresh || !licensed\"" in settings
    assert "async function refetchLicense() { await loadLicense()" not in settings


def test_admin_server_api_consumes_the_complete_paginated_fleet():
    api = _read("src/web/frontend/src/api/index.js")

    assert "getAll: async () =>" in api
    assert "const pageSize = 500" in api
    assert "while (offset < total)" in api
    assert "items.push(...page)" in api
    assert "data: { ...body, items, limit: items.length, offset: 0 }" in api
