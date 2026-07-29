import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import App from './App.vue'
import router from './router'
import i18n from './i18n'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '@mdi/font/css/materialdesignicons.min.css'
import './assets/style.css'
import './assets/themes.css'
import './assets/design-tokens.css'

import VueApexCharts from 'vue3-apexcharts'
import HelpTooltip from './components/HelpTooltip.vue'
import { applyPortalBranding, applyPortalDocumentBranding } from './branding.js'

// Pre-fetch branding BEFORE mounting Vue. The previous flow let App.vue
// kick off the branding fetch in onMounted, then Login/Register/Layout
// read `window.__branding` from inside Vue's reactivity graph — except
// `window.__branding` isn't reactive, so the brandLogo computed evaluated
// once on mount (often before the fetch resolved), returned the bundled
// platform default, and any later re-render flipped the <img src> to
// whatever branding had landed. On a host where `branding_logo_url`
// points at a broken path, that second render produced a broken-image
// icon. Resolving the fetch first means every component's first read of
// `window.__branding` already has the real values.
async function prefetchBranding() {
  try {
    const baseUrl = window.location.port === '10090'
      ? `${window.location.protocol}//${window.location.hostname}:10086`
      : ''
    const { data } = await axios.get(`${baseUrl}/api/v1/public/branding`, {
      timeout: 2500,
    })
    window.__branding = data
    // Apply the complete accent ramp before Vue mounts, so Login/Register and
    // the authenticated shell render in the operator's colour on first paint.
    applyPortalBranding(data)
    applyPortalDocumentBranding(data)
  } catch {
    // Fall through with no branding — components default to bundled
    // assets, which is exactly what an untouched fresh install gets too.
    window.__branding = {}
    applyPortalBranding({})
    applyPortalDocumentBranding({})
  }
}

prefetchBranding().then(() => {
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(VueApexCharts)
  app.component('HelpTooltip', HelpTooltip)
  app.mount('#app')
})
