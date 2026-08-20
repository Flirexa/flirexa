import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import VueApexCharts from 'vue3-apexcharts'
import DemoApp from './DemoApp.vue'
import router from './router.js'
import i18n from '../i18n'
import api from '../api'
import { createPortalDemoAdapter } from './mockAdapter.js'
import { applyPortalBranding, applyPortalDocumentBranding } from '../branding.js'
import HelpTooltip from '../components/HelpTooltip.vue'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '@mdi/font/css/materialdesignicons.min.css'
import '../assets/style.css'
import '../assets/themes.css'
import '../assets/design-tokens.css'

const supportedDemoLocales = ['en', 'ru', 'de', 'fr', 'es']
const requestedDemoLocale = new URLSearchParams(window.location.search).get('lang')
let storedDemoLocale = ''
try { storedDemoLocale = localStorage.getItem('flirexa_lang') || localStorage.getItem('sb_lang') || '' } catch (_) {}
const demoLocale = supportedDemoLocales.includes(requestedDemoLocale)
  ? requestedDemoLocale
  : (supportedDemoLocales.includes(storedDemoLocale) ? storedDemoLocale : 'en')
window.__FLIREXA_DEMO_LOCALE__ = demoLocale
i18n.global.locale.value = demoLocale
document.documentElement.lang = demoLocale
try {
  localStorage.setItem('sb_lang', demoLocale)
  localStorage.setItem('flirexa_lang', demoLocale)
} catch (_) {}

const branding = {
  branding_customer_app_name: 'Flirexa',
  branding_customer_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
  branding_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
  branding_favicon_url: '/assets/flirexa-logo-globe-v2-transparent.png',
  branding_primary_color: '#6366f1',
  branding_footer_text: '© 2026 Flirexa',
  branding_support_url: 'mailto:support@example.test',
  branding_privacy_url: '/demo-authentic/portal/#/legal/privacy',
  branding_terms_url: '/demo-authentic/portal/#/legal/terms',
  branding_privacy_text: 'This interactive preview uses synthetic data only. It does not collect customer credentials or connect to a live VPN service.',
  branding_terms_text: 'This demo is provided for product evaluation. All accounts, payments, devices and network details shown here are fictional.',
  branding_powered_by: false,
  branding_github_card: false,
}
window.__FLIREXA_DEMO__ = true
window.__FLIREXA_DEMO_ACCOUNT__ = {
  identifier: 'emma.wilson@example.test',
  password: 'flirexa-demo',
}
const requestedDemoTheme = new URLSearchParams(window.location.search).get('theme')
if (requestedDemoTheme === 'dark' || requestedDemoTheme === 'light') {
  try { localStorage.setItem('sb_theme', requestedDemoTheme) } catch (_) {}
}
const readDemoTheme = () => localStorage.getItem('sb_theme') === 'dark' ? 'dark' : 'light'
const applyDemoTheme = theme => {
  const nextTheme = theme === 'dark' ? 'dark' : 'light'
  document.body.classList.add('fx-portal')
  document.body.classList.toggle('theme-light', nextTheme === 'light')
  document.body.classList.toggle('theme-dark', nextTheme === 'dark')
  document.documentElement.setAttribute('data-theme', nextTheme)
}
applyDemoTheme(readDemoTheme())

// DemoApp mounts the real Login/Layout components without production App.vue,
// so it must own the same theme event bridge as the production shell.
window.addEventListener('storage', event => {
  if (event.key === 'sb_theme') applyDemoTheme(readDemoTheme())
})
window.addEventListener('fx:theme', event => {
  applyDemoTheme(event.detail || readDemoTheme())
})
window.__branding = branding
applyPortalBranding(branding)
applyPortalDocumentBranding(branding)

const adapter = createPortalDemoAdapter()
api.defaults.adapter = adapter
axios.defaults.adapter = adapter

const app = createApp(DemoApp)
app.config.errorHandler = (error, instance, info) => {
  console.error('PORTAL_DEMO_ERROR', info, error)
}
app.use(createPinia())
app.use(router)
app.use(i18n)
i18n.global.locale.value = demoLocale
app.use(VueApexCharts)
app.component('HelpTooltip', HelpTooltip)
app.mount('#app')
// Keep the mounted production components on the chooser locale from their
// first painted frame.
i18n.global.locale.value = demoLocale
