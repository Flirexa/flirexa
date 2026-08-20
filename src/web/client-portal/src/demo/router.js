import { createRouter, createWebHashHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import LegalPage from '../views/LegalPage.vue'
import Dashboard from '../views/Dashboard.vue'
import Devices from '../views/Devices.vue'
import Plans from '../views/Plans.vue'
import Payments from '../views/Payments.vue'
import Support from '../views/Support.vue'
import CorporateVPN from '../views/CorporateVPN.vue'

const routes = [
  { path: '/login', name: 'Login', component: Login, meta: { layout: 'auth', public: true } },
  { path: '/register', name: 'Register', component: Register, meta: { layout: 'auth', public: true } },
  { path: '/legal/privacy', name: 'Privacy', component: LegalPage, props: { kind: 'privacy' }, meta: { layout: 'auth', public: true } },
  { path: '/legal/terms', name: 'Terms', component: LegalPage, props: { kind: 'terms' }, meta: { layout: 'auth', public: true } },
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/devices', name: 'Devices', component: Devices },
  { path: '/plans', name: 'Plans', component: Plans },
  { path: '/payments', name: 'Payments', component: Payments },
  { path: '/support', name: 'Support', component: Support },
  { path: '/corporate', name: 'CorporateVPN', component: CorporateVPN },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export default createRouter({ history: createWebHashHistory(), routes })
