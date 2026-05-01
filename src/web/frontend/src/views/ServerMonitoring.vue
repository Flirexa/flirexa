<template>
  <div>
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
      <div>
        <h4 class="mb-0">{{ $t('serverMonitoring.title') }}</h4>
        <small class="text-muted" v-if="lastChecked">
          {{ $t('serverMonitoring.updated') }} {{ formatTime(lastChecked) }}
        </small>
      </div>
      <div class="d-flex gap-2 flex-wrap">
        <select v-model="filterStatus" class="form-select form-select-sm sm-filter-select">
          <option value="">{{ $t('serverMonitoring.allStatuses') }}</option>
          <option value="healthy">{{ $t('serverMonitoring.healthy') }}</option>
          <option value="warning">{{ $t('serverMonitoring.warning') }}</option>
          <option value="error">Error</option>
          <option value="offline">Offline</option>
        </select>
        <button class="btn btn-sm btn-outline-secondary" @click="toggleFull" :disabled="loadingAll">
          {{ fullMode ? $t('serverMonitoring.quick') : $t('serverMonitoring.full') }}
        </button>
        <button class="btn btn-sm btn-outline-primary" @click="refreshAll" :disabled="loadingAll">
          <span v-if="loadingAll" class="spinner-border spinner-border-sm me-1"></span>
          {{ $t('serverMonitoring.refreshAll') }}
        </button>
      </div>
    </div>

    <!-- Summary KPI -->
    <div class="row g-3 mb-4" v-if="summary">
      <div class="col-6 col-xl-3" v-for="(val, key) in summaryCards" :key="key">
        <div class="sm-kpi" :class="val.borderCls">
          <div class="sm-kpi__value" :class="val.cls">{{ val.count }}</div>
          <div class="sm-kpi__label">{{ val.label }}</div>
        </div>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loadingAll && !servers.length" class="row g-3">
      <div class="col-12 col-lg-6" v-for="i in 4" :key="i">
        <div class="card"><div class="card-body placeholder-glow">
          <span class="placeholder col-4 mb-2 d-block"></span>
          <span class="placeholder col-8"></span>
        </div></div>
      </div>
    </div>

    <!-- Server cards -->
    <div class="row g-3" v-if="filteredServers.length">
      <div class="col-12 col-lg-6" v-for="srv in filteredServers" :key="srv.server_id">
        <div class="sm-card" :class="'sm-card--' + srv.status">

          <!-- LEVEL 1: Name + Status -->
          <div class="sm-card__header">
            <div class="sm-card__name-block">
              <div class="sm-card__name">{{ srv.server_name }}</div>
              <div class="sm-card__meta">
                <span>{{ srv.connection_mode }}</span>
                <span v-if="srv.details?.server_type === 'amneziawg'" class="sm-card__tag sm-card__tag--awg">AWG</span>
                <span v-if="srv.latency_ms != null">{{ srv.latency_ms }} ms</span>
              </div>
            </div>
            <div class="d-flex align-items-center gap-2">
              <span v-if="srv.drift?.detected" class="sm-badge sm-badge--drift" :title="driftTooltip(srv.drift)">
                {{ $t('serverMonitoring.drifted') }}
              </span>
              <span class="sm-badge" :class="'sm-badge--' + srv.status">{{ srv.status }}</span>
            </div>
          </div>

          <!-- LEVEL 2: Status message -->
          <div class="sm-card__message" :class="srv.status === 'healthy' ? 'sm-card__message--ok' : ''">
            {{ srv.message || '—' }}
          </div>

          <!-- LEVEL 3: WireGuard metrics -->
          <div v-if="srv.wireguard" class="sm-card__metrics">
            <div class="sm-metric">
              <div class="sm-metric__value">{{ srv.wireguard.peers_total }}</div>
              <div class="sm-metric__label">{{ $t('serverMonitoring.peers') }}</div>
            </div>
            <div class="sm-metric">
              <div class="sm-metric__value sm-metric__value--ok">{{ srv.wireguard.peers_active }}</div>
              <div class="sm-metric__label">{{ $t('serverMonitoring.active3m') }}</div>
            </div>
            <div class="sm-metric">
              <div class="sm-metric__value sm-metric__value--info">{{ srv.wireguard.peers_recent }}</div>
              <div class="sm-metric__label">{{ $t('serverMonitoring.recent15m') }}</div>
            </div>
          </div>

          <!-- Traffic (inline, muted) -->
          <div v-if="srv.wireguard && (srv.wireguard.rx_bytes || srv.wireguard.tx_bytes)"
               class="sm-card__traffic">
            ↓ {{ formatBytes(srv.wireguard.rx_bytes) }}
            ↑ {{ formatBytes(srv.wireguard.tx_bytes) }}
          </div>

          <!-- System metrics bars -->
          <div v-if="srv.system && hasMetrics(srv.system)" class="sm-card__resources">
            <div v-for="[label, pct] in resourceBars(srv.system)" :key="label" class="sm-resource">
              <span class="sm-resource__label">{{ label }}</span>
              <div class="progress sm-resource__bar">
                <div class="progress-bar" :class="barClass(pct)" :style="{ width: pct + '%' }"></div>
              </div>
              <span class="sm-resource__pct">{{ pct }}%</span>
            </div>
            <div v-if="srv.system.uptime_seconds != null" class="sm-card__uptime">
              {{ $t('serverMonitoring.uptime') }}: {{ formatUptime(srv.system.uptime_seconds) }}
            </div>
          </div>

          <!-- Actions -->
          <div class="sm-card__actions">
            <button v-if="srv.drift?.detected"
                    class="sm-action-btn sm-action-btn--warning"
                    :disabled="reconciling[srv.server_id]"
                    @click="reconcileOne(srv.server_id)"
                    :title="$t('serverMonitoring.drifted')">
              <span v-if="reconciling[srv.server_id]" class="spinner-border spinner-border-sm"></span>
              <i v-else class="mdi mdi-wrench-outline"></i>
            </button>
            <button class="sm-action-btn"
                    @click="refreshOne(srv.server_id)" :disabled="refreshing[srv.server_id]">
              <span v-if="refreshing[srv.server_id]" class="spinner-border spinner-border-sm"></span>
              <i v-else class="mdi mdi-refresh"></i>
            </button>
            <button class="sm-action-btn"
                    @click="toggleEvents(srv.server_id)"
                    :class="{ 'sm-action-btn--active': expandedEvents[srv.server_id] }">
              <i class="mdi mdi-clipboard-text-outline"></i>
            </button>
          </div>

          <!-- Expandable event log -->
          <div v-if="expandedEvents[srv.server_id]" class="sm-card__events">
            <div v-if="serverEvents[srv.server_id]?.loading" class="text-muted small">{{ $t('common.loading') }}</div>
            <div v-else-if="!serverEvents[srv.server_id]?.events?.length"
                 class="text-muted small">{{ $t('serverMonitoring.noEvents') }}</div>
            <table v-else class="table table-sm mb-0 sm-events-table">
              <tbody>
                <tr v-for="e in serverEvents[srv.server_id].events" :key="e.id">
                  <td class="text-muted ps-0">{{ formatTime(e.timestamp) }}</td>
                  <td>
                    <span class="badge" :class="badgeClass(e.old_status)" style="font-size:.65rem">{{ e.old_status }}</span>
                    <span class="text-muted mx-1">→</span>
                    <span class="badge" :class="badgeClass(e.new_status)" style="font-size:.65rem">{{ e.new_status }}</span>
                  </td>
                  <td class="text-muted pe-0">{{ e.message }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Footer: checked time -->
          <div class="sm-card__footer">
            {{ $t('serverMonitoring.checked') }}: {{ formatTime(srv.checked_at) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-if="!loadingAll && !filteredServers.length && !error" class="text-center py-5 text-muted">
      <p>{{ filterStatus ? $t('serverMonitoring.noServersFilter') : $t('serverMonitoring.noServers') }}</p>
    </div>

    <div v-if="error" class="alert alert-danger mt-3">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { healthApi, serversApi } from '../api'
import { formatBytes, formatTime, formatUptime, formatDuration } from '../utils'

const { t } = useI18n()

const servers      = ref([])
const loadingAll   = ref(false)
const error        = ref(null)
const lastChecked  = ref(null)
const filterStatus = ref('')
const fullMode     = ref(false)
const refreshing   = reactive({})
const reconciling  = reactive({})
const expandedEvents  = reactive({})
const serverEvents    = reactive({})

// ─── Computed ────────────────────────────────────────────────────────────

const filteredServers = computed(() => {
  if (!filterStatus.value) return servers.value
  return servers.value.filter(s => s.status === filterStatus.value)
})

const summary = computed(() => {
  if (!servers.value.length) return null
  return {
    total:   servers.value.length,
    healthy: servers.value.filter(s => s.status === 'healthy').length,
    warning: servers.value.filter(s => s.status === 'warning').length,
    offline: servers.value.filter(s => ['offline','error'].includes(s.status)).length,
  }
})

const summaryCards = computed(() => {
  if (!summary.value) return {}
  return {
    total:   { count: summary.value.total,   label: t('serverMonitoring.total'),       cls: '',             borderCls: '' },
    healthy: { count: summary.value.healthy, label: t('serverMonitoring.healthy'),     cls: 'sm-kpi__value--ok',  borderCls: 'sm-kpi--ok' },
    warning: { count: summary.value.warning, label: t('serverMonitoring.warning'),     cls: summary.value.warning > 0 ? 'sm-kpi__value--warn' : '', borderCls: '' },
    offline: { count: summary.value.offline, label: t('serverMonitoring.offlineError'),cls: summary.value.offline > 0 ? 'sm-kpi__value--err' : '',  borderCls: '' },
  }
})

// ─── Helpers ─────────────────────────────────────────────────────────────

function badgeClass(s) {
  return { healthy: 'badge-online', warning: 'badge-warning',
           error: 'badge-offline', offline: 'badge-offline', unknown: 'badge-soft-secondary' }[s] || 'badge-soft-secondary'
}
function barClass(pct) { return pct >= 95 ? 'bg-danger' : pct >= 85 ? 'bg-warning' : 'bg-success' }

function driftTooltip(drift) {
  if (!drift?.detected) return ''
  const issues = drift.details?.issues?.join(', ') || 'unknown'
  return `DRIFTED — ${issues}`
}

function hasMetrics(sys) {
  return sys.cpu_percent != null || sys.memory_percent != null || sys.disk_percent != null
}
function resourceBars(sys) {
  const bars = []
  if (sys.cpu_percent != null)    bars.push(['CPU', sys.cpu_percent])
  if (sys.memory_percent != null) bars.push(['RAM', sys.memory_percent])
  if (sys.disk_percent != null)   bars.push(['Disk', sys.disk_percent])
  return bars
}

// ─── Events panel ─────────────────────────────────────────────────────────

async function toggleEvents(serverId) {
  if (expandedEvents[serverId]) {
    expandedEvents[serverId] = false
    return
  }
  expandedEvents[serverId] = true
  if (!serverEvents[serverId]) {
    serverEvents[serverId] = { loading: true, events: [] }
    try {
      const res = await healthApi.getServerHistory(serverId, 20)
      serverEvents[serverId] = { loading: false, events: res.data.events || [] }
    } catch {
      serverEvents[serverId] = { loading: false, events: [] }
    }
  }
}

// ─── Data loading ─────────────────────────────────────────────────────────

async function loadAll() {
  loadingAll.value = true
  error.value = null
  try {
    const res = await healthApi.getAllServersHealth(fullMode.value)
    servers.value = res.data.servers || []
    lastChecked.value = new Date().toISOString()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loadingAll.value = false
  }
}

async function refreshAll() {
  loadingAll.value = true
  error.value = null
  try {
    const list = await healthApi.getAllServersHealth(fullMode.value)
    const allIds = (list.data.servers || []).map(s => s.server_id)
    const refreshed = await Promise.all(
      allIds.map(id => healthApi.refreshServerHealth(id).then(r => r.data))
    )
    servers.value = refreshed
    lastChecked.value = new Date().toISOString()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loadingAll.value = false
  }
}

async function refreshOne(serverId) {
  refreshing[serverId] = true
  try {
    const res = await healthApi.refreshServerHealth(serverId)
    const idx = servers.value.findIndex(s => s.server_id === serverId)
    if (idx !== -1) servers.value[idx] = res.data
    if (expandedEvents[serverId]) {
      const ev = await healthApi.getServerHistory(serverId, 20)
      serverEvents[serverId] = { loading: false, events: ev.data.events || [] }
    }
  } catch (e) {
    console.error('Refresh failed:', e)
  } finally {
    refreshing[serverId] = false
  }
}

async function reconcileOne(serverId) {
  reconciling[serverId] = true
  try {
    await serversApi.reconcile(serverId)
    await refreshOne(serverId)
  } catch (e) {
    console.error('Reconcile failed:', e)
  } finally {
    reconciling[serverId] = false
  }
}

function toggleFull() { fullMode.value = !fullMode.value; loadAll() }

let pollTimer = null
onMounted(() => { loadAll(); pollTimer = setInterval(loadAll, 60000) })
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
/* ── Filter select ─────────────────────────────────────────── */
.sm-filter-select { width: auto; font-size: .82rem; }

/* ── KPI Summary Cards ─────────────────────────────────────── */
.sm-kpi {
  background: var(--vxy-card-bg);
  border-radius: var(--vxy-card-radius);
  box-shadow: var(--vxy-card-shadow);
  padding: 1rem 1.25rem;
  text-align: center;
  transition: box-shadow .2s;
}
.sm-kpi:hover { box-shadow: 0 6px 20px rgba(34,41,47,.12); }
.sm-kpi--ok { border-bottom: 3px solid var(--vxy-success); }
.sm-kpi__value { font-size: 1.75rem; font-weight: 700; line-height: 1.2; color: var(--vxy-heading); }
.sm-kpi__value--ok { color: var(--vxy-success); }
.sm-kpi__value--warn { color: var(--vxy-warning); }
.sm-kpi__value--err { color: var(--vxy-danger); }
.sm-kpi__label { font-size: .78rem; color: var(--vxy-muted); text-transform: uppercase; letter-spacing: .04em; font-weight: 600; margin-top: .15rem; }

/* ── Server Card ───────────────────────────────────────────── */
.sm-card {
  background: var(--vxy-card-bg);
  border-radius: var(--vxy-card-radius);
  box-shadow: var(--vxy-card-shadow);
  padding: 1.25rem;
  border-left: 4px solid var(--vxy-border);
  transition: box-shadow .2s, transform .15s;
  display: flex; flex-direction: column; gap: .5rem;
  height: 100%;
}
.sm-card:hover { box-shadow: 0 8px 28px rgba(34,41,47,.14); transform: translateY(-1px); }
.sm-card--healthy { border-left-color: var(--vxy-success); }
.sm-card--warning { border-left-color: var(--vxy-warning); }
.sm-card--error,
.sm-card--offline { border-left-color: var(--vxy-danger); }

/* Card header: name + status */
.sm-card__header { display: flex; justify-content: space-between; align-items: flex-start; gap: .75rem; }
.sm-card__name-block { min-width: 0; }
.sm-card__name { font-size: 1rem; font-weight: 600; color: var(--vxy-heading); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sm-card__meta { display: flex; align-items: center; gap: .5rem; font-size: .72rem; color: var(--vxy-muted); margin-top: .15rem; opacity: .7; }
.sm-card__tag { font-size: .65rem; padding: .1em .4em; border-radius: .2rem; font-weight: 600; }
.sm-card__tag--awg { background: var(--vxy-primary-light); color: var(--vxy-primary); }

/* Status badge */
.sm-badge {
  display: inline-block; padding: .3em .7em; border-radius: .35rem;
  font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
  white-space: nowrap;
}
.sm-badge--healthy { background: var(--vxy-success); color: #fff; }
.sm-badge--warning { background: var(--vxy-warning); color: #fff; }
.sm-badge--error,
.sm-badge--offline { background: var(--vxy-danger); color: #fff; }
.sm-badge--unknown { background: var(--vxy-border); color: var(--vxy-muted); }
.sm-badge--drift { background: rgba(255,159,67,.15); color: var(--vxy-warning); font-size: .7rem; }

/* Status message */
.sm-card__message { font-size: .82rem; color: var(--vxy-muted); }
.sm-card__message--ok { color: var(--vxy-success); }

/* Metrics row */
.sm-card__metrics {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: .25rem; text-align: center;
  background: rgba(125,125,125,.04); border-radius: .375rem;
  padding: .5rem;
}
.sm-metric__value { font-size: 1.15rem; font-weight: 700; color: var(--vxy-heading); line-height: 1.2; }
.sm-metric__value--ok { color: var(--vxy-success); }
.sm-metric__value--info { color: var(--vxy-info, #0dcaf0); }
.sm-metric__label { font-size: .68rem; color: var(--vxy-muted); text-transform: uppercase; letter-spacing: .03em; }

/* Traffic */
.sm-card__traffic { font-size: .72rem; color: var(--vxy-muted); opacity: .65; text-align: center; }

/* Resource bars */
.sm-card__resources { display: flex; flex-direction: column; gap: .3rem; }
.sm-resource { display: flex; align-items: center; gap: .5rem; }
.sm-resource__label { font-size: .72rem; color: var(--vxy-muted); width: 32px; flex-shrink: 0; }
.sm-resource__bar { flex: 1; height: 4px; border-radius: 2px; }
.sm-resource__pct { font-size: .72rem; color: var(--vxy-muted); width: 32px; text-align: right; flex-shrink: 0; }

.sm-card__uptime { font-size: .7rem; color: var(--vxy-muted); opacity: .6; }

/* Action buttons */
.sm-card__actions { display: flex; gap: .35rem; margin-top: auto; padding-top: .25rem; }
.sm-action-btn {
  width: 32px; height: 32px; border-radius: .375rem;
  border: 1px solid var(--vxy-border); background: transparent;
  display: flex; align-items: center; justify-content: center;
  font-size: .8rem; cursor: pointer; color: var(--vxy-muted);
  transition: background .15s, color .15s, border-color .15s;
}
.sm-action-btn:hover { background: var(--vxy-hover-bg); color: var(--vxy-text); border-color: var(--vxy-text); }
.sm-action-btn--active { background: var(--vxy-primary-light); color: var(--vxy-primary); border-color: var(--vxy-primary); }
.sm-action-btn--warning { color: var(--vxy-warning); border-color: var(--vxy-warning); }
.sm-action-btn--warning:hover { background: rgba(255,159,67,.1); }
.sm-action-btn:disabled { opacity: .5; cursor: default; }

/* Events */
.sm-card__events { border-top: 1px solid rgba(125,125,125,.1); padding-top: .5rem; }
.sm-events-table { font-size: .75rem; }
.sm-events-table td { padding: .25rem .35rem; white-space: nowrap; }
.sm-events-table td:last-child { white-space: normal; }

/* Footer */
.sm-card__footer { font-size: .68rem; color: var(--vxy-muted); opacity: .5; }

/* ── Mobile ────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .sm-kpi { padding: .75rem; }
  .sm-kpi__value { font-size: 1.35rem; }
  .sm-card { padding: 1rem; }
  .sm-card__header { flex-wrap: wrap; }
  .sm-card__metrics { grid-template-columns: repeat(3, 1fr); gap: .15rem; }
  .sm-metric__value { font-size: 1rem; }
  .sm-card__actions { flex-wrap: wrap; }
  .sm-action-btn { width: 38px; height: 38px; }
}
@media (max-width: 576px) {
  .sm-kpi__value { font-size: 1.15rem; }
  .sm-card__name { font-size: .9rem; }
}
</style>
