import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sb_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Global error toast helper
let _toastTimeout = null
function showErrorToast(message) {
  // Remove existing toast
  const existing = document.getElementById('api-error-toast')
  if (existing) existing.remove()
  if (_toastTimeout) clearTimeout(_toastTimeout)

  const toast = document.createElement('div')
  toast.id = 'api-error-toast'
  toast.style.cssText = 'position:fixed;top:20px;right:20px;z-index:99999;max-width:400px;padding:12px 20px;background:#dc3545;color:#fff;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.3);font-size:14px;animation:fadeIn .2s'
  toast.textContent = message
  document.body.appendChild(toast)
  _toastTimeout = setTimeout(() => toast.remove(), 5000)
}

// Refresh token logic
let _isRefreshing = false
let _refreshQueue = []

function _processQueue(error, token = null) {
  _refreshQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  _refreshQueue = []
}

// Response interceptor — auto-refresh on 401, show toast on errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    // 403 activation_required → redirect to activation screen
    if (error.response?.status === 403 && error.response?.data?.activation_required) {
      const data = error.response.data
      window.__activationCode    = data.activation_code || ''
      window.__activationMessage = data.detail || ''
      if (window.location.pathname !== '/activation') {
        window.location.href = '/activation'
      }
      return Promise.reject(error)
    }

    // 403 with upgrade_url → broadcast a global event so views can render
    // a "Buy {tier}" toast / modal. Detail can be either a string (legacy)
    // or an object with {message, upgrade_url, upgrade_tier,
    // license_feature_required}; normalize both shapes.
    if (error.response?.status === 403 && error.response?.data?.upgrade_url) {
      const data = error.response.data
      const detail = data.detail
      const message = (typeof detail === 'object' && detail?.message)
        ? detail.message
        : (typeof detail === 'string' ? detail : data.message || '')
      const upgradeTier = data.upgrade_tier || (typeof detail === 'object' ? detail.upgrade_tier : null)
      const upgradeUrl  = data.upgrade_url  || (typeof detail === 'object' ? detail.upgrade_url  : null)
      const feature     = data.license_feature_required || (typeof detail === 'object' ? detail.license_feature_required : null)
      window.dispatchEvent(new CustomEvent('flirexa:upgrade-required', {
        detail: { message, tier: upgradeTier, url: upgradeUrl, feature },
      }))
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      const url = originalRequest?.url || ''
      if (url.startsWith('/auth/') || url.startsWith('auth/')) {
        return Promise.reject(error)
      }

      const refreshToken = localStorage.getItem('sb_refresh_token')
      if (!refreshToken) {
        localStorage.removeItem('sb_token')
        if (window.location.pathname !== '/login') window.location.href = '/login'
        return Promise.reject(error)
      }

      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject })
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      _isRefreshing = true

      try {
        const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
        localStorage.setItem('sb_token', data.access_token)
        if (data.refresh_token) localStorage.setItem('sb_refresh_token', data.refresh_token)
        _processQueue(null, data.access_token)
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        _processQueue(refreshError, null)
        localStorage.removeItem('sb_token')
        localStorage.removeItem('sb_refresh_token')
        if (window.location.pathname !== '/login') window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        _isRefreshing = false
      }
    } else if (error.response?.status >= 500) {
      showErrorToast('Server error. Please try again later.')
    } else if (!error.response && error.code === 'ECONNABORTED') {
      showErrorToast('Request timed out. Check your connection.')
    } else if (!error.response) {
      showErrorToast('Network error. Check your connection.')
    }
    return Promise.reject(error)
  }
)

// ===== Auth =====
export const authApi = {
  setupStatus: () => api.get('/auth/setup-status'),
  setup: (data) => api.post('/auth/setup', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
  createAdmin: (data) => api.post('/auth/create-admin', data),
}

// ===== Clients =====
export const clientsApi = {
  getAll: (params) => api.get('/clients', { params }),
  get: (id) => api.get(`/clients/${id}`),
  create: (data) => api.post('/clients', data),
  update: (id, data) => api.put(`/clients/${id}`, data),
  delete: (id) => api.delete(`/clients/${id}`),
  enable: (id) => api.post(`/clients/${id}/enable`),
  disable: (id) => api.post(`/clients/${id}/disable`),
  getConfig: (id) => api.get(`/clients/${id}/config`),
  getQR: (id, format) => api.get(`/clients/${id}/qrcode${format ? '?format=' + format : ''}`, { responseType: 'blob' }),
  getPeerDevices: (id) => api.get(`/clients/${id}/peer-devices`),
  setTrafficLimit: (id, data) => api.post(`/clients/${id}/traffic-limit`, data),
  resetTraffic: (id) => api.post(`/clients/${id}/reset-traffic`),
  setBandwidth: (id, data) => api.post(`/clients/${id}/bandwidth-limit`, data),
  setExpiry: (id, data) => api.post(`/clients/${id}/expiry`, data),
  getMapData: () => api.get('/clients/map-data'),
}

// ===== Servers =====
export const serversApi = {
  getAll: () => api.get('/servers'),
  get: (id) => api.get(`/servers/${id}`),
  create: (data) => api.post('/servers', data, { timeout: 300000 }),
  update: (id, data) => api.put(`/servers/${id}`, data),
  delete: (id, force = false) => api.delete(`/servers/${id}`, { params: { force } }),
  start: (id) => api.post(`/servers/${id}/start`),
  stop: (id) => api.post(`/servers/${id}/stop`),
  restart: (id) => api.post(`/servers/${id}/restart`),
  getStats: (id) => api.get(`/servers/${id}/stats`),
  getBandwidth: (id) => api.get(`/servers/${id}/bandwidth`),
  getClients: (id) => api.get(`/servers/${id}/clients`),
  saveConfig: (id) => api.post(`/servers/${id}/save-config`),
  discover: (data) => api.post('/servers/discover', data, { timeout: 120000 }),
  installAgent: (id, port = 8001) => api.post(`/servers/${id}/install-agent`, { port }, { timeout: 300000 }),
  checkAgentStatus: (id) => api.get(`/agent/${id}/status`),
  uninstallAgent: (id) => api.post(`/agent/${id}/uninstall`, {}, { timeout: 120000 }),
  backup: (id) => api.get(`/servers/${id}/backup`, { responseType: 'blob' }),
  restore: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/servers/${id}/restore`, form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
  },
  setDefault: (id) => api.post(`/servers/${id}/set-default`),
  reconcile: (id) => api.post(`/servers/${id}/reconcile`),
  getBootstrapLogs: (taskId, since = 0) => api.get(`/servers/bootstrap/${taskId}`, { params: { since } }),
  installProxy: (id, data) => api.post(`/servers/${id}/install-proxy`, data, { timeout: 300000 }),
}

// ===== Bots =====
export const botsApi = {
  getAdminStatus: () => api.get('/bots/admin/status'),
  startAdmin: () => api.post('/bots/admin/start'),
  stopAdmin: () => api.post('/bots/admin/stop'),
  restartAdmin: () => api.post('/bots/admin/restart'),
  getClientStatus: () => api.get('/bots/client/status'),
  startClient: () => api.post('/bots/client/start'),
  stopClient: () => api.post('/bots/client/stop'),
  restartClient: () => api.post('/bots/client/restart'),
  getConfig: () => api.get('/bots/config'),
  updateConfig: (data) => api.post('/bots/config', data),
}

// ===== Payments =====
export const paymentsApi = {
  getPlans: () => api.get('/payments/plans'),
  createPlan: (data) => api.post('/payments/plans', data),
  getInvoices: (params) => api.get('/payments', { params }),
  createInvoice: (data) => api.post('/payments/invoice', data),
  checkInvoice: (id) => api.get(`/payments/${id}`),
}

// ===== Tariffs (Subscription Plans) =====
export const tariffsApi = {
  list: (params) => api.get('/tariffs', { params }),
  get: (id) => api.get(`/tariffs/${id}`),
  create: (data) => api.post('/tariffs', data),
  update: (id, data) => api.put(`/tariffs/${id}`, data),
  delete: (id) => api.delete(`/tariffs/${id}`),
  reorder: (data) => api.post('/tariffs/reorder', data),
  simulatePayment: (invoiceId) => api.post(`/tariffs/simulate-payment/${invoiceId}`),
}

// ===== Traffic Rules =====
export const trafficApi = {
  getTop: (period = 'day', limit = 10) => api.get('/traffic/top', { params: { period, limit } }),
  getRules: () => api.get('/traffic/rules'),
  getClients: () => api.get('/traffic/clients'),
  createRule: (data) => api.post('/traffic/rules', data),
  updateRule: (id, data) => api.put(`/traffic/rules/${id}`, data),
  deleteRule: (id) => api.delete(`/traffic/rules/${id}`),
  checkRules: () => api.post('/traffic/check-rules'),
}

// ===== Portal Users =====
export const portalUsersApi = {
  createAccount: (data) => api.post('/portal-users/create-account', data),
  list: (params) => api.get('/portal-users', { params }),
  get: (id) => api.get(`/portal-users/${id}`),
  update: (id, data) => api.put(`/portal-users/${id}`, data),
  getTiers: () => api.get('/portal-users/tiers'),
  grantSubscription: (id, data) => api.post(`/portal-users/${id}/grant-subscription`, data),
  extendSubscription: (id, data) => api.post(`/portal-users/${id}/extend-subscription`, data),
  cancelSubscription: (id) => api.post(`/portal-users/${id}/cancel-subscription`),
  resetTraffic: (id) => api.post(`/portal-users/${id}/reset-traffic`),
  deleteUser: (id) => api.delete(`/portal-users/${id}`),
  getPayments: (params) => api.get('/portal-users/payments', { params }),
  confirmPayment: (id) => api.post(`/portal-users/payments/${id}/confirm`),
  rejectPayment: (id) => api.post(`/portal-users/payments/${id}/reject`),
  deletePayment: (id) => api.delete(`/portal-users/payments/${id}`),
  getRevenueStats: () => api.get('/portal-users/stats/revenue'),
  getChartData: () => api.get('/portal-users/stats/charts'),
  sendMessage: (id, data) => api.post(`/portal-users/${id}/send-message`, data),
  broadcast: (data) => api.post('/portal-users/broadcast', data),
  // Support
  getSupportMessages: (params) => api.get('/portal-users/support-messages', { params }),
  getSupportUnread: () => api.get('/portal-users/support-messages/unread-count'),
  getSupportTicket: (id) => api.get(`/portal-users/support-messages/${id}`),
  replySupportTicket: (id, data) => api.post(`/portal-users/support-messages/${id}/reply`, data),
  closeSupportTicket: (id) => api.post(`/portal-users/support-messages/${id}/close`),
  reopenSupportTicket: (id) => api.post(`/portal-users/support-messages/${id}/reopen`),
  deleteSupportTicket: (id) => api.delete(`/portal-users/support-messages/${id}`),
}

// ===== Promo Codes =====
export const promoCodesApi = {
  list: (params) => api.get('/promo-codes', { params }),
  get: (id) => api.get(`/promo-codes/${id}`),
  create: (data) => api.post('/promo-codes', data),
  update: (id, data) => api.put(`/promo-codes/${id}`, data),
  delete: (id) => api.delete(`/promo-codes/${id}`),
  stats: () => api.get('/promo-codes/stats'),
}

// ===== System =====
// ===== Backups =====
export const backupApi = {
  create: () => api.post('/backup/create', {}, { timeout: 300000 }),
  list: () => api.get('/backup/list'),
  verify: (backupId) => api.post(`/backup/verify/${backupId}`, {}, { timeout: 120000 }),
  restoreFull: (backupId, data = {}) => api.post(`/backup/restore/full/${backupId}`, data, { timeout: 300000 }),
  restoreDatabase: (backupId) => api.post(`/backup/restore/database/${backupId}`, {}, { timeout: 120000 }),
  restoreServer: (serverId, backupId) => api.post(`/backup/restore/server/${serverId}/${backupId}`, {}, { timeout: 120000 }),
  delete: (backupId) => api.delete(`/backup/${backupId}`),
  getSettings: () => api.get('/system/backup-settings'),
  saveSettings: (data) => api.post('/system/backup-settings', data),
  mount: () => api.post('/system/backup-mount', {}, { timeout: 60000 }),
  unmount: () => api.post('/system/backup-unmount'),
  mountStatus: () => api.get('/system/backup-mount-status'),
  testWrite: () => api.post('/system/backup-test-write'),
}

export const systemApi = {
  // Branding
  getBranding: () => api.get('/system/branding'),
  updateBranding: (data) => api.post('/system/branding', data),
  uploadLogo: (formData) => api.post('/system/branding/logo', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  // License
  getLicense: () => api.get('/system/license'),
  activateLicense: (data) => api.post('/system/license', data),
  replayLicense: (data) => api.post('/system/license/replay', data),
  getLicenseServer: () => api.get('/system/license-server'),
  applyMigrationCode: (data) => api.post('/system/license-migration', data),
  triggerLicenseCheck: () => api.post('/system/license-check'),
  // System
  getStatus: () => api.get('/system/status'),
  getHealth: () => api.get('/system/health'),
  getLogs: (params) => api.get('/system/logs', { params }),
  getConfig: () => api.get('/system/config'),
  getTrafficStats: () => api.get('/system/stats/traffic'),
  getExpiryStats: () => api.get('/system/stats/expiry'),
  getExpiringSoon: (params) => api.get('/system/expiring-soon', { params }),
  triggerLimitCheck: () => api.post('/system/check-limits'),
  getPaymentSettings: () => api.get('/system/payment-settings'),
  updatePaymentSettings: (data) => api.post('/system/payment-settings', data),
  getSmtpSettings: () => api.get('/system/smtp-settings'),
  updateSmtpSettings: (data) => api.post('/system/smtp-settings', data),
  testSmtp: () => api.post('/system/smtp-test'),
  getNotificationSettings: () => api.get('/system/notification-settings'),
  updateNotificationSettings: (data) => api.post('/system/notification-settings', data),
  getWebAccessSettings: () => api.get('/system/web-access'),
  applyWebAccessSettings: (data) => api.post('/system/web-access', data, { timeout: 300000 }),
  getPublicIp: () => api.get('/system/public-ip'),
  getAppLogs: (params) => api.get('/system/app-logs', { params }),
  getAppLogsErrors: (params) => api.get('/system/app-logs/errors', { params }),
}

export const appAccountsApi = {
  list: () => api.get('/app-accounts'),
  get: (id) => api.get(`/app-accounts/${id}`),
  create: (data) => api.post('/app-accounts', data),
  update: (id, data) => api.put(`/app-accounts/${id}`, data),
  delete: (id) => api.delete(`/app-accounts/${id}`),
  permissions: () => api.get('/app-accounts/permissions'),
}

export const healthApi = {
  // System health
  getSystemHealth: (full = false) => api.get('/health/system', { params: full ? { full: 1 } : {} }),
  refreshSystemHealth: () => api.post('/health/system/refresh'),
  // Server health
  getAllServersHealth: (full = false) => api.get('/health/servers', { params: full ? { full: 1 } : {} }),
  getServerHealth: (id) => api.get(`/health/servers/${id}`),
  refreshServerHealth: (id) => api.post(`/health/servers/${id}/refresh`),
  // Events & history
  getEvents: (params = {}) => api.get('/health/events', { params }),
  getIssues: () => api.get('/health/issues'),
  getComponentHistory: (name, eventsLimit = 50) => api.get(`/health/components/${name}/history`, { params: { events_limit: eventsLimit } }),
  getServerHistory: (id, eventsLimit = 50) => api.get(`/health/servers/${id}/history`, { params: { events_limit: eventsLimit } }),
}

export default api
