import { createRouter, createWebHistory } from 'vue-router'
import { ensurePortalSession } from '../session'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { layout: 'auth', public: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { layout: 'auth', public: true }
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/plans',
    name: 'Plans',
    component: () => import('../views/Plans.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/payments',
    name: 'Payments',
    component: () => import('../views/Payments.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/support',
    name: 'Support',
    component: () => import('../views/Support.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/corporate',
    name: 'CorporateVPN',
    component: () => import('../views/CorporateVPN.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/devices',
    name: 'Devices',
    component: () => import('../views/Devices.vue'),
    meta: { requiresAuth: true }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const hasSession = await ensurePortalSession()

  if (to.meta.requiresAuth && !hasSession) {
    // Preserve the originally requested URL so the auth views can
    // bounce there after a successful login / register. Customers
    // who don't have an account yet click "Sign up" on the login
    // page — funnelling everyone through /register on first visit
    // is too aggressive for returning customers who only want to
    // sign back in.
    const next_url = to.fullPath
    if (next_url && next_url !== '/') {
      return { path: '/login', query: { next: next_url } }
    }
    return '/login'
  }

  if ((to.path === '/login' || to.path === '/register') && hasSession) {
    // Already authenticated — if they came in with a next= hint,
    // honor it so the marketing-landing → register → /plans loop
    // works even on the second visit when the user happened to
    // already be logged in.
    const hinted = typeof to.query.next === 'string' && to.query.next.startsWith('/')
      ? to.query.next
      : '/'
    return hinted
  }
})

export default router
