// Tiny store for the customer-app integration toggle. Settings → Apps
// flips `enabled`; the sidebar and Notifications view both read it
// instead of poking the system_config endpoint themselves on every
// render. Single source of truth, no duplicated fetch logic.
import { defineStore } from 'pinia'
import api from '../api'

export const useAppsStore = defineStore('apps', {
  state: () => ({
    loaded:  false,
    enabled: false,    // app_integration_enabled (system_config)
    name:    '',       // app_name — shown verbatim in the Push Notifications page
                       // subtitle so each operator sees their own brand, not
                       // the brand string that was hardcoded for one operator
                       // and leaked into every install.
    fcm_set: false,    // true if fcm_server_key is set (legacy push)
  }),
  actions: {
    async refresh() {
      try {
        const { data } = await api.get('/system/notification-settings')
        this.enabled = String(data?.app_integration_enabled || '').toLowerCase() === 'true'
        this.name    = (data?.app_name || '').trim()
        this.fcm_set = !!data?.fcm_server_key_set
      } catch (e) {
        // First-render gracefully degrades to "disabled" — the worst case
        // is one menu item that's actually gated by license still shows
        // for a few frames before the real state arrives.
        this.enabled = false
        this.name    = ''
        this.fcm_set = false
      } finally {
        this.loaded = true
      }
    },
  },
})
