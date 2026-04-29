<template>
  <transition name="upgrade-toast">
    <div v-if="visible" class="upgrade-toast" role="alert" aria-live="polite">
      <div class="upgrade-toast__body">
        <div class="upgrade-toast__title">{{ tierLabel }} feature</div>
        <div class="upgrade-toast__msg">{{ message }}</div>
      </div>
      <div class="upgrade-toast__actions">
        <button class="btn btn-light btn-sm" @click="openUpgrade">Upgrade</button>
        <button class="btn btn-link btn-sm text-light" @click="dismiss" aria-label="Dismiss">×</button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'

const visible = ref(false)
const message = ref('')
const tier    = ref('')
const url     = ref('https://flirexa.biz/#pricing')

let dismissTimer = null

function dismiss() {
  visible.value = false
  if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null }
}

function openUpgrade() {
  // Defer to a global UpgradeModal if one is mounted; otherwise fall back
  // to opening the pricing page in a new tab.
  if (window.flirexaOpenUpgrade) {
    window.flirexaOpenUpgrade({ tier: tier.value, url: url.value })
    dismiss()
    return
  }
  window.open(url.value, '_blank', 'noopener')
  dismiss()
}

const tierLabel = computed(() => {
  if (!tier.value) return 'Paid'
  return tier.value.charAt(0).toUpperCase() + tier.value.slice(1)
})

function onUpgradeRequired(event) {
  const d = event.detail || {}
  message.value = d.message || 'This is a paid feature.'
  tier.value    = d.tier || ''
  url.value     = d.url  || 'https://flirexa.biz/#pricing'
  visible.value = true
  if (dismissTimer) clearTimeout(dismissTimer)
  // Auto-hide after 8s — long enough to read, short enough not to be sticky
  dismissTimer = setTimeout(dismiss, 8000)
}

onMounted(() => {
  window.addEventListener('flirexa:upgrade-required', onUpgradeRequired)
})
onBeforeUnmount(() => {
  window.removeEventListener('flirexa:upgrade-required', onUpgradeRequired)
  if (dismissTimer) clearTimeout(dismissTimer)
})
</script>

<style scoped>
.upgrade-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 9999;
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #5865f2 0%, #4752c4 100%);
  color: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25);
  max-width: 420px;
  font-size: 13px;
}
.upgrade-toast__title { font-weight: 600; margin-bottom: 2px; }
.upgrade-toast__msg   { opacity: .92; line-height: 1.4; }
.upgrade-toast__actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.upgrade-toast-enter-active,
.upgrade-toast-leave-active { transition: transform .2s ease, opacity .2s ease; }
.upgrade-toast-enter-from,
.upgrade-toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
