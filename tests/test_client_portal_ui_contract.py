"""Static contracts for customer-visible client portal actions."""

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_subscription_link_is_not_advertised_as_wireguard_auto_setup():
    dashboard = _read("src/web/client-portal/src/views/Dashboard.vue")
    api = _read("src/web/client-portal/src/api/index.js")
    locales = "\n".join(
        _read(f"src/web/client-portal/src/i18n/locales/{language}.js")
        for language in ("en", "ru", "de", "fr", "es")
    )

    assert "subscriptionLink" not in dashboard
    assert "getSubscriptionLink" not in api
    assert "regenerateSubscriptionLink" not in api
    assert "Ссылка на подписку" not in locales
    assert "auto-configure WireGuard" not in locales


def test_public_support_and_footer_have_no_dead_links():
    layout = _read("src/web/client-portal/src/components/Layout.vue")
    support = _read("src/web/client-portal/src/views/Support.vue")
    login = _read("src/web/client-portal/src/views/Login.vue")
    register = _read("src/web/client-portal/src/views/Register.vue")

    assert '<a href="#" @click.prevent>' not in layout
    assert 'branding_support_url' in layout
    assert 'v-if="supportEmail"' in support
    assert 'v-if="supportUrl"' in support
    assert "branding_docs_url" not in support
    assert "branding_status_url" not in support
    assert '<router-link to="/support">' not in login
    assert '<router-link to="/support">' not in register
    assert 'v-if="supportHref"' in login
    assert 'v-if="supportHref"' in register


def test_github_promo_invites_exploration_without_fork_language():
    layout = _read("src/web/client-portal/src/components/Layout.vue")
    locales = {
        language: _read(f"src/web/client-portal/src/i18n/locales/{language}.js")
        for language in ("en", "ru", "de", "fr", "es")
    }

    assert all("openSource:" in locale for locale in locales.values())
    assert all("openSourceHint:" in locale for locale in locales.values())
    assert "Explore Flirexa on GitHub" in locales["en"]
    assert "Изучить Flirexa на GitHub" in locales["ru"]
    assert "fork" not in "\n".join(locales.values()).lower()
    assert "форк" not in "\n".join(locales.values()).lower()
    assert "branding.branding_github_card" in layout
    assert "brandingBoolean(branding.branding_github_card, poweredBy)" in layout


def test_payment_screen_has_only_real_actions_and_configured_providers():
    payments = _read("src/web/client-portal/src/views/Payments.vue")
    modal = _read("src/web/client-portal/src/views/PaymentModal.vue")

    assert ':key="p.invoice_id || p.id"' in payments
    assert 'name="external"' not in payments
    assert "provider.configured !== false" in payments
    assert "provider.configured !== false" in modal
    assert "providers.value.some(provider => provider.id === selectedProvider.value)" in modal
    assert "p.tier === 'paid'" not in payments
    assert "fx-method-upsell" not in payments
    assert 'rel="noreferrer"' in modal


def test_payment_and_location_controls_use_design2_primitives():
    modal = _read("src/web/client-portal/src/views/PaymentModal.vue")
    payments = _read("src/web/client-portal/src/views/Payments.vue")
    simple = _read("src/web/client-portal/src/views/SimpleDevices.vue")
    advanced = _read("src/web/client-portal/src/views/AdvancedDevices.vue")
    dashboard = _read("src/web/client-portal/src/views/Dashboard.vue")
    provider_mark = _read("src/web/client-portal/src/components/PaymentProviderMark.vue")
    country_flag = _read("src/web/client-portal/src/components/CountryFlag.vue")
    utility = _read("src/web/client-portal/src/utils.js")
    backend = _read("src/api/routes/client_portal.py")

    # Checkout must not regress to Bootstrap/emoji payment decoration.
    for legacy_class in ('class="btn ', 'class="alert ', 'class="form-control', 'input-group'):
        assert legacy_class not in modal
    for emoji in ('💎', '🅿️', '🔗', '💳', '💰'):
        assert emoji not in modal
        assert emoji not in provider_mark
    assert "PaymentProviderMark" in modal
    assert "PaymentProviderMark" in payments

    # Free-form operator locations resolve to a real country mark, while the
    # backend gives slot cards enough public metadata to avoid IP guesses.
    assert "CountryFlag" in simple
    assert "CountryFlag" in advanced
    assert "CountryFlag" in dashboard
    assert "countryCodeFromLocation" in utility
    assert '"server_location"' in backend
    assert '"server_type"' in backend
    assert "text-overflow:ellipsis" in simple
    assert "fx-slot-server-protocol" in advanced


def test_hosted_checkout_is_one_redirect_and_paypal_return_is_confirmed_server_side():
    payments = _read("src/web/client-portal/src/views/Payments.vue")
    modal = _read("src/web/client-portal/src/views/PaymentModal.vue")
    api = _read("src/web/client-portal/src/api/index.js")

    assert "window.location.assign(target.href)" in modal
    assert "target.protocol !== 'https:'" in modal
    assert "pay.continueToPayment" in modal
    assert "route.query.paypal_return" in payments
    assert "portalApi.capturePayPal(orderId)" in payments
    assert "payments/paypal/capture" in api


def test_plan_cards_preserve_cent_precision_used_by_checkout():
    plans = _read("src/web/client-portal/src/views/Plans.vue")
    price_function = plans[plans.index("function priceFor"):plans.index("function planTagline")]

    assert "formatPlanPrice(plan.price_monthly_usd || 0)" in price_function
    assert "amount.toFixed(2).replace(/\\.00$/, '')" in price_function
    assert ".toFixed(0)" not in price_function


def test_referral_link_reaches_the_registration_payload():
    dashboard = _read("src/web/client-portal/src/views/Dashboard.vue")
    register = _read("src/web/client-portal/src/views/Register.vue")

    assert "/register?ref=${referral.value.referral_code}" in dashboard
    assert "route.query.ref" in register
    assert "referral_code: referralCode" in register
    assert "delete payload.referral_code" in register
    assert "window.__FLIREXA_DEMO__" in dashboard
    assert "https://account.example.test" in dashboard


def test_corporate_portal_uses_design2_components_without_legacy_decoration():
    corporate = _read("src/web/client-portal/src/views/CorporateVPN.vue")

    assert 'class="fx-page corp-page"' in corporate
    assert 'class="corp-notice"' in corporate
    assert 'class="corp-site-actions"' in corporate
    assert 'class="corp-modal-head"' in corporate
    for legacy_class in ('class="alert ', 'class="card ', 'class="btn '):
        assert legacy_class not in corporate
    for legacy_glyph in ("🌐", "🖥", "🗑", "🩺", "📋", "🗺", "🏠", "💡"):
        assert legacy_glyph not in corporate


def test_portal_navigation_and_notifications_fail_safely():
    layout = _read("src/web/client-portal/src/components/Layout.vue")
    router = _read("src/web/client-portal/src/router/index.js")
    login = _read("src/web/client-portal/src/views/Login.vue")

    assert "ref({ corp_networks: false, account_balance: false })" in layout
    assert "portalApi.getBalance(1)" in layout
    assert "query: { topup: '1' }" in layout
    assert "data.filter(isUnreadNotification)" in layout
    assert 'v-if="notifsOpen"' in layout
    assert "path: '/:pathMatch(.*)*'" in router
    assert "safePortalPath(to.query.next)" in router
    assert "remember_me" not in login
    assert "rememberMe" not in login


def test_structured_api_errors_have_one_safe_formatter():
    utility = _read("src/web/client-portal/src/utils.js")
    assert "export function apiErrorMessage" in utility
    assert "['message', 'msg', 'detail', 'error']" in utility

    for component in (
        "Dashboard.vue",
        "AdvancedDevices.vue",
        "SimpleDevices.vue",
        "PaymentModal.vue",
        "Payments.vue",
        "Support.vue",
        "CorporateVPN.vue",
    ):
        source = _read(f"src/web/client-portal/src/views/{component}")
        if "FLIREXA_COMMERCIAL_STUB = True" in source:
            # Open-core mirrors intentionally replace commercial screens with
            # deterministic placeholders. The private suite still exercises
            # the real implementation through this same test.
            assert component == "CorporateVPN.vue"
        else:
            assert "apiErrorMessage" in source


def test_client_portal_modes_share_one_device_slot_backend():
    wrapper = _read("src/web/client-portal/src/views/Devices.vue")
    simple = _read("src/web/client-portal/src/views/SimpleDevices.vue")
    advanced = _read("src/web/client-portal/src/views/AdvancedDevices.vue")
    api = _read("src/web/client-portal/src/api/index.js")
    backend = _read("src/api/routes/client_portal.py")

    assert "portalMode === 'advanced'" in wrapper
    assert "<AdvancedDevices" in wrapper
    assert "<SimpleDevices" in wrapper
    assert "portalApi.createSlot" in simple
    assert "initial_server_id" in simple
    assert "portalApi.getSlotServerQr" in simple
    assert "slot.is_bound" in simple
    assert "simpleDevices.releaseBeforeSetup" in simple
    assert "portalApi.createSlot" in advanced
    assert "getSlotServerQr" in api
    assert '@router.get("/devices/{slot_id}/qrcode/{server_id}")' in backend
    assert "mgr.get_slot(slot_id, user_id)" in backend


def test_simple_portal_copy_hides_slot_internals_from_customers():
    simple = _read("src/web/client-portal/src/views/SimpleDevices.vue")
    locales = "\n".join(
        _read(f"src/web/client-portal/src/i18n/locales/{language}.js")
        for language in ("en", "ru", "de", "fr", "es")
    )

    assert "simpleDevices.add" in simple
    assert "simpleDevices.setupReady" in simple
    assert "Technical slots stay hidden" not in simple
    assert locales.count("simpleDevices:") == 5
    assert locales.count("releaseBeforeSetup:") == 5
    assert locales.count("balance:") >= 5


def test_browser_and_pwa_branding_do_not_leak_static_platform_identity():
    index = _read("src/web/client-portal/index.html")
    manifest = _read("src/web/client-portal/public/manifest.json")
    branding = _read("src/web/client-portal/src/branding.js")

    assert "<title>Flirexa</title>" not in index
    assert '"name": "Flirexa"' not in manifest
    assert "applyPortalDocumentBranding" in branding
    assert "branding_customer_app_name" in branding
    assert "branding_favicon_url" in branding


def test_legal_documents_are_public_branded_and_rendered_as_plain_text():
    router = _read("src/web/client-portal/src/router/index.js")
    legal = _read("src/web/client-portal/src/views/LegalPage.vue")
    branding = _read("src/web/client-portal/src/branding.js")

    assert "path: '/legal/privacy'" in router
    assert "path: '/legal/terms'" in router
    assert "meta: { layout: 'auth', public: true }" in router
    assert "legalDocumentHref" in branding
    assert "branding_${kind}_text" in branding
    assert "{{ body }}" in legal
    assert "v-html" not in legal
    assert "white-space:pre-wrap" in legal


def test_dashboard_status_and_account_controls_have_clear_actions():
    dashboard = _read("src/web/client-portal/src/views/Dashboard.vue")
    layout = _read("src/web/client-portal/src/components/Layout.vue")

    assert "fx-status-orb" not in dashboard
    assert "fx-status-symbol" in dashboard
    assert "statusVisualIcon" in dashboard
    assert 'class="fx-avatar"' in layout
    assert 'class="fx-account-menu"' in layout
    assert '@click="logout"' in layout
    assert "document.addEventListener('pointerdown', onOutsidePointer)" in layout


def test_native_select_popup_follows_portal_theme():
    tokens = _read("src/web/client-portal/src/assets/design-tokens.css")

    assert ".theme-light select { color-scheme: light; }" in tokens
    assert ".theme-dark select { color-scheme: dark; }" in tokens
    assert ".theme-dark select option" in tokens
    assert "background-color: #11131f" in tokens
