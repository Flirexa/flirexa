<!-- Server monitoring — reproduced 1:1 from the designer's markup (his KPI cards,
     filter select + quick/full segmented toggle, refresh-all button, and per-server
     cards: status pill, drift banner, peers/uptime, CPU/RAM/Disk meter bars,
     refresh + events buttons, expandable events history).
     Wired to healthApi.getAllServersHealth + refreshServerHealth + serversApi.reconcile. -->
<template>
  <div class="d2-mon">
    <!-- KPIs -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px">
      <div v-for="k in monKpis" :key="k.label" style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:15px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ k.label }}</div>
        <div :style="{ fontSize:'24px', fontWeight:680, letterSpacing:'-.02em', marginTop:'7px', color:k.color }">{{ k.value }}</div>
      </div>
    </div>

    <!-- filter + mode toggle + refresh all -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <select :value="monFilter" @change="onMonFilter" style="height:34px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;padding:0 9px;font:inherit;font-size:12.5px;outline:none;cursor:pointer">
        <option value="all">{{ tr('serverMonitoring.filterAll') || 'All' }}</option>
        <option value="healthy">{{ tr('serverMonitoring.filterHealthy') || 'Healthy' }}</option>
        <option value="degraded">{{ tr('serverMonitoring.filterDegraded') || 'Degraded' }}</option>
        <option value="down">{{ tr('serverMonitoring.filterDown') || 'Down' }}</option>
      </select>
      <div style="display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px">
        <button @click="toggleMonFull" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'11.5px', fontWeight:monQuickWeight, cursor:'pointer', background:monQuickBg, color:monQuickColor }">{{ tr('serverMonitoring.quick') || 'Quick' }}</button>
        <button @click="toggleMonFull" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'11.5px', fontWeight:monFullWeight, cursor:'pointer', background:monFullBg, color:monFullColor }">{{ tr('serverMonitoring.full') || 'Full' }}</button>
      </div>
      <button @click="refreshAll" class="hov-panel2" style="margin-left:auto;display:flex;align-items:center;gap:7px;height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0115-6.7L21 8"></path><path d="M21 3v5h-5"></path><path d="M21 12a9 9 0 01-15 6.7L3 16"></path><path d="M3 21v-5h5"></path></svg>{{ tr('serverMonitoring.refreshAll') || 'Refresh all' }}
      </button>
    </div>

    <div v-if="loading && !rows.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
    <div v-else-if="!monServers.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('serverMonitoring.noServers') || 'No servers monitored' }}</div>

    <!-- server cards -->
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;align-items:start">
      <div v-for="s in monServers" :key="s.id" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:14px">
          <div style="flex:1;min-width:0">
            <div style="font-weight:620;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ s.name }}</div>
            <div style="font-size:11.5px;color:var(--text-3)">{{ s.region }}</div>
          </div>
          <span :style="{ display:'inline-flex', alignItems:'center', gap:'5px', fontSize:'11px', fontWeight:600, padding:'3px 9px', borderRadius:'20px', color:s.statusColor, background:s.statusBg, flex:'none' }"><span :style="{ width:'6px', height:'6px', borderRadius:'50%', background:s.statusColor }"></span>{{ s.statusLabel }}</span>
        </div>

        <div v-if="s.drift" style="display:flex;align-items:center;gap:8px;padding:7px 11px;border:1px solid var(--amber-soft);background:var(--amber-soft);border-radius:9px;margin-bottom:12px">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8"><path d="M12 9v4M12 17h.01M10.3 3.9l-8 14A2 2 0 004 21h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z"></path></svg>
          <span style="font-size:12px;color:var(--amber);font-weight:550;flex:1" :title="s.driftTip">{{ tr('serverMonitoring.driftDetected') || 'Configuration drift detected' }}</span>
          <button @click="reconcile(s.id)" style="border:none;background:transparent;color:var(--amber);font:inherit;font-size:12px;font-weight:600;cursor:pointer">{{ tr('serverMonitoring.reconcile') || 'Reconcile' }}</button>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:9px 14px;margin-bottom:12px">
          <div><div style="font-size:10.5px;color:var(--text-3)">{{ tr('serverMonitoring.peers') || 'Peers' }}</div><div style="font-size:14px;font-weight:650;font-family:'JetBrains Mono',monospace">{{ s.peers }}</div></div>
          <div><div style="font-size:10.5px;color:var(--text-3)">{{ tr('serverMonitoring.uptime') || 'Uptime' }}</div><div style="font-size:14px;font-weight:650;font-family:'JetBrains Mono',monospace">{{ s.uptime }}</div></div>
        </div>

        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px">
          <div v-for="(m, i) in s.meters" :key="i">
            <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span style="color:var(--text-3)">{{ m.label }}</span><span style="font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ m.value }}</span></div>
            <div style="height:5px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:m.color, width:m.value }"></div></div>
          </div>
        </div>

        <div style="display:flex;gap:7px">
          <button @click="refreshOne(s.id)" class="hov-panel2" style="height:32px;padding:0 11px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="display:block"><path d="M3 12a9 9 0 0115-6.7L21 8"></path><path d="M21 3v5h-5"></path><path d="M21 12a9 9 0 01-15 6.7L3 16"></path><path d="M3 21v-5h5"></path></svg>
          </button>
          <button @click="toggleEvents(s.id)" class="hov-panel2" style="flex:1;height:32px;padding:0 11px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">{{ tr('serverMonitoring.events') || 'Events' }}</button>
        </div>

        <div v-if="openEvents[s.id]" style="margin-top:11px;border-top:1px solid var(--border);padding-top:11px;display:flex;flex-direction:column;gap:8px">
          <div v-for="(h, i) in s.history" :key="i" style="display:flex;gap:10px;font-size:12px"><span style="color:var(--text-3);font-family:'JetBrains Mono',monospace;flex:none">{{ h.ts }}</span><span style="color:var(--text-2)">{{ h.text }}</span></div>
          <div v-if="!s.history.length" style="font-size:12px;color:var(--text-3)">{{ tr('common.noData') || 'No events' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { healthApi, serversApi, silentPoll } from '../../api'
import { formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const rows = ref([])
const loading = ref(false)
const busy = reactive({})
const monFilter = ref('all')
const monFull = ref(false)
const openEvents = reactive({})
let timer = null

async function loadAll(full = monFull.value) {
  loading.value = true
  try { const res = await healthApi.getAllServersHealth(full); const d = res.data; rows.value = d.servers || d.items || (Array.isArray(d) ? d : []) }
  catch (e) { console.error(e) } finally { loading.value = false }
}
async function refreshAll() {
  loading.value = true
  try {
    const res = await healthApi.getAllServersHealth(monFull.value); const d = res.data; const list = d.servers || d.items || (Array.isArray(d) ? d : [])
    await Promise.allSettled(list.map(s => healthApi.refreshServerHealth(s.server_id)))
    await loadAll()
  } catch (e) { console.error(e) } finally { loading.value = false }
}
async function refreshOne(id) { busy[id] = true; try { await healthApi.refreshServerHealth(id); await loadAll() } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { busy[id] = false } }
async function reconcile(id) { if (!await d2confirm(tr('serverMonitoring.reconcileConfirm') || 'Reconcile this server to fix drift?')) return; try { await serversApi.reconcile(id); await refreshOne(id) } catch (e) { alert(e.response?.data?.detail || 'Error') } }
function onMonFilter(e) { monFilter.value = e.target.value }
function toggleMonFull() { monFull.value = !monFull.value; loadAll(monFull.value) }
function toggleEvents(id) { openEvents[id] = !openEvents[id] }

function statusTone(s) { const x = String(s || '').toLowerCase(); if (['ok', 'healthy', 'up', 'online', 'good'].includes(x)) return 'green'; if (['warn', 'warning', 'degraded'].includes(x)) return 'amber'; if (['error', 'down', 'critical', 'unreachable', 'fail', 'offline'].includes(x)) return 'red'; return 'gray' }
function statusColor(s) { const t = statusTone(s); return t === 'green' ? 'var(--green)' : t === 'amber' ? 'var(--amber)' : t === 'red' ? 'var(--red)' : 'var(--text-3)' }
function statusBg(s) { const t = statusTone(s); return t === 'green' ? 'var(--green-soft)' : t === 'amber' ? 'var(--amber-soft)' : t === 'red' ? 'var(--red-soft)' : 'var(--panel-2)' }
function statusLabel(s) { const x = String(s || '').toLowerCase(); if (['ok', 'healthy', 'up', 'online', 'good'].includes(x)) return tr('serverMonitoring.healthy') || 'Healthy'; if (['warn', 'warning', 'degraded'].includes(x)) return tr('serverMonitoring.degraded') || 'Degraded'; if (['error', 'down', 'critical', 'unreachable', 'fail', 'offline'].includes(x)) return tr('serverMonitoring.down') || 'Down'; return s || '—' }
function meterColor(v) { const n = Number(v) || 0; return n > 80 ? 'var(--red)' : n > 60 ? 'var(--amber)' : 'var(--accent)' }
function fmtUptime(sec) { if (sec == null) return '—'; const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600); if (d > 0) return d + 'd ' + h + 'h'; const m = Math.floor((sec % 3600) / 60); return h > 0 ? h + 'h ' + m + 'm' : m + 'm' }
function driftTip(drift) { const iss = drift?.details?.issues || drift?.issues || []; return 'DRIFTED — ' + (Array.isArray(iss) ? iss.join(', ') : String(iss)) }

const monKpis = computed(() => {
  const list = rows.value || []
  const healthy = list.filter(s => statusTone(s.status) === 'green').length
  const issues = list.filter(s => statusTone(s.status) !== 'green').length
  const peers = list.reduce((a, s) => a + (Number(s.wireguard?.peers_total) || 0), 0)
  return [
    { label: tr('serverMonitoring.kpiTotal') || 'Total servers', value: list.length, color: 'var(--text)' },
    { label: tr('serverMonitoring.kpiHealthy') || 'Healthy', value: healthy, color: 'var(--green)' },
    { label: tr('serverMonitoring.kpiIssues') || 'Issues', value: issues, color: 'var(--amber)' },
    { label: tr('serverMonitoring.kpiPeers') || 'Peers', value: peers.toLocaleString(), color: 'var(--text)' },
  ]
})

const monServers = computed(() => {
  return (rows.value || [])
    .filter(s => {
      if (monFilter.value === 'all') return true
      return statusTone(s.status) === (monFilter.value === 'down' ? 'red' : monFilter.value === 'degraded' ? 'amber' : 'green')
    })
    .map(s => {
      const sys = s.system || {}
      const wg = s.wireguard || {}
      const drift = s.drift?.detected ? s.drift : null
      const meters = []
      if (sys.cpu_percent != null) meters.push({ label: 'CPU', value: Math.round(sys.cpu_percent) + '%', color: meterColor(sys.cpu_percent) })
      if (sys.memory_percent != null) meters.push({ label: 'RAM', value: Math.round(sys.memory_percent) + '%', color: meterColor(sys.memory_percent) })
      if (sys.disk_percent != null) meters.push({ label: 'Disk', value: Math.round(sys.disk_percent) + '%', color: meterColor(sys.disk_percent) })
      const peers = wg.peers_total != null ? (wg.peers_active != null ? wg.peers_active + '/' + wg.peers_total : String(wg.peers_total)) : '—'
      const history = []
      if (s.checked_at) history.push({ ts: fmtDate(s.checked_at), text: (tr('serverMonitoring.lastCheck') || 'Last check') + ' · ' + statusLabel(s.status) })
      if (s.latency_ms != null) history.push({ ts: fmtDate(s.checked_at), text: (tr('serverMonitoring.latency') || 'Latency') + ' ' + Math.round(s.latency_ms) + ' ms' })
      if (s.message) history.push({ ts: fmtDate(s.checked_at), text: s.message })
      return {
        id: s.server_id,
        name: s.server_name,
        region: s.connection_mode || 'ssh',
        statusColor: statusColor(s.status),
        statusBg: statusBg(s.status),
        statusLabel: statusLabel(s.status),
        drift,
        driftTip: drift ? driftTip(drift) : '',
        peers,
        uptime: fmtUptime(sys.uptime_seconds),
        meters,
        history,
      }
    })
})

// mode segmented toggle styling (Quick = !full, Full = full)
const monQuickWeight = computed(() => (monFull.value ? 500 : 650))
const monFullWeight = computed(() => (monFull.value ? 650 : 500))
const monQuickBg = computed(() => (monFull.value ? 'transparent' : 'var(--panel)'))
const monFullBg = computed(() => (monFull.value ? 'var(--panel)' : 'transparent'))
const monQuickColor = computed(() => (monFull.value ? 'var(--text-3)' : 'var(--text)'))
const monFullColor = computed(() => (monFull.value ? 'var(--text)' : 'var(--text-3)'))

function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }

onMounted(() => {
  ui.set({ title: tr('nav.monitoring') || 'Monitoring', live: true })
  loadAll()
  timer = setInterval(() => silentPoll(() => loadAll()), 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.d2-mon { display: block; }
</style>
