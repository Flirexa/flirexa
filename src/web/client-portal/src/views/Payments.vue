<template>
  <div class="fx-page">
    <div class="fx-page-head">
      <div>
        <h1 class="fx-page-title">{{ $t('payments.title') }}</h1>
        <p class="fx-page-sub">{{ $t('payments.subtitle') }}</p>
      </div>
      <div style="display:flex; gap:8px">
        <router-link to="/plans" class="fx-btn fx-btn-primary">
          <FxIcon name="plus" :size="14" /> {{ $t('payments.subscribePlan') }}
        </router-link>
      </div>
    </div>

    <div v-if="loadError" class="fx-card" style="padding:14px var(--pad-card); margin-bottom:var(--gap); display:flex; align-items:center; justify-content:space-between; gap:12px">
      <span style="color:var(--danger); font-size:12px">{{ loadError }}</span>
      <button class="fx-btn fx-btn-secondary fx-btn-sm" @click="loadData">{{ $t('common.retry') }}</button>
    </div>

    <!-- Stat row -->
    <div class="fx-stat-row fx-stat-row-3">
      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('payments.totalPaid') }}</span>
          <span class="fx-stat-icon"><FxIcon name="card" :size="14" /></span>
        </div>
        <div class="fx-stat-value">${{ totalPaid.toFixed(2) }}</div>
        <div class="fx-stat-foot">
          <span>{{ $t('payments.acrossN', { count: paidCount }) }}</span>
        </div>
      </div>
      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('payments.nextCharge') }}</span>
          <span class="fx-stat-icon"><FxIcon name="calendar" :size="14" /></span>
        </div>
        <div class="fx-stat-value">{{ nextChargeAmount }}</div>
        <div class="fx-stat-foot"><span>{{ nextChargeMeta }}</span></div>
      </div>
      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('payments.lastPayment') }}</span>
          <span class="fx-stat-icon"><FxIcon name="star" :size="14" /></span>
        </div>
        <div class="fx-stat-value">{{ lastPaymentAmount }}</div>
        <div class="fx-stat-foot">
          <span>{{ lastPaymentDate }}</span>
        </div>
      </div>
    </div>

    <!-- Loading / empty -->
    <div v-if="loading" class="fx-empty">
      <div class="fx-empty-icon"><FxIcon name="refresh" :size="22" /></div>
      <p class="fx-empty-sub">{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="!payments.length" class="fx-card fx-empty">
      <div class="fx-empty-icon"><FxIcon name="card" :size="22" /></div>
      <h3 class="fx-empty-title">{{ $t('payments.noPayments') }}</h3>
      <p class="fx-empty-sub">{{ $t('payments.noPaymentsHint') }}</p>
      <router-link to="/plans" class="fx-btn fx-btn-primary">{{ $t('payments.viewPlans') }}</router-link>
    </div>

    <div v-else class="fx-payments-grid">
      <!-- History table -->
      <div class="fx-card" style="overflow:hidden">
        <div style="padding:var(--pad-card); display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap">
          <h3 class="fx-section-title">{{ $t('payments.history') }}</h3>
          <div class="fx-chart-tabs">
            <button v-for="(label, key) in filterLabels" :key="key"
                    :class="['fx-chart-tab', { active: filter === key }]"
                    @click="filter = key">{{ label }}</button>
          </div>
        </div>
        <table class="fx-pay-table">
          <thead>
            <tr>
              <th>{{ $t('payments.invoice') }}</th>
              <th>{{ $t('payments.date') }}</th>
              <th>{{ $t('payments.plan') }}</th>
              <th>{{ $t('payments.method') }}</th>
              <th style="text-align:right">{{ $t('payments.amount') }}</th>
              <th>{{ $t('payments.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filteredPayments" :key="p.invoice_id || p.id">
              <td>
                <span style="font-family:var(--mono); font-size:12px">{{ invoiceId(p) }}</span>
              </td>
              <td style="color:var(--text-2)">{{ formatDate(p.created_at) }}</td>
              <td>
                <span class="fx-badge fx-badge-accent">{{ p.subscription_tier || '—' }}</span>
                <small v-if="p.duration_days" style="color:var(--text-3); margin-left:6px">{{ p.duration_days }}d</small>
              </td>
              <td>
                <span class="fx-pay-method">
                  <span class="fx-pay-method-icon" :class="{ crypto: isCrypto(p.payment_method) }">{{ payMethodLabel(p.payment_method) }}</span>
                  <span style="color:var(--text-2)">{{ p.payment_method || '—' }}</span>
                </span>
              </td>
              <td class="fx-pay-amount" style="text-align:right">
                ${{ Number(p.amount_usd || 0).toFixed(2) }}
                <small v-if="p.crypto_amount" style="color:var(--text-3); display:block">{{ p.crypto_amount }} {{ p.payment_method }}</small>
              </td>
              <td><span class="fx-badge" :class="statusBadge(p.status)">{{ p.status }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Right rail: real provider list + billing details -->
      <div class="fx-dash-col">
        <div class="fx-card" style="padding:var(--pad-card)">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap">
            <h3 class="fx-section-title">{{ $t('payments.paymentMethod') }}</h3>
            <span v-if="!providersLoading && providers.length" class="fx-badge fx-badge-neutral">
              {{ providers.length }}
            </span>
          </div>

          <div v-if="providersLoading" style="padding:24px 0; text-align:center; color:var(--text-3); font-size:12px">
            {{ $t('common.loading') }}
          </div>

          <div v-else-if="!providers.length" class="fx-empty" style="padding:32px 0">
            <div class="fx-empty-icon"><FxIcon name="card" :size="20" /></div>
            <p class="fx-empty-sub">{{ $t('payments.noProvidersConfigured') }}</p>
          </div>

          <div v-else class="fx-method-list">
            <div v-for="p in providers" :key="p.id" class="fx-method-row" @click="payWith(p)">
              <span class="fx-method-icon" :class="providerIconClass(p)">
                {{ providerInitials(p) }}
              </span>
              <div class="fx-method-text">
                <div class="fx-method-name">
                  {{ p.display_name || p.name }}
                  <span v-if="defaultProviderId === p.id" class="fx-badge fx-badge-success">{{ $t('payments.default') }}</span>
                </div>
                <div class="fx-method-meta">
                  {{ providerKindLabel(p) }}
                </div>
              </div>
              <FxIcon name="chevron" :size="14" style="color:var(--text-3)" />
            </div>
          </div>

        </div>

        <div class="fx-card" style="padding:var(--pad-card)">
          <h3 class="fx-section-title">{{ $t('payments.billingDetails') }}</h3>
          <div class="fx-sub-rows" style="margin-top:10px">
            <div class="fx-sub-row">
              <span class="k">{{ $t('payments.email') }}</span>
              <span class="v">{{ userEmail }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add method chooser → opens existing PaymentModal preselected to the chosen provider. -->
    <PaymentModal
      v-if="payModalOpen"
      :preselect-provider="payModalProvider"
      @close="payModalOpen = false"
      @success="onPaymentSuccess"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { portalSession } from '../session'
import FxIcon from '../components/FxIcon.vue'
import PaymentModal from './PaymentModal.vue'
import { apiErrorMessage } from '../utils.js'

const { t, locale } = useI18n()

const payments = ref([])
const subscription = ref({})
const loading = ref(true)
const loadError = ref('')
const filter = ref('all')

const providers = ref([])
const providersLoading = ref(true)
const payModalOpen = ref(false)
const payModalProvider = ref('')

const filterLabels = computed(() => ({
  all: t('payments.filterAll'),
  paid: t('payments.filterPaid'),
  pending: t('payments.filterPending'),
  failed: t('payments.filterFailed'),
}))

const filteredPayments = computed(() => {
  if (filter.value === 'all') return payments.value
  if (filter.value === 'paid') return payments.value.filter(p => p.status === 'completed')
  return payments.value.filter(p => p.status === filter.value)
})

const totalPaid = computed(() =>
  payments.value
    .filter(p => p.status === 'completed')
    .reduce((s, p) => s + Number(p.amount_usd || 0), 0))

const paidCount = computed(() => payments.value.filter(p => p.status === 'completed').length)

const lastPayment = computed(() => payments.value.find(p => p.status === 'completed') || null)
const lastPaymentAmount = computed(() => lastPayment.value ? '$' + Number(lastPayment.value.amount_usd || 0).toFixed(2) : '—')
const lastPaymentDate = computed(() => lastPayment.value ? formatDate(lastPayment.value.created_at) : t('payments.noPayments'))

// No automatic debit is scheduled while settlement-backed renewal is
// disabled. Never infer a future charge from the stored monthly price.
const nextChargeAmount = computed(() => '—')
const nextChargeMeta = computed(() => t('payments.noChargeScheduled'))

const userEmail = computed(() => {
  return portalSession.user?.email || '—'
})

// "Default" = the provider used for the most recent successful payment.
const defaultProviderId = computed(() => {
  const lp = lastPayment.value
  if (!lp || !lp.payment_method) return ''
  const m = lp.payment_method.toLowerCase()
  // payment_method on payments is the currency or provider name — best-effort match.
  return providers.value.find(p => m.includes(p.id))?.id || ''
})

const providerInitials = (p) => {
  const name = (p.display_name || p.name || p.id || '?').replace(/\(.+\)/, '').trim()
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return parts[0].slice(0, 2).toUpperCase()
}
const providerKindLabel = (p) => {
  if (p.type === 'crypto') return 'Crypto'
  if (p.type === 'fiat') return 'Card / Bank'
  if (p.type === 'plugin') return 'Plugin'
  return p.type || ''
}
const providerIconClass = (p) => {
  if (p.id === 'nowpayments' || p.type === 'crypto') return 'crypto'
  if (p.id === 'paypal') return 'paypal'
  if (p.id === 'stripe') return 'stripe'
  return 'fiat'
}

const payWith = (p) => { payModalProvider.value = p.id; payModalOpen.value = true }
const onPaymentSuccess = () => {
  payModalOpen.value = false
  // Refresh history so the new payment appears immediately.
  loading.value = true
  portalApi.getPaymentHistory(50).then(r => { payments.value = r.data || [] })
                              .finally(() => { loading.value = false })
}

const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString(locale.value, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

const isCrypto = (m) => m && /btc|eth|usdt|trx|crypto/i.test(m)
const payMethodLabel = (m) => {
  if (!m) return 'N/A'
  if (/paypal/i.test(m)) return 'PP'
  if (/visa/i.test(m)) return 'VISA'
  if (isCrypto(m)) return 'CR'
  return m.slice(0, 4).toUpperCase()
}
const statusBadge = (s) => {
  if (s === 'completed') return 'fx-badge-success'
  if (s === 'pending') return 'fx-badge-warning'
  if (s === 'failed') return 'fx-badge-danger'
  if (s === 'expired') return 'fx-badge-neutral'
  return 'fx-badge-neutral'
}
const invoiceId = (p) => p.invoice_id || `INV-${String(p.id).padStart(6, '0')}`

const loadData = async () => {
  loading.value = true
  providersLoading.value = true
  loadError.value = ''
  const results = await Promise.allSettled([
    portalApi.getPaymentHistory(50),
    portalApi.getSubscription(),
    portalApi.getProviders(),
  ])
  const [paymentsRes, subRes, provRes] = results
  if (paymentsRes.status === 'fulfilled') payments.value = paymentsRes.value.data || []
  if (subRes.status === 'fulfilled') subscription.value = subRes.value.data || {}
  if (provRes.status === 'fulfilled') {
    const rows = Array.isArray(provRes.value.data) ? provRes.value.data : []
    providers.value = rows.filter(provider => provider.configured !== false)
  }
  const firstError = results.find(result => result.status === 'rejected')
  if (firstError) loadError.value = apiErrorMessage(firstError.reason, t('common.loadError'))
  loading.value = false
  providersLoading.value = false
}

onMounted(loadData)
</script>

<style scoped>
.fx-method-list {
  display: flex; flex-direction: column;
  margin-top: 12px;
  gap: 4px;
}
.fx-method-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  background: var(--bg-elev);
  cursor: pointer;
  transition: border-color .12s, background .12s, transform .12s;
}
.fx-method-row:hover {
  border-color: var(--accent);
  background: var(--bg-hover);
  transform: translateY(-1px);
}
.fx-method-icon {
  width: 36px; height: 36px;
  border-radius: var(--r-sm);
  display: grid; place-items: center;
  font-size: 11px; font-weight: 700; letter-spacing: .04em;
  color: white;
  background: linear-gradient(135deg, #1a1f71, #5b6cff);
}
.fx-method-icon.crypto { background: linear-gradient(135deg, #f7931a, #ffb84d); }
.fx-method-icon.paypal { background: linear-gradient(135deg, #003087, #009cde); }
.fx-method-icon.stripe { background: linear-gradient(135deg, #635bff, #9d8df1); }
.fx-method-text { min-width: 0; }
.fx-method-name {
  font-size: 13px; font-weight: 500;
  color: var(--text);
  display: flex; align-items: center; gap: 8px;
}
.fx-method-name .fx-badge { height: 18px; font-size: 10px; }
.fx-method-meta { font-size: 11px; color: var(--text-3); margin-top: 2px; }
</style>
