<template>
  <div class="client-payments">
    <h4 class="fw-bold mb-4">{{ $t('payments.title') }}</h4>

    <!-- Loading spinner -->
    <div class="text-center py-5" v-if="loading">
      <div class="spinner-border text-primary" role="status"></div>
      <div class="mt-2 text-muted small">{{ $t('common.loading') }}</div>
    </div>

    <div class="card" v-else-if="payments.length === 0">
      <div class="card-body text-center py-5">
        <div style="font-size: 3rem; margin-bottom: 1rem;">💳</div>
        <h5>{{ $t('payments.noPayments') }}</h5>
        <p class="text-muted">{{ $t('payments.noPaymentsHint') }}</p>
        <router-link to="/plans" class="btn btn-primary">{{ $t('payments.viewPlans') }}</router-link>
      </div>
    </div>

    <div class="card" v-else>
      <!-- Desktop table -->
      <div class="table-responsive d-none d-md-block">
        <table class="table table-hover mb-0">
          <thead>
            <tr>
              <th>{{ $t('payments.date') }}</th>
              <th>{{ $t('payments.plan') }}</th>
              <th>{{ $t('payments.amount') }}</th>
              <th>{{ $t('payments.method') }}</th>
              <th>{{ $t('payments.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="payment in payments" :key="payment.id">
              <td>{{ formatDate(payment.created_at) }}</td>
              <td>
                <span class="badge bg-info">{{ payment.subscription_tier || '-' }}</span>
                <small class="text-muted ms-1" v-if="payment.duration_days">{{ payment.duration_days }}d</small>
              </td>
              <td>
                <strong>${{ payment.amount_usd?.toFixed(2) || '0.00' }}</strong>
                <small class="text-muted d-block" v-if="payment.crypto_amount">{{ payment.crypto_amount }} {{ payment.payment_method }}</small>
              </td>
              <td>{{ payment.payment_method || '-' }}</td>
              <td><span class="badge" :class="statusClass(payment.status)">{{ payment.status }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Mobile cards -->
      <div class="d-md-none p-3">
        <div class="payment-card-mobile" v-for="payment in payments" :key="'m-' + payment.id">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
              <span class="badge bg-info me-1">{{ payment.subscription_tier || '-' }}</span>
              <small class="text-muted" v-if="payment.duration_days">{{ payment.duration_days }}d</small>
            </div>
            <span class="badge" :class="statusClass(payment.status)">{{ payment.status }}</span>
          </div>
          <div class="d-flex justify-content-between align-items-end">
            <div>
              <div class="fw-bold fs-5">${{ payment.amount_usd?.toFixed(2) || '0.00' }}</div>
              <small class="text-muted">{{ payment.payment_method || '-' }}</small>
            </div>
            <small class="text-muted">{{ formatDate(payment.created_at) }}</small>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'

const { locale } = useI18n()
const payments = ref([])
const loading = ref(true)

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString(locale.value, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

const statusClass = (status) => {
  switch (status) {
    case 'completed': return 'bg-success'
    case 'pending': return 'bg-warning'
    case 'failed': return 'bg-danger'
    case 'expired': return 'bg-secondary'
    default: return 'bg-secondary'
  }
}

onMounted(async () => {
  try {
    const res = await portalApi.getPaymentHistory(50)
    payments.value = res.data
  } catch (err) { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.payment-card-mobile {
  background: var(--vxy-card-bg);
  border: 1px solid var(--vxy-border);
  border-radius: var(--vxy-card-radius);
  padding: .875rem;
  margin-bottom: .625rem;
}
</style>
