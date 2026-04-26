import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '@mdi/font/css/materialdesignicons.min.css'
import './assets/style.css'

import VueApexCharts from 'vue3-apexcharts'
import HelpTooltip from './components/HelpTooltip.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(VueApexCharts)
app.component('HelpTooltip', HelpTooltip)
app.mount('#app')
