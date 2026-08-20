<template>
  <div v-if="loadingMode" class="fx-page">
    <div class="fx-card fx-device-mode-loading">{{ $t('common.loading') }}</div>
  </div>
  <AdvancedDevices v-else-if="portalMode === 'advanced'" />
  <SimpleDevices v-else />
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { portalApi } from '../api/index.js'
import AdvancedDevices from './AdvancedDevices.vue'
import SimpleDevices from './SimpleDevices.vue'

const loadingMode = ref(true)
const portalMode = ref('simple')

onMounted(async () => {
  try {
    const { data } = await portalApi.getFeatures()
    portalMode.value = data?.portal_mode === 'advanced' ? 'advanced' : 'simple'
  } catch {
    // A presentation lookup must never prevent device management. The simple
    // experience is the least technical and therefore the safest fallback.
    portalMode.value = 'simple'
  } finally {
    loadingMode.value = false
  }
})
</script>

<style scoped>
.fx-device-mode-loading {
  min-height: 180px;
  display: grid;
  place-items: center;
  color: var(--text-3);
  font-size: 13px;
}
</style>
