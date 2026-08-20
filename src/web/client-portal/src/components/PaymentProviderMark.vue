<template>
  <span class="fx-provider-mark" :class="providerClass" aria-hidden="true">
    <svg v-if="providerId === 'paypal'" viewBox="0 0 28 28">
      <path class="mark-fill" d="M9 22h3.7l1.1-6.3h2.4c4.8 0 7.2-2.3 7.8-6 .5-3.3-1.8-5.2-5.5-5.2h-6.8L9 22Z" />
      <path class="mark-alt" d="M6 19.5h3.7l1.7-9.6h4.1c3.2 0 5.4-.9 6.7-2.8-.5-2.8-2.8-4.1-6.2-4.1H9L6 19.5Z" />
    </svg>
    <svg v-else-if="providerId === 'nowpayments' || providerId === 'cryptopay'" viewBox="0 0 28 28">
      <path d="M8.2 9.2h7.9a4.8 4.8 0 0 1 0 9.6H12" />
      <path d="M19.8 18.8h-7.9a4.8 4.8 0 1 1 0-9.6H16" />
      <path class="mark-alt" d="m11 14 6 0" />
    </svg>
    <svg v-else-if="providerId === 'balance'" viewBox="0 0 28 28">
      <path d="M5 8.5h16.5A2.5 2.5 0 0 1 24 11v10a2.5 2.5 0 0 1-2.5 2.5h-16A2.5 2.5 0 0 1 3 21V7a2.5 2.5 0 0 1 2.5-2.5H20" />
      <path class="mark-alt" d="M19 14h5v5h-5a2.5 2.5 0 0 1 0-5Z" />
    </svg>
    <svg v-else-if="genericCard" viewBox="0 0 28 28">
      <rect x="3" y="6" width="22" height="16" rx="3" />
      <path class="mark-alt" d="M3 11h22M7 17h5" />
    </svg>
    <span v-else class="fx-provider-letter">{{ letter }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  id: { type: String, default: '' },
  name: { type: String, default: '' },
})

const providerId = computed(() => String(props.id || '').toLowerCase().replace(/[^a-z0-9]/g, ''))
const providerClass = computed(() => `provider-${providerId.value || 'generic'}`)
const genericCard = computed(() => ['paylio', 'mollie', 'razorpay', 'payme'].includes(providerId.value))
const letter = computed(() => ({
  stripe: 'S',
  mollie: 'M',
  razorpay: 'R',
  payme: 'P',
  paylio: 'P',
}[providerId.value] || String(props.name || props.id || '?').trim().charAt(0).toUpperCase()))
</script>

<style scoped>
.fx-provider-mark {
  width: 38px;
  height: 38px;
  min-width: 38px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  color: var(--text-2);
  background: var(--bg-elev);
  box-shadow: var(--shadow-sm);
}
.fx-provider-mark svg { width: 23px; height: 23px; fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round; }
.fx-provider-mark svg .mark-fill { fill: currentColor; stroke: none; }
.fx-provider-mark svg .mark-alt { fill: none; stroke: currentColor; }
.fx-provider-letter { font-size: 15px; font-weight: 750; letter-spacing: -.04em; }
.provider-paypal { color: #1666a8; }
.provider-stripe { color: #635bff; }
.provider-nowpayments { color: #2a8d78; }
.provider-cryptopay { color: #3868d6; }
.provider-balance { color: var(--accent); }
.theme-dark .provider-paypal { color: #62b2ed; }
.theme-dark .provider-stripe { color: #9b96ff; }
.theme-dark .provider-nowpayments { color: #65cdb5; }
.theme-dark .provider-cryptopay { color: #7ea2ff; }
</style>
