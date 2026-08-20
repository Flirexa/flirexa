import base64
import re
from pathlib import Path


DEMO = Path("landing/demo-next")
INDEX = DEMO / "index.html"
SCRIPT = DEMO / "demo.js"
AUTHENTIC_SOURCE = Path("src/web/frontend/src/demo-admin")
AUTHENTIC_INDEX = AUTHENTIC_SOURCE / "index.html"
AUTHENTIC_APP = AUTHENTIC_SOURCE / "App.vue"
AUTHENTIC_MAIN = AUTHENTIC_SOURCE / "main.js"
AUTHENTIC_ROUTER = AUTHENTIC_SOURCE / "router.js"
AUTHENTIC_MOCK = AUTHENTIC_SOURCE / "mockAdapter.js"
PORTAL_SOURCE = Path("src/web/client-portal/src/demo")
PORTAL_INDEX = PORTAL_SOURCE / "index.html"
PORTAL_APP = PORTAL_SOURCE / "DemoApp.vue"
PORTAL_LOGIN = Path("src/web/client-portal/src/views/Login.vue")
PORTAL_MAIN = PORTAL_SOURCE / "main.js"
PORTAL_ROUTER = PORTAL_SOURCE / "router.js"
PORTAL_MOCK = PORTAL_SOURCE / "mockAdapter.js"
ADMIN_I18N = Path("src/web/frontend/src/i18n/index.js")
PORTAL_I18N = Path("src/web/client-portal/src/i18n/index.js")
DEMO_QR = Path("src/web/demo/demoQr.js")
D2_SHELL = Path("src/web/frontend/src/design2/shell/D2Shell.vue")
LIVE_INDEX = Path("landing/index.html")
APP_ASSETS = DEMO / "assets" / "apps"
APP_VARIANT_INDEX = Path("landing/demo-next-apps/index.html")


def test_candidate_demo_is_static_and_cannot_call_a_backend():
    index = INDEX.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "connect-src 'none'" in index
    assert "form-action 'none'" in index
    assert "<script src=\"demo.js\" defer></script>" in index
    for network_primitive in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "sendBeacon",
        "axios",
    ):
        assert network_primitive not in script


def test_candidate_demo_uses_exact_synthetic_business_numbers():
    script = SCRIPT.read_text(encoding="utf-8")
    server_block = script.split("const servers = [", 1)[1].split(
        "].map((v,i)=>", 1
    )[0]
    client_counts = [
        int(value)
        for value in re.findall(
            r"\['[^']+','[^']+','[^']+','[^']+',([0-9]+),", server_block
        )
    ]

    assert len(client_counts) == 17
    assert sum(client_counts) == 7977
    assert "'7,977'" in script
    assert "'$31,908'" in script
    assert "'$382,896'" in script
    assert "at $4.00 average revenue" in script


def test_admin_and_client_portal_are_presented_as_separate_apps():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "Run your entire VPN business" in script
    assert "Built for a commercial VPN service" in script
    assert "admin.example.com" in script
    assert "account.example.com" in script
    assert "This customer account exists only in the Client Portal" in script
    assert "does not provide access to the Flirexa Admin Panel" in script
    assert "data-action=\"portal-login\"" in script
    assert "data-action=\"portal-menu\"" in script
    assert "data-modal-portal-page" in script


def test_picker_opens_both_authentic_applications():
    script = SCRIPT.read_text(encoding="utf-8")
    app = AUTHENTIC_APP.read_text(encoding="utf-8")

    assert "function authenticDemoUrl(application, hash = '')" in script
    assert "params.set('lang', state.lang)" in script
    assert "window.location.href=authenticDemoUrl('admin')" in script
    assert "window.location.href=authenticDemoUrl('portal','#/login')" in script
    assert "data-action=\"choose-portal\"" in script
    assert "`/demo/?lang=${encodeURIComponent(locale.value || 'en')}`" in app


def test_authentic_apps_apply_the_selected_demo_locale_before_mount():
    admin = AUTHENTIC_MAIN.read_text(encoding="utf-8")
    portal = PORTAL_MAIN.read_text(encoding="utf-8")

    for source in (admin, portal):
        assert "new URLSearchParams(window.location.search).get('lang')" in source
        assert "const supportedDemoLocales = ['en', 'ru', 'de', 'fr', 'es']" in source
        assert "i18n.global.locale.value = demoLocale" in source
        assert "document.documentElement.lang = demoLocale" in source
        assert "localStorage.setItem('flirexa_lang', demoLocale)" in source
        assert "window.__FLIREXA_DEMO_LOCALE__ = demoLocale" in source
        assert "app.mount('#app')" in source
    for source in (ADMIN_I18N, PORTAL_I18N):
        bootstrap = source.read_text(encoding="utf-8")
        assert "window.location.pathname.includes('/demo-authentic/')" in bootstrap
        assert "locale: initialLocale" in bootstrap


def test_picker_uses_the_official_logo_and_translates_all_supported_languages():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "flirexa-logo-globe-v2-transparent.png" in script
    assert "pickerTranslations" in script


def test_picker_uses_the_shared_site_header_and_exclusive_dropdowns():
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'class="demo-site-nav"' in script
    assert 'class="demo-mobile-nav"' in script
    assert 'class="demo-site-language"' in script
    assert 'flirexa-logo-mark-128.png' in script
    assert 'class="picker-tools"' not in script
    assert "details[data-demo-nav][open]" in script
    assert "if(item!==opened)item.removeAttribute('open')" in script
    assert "data-picker-lang" in script
    for locale in ("en", "ru", "de", "fr", "es"):
        assert f"{locale}: {{" in script


def test_picker_keeps_sanitized_app_previews_in_an_explicit_local_variant():
    script = SCRIPT.read_text(encoding="utf-8")
    variant = APP_VARIANT_INDEX.read_text(encoding="utf-8")
    expected_assets = {
        "android-home.webp",
        "android-plans.webp",
        "android-settings.webp",
        "linux-desktop.webp",
    }

    assert "appShowcaseTranslations" in script
    assert "showClientApps" in script
    assert "get('apps') === '1'" in script
    assert "demo/?apps=1" in variant
    assert 'class="apps-showcase"' in script
    assert "data-app-image" in script
    assert "app-lightbox-image" in script
    assert "console client running in a Linux terminal" in script
    assert "windows-desktop.webp" not in script
    for filename in expected_assets:
        assert (APP_ASSETS / filename).is_file()
        assert f"assets/apps/{filename}" in script

    # Intermediate captures can contain source-machine details and must not ship.
    assert not (APP_ASSETS / "android-home-base.webp").exists()
    assert not (APP_ASSETS / "windows-home.webp").exists()
    assert not (APP_ASSETS / "windows-desktop.webp").exists()
    assert not (APP_ASSETS / "linux-home.webp").exists()
    assert not (APP_ASSETS / "linux-terminal-preview.html").exists()


def test_authentic_admin_demo_mounts_design2_with_real_map_tiles_and_mocked_api():
    index = AUTHENTIC_INDEX.read_text(encoding="utf-8")
    app = AUTHENTIC_APP.read_text(encoding="utf-8")
    main = AUTHENTIC_MAIN.read_text(encoding="utf-8")

    assert "connect-src 'none'" in index
    assert "form-action 'none'" in index
    assert "import D2App from '../design2/D2App.vue'" in app
    assert "<D2App />" in app
    assert "api.defaults.adapter = adapter" in main
    assert "axios.defaults.adapter = adapter" in main
    assert "L.tileLayer = ()" not in main
    assert "https://*.basemaps.cartocdn.com" in index
    assert "connect-src 'none'" in index


def test_authentic_admin_exposes_every_registered_enterprise_screen():
    router = AUTHENTIC_ROUTER.read_text(encoding="utf-8")
    expected_routes = {
        "/", "/online-users", "/clients", "/slots", "/servers",
        "/server-monitoring", "/system-health", "/subscriptions",
        "/payments", "/portal-users", "/promo-codes",
        "/support-messages", "/notifications", "/bots", "/traffic",
        "/applications", "/dns-protection", "/plugins", "/backup",
        "/updates", "/settings", "/logs", "/app-logs",
    }

    actual_routes = set(re.findall(r"\['(/[^']*)',", router))
    assert expected_routes == actual_routes


def test_authentic_admin_uses_the_same_synthetic_scale_as_the_portal_demo():
    mock = AUTHENTIC_MOCK.read_text(encoding="utf-8")
    seed = mock.split("const serverSeed = [", 1)[1].split("]\n\nexport const demoServers", 1)[0]
    client_counts = [
        int(value)
        for value in re.findall(
            r"\['[^']+', '[^']+', '[^']+', ([0-9]+), '[^']+'\]", seed
        )
    ]

    assert len(client_counts) == 17
    assert sum(client_counts) == 7977
    assert "revenue_30d: '31908.00'" in mock


def test_authentic_portal_reuses_current_product_screens_and_layout():
    router = PORTAL_ROUTER.read_text(encoding="utf-8")
    app = PORTAL_APP.read_text(encoding="utf-8")

    for source in (
        "../views/Dashboard.vue", "../views/Devices.vue", "../views/Plans.vue",
        "../views/Payments.vue", "../views/Support.vue", "../views/CorporateVPN.vue",
    ):
        assert source in router
    assert "../components/Layout.vue" in app
    assert "<PortalLayout v-else>" in app
    assert "`/demo-authentic/admin/?lang=${encodeURIComponent(locale.value || 'en')}`" in app
    assert 'class="demo-preview-bar"' in app
    assert 'class="demo-switcher"' not in app
    assert "position: fixed" not in app


def test_authentic_portal_reuses_the_original_login_and_official_branding():
    login = PORTAL_LOGIN.read_text(encoding="utf-8")
    main = PORTAL_MAIN.read_text(encoding="utf-8")
    router = PORTAL_ROUTER.read_text(encoding="utf-8")

    assert "fx-login-shell" in login
    assert "fx-login-card" in login
    assert "import Login from '../views/Login.vue'" in router
    assert "component: Login" in router
    assert "DemoApp" in main
    assert "branding_customer_logo_url" in main
    assert "__FLIREXA_DEMO_ACCOUNT__" in main
    assert "demoAccount?.identifier" in login
    assert "demoAccount?.password" in login
    assert "window.addEventListener('fx:theme'" in main
    assert "classList.toggle('theme-light'" in main
    assert "classList.toggle('theme-dark'" in main
    assert "branding_customer_app_name: 'Flirexa'" in main
    assert "window.__FLIREXA_DEMO__ = true" in main


def test_authentic_portal_has_complete_public_demo_routes():
    router = PORTAL_ROUTER.read_text(encoding="utf-8")

    assert "import Register from '../views/Register.vue'" in router
    assert "import LegalPage from '../views/LegalPage.vue'" in router
    assert "path: '/register'" in router
    assert "path: '/legal/privacy'" in router
    assert "path: '/legal/terms'" in router
    assert router.count("meta: { layout: 'auth', public: true }") >= 4


def test_authentic_demos_return_a_real_self_contained_qr_image():
    qr = DEMO_QR.read_text(encoding="utf-8")
    admin_mock = AUTHENTIC_MOCK.read_text(encoding="utf-8")
    portal_mock = PORTAL_MOCK.read_text(encoding="utf-8")

    assert "DEMO_QR_BASE64" in qr
    assert "image/png" in qr
    assert "flirexa-demo://device/enterprise-preview" in qr
    encoded = re.search(r"DEMO_QR_BASE64 = '([^']+)'", qr).group(1)
    image = base64.b64decode(encoded)
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(image[16:20], "big") == 320
    assert int.from_bytes(image[20:24], "big") == 320
    assert "demoQrBlob()" in admin_mock
    assert "demoQrBlob()" in portal_mock
    assert "new Blob(['demo']" not in admin_mock
    assert "new Blob(['demo']" not in portal_mock


def test_admin_brand_logo_has_no_accent_tile_when_an_image_is_present():
    shell = D2_SHELL.read_text(encoding="utf-8")

    assert "'d2-brand-logo--image': branding.logoUrl" in shell
    assert ".d2-brand-logo--image { background:transparent" in shell
    assert "box-shadow:none" in shell


def test_authentic_portal_is_offline_and_mocks_the_real_api_client():
    index = PORTAL_INDEX.read_text(encoding="utf-8")
    main = PORTAL_MAIN.read_text(encoding="utf-8")
    mock = PORTAL_MOCK.read_text(encoding="utf-8")

    assert "connect-src 'none'" in index
    assert "form-action 'none'" in index
    assert "api.defaults.adapter = adapter" in main
    assert "axios.defaults.adapter = adapter" in main
    assert "/client-portal/subscription" in mock
    assert "/client-portal/devices" in mock
    assert "/client-portal/payments/balance" in mock
    assert "/client-portal/corporate/networks" in mock
    assert "/client-portal/payments/create-invoice" in mock
    assert "const paymentCheck = path.match" in mock
    assert "status: 'completed', paid: true" in mock
    assert "/client-portal/promo/validate" in mock
    assert "/client-portal/support/send" in mock
    assert "suggested_interface" in mock
    assert "config_downloaded_at" in mock
    assert "payment_url" not in mock


def test_authentic_portal_uses_all_product_locales():
    i18n = Path("src/web/client-portal/src/i18n/index.js").read_text(encoding="utf-8")
    login = PORTAL_LOGIN.read_text(encoding="utf-8")

    assert "messages: { en, ru, de, fr, es }" in i18n
    assert "$t('auth.signIn')" in login
    assert "$t('auth.identifier')" in login


def test_public_landing_points_to_the_clean_demo_chooser():
    live_index = LIVE_INDEX.read_text(encoding="utf-8")
    chooser = Path("landing/demo/index.html").read_text(encoding="utf-8")

    assert 'href="/demo/"' in live_index
    assert "demo/VPN-Admin-Panel-demo.html" not in live_index
    assert 'src="/demo-next/demo.js"' in chooser
    assert 'id="demoRoot"' in chooser
    assert "/seo-pages.js" not in chooser
