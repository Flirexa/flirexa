import { createRouter, createWebHistory } from 'vue-router'

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

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('client_access_token')
  let hasToken = !!token

  // Check JWT expiry
  if (hasToken) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        localStorage.removeItem('client_access_token')
        hasToken = false
      }
    } catch {
      localStorage.removeItem('client_access_token')
      hasToken = false
    }
  }

  if (to.meta.requiresAuth && !hasToken) {
    // Preserve the originally requested URL so the auth views can
    // bounce there after a successful login / register. Customers
    // who don't have an account yet click "Sign up" on the login
    // page — funnelling everyone through /register on first visit
    // is too aggressive for returning customers who only want to
    // sign back in.
    const next_url = to.fullPath
    if (next_url && next_url !== '/') {
      return next({ path: '/login', query: { next: next_url } })
    }
    return next('/login')
  }

  if ((to.path === '/login' || to.path === '/register') && hasToken) {
    // Already authenticated — if they came in with a next= hint,
    // honor it so the marketing-landing → register → /plans loop
    // works even on the second visit when the user happened to
    // already be logged in.
    const hinted = typeof to.query.next === 'string' && to.query.next.startsWith('/')
      ? to.query.next
      : '/'
    return next(hinted)
  }

  next()
})

export default router
