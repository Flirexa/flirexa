<template>
  <div class="fx-modal-overlay fx-payment-overlay" @click.self="$emit('close')">
    <section class="fx-modal-box fx-payment-dialog" role="dialog" aria-modal="true" :aria-label="stepTitle">
      <header class="fx-modal-header fx-payment-header">
        <div>
          <span class="fx-payment-kicker">{{ isTopup ? $t('payments.accountBalance') : $t('payments.paymentMethod') }}</span>
          <h3>{{ stepTitle }}</h3>
        </div>
        <div class="fx-payment-header-actions">
          <span v-if="!isTopup" class="fx-payment-step">{{ Math.min(step, 3) }} / 3</span>
          <button type="button" class="fx-icon-btn-sm" :aria-label="$t('common.close')" @click="$emit('close')">
            <FxIcon name="close" :size="16" />
          </button>
        </div>
      </header>

      <div class="fx-modal-body fx-payment-body">
        <div v-if="step === 1" class="fx-payment-section">
          <div class="fx-payment-option-list">
            <button
              v-for="plan in plans"
              :key="plan.tier"
              type="button"
              class="fx-plan-option"
              :class="{ selected: selectedPlan?.tier === plan.tier }"
              @click="selectedPlan = plan"
            >
              <span class="fx-plan-main">
                <strong>{{ plan.name }}</strong>
                <small>
                  {{ $t('pay.maxDevices', { n: plan.max_devices }) }} ·
                  {{ plan.traffic_limit_gb ? $t('pay.trafficGb', { gb: plan.traffic_limit_gb }) : $t('pay.unlimitedData') }}
                </small>
              </span>
              <span class="fx-plan-price">${{ plan.price_monthly_usd }}<small>{{ $t('pay.perMonth') }}</small></span>
              <span class="fx-option-check"><FxIcon v-if="selectedPlan?.tier === plan.tier" name="check" :size="12" /></span>
            </button>
          </div>

          <div class="fx-payment-field">
            <label class="fx-label">{{ $t('pay.duration') }}</label>
            <div v-if="customTiers" class="fx-choice-grid">
              <label v-for="tier in customTiers" :key="tier.days" class="fx-choice" :class="{ selected: duration === String(tier.days) }">
                <input v-model="duration" type="radio" name="dur" :value="String(tier.days)" />
                <strong>{{ tier.label || (tier.days + ' ' + $t('pay.daysShort')) }}</strong>
                <small>${{ Number(tier.price_usd || 0).toFixed(2) }}</small>
              </label>
            </div>
            <div v-else class="fx-choice-grid">
              <label class="fx-choice" :class="{ selected: duration === '30' }">
                <input v-model="duration" type="radio" name="dur" value="30" />
                <strong>{{ $t('pay.month1') }}</strong>
              </label>
              <label class="fx-choice" :class="{ selected: duration === '90' }">
                <input v-model="duration" type="radio" name="dur" value="90" />
                <strong>{{ $t('pay.months3') }}</strong><small>{{ $t('pay.save10') }}</small>
              </label>
              <label class="fx-choice" :class="{ selected: duration === '365' }">
                <input v-model="duration" type="radio" name="dur" value="365" />
                <strong>{{ $t('pay.year1') }}</strong><small>{{ $t('pay.save20') }}</small>
              </label>
            </div>
          </div>

          <div v-if="operatorFeatures.promo_codes" class="fx-payment-field">
            <label class="fx-label">{{ $t('pay.promoPlaceholder') }}</label>
            <div class="fx-payment-inline-field">
              <input v-model="promoCode" type="text" class="fx-input" :placeholder="$t('pay.promoPlaceholder')" :disabled="promoApplied" />
              <button type="button" class="fx-btn fx-btn-secondary" :disabled="!promoCode || promoApplied || promoChecking" @click="applyPromo">
                <FxIcon v-if="promoApplied" name="check" :size="14" />
                <span v-else>{{ $t('pay.applyPromo') }}</span>
              </button>
            </div>
            <small v-if="promoApplied" class="fx-field-message success">{{ promoMessage }}</small>
            <small v-if="promoError" class="fx-field-message danger">{{ promoError }}</small>
          </div>

          <div class="fx-payment-total">
            <span>{{ $t('pay.total') }}</span>
            <strong>${{ totalPrice }}</strong>
          </div>
        </div>

        <div v-if="step === 2" class="fx-payment-section">
          <div v-if="isTopup" class="fx-payment-field fx-payment-field-first">
            <label class="fx-label">{{ $t('pay.topupAmount') }}</label>
            <div class="fx-topup-grid">
              <button
                v-for="amount in topupPresets"
                :key="amount"
                type="button"
                class="fx-topup-choice"
                :class="{ selected: Number(topupAmount) === amount }"
                @click="topupAmount = amount"
              >${{ amount }}</button>
            </div>
            <input v-model.number="topupAmount" type="number" min="5" max="1000" step="0.01" class="fx-input" :placeholder="$t('pay.customTopupAmount')" />
            <small class="fx-field-help">{{ $t('pay.topupLimits') }}</small>
          </div>

          <div v-if="providers.length > 1" class="fx-payment-field fx-payment-field-first">
            <label class="fx-label">{{ $t('pay.paymentMethod') }}</label>
            <div class="fx-provider-list">
              <button
                v-for="provider in providers"
                :key="provider.id"
                type="button"
                class="fx-provider-option"
                :class="{ selected: selectedProvider === provider.id }"
                @click="selectedProvider = provider.id"
              >
                <PaymentProviderMark :id="provider.id" :name="provider.display_name || provider.name" />
                <span class="fx-provider-copy">
                  <strong>{{ provider.display_name || provider.name }}</strong>
                  <small>{{ providerTypeLabel(provider) }}</small>
                </span>
                <span class="fx-option-check"><FxIcon v-if="selectedProvider === provider.id" name="check" :size="12" /></span>
              </button>
            </div>
          </div>

          <div class="fx-checkout-summary">
            <PaymentProviderMark :id="selectedProvider" :name="selectedProviderName" />
            <div>
              <strong>{{ selectedProviderName }}</strong>
              <p>{{ selectedProvider === 'balance' ? $t('pay.balanceCheckoutHint', { balance: balanceAvailable }) : $t('pay.cardCheckoutHint') }}</p>
            </div>
          </div>

          <div v-if="selectedProvider === 'balance' && !balanceSufficient" class="fx-inline-notice danger">
            <FxIcon name="warning" :size="17" />
            <span>{{ $t('pay.insufficientBalance', { balance: balanceAvailable, total: Number(totalPrice).toFixed(2) }) }}</span>
          </div>
          <div v-else class="fx-inline-notice info">
            <FxIcon name="external" :size="17" />
            <span>{{ selectedProvider === 'balance' ? $t('pay.balanceInstantHint') : $t('pay.redirectHint') }}</span>
          </div>
        </div>

        <div v-if="step === 3 && invoice" class="fx-payment-section">
          <div class="fx-invoice-amount">
            <span>{{ $t('pay.amount') }}</span>
            <strong>{{ invoiceDisplayAmount }}</strong>
            <button type="button" class="fx-btn fx-btn-secondary fx-btn-sm" @click="copyToClipboard(String(invoice.amount_crypto || invoice.amount_usd))">
              <FxIcon name="copy" :size="13" /> {{ copied ? $t('common.copied') : $t('common.copy') }}
            </button>
          </div>
          <div class="fx-inline-notice warning"><FxIcon name="warning" :size="17" /><span>{{ $t('pay.expiresIn', { min: expiryMinutes }) }}</span></div>
          <p v-if="invoice.amount_crypto" class="fx-invoice-hint">{{ $t('pay.cryptoRateDisclaimer') }}</p>
          <a v-if="invoice.payment_url" :href="invoice.payment_url" target="_blank" rel="noreferrer" class="fx-btn fx-btn-primary fx-btn-block">{{ $t('pay.openPaymentPage') }}</a>
          <button type="button" class="fx-btn fx-btn-secondary fx-btn-block" :disabled="checkingPayment" @click="checkPayment">
            <FxIcon :name="checkingPayment ? 'refresh' : 'checkCircle'" :size="14" :class="{ 'fx-spin': checkingPayment }" />
            {{ $t('pay.checkStatus') }}
          </button>
        </div>

        <div v-if="loading" class="fx-payment-loading">
          <FxIcon name="refresh" :size="20" class="fx-spin" />
          <span>{{ $t('pay.processing') }}</span>
        </div>
        <div v-if="error" class="fx-inline-notice danger fx-payment-error"><FxIcon name="warning" :size="17" /><span>{{ error }}</span></div>
      </div>

      <footer class="fx-modal-footer fx-payment-footer">
        <button type="button" class="fx-btn fx-btn-ghost" @click="goBack">
          {{ step > 1 && step < 3 ? $t('common.back') : $t('common.close') }}
        </button>
        <button v-if="step < 3" type="button" class="fx-btn fx-btn-primary" :disabled="!canProceed || loading" @click="nextStep">
          {{ step === 2 ? $t('pay.continueToPayment') : $t('common.next') }}
          <FxIcon name="chevron" :size="14" />
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import FxIcon from '../components/FxIcon.vue'
import PaymentProviderMark from '../components/PaymentProviderMark.vue'
import { apiErrorMessage, copyText } from '../utils.js'

const emit = defineEmits(['close', 'success'])
const props = defineProps({
  plan: { type: Object, default: null },
  preselectProvider: { type: String, default: '' },
  mode: { type: String, default: 'subscription' },
})

const { t } = useI18n()

const isTopup = computed(() => props.mode === 'topup')
const step = ref(props.mode === 'topup' ? 2 : 1)
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
const balanceSnapshot = ref(null)
const topupAmount = ref(25)
const topupPresets = [10, 25, 50, 100]
const copied = ref(false)

const stepTitle = computed(() => {
  if (isTopup.value) return t('pay.addFunds')
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
  if (isTopup.value) return Number(topupAmount.value || 0).toFixed(2)
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
    const providerReady = selectedCurrency.value
      && providers.value.some(provider => provider.id === selectedProvider.value)
    if (!providerReady) return false
    if (isTopup.value) return Number(topupAmount.value) >= 5 && Number(topupAmount.value) <= 1000
    if (selectedProvider.value === 'balance') return balanceSufficient.value
    return true
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

const balanceAvailableMinor = computed(() => Number(balanceSnapshot.value?.available_minor || 0))
const balanceAvailable = computed(() => (balanceAvailableMinor.value / 100).toFixed(2))
const balanceSufficient = computed(() => balanceAvailableMinor.value >= Math.round(Number(totalPrice.value || 0) * 100))

const providerTypeLabel = provider => {
  if (provider?.id === 'balance' || provider?.type === 'balance') return t('pay.providerBalance')
  if (provider?.type === 'crypto' || ['nowpayments', 'cryptopay'].includes(provider?.id)) return t('pay.providerCrypto')
  return t('pay.providerHosted')
}

const goBack = () => {
  if (isTopup.value) emit('close')
  else if (step.value === 2) step.value = 1
  else emit('close')
}

const nextStep = async () => { step.value === 2 ? await createInvoice() : step.value++ }

const createInvoice = async () => {
  loading.value = true
  error.value = null
  try {
    if (selectedProvider.value === 'balance' && !isTopup.value) {
      const response = await portalApi.purchaseWithBalance({
        plan_tier: selectedPlan.value.tier,
        duration_days: parseInt(duration.value),
        ...(promoApplied.value && promoCode.value ? { promo_code: promoCode.value.trim().toUpperCase() } : {}),
        request_id: (globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`).replace(/-/g, '_'),
      })
      balanceSnapshot.value = response.data?.balance || balanceSnapshot.value
      emit('success')
      emit('close')
      return
    }
    const invoiceData = {
      plan_tier: isTopup.value ? null : selectedPlan.value.tier,
      duration_days: parseInt(duration.value),
      currency: selectedCurrency.value,
      provider: selectedProvider.value,
      purpose: isTopup.value ? 'balance_topup' : 'subscription',
    }
    if (isTopup.value) invoiceData.topup_amount_usd = Number(topupAmount.value)
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
    if (!plans.value.length && !isTopup.value) error.value = t('common.loadError')
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
      if (operatorFeatures.value.account_balance) {
        try {
          const balanceRes = await portalApi.getBalance(20)
          balanceSnapshot.value = balanceRes.data || null
          if (!isTopup.value && Number(balanceSnapshot.value?.available_minor || 0) > 0) {
            // Keep the operator's normal checkout provider as the default.
            // Balance is an optional payment source, not a dead-end first
            // choice for customers whose wallet is still empty.
            providers.value.push({
              id: 'balance',
              name: t('pay.accountBalance'),
              display_name: t('pay.accountBalance'),
              type: 'balance',
            })
          }
        } catch (_) { /* keep external checkout available */ }
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
.fx-payment-overlay { animation:fx-payment-fade .18s ease; }
.fx-payment-dialog { width:min(620px,calc(100vw - 28px));max-width:620px;overflow:hidden;animation:fx-payment-enter .2s ease; }
@keyframes fx-payment-fade { from { opacity:0 } }
@keyframes fx-payment-enter { from { opacity:0;transform:translateY(8px) scale(.985) } }
.fx-payment-header { min-height:72px;padding:16px 20px; }
.fx-payment-header h3 { margin:2px 0 0;font-size:17px;letter-spacing:-.015em; }
.fx-payment-kicker { display:block;color:var(--text-3);font-size:10px;font-weight:650;letter-spacing:.09em;text-transform:uppercase; }
.fx-payment-header-actions { display:flex;align-items:center;gap:8px; }
.fx-payment-step { display:inline-flex;align-items:center;height:27px;padding:0 9px;border:1px solid var(--border);border-radius:var(--r-pill);color:var(--text-3);font:500 10px var(--mono); }
.fx-payment-body { padding:20px; }
.fx-payment-section { display:flex;flex-direction:column;gap:16px; }
.fx-payment-option-list,.fx-provider-list { display:flex;flex-direction:column;gap:8px; }
.fx-plan-option,.fx-provider-option {
  width:100%;min-width:0;border:1px solid var(--border);border-radius:12px;background:var(--bg-elev);color:var(--text);font:inherit;cursor:pointer;text-align:left;
  display:grid;align-items:center;transition:border-color .15s,box-shadow .15s,transform .15s;
}
.fx-plan-option { grid-template-columns:minmax(0,1fr) auto 22px;gap:14px;padding:13px 14px; }
.fx-plan-option:hover,.fx-provider-option:hover { border-color:var(--border-strong);box-shadow:var(--shadow-sm);transform:translateY(-1px); }
.fx-plan-option.selected,.fx-provider-option.selected { border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset; }
.fx-plan-main { display:flex;flex-direction:column;gap:4px;min-width:0; }
.fx-plan-main strong { font-size:13.5px;font-weight:650; }
.fx-plan-main small { color:var(--text-3);font-size:11px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.fx-plan-price { color:var(--text);font:650 16px var(--font);white-space:nowrap; }
.fx-plan-price small { margin-left:2px;color:var(--text-3);font-size:10.5px;font-weight:500; }
.fx-option-check { width:20px;height:20px;border:1px solid var(--border-strong);border-radius:50%;display:grid;place-items:center;color:var(--accent); }
.selected > .fx-option-check { border-color:var(--accent);background:var(--accent);color:var(--accent-fg); }
.fx-payment-field { display:flex;flex-direction:column;gap:8px;padding-top:2px; }
.fx-payment-field-first { padding-top:0; }
.fx-choice-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px; }
.fx-choice { position:relative;min-width:0;min-height:58px;padding:10px;border:1px solid var(--border);border-radius:10px;background:var(--bg-elev);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;cursor:pointer;text-align:center;transition:border-color .15s,box-shadow .15s; }
.fx-choice input { position:absolute;opacity:0;pointer-events:none; }
.fx-choice strong { max-width:100%;font-size:12px;font-weight:600;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.fx-choice small { color:var(--text-3);font-size:10px; }
.fx-choice.selected { border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset; }
.fx-payment-inline-field { display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px; }
.fx-field-message,.fx-field-help { display:block;font-size:10.5px;line-height:1.4; }
.fx-field-help { color:var(--text-3); }
.fx-field-message.success { color:var(--success); }.fx-field-message.danger { color:var(--danger); }
.fx-payment-total { min-height:58px;padding:12px 14px;border:1px solid var(--border);border-radius:12px;background:var(--bg-subtle);display:flex;align-items:center;justify-content:space-between;gap:16px;color:var(--text-2);font-size:12px; }
.fx-payment-total strong { color:var(--text);font-size:22px;font-weight:650;letter-spacing:-.025em;font-variant-numeric:tabular-nums; }
.fx-topup-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px; }
.fx-topup-choice { height:42px;border:1px solid var(--border);border-radius:10px;background:var(--bg-elev);color:var(--text);font:600 12px var(--font);cursor:pointer; }
.fx-topup-choice:hover { border-color:var(--border-strong); }.fx-topup-choice.selected { border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset;color:var(--accent); }
.fx-provider-option { grid-template-columns:38px minmax(0,1fr) 20px;gap:12px;padding:10px 12px; }
.fx-provider-copy { min-width:0;display:flex;flex-direction:column;gap:2px; }
.fx-provider-copy strong { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:600; }
.fx-provider-copy small { color:var(--text-3);font-size:10.5px; }
.fx-checkout-summary { display:grid;grid-template-columns:38px minmax(0,1fr);gap:12px;align-items:center;padding:14px;border:1px solid var(--border);border-radius:12px;background:var(--bg-subtle); }
.fx-checkout-summary strong { display:block;color:var(--text);font-size:13px;font-weight:600; }
.fx-checkout-summary p { margin:3px 0 0;color:var(--text-3);font-size:11px;line-height:1.45; }
.fx-inline-notice { display:flex;align-items:flex-start;gap:10px;padding:11px 12px;border:1px solid var(--border);border-left-width:3px;border-radius:10px;background:var(--bg-elev);color:var(--text-2);font-size:11.5px;line-height:1.45; }
.fx-inline-notice svg { flex-shrink:0;margin-top:1px; }.fx-inline-notice.info { border-left-color:var(--accent); }.fx-inline-notice.info svg { color:var(--accent); }.fx-inline-notice.warning { border-left-color:var(--warning); }.fx-inline-notice.warning svg { color:var(--warning); }.fx-inline-notice.danger { border-left-color:var(--danger); }.fx-inline-notice.danger svg { color:var(--danger); }
.fx-invoice-amount { display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:4px 12px;padding:16px;border:1px solid var(--border);border-radius:12px;background:var(--bg-subtle); }
.fx-invoice-amount > span { grid-column:1;color:var(--text-3);font-size:10px;font-weight:650;text-transform:uppercase;letter-spacing:.08em; }.fx-invoice-amount strong { grid-column:1;color:var(--text);font:650 22px var(--mono);overflow-wrap:anywhere; }.fx-invoice-amount .fx-btn { grid-column:2;grid-row:1/3; }
.fx-invoice-hint { margin:0;color:var(--text-3);font-size:11px;line-height:1.45; }
.fx-payment-loading { display:flex;align-items:center;justify-content:center;gap:9px;padding:16px;color:var(--text-2);font-size:12px; }
.fx-payment-error { margin-top:14px; }
.fx-payment-footer { justify-content:space-between;padding:13px 20px; }

@media (max-width:640px) {
  .fx-payment-overlay { align-items:flex-end;padding:0; }
  .fx-payment-dialog { width:100%;max-width:none;max-height:min(92vh,820px);border-radius:18px 18px 0 0;animation:fx-payment-sheet .22s ease; }
  @keyframes fx-payment-sheet { from { opacity:.7;transform:translateY(40px) } }
  .fx-payment-header { position:relative;min-height:68px;padding:18px 16px 12px; }
  .fx-payment-header::before { content:"";position:absolute;top:7px;left:50%;width:34px;height:3px;transform:translateX(-50%);border-radius:2px;background:var(--border-strong); }
  .fx-payment-body { padding:16px; }
  .fx-payment-footer { position:sticky;bottom:0;padding:11px 16px calc(11px + env(safe-area-inset-bottom,0px));background:var(--bg-elev); }
  .fx-plan-option { grid-template-columns:minmax(0,1fr) auto 20px;gap:10px;padding:12px; }
  .fx-plan-main small { white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical; }
  .fx-topup-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:390px) {
  .fx-choice-grid { grid-template-columns:1fr; }
  .fx-choice { min-height:46px;flex-direction:row;justify-content:space-between;padding:9px 11px;text-align:left; }
  .fx-plan-option { grid-template-columns:minmax(0,1fr) 20px; }
  .fx-plan-price { grid-column:1;font-size:14px; }.fx-plan-option > .fx-option-check { grid-column:2;grid-row:1/3; }
  .fx-payment-inline-field { grid-template-columns:1fr; }.fx-payment-inline-field .fx-btn { width:100%; }
  .fx-payment-footer .fx-btn { min-width:0;padding:0 11px; }
}
</style>
