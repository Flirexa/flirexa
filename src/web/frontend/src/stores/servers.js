import { defineStore } from 'pinia'
import { serversApi } from '../api'

export const useServersStore = defineStore('servers', {
  state: () => ({
    servers: [],
    currentServer: null,
    loading: false,
    error: null,
  }),

  getters: {
    onlineServers: (state) => state.servers.filter((s) => s.status === 'online'),
    totalCapacity: (state) =>
      state.servers.reduce((sum, s) => sum + (s.max_clients || 250), 0),
  },

  actions: {
    async fetchServers() {
      this.loading = true
      this.error = null
      try {
        const { data } = await serversApi.getAll()
        // Handle paginated response {total, items} or plain array
        this.servers = (data && data.items) ? data.items : (Array.isArray(data) ? data : [])
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },

    async fetchServer(id) {
      this.loading = true
      try {
        const { data } = await serversApi.get(id)
        this.currentServer = data
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        return null
      } finally {
        this.loading = false
      }
    },

    async createServer(serverData) {
      try {
        const { data } = await serversApi.create(serverData)
        this.servers.push(data)
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async deleteServer(id) {
      try {
        await serversApi.delete(id)
        this.servers = this.servers.filter((s) => s.id !== id)
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async serverAction(id, action) {
      try {
        if (action === 'start') await serversApi.start(id)
        else if (action === 'stop') await serversApi.stop(id)
        else if (action === 'restart') await serversApi.restart(id)
        await this.fetchServers()
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },

    async saveConfig(id) {
      try {
        await serversApi.saveConfig(id)
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        throw err
      }
    },
  },
})
