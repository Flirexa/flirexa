import { defineStore } from 'pinia'
import { serversApi } from '../api'

// localStorage cache so the Servers tab stays usable when the API is briefly
// 5xx-ing — operators need the delete button on dead boxes more than they
// need fresh data. Cache key is namespaced to avoid colliding with anything
// else.
const CACHE_KEY = 'srv:list-cache:v1'

function _loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || !Array.isArray(parsed.items)) return null
    return parsed
  } catch { return null }
}

function _saveCache(items) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ items, savedAt: Date.now() }))
  } catch { /* quota / disabled — ignore */ }
}

export const useServersStore = defineStore('servers', {
  state: () => ({
    servers: [],
    currentServer: null,
    loading: false,
    error: null,
    // True when `servers` is from localStorage because the API call failed.
    // Cleared on the next successful fetch. UI shows a banner while set.
    usingCache: false,
    cacheSavedAt: null,
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
        const items = (data && data.items) ? data.items : (Array.isArray(data) ? data : [])
        this.servers = items
        this.usingCache = false
        this.cacheSavedAt = null
        _saveCache(items)
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        // Only fall back to cache when we have NOTHING to show. If `servers`
        // already holds a previous successful load (e.g. mid-session
        // refresh), keep it as-is — last good wins, no flicker.
        if (this.servers.length === 0) {
          const cached = _loadCache()
          if (cached && cached.items.length > 0) {
            this.servers = cached.items
            this.usingCache = true
            this.cacheSavedAt = cached.savedAt || null
          }
        }
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

    async updateServer(id, data) {
      try {
        const { data: server } = await serversApi.update(id, data)
        const idx = this.servers.findIndex((s) => s.id === id)
        if (idx >= 0) this.servers[idx] = server
        return server
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
