<template>
  <FeatureGuard
    feature="promo_codes"
    tier="starter"
    title="Promo Codes"
    description="Create discount codes (percent off, free-day extensions, tier-restricted, expiring) for your client portal. Available on Starter and above."
  >
  <div>
    <!-- Stats -->
    <div class="row g-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ stats.total_codes ?? 0 }}</div>
              <div class="stat-label">{{ $t('promo.totalCodes') }}</div>
            </div>
            <div class="stat-icon">&#x1F3AB;</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value text-success">{{ stats.active_codes ?? 0 }}</div>
              <div class="stat-label">{{ $t('promo.activeCodes') }}</div>
            </div>
            <div class="stat-icon">&#x2705;</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ stats.total_uses ?? 0 }}</div>
              <div class="stat-label">{{ $t('promo.totalUses') }}</div>
            </div>
            <div class="stat-icon">&#x1F4CA;</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ stats.active_codes ?? 0 }}/{{ stats.total_codes ?? 0 }}</div>
              <div class="stat-label">{{ $t('promo.activeRatio') || 'Active / Total' }}</div>
            </div>
            <div class="stat-icon">&#x1F4B0;</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Inline feedback -->
    <div v-if="successMsg" class="alert alert-success alert-dismissible fade show">
      {{ successMsg }}
      <button type="button" class="btn-close" @click="successMsg = null"></button>
    </div>
    <div v-if="errorMsg" class="alert alert-danger alert-dismissible fade show">
      {{ errorMsg }}
      <button type="button" class="btn-close" @click="errorMsg = null"></button>
    </div>

    <!-- Table -->
    <div class="table-card">
      <div class="table-card-header">
        <h6>{{ $t('promo.title') }}</h6>
        <button class="btn btn-sm btn-primary" @click="openCreate">+ {{ $t('promo.createCode') }}</button>
      </div>
      <div class="table-responsive">
        <table class="table table-hover mb-0">
          <thead>
            <tr>
              <th>{{ $t('promo.code') }}</th>
              <th>{{ $t('promo.type') }}</th>
              <th class="d-none d-sm-table-cell">{{ $t('promo.value') }}</th>
              <th class="d-none d-md-table-cell">{{ $t('promo.uses') }}</th>
              <th class="d-none d-md-table-cell">{{ $t('promo.expiry') }}</th>
              <th>{{ $t('common.status') }}</th>
              <th>{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="code in codes" :key="code.id">
              <td><code class="fw-bold">{{ code.code }}</code></td>
              <td>
                <span class="badge" :class="code.discount_type === 'percent' ? 'badge-soft-info' : 'badge-soft-warning'">
                  {{ code.discount_type }}
                </span>
              </td>
              <td class="d-none d-sm-table-cell">
                <template v-if="code.discount_type === 'percent'">{{ code.discount_value }}%</template>
                <template v-else>{{ code.discount_value }} {{ $t('promo.days') }}</template>
              </td>
              <td class="d-none d-md-table-cell">{{ code.used_count }} / {{ code.max_uses ?? '&infin;' }}</td>
              <td class="d-none d-md-table-cell">{{ code.expires_at ? new Date(code.expires_at).toLocaleDateString() : '-' }}</td>
              <td>
                <span class="badge" :class="code.is_active ? 'badge-online' : 'badge-offline'">
                  {{ code.is_active ? $t('common.enabled') : $t('common.disabled') }}
                </span>
              </td>
              <td>
                <div class="d-flex flex-wrap gap-1">
                  <button class="btn btn-sm btn-outline-primary" @click="openEdit(code)">{{ $t('common.edit') }}</button>
                  <button class="btn btn-sm btn-outline-danger" @click="deleteCode(code)">{{ $t('common.delete') }}</button>
                </div>
              </td>
            </tr>
            <tr v-if="codes.length === 0">
              <td colspan="7" class="text-center text-muted py-4">{{ $t('promo.noCodes') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <div v-if="showModal" class="modal d-block" tabindex="-1" @mousedown.self="showModal = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editing ? $t('promo.editCode') : $t('promo.createCode') }}</h5>
            <button type="button" class="btn-close" @click="showModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('promo.code') }}</label>
              <input v-model="form.code" class="form-control" :placeholder="$t('promo.codePlaceholder')" :disabled="editing">
              <small class="text-muted">{{ $t('promo.codeHint') }}</small>
            </div>
            <div class="row mb-3">
              <div class="col-6">
                <label class="form-label">{{ $t('promo.type') }}</label>
                <select v-model="form.discount_type" class="form-select">
                  <option value="percent">{{ $t('promo.typePercent') }}</option>
                  <option value="days">{{ $t('promo.typeDays') }}</option>
                </select>
              </div>
              <div class="col-6">
                <label class="form-label">{{ $t('promo.value') }}</label>
                <input v-model.number="form.discount_value" type="number" class="form-control" min="1">
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-6">
                <label class="form-label">{{ $t('promo.maxUses') }}</label>
                <input v-model.number="form.max_uses" type="number" class="form-control" min="0" :placeholder="$t('promo.unlimitedPlaceholder')">
              </div>
              <div class="col-6">
                <label class="form-label">{{ $t('promo.expiry') }}</label>
                <input v-model="form.expiry_date" type="date" class="form-control">
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('promo.tierRestriction') }}</label>
              <input v-model="form.applicable_tiers" class="form-control" :placeholder="$t('promo.tierPlaceholder')">
            </div>
            <div class="form-check">
              <input v-model="form.is_active" type="checkbox" class="form-check-input" id="promoActive">
              <label class="form-check-label" for="promoActive">{{ $t('common.enabled') }}</label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showModal = false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="saveCode" :disabled="saving">
              {{ saving ? $t('common.saving') : $t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showModal" class="modal-backdrop fade show"></div>
  </div>
  </FeatureGuard>
</template>

<script setup>
import FeatureGuard from '../components/FeatureGuard.vue'
import { ref, onMounted } from 'vue'
import { promoCodesApi } from '../api'

const codes = ref([])
const stats = ref({})
const successMsg = ref(null)
const errorMsg = ref(null)
const showModal = ref(false)
const editing = ref(false)
const saving = ref(false)
const editId = ref(null)

const form = ref({
  code: '',
  discount_type: 'percent',
  discount_value: 10,
  max_uses: null,
  expiry_date: '',
  applicable_tiers: '',
  is_active: true,
})

const loading = ref(false)

function showSuccess(msg) {
  successMsg.value = msg
  setTimeout(() => successMsg.value = null, 3000)
}

function showError(msg) {
  errorMsg.value = msg
  setTimeout(() => errorMsg.value = null, 5000)
}

async function loadData() {
  loading.value = true
  try {
    const [codesRes, statsRes] = await Promise.all([
      promoCodesApi.list(),
      promoCodesApi.stats().catch(() => ({ data: {} })),
    ])
    codes.value = codesRes.data.items || codesRes.data
    stats.value = statsRes.data
  } catch (e) {
    console.error('Failed to load promo codes:', e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  editId.value = null
  form.value = {
    code: '',
    discount_type: 'percent',
    discount_value: 10,
    max_uses: null,
    expiry_date: '',
    applicable_tiers: '',
    is_active: true,
  }
  showModal.value = true
}

function openEdit(code) {
  editing.value = true
  editId.value = code.id
  form.value = {
    code: code.code,
    discount_type: code.discount_type,
    discount_value: code.discount_value,
    max_uses: code.max_uses,
    expiry_date: code.expires_at ? code.expires_at.split('T')[0] : '',
    applicable_tiers: code.applies_to_tier || '',
    is_active: code.is_active,
  }
  showModal.value = true
}

async function saveCode() {
  saving.value = true
  try {
    const raw = { ...form.value }
    // Map frontend field names to backend schema
    const data = {
      code: raw.code || undefined,
      discount_type: raw.discount_type,
      discount_value: raw.discount_value,
      max_uses: raw.max_uses || null,
      applies_to_tier: raw.applicable_tiers || null,
      expires_at: raw.expiry_date ? new Date(raw.expiry_date + 'T23:59:59Z').toISOString() : null,
      is_active: raw.is_active,
    }
    if (!data.code) delete data.code

    if (editing.value) {
      await promoCodesApi.update(editId.value, data)
    } else {
      await promoCodesApi.create(data)
    }
    showModal.value = false
    await loadData()
    showSuccess(editing.value ? 'Promo code updated' : 'Promo code created')
  } catch (e) {
    showError(e.response?.data?.detail || 'Error saving promo code')
  } finally {
    saving.value = false
  }
}

async function deleteCode(code) {
  if (!confirm(`Delete promo code "${code.code}"?`)) return
  try {
    await promoCodesApi.delete(code.id)
    await loadData()
    showSuccess(`Promo code "${code.code}" deleted`)
  } catch (e) {
    showError('Error deleting promo code')
  }
}

onMounted(loadData)
</script>
