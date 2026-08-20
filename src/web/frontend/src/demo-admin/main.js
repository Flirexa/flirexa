import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import VueApexCharts from 'vue3-apexcharts'
import App from './App.vue'
import router from './router'
import i18n from '../i18n'
import api from '../api'
import { createDemoAdapter, enterpriseFeatures } from './mockAdapter'
import { useBrandingStore } from '../stores/branding'
import { useLicenseStore } from '../stores/license'
import { useSystemStore } from '../stores/system'
import HelpTooltip from '../components/HelpTooltip.vue'

import 'bootstrap/dist/css/bootstrap.min.css'
import '@mdi/font/css/materialdesignicons.min.css'
import '../assets/style.css'

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

const adapter = createDemoAdapter()
api.defaults.adapter = adapter
axios.defaults.adapter = adapter

try {
  localStorage.setItem('sb_token', 'demo.enterprise.token')
  localStorage.setItem('sb_username', 'Alex Morgan')
  localStorage.setItem('sb_lang', demoLocale)
  localStorage.setItem('flirexa_lang', demoLocale)
} catch (_) {}

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(i18n)
i18n.global.locale.value = demoLocale
app.use(VueApexCharts)
app.component('HelpTooltip', HelpTooltip)

const branding = useBrandingStore(pinia)
branding.$patch({
  appName: 'Flirexa', companyName: 'Enterprise Demo',
  logoUrl: '/assets/flirexa-logo-globe-v2-transparent.png',
  faviconUrl: '/assets/flirexa-logo-globe-v2-transparent.png',
  primaryColor: '#6366f1', poweredBy: false, loaded: true,
})
branding.applyBranding()

const license = useLicenseStore(pinia)
license.features = enterpriseFeatures
license.tier = 'enterprise'
license.loaded = true

const system = useSystemStore(pinia)
system.initTheme()

app.mount('#app')
