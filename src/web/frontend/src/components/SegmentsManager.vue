<template>
  <div v-if="show" class="modal fade show" tabindex="-1" style="display:block;z-index:1055" @mousedown.self="$emit('close')">
    <div class="modal-dialog modal-xl modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">{{ t('clients.segments.title') }}</h5>
          <button type="button" class="btn-close" @click="$emit('close')"></button>
        </div>
        <div class="modal-body">
          <!-- Error/Success feedback -->
          <div v-if="successMsg" class="alert alert-success alert-dismissible fade show py-2">
            {{ successMsg }}
            <button type="button" class="btn-close" @click="successMsg = null"></button>
          </div>
          <div v-if="errorMsg" class="alert alert-danger alert-dismissible fade show py-2">
            {{ errorMsg }}
            <button type="button" class="btn-close" @click="errorMsg = null"></button>
          </div>

          <!-- Create / Edit form -->
          <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
              <span class="fw-medium">{{ editingId ? t('clients.segments.editSegment') : t('clients.segments.newSegment') }}</span>
              <button v-if="editingId" class="btn btn-sm btn-link text-muted" @click="resetForm">{{ t('common.cancel') }}</button>
            </div>
            <div class="card-body">
              <form @submit.prevent="saveSegment">
                <div class="row g-3">
                  <div class="col-12 col-md-4">
                    <label class="form-label form-label-sm">{{ t('common.name') }} *</label>
                    <input v-model="form.name" type="text" class="form-control form-control-sm" required :placeholder="t('clients.segments.namePlaceholder')" />
                  </div>
                  <div class="col-12 col-md-2">
                    <label class="form-label form-label-sm">{{ t('clients.segments.color') }}</label>
                    <div class="d-flex align-items-center gap-2">
                      <input v-model="form.color" type="color" class="form-control form-control-color form-control-sm" style="width:40px;padding:2px" />
                      <input v-model="form.color" type="text" class="form-control form-control-sm" placeholder="#6B7280" style="max-width:90px" />
                    </div>
                  </div>
                  <div class="col-12 col-md-3">
                    <label class="form-label form-label-sm">{{ t('clients.segments.bandwidthLimit') }}</label>
                    <div class="input-group input-group-sm">
                      <input v-model.number="form.bandwidth_limit" type="number" min="0" class="form-control form-control-sm" placeholder="0" />
                      <span class="input-group-text">Mbps</span>
                    </div>
                  </div>
                  <div class="col-12 col-md-3">
                    <label class="form-label form-label-sm">{{ t('clients.segments.trafficLimit') }}</label>
                    <div class="input-group input-group-sm">
                      <input v-model.number="form.traffic_limit_mb" type="number" min="0" class="form-control form-control-sm" placeholder="0" />
                      <span class="input-group-text">MB</span>
                    </div>
                  </div>
                  <div class="col-12 col-md-4">
                    <label class="form-label form-label-sm">{{ t('clients.segments.expiryDate') }}</label>
                    <input v-model="form.expiry_date" type="date" class="form-control form-control-sm" />
                  </div>
                  <div class="col-12 col-md-4">
                    <label class="form-label form-label-sm">{{ t('clients.segments.autoBandwidthRule') }}</label>
                    <select v-model="form.auto_bandwidth_rule_id" class="form-select form-select-sm">
                      <option :value="null">{{ t('clients.segments.noRule') }}</option>
                      <option v-for="rule in trafficRules" :key="rule.id" :value="rule.id">{{ rule.name }}</option>
                    </select>
                    <button type="button" class="btn btn-link btn-sm p-0 mt-1" @click="showRuleForm = !showRuleForm">
                      <i class="mdi mdi-plus"></i> {{ t('clients.segments.addRule') }}
                    </button>
                  </div>
                  <!-- inline create-rule: makes a traffic rule and binds it to THIS segment -->
                  <div v-if="showRuleForm" class="col-12">
                    <div class="border rounded p-2 bg-light">
                      <div class="row g-2 align-items-end">
                        <div class="col-12 col-md-3">
                          <label class="form-label form-label-sm">{{ t('clients.segments.ruleName') }}</label>
                          <input v-model="ruleForm.name" type="text" class="form-control form-control-sm" />
                        </div>
                        <div class="col-6 col-md-2">
                          <label class="form-label form-label-sm">{{ t('clients.segments.rulePeriod') }}</label>
                          <select v-model="ruleForm.period" class="form-select form-select-sm">
                            <option value="day">{{ t('clients.segments.periodDay') }}</option>
                            <option value="week">{{ t('clients.segments.periodWeek') }}</option>
                            <option value="month">{{ t('clients.segments.periodMonth') }}</option>
                          </select>
                        </div>
                        <div class="col-6 col-md-2">
                          <label class="form-label form-label-sm">{{ t('clients.segments.ruleThreshold') }}</label>
                          <input v-model.number="ruleForm.threshold_mb" type="number" min="1" class="form-control form-control-sm" />
                        </div>
                        <div class="col-6 col-md-2">
                          <label class="form-label form-label-sm">{{ t('clients.segments.ruleLimit') }}</label>
                          <input v-model.number="ruleForm.bandwidth_limit_mbps" type="number" min="1" class="form-control form-control-sm" />
                        </div>
                        <div class="col-6 col-md-3">
                          <button type="button" class="btn btn-primary btn-sm w-100" @click="createRule" :disabled="creatingRule">
                            <span v-if="creatingRule" class="spinner-border spinner-border-sm me-1"></span>
                            {{ t('clients.segments.createRule') }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="col-12 col-md-4">
                    <label class="form-label form-label-sm">{{ t('clients.segments.notes') }}</label>
                    <input v-model="form.notes" type="text" class="form-control form-control-sm" :placeholder="t('clients.segments.notesPlaceholder')" />
                  </div>
                </div>
                <div class="mt-3">
                  <button type="submit" class="btn btn-primary btn-sm" :disabled="saving">
                    <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
                    {{ editingId ? t('clients.saveChanges') : t('clients.segments.create') }}
                  </button>
                </div>
              </form>
            </div>
          </div>

          <!-- Segments list -->
          <div v-if="loading" class="text-center py-4 text-muted">
            <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
          </div>
          <div v-else-if="segments.length === 0" class="text-center text-muted py-4">
            {{ t('clients.segments.empty') }}
          </div>
          <div v-else class="table-responsive">
            <table class="table table-sm table-hover align-middle">
              <thead>
                <tr>
                  <th style="width:30px"></th>
                  <th>{{ t('common.name') }}</th>
                  <th class="d-none d-md-table-cell">{{ t('clients.segments.members') }}</th>
                  <th class="d-none d-lg-table-cell">{{ t('dashboard.bandwidth') }}</th>
                  <th class="d-none d-lg-table-cell">{{ t('clients.segments.trafficLimit') }}</th>
                  <th class="d-none d-lg-table-cell">{{ t('clients.expiry') }}</th>
                  <th class="d-none d-md-table-cell">{{ t('clients.segments.notes') }}</th>
                  <th>{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="seg in segments" :key="seg.id">
                  <td>
                    <span class="segment-color-dot" :style="{ background: seg.color || '#6B7280' }"></span>
                  </td>
                  <td class="fw-medium">{{ seg.name }}</td>
                  <td class="d-none d-md-table-cell text-muted small">{{ seg.member_count ?? '—' }}</td>
                  <td class="d-none d-lg-table-cell text-muted small">{{ seg.bandwidth_limit ? seg.bandwidth_limit + ' Mbps' : '∞' }}</td>
                  <td class="d-none d-lg-table-cell text-muted small">{{ seg.traffic_limit_mb ? formatMB(seg.traffic_limit_mb) : '∞' }}</td>
                  <td class="d-none d-lg-table-cell text-muted small">{{ seg.expiry_date ? formatDate(seg.expiry_date) : '∞' }}</td>
                  <td class="d-none d-md-table-cell text-muted small">{{ seg.notes || '—' }}</td>
                  <td>
                    <div class="btn-group btn-group-sm">
                      <button class="btn btn-outline-secondary" @click="applySegment(seg)" :title="t('clients.segments.apply')" :disabled="actionLoading === seg.id">
                        <span v-if="actionLoading === seg.id" class="spinner-border spinner-border-sm"></span>
                        <i v-else class="mdi mdi-check-all"></i>
                      </button>
                      <button class="btn btn-outline-success" @click="enableSegment(seg)" :title="t('clients.segments.enableAll')" :disabled="actionLoading === seg.id">
                        <i class="mdi mdi-play"></i>
                      </button>
                      <button class="btn btn-outline-secondary" @click="disableSegment(seg)" :title="t('clients.segments.disableAll')" :disabled="actionLoading === seg.id">
                        <i class="mdi mdi-pause"></i>
                      </button>
                      <button class="btn btn-outline-secondary" @click="startEdit(seg)" :title="t('clients.tipEdit')">
                        <i class="mdi mdi-pencil-outline"></i>
                      </button>
                      <button class="btn btn-outline-danger" @click="deleteSegment(seg)" :title="t('clients.tipDelete')" :disabled="actionLoading === seg.id">
                        <i class="mdi mdi-trash-can-outline"></i>
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="$emit('close')">{{ t('common.close') }}</button>
        </div>
      </div>
    </div>
  </div>
  <div v-if="show" class="modal-backdrop fade show" style="z-index:1054"></div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { segmentsApi, trafficApi } from '../api'
import { formatMB, formatDate } from '../utils'

const props = defineProps({
  show: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'refreshed'])

const { t } = useI18n()

const segments = ref([])
const trafficRules = ref([])
const loading = ref(false)
const saving = ref(false)
const actionLoading = ref(null)
const successMsg = ref(null)
const errorMsg = ref(null)

const editingId = ref(null)
const form = ref(emptyForm())

// Inline "add rule" — create a traffic rule and bind it to the segment being edited.
const showRuleForm = ref(false)
const creatingRule = ref(false)
const ruleForm = ref(emptyRuleForm())

function emptyRuleForm() {
  return { name: '', period: 'month', threshold_mb: null, bandwidth_limit_mbps: null }
}

function emptyForm() {
  return {
    name: '',
    color: '#6B7280',
    notes: '',
    bandwidth_limit: 0,
    traffic_limit_mb: 0,
    expiry_date: '',
    auto_bandwidth_rule_id: null,
  }
}

function resetForm() {
  editingId.value = null
  form.value = emptyForm()
  showRuleForm.value = false
  ruleForm.value = emptyRuleForm()
}

async function createRule() {
  const r = ruleForm.value
  if (!r.name || !r.threshold_mb || !r.bandwidth_limit_mbps) {
    showError(t('clients.segments.ruleIncomplete') || 'Fill in rule name, threshold and limit')
    return
  }
  creatingRule.value = true
  try {
    const res = await trafficApi.createRule({
      name: r.name,
      period: r.period,
      threshold_mb: Number(r.threshold_mb),
      bandwidth_limit_mbps: Number(r.bandwidth_limit_mbps),
      client_id: null,
    })
    // reload rules and select the freshly-created one for this segment
    const ruleRes = await trafficApi.getRules().catch(() => ({ data: [] }))
    const ruleData = ruleRes.data
    trafficRules.value = Array.isArray(ruleData) ? ruleData : (ruleData?.items || [])
    const newId = res.data?.id ?? res.data?.rule?.id
    if (newId) form.value.auto_bandwidth_rule_id = newId
    showRuleForm.value = false
    ruleForm.value = emptyRuleForm()
    showSuccess(t('clients.segments.ruleCreated') || 'Rule created and selected for this segment')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    creatingRule.value = false
  }
}

function startEdit(seg) {
  editingId.value = seg.id
  form.value = {
    name: seg.name || '',
    color: seg.color || '#6B7280',
    notes: seg.notes || '',
    bandwidth_limit: seg.bandwidth_limit || 0,
    traffic_limit_mb: seg.traffic_limit_mb || 0,
    expiry_date: seg.expiry_date ? seg.expiry_date.split('T')[0] : '',
    auto_bandwidth_rule_id: seg.auto_bandwidth_rule_id || null,
  }
}

function showSuccess(msg) {
  successMsg.value = msg
  setTimeout(() => { successMsg.value = null }, 4000)
}

function showError(msg) {
  errorMsg.value = msg
  setTimeout(() => { errorMsg.value = null }, 5000)
}

async function loadData() {
  loading.value = true
  try {
    const [segRes, ruleRes] = await Promise.all([
      segmentsApi.list(),
      trafficApi.getRules().catch(() => ({ data: [] })),
    ])
    const segData = segRes.data
    segments.value = Array.isArray(segData) ? segData : (segData?.items || [])
    const ruleData = ruleRes.data
    trafficRules.value = Array.isArray(ruleData) ? ruleData : (ruleData?.items || [])
  } catch (err) {
    showError('Error loading segments: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

async function saveSegment() {
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.bandwidth_limit) payload.bandwidth_limit = null
    if (!payload.traffic_limit_mb) payload.traffic_limit_mb = null
    if (!payload.expiry_date) payload.expiry_date = null
    if (editingId.value) {
      await segmentsApi.update(editingId.value, payload)
      showSuccess(t('clients.segments.updated') || 'Segment updated')
    } else {
      await segmentsApi.create(payload)
      showSuccess(t('clients.segments.created') || 'Segment created')
    }
    resetForm()
    await loadData()
    emit('refreshed')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function deleteSegment(seg) {
  if (!confirm(t('clients.segments.deleteConfirm', { name: seg.name }) || `Delete segment "${seg.name}"?`)) return
  actionLoading.value = seg.id
  try {
    await segmentsApi.remove(seg.id)
    showSuccess(t('clients.segments.deleted') || 'Segment deleted')
    await loadData()
    emit('refreshed')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    actionLoading.value = null
  }
}

async function applySegment(seg) {
  actionLoading.value = seg.id
  try {
    await segmentsApi.apply(seg.id)
    showSuccess(t('clients.segments.applied') || 'Segment settings applied to all members')
    await loadData()
    emit('refreshed')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    actionLoading.value = null
  }
}

async function enableSegment(seg) {
  actionLoading.value = seg.id
  try {
    await segmentsApi.enable(seg.id)
    showSuccess(t('clients.segments.enabledAll') || 'All members enabled')
    await loadData()
    emit('refreshed')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    actionLoading.value = null
  }
}

async function disableSegment(seg) {
  actionLoading.value = seg.id
  try {
    await segmentsApi.disable(seg.id)
    showSuccess(t('clients.segments.disabledAll') || 'All members disabled')
    await loadData()
    emit('refreshed')
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    actionLoading.value = null
  }
}

watch(() => props.show, (val) => {
  if (val) {
    resetForm()
    loadData()
  }
})
</script>

<style scoped>
.segment-color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,.12);
}
</style>
