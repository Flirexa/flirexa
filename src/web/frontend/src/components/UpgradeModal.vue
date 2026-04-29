<template>
  <transition name="upgrade-modal">
    <div v-if="open" class="upgrade-modal-backdrop" @click.self="close">
      <div class="upgrade-modal">
        <button class="upgrade-modal__close" @click="close" aria-label="Close">×</button>
        <h2 class="upgrade-modal__title">Upgrade to {{ tierLabel }}</h2>
        <p v-if="reason" class="upgrade-modal__reason">{{ reason }}</p>

        <div class="upgrade-modal__tiers">
          <div
            v-for="t in tiers"
            :key="t.id"
            class="upgrade-tier"
            :class="{ 'upgrade-tier--featured': t.id === preferredTier }"
            @click="selectedTier = t.id"
          >
            <input type="radio" :value="t.id" v-model="selectedTier" />
            <div class="upgrade-tier__name">{{ t.name }}</div>
            <div class="upgrade-tier__price">${{ t.price }}<span>/mo</span></div>
            <ul class="upgrade-tier__features">
              <li v-for="f in t.features" :key="f">{{ f }}</li>
            </ul>
          </div>
        </div>

        <label class="upgrade-modal__email">
          <span>Email (for activation code delivery)</span>
          <input type="email" v-model="email" placeholder="you@example.com" required />
        </label>

        <div v-if="error" class="upgrade-modal__error">{{ error }}</div>

        <button
          class="btn btn-primary upgrade-modal__pay"
          :disabled="!email || loading"
          @click="startCheckout"
        >
          {{ loading ? 'Opening NOWPayments…' : 'Pay with crypto →' }}
        </button>
        <p class="upgrade-modal__note">
          Payment is processed by NOWPayments. After confirmation
          (10–30 min) you receive an activation code by email — paste
          it under <strong>Settings → License</strong>.
        </p>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const TIERS = [
  {
    id: 'starter',
    name: 'Starter',
    price: 19,
    features: ['Hysteria2 + TUIC', 'Promo codes', 'Auto-renewal', 'Up to 300 clients'],
  },
  {
    id: 'business',
    name: 'Business',
    price: 49,
    features: ['Multi-server (up to 10)', 'Client Telegram bot', 'Traffic rules', 'White-label basic', 'Auto-backup'],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 149,
    features: ['Site-to-site corporate VPN', 'Multi-admin RBAC', 'Full white-label', 'Unlimited clients/servers'],
  },
]

const open          = ref(false)
const reason        = ref('')
const preferredTier = ref('business')
const selectedTier  = ref('business')
const email         = ref('')
const error         = ref('')
const loading       = ref(false)

const tiers = TIERS
const tierLabel = computed(() => {
  const t = TIERS.find(x => x.id === selectedTier.value)
  return t ? t.name : 'Paid'
})

function close() {
  open.value = false
  error.value = ''
}

async function startCheckout() {
  error.value = ''
  loading.value = true
  try {
    const resp = await fetch('https://flirexa.biz/api/v1/subscriptions/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plan:           selectedTier.value,
        billing_period: 'monthly',
        customer_email: email.value,
      }),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`License server returned ${resp.status}: ${text.slice(0, 160)}`)
    }
    const data = await resp.json()
    if (data.payment_url) {
      // Redirect into NOWPayments invoice in a new tab.
      window.open(data.payment_url, '_blank', 'noopener')
      close()
    } else {
      throw new Error('License server did not return a payment URL')
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

function flirexaOpenUpgrade(opts) {
  preferredTier.value = opts?.tier || 'business'
  selectedTier.value  = opts?.tier || 'business'
  reason.value        = opts?.reason || (opts?.feature ? `Required for: ${opts.feature}` : '')
  open.value          = true
}

onMounted(() => {
  // Expose so any view (or the UpgradeBanner toast) can pop the modal.
  window.flirexaOpenUpgrade = flirexaOpenUpgrade
  // Best-effort: cache hardware_id from the system endpoint so checkout
  // can bind the resulting subscription to this install.
  try {
    fetch('/api/v1/system/license', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) window.__flirexaHardwareId = d.hardware_id || d.server_id || '' })
      .catch(() => {})
  } catch (_) {}
})
</script>

<style scoped>
.upgrade-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .55);
  display: flex; align-items: center; justify-content: center;
  z-index: 9998;
  padding: 16px;
}
.upgrade-modal {
  background: var(--card-bg, #14171c);
  border: 1px solid var(--card-border, #232830);
  border-radius: 12px;
  width: 100%;
  max-width: 760px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  padding: 28px;
  position: relative;
}
.upgrade-modal__close {
  position: absolute; top: 12px; right: 14px;
  background: none; border: none;
  color: var(--muted, #8a93a3);
  font-size: 24px; cursor: pointer;
}
.upgrade-modal__title  { margin: 0 0 6px; font-size: 22px; }
.upgrade-modal__reason { color: var(--muted, #8a93a3); margin: 0 0 18px; font-size: 13px; }
.upgrade-modal__tiers  { display: grid; gap: 12px; grid-template-columns: 1fr; margin-bottom: 18px; }
@media (min-width: 640px) {
  .upgrade-modal__tiers { grid-template-columns: repeat(3, 1fr); }
}
.upgrade-tier {
  position: relative;
  padding: 14px 14px 16px;
  border: 1px solid var(--card-border, #232830);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color .15s;
}
.upgrade-tier:hover                     { border-color: rgba(88, 101, 242, .5); }
.upgrade-tier--featured                 { border-color: #5865f2; box-shadow: 0 0 0 1px #5865f2; }
.upgrade-tier input[type=radio]         { position: absolute; top: 12px; right: 12px; }
.upgrade-tier__name                     { font-weight: 600; margin-bottom: 4px; }
.upgrade-tier__price                    { font-size: 22px; font-weight: 600; margin-bottom: 8px; }
.upgrade-tier__price span               { font-size: 12px; font-weight: 400; color: var(--muted, #8a93a3); }
.upgrade-tier__features                 { margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.55; color: var(--muted, #8a93a3); }
.upgrade-modal__email                   { display: block; margin-bottom: 14px; font-size: 13px; }
.upgrade-modal__email span              { display: block; margin-bottom: 4px; color: var(--muted, #8a93a3); }
.upgrade-modal__email input             { width: 100%; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--card-border, #232830); background: var(--bg, #0d0f12); color: inherit; }
.upgrade-modal__error                   { color: #e35d6a; font-size: 13px; margin-bottom: 12px; }
.upgrade-modal__pay                     { width: 100%; padding: 11px; font-weight: 600; }
.upgrade-modal__note                    { font-size: 11px; color: var(--muted, #8a93a3); line-height: 1.5; margin-top: 10px; margin-bottom: 0; }
.upgrade-modal-enter-active,
.upgrade-modal-leave-active             { transition: opacity .15s; }
.upgrade-modal-enter-from,
.upgrade-modal-leave-to                 { opacity: 0; }
</style>
