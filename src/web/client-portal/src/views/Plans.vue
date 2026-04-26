<template>
  <div class="plans-page">
    <div class="text-center mb-4">
      <h3 class="fw-bold">{{ $t('plans.title') }}</h3>
      <p class="text-muted">{{ $t('plans.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary mb-3"></div>
      <div class="text-muted small">{{ $t('common.loading') }}</div>
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-center py-5">
      <div class="mb-3" style="font-size:2.5rem">⚠️</div>
      <p class="text-muted">{{ $t('common.loadError') }}</p>
      <button class="btn btn-outline-primary btn-sm" @click="loadPlans">{{ $t('common.retry') }}</button>
    </div>

    <!-- Plans grid -->
    <div v-else class="row g-3 g-md-4 justify-content-center plans-row">
      <div class="col-12 col-sm-6 col-lg-3" v-for="plan in plans" :key="plan.tier">
        <div class="plan-card" :class="{ 'plan-popular': plan.tier.toLowerCase() === 'standard', 'plan-current': currentTier.toLowerCase() === plan.tier.toLowerCase() }">
          <div class="plan-badge" v-if="plan.tier.toLowerCase() === 'standard' && currentTier.toLowerCase() !== plan.tier.toLowerCase()">{{ $t('plans.popular') }}</div>
          <div class="plan-badge plan-badge-current" v-if="currentTier.toLowerCase() === plan.tier.toLowerCase()">{{ $t('plans.current') }}</div>

          <div class="plan-header">
            <h5 class="plan-name">{{ plan.name }}</h5>
            <p class="plan-description">{{ plan.description }}</p>
          </div>

          <div class="plan-price">
            <span class="price-amount">${{ plan.price_monthly_usd }}</span>
            <span class="price-period">{{ $t('pay.perMonth') }}</span>
          </div>

          <ul class="plan-features">
            <li>{{ plan.max_devices }} {{ $t('pay.dev') }}</li>
            <li>{{ plan.traffic_limit_gb ? $t('plans.gbTraffic', { amount: plan.traffic_limit_gb }) : $t('plans.unlimitedTraffic') }}</li>
            <li>{{ plan.bandwidth_limit_mbps ? plan.bandwidth_limit_mbps + ' Mbps' : $t('plans.maxSpeed') }}</li>
            <li v-if="plan.price_quarterly_usd">{{ $t('plans.quarterly', { amount: plan.price_quarterly_usd }) }}</li>
            <li v-if="plan.price_yearly_usd">{{ $t('plans.yearly', { amount: plan.price_yearly_usd }) }}</li>
          </ul>

          <button v-if="plan.tier.toLowerCase() !== 'free'" class="btn w-100"
            :class="currentTier.toLowerCase() === plan.tier.toLowerCase() ? 'btn-outline-primary' : 'btn-primary'"
            :disabled="currentTier.toLowerCase() === plan.tier.toLowerCase()" @click="selectPlan(plan)">
            {{ currentTier.toLowerCase() === plan.tier.toLowerCase() ? $t('plans.currentPlan') : (plan.price_monthly_usd === 0 ? $t('plans.freePlan') : $t('plans.subscribe')) }}
          </button>
          <button v-else class="btn btn-outline-secondary w-100" disabled>
            {{ currentTier.toLowerCase() === 'free' ? $t('plans.currentPlan') : $t('plans.freeTier') }}
          </button>
        </div>
      </div>
    </div>

    <PaymentModal v-if="showPayment" :plan="selectedPlan" @close="showPayment = false" @success="onPaymentSuccess" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { portalApi } from '../api/index.js'
import PaymentModal from './PaymentModal.vue'

const plans = ref([])
const currentTier = ref('free')
const selectedPlan = ref(null)
const showPayment = ref(false)
const loading = ref(false)
const loadError = ref(false)

const loadPlans = async () => {
  loading.value = true
  loadError.value = false
  try {
    const [plansRes, subRes] = await Promise.all([
      portalApi.getPlans(),
      portalApi.getSubscription()
    ])
    plans.value = plansRes.data
    currentTier.value = subRes.data?.tier || 'free'
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

const selectPlan = (plan) => { selectedPlan.value = plan; showPayment.value = true }
const onPaymentSuccess = () => { showPayment.value = false; loadPlans() }

onMounted(() => { loadPlans() })
</script>

<style scoped>
.plans-row { padding-top: 16px; }

.plan-card {
  background: var(--vxy-card-bg);
  border: 2px solid var(--vxy-border);
  border-radius: var(--vxy-card-radius);
  box-shadow: var(--vxy-card-shadow);
  padding: 2rem 1.5rem; text-align: center;
  position: relative; transition: all .3s ease;
  height: 100%; display: flex; flex-direction: column;
}
.plan-card:hover { transform: translateY(-4px); box-shadow: 0 8px 30px rgba(34,41,47,.15); }
.plan-popular { border-color: var(--vxy-primary); box-shadow: 0 4px 20px rgba(115,103,240,.25); }
.plan-current { border-color: var(--vxy-success); }

.plan-badge {
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  background: var(--vxy-primary); color: #fff;
  padding: .25rem 1rem; border-radius: 20px;
  font-size: .75rem; font-weight: 700; text-transform: uppercase; white-space: nowrap;
}
.plan-badge-current { background: var(--vxy-success); }

.plan-header { margin-bottom: 1rem; }
.plan-name { font-weight: 700; margin-bottom: .25rem; color: var(--vxy-heading); }
.plan-description { font-size: .85rem; color: var(--vxy-muted); margin-bottom: 0; }
.plan-price { margin-bottom: 1.5rem; }
.price-amount { font-size: 2.5rem; font-weight: 800; color: var(--vxy-heading); }
.price-period { font-size: .9rem; color: var(--vxy-muted); }
.plan-features { list-style: none; padding: 0; margin-bottom: 1.5rem; flex-grow: 1; }
.plan-features li { padding: .4rem 0; font-size: .9rem; color: var(--vxy-text); border-bottom: 1px solid var(--vxy-border); }
.plan-features li:last-child { border-bottom: none; }
.btn-primary { background: var(--vxy-primary); border-color: var(--vxy-primary); border-radius: .375rem; padding: .65rem; font-weight: 600; }
.btn-primary:hover { background: var(--vxy-primary-dark); border-color: var(--vxy-primary-dark); box-shadow: 0 4px 12px rgba(115,103,240,.5); }

@media (max-width: 576px) {
  .plan-card { padding: 1.5rem 1rem; }
  .price-amount { font-size: 2rem; }
  .plan-features li { font-size: .85rem; padding: .3rem 0; }
}
</style>
