<template>
  <div class="app-logs-page">
    <!-- Toolbar -->
    <div class="d-flex gap-2 mb-3 flex-wrap align-items-center mobile-filter-bar">
      <!-- Component tabs -->
      <div class="btn-group btn-group-sm">
        <button
          v-for="c in components"
          :key="c.value"
          class="btn"
          :class="component === c.value ? 'btn-primary' : 'btn-outline-secondary'"
          @click="setComponent(c.value)"
        >{{ c.label }}</button>
      </div>

      <!-- Error filter -->
      <div class="btn-group btn-group-sm">
        <button
          class="btn"
          :class="!errorsOnly ? 'btn-secondary' : 'btn-outline-secondary'"
          @click="setFilter(false)"
        >{{ $t('appLogs.filterAll') }}</button>
        <button
          class="btn"
          :class="errorsOnly ? 'btn-danger' : 'btn-outline-secondary'"
          @click="setFilter(true)"
        >{{ $t('appLogs.filterErrors') }}</button>
      </div>

      <div class="ms-auto d-flex gap-2 align-items-center mobile-toolbar__actions">
        <small v-if="entries.length" class="text-muted">{{ entries.length }} {{ $t('appLogs.entries') }}</small>
        <button class="btn btn-sm btn-outline-primary" @click="load" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i class="mdi mdi-refresh me-1"></i>Refresh
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && !entries.length" class="text-center text-muted py-5">
      <div class="spinner-border spinner-border-sm me-2"></div>{{ $t('appLogs.loading') }}
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && !entries.length" class="text-center text-muted py-5">
      <div style="font-size:2rem"><i class="mdi mdi-file-document-outline"></i></div>
      <div>{{ $t('appLogs.noEntries') }}</div>
      <small v-if="errorsOnly">{{ $t('appLogs.noErrorsFor', { component: component }) }}</small>
      <small v-else>{{ $t('appLogs.fileNotExist') }}</small>
    </div>

    <!-- Log table -->
    <div v-else class="log-table-wrapper">
      <table class="table table-sm table-hover log-table mb-0">
        <thead class="table-dark sticky-top">
          <tr>
            <th style="width:160px">{{ $t('appLogs.colTime') }}</th>
            <th style="width:85px">{{ $t('appLogs.colLevel') }}</th>
            <th style="width:70px">{{ $t('appLogs.colReqId') }}</th>
            <th style="width:60px">{{ $t('appLogs.colMethod') }}</th>
            <th style="width:220px">{{ $t('appLogs.colPath') }}</th>
            <th style="width:60px">{{ $t('appLogs.colStatus') }}</th>
            <th style="width:65px">{{ $t('appLogs.colDuration') }}</th>
            <th>{{ $t('appLogs.colMessage') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(e, idx) in entries" :key="idx">
            <tr
              :class="rowClass(e)"
              @click="toggle(idx)"
              style="cursor:pointer"
            >
              <td class="text-nowrap small text-muted">{{ fmtTime(e.timestamp) }}</td>
              <td>
                <span class="badge" :class="levelBadge(e.level)">{{ e.level }}</span>
              </td>
              <td class="small text-muted font-monospace">{{ e.request_id || '' }}</td>
              <td class="small">{{ e.method || '' }}</td>
              <td class="small text-truncate" style="max-width:220px" :title="e.path">{{ e.path || '' }}</td>
              <td class="small">
                <span v-if="e.status_code" :class="statusClass(e.status_code)">{{ e.status_code }}</span>
              </td>
              <td class="small text-muted">{{ e.duration_ms != null ? e.duration_ms : '' }}</td>
              <td class="small">
                <span class="message-text">{{ e.message }}</span>
                <span v-if="e.error" class="ms-1 badge bg-danger-subtle text-danger-emphasis">ERR</span>
              </td>
            </tr>
            <!-- Expandable error row -->
            <tr v-if="expanded.has(idx) && e.error" :key="'err-' + idx" class="table-danger">
              <td colspan="8">
                <pre class="small mb-0 p-2 bg-danger-subtle text-danger-emphasis rounded" style="white-space:pre-wrap;word-break:break-all;">{{ e.error }}</pre>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Error footer -->
    <div v-if="loadError" class="alert alert-danger mt-3 py-2 small">{{ loadError }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { systemApi } from '../api'

const { t } = useI18n()

const components = computed(() => [
  { value: 'api',    label: t('appLogs.tabApi') },
  { value: 'worker', label: t('appLogs.tabWorker') },
  { value: 'agent',  label: t('appLogs.tabAgent') },
])

const component  = ref('api')
const errorsOnly = ref(false)
const entries    = ref([])
const loading    = ref(false)
const loadError  = ref('')
const expanded   = ref(new Set())

function setComponent(c) {
  component.value = c
  load()
}

function setFilter(v) {
  errorsOnly.value = v
  load()
}

function toggle(idx) {
  const s = new Set(expanded.value)
  s.has(idx) ? s.delete(idx) : s.add(idx)
  expanded.value = s
}

async function load() {
  loading.value  = true
  loadError.value = ''
  expanded.value  = new Set()
  try {
    const { data } = await systemApi.getAppLogs({
      component: component.value,
      lines: 100,
      errors_only: errorsOnly.value,
    })
    entries.value = (data.entries || []).slice().reverse()  // newest first
  } catch (err) {
    loadError.value = err?.response?.data?.detail || err.message || 'Failed to load logs'
    entries.value = []
  } finally {
    loading.value = false
  }
}

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z')
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    + ' ' + d.toLocaleDateString([], { month: '2-digit', day: '2-digit' })
}

function rowClass(e) {
  if (e.level === 'ERROR' || e.level === 'CRITICAL') return 'table-danger'
  if (e.level === 'WARNING') return 'table-warning'
  return ''
}

function levelBadge(level) {
  return {
    ERROR:    'bg-danger',
    CRITICAL: 'bg-danger',
    WARNING:  'bg-warning text-dark',
    INFO:     'bg-info text-dark',
    DEBUG:    'bg-secondary',
  }[level] || 'bg-secondary'
}

function statusClass(code) {
  if (code >= 500) return 'text-danger fw-bold'
  if (code >= 400) return 'text-warning fw-bold'
  return 'text-success'
}

onMounted(load)
</script>

<style scoped>
.log-table-wrapper {
  border: 1px solid var(--bs-border-color);
  border-radius: 0.375rem;
  overflow: auto;
  max-height: 75vh;
}
.log-table {
  font-size: 0.78rem;
}
.message-text {
  word-break: break-all;
}
</style>
