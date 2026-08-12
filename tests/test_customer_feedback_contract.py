"""Regression contracts for the paid-customer UI feedback fixed in 2.2.68."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.routes.system_branding import BrandingUpdateRequest
from src.api.routes.server_schemas import ServerUpdate
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


def test_design2_can_edit_client_endpoint_dns_and_server_metadata_safely():
    source = _read("src/web/frontend/src/design2/screens/D2Servers.vue")

    assert "tr('servers.editServer')" in source
    assert 'v-model="edit.form.endpoint"' in source
    assert 'v-model="edit.form.dns"' in source
    assert "This does not change the VPS or SSH address" in source
    assert "Manually downloaded configuration files must be downloaded again" in source
    assert "await serversApi.update(edit.serverId, payload)" in source
    assert "Array.isArray(detail)" in source


def test_design2_does_not_use_pale_orange_warning_surfaces():
    tokens = _read("src/web/frontend/src/design2/tokens.css")
    assert "--amber-soft: var(--panel-2)" in tokens
    assert "#fde6d3" not in tokens.lower()
    assert "rgba(251, 146, 60" not in tokens


def test_design2_mobile_layout_keeps_table_card_conversion_opt_in():
    css = _read("src/web/frontend/src/design2/handoff.css")
    shell = _read("src/web/frontend/src/design2/shell/D2Shell.vue")
    mobile_css = css.split("/* mobile", 1)[1]

    assert "@media (max-width: 900px)" in mobile_css
    assert ".d2-root table[data-rtab]" in mobile_css
    assert ".d2-root table[data-mobile-cards]" in mobile_css
    assert "\n  .d2-root table {" not in mobile_css
    assert '.d2-root div[style*="overflow-x:auto"]' not in mobile_css
    assert "if (window.innerWidth > 900) return" in shell
    assert "document.addEventListener('click', onMobileTableClick, true)" in shell
    assert "document.removeEventListener('click', onMobileTableClick, true)" in shell

    for screen in Path("src/web/frontend/src/design2/screens").glob("*.vue"):
        source = screen.read_text(encoding="utf-8")
        if "data-rcollapse" in source:
            assert "data-rtab data-rcollapse" in source, screen


def test_design2_mobile_admin_screens_have_compact_explicit_contracts():
    shell = _read("src/web/frontend/src/design2/shell/D2Shell.vue")
    css = _read("src/web/frontend/src/design2/handoff.css")
    online = _read("src/web/frontend/src/design2/screens/D2OnlineUsers.vue")
    clients = _read("src/web/frontend/src/design2/screens/D2Clients.vue")
    subscriptions = _read("src/web/frontend/src/design2/screens/D2Subscriptions.vue")
    health = _read("src/web/frontend/src/design2/screens/D2SystemHealth.vue")
    settings = _read("src/web/frontend/src/design2/screens/D2Settings.vue")

    assert 'class="d2-mobile-actions"' in shell
    assert 'class="d2-mobile-primary"' in shell
    assert 'class="d2-mobile-menu"' in shell
    assert 'class="d2-mobile-search"' in shell
    assert ".d2-desktop-actions { display:none !important; }" in shell
    assert "grid-template-columns:34px minmax(0,1fr) auto" in shell
    assert "td[data-mprimary]" in css
    assert 'class="d2-ou-server-select"' in online
    assert "function onServerSelect" in online
    assert 'class="d2-clients-mobile"' in clients
    assert 'class="d2-client-mobile-row"' in clients
    assert 'D2MobileSheet' in clients
    assert "flirexa:d2:clients-mobile-fields" in clients
    assert "isMobilePrimary('server')" in clients
    assert 'class="d2-ou-mobile"' in online
    assert 'class="d2-ou-mobile-card"' in online
    assert 'class="d2-plans-mobile"' in subscriptions
    assert 'class="d2-plan-mobile-row"' in subscriptions
    assert 'D2MobileSheet' in subscriptions
    assert 'class="d2-health-banner"' in health
    assert "obj.target_name" in health
    assert "obj.current_status" in health
    assert "i.data.recent_recoveries" in health
    assert 'class="d2-settings-mobile-nav"' in settings
    assert 'class="d2-settings-rail"' in settings
    assert "function selectSettingsTab" in settings
    assert 'class="d2-license-mobile"' in settings
    assert 'class="d2-license-desktop"' in settings
    assert 'licenseSheet = \'details\'' in settings
    assert 'class="d2-settings-picker-list"' in settings
    assert '.d2-license-desktop { display:none !important; }' in settings
    assert '.d2-settings-actionbar.has-three > button:first-child' in settings
    assert '<select :value="active"' not in settings

    mobile_actions = shell.split('<div class="d2-mobile-actions">', 1)[1].split('</div>\n\n        <div v-if="ui.onSearch', 1)[0]
    overflow_menu = mobile_actions.split('<div v-if="mobileMenuOpen" class="d2-mobile-menu">', 1)[1]
    assert 'd2-mobile-language-btn' in mobile_actions
    assert 'd2-mobile-github' in mobile_actions
    assert 'd2-mobile-theme' in mobile_actions
    assert 'd2-mobile-languages' not in overflow_menu
    assert '>GitHub<' not in overflow_menu

    backup = _read("src/web/frontend/src/design2/screens/D2Backup.vue")
    assert 'class="d2-backup-mobile-tabs"' in backup
    assert 'class="d2-backup-mobile-row"' in backup
    assert "mobile-archives" in backup
    assert ':disabled="creating"' in backup


def test_design2_remaining_operational_screens_have_mobile_first_surfaces():
    """Desktop tables must not become squeezed phone-width spreadsheets."""
    screens = {
        "D2Dashboard.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2Payments.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2PortalUsers.vue": ("d2-desktop-only", "d2-portal-mobile-user"),
        "D2Logs.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2Updates.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2PromoCodes.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2Applications.vue": ("d2-desktop-only", "d2-mobile-list"),
        "D2Notifications.vue": ("d2-desktop-only", "d2-mobile-list"),
    }
    root = Path("src/web/frontend/src/design2/screens")
    for filename, markers in screens.items():
        source = (root / filename).read_text(encoding="utf-8")
        if "FLIREXA_COMMERCIAL_STUB = True" in source:
            continue
        for marker in markers:
            assert marker in source, f"{filename} is missing {marker}"

    support = (root / "D2Support.vue").read_text(encoding="utf-8")
    assert "d2-support-hidden-mobile" in support
    assert "d2-support-back" in support

    shared = _read("src/web/frontend/src/design2/handoff.css")
    assert ".d2-root .d2-mobile-only { display: none !important; }" in shared
    assert ".d2-root .d2-desktop-only { display: none !important; }" in shared
    assert ".d2-root .d2-mobile-kv" in shared


def test_system_health_ui_does_not_collide_with_liveness_endpoint():
    router = _read("src/web/frontend/src/router/index.js")
    nav = _read("src/web/frontend/src/design2/nav.js")

    assert "path: '/system-health'" in router
    assert "health: { path: '/system-health'" in nav
    assert "path: '/health',\n    name: 'SystemHealth'" not in router


def test_server_update_validates_client_endpoint_and_dns():
    update = ServerUpdate(
        endpoint="vpn.example.com:51820",
        dns=" 1.1.1.1, 2606:4700:4700::1111 ",
    )
    assert update.endpoint == "vpn.example.com:51820"
    assert update.dns == "1.1.1.1,2606:4700:4700::1111"
    assert ServerUpdate(endpoint="[2001:db8::1]:51820").endpoint == "[2001:db8::1]:51820"

    for payload in (
        {"endpoint": "not-an-endpoint"},
        {"endpoint": "example.com:70000"},
        {"endpoint": "2001:db8::1:51820"},
        {"dns": "1.1.1.999"},
        {"dns": "1.1.1.1,,8.8.8.8"},
    ):
        with pytest.raises(ValidationError):
            ServerUpdate(**payload)


def test_server_response_returns_dns_for_edit_form_round_trip():
    source = _read("src/api/routes/server_schemas.py")
    assert "dns: Optional[str] = None" in source
    assert "dns=getattr(server, 'dns', None)" in source


def test_paid_panels_hide_donation_automatically():
    app = _read("src/web/frontend/src/App.vue")
    shell = _read("src/web/frontend/src/design2/shell/D2Shell.vue")

    assert "useDesignMode" not in app
    assert "showLegacyDonate" not in app
    assert "components/DonateModal" not in app
    assert "license.loaded && !license.isPaid" in shell
    assert 'v-if="showDonate" @click="donate"' in shell
    assert "setTimeout(() => { donateOpen.value = true }" not in shell


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
