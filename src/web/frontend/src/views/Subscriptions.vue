<template>
  <div class="subscriptions-page">
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-4 mobile-toolbar">
      <h6 class="mb-0">{{ $t('subscriptions.title') }}</h6>
      <button class="btn btn-primary btn-sm" @click="openCreateModal">
        {{ $t('subscriptions.newPlan') }}
      </button>
    </div>

    <div class="row g-4 mb-4">
      <!-- Tariffs Table -->
      <div class="col-lg-8">
        <div class="table-card">
          <div class="table-responsive">
            <table class="table table-hover mb-0 sub-table">
              <thead>
                <tr>
                  <th class="d-none d-xl-table-cell">#</th>
                  <th class="d-none d-md-table-cell">{{ $t('subscriptions.tier') }}</th>
                  <th>{{ $t('common.name') }}</th>
                  <th class="text-end">{{ $t('subscriptions.perMonth') }}</th>
                  <th class="d-none d-xl-table-cell text-end sub-th--secondary">{{ $t('subscriptions.per3Months') }}</th>
                  <th class="d-none d-xl-table-cell text-end sub-th--secondary">{{ $t('subscriptions.perYear') }}</th>
                  <th class="d-none d-lg-table-cell text-center">{{ $t('subscriptions.devices') }}</th>
                  <th class="d-none d-lg-table-cell text-end">{{ $t('subscriptions.traffic') }}</th>
                  <th class="d-none d-xl-table-cell text-end sub-th--secondary">{{ $t('subscriptions.bandwidth') }}</th>
                  <th class="d-none d-sm-table-cell">{{ $t('subscriptions.status') }}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(tariff, idx) in tariffs" :key="tariff.id" :class="idx % 2 === 1 ? 'sub-row-alt' : ''">
                  <td class="text-muted small d-none d-xl-table-cell">{{ tariff.display_order }}</td>
                  <td class="d-none d-md-table-cell">
                    <span class="sub-tier-badge" :class="subTierClass(tariff.tier)">{{ tariff.tier }}</span>
                  </td>
                  <td class="fw-semibold">{{ tariff.name }}</td>
                  <td class="text-end fw-medium">${{ (tariff.price_monthly_usd ?? 0).toFixed(2) }}</td>
                  <td class="d-none d-xl-table-cell text-end sub-secondary">{{ tariff.price_quarterly_usd ? '$' + tariff.price_quarterly_usd.toFixed(2) : '—' }}</td>
                  <td class="d-none d-xl-table-cell text-end sub-secondary">{{ tariff.price_yearly_usd ? '$' + tariff.price_yearly_usd.toFixed(2) : '—' }}</td>
                  <td class="d-none d-lg-table-cell text-center">{{ tariff.max_devices }}</td>
                  <td class="d-none d-lg-table-cell text-end">{{ tariff.traffic_limit_gb ? tariff.traffic_limit_gb + ' GB' : $t('subscriptions.unlimited') }}</td>
                  <td class="d-none d-xl-table-cell text-end sub-secondary">{{ tariff.bandwidth_limit_mbps ? tariff.bandwidth_limit_mbps + ' Mbps' : $t('subscriptions.unlimited') }}</td>
                  <td class="d-none d-sm-table-cell" style="white-space:nowrap">
                    <span class="badge" :class="tariff.is_active ? 'badge-online' : 'badge-offline'">
                      {{ tariff.is_active ? $t('subscriptions.active') : $t('subscriptions.inactive') }}
                    </span>
                    <span class="badge bg-secondary ms-1" v-if="!tariff.is_visible" style="font-size:.65rem">{{ $t('subscriptions.hidden') }}</span>
                    <span class="sub-corp-badge ms-1" v-if="tariff.corp_networks > 0">
                      Corp {{ tariff.corp_networks }}/{{ tariff.corp_sites || 0 }}
                    </span>
                  </td>
                  <td class="sub-actions-cell">
                    <button class="btn btn-sm sub-edit-btn" @click="openEditModal(tariff)" :title="$t('subscriptions.editTariff')">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293l6.5-6.5z"/></svg>
                    </button>
                    <button
                      class="btn btn-sm sub-delete-btn"
                      @click="deleteTariff(tariff)"
                      :title="$t('common.delete')"
                      v-if="tariff.tier !== 'free'"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H5.5l1-1h3l1 1h2.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>
                    </button>
                  </td>
                </tr>
                <tr v-if="tariffs.length === 0 && !loading">
                  <td colspan="11" class="text-center text-muted py-4">{{ $t('subscriptions.noPlans') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Right sidebar -->
      <div class="col-lg-4 sub-sidebar">
        <!-- Stats -->
        <div class="stat-card mb-3">
          <div class="stat-value">{{ tariffs.length }}</div>
          <div class="stat-label">{{ $t('subscriptions.totalPlans') }}</div>
        </div>
        <div class="stat-card mb-3">
          <div class="stat-value">{{ tariffs.filter(t => t.is_active).length }}</div>
          <div class="stat-label">{{ $t('subscriptions.activePlans') }}</div>
        </div>

        <!-- Simulate Payment -->
        <div class="card mt-3 sub-simulate-card">
          <div class="card-header py-2">
            <h6 class="mb-0 small">{{ $t('subscriptions.simulatePayment') }}</h6>
          </div>
          <div class="card-body">
            <p class="small text-muted">{{ $t('subscriptions.simulateDesc') }}</p>
            <div class="mb-3">
              <label class="form-label small">{{ $t('subscriptions.invoiceId') }}</label>
              <input v-model="simulateInvoiceId" type="text" class="form-control form-control-sm" :placeholder="$t('subscriptions.invoicePlaceholder')" />
            </div>
            <button
              class="btn btn-warning btn-sm w-100"
              @click="simulatePayment"
              :disabled="!simulateInvoiceId || simulating"
            >
              <span v-if="simulating" class="spinner-border spinner-border-sm me-1"></span>
              {{ simulating ? $t('subscriptions.processing') : $t('subscriptions.simulateSuccess') }}
            </button>
            <div class="alert alert-success mt-2 small py-1 px-2" v-if="simulateResult">
              {{ simulateResult }}
            </div>
            <div class="alert alert-danger mt-2 small py-1 px-2" v-if="simulateError">
              {{ simulateError }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <div class="modal fade" :class="{ show: showModal }" :style="{ display: showModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingTariff ? $t('subscriptions.editTariff') : $t('subscriptions.createTariff') }}</h5>
            <button type="button" class="btn-close" @click="showModal = false"></button>
          </div>
          <div class="modal-body sub-modal-body">
            <!-- GROUP 1: Basic -->
            <div class="sub-form-group">
              <div class="sub-form-group__title">{{ $t('subscriptions.planName') }}</div>
              <div class="row g-3">
                <div class="col-md-8">
                  <label class="form-label small fw-medium">{{ $t('subscriptions.planName') }}</label>
                  <input v-model="form.name" type="text" class="form-control" :placeholder="$t('subscriptions.planNamePlaceholder')" />
                </div>
                <div class="col-md-4">
                  <label class="form-label small sub-label-muted">{{ $t('subscriptions.tierSlug') }}</label>
                  <input v-model="form.tier" type="text" class="form-control form-control-sm sub-input-muted"
                    :placeholder="$t('subscriptions.tierSlugPlaceholder')" :disabled="!!editingTariff" />
                  <div class="form-text" style="font-size:.68rem">{{ $t('subscriptions.tierSlugHint') }}</div>
                </div>
              </div>
              <div class="mt-2">
                <label class="form-label small sub-label-muted">{{ $t('subscriptions.description') }}</label>
                <input v-model="form.description" type="text" class="form-control form-control-sm sub-input-muted" :placeholder="$t('subscriptions.descriptionPlaceholder')" />
              </div>
            </div>

            <!-- GROUP 2: Pricing -->
            <div class="sub-form-group">
              <div class="sub-form-group__title">{{ $t('subscriptions.pricingUsd') }}</div>
              <div class="row g-3">
                <div class="col-md-4">
                  <label class="form-label small fw-medium">{{ $t('subscriptions.monthlyPrice') }}</label>
                  <div class="input-group">
                    <span class="input-group-text">$</span>
                    <input v-model.number="form.price_monthly_usd" type="number" step="0.01" class="form-control" />
                  </div>
                </div>
                <div class="col-md-4">
                  <label class="form-label small sub-label-muted">{{ $t('subscriptions.quarterlyPrice') }}</label>
                  <div class="input-group input-group-sm">
                    <span class="input-group-text">$</span>
                    <input v-model.number="form.price_quarterly_usd" type="number" step="0.01" class="form-control" />
                  </div>
                </div>
                <div class="col-md-4">
                  <label class="form-label small sub-label-muted">{{ $t('subscriptions.yearlyPrice') }}</label>
                  <div class="input-group input-group-sm">
                    <span class="input-group-text">$</span>
                    <input v-model.number="form.price_yearly_usd" type="number" step="0.01" class="form-control" />
                  </div>
                </div>
              </div>
            </div>

            <!-- GROUP 3: Limits -->
            <div class="sub-form-group">
              <div class="sub-form-group__title">{{ $t('subscriptions.devices') }} &amp; {{ $t('subscriptions.traffic') }}</div>
              <div class="row g-3">
                <div class="col-md-4">
                  <label class="form-label small d-flex align-items-center">{{ $t('subscriptions.maxDevices') }}<HelpTooltip :text="$t('help.maxDevices')" /></label>
                  <input v-model.number="form.max_devices" type="number" min="1" class="form-control form-control-sm" />
                </div>
                <div class="col-md-4">
                  <label class="form-label small d-flex align-items-center">{{ $t('subscriptions.trafficLimitGb') }}<HelpTooltip :text="$t('help.trafficLimit')" /></label>
                  <input v-model.number="form.traffic_limit_gb" type="number" class="form-control form-control-sm" :placeholder="$t('subscriptions.emptyUnlimited')" />
                </div>
                <div class="col-md-4">
                  <label class="form-label small d-flex align-items-center">{{ $t('subscriptions.bandwidthMbps') }}<HelpTooltip :text="$t('help.bandwidthLimit')" /></label>
                  <input v-model.number="form.bandwidth_limit_mbps" type="number" class="form-control form-control-sm" :placeholder="$t('subscriptions.emptyUnlimited')" />
                </div>
              </div>
            </div>

            <!-- GROUP 4: Corporate (advanced, muted) -->
            <div class="sub-form-group sub-form-group--advanced">
              <div class="sub-form-group__title sub-form-group__title--muted">Corporate VPN</div>
              <div class="row g-3">
                <div class="col-md-6">
                  <label class="form-label small d-flex align-items-center sub-label-muted">{{ $t('subscriptions.corpNetworks') }}<HelpTooltip :text="$t('help.corpNetworks')" /></label>
                  <input v-model.number="form.corp_networks" type="number" min="0" class="form-control form-control-sm" />
                </div>
                <div class="col-md-6">
                  <label class="form-label small sub-label-muted">Corp sites per network</label>
                  <input v-model.number="form.corp_sites" type="number" min="0" class="form-control form-control-sm" />
                </div>
              </div>
            </div>

            <!-- GROUP 5: System -->
            <div class="sub-form-group sub-form-group--last">
              <div class="sub-form-group__title">{{ $t('subscriptions.status') }}</div>
              <div class="d-flex flex-wrap align-items-center gap-4">
                <div class="form-check form-switch">
                  <input class="form-check-input" type="checkbox" v-model="form.is_active" id="isActive" />
                  <label class="form-check-label small" for="isActive">{{ $t('subscriptions.active') }}</label>
                </div>
                <div class="form-check form-switch">
                  <input class="form-check-input" type="checkbox" v-model="form.is_visible" id="isVisible" />
                  <label class="form-check-label small" for="isVisible">{{ $t('subscriptions.visibleInPortal') }}</label>
                </div>
                <div class="d-flex align-items-center gap-2">
                  <label class="form-label small mb-0 sub-label-muted">{{ $t('subscriptions.displayOrder') }}</label>
                  <input v-model.number="form.display_order" type="number" class="form-control form-control-sm" style="width:70px" />
                </div>
              </div>
            </div>

            <!-- Error -->
            <div class="alert alert-danger mt-3 py-2 small" v-if="formError">{{ formError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="saveTariff" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
              {{ editingTariff ? $t('subscriptions.saveChanges') : $t('subscriptions.create') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showModal"></div>

    <!-- Delete Confirmation Modal -->
    <div class="modal fade" :class="{ show: showDeleteModal }" :style="{ display: showDeleteModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('subscriptions.deleteTariff') }}</h5>
            <button type="button" class="btn-close" @click="showDeleteModal = false"></button>
          </div>
          <div class="modal-body">
            <p>{{ $t('subscriptions.deactivateConfirm', { name: deletingTariff?.name }) }}</p>
            <p class="text-muted small">{{ $t('subscriptions.deactivateHint') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="showDeleteModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-danger btn-sm" @click="confirmDelete">{{ $t('common.delete') }}</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showDeleteModal"></div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { tariffsApi } from '../api'

// State
const tariffs = ref([])
const loading = ref(false)
const showModal = ref(false)
const showDeleteModal = ref(false)
const editingTariff = ref(null)
const deletingTariff = ref(null)
const saving = ref(false)
const formError = ref(null)

// Simulate payment
const simulateInvoiceId = ref('')
const simulating = ref(false)
const simulateResult = ref(null)
const simulateError = ref(null)

const defaultForm = {
  tier: '',
  name: '',
  description: '',
  max_devices: 1,
  traffic_limit_gb: null,
  bandwidth_limit_mbps: null,
  price_monthly_usd: 0,
  price_quarterly_usd: null,
  price_yearly_usd: null,
  is_active: true,
  is_visible: true,
  display_order: 0,
  corp_networks: 0,
  corp_sites: 0,
}

const form = ref({ ...defaultForm })

// Methods
async function loadTariffs() {
  loading.value = true
  try {
    const { data } = await tariffsApi.list()
    tariffs.value = data
  } catch (err) {
    console.error('Error loading tariffs:', err)
  } finally {
    loading.value = false
  }
}

function openCreateModal() {
  editingTariff.value = null
  form.value = { ...defaultForm, display_order: tariffs.value.length }
  formError.value = null
  showModal.value = true
}

function openEditModal(tariff) {
  editingTariff.value = tariff
  form.value = {
    tier: tariff.tier,
    name: tariff.name,
    description: tariff.description || '',
    max_devices: tariff.max_devices,
    traffic_limit_gb: tariff.traffic_limit_gb,
    bandwidth_limit_mbps: tariff.bandwidth_limit_mbps,
    price_monthly_usd: tariff.price_monthly_usd,
    price_quarterly_usd: tariff.price_quarterly_usd,
    price_yearly_usd: tariff.price_yearly_usd,
    is_active: tariff.is_active,
    is_visible: tariff.is_visible,
    display_order: tariff.display_order,
    corp_networks: tariff.corp_networks ?? 0,
    corp_sites: tariff.corp_sites ?? 0,
  }
  formError.value = null
  showModal.value = true
}

async function saveTariff() {
  saving.value = true
  formError.value = null

  try {
    // Clean up null-ish values
    const payload = { ...form.value }
    if (!payload.traffic_limit_gb) payload.traffic_limit_gb = null
    if (!payload.bandwidth_limit_mbps) payload.bandwidth_limit_mbps = null
    if (!payload.price_quarterly_usd) payload.price_quarterly_usd = null
    if (!payload.price_yearly_usd) payload.price_yearly_usd = null

    if (editingTariff.value) {
      // Update
      const { tier, ...updateData } = payload
      await tariffsApi.update(editingTariff.value.id, updateData)
    } else {
      // Create
      await tariffsApi.create(payload)
    }

    showModal.value = false
    await loadTariffs()
  } catch (err) {
    formError.value = err.response?.data?.detail || err.message
  } finally {
    saving.value = false
  }
}

function deleteTariff(tariff) {
  deletingTariff.value = tariff
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (!deletingTariff.value) return

  try {
    await tariffsApi.delete(deletingTariff.value.id)
    showDeleteModal.value = false
    await loadTariffs()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function simulatePayment() {
  simulating.value = true
  simulateResult.value = null
  simulateError.value = null

  try {
    const { data } = await tariffsApi.simulatePayment(simulateInvoiceId.value)
    simulateResult.value = `Payment simulated! User #${data.user_id} → ${data.tier} ($${data.amount_usd})`
    simulateInvoiceId.value = ''
  } catch (err) {
    simulateError.value = err.response?.data?.detail || err.message
  } finally {
    simulating.value = false
  }
}

function subTierClass(tier) {
  const map = { free: 'sub-tier--free', basic: 'sub-tier--basic', standard: 'sub-tier--standard', premium: 'sub-tier--premium', enterprise: 'sub-tier--enterprise', corporation: 'sub-tier--corporation' }
  return map[tier] || 'sub-tier--free'
}

onMounted(loadTariffs)
</script>

<style scoped>
/* ── Table ─────────────────────────────────────────────────── */
.sub-table { font-size: .875rem; }
.sub-table thead th {
  font-size: .72rem; text-transform: uppercase; letter-spacing: .03em;
  color: var(--vxy-muted); font-weight: 600; padding: .55rem .75rem;
  border-bottom: 2px solid var(--vxy-border);
}
.sub-th--secondary { opacity: .6; }
.sub-table tbody td {
  padding: .65rem .75rem; vertical-align: middle;
  border-bottom: 1px solid rgba(125,125,125,.07);
}
.sub-row-alt { background: rgba(125,125,125,.025); }
.sub-table tbody tr { transition: background .15s; }
.sub-table tbody tr:hover { background: rgba(115,103,240,.06); }

/* Secondary text for less important columns */
.sub-secondary { font-size: .8rem; color: var(--vxy-muted); }

/* ── Actions cell ──────────────────────────────────────────── */
.sub-actions-cell {
  white-space: nowrap;
  display: flex; align-items: center; gap: .25rem;
}
/* Delete button: hidden by default, shown on row hover */
.sub-delete-btn {
  opacity: 0; transition: opacity .15s;
  border: 1px solid transparent; background: transparent;
  color: var(--vxy-muted); font-size: .78rem;
  width: 30px; height: 30px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: .3rem;
}
.sub-delete-btn:hover { color: var(--vxy-danger, #dc3545); border-color: rgba(220,53,69,.3); background: rgba(220,53,69,.06); }
.sub-table tbody tr:hover .sub-delete-btn { opacity: 1; }

/* ── Sidebar ───────────────────────────────────────────────── */
.sub-sidebar { border-left: 1px solid rgba(125,125,125,.1); padding-left: 1.5rem; }

/* ── Tier badges ───────────────────────────────────────────── */
.sub-tier-badge {
  display: inline-block; padding: .2em .55em; border-radius: .3rem;
  font-size: .7rem; font-weight: 600; text-transform: capitalize;
  white-space: nowrap;
}
.sub-tier--free { background: rgba(108,117,125,.12); color: #6c757d; }
.sub-tier--basic { background: rgba(13,202,240,.12); color: #0aa2c0; }
.sub-tier--standard { background: var(--vxy-primary-light); color: var(--vxy-primary); }
.sub-tier--premium { background: rgba(255,159,67,.15); color: #e8851c; }
.sub-tier--corporation { background: rgba(234,84,85,.1); color: #ea5455; }
.sub-tier--enterprise { background: rgba(115,103,240,.12); color: #7367f0; }

/* Corp badge — muted tertiary */
.sub-corp-badge {
  display: inline-block; padding: .12em .35em; border-radius: .2rem;
  font-size: .62rem; font-weight: 500;
  background: rgba(108,117,125,.08); color: var(--vxy-muted);
}

/* Edit button */
.sub-edit-btn {
  border: 1px solid var(--vxy-border); background: transparent;
  color: var(--vxy-muted); cursor: pointer;
  width: 30px; height: 30px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: .3rem;
  transition: background .15s, border-color .15s, color .15s;
}
.sub-edit-btn:hover {
  background: var(--vxy-primary-light, rgba(115,103,240,.08));
  border-color: var(--vxy-primary); color: var(--vxy-primary);
}

/* Simulate card — quieter */
.sub-simulate-card { opacity: .75; transition: opacity .2s; }
.sub-simulate-card:hover { opacity: 1; }

/* ── Modal form groups ─────────────────────────────────────── */
.sub-modal-body { padding: 1.25rem 1.5rem; }
.sub-form-group {
  padding-bottom: 1.25rem; margin-bottom: 1.25rem;
  border-bottom: 1px solid rgba(125,125,125,.1);
}
.sub-form-group--last { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
.sub-form-group--advanced { opacity: .75; }
.sub-form-group--advanced:focus-within { opacity: 1; }
.sub-form-group__title {
  font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--vxy-primary, #7367f0);
  margin-bottom: .65rem;
}
.sub-form-group__title--muted { color: var(--vxy-muted); }

/* Muted labels & inputs for secondary fields */
.sub-label-muted { color: var(--vxy-muted) !important; font-weight: 400 !important; }
.sub-input-muted { color: var(--vxy-muted); font-size: .82rem; }

/* ── Mobile ────────────────────────────────────────────────── */
@media (max-width: 991px) {
  .sub-sidebar { border-left: none; padding-left: 0; }
}
@media (max-width: 768px) {
  .sub-table { font-size: .82rem; }
  .sub-table tbody td { padding: .55rem .5rem; }
  .sub-delete-btn { opacity: 1; }
  .sub-modal-body { padding: .875rem 1rem; }
}
</style>
