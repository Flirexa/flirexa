<template>
  <div class="payments-page">
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-4 mobile-toolbar">
      <h6 class="mb-0">{{ $t('payments.title') }}</h6>
      <div class="d-flex gap-2 flex-wrap mobile-filter-bar">
        <input
          v-model="searchQuery"
          type="text"
          class="form-control form-control-sm"
          style="min-width: 180px"
          placeholder="Invoice ID or email..."
          @input="loadPayments"
        />
        <select v-model="statusFilter" class="form-select form-select-sm" style="width: auto; min-width: 120px;" @change="loadPayments">
          <option value="">{{ $t('clients.all') || 'All' }}</option>
          <option value="completed">{{ $t('payments.completed') }}</option>
          <option value="pending">{{ $t('payments.pending') }}</option>
          <option value="rejected">{{ $t('payments.rejected') }}</option>
          <option value="expired">{{ $t('payments.expiredFailed') || 'Expired' }}</option>
        </select>
      </div>
    </div>

    <div class="row g-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="stat-value">{{ total }}</div>
          <div class="stat-label">{{ $t('payments.totalInvoices') }}</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="stat-value text-success">{{ completedCount }}</div>
          <div class="stat-label">{{ $t('payments.completed') }}</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="stat-value text-warning">{{ pendingCount }}</div>
          <div class="stat-label">{{ $t('payments.pending') }}</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="stat-value text-danger">{{ rejectedCount }}</div>
          <div class="stat-label">{{ $t('payments.rejected') }}</div>
        </div>
      </div>
    </div>

    <div class="table-card">
      <div v-if="loading" class="text-center py-4">
        <span class="spinner-border spinner-border-sm me-2"></span>{{ $t('common.loading') || 'Loading...' }}
      </div>
      <div v-else class="table-responsive">
        <table class="table table-hover">
          <thead>
            <tr>
              <th class="d-none d-md-table-cell">{{ $t('payments.invoiceId') }}</th>
              <th>{{ $t('payments.client') || 'User' }}</th>
              <th>{{ $t('payments.amount') }}</th>
              <th class="d-none d-sm-table-cell">{{ $t('payments.tier') }}</th>
              <th class="d-none d-lg-table-cell">{{ $t('payments.provider') }}</th>
              <th>{{ $t('payments.status') }}</th>
              <th class="d-none d-md-table-cell">{{ $t('payments.created') }}</th>
              <th>{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in payments" :key="p.id">
              <td class="d-none d-md-table-cell"><code class="small">{{ p.invoice_id }}</code></td>
              <td>
                <div>{{ p.username || '-' }}</div>
                <small class="text-muted d-none d-sm-block">{{ p.email }}</small>
              </td>
              <td class="fw-medium">${{ p.amount_usd }}</td>
              <td class="d-none d-sm-table-cell">
                <span class="badge" :class="tierBadge(p.subscription_tier)">{{ p.subscription_tier || '-' }}</span>
              </td>
              <td class="d-none d-lg-table-cell">{{ p.provider_name || p.payment_method || '-' }}</td>
              <td>
                <span class="badge" :class="statusClass(p.status)">{{ p.status }}</span>
              </td>
              <td class="d-none d-md-table-cell">{{ formatDate(p.created_at) }}</td>
              <td>
                <div class="btn-group btn-group-sm mobile-table-actions" v-if="p.status === 'pending'">
                  <button class="btn btn-outline-success btn-sm" @click="confirmPayment(p)" title="Confirm">&#x2714;</button>
                  <button class="btn btn-outline-danger btn-sm" @click="rejectPayment(p)" title="Reject">&#x2716;</button>
                </div>
                <button v-if="p.status !== 'pending'" class="btn btn-outline-danger btn-sm" @click="deletePayment(p)" title="Delete">&#x1F5D1;</button>
              </td>
            </tr>
            <tr v-if="payments.length === 0">
              <td colspan="8" class="text-center text-muted py-4">{{ $t('payments.noPayments') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { portalUsersApi } from '../api'

const payments = ref([])
const total = ref(0)
const statusFilter = ref('')
const searchQuery = ref('')
const loading = ref(false)

const completedCount = computed(() => payments.value.filter((p) => p.status === 'completed').length)
const pendingCount = computed(() => payments.value.filter((p) => p.status === 'pending').length)
const rejectedCount = computed(() => payments.value.filter((p) => p.status === 'rejected').length)

function statusClass(status) {
  const map = {
    completed: 'badge-online',
    pending: 'badge-warning',
    rejected: 'badge-soft-danger',
    expired: 'badge-offline',
    failed: 'badge-offline',
  }
  return map[status] || 'badge-soft-secondary'
}

function tierBadge(tier) {
  const map = { basic: 'badge-soft-info', standard: 'badge-soft-primary', premium: 'badge-soft-warning', free: 'badge-soft-secondary' }
  return map[tier?.toLowerCase()] || 'badge-soft-secondary'
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

async function loadPayments() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (statusFilter.value) params.status = statusFilter.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await portalUsersApi.getPayments(params)
    payments.value = data.items || []
    total.value = data.total || payments.value.length
  } catch (err) {
    console.error('Error loading payments:', err)
  } finally {
    loading.value = false
  }
}

async function confirmPayment(p) {
  if (!confirm(`Confirm payment ${p.invoice_id} ($${p.amount_usd})?`)) return
  try {
    await portalUsersApi.confirmPayment(p.id)
    await loadPayments()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function rejectPayment(p) {
  if (!confirm(`Reject payment ${p.invoice_id}?`)) return
  try {
    await portalUsersApi.rejectPayment(p.id)
    await loadPayments()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function deletePayment(p) {
  if (!confirm(`Delete payment ${p.invoice_id}?`)) return
  try {
    await portalUsersApi.deletePayment(p.id)
    await loadPayments()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

onMounted(loadPayments)
</script>
