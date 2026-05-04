<template>
  <div class="fx-page">
    <div style="text-align:center; margin-bottom:28px">
      <h1 class="fx-page-title" style="font-size:32px">{{ $t('plans.title') }}</h1>
      <p class="fx-page-sub" style="font-size:15px">{{ $t('plans.subtitle') }}</p>
      <div style="display:flex; justify-content:center; margin-top:22px">
        <div class="fx-billing-toggle">
          <button v-for="(label, key) in periodLabels" :key="key"
                  :class="{ active: billing === key }"
                  @click="billing = key">
            {{ label }}<span v-if="key === 'yearly'" class="save">−{{ yearlyDiscountPct }}%</span>
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="fx-empty">
      <div class="fx-empty-icon"><FxIcon name="refresh" :size="22" /></div>
      <p class="fx-empty-sub">{{ $t('common.loading') }}</p>
    </div>

    <div v-else-if="loadError" class="fx-empty">
      <div class="fx-empty-icon"><FxIcon name="warning" :size="22" /></div>
      <h3 class="fx-empty-title">{{ $t('common.loadError') }}</h3>
      <button class="fx-btn fx-btn-secondary fx-btn-sm" @click="loadPlans">{{ $t('common.retry') }}</button>
    </div>

    <div v-else class="fx-tariffs-grid">
      <div
        v-for="plan in plans"
        :key="plan.tier"
        class="fx-tariff"
        :class="{
          popular: plan.tier.toLowerCase() === 'standard' && currentTier.toLowerCase() !== plan.tier.toLowerCase(),
          current: currentTier.toLowerCase() === plan.tier.toLowerCase(),
        }"
      >
        <div v-if="plan.tier.toLowerCase() === 'standard' && currentTier.toLowerCase() !== plan.tier.toLowerCase()"
             class="fx-tariff-ribbon">{{ $t('plans.popular') }}</div>
        <div v-if="currentTier.toLowerCase() === plan.tier.toLowerCase()"
             class="fx-tariff-ribbon">{{ $t('plans.current') }}</div>

        <h3 class="fx-tariff-name">{{ plan.name }}</h3>
        <p class="fx-tariff-tagline">{{ plan.description || planTagline(plan) }}</p>

        <div class="fx-tariff-price">
          <span class="num">${{ priceFor(plan) }}</span>
          <span class="per">{{ priceLabel }}</span>
        </div>

        <ul class="fx-tariff-features">
          <li><FxIcon name="check" :size="15" /> {{ $t('plans.featureDevices', { count: plan.max_devices }) }}</li>
          <li><FxIcon name="check" :size="15" /> {{ plan.traffic_limit_gb ? $t('plans.gbTraffic', { amount: plan.traffic_limit_gb }) : $t('plans.unlimitedTraffic') }}</li>
          <li><FxIcon name="check" :size="15" /> {{ plan.bandwidth_limit_mbps ? plan.bandwidth_limit_mbps + ' Mbps' : $t('plans.maxSpeed') }}</li>
          <li v-if="plan.tier.toLowerCase() === 'free'"><FxIcon name="check" :size="15" /> {{ $t('plans.featureBasicSupport') }}</li>
          <li v-else-if="plan.tier.toLowerCase() === 'premium' || plan.tier.toLowerCase() === 'corporate'">
            <FxIcon name="check" :size="15" /> {{ $t('plans.featurePrioritySupport') }}
          </li>
          <li v-else><FxIcon name="check" :size="15" /> {{ $t('plans.featureEmailSupport') }}</li>
        </ul>

        <button v-if="currentTier.toLowerCase() === plan.tier.toLowerCase()"
                class="fx-btn fx-btn-secondary fx-btn-block fx-btn-lg" disabled>
          {{ $t('plans.currentPlan') }}
        </button>
        <button v-else-if="plan.tier.toLowerCase() === 'free'"
                class="fx-btn fx-btn-secondary fx-btn-block fx-btn-lg" disabled>
          {{ $t('plans.freeTier') }}
        </button>
        <button v-else
                class="fx-btn fx-btn-block fx-btn-lg"
                :class="plan.tier.toLowerCase() === 'standard' ? 'fx-btn-primary' : 'fx-btn-secondary'"
                @click="selectPlan(plan)">
          {{ plan.price_monthly_usd === 0 ? $t('plans.freePlan') : $t('plans.subscribe') }}
        </button>
      </div>
    </div>

    <div style="text-align:center; margin-top:40px; font-size:13px; color:var(--text-3)">
      {{ $t('plans.contactSalesHint') }}
      <a href="#" @click.prevent="openContact" style="color:var(--accent)">{{ $t('plans.contactSales') }} →</a>
    </div>

    <PaymentModal v-if="showPayment" :plan="selectedPlan" @close="showPayment = false" @success="onPaymentSuccess" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { portalApi } from '../api/index.js'
import PaymentModal from './PaymentModal.vue'
import FxIcon from '../components/FxIcon.vue'

const { t } = useI18n()
const router = useRouter()

const plans = ref([])
const currentTier = ref('free')
const selectedPlan = ref(null)
const showPayment = ref(false)
const loading = ref(false)
const loadError = ref(false)
const billing = ref('monthly')

const periodLabels = computed(() => ({
  monthly: t('plans.billingMonthly'),
  quarterly: t('plans.billingQuarterly'),
  yearly: t('plans.billingYearly'),
}))
const priceLabel = computed(() => billing.value === 'monthly'
  ? t('plans.perMo')
  : billing.value === 'quarterly' ? t('plans.perQuarter') : t('plans.perYear'))

const yearlyDiscountPct = computed(() => {
  // Pick the first paid plan to compute the discount
  const p = plans.value.find(x => x.price_monthly_usd > 0)
  if (!p || !p.price_yearly_usd) return 20
  const naive = p.price_monthly_usd * 12
  if (!naive) return 20
  const pct = Math.max(0, Math.round((naive - p.price_yearly_usd) / naive * 100))
  return pct || 20
})

function priceFor(plan) {
  if (billing.value === 'monthly') return Number(plan.price_monthly_usd || 0).toFixed(0)
  if (billing.value === 'quarterly') return Number(plan.price_quarterly_usd ?? plan.price_monthly_usd * 3).toFixed(0)
  return Number(plan.price_yearly_usd ?? plan.price_monthly_usd * 12).toFixed(0)
}

function planTagline(plan) {
  const tier = (plan.tier || '').toLowerCase()
  if (tier === 'free') return t('plans.taglineFree')
  if (tier === 'standard') return t('plans.taglineStandard')
  if (tier === 'premium') return t('plans.taglinePremium')
  if (tier === 'corporate') return t('plans.taglineCorporate')
  return ''
}

const loadPlans = async () => {
  loading.value = true
  loadError.value = false
  try {
    const [plansRes, subRes] = await Promise.all([
      portalApi.getPlans(),
      portalApi.getSubscription(),
    ])
    plans.value = plansRes.data
    currentTier.value = subRes.data?.tier || 'free'
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

const selectPlan = (plan) => {
  selectedPlan.value = { ...plan, billing_period: billing.value }
  showPayment.value = true
}
const onPaymentSuccess = () => { showPayment.value = false; loadPlans() }
const openContact = () => router.push('/support')

onMounted(loadPlans)
</script>
