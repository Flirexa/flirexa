import { defineStore } from 'pinia'
import { clientsApi } from '../api'

export const useClientsStore = defineStore('clients', {
  state: () => ({
    clients: [],
    totalClients: 0,
    currentClient: null,
    loading: false,
    error: null,
  }),

  getters: {
    activeClients: (state) => state.clients.filter((c) => c.enabled),
    disabledClients: (state) => state.clients.filter((c) => !c.enabled),
    totalTraffic: (state) => {
      return state.clients.reduce(
        (acc, c) => ({
          rx: acc.rx + (c.traffic_used_rx || 0),
          tx: acc.tx + (c.traffic_used_tx || 0),
        }),
        { rx: 0, tx: 0 }
      )
    },
  },

  actions: {
    async fetchClients(params = {}) {
      this.loading = true
      this.error = null
      try {
        const { data } = await clientsApi.getAll(params)
        // Handle paginated response {total, items} or plain array
        if (data && data.items) {
          this.clients = data.items
          this.totalClients = data.total || data.items.length
        } else {
          this.clients = Array.isArray(data) ? data : []
          this.totalClients = this.clients.length
        }
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    async fetchClient(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await clientsApi.get(id)
        this.currentClient = data
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        return null
      } finally {
        this.loading = false
      }
    },

    async createClient(clientData) {
      try {
        const { data } = await clientsApi.create(clientData)
        this.clients.push(data)
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async deleteClient(id) {
      try {
        await clientsApi.delete(id)
        this.clients = this.clients.filter((c) => c.id !== id)
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async toggleClient(id, enable) {
      try {
        if (enable) {
          await clientsApi.enable(id)
        } else {
          await clientsApi.disable(id)
        }
        const client = this.clients.find((c) => c.id === id)
        if (client) client.enabled = enable
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async setTrafficLimit(id, limitMb, autoReset = false) {
      try {
        await clientsApi.setTrafficLimit(id, { limit_mb: limitMb, auto_reset: autoReset })
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async setBandwidth(id, limitMbps) {
      try {
        await clientsApi.setBandwidth(id, { limit_mbps: limitMbps })
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async setExpiry(id, days, extend = false) {
      try {
        await clientsApi.setExpiry(id, { days, extend })
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async resetTraffic(id) {
      try {
        await clientsApi.resetTraffic(id)
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },
  },
})
