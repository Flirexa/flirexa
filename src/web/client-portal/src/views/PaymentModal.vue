<template>
  <div class="payment-overlay" @click.self="$emit('close')">
    <div class="payment-modal">
      <div class="payment-modal-header">
        <h5 class="mb-0">{{ stepTitle }}</h5>
        <button type="button" class="btn-close" @click="$emit('close')"></button>
      </div>

      <div class="payment-modal-body">
        <!-- Step 1: Select Plan -->
        <div v-if="step === 1">
          <div class="plan-grid">
            <div v-for="plan in plans" :key="plan.tier" class="plan-option"
              :class="{ selected: selectedPlan?.tier === plan.tier }" @click="selectedPlan = plan">
              <div class="plan-option-name">{{ plan.name }}</div>
              <div class="plan-option-price">${{ plan.price_monthly_usd }}<small>{{ $t('pay.perMonth') }}</small></div>
              <div class="plan-option-info">
                {{ $t('pay.maxDevices', { n: plan.max_devices }) }} &middot;
                {{ plan.traffic_limit_gb
                    ? $t('pay.trafficGb', { gb: plan.traffic_limit_gb })
                    : $t('pay.unlimitedData') }} &middot;
                {{ plan.bandwidth_limit_mbps
                    ? plan.bandwidth_limit_mbps + ' Mbps'
                    : $t('pay.maxBandwidth') }}
              </div>
            </div>
          </div>
          <div class="mt-3">
            <label class="form-label fw-bold small">{{ $t('pay.duration') }}</label>
            <!-- Custom ladder from the plan, when the operator defined one -->
            <div v-if="customTiers" class="duration-grid">
              <label v-for="t in customTiers" :key="t.days" class="duration-option"
                     :class="{ selected: duration === String(t.days) }">
                <input type="radio" name="dur" :value="String(t.days)" v-model="duration" class="d-none" />
                <span class="fw-bold">{{ t.label || (t.days + ' ' + $t('pay.daysShort')) }}</span>
                <small class="d-block text-muted">${{ Number(t.price_usd || 0).toFixed(2) }}</small>
              </label>
            </div>
            <!-- Legacy monthly/quarterly/yearly buttons when no custom ladder set -->
            <div v-else class="duration-grid">
              <label class="duration-option" :class="{ selected: duration === '30' }">
                <input type="radio" name="dur" value="30" v-model="duration" class="d-none" />
                <span class="fw-bold">{{ $t('pay.month1') }}</span>
              </label>
              <label class="duration-option" :class="{ selected: duration === '90' }">
                <input type="radio" name="dur" value="90" v-model="duration" class="d-none" />
                <span class="fw-bold">{{ $t('pay.months3') }}</span>
                <small class="d-block text-success">{{ $t('pay.save10') }}</small>
              </label>
              <label class="duration-option" :class="{ selected: duration === '365' }">
                <input type="radio" name="dur" value="365" v-model="duration" class="d-none" />
                <span class="fw-bold">{{ $t('pay.year1') }}</span>
                <small class="d-block text-success">{{ $t('pay.save20') }}</small>
              </label>
            </div>
          </div>
          <!-- Promo Code -->
          <div v-if="operatorFeatures.promo_codes" class="mt-3">
            <div class="input-group input-group-sm">
              <input type="text" class="form-control" v-model="promoCode" :placeholder="$t('pay.promoPlaceholder')" :disabled="promoApplied">
              <button class="btn btn-outline-primary" @click="applyPromo" :disabled="!promoCode || promoApplied || promoChecking">
                {{ promoApplied ? '✓' : ($t('pay.applyPromo')) }}
              </button>
            </div>
            <small v-if="promoApplied" class="text-success">{{ promoMessage }}</small>
            <small v-if="promoError" class="text-danger">{{ promoError }}</small>
          </div>
          <div class="total-bar mt-3">
            <span>{{ $t('pay.total') }}</span>
            <span class="total-amount">${{ totalPrice }}</span>
          </div>
        </div>

        <!-- Step 2: Select Payment Method -->
        <div v-if="step === 2">
          <!-- Provider Selection -->
          <div v-if="providers.length > 1" class="mb-3">
            <label class="form-label fw-bold small">{{ $t('pay.paymentMethod') }}</label>
            <div class="provider-grid">
              <div v-for="prov in providers" :key="prov.id" class="provider-option"
                :class="{ selected: selectedProvider === prov.id }" @click="selectedProvider = prov.id">
                <span class="provider-icon">{{ getProviderIcon(prov.id) }}</span>
                <span class="provider-name">{{ prov.name }}</span>
              </div>
            </div>
          </div>

          <!-- Every provider we ship (Stripe / Mollie / Razorpay / Payme /
               PayLio / NOWPayments / PayPal / CryptoPay) opens its own
               hosted checkout where the customer picks the actual coin /
               card / currency. Surface the provider's display name so
               single-provider setups don't leave the customer wondering
               who they're paying, and skip the client-side currency
               picker entirely — it was confusing customers and, on
               NOWPayments, pre-seeded `price_currency=USDT` which broke
               every coin's availability lookup on the hosted page. -->
          <div class="card-pay-summary">
            <div class="card-pay-line">
              <span class="card-pay-icon">{{ getProviderIcon(selectedProvider) }}</span>
              <div>
                <div class="card-pay-title">{{ selectedProviderName }}</div>
                <div class="card-pay-sub">
                  {{ $t('pay.cardCheckoutHint') }}
                </div>
              </div>
            </div>
          </div>

          <div class="alert alert-info mt-3 small py-2">{{ $t('pay.redirectHint') }}</div>
        </div>

        <!-- Step 3: Invoice -->
        <div v-if="step === 3 && invoice">
          <div class="text-center">
            <div class="mb-3">
              <label class="text-muted small">{{ $t('pay.amount') }}</label>
              <div class="input-group input-group-sm">
                <input type="text" class="form-control text-center fw-bold" :value="invoiceDisplayAmount" readonly />
                <button class="btn btn-outline-secondary" @click="copyToClipboard(String(invoice.amount_crypto || invoice.amount_usd))">{{ copied ? $t('common.copied') : $t('common.copy') }}</button>
              </div>
            </div>
            <div class="alert alert-warning small py-2">{{ $t('pay.expiresIn', { min: expiryMinutes }) }}</div>
            <div v-if="invoice.amount_crypto" class="small text-muted mb-2">{{ $t('pay.cryptoRateDisclaimer') }}</div>
            <a v-if="invoice.payment_url" :href="invoice.payment_url" target="_blank" rel="noreferrer" class="btn btn-primary w-100 mb-2">{{ $t('pay.openPaymentPage') }}</a>
            <button class="btn btn-outline-primary btn-sm w-100" @click="checkPayment" :disabled="checkingPayment">
              <span v-if="checkingPayment" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('pay.checkStatus') }}
            </button>
          </div>
        </div>

        <div v-if="loading" class="text-center py-4">
          <div class="spinner-border text-primary"></div>
          <div class="mt-2 small">{{ $t('pay.processing') }}</div>
        </div>
        <div v-if="error" class="alert alert-danger small mt-2 py-2">{{ error }}</div>
      </div>

      <div class="payment-modal-footer">
        <button type="button" class="btn btn-secondary btn-sm" @click="goBack">
          {{ step > 1 && step < 3 ? $t('common.back') : $t('common.close') }}
        </button>
        <button type="button" class="btn btn-primary btn-sm" @click="nextStep" :disabled="!canProceed || loading" v-if="step < 3">
          {{ step === 2 ? $t('pay.continueToPayment') : $t('common.next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { apiErrorMessage, copyText } from '../utils.js'

const emit = defineEmits(['close', 'success'])
const props = defineProps({
  plan: { type: Object, default: null },
  preselectProvider: { type: String, default: '' },
})

const { t } = useI18n()

const step = ref(1)
const plans = ref([])
const providers = ref([])
const selectedProvider = ref('')
const selectedPlan = ref(null)
const duration = ref('30')
// Always submit USD as the price denomination — every hosted-checkout
// provider we ship accepts it and runs its own coin / fiat picker
// downstream. Forcing the customer to pick a crypto here was both
// redundant and bug-prone: NOWPayments interpreted `currency=USDT` as
// the price unit and broke availability lookup on its hosted page.
const selectedCurrency = ref('USD')
const invoice = ref(null)
const loading = ref(false)
const error = ref(null)
const checkingPayment = ref(false)
const promoCode = ref('')
const promoApplied = ref(false)
const promoChecking = ref(false)
const promoMessage = ref('')
const promoError = ref('')
const promoDiscount = ref(0)
const operatorFeatures = ref({ promo_codes: false })
const copied = ref(false)

const stepTitle = computed(() => {
  if (step.value === 1) return t('pay.choosePlan')
  if (step.value === 2) return t('pay.selectPayment')
  return t('pay.invoice')
})

// Operator-defined duration ladder takes precedence over the legacy
// monthly/quarterly/yearly trio. When the plan ships `pricing_tiers`
// (non-empty list), we render those buttons EXACTLY as defined and
// price each one from the ladder entry — no proration, no
// monthly-equivalent math.
const customTiers = computed(() => {
  const t = selectedPlan.value?.pricing_tiers
  return Array.isArray(t) && t.length ? t : null
})

// When the user picks a plan that ships a custom ladder, snap
// `duration` to the first tier's days so the price card and Pay
// button reflect a valid selection instead of staying on stale '30'
// (which may not exist in the ladder at all).
watch(selectedPlan, (plan) => {
  if (!plan) return
  const tiers = Array.isArray(plan.pricing_tiers) ? plan.pricing_tiers : null
  if (tiers && tiers.length) {
    if (!tiers.some(t => String(t.days) === duration.value)) {
      duration.value = String(tiers[0].days)
    }
  } else {
    // Reverting from a custom-ladder plan to a legacy plan — make
    // sure duration is one of the legacy options.
    if (!['30', '90', '365'].includes(duration.value)) {
      duration.value = '30'
    }
  }
})

const totalPrice = computed(() => {
  if (!selectedPlan.value) return 0
  const days = parseInt(duration.value)
  let price
  if (customTiers.value) {
    const hit = customTiers.value.find(t => Number(t.days) === days)
    price = hit ? Number(hit.price_usd || 0) : 0
  } else {
    const monthly = selectedPlan.value.price_monthly_usd
    if (days >= 365) price = selectedPlan.value.price_yearly_usd || (monthly * 12)
    else if (days >= 90) price = selectedPlan.value.price_quarterly_usd || (monthly * 3)
    else price = (monthly * days / 30).toFixed(2)
  }
  if (promoDiscount.value > 0) price = (Number(price) * (1 - promoDiscount.value / 100)).toFixed(2)
  return price
})

const canProceed = computed(() => {
  if (step.value === 1) return selectedPlan.value && duration.value
  if (step.value === 2) {
    return selectedCurrency.value
      && providers.value.some(provider => provider.id === selectedProvider.value)
  }
  return false
})

// Heartbeat ref that ticks every 15 seconds. expiryMinutes depends on
// `now.value` (rather than calling `new Date()` directly inside the
// computed), so the displayed countdown actually updates instead of
// freezing at whatever value the modal was opened with.
const now = ref(Date.now())
let nowInterval = null
onMounted(() => {
  nowInterval = setInterval(() => { now.value = Date.now() }, 15000)
})
onBeforeUnmount(() => {
  if (nowInterval) { clearInterval(nowInterval); nowInterval = null }
})
const expiryMinutes = computed(() => {
  if (!invoice.value?.expires_at) return 60
  return Math.max(0, Math.floor(
    (new Date(invoice.value.expires_at).getTime() - now.value) / 60000
  ))
})

const invoiceDisplayAmount = computed(() => {
  if (!invoice.value) return ''
  if (invoice.value.amount_crypto) return `${invoice.value.amount_crypto} ${invoice.value.currency}`
  return `$${invoice.value.amount_usd || totalPrice.value}`
})

const selectedProviderName = computed(() => {
  const p = providers.value.find((x) => x.id === selectedProvider.value)
  return p?.display_name || p?.name || selectedProvider.value
})

const getProviderIcon = (id) => {
  const icons = {
    cryptopay:   '💎',
    paypal:      '🅿️',
    nowpayments: '🔗',
    stripe:      '💳',
    mollie:      '💳',
    razorpay:    '💳',
    payme:       '💳',
    paylio:      '💳',
  }
  return icons[id] || '💰'
}

const goBack = () => { step.value === 2 ? step.value = 1 : emit('close') }

const nextStep = async () => { step.value === 2 ? await createInvoice() : step.value++ }

const createInvoice = async () => {
  loading.value = true
  error.value = null
  try {
    const invoiceData = {
      plan_tier: selectedPlan.value.tier,
      duration_days: parseInt(duration.value),
      currency: selectedCurrency.value,
      provider: selectedProvider.value,
    }
    if (promoApplied.value && promoCode.value) invoiceData.promo_code = promoCode.value.trim().toUpperCase()
    const response = await portalApi.createInvoice(invoiceData)
    invoice.value = response.data
    if (invoice.value?.payment_url) {
      const target = new URL(invoice.value.payment_url, window.location.origin)
      if (target.protocol !== 'https:') throw new Error(t('pay.invalidPaymentLink'))
      // Keep the flow in one tab: provider approval returns to /payments,
      // where the authenticated portal safely captures and verifies PayPal.
      window.location.assign(target.href)
      return
    }
    step.value = 3
    startPaymentCheck()
  } catch (err) {
    const detail = apiErrorMessage(err, '')
    // If the promo was reserved at validate-time but is no longer valid
    // here (admin disabled / max_uses just hit / expired between
    // validate and submit), drop the local promo state so the user
    // sees the full price again and can retry without the modal stuck
    // on a stale discount.
    if (promoApplied.value && /promo/i.test(detail)) {
      promoApplied.value = false
      promoCode.value = ''
      promoError.value = t('pay.promoNoLongerValid') || detail
    } else {
      error.value = detail || t('pay.createInvoiceFailed') || 'Failed to create invoice'
    }
  } finally { loading.value = false }
}

const checkPayment = async () => {
  checkingPayment.value = true
  try {
    const response = await portalApi.checkPayment(invoice.value.invoice_id)
    if (response.data.status === 'completed' || response.data.status === 'paid') { emit('success'); emit('close') }
    else { error.value = t('pay.notReceived'); setTimeout(() => { error.value = null }, 3000) }
  } catch { /* ignore */ }
  finally { checkingPayment.value = false }
}

let paymentCheckInterval = null
const startPaymentCheck = () => {
  paymentCheckInterval = setInterval(async () => {
    try {
      const response = await portalApi.checkPayment(invoice.value.invoice_id)
      if (response.data.status === 'completed' || response.data.status === 'paid') { clearInterval(paymentCheckInterval); emit('success') }
    } catch { /* ignore */ }
  }, 10000)
}

const applyPromo = async () => {
  promoChecking.value = true
  promoError.value = ''
  promoMessage.value = ''
  try {
    const { data } = await portalApi.validatePromo(promoCode.value.trim().toUpperCase())
    if (data.valid) {
      promoApplied.value = true
      if (data.discount_type === 'percent') {
        promoDiscount.value = data.discount_value
        promoMessage.value = `-${data.discount_value}% discount applied!`
      } else {
        promoMessage.value = `+${data.discount_value} bonus days!`
      }
    } else {
      promoError.value = data.error || 'Invalid promo code'
    }
  } catch (err) {
    promoError.value = apiErrorMessage(err, 'Failed to validate promo')
  } finally { promoChecking.value = false }
}

const copyToClipboard = async (text) => {
  if (!await copyText(text)) return
  copied.value = true
  setTimeout(() => { copied.value = false }, 1500)
}

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  try {
    const [plansRes, providersRes] = await Promise.all([
      portalApi.getPlans(),
      portalApi.getProviders()
    ])
    plans.value = Array.isArray(plansRes.data)
      ? plansRes.data.filter(p => p.tier !== 'free')
      : []
    providers.value = Array.isArray(providersRes.data)
      ? providersRes.data.filter(provider => provider.configured !== false)
      : []
    if (!plans.value.length) error.value = t('common.loadError')
    else if (!providers.value.length) error.value = t('payments.noProvidersConfigured')
    // Feature decoration must never block the working purchase flow. The
    // backend still enforces promo/provider entitlements if this optional
    // request fails.
    try {
      const featuresRes = await portalApi.getFeatures()
      operatorFeatures.value = {
        ...operatorFeatures.value,
        ...(featuresRes.data?.features || {}),
      }
    } catch (_) { /* keep commercial controls hidden */ }
    // Honor the parent's preselectProvider if it matches a configured one,
    // otherwise fall back to the first available provider.
    const wanted = (props.preselectProvider || '').trim()
    const match = wanted && providers.value.find(p => p.id === wanted)
    if (match) selectedProvider.value = match.id
    else if (providers.value.length >= 1) selectedProvider.value = providers.value[0].id
  } catch (err) {
    error.value = apiErrorMessage(err, t('common.loadError'))
  }
  if (props.plan) {
    selectedPlan.value = props.plan
    // Plans.vue picks a billing period (monthly/quarterly/yearly)
    // and passes it on the plan object so the modal jumps straight
    // to the payment step with the right duration. Previously the
    // `duration` ref kept its default '30', so a customer who chose
    // "1 year" saw the yearly price on the Plans card but got
    // billed + provisioned for one month. Map billing_period to the
    // backend's day count up front.
    const map = { yearly: '365', quarterly: '90', monthly: '30' }
    const d = map[props.plan.billing_period]
    if (d) duration.value = d
    if (props.plan.price_monthly_usd > 0) step.value = 2
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
  if (paymentCheckInterval) clearInterval(paymentCheckInterval)
})
</script>

<style scoped>
.payment-overlay { position: fixed; inset: 0; background: rgba(34,41,47,.55); z-index: 1050; overflow-y: auto; padding: 1rem; display: flex; align-items: flex-start; justify-content: center; animation: overlayIn .25s ease; }
.payment-modal { background: var(--vxy-modal-bg); color: var(--vxy-text); border-radius: .75rem; width: 100%; max-width: 500px; margin: auto; box-shadow: 0 20px 60px rgba(0,0,0,.3); display: flex; flex-direction: column; max-height: calc(100vh - 2rem); animation: modalSlideIn .25s ease; }
@keyframes overlayIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes modalSlideIn { from { opacity: 0; transform: scale(.95) translateY(-10px); } to { opacity: 1; transform: scale(1) translateY(0); } }
.payment-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--vxy-border); flex-shrink: 0; }
.payment-modal-body { padding: 1.25rem; overflow-y: auto; flex: 1; min-height: 0; }
.payment-modal-footer { display: flex; justify-content: space-between; padding: 1rem 1.5rem; border-top: 1px solid var(--vxy-border); flex-shrink: 0; }
.plan-grid { display: grid; grid-template-columns: 1fr; gap: .5rem; }
.plan-option { border: 2px solid var(--vxy-border); border-radius: .5rem; padding: .75rem 1rem; cursor: pointer; transition: all .2s; display: flex; align-items: center; gap: .75rem; color: var(--vxy-text); }
.plan-option.selected { border-color: var(--vxy-primary); background: var(--vxy-primary-light); }
.plan-option-name { font-weight: 700; min-width: 80px; color: var(--vxy-heading); }
.plan-option-price { font-weight: 700; color: var(--vxy-primary); white-space: nowrap; }
.plan-option-price small { font-weight: 400; color: var(--vxy-muted); }
.plan-option-info { font-size: .75rem; color: var(--vxy-muted); margin-left: auto; }
.duration-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; }
.duration-option { border: 2px solid var(--vxy-border); border-radius: .5rem; padding: .5rem; text-align: center; cursor: pointer; transition: all .2s; font-size: .85rem; color: var(--vxy-text); }
.duration-option.selected { border-color: var(--vxy-primary); background: var(--vxy-primary-light); }
.total-bar { display: flex; justify-content: space-between; align-items: center; background: var(--vxy-hover-bg); padding: .75rem 1rem; border-radius: .375rem; font-weight: 600; color: var(--vxy-text); }
.total-amount { font-size: 1.5rem; color: var(--vxy-primary); font-weight: 800; }
.provider-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: .5rem; }
.provider-option { border: 2px solid var(--vxy-border); border-radius: .5rem; padding: .75rem; text-align: center; cursor: pointer; transition: all .2s; color: var(--vxy-text); }
.provider-option.selected { border-color: var(--vxy-primary); background: var(--vxy-primary-light); }
.provider-icon { font-size: 1.5rem; display: block; margin-bottom: .25rem; }
.provider-name { font-size: .8rem; font-weight: 600; }
.crypto-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; }
.crypto-option { border: 2px solid var(--vxy-border); border-radius: .5rem; padding: .75rem .5rem; text-align: center; cursor: pointer; transition: all .2s; color: var(--vxy-text); }
.crypto-option.selected { border-color: var(--vxy-warning); background: var(--vxy-warning-light); }
.crypto-option-icon { font-size: 1.75rem; display: block; margin-bottom: .25rem; }
.crypto-option-name { font-size: .8rem; font-weight: 700; }

/* Card-checkout summary panel: no currency picker, just "you'll be redirected
   to the hosted card page" framing so the user understands why the picker
   they saw with crypto/PayPal isn't here. */
.card-pay-summary {
  border: 1px solid var(--vxy-border);
  border-radius: .5rem;
  padding: 1rem 1.1rem;
  background: var(--vxy-hover-bg);
}
.card-pay-line { display: flex; align-items: center; gap: .85rem; }
.card-pay-icon { font-size: 1.75rem; line-height: 1; flex-shrink: 0; }
.card-pay-title { font-weight: 700; font-size: .95rem; color: var(--vxy-text); }
.card-pay-sub { font-size: .8rem; color: var(--vxy-muted); margin-top: 2px; line-height: 1.4; }

@media (max-width: 768px) {
  /* Bottom sheet on mobile */
  .payment-overlay {
    align-items: flex-end;
    padding: 0;
  }
  .payment-modal {
    max-width: 100%;
    margin: 0;
    border-radius: 1rem 1rem 0 0;
    max-height: 92vh;
    animation: modalSlideUp .3s ease;
  }
  @keyframes modalSlideUp {
    from { transform: translateY(100%); opacity: .8; }
    to   { transform: translateY(0);   opacity: 1; }
  }
  /* Drag handle */
  .payment-modal-header::before {
    content: '';
    display: block;
    position: absolute;
    top: .5rem; left: 50%;
    transform: translateX(-50%);
    width: 36px; height: 4px;
    border-radius: 2px;
    background: var(--vxy-border);
  }
  .payment-modal-header { position: relative; padding: 1.25rem 1rem .875rem; }
  .payment-modal-body { padding: 1rem; }
  .payment-modal-footer {
    padding: .75rem 1rem;
    padding-bottom: calc(.75rem + env(safe-area-inset-bottom, 0px));
  }
  .provider-grid { grid-template-columns: repeat(2, 1fr); }
  .duration-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 400px) {
  .duration-grid { grid-template-columns: 1fr; }
  .crypto-grid { grid-template-columns: repeat(2, 1fr); }
  .plan-option { flex-wrap: wrap; gap: .4rem; padding: .65rem .75rem; }
  .plan-option-info { margin-left: 0; font-size: .7rem; }
  .total-amount { font-size: 1.25rem; }
}
</style>
