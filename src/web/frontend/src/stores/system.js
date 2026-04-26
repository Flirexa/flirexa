import { defineStore } from 'pinia'
import { systemApi, botsApi } from '../api'

export const useSystemStore = defineStore('system', {
  state: () => ({
    status: null,
    health: null,
    adminBot: null,
    clientBot: null,
    loading: false,
    error: null,
    theme: (() => {
      const saved = localStorage.getItem('sb_theme') || (localStorage.getItem('sb_dark') === 'true' ? 'dark' : 'light')
      // Only light and dark are supported
      if (saved !== 'light' && saved !== 'dark') return 'dark'
      return saved
    })(),
    sidebarOpen: false,
    sidebarCollapsed: localStorage.getItem('sb_sidebar_collapsed') === 'true',
  }),

  getters: {
    darkMode: (state) => state.theme !== 'light',
  },

  actions: {
    async fetchStatus() {
      this.loading = true
      try {
        const { data } = await systemApi.getStatus()
        this.status = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    async fetchHealth() {
      try {
        const { data } = await systemApi.getHealth()
        this.health = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      }
    },

    async fetchBotStatuses() {
      try {
        const [admin, client] = await Promise.all([
          botsApi.getAdminStatus(),
          botsApi.getClientStatus(),
        ])
        this.adminBot = admin.data
        this.clientBot = client.data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      }
    },

    setTheme(name) {
      this.theme = name
      localStorage.setItem('sb_theme', name)
      if (name === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark')
      } else {
        document.documentElement.removeAttribute('data-theme')
      }
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen
    },

    closeSidebar() {
      this.sidebarOpen = false
    },

    collapseSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem('sb_sidebar_collapsed', this.sidebarCollapsed)
    },

    initTheme() {
      if (this.theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark')
      } else {
        document.documentElement.removeAttribute('data-theme')
      }
    },
  },
})
