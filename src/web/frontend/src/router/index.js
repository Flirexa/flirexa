import { createRouter, createWebHistory } from 'vue-router'
import { D2_SCREENS } from '../design2/screens/registry.js'

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
    component: D2_SCREENS.Activation,
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: D2_SCREENS.Dashboard,
  },
  {
    path: '/online-users',
    name: 'OnlineUsers',
    component: D2_SCREENS.OnlineUsers,
  },
  {
    path: '/clients',
    name: 'Clients',
    component: D2_SCREENS.Clients,
  },
  {
    path: '/slots',
    name: 'Slots',
    component: D2_SCREENS.Slots,
  },
  {
    path: '/servers',
    name: 'Servers',
    component: D2_SCREENS.Servers,
  },
  {
    path: '/subscriptions',
    name: 'Subscriptions',
    component: D2_SCREENS.Subscriptions,
  },
  {
    path: '/payments',
    name: 'Payments',
    component: D2_SCREENS.Payments,
  },
  {
    path: '/bots',
    name: 'Bots',
    component: D2_SCREENS.Bots,
  },
  {
    path: '/settings',
    name: 'Settings',
    component: D2_SCREENS.Settings,
  },
  {
    path: '/design',
    redirect: '/settings',
  },
  {
    path: '/portal-users',
    name: 'PortalUsers',
    component: D2_SCREENS.PortalUsers,
  },
  {
    path: '/traffic',
    name: 'TrafficRules',
    component: D2_SCREENS.TrafficRules,
  },
  {
    path: '/logs',
    name: 'Logs',
    component: D2_SCREENS.Logs,
  },
  {
    path: '/app-logs',
    name: 'AppLogs',
    component: D2_SCREENS.AppLogs,
  },
  {
    path: '/health',
    name: 'SystemHealth',
    component: D2_SCREENS.SystemHealth,
  },
  {
    path: '/server-monitoring',
    name: 'ServerMonitoring',
    component: D2_SCREENS.ServerMonitoring,
  },
  {
    path: '/backup',
    name: 'Backup',
    component: D2_SCREENS.Backup,
  },
  {
    path: '/updates',
    name: 'Updates',
    component: D2_SCREENS.Updates,
  },
  {
    path: '/plugins',
    name: 'Plugins',
    component: D2_SCREENS.Plugins,
  },
  {
    path: '/promo-codes',
    name: 'PromoCodes',
    component: D2_SCREENS.PromoCodes,
  },
  {
    path: '/support-messages',
    name: 'SupportMessages',
    component: D2_SCREENS.SupportMessages,
  },
  {
    path: '/applications',
    name: 'Applications',
    component: D2_SCREENS.Applications,
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: D2_SCREENS.Notifications,
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: D2_SCREENS.Dashboard,
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
