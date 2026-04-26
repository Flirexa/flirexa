import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('client_access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('client_access_token')
      localStorage.removeItem('client_user')
      const p = window.location.pathname
      if (p !== '/login' && p !== '/register') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export const portalApi = {
  // Auth
  register: (data) => api.post('/client-portal/auth/register', data),
  login: (data) => api.post('/client-portal/auth/login', data),
  getMe: () => api.get('/client-portal/auth/me'),
  forgotPassword: (data) => api.post('/client-portal/auth/forgot-password', data),
  resetPassword: (data) => api.post('/client-portal/auth/reset-password', data),

  // Subscription
  getSubscription: () => api.get('/client-portal/subscription'),
  getPlans: () => api.get('/client-portal/subscription/plans'),
  getDashboardStats: () => api.get('/client-portal/dashboard/stats'),
  getFeatures: () => api.get('/client-portal/features'),

  // Payments
  createInvoice: (data) => api.post('/client-portal/payments/create-invoice', data),
  checkPayment: (invoiceId) => api.get(`/client-portal/payments/check/${invoiceId}`),
  getPaymentHistory: (limit = 50) => api.get(`/client-portal/payments/history?limit=${limit}`),

  // Providers & Crypto
  getProviders: () => api.get('/client-portal/payments/providers'),
  getCurrencies: () => api.get('/client-portal/crypto/currencies'),
  getRates: () => api.get('/client-portal/crypto/rates'),

  // Subscription actions
  cancelSubscription: () => api.post('/client-portal/subscription/cancel'),
  changePassword: (data) => api.post('/client-portal/auth/change-password', data),
  toggleAutoRenew: (enabled) => api.post('/client-portal/subscription/auto-renew', { auto_renew: enabled }),

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

  // Support
  getSupportMessages: () => api.get('/client-portal/support/messages'),
  sendSupportMessage: (data) => api.post('/client-portal/support/send', data),
  replySupportTicket: (ticketId, data) => api.post(`/client-portal/support/${ticketId}/reply`, data),
  getUnreadCount: () => api.get('/client-portal/support/unread-count'),

  // Notifications
  getNotifications: () => api.get('/client-portal/notifications'),
  markNotificationRead: (id) => api.post(`/client-portal/notifications/${id}/read`),

  // Subscription link
  getSubscriptionLink: () => api.get('/client-portal/subscription-link'),
  regenerateSubscriptionLink: () => api.post('/client-portal/subscription-link/regenerate'),

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
