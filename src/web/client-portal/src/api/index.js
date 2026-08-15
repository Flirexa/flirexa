import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 15000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    'X-Portal-Client': 'web',
  },
})

const unsafeMethods = new Set(['post', 'put', 'patch', 'delete'])

function readCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split('; ').find(value => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : ''
}

function csrfToken() {
  // Production uses the hardened __Host- name; local HTTP development can
  // explicitly opt out of Secure cookies and receives the unprefixed name.
  return readCookie('__Host-flirexa_portal_csrf')
    || readCookie('flirexa_portal_csrf')
}

// Cookie auth is ambient, so every state-changing browser request carries the
// non-HttpOnly half of the double-submit CSRF pair.
api.interceptors.request.use((config) => {
  if (unsafeMethods.has((config.method || 'get').toLowerCase())) {
    const token = csrfToken()
    if (token) config.headers['X-CSRF-Token'] = token
  }
  return config
})

let refreshPromise = null

function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = api.post(
      '/client-portal/auth/refresh',
      null,
      { _skipAuthInterceptor: true },
    ).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

function redirectToLogin() {
  window.dispatchEvent(new CustomEvent('fx:auth-expired'))
  const p = window.location.pathname
  if (p !== '/login' && p !== '/register') {
    window.location.href = '/login'
  }
}

const publicAuthPath = /\/auth\/(login|register|forgot-password|reset-password|refresh)$/

// Renew an expired short access cookie once, then replay the original request.
// Authentication failures from public auth/verification flows remain local to
// their form and never destroy an otherwise healthy browser session.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config || {}
    const skip = config._skipAuthInterceptor
      || publicAuthPath.test(config.url || '')
    if (error.response?.status === 401 && !skip && !config._authRetried) {
      config._authRetried = true
      try {
        await refreshSession()
        return api(config)
      } catch {
        redirectToLogin()
      }
    }
    return Promise.reject(error)
  }
)

export const portalApi = {
  // Auth
  register: (data) => api.post('/client-portal/auth/register', data),
  // `config` lets the caller pass `_skipAuthInterceptor: true` so a
  // wrong-password 401 from the verify-only delete flow doesn't kick
  // the user out of their good session.
  login: (data, config = {}) => api.post('/client-portal/auth/login', data, config),
  getMe: () => api.get('/client-portal/auth/me'),
  forgotPassword: (data) => api.post('/client-portal/auth/forgot-password', data),
  resetPassword: (data) => api.post('/client-portal/auth/reset-password', data),
  refresh: () => refreshSession(),
  logout: () => api.post('/client-portal/auth/logout'),
  verifyPassword: (password) => api.post(
    '/client-portal/auth/verify-password',
    { password },
    { _skipAuthInterceptor: true },
  ),

  // Subscription
  getSubscription: () => api.get('/client-portal/subscription'),
  getPlans: () => api.get('/client-portal/subscription/plans'),
  getDashboardStats: () => api.get('/client-portal/dashboard/stats'),
  getTrafficSeries: (range = '14d') => api.get(`/client-portal/dashboard/traffic-series?range=${encodeURIComponent(range)}`),
  getFeatures: () => api.get('/client-portal/features'),

  // Payments
  createInvoice: (data) => api.post('/client-portal/payments/create-invoice', data),
  capturePayPal: (orderId) => api.post('/client-portal/payments/paypal/capture', { order_id: orderId }),
  checkPayment: (invoiceId) => api.get(`/client-portal/payments/check/${invoiceId}`),
  getPaymentHistory: (limit = 50) => api.get(`/client-portal/payments/history?limit=${limit}`),

  // Providers & Crypto
  getProviders: () => api.get('/client-portal/payments/providers'),
  getCurrencies: () => api.get('/client-portal/crypto/currencies'),
  getRates: () => api.get('/client-portal/crypto/rates'),

  // Subscription actions
  cancelSubscription: () => api.post('/client-portal/subscription/cancel'),
  changePassword: (data) => api.post('/client-portal/auth/change-password', data),
  // Referral
  getReferral: () => api.get('/client-portal/referral'),

  // Promo
  validatePromo: (code) => api.post('/client-portal/promo/validate', { code }),

  // WireGuard
  getDevices: () => api.get('/client-portal/wireguard/clients'),
  getConfig: (clientId) => api.get(`/client-portal/wireguard/config/${clientId}`),
  getQRCode: (clientId) => api.get(`/client-portal/wireguard/qrcode/${clientId}`, { responseType: 'blob' }),
  createDevice: (serverId, name) => api.post('/client-portal/wireguard/create', { ...(serverId ? { server_id: serverId } : {}), ...(name ? { name } : {}) }),
  deleteDevice: (clientId) => api.delete(`/client-portal/wireguard/clients/${clientId}`),
  getServers: () => api.get('/client-portal/servers'),
  probeServer: (serverId) => api.get(`/client-portal/servers/${serverId}/probe`),

  // ── Device slots (multi-server toggle) ─────────────────────────────
  // Each slot = one device with peers on every customer-visible server.
  // Switching the active server flips enabled flags server-side without
  // rotating keys, so the user can roam between regions cleanly.
  listSlots: () => api.get('/client-portal/devices'),
  createSlot: (data) => api.post('/client-portal/devices', data || {}),
  switchSlotServer: (slotId, serverId) =>
    api.post(`/client-portal/devices/${slotId}/switch-server`, { server_id: serverId }),
  renameSlot: (slotId, label) =>
    api.patch(`/client-portal/devices/${slotId}`, { label }),
  deleteSlot: (slotId) => api.delete(`/client-portal/devices/${slotId}`),
  // Clear the slot's device-bind so a different phone can claim it on
  // its next wg-quick fetch. Used by the "Release device" button on
  // bound slots — needed when the customer replaces or loses the
  // originally-bound phone.
  releaseSlotDevice: (slotId) =>
    api.post(`/client-portal/devices/${slotId}/release`),
  getSlotServerConfig: (slotId, serverId) =>
    api.get(`/client-portal/devices/${slotId}/config/${serverId}`),

  // Support
  getSupportMessages: () => api.get('/client-portal/support/messages'),
  sendSupportMessage: (data) => api.post('/client-portal/support/send', data),
  replySupportTicket: (ticketId, data) => api.post(`/client-portal/support/${ticketId}/reply`, data),
  getUnreadCount: () => api.get('/client-portal/support/unread-count'),

  // Notifications
  getNotifications: () => api.get('/client-portal/notifications'),
  markNotificationRead: (id) => api.post(`/client-portal/notifications/${id}/read`),

  // Corporate VPN
  getCorporateNetworks: () => api.get('/client-portal/corporate/networks'),
  getCorporateNetwork: (id) => api.get(`/client-portal/corporate/networks/${id}`),
  createCorporateNetwork: (data) => api.post('/client-portal/corporate/networks', data),
  deleteCorporateNetwork: (id) => api.delete(`/client-portal/corporate/networks/${id}`),
  addCorporateSite: (netId, data) => api.post(`/client-portal/corporate/networks/${netId}/sites`, data),
  updateCorporateSite: (netId, siteId, data) => api.patch(`/client-portal/corporate/networks/${netId}/sites/${siteId}`, data),
  deleteCorporateSite: (netId, siteId) => api.delete(`/client-portal/corporate/networks/${netId}/sites/${siteId}`),
  downloadCorporateConfig: (netId, siteId) => api.get(`/client-portal/corporate/networks/${netId}/sites/${siteId}/config`, { responseType: 'text' }),
  regenerateCorporateSiteKeys: (netId, siteId) => api.post(`/client-portal/corporate/networks/${netId}/sites/${siteId}/regenerate-keys`),
  getCorporateNetworkHealth: (netId) => api.get(`/client-portal/corporate/networks/${netId}/health`),
  diagnoseCorporateNetwork: (netId) => api.get(`/client-portal/corporate/networks/${netId}/diagnostics`),
  getCorporateNetworkEvents: (netId, limit = 50) => api.get(`/client-portal/corporate/networks/${netId}/events?limit=${limit}`),
  getCorporateRelayTopology: (netId) => api.get(`/client-portal/corporate/networks/${netId}/relay`),
  setCorporateSiteRelay: (netId, siteId, isRelay) => api.patch(`/client-portal/corporate/networks/${netId}/sites/${siteId}/relay`, { is_relay: isRelay }),
}

export default api
