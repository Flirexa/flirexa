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
                {{ plan.max_devices }} {{ $t('pay.dev') }} &middot;
                {{ plan.traffic_limit_gb ? plan.traffic_limit_gb + ' GB' : $t('pay.unlim') }} &middot;
                {{ plan.bandwidth_limit_mbps ? plan.bandwidth_limit_mbps + ' Mbps' : 'Max' }}
              </div>
            </div>
          </div>
          <div class="mt-3">
            <label class="form-label fw-bold small">{{ $t('pay.duration') }}</label>
            <div class="duration-grid">
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
          <div class="mt-3">
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

          <!-- Currency Selection (for crypto providers) -->
          <div v-if="selectedProvider !== 'paypal'">
            <label class="form-label fw-bold small">{{ $t('pay.selectCurrency') }}</label>
            <div class="crypto-grid">
              <div v-for="currency in cryptoCurrencies" :key="currency.code" class="crypto-option"
                :class="{ selected: selectedCurrency === currency.code }" @click="selectedCurrency = currency.code">
                <span class="crypto-option-icon">{{ getCryptoIcon(currency.code) }}</span>
                <span class="crypto-option-name">{{ currency.code }}</span>
              </div>
            </div>
          </div>

          <!-- PayPal currency -->
          <div v-else>
            <label class="form-label fw-bold small">{{ $t('pay.selectCurrency') }}</label>
            <div class="crypto-grid">
              <div v-for="cur in paypalCurrencies" :key="cur.code" class="crypto-option"
                :class="{ selected: selectedCurrency === cur.code }" @click="selectedCurrency = cur.code">
                <span class="crypto-option-icon">{{ cur.icon }}</span>
                <span class="crypto-option-name">{{ cur.code }}</span>
              </div>
            </div>
          </div>

          <div class="alert alert-info mt-3 small py-2">{{ $t('pay.paymentLinkHint') }}</div>
        </div>

        <!-- Step 3: Invoice -->
        <div v-if="step === 3 && invoice">
          <div class="text-center">
            <div class="mb-3">
              <label class="text-muted small">{{ $t('pay.amount') }}</label>
              <div class="input-group input-group-sm">
                <input type="text" class="form-control text-center fw-bold" :value="invoiceDisplayAmount" readonly />
                <button class="btn btn-outline-secondary" @click="copyToClipboard(String(invoice.amount_crypto || invoice.amount_usd))">{{ $t('common.copy') }}</button>
              </div>
            </div>
            <div class="alert alert-warning small py-2">{{ $t('pay.expiresIn', { min: expiryMinutes }) }}</div>
            <a v-if="invoice.payment_url" :href="invoice.payment_url" target="_blank" class="btn btn-primary w-100 mb-2">{{ $t('pay.openPaymentPage') }}</a>
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
          {{ step === 2 ? $t('pay.createInvoice') : $t('common.next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'

const emit = defineEmits(['close', 'success'])
const props = defineProps({ plan: { type: Object, default: null } })

const { t } = useI18n()

const step = ref(1)
const plans = ref([])
const providers = ref([])
const selectedProvider = ref('cryptopay')
const cryptoCurrencies = ref([
  { code: 'USDT', name: 'Tether' }, { code: 'BTC', name: 'Bitcoin' },
  { code: 'TON', name: 'Toncoin' }, { code: 'ETH', name: 'Ethereum' },
  { code: 'USDC', name: 'USD Coin' }, { code: 'BUSD', name: 'Binance USD' }
])
const paypalCurrencies = ref([
  { code: 'USD', icon: '$', name: 'US Dollar' },
  { code: 'EUR', icon: '€', name: 'Euro' },
])
const selectedPlan = ref(null)
const duration = ref('30')
const selectedCurrency = ref('USDT')
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

const stepTitle = computed(() => {
  if (step.value === 1) return t('pay.choosePlan')
  if (step.value === 2) return t('pay.selectPayment')
  return t('pay.invoice')
})

const totalPrice = computed(() => {
  if (!selectedPlan.value) return 0
  const monthly = selectedPlan.value.price_monthly_usd
  const days = parseInt(duration.value)
  let price
  if (days >= 365) price = selectedPlan.value.price_yearly_usd || (monthly * 12)
  else if (days >= 90) price = selectedPlan.value.price_quarterly_usd || (monthly * 3)
  else price = (monthly * days / 30).toFixed(2)
  if (promoDiscount.value > 0) price = (price * (1 - promoDiscount.value / 100)).toFixed(2)
  return price
})

const canProceed = computed(() => {
  if (step.value === 1) return selectedPlan.value && duration.value
  if (step.value === 2) return selectedCurrency.value
  return false
})

const expiryMinutes = computed(() => {
  if (!invoice.value?.expires_at) return 60
  return Math.max(0, Math.floor((new Date(invoice.value.expires_at) - new Date()) / 60000))
})

const invoiceDisplayAmount = computed(() => {
  if (!invoice.value) return ''
  if (invoice.value.amount_crypto) return `${invoice.value.amount_crypto} ${invoice.value.currency}`
  return `$${invoice.value.amount_usd || totalPrice.value}`
})

const getProviderIcon = (id) => {
  const icons = { cryptopay: '💎', paypal: '🅿️', nowpayments: '🔗' }
  return icons[id] || '💰'
}

const getCryptoIcon = (code) => {
  const icons = { BTC: '₿', USDT: '₮', TON: '💎', ETH: 'Ξ', USDC: '$', BUSD: '$' }
  return icons[code] || '💰'
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
    step.value = 3
    startPaymentCheck()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to create invoice'
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
    promoError.value = err.response?.data?.detail || 'Failed to validate promo'
  } finally { promoChecking.value = false }
}

const copyToClipboard = (text) => { if (navigator.clipboard) navigator.clipboard.writeText(text) }

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  try {
    const [plansRes, providersRes] = await Promise.all([
      portalApi.getPlans(),
      portalApi.getProviders()
    ])
    plans.value = plansRes.data.filter(p => p.tier !== 'free')
    providers.value = providersRes.data
    if (providers.value.length === 1) selectedProvider.value = providers.value[0].id
    else if (providers.value.length > 0) selectedProvider.value = providers.value[0].id
  } catch { /* ignore */ }
  if (props.plan) { selectedPlan.value = props.plan; if (props.plan.price_monthly_usd > 0) step.value = 2 }
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
