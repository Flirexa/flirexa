<!-- Live mm:ss countdown to an ISO `expiresAt`. Ticks every second, turns red in
     the last 2 minutes, shows "Expired" at zero. Emits nothing — pure display. -->
<template>
  <span class="d2cd" :class="{ low, expired }">
    <i class="mdi" :class="expired ? 'mdi-clock-remove-outline' : 'mdi-clock-outline'"></i>
    {{ expired ? (expiredText || 'Expired') : left }}
  </span>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
const props = defineProps({
  expiresAt: { type: [String, Number, Date], default: null },
  expiredText: { type: String, default: '' },
})
const now = ref(Date.now())
let t = null
onMounted(() => { t = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => { if (t) clearInterval(t) })

const ms = computed(() => {
  if (!props.expiresAt) return 0
  return new Date(props.expiresAt).getTime() - now.value
})
const expired = computed(() => !!props.expiresAt && ms.value <= 0)
const low = computed(() => !expired.value && ms.value <= 120000)
const left = computed(() => {
  const s = Math.max(0, Math.floor(ms.value / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})
</script>

<style scoped>
.d2cd { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 600; color: var(--d2-text-2); font-variant-numeric: tabular-nums; }
.d2cd .mdi { font-size: 14px; }
.d2cd.low { color: var(--d2-amber); }
.d2cd.expired { color: var(--d2-red); }
</style>
