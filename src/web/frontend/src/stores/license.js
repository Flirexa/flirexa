import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useLicenseStore = defineStore('license', () => {
  const features  = ref([])
  const tier      = ref('free')
  const loaded    = ref(false)

  async function load() {
    try {
      const { data } = await api.get('/system/license')
      features.value = data.features || []
      tier.value     = data.type || data.tier || 'free'
      loaded.value   = true
    } catch (e) {
      // Endpoint may 401 before login — leave defaults; next call will retry.
      features.value = []
      tier.value     = 'free'
    }
  }

  function has(feature) {
    return features.value.includes(feature)
  }

  const isPaid = computed(() => tier.value !== 'free' && tier.value !== 'trial')

  return { features, tier, loaded, load, has, isPaid }
})
