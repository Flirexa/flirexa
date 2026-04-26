import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/AdminLogin.vue'),
    meta: { public: true },
  },
  {
    path: '/activation',
    name: 'Activation',
    component: () => import('../views/Activation.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/clients',
    name: 'Clients',
    component: () => import('../views/Clients.vue'),
  },
  {
    path: '/servers',
    name: 'Servers',
    component: () => import('../views/Servers.vue'),
  },
  {
    path: '/subscriptions',
    name: 'Subscriptions',
    component: () => import('../views/Subscriptions.vue'),
  },
  {
    path: '/payments',
    name: 'Payments',
    component: () => import('../views/Payments.vue'),
  },
  {
    path: '/bots',
    name: 'Bots',
    component: () => import('../views/Bots.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/Settings.vue').catch(err => {
      console.error('SETTINGS LOAD ERROR:', err)
      return { template: '<div class="alert alert-danger m-4"><h5>Settings failed to load</h5><p>Please refresh the page.</p></div>' }
    }),
  },
  {
    path: '/portal-users',
    name: 'PortalUsers',
    component: () => import('../views/PortalUsers.vue'),
  },
  {
    path: '/traffic',
    name: 'TrafficRules',
    component: () => import('../views/TrafficRules.vue'),
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
  },
  {
    path: '/app-logs',
    name: 'AppLogs',
    component: () => import('../views/AppLogs.vue'),
  },
  {
    path: '/health',
    name: 'SystemHealth',
    component: () => import('../views/SystemHealth.vue'),
  },
  {
    path: '/server-monitoring',
    name: 'ServerMonitoring',
    component: () => import('../views/ServerMonitoring.vue'),
  },
  {
    path: '/backup',
    name: 'Backup',
    component: () => import('../views/Backup.vue'),
  },
  {
    path: '/updates',
    name: 'Updates',
    component: () => import('../views/Updates.vue'),
  },
  {
    path: '/promo-codes',
    name: 'PromoCodes',
    component: () => import('../views/PromoCodes.vue'),
  },
  {
    path: '/support-messages',
    name: 'SupportMessages',
    component: () => import('../views/SupportMessages.vue'),
  },
  {
    path: '/applications',
    name: 'Applications',
    component: () => import('../views/Applications.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/Dashboard.vue'),
    meta: { public: false },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Auth guard — redirect to /login if no token or token expired
router.beforeEach((to, from, next) => {
  if (to.meta.public) {
    next()
    return
  }

  const token = localStorage.getItem('sb_token')
  if (!token) {
    next('/login')
    return
  }

  // Check JWT expiry — if expired and no refresh token, redirect to login
  // If refresh token exists, let the API interceptor handle transparent refresh
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      const refreshToken = localStorage.getItem('sb_refresh_token')
      if (!refreshToken) {
        localStorage.removeItem('sb_token')
        next('/login')
        return
      }
      // Let through — axios interceptor will refresh on first API call
    }
  } catch {
    localStorage.removeItem('sb_token')
    localStorage.removeItem('sb_refresh_token')
    next('/login')
    return
  }

  next()
})

export default router
