<template>
  <div class="traffic-rules-page">
    <!-- Inline feedback -->
    <div v-if="successMsg" class="alert alert-success alert-dismissible fade show">
      {{ successMsg }}
      <button type="button" class="btn-close" @click="successMsg = null"></button>
    </div>
    <div v-if="errorMsg" class="alert alert-danger alert-dismissible fade show">
      {{ errorMsg }}
      <button type="button" class="btn-close" @click="errorMsg = null"></button>
    </div>

    <!-- Top Consumers -->
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-3 mobile-toolbar">
      <h6 class="mb-0">{{ $t('traffic.topConsumers') || 'Top Consumers' }}</h6>
      <div class="d-flex gap-2 flex-wrap justify-content-end mobile-filter-bar">
        <select v-model="filterTopServer" class="form-select form-select-sm" style="min-width: 130px; width: auto">
          <option value="">All servers</option>
          <option v-for="s in availableServers" :key="s" :value="s">{{ s }}</option>
        </select>
        <div class="btn-group btn-group-sm">
          <button class="btn" :class="period === 'day' ? 'btn-primary' : 'btn-outline-primary'" @click="period = 'day'">
            {{ $t('traffic.day') || 'Day' }}
          </button>
          <button class="btn" :class="period === 'week' ? 'btn-primary' : 'btn-outline-primary'" @click="period = 'week'">
            {{ $t('traffic.week') || 'Week' }}
          </button>
          <button class="btn" :class="period === 'month' ? 'btn-primary' : 'btn-outline-primary'" @click="period = 'month'">
            {{ $t('traffic.month') || 'Month' }}
          </button>
        </div>
      </div>
    </div>

    <div class="stat-card mb-4">
      <div v-if="loadingTop" class="text-center py-3">
        <span class="spinner-border spinner-border-sm"></span>
      </div>
      <div v-else-if="topList.length === 0" class="text-center text-muted py-3">
        {{ $t('traffic.noData') || 'No traffic data yet' }}
      </div>
      <div v-else>
        <div v-for="(item, idx) in filteredTopList" :key="item.client_id" class="d-flex align-items-center mb-2">
          <span class="fw-bold me-2" style="min-width: 24px">{{ idx + 1 }}.</span>
          <div class="flex-grow-1">
            <div class="d-flex justify-content-between mb-1">
              <span>
                {{ item.client_name }}
                <small class="text-muted ms-1">[{{ item.server_name }}]</small>
                <span v-if="item.auto_bandwidth_limit" class="badge bg-warning ms-1" style="font-size: 0.7em">
                  {{ item.auto_bandwidth_limit }} Mbps
                </span>
              </span>
              <small class="text-muted">{{ formatBytes(item.bytes_total) }}</small>
            </div>
            <div class="progress" style="height: 6px">
              <div class="progress-bar bg-info" :style="{ width: barWidth(item) + '%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-Limit Rules -->
    <div class="d-flex justify-content-between align-items-center mb-3 mobile-toolbar">
      <h6 class="mb-0">{{ $t('traffic.rules') || 'Auto-Limit Rules' }}</h6>
      <button class="btn btn-primary btn-sm" @click="openAddRule">+ {{ $t('traffic.addRule') || 'Add Rule' }}</button>
    </div>

    <div class="stat-card mb-4">
      <div v-if="rules.length === 0" class="text-center text-muted py-3">
        {{ $t('traffic.noRules') || 'No rules configured' }}
      </div>
      <table v-else class="table table-sm mb-0">
        <thead>
          <tr>
            <th>{{ $t('common.name') || 'Name' }}</th>
            <th class="d-none d-md-table-cell">{{ $t('traffic.targetClient') || 'Client' }}</th>
            <th class="d-none d-sm-table-cell">{{ $t('traffic.period') || 'Period' }}</th>
            <th>{{ $t('traffic.threshold') || 'Threshold' }}</th>
            <th class="d-none d-sm-table-cell">{{ $t('traffic.limitMbps') || 'Limit' }}</th>
            <th>{{ $t('traffic.enabled') || 'Active' }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rule in rules" :key="rule.id">
            <td>{{ rule.name }}</td>
            <td class="d-none d-md-table-cell">
              <span v-if="rule.client_id">
                {{ rule.client_name }} <small class="text-muted">[{{ rule.server_name }}]</small>
              </span>
              <span v-else class="text-muted">{{ $t('traffic.allClients') || 'All' }}</span>
            </td>
            <td class="d-none d-sm-table-cell">
              <span class="badge bg-secondary">{{ periodLabel(rule.period) }}</span>
            </td>
            <td>{{ formatMB(rule.threshold_mb) }}</td>
            <td class="d-none d-sm-table-cell">{{ rule.bandwidth_limit_mbps }} Mbps</td>
            <td>
              <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" :checked="rule.enabled" @change="toggleRule(rule)">
              </div>
            </td>
            <td>
              <div class="mobile-card-actions">
                <button class="btn btn-outline-secondary btn-sm me-1" @click="openEditRule(rule)">&#x270E;</button>
                <button class="btn btn-outline-danger btn-sm" @click="deleteRule(rule)">&#x2716;</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Active Auto-Limits -->
    <div v-if="activeLimits.length > 0">
      <h6 class="mb-3">
        {{ $t('traffic.activeLimits') || 'Active Auto-Limits' }}
        <span class="badge bg-warning ms-1">{{ activeLimits.length }}</span>
      </h6>
      <div class="stat-card">
        <div v-for="item in activeLimits" :key="item.client_id" class="d-flex justify-content-between align-items-center mb-2" style="font-size: 0.9em">
          <span>{{ item.client_name }} <small class="text-muted">[{{ item.server_name }}]</small></span>
          <span>
            <span class="badge bg-warning">{{ item.auto_bandwidth_limit }} Mbps</span>
            <small class="text-muted ms-1">({{ formatBytes(item.bytes_total) }})</small>
          </span>
        </div>
      </div>
    </div>

    <!-- Add/Edit Rule Modal -->
    <div class="modal fade" :class="{ show: showRuleModal }" :style="{ display: showRuleModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingRule ? ($t('traffic.editRule') || 'Edit Rule') : ($t('traffic.addRule') || 'Add Rule') }}</h5>
            <button type="button" class="btn-close" @click="showRuleModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('common.name') || 'Name' }}</label>
              <input type="text" class="form-control" v-model="ruleForm.name" :placeholder="$t('traffic.ruleNamePlaceholder') || 'e.g. Heavy user daily'" />
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('traffic.targetClient') || 'Client' }}</label>
              <select class="form-select" v-model="ruleForm.client_id">
                <option :value="null">{{ $t('traffic.allClients') || '-- All clients --' }}</option>
                <optgroup v-for="group in clientsByServer" :key="group.server" :label="group.server">
                  <option v-for="c in group.clients" :key="c.id" :value="c.id">{{ c.name }}</option>
                </optgroup>
              </select>
              <small class="text-muted">{{ $t('traffic.clientHint') || 'Leave empty to apply to all clients' }}</small>
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('traffic.period') || 'Period' }}</label>
              <select class="form-select" v-model="ruleForm.period">
                <option value="day">{{ $t('traffic.day') || 'Day' }}</option>
                <option value="week">{{ $t('traffic.week') || 'Week' }}</option>
                <option value="month">{{ $t('traffic.month') || 'Month' }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('traffic.threshold') || 'Threshold' }} (MB)</label>
              <input type="number" class="form-control" v-model.number="ruleForm.threshold_mb" min="1" />
              <small class="text-muted">{{ formatMB(ruleForm.threshold_mb || 0) }}</small>
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('traffic.limitMbps') || 'Bandwidth Limit' }} (Mbps)</label>
              <input type="number" class="form-control" v-model.number="ruleForm.bandwidth_limit_mbps" min="1" />
            </div>
            <div class="alert alert-danger" v-if="ruleError">{{ ruleError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="showRuleModal = false">{{ $t('common.cancel') || 'Cancel' }}</button>
            <button type="button" class="btn btn-primary btn-sm" @click="saveRule" :disabled="savingRule">
              <span v-if="savingRule" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('common.save') || 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showRuleModal"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { trafficApi } from '../api'
import { formatBytes } from '../utils'

const successMsg = ref(null)
const errorMsg = ref(null)
const period = ref('day')
const topList = ref([])
const loadingTop = ref(false)
const filterTopServer = ref('')
const loadingRules = ref(false)
const rules = ref([])
const allClients = ref([])

// Rule form
const showRuleModal = ref(false)
const editingRule = ref(null)
const savingRule = ref(false)
const ruleError = ref('')
const ruleForm = ref({
  name: '',
  period: 'day',
  threshold_mb: 5000,
  bandwidth_limit_mbps: 10,
  client_id: null,
})

// Computed: clients with active auto-limits from current period's top list
const activeLimits = ref([])

// Unique server names from top list for filter dropdown
const availableServers = computed(() => {
  const names = new Set(topList.value.map((i) => i.server_name).filter(Boolean))
  return [...names].sort()
})

// Filtered top list by server
const filteredTopList = computed(() => {
  if (!filterTopServer.value) return topList.value
  return topList.value.filter((i) => i.server_name === filterTopServer.value)
})

// Group clients by server for the dropdown
const clientsByServer = computed(() => {
  const groups = {}
  for (const c of allClients.value) {
    if (!groups[c.server_name]) {
      groups[c.server_name] = { server: c.server_name, clients: [] }
    }
    groups[c.server_name].clients.push(c)
  }
  return Object.values(groups)
})

function showSuccess(msg) {
  successMsg.value = msg
  setTimeout(() => successMsg.value = null, 3000)
}

function showError(msg) {
  errorMsg.value = msg
  setTimeout(() => errorMsg.value = null, 5000)
}

function formatMB(mb) {
  if (!mb) return '0 MB'
  if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB'
  return mb + ' MB'
}

function periodLabel(p) {
  const labels = { day: 'Day', week: 'Week', month: 'Month' }
  return labels[p] || p
}

function barWidth(item) {
  if (!filteredTopList.value.length) return 0
  const max = filteredTopList.value[0].bytes_total
  return max > 0 ? (item.bytes_total / max) * 100 : 0
}

async function fetchTop() {
  loadingTop.value = true
  try {
    const { data } = await trafficApi.getTop(period.value, 10)
    topList.value = data
    activeLimits.value = data.filter(d => d.auto_bandwidth_limit)
  } catch {
    topList.value = []
  } finally {
    loadingTop.value = false
  }
}

async function fetchRules() {
  loadingRules.value = true
  try {
    const { data } = await trafficApi.getRules()
    rules.value = data
  } catch (e) {
    console.error('Failed to load rules:', e)
    rules.value = []
  } finally {
    loadingRules.value = false
  }
}

async function fetchClients() {
  try {
    const { data } = await trafficApi.getClients()
    allClients.value = data
  } catch {
    allClients.value = []
  }
}

function openAddRule() {
  editingRule.value = null
  ruleForm.value = { name: '', period: 'day', threshold_mb: 5000, bandwidth_limit_mbps: 10, client_id: null }
  ruleError.value = ''
  showRuleModal.value = true
}

function openEditRule(rule) {
  editingRule.value = rule
  ruleForm.value = {
    name: rule.name,
    period: rule.period,
    threshold_mb: rule.threshold_mb,
    bandwidth_limit_mbps: rule.bandwidth_limit_mbps,
    client_id: rule.client_id || null,
  }
  ruleError.value = ''
  showRuleModal.value = true
}

async function saveRule() {
  if (!ruleForm.value.name || !ruleForm.value.threshold_mb || !ruleForm.value.bandwidth_limit_mbps) {
    ruleError.value = 'Fill in all fields'
    return
  }
  savingRule.value = true
  ruleError.value = ''
  try {
    if (editingRule.value) {
      await trafficApi.updateRule(editingRule.value.id, ruleForm.value)
    } else {
      await trafficApi.createRule(ruleForm.value)
    }
    showRuleModal.value = false
    await fetchRules()
    showSuccess(editingRule.value ? `Rule updated` : `Rule created`)
  } catch (err) {
    ruleError.value = err.response?.data?.detail || err.message
  } finally {
    savingRule.value = false
  }
}

async function toggleRule(rule) {
  try {
    await trafficApi.updateRule(rule.id, { enabled: !rule.enabled })
    await fetchRules()
    showSuccess(`Rule "${rule.name}" ${!rule.enabled ? 'enabled' : 'disabled'}`)
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function deleteRule(rule) {
  if (!confirm(`Delete rule "${rule.name}"?`)) return
  try {
    await trafficApi.deleteRule(rule.id)
    await fetchRules()
    await fetchTop()
    showSuccess(`Rule "${rule.name}" deleted`)
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

watch(period, () => fetchTop())

onMounted(() => {
  fetchTop()
  fetchRules()
  fetchClients()
})
</script>

<style scoped>
@media (max-width: 575.98px) {
  .btn-group.btn-group-sm {
    display: flex;
    flex-wrap: wrap;
    gap: .25rem;
  }
  .btn-group.btn-group-sm .btn {
    flex: 1;
    border-radius: .375rem !important;
  }
}
</style>
