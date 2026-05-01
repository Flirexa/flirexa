<template>
  <div class="sh-page">
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
      <div>
        <h4 class="mb-0">{{ $t('systemHealth.title') }}</h4>
        <small class="text-muted" v-if="checkedAt">
          {{ health?.mode === 'quick' ? $t('systemHealth.quickCheck') : $t('systemHealth.fullCheck') }} ·
          {{ formatTime(checkedAt) }}
        </small>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" @click="toggleFull" :disabled="loading">
          {{ fullMode ? $t('systemHealth.switchQuick') : $t('systemHealth.switchFull') }}
        </button>
        <button class="btn btn-sm btn-outline-primary" @click="refresh" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          {{ $t('systemHealth.refresh') }}
        </button>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading && !health" class="row g-3">
      <div class="col-12 col-md-6 col-xl-4" v-for="i in 6" :key="i">
        <div class="card"><div class="card-body placeholder-glow">
          <span class="placeholder col-5 mb-2 d-block"></span>
          <span class="placeholder col-8"></span>
        </div></div>
      </div>
    </div>

    <template v-if="health">
      <!-- Overall status banner (compact) -->
      <div class="sh-banner" :class="'sh-banner--' + health.status">
        <div class="sh-banner__left">
          <span class="sh-banner__icon"><i :class="'mdi mdi-' + overallIcon"></i></span>
          <div>
            <div class="sh-banner__title">{{ overallLabel }}</div>
            <div class="sh-banner__summary">
              {{ healthyCount }}/{{ totalCount }} {{ $t('systemHealth.componentsOk') }}
              <span class="sh-banner__mode">
                {{ health.mode === 'quick' ? $t('systemHealth.quickCheck') : $t('systemHealth.fullCheck') }}
              </span>
            </div>
          </div>
        </div>
        <div class="d-flex align-items-center gap-2">
          <span v-if="activeIssues.length" class="badge bg-danger">
            {{ activeIssues.length }} {{ $t('systemHealth.issues') }}
          </span>
          <span v-if="health.mode === 'quick'" class="sh-banner__hint" @click="toggleFull">
            {{ $t('systemHealth.fullAvailable') }}
          </span>
        </div>
      </div>

      <!-- Active issues -->
      <div v-if="activeIssues.length" class="sh-issues-card mb-4">
        <div class="sh-issues-card__header">
          {{ $t('systemHealth.activeIssues') }} ({{ activeIssues.length }})
        </div>
        <div v-for="issue in activeIssues" :key="issue.target_id" class="sh-issues-card__row">
          <div>
            <span class="fw-semibold small">{{ issue.target_name }}</span>
            <span class="sh-detail-text ms-2">
              {{ issue.target_type === 'server' ? 'server' : 'system' }}
            </span>
          </div>
          <div class="d-flex align-items-center gap-2">
            <span class="sh-detail-text">{{ formatDuration(issue.duration_seconds) }}</span>
            <span class="badge" :class="badgeClass(issue.current_status)" style="font-size:.7rem">
              {{ issue.current_status }}
            </span>
          </div>
        </div>
      </div>

      <!-- Recent recoveries -->
      <div v-if="recentRecoveries.length" class="sh-recoveries-card mb-4">
        <div class="sh-recoveries-card__header">
          {{ $t('systemHealth.recentlyRecovered') }}
        </div>
        <div v-for="r in recentRecoveries" :key="r.timestamp + r.target_id" class="sh-recoveries-card__row">
          <div>
            <span class="fw-semibold small">{{ r.target_name }}</span>
            <span class="sh-detail-text ms-2">{{ r.old_status }} → {{ $t('systemHealth.healthy') }}</span>
          </div>
          <span class="sh-detail-text">{{ formatTime(r.timestamp) }}</span>
        </div>
      </div>

      <!-- Component cards -->
      <div class="row g-3 mb-4">
        <div class="col-12 col-md-6 col-xl-4"
             v-for="comp in health.components" :key="comp.name">
          <div class="sh-comp" :class="'sh-comp--' + comp.status">

            <!-- Level 1: Name + Status -->
            <div class="sh-comp__header">
              <div class="sh-comp__title">
                <span class="sh-comp__icon"><i :class="'mdi mdi-' + compIcon(comp.name)"></i></span>
                {{ compLabel(comp.name) }}
              </div>
              <span class="sh-status" :class="'sh-status--' + comp.status">
                {{ comp.status }}
              </span>
            </div>

            <!-- Level 2: Message -->
            <div class="sh-comp__message">{{ comp.message }}</div>

            <!-- Level 2.5: Latency (if present) -->
            <div v-if="comp.latency_ms != null" class="sh-comp__latency">
              {{ comp.latency_ms }} ms
            </div>

            <!-- Level 3: Resource bar (disk/memory/cpu) -->
            <div v-if="hasProgressBar(comp.name, comp.details)" class="sh-comp__bar-section">
              <div class="sh-comp__bar-row">
                <div class="sh-comp__pct">{{ comp.details.percent }}%</div>
                <div class="progress sh-comp__bar">
                  <div class="progress-bar" :class="barClass(comp.details.percent)"
                       :style="{ width: comp.details.percent + '%' }"></div>
                </div>
              </div>
              <div class="sh-comp__bar-detail" v-if="usageText(comp)">
                {{ usageText(comp) }}
              </div>
            </div>

            <!-- Level 3: Detail metrics (as plain text, not pills) -->
            <div v-if="visibleDetails(comp).length" class="sh-comp__details">
              <div v-for="[k,v] in visibleDetails(comp)" :key="k" class="sh-comp__detail-row">
                <span class="sh-comp__detail-key">{{ formatKey(k) }}</span>
                <span class="sh-comp__detail-val">{{ formatDetailVal(k, v) }}</span>
              </div>
            </div>

            <!-- Status history -->
            <div v-if="comp.history?.last_status_change" class="sh-comp__since">
              {{ $t('systemHealth.since') || 'Since' }} {{ formatTime(comp.history.last_status_change) }}
              <span v-if="comp.history.duration_seconds != null">
                ({{ formatDuration(comp.history.duration_seconds) }})
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Event log -->
      <div class="sh-log">
        <div class="sh-log__header">
          <span class="fw-semibold small">{{ $t('systemHealth.eventLog') }}</span>
          <select v-model="eventFilter.severity" class="form-select form-select-sm sh-log__filter">
            <option value="">{{ $t('systemHealth.allSeverity') }}</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>
        <div class="sh-log__body">
          <div v-if="filteredEvents.length === 0" class="sh-log__empty">
            {{ $t('systemHealth.noEvents') }}
          </div>
          <table v-else class="table table-sm table-hover mb-0 sh-log__table">
            <tbody>
              <tr v-for="e in filteredEvents" :key="e.id">
                <td class="text-muted ps-3 sh-log__time">{{ formatTime(e.timestamp) }}</td>
                <td>
                  <span class="badge" :class="severityBadge(e.severity)" style="font-size:.68rem">
                    {{ e.severity }}
                  </span>
                </td>
                <td class="fw-semibold">{{ e.target_name }}</td>
                <td>
                  <span class="badge me-1" :class="badgeClass(e.old_status)" style="font-size:.65rem">{{ e.old_status }}</span>
                  <span class="text-muted">→</span>
                  <span class="badge ms-1" :class="badgeClass(e.new_status)" style="font-size:.65rem">{{ e.new_status }}</span>
                </td>
                <td class="text-muted pe-3">{{ e.message }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <div v-if="error && !health" class="alert alert-danger mt-3">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { healthApi } from '../api'
import { formatTime, formatDuration } from '../utils'

const { t } = useI18n()

const health       = ref(null)
const events       = ref([])
const activeIssues = ref([])
const recentRecoveries = ref([])
const loading      = ref(false)
const error        = ref(null)
const checkedAt    = ref(null)
const fullMode     = ref(false)
const eventFilter  = reactive({ severity: '' })

let pollTimer = null

// ─── Computed ────────────────────────────────────────────────────────────

const healthyCount = computed(() => {
  if (!health.value?.components) return 0
  return health.value.components.filter(c => c.status === 'healthy').length
})
const totalCount = computed(() => health.value?.components?.length || 0)

const overallIcon = computed(() => {
  return {
    healthy: 'check-circle',
    warning: 'alert',
    error: 'close-circle',
    offline: 'circle-off-outline',
    unknown: 'help-circle',
  }[health.value?.status] || 'help-circle'
})
const overallLabel = computed(() => {
  const m = {
    healthy: t('systemHealth.statusOperational'),
    warning: t('systemHealth.statusDegraded'),
    error: t('systemHealth.statusFailure'),
    offline: t('systemHealth.statusOffline'),
    unknown: t('systemHealth.statusUnknown'),
  }
  return m[health.value?.status] || t('systemHealth.statusUnknown')
})
const filteredEvents = computed(() => {
  if (!eventFilter.severity) return events.value
  return events.value.filter(e => e.severity === eventFilter.severity)
})

// ─── Helpers ─────────────────────────────────────────────────────────────

function badgeClass(status) {
  return { healthy: 'bg-success', warning: 'bg-warning text-dark',
           error: 'bg-danger', offline: 'bg-danger', unknown: 'bg-secondary' }[status] || 'bg-secondary'
}
function barClass(pct) {
  return pct >= 95 ? 'bg-danger' : pct >= 80 ? 'bg-warning' : 'bg-success'
}
function severityBadge(sev) {
  return { critical: 'bg-danger', warning: 'bg-warning text-dark', info: 'bg-secondary' }[sev] || 'bg-secondary'
}
function compIcon(name) {
  return {
    database:         'database',
    api_process:      'cog',
    worker:           'wrench',
    license_server:   'key',
    wireguard_local:  'web',
    telegram_bots:    'robot',
    payment_provider: 'credit-card',
    disk:             'harddisk',
    memory:           'memory',
    cpu:              'chip',
  }[name] || 'square-outline'
}
function compLabel(name) {
  return { database: 'Database', api_process: 'API Process', worker: 'Background Worker',
           license_server: 'License Server', wireguard_local: 'WireGuard',
           telegram_bots: 'Telegram Bots', payment_provider: 'Payment Provider',
           disk: 'Disk', memory: 'Memory', cpu: 'CPU' }[name] || name
}
function hasProgressBar(name, details) {
  return ['disk', 'memory', 'cpu'].includes(name) && details?.percent != null
}
function visibleDetails(comp) {
  if (!comp.details) return []
  return Object.entries(comp.details).filter(([k, v]) => {
    if (k === 'percent') return false
    if (k === 'used_display' || k === 'total_display') return false
    if (typeof v === 'object' || typeof v === 'boolean') return false
    return true
  })
}
function formatKey(k) {
  return k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    .replace(/ Gb$/, '').replace(/ Mb$/, '')
    .replace(/^Pid$/, 'PID').replace(/^Ram /, 'RAM ')
    .replace(/^Memory /, 'RAM ').replace(/^Rss Mb$/, 'RAM')
    .replace(/^Load Avg /, 'Load ')
}
function formatDetailVal(k, v) {
  if (typeof v === 'number') {
    if (k.endsWith('_gb')) return v.toFixed(1) + ' GB'
    if (k.endsWith('_mb') || k === 'rss_mb') return v.toFixed(1) + ' MB'
  }
  return v
}
function usageText(comp) {
  const d = comp.details
  if (!d) return ''
  if (d.used_display && d.total_display) return `${d.used_display} / ${d.total_display}`
  if (d.used_gb != null && d.total_gb != null) return `${d.used_gb.toFixed(1)} / ${d.total_gb.toFixed(1)} GB`
  if (d.used_mb != null && d.total_mb != null) return `${d.used_mb.toFixed(0)} / ${d.total_mb.toFixed(0)} MB`
  return ''
}

// ─── Data loading ─────────────────────────────────────────────────────────

async function load(force = false) {
  loading.value = true
  error.value = null
  try {
    const [healthRes, issuesRes, eventsRes] = await Promise.all([
      force
        ? healthApi.refreshSystemHealth()
        : healthApi.getSystemHealth(fullMode.value),
      healthApi.getIssues(),
      healthApi.getEvents({ limit: 100 }),
    ])
    health.value = healthRes.data
    checkedAt.value = healthRes.data.checked_at
    activeIssues.value = issuesRes.data.active_issues || []
    recentRecoveries.value = issuesRes.data.recent_recoveries || []
    events.value = eventsRes.data.events || []
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function refresh() { load(true) }
function toggleFull() { fullMode.value = !fullMode.value; load(false) }

onMounted(() => {
  load()
  pollTimer = setInterval(() => load(), 60000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
/* ── Overall Banner (compact) ──────────────────────────────── */
.sh-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: .75rem 1.25rem; border-radius: var(--vxy-card-radius, .5rem);
  margin-bottom: 1.25rem;
}
.sh-banner__left { display: flex; align-items: center; gap: .75rem; }
.sh-banner__icon { font-size: 1.3rem; }
.sh-banner__title { font-weight: 600; font-size: .9rem; }
.sh-banner__summary { font-size: .78rem; opacity: .8; display: flex; align-items: center; gap: .4rem; flex-wrap: wrap; }
.sh-banner__mode {
  font-size: .68rem; opacity: .6; padding: .1em .4em;
  border: 1px solid currentColor; border-radius: .2rem;
}
.sh-banner__hint {
  font-size: .72rem; opacity: .7; cursor: pointer;
  text-decoration: underline; white-space: nowrap;
}
.sh-banner__hint:hover { opacity: 1; }
.sh-banner--healthy { background: var(--vxy-success-light); color: var(--vxy-success); }
.sh-banner--warning { background: var(--vxy-warning-light); color: var(--vxy-warning); }
.sh-banner--error,
.sh-banner--offline { background: var(--vxy-danger-light); color: var(--vxy-danger); }
.sh-banner--unknown { background: rgba(108,117,125,.1); color: #6c757d; }

/* ── Issues / Recoveries cards ─────────────────────────────── */
.sh-issues-card, .sh-recoveries-card {
  border-radius: var(--vxy-card-radius, .5rem);
  overflow: hidden; box-shadow: var(--vxy-card-shadow);
}
.sh-issues-card__header {
  padding: .5rem 1rem; font-size: .8rem; font-weight: 600;
  background: var(--vxy-danger-light); color: var(--vxy-danger);
}
.sh-recoveries-card__header {
  padding: .5rem 1rem; font-size: .8rem; font-weight: 600;
  background: var(--vxy-success-light); color: var(--vxy-success);
}
.sh-issues-card__row, .sh-recoveries-card__row {
  display: flex; justify-content: space-between; align-items: center;
  padding: .45rem 1rem; border-bottom: 1px solid rgba(125,125,125,.08);
  background: var(--vxy-card-bg);
}
.sh-issues-card__row:last-child, .sh-recoveries-card__row:last-child { border-bottom: none; }

/* ── Component Cards ───────────────────────────────────────── */
.sh-comp {
  background: var(--vxy-card-bg);
  border-radius: var(--vxy-card-radius, .5rem);
  box-shadow: var(--vxy-card-shadow);
  padding: 1rem 1.25rem;
  border-left: 4px solid var(--vxy-border);
  transition: box-shadow .15s;
  height: 100%;
  display: flex; flex-direction: column; gap: .4rem;
}
.sh-comp:hover { box-shadow: 0 6px 20px rgba(34,41,47,.12); }
.sh-comp--healthy { border-left-color: var(--vxy-success); }
.sh-comp--warning { border-left-color: var(--vxy-warning); }
.sh-comp--error, .sh-comp--offline { border-left-color: var(--vxy-danger); }

.sh-comp__header { display: flex; justify-content: space-between; align-items: center; }
.sh-comp__title { font-weight: 600; font-size: .9rem; color: var(--vxy-heading); }
.sh-comp__icon { margin-right: .35rem; }

/* Status badge — small, quiet when healthy */
.sh-status {
  font-size: .68rem; font-weight: 600; text-transform: uppercase;
  padding: .2em .5em; border-radius: .25rem;
  letter-spacing: .02em;
}
.sh-status--healthy { background: var(--vxy-success-light); color: var(--vxy-success); }
.sh-status--warning { background: var(--vxy-warning); color: #fff; }
.sh-status--error, .sh-status--offline { background: var(--vxy-danger); color: #fff; }
.sh-status--unknown { background: var(--vxy-border); color: var(--vxy-muted); }

.sh-comp__message { font-size: .8rem; color: var(--vxy-muted); }
.sh-comp__latency { font-size: .75rem; color: var(--vxy-muted); opacity: .7; }

/* Progress bar section */
.sh-comp__bar-section { margin-top: .15rem; }
.sh-comp__bar-row { display: flex; align-items: center; gap: .5rem; }
.sh-comp__pct { font-size: 1.1rem; font-weight: 700; color: var(--vxy-heading); min-width: 3ch; }
.sh-comp__bar { flex: 1; height: 6px; border-radius: 3px; }
.sh-comp__bar-detail { font-size: .72rem; color: var(--vxy-muted); opacity: .7; margin-top: .1rem; }

/* Detail metrics (plain text rows, not pills) */
.sh-comp__details { display: flex; flex-direction: column; gap: .1rem; margin-top: .1rem; }
.sh-comp__detail-row { display: flex; justify-content: space-between; align-items: center; }
.sh-comp__detail-key { font-size: .72rem; color: var(--vxy-muted); }
.sh-comp__detail-val { font-size: .78rem; color: var(--vxy-text); font-weight: 500; }

.sh-comp__since { font-size: .68rem; color: var(--vxy-muted); opacity: .5; margin-top: auto; }

/* ── Muted detail text ─────────────────────────────────────── */
.sh-detail-text { font-size: .75rem; color: var(--vxy-muted); }

/* ── Event Log ─────────────────────────────────────────────── */
.sh-log {
  background: var(--vxy-card-bg);
  border-radius: var(--vxy-card-radius, .5rem);
  box-shadow: var(--vxy-card-shadow);
  overflow: hidden;
}
.sh-log__header {
  display: flex; justify-content: space-between; align-items: center;
  padding: .6rem 1rem; border-bottom: 1px solid rgba(125,125,125,.1);
}
.sh-log__filter { width: auto; font-size: .78rem; }
.sh-log__body { max-height: 340px; overflow-y: auto; }
.sh-log__empty { text-align: center; padding: 1.5rem 1rem; color: var(--vxy-muted); font-size: .85rem; }
.sh-log__table { font-size: .8rem; }
.sh-log__table td { vertical-align: middle; }
.sh-log__time { white-space: nowrap; width: 80px; }

/* ── Mobile ────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .sh-banner { padding: .6rem 1rem; }
  .sh-banner__icon { font-size: 1.1rem; }
  .sh-comp { padding: .875rem 1rem; }
  .sh-comp__pct { font-size: 1rem; }
  .sh-log__table { font-size: .75rem; }
}
@media (max-width: 576px) {
  .sh-comp__title { font-size: .85rem; }
}
</style>
