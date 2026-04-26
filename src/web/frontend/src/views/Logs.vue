<template>
  <div class="logs-page">
    <!-- Filters -->
    <div class="d-flex gap-2 mb-4 flex-wrap mobile-filter-bar">
      <select v-model="filterAction" class="form-select form-select-sm filter-select-wide">
        <option value="">{{ $t('logs.allActions') }}</option>
        <option v-for="action in actionTypes" :key="action" :value="action">{{ action }}</option>
      </select>
      <input
        v-model="filterTarget"
        type="text"
        class="form-control form-control-sm filter-input"
        :placeholder="$t('logs.filterTarget')"
      />
      <input
        v-model="filterUser"
        type="text"
        class="form-control form-control-sm filter-input"
        :placeholder="$t('logs.filterUser')"
      />
      <button class="btn btn-outline-primary btn-sm" @click="loadLogs">{{ $t('nav.refresh') }}</button>
    </div>

    <!-- Logs Table -->
    <div class="table-card">
      <div class="table-responsive">
        <table class="table table-hover table-sm">
          <thead>
            <tr>
              <th>{{ $t('logs.time') }}</th>
              <th>{{ $t('logs.action') }}</th>
              <th class="d-none d-md-table-cell">{{ $t('logs.user') }}</th>
              <th class="d-none d-sm-table-cell">{{ $t('logs.target') }}</th>
              <th class="d-none d-md-table-cell">{{ $t('logs.details') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>
                <small>{{ formatDate(log.timestamp) }}</small>
              </td>
              <td>
                <span class="badge badge-soft-secondary">{{ log.action }}</span>
              </td>
              <td class="d-none d-md-table-cell">{{ log.user_id || 'system' }}</td>
              <td class="d-none d-sm-table-cell fw-medium">{{ log.target || '-' }}</td>
              <td class="d-none d-md-table-cell">
                <small class="text-muted">{{ truncate(log.details, 80) }}</small>
              </td>
            </tr>
            <tr v-if="logs.length === 0">
              <td colspan="5" class="text-center text-muted py-4">
                {{ loading ? $t('common.loading') : $t('logs.noLogs') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    <div class="d-flex justify-content-between align-items-center mt-3 mobile-pagination" v-if="logs.length > 0">
      <small class="text-muted">{{ $t('logs.showingEntries', { count: logs.length, page: page }) }}</small>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="page--; loadLogs()">
          &laquo; {{ $t('common.prev') }}
        </button>
        <button class="btn btn-outline-secondary" :disabled="logs.length < pageSize" @click="page++; loadLogs()">
          {{ $t('common.next') }} &raquo;
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { systemApi } from '../api'

const logs = ref([])
const loading = ref(false)
const filterAction = ref('')
const filterTarget = ref('')
const filterUser = ref('')
const page = ref(1)
const pageSize = 50

const actionTypes = [
  'client_created',
  'client_deleted',
  'client_enabled',
  'client_disabled',
  'traffic_limit_set',
  'bandwidth_set',
  'expiry_set',
  'server_started',
  'server_stopped',
]

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

function truncate(str, len) {
  if (!str) return '-'
  return str.length > len ? str.slice(0, len) + '...' : str
}

async function loadLogs() {
  loading.value = true
  try {
    const params = {
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    }
    if (filterAction.value) params.action = filterAction.value
    if (filterTarget.value) params.target = filterTarget.value
    if (filterUser.value) params.user = filterUser.value

    const { data } = await systemApi.getLogs(params)
    logs.value = data
  } catch (err) {
    console.error('Error loading logs:', err)
  } finally {
    loading.value = false
  }
}

onMounted(loadLogs)
</script>
