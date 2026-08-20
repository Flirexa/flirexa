<!-- System Health — his exact 1:1 handoff: status banner + Quick/Full pill toggle
     / Active issues + Recovered cards / Components grid / Event log with severity
     filter. Wired to healthApi (getSystemHealth/refresh/getIssues/getEvents). -->
<template>
  <div class="d2-health-root">
    <!-- ===== SYSTEM HEALTH ===== -->
    <div class="d2-health-banner" :style="{ display:'flex', alignItems:'center', gap:'12px', flexWrap:'wrap', rowGap:'10px', padding:'16px 20px', border:'1px solid '+healthBannerBorder, background:healthBannerBg, borderRadius:'14px', marginBottom:'14px' }">
      <div :style="{ width:'40px', height:'40px', borderRadius:'11px', background:healthBannerIconBg, color:healthBannerColor, display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }">
        <svg v-if="healthOk" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"></path></svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M4.9 4.9l14.2 14.2"></path></svg>
      </div>
      <div class="d2-health-summary" style="flex:1">
        <div :style="{ fontWeight:650, fontSize:'15px', color:healthBannerColor }">{{ healthBannerTitle }}</div>
        <div style="font-size:12.5px;color:var(--text-2);margin-top:1px">{{ healthBannerSub }}</div>
      </div>
      <div class="d2-health-mode" style="display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px">
        <button @click="healthFull = false" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'11.5px', fontWeight:hlQuickWeight, cursor:'pointer', background:hlQuickBg, color:hlQuickColor }">{{ tr('mon.quick') || 'Quick' }}</button>
        <button @click="healthFull = true" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'11.5px', fontWeight:hlFullWeight, cursor:'pointer', background:hlFullBg, color:hlFullColor }">{{ tr('mon.full') || 'Full' }}</button>
      </div>
      <button @click="load(true)" class="d2-hl-refresh" style="height:36px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer;flex:none">{{ tr('health.refresh') || 'Refresh' }}</button>
    </div>

    <div class="d2-health-pair" :style="{ display:'grid', gridTemplateColumns:gPair, gap:'14px', marginBottom:'14px' }">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:16px 20px">
        <div style="font-weight:600;font-size:14px;margin-bottom:12px">{{ tr('health.activeIssues') || 'Active issues' }}</div>
        <div v-if="noIssues" style="font-size:13px;color:var(--text-3);padding:8px 0">{{ tr('health.overallOk') || 'All systems operational' }}</div>
        <div style="display:flex;flex-direction:column;gap:9px">
          <div v-for="i in healthIssues" :key="i.id" class="d2-health-issue" :style="{ display:'flex', gap:'10px', padding:'11px 13px', border:'1px solid '+i.border, background:i.bg, borderRadius:'10px' }">
            <span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:i.color, marginTop:'5px', flex:'none' }"></span>
            <div style="flex:1">
              <div style="font-size:12.5px;color:var(--text);line-height:1.4">{{ i.text }}</div>
              <div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ i.comp }} · {{ i.since }}</div>
            </div>
          </div>
        </div>
      </div>
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:16px 20px">
        <div style="font-weight:600;font-size:14px;margin-bottom:12px">{{ tr('health.recovered') || 'Recovered' }}</div>
        <div style="display:flex;flex-direction:column;gap:9px">
          <div v-for="r in healthRecovered" :key="r.id" style="display:flex;gap:10px;padding:11px 13px;border:1px solid var(--green-soft);background:var(--green-soft);border-radius:10px">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-top:1px;flex:none"><path d="M5 12l4 4L19 7"></path></svg>
            <div style="flex:1">
              <div style="font-size:12.5px;color:var(--text);line-height:1.4">{{ r.text }}</div>
              <div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ r.comp }} · {{ r.since }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:16px 20px;margin-bottom:14px">
      <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('health.components') || 'Components' }}</div>
      <div class="d2-health-components" :style="{ display:'grid', gridTemplateColumns:gComponents, gap:'11px' }">
        <div v-for="c in healthComponents" :key="c.name" class="d2-health-component" style="display:flex;align-items:center;gap:11px;padding:12px 14px;border:1px solid var(--border);border-radius:11px">
          <span :style="{ width:'10px', height:'10px', borderRadius:'50%', background:c.color, flex:'none' }"></span>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:550">{{ c.label }}</div>
            <div style="font-size:11px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ c.detail }}</div>
          </div>
          <span class="mono" style="font-size:11px;color:var(--text-3);flex:none">{{ c.latency }}</span>
        </div>
      </div>
    </div>

    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px 12px">
        <div style="font-weight:600;font-size:14px">{{ tr('health.eventLog') || 'Event log' }}</div>
        <select v-model="healthSev" style="height:30px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;padding:0 9px;font:inherit;font-size:12px;outline:none;cursor:pointer">
          <option value="all">{{ tr('health.allSeverities') || 'All severities' }}</option>
          <option value="critical">{{ tr('health.critical') || 'Critical' }}</option>
          <option value="warning">{{ tr('health.warning') || 'Warning' }}</option>
          <option value="info">{{ tr('health.info') || 'Info' }}</option>
        </select>
      </div>
      <div class="mono" style="font-size:12px">
        <div v-for="(e, idx) in healthEvents" :key="idx" class="d2-health-event" style="display:flex;gap:12px;align-items:baseline;padding:9px 20px;border-top:1px solid var(--border)">
          <span style="color:var(--text-3);flex:none">{{ e.ts }}</span>
          <span :style="{ flex:'none', fontWeight:600, textTransform:'uppercase', fontSize:'10px', letterSpacing:'.04em', color:e.sevColor, background:e.sevBg, padding:'2px 6px', borderRadius:'5px', minWidth:'62px', textAlign:'center' }">{{ e.sev }}</span>
          <span style="color:var(--text-2);word-break:break-word">{{ e.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { healthApi } from '../../api'
import { formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n({ useScope: 'global' })
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const health = ref(null)
const issues = ref([])
const recoveries = ref([])
const events = ref([])
const loading = ref(false)
const components = computed(() => {
  const c = health.value?.components
  if (Array.isArray(c)) return c
  if (c && typeof c === 'object') return Object.entries(c).map(([name, v]) => ({ name, ...(typeof v === 'object' ? v : { status: v }) }))
  return []
})
async function load(force = false) {
  loading.value = true
  try {
    const [h, i, e] = await Promise.all([
      force ? healthApi.refreshSystemHealth() : healthApi.getSystemHealth(false),
      healthApi.getIssues().catch(() => ({ data: [] })),
      healthApi.getEvents({ limit: 50 }).catch(() => ({ data: [] })),
    ])
    health.value = h.data
    issues.value = i.data.active_issues || i.data.items || (Array.isArray(i.data) ? i.data : [])
    recoveries.value = i.data.recent_recoveries || []
    events.value = e.data.events || e.data.items || (Array.isArray(e.data) ? e.data : [])
  } catch (err) { console.error(err) } finally { loading.value = false }
}
function prettyName(n) { return String(n || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }
function statusTone(s) { const x = String(s || '').toLowerCase(); if (['ok', 'healthy', 'up', 'online', 'good'].includes(x)) return 'green'; if (['warn', 'warning', 'degraded'].includes(x)) return 'amber'; if (['error', 'down', 'critical', 'fail'].includes(x)) return 'red'; return 'gray' }
function dotClass(s) { return statusTone(s) === 'green' ? 'g' : statusTone(s) === 'amber' ? 'a' : statusTone(s) === 'red' ? 'r' : 'm' }
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }
function fmtDuration(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value < 0) return ''
  if (value < 60) return `${Math.floor(value)}s`
  if (value < 3600) return `${Math.floor(value / 60)}m`
  if (value < 86400) return `${Math.floor(value / 3600)}h`
  return `${Math.floor(value / 86400)}d`
}

// ---- adapters to his field names ----
const healthFull = ref(false)
const healthSev = ref('all')

const HL_STAT = { healthy: 'var(--green)', degraded: 'var(--amber)', down: 'var(--red)' }
function toHlStatus(s) { const tone = statusTone(s); return tone === 'green' ? 'healthy' : tone === 'amber' ? 'degraded' : tone === 'red' ? 'down' : 'healthy' }
function toSev(s) { const tone = statusTone(s); const x = String(s || '').toLowerCase(); if (tone === 'red' || x === 'critical' || x === 'error') return 'critical'; if (tone === 'amber' || x === 'warning' || x === 'warn') return 'warning'; return 'info' }
const sevMeta = computed(() => ({
  critical: { c: 'var(--red)', b: 'var(--red-soft)', l: tr('health.critical') || 'Critical' },
  warning: { c: 'var(--amber)', b: 'var(--amber-soft)', l: tr('health.warning') || 'Warning' },
  info: { c: 'var(--text-2)', b: 'var(--gray-soft)', l: tr('health.info') || 'Info' },
}))

const healthComponents = computed(() => components.value.map(c => {
  const status = toHlStatus(c.status)
  const latency = c.latency != null ? c.latency : (c.latency_ms != null ? c.latency_ms + 'ms' : '—')
  const detail = c.detail || c.message || ''
  return { name: c.name, label: prettyName(c.label || c.name), status, latency, detail, color: HL_STAT[status] || HL_STAT.healthy }
}))

const healthIssues = computed(() => issues.value.map((i, idx) => {
  const obj = (i && typeof i === 'object') ? i : { message: i }
  const sev = obj.sev || toSev(obj.level || obj.severity || obj.status || obj.current_status)
  const m = sevMeta.value[sev] || sevMeta.value.info
  const component = obj.comp || obj.component || obj.target_name || obj.name || obj.target_id || ''
  const status = prettyName(obj.current_status || obj.status || '')
  const text = obj.text || obj.message || obj.title || obj.last_error || status || (tr('health.issueDetected') || 'Health issue detected')
  const since = obj.since || fmtDuration(obj.duration_seconds) || (obj.last_status_change || obj.created_at || obj.timestamp ? fmtDate(obj.last_status_change || obj.created_at || obj.timestamp) : '')
  return { id: obj.id ?? `${obj.target_type || 'issue'}-${obj.target_id || idx}`, comp: component, text, since, color: m.c, bg: m.b, border: m.b }
}))

const healthRecovered = computed(() => {
  const src = recoveries.value.length ? recoveries.value : (health.value?.recovered || issues.value.filter(i => i && typeof i === 'object' && i.recovered))
  const list = Array.isArray(src) ? src : []
  return list.map((r, idx) => ({ id: r.id ?? idx, comp: r.comp || r.component || r.target_name || r.name || '', text: r.text || r.message || (tr('health.recovered') || 'Recovered'), since: r.since || (r.created_at || r.timestamp ? fmtDate(r.created_at || r.timestamp) : '') }))
})

const healthEvents = computed(() => events.value
  .map((e, idx) => {
    const sevKey = e.sev || toSev(e.level || e.severity || e.status)
    return { _idx: idx, sevKey, ts: e.ts || (e.created_at || e.timestamp ? fmtDate(e.created_at || e.timestamp) : ''), comp: e.comp || e.component || '', text: e.text || e.message || e.event || '' }
  })
  .filter(e => healthSev.value === 'all' || e.sevKey === healthSev.value)
  .map(e => { const m = sevMeta.value[e.sevKey] || sevMeta.value.info; return { ...e, sev: m.l, sevColor: m.c, sevBg: m.b } }))

const healthOk = computed(() => healthIssues.value.length === 0)
const noIssues = computed(() => healthOk.value)

const healthBannerBorder = computed(() => healthOk.value ? 'var(--green-soft)' : 'var(--red-soft)')
const healthBannerBg = computed(() => healthOk.value ? 'var(--green-soft)' : 'var(--red-soft)')
// chip behind the banner icon: a raised panel-colored square that lifts off the
// soft-tinted banner in BOTH themes (a hardcoded white broke dark mode, and a
// -soft tint matched the banner bg exactly → no contrast).
const healthBannerIconBg = computed(() => 'var(--panel)')
const healthBannerColor = computed(() => healthOk.value ? 'var(--green)' : 'var(--red)')
const healthBannerTitle = computed(() => healthOk.value ? (tr('health.overallOk') || 'All systems operational') : (tr('health.overallBad') || 'Issues detected'))
const healthBannerSub = computed(() => `${healthIssues.value.length} ${tr('health.issuesWord') || 'active issues'} · ${healthComponents.value.length} ${tr('health.componentsWord') || 'components'}`)

const hlQuickBg = computed(() => !healthFull.value ? 'var(--panel)' : 'transparent')
const hlQuickColor = computed(() => !healthFull.value ? 'var(--text)' : 'var(--text-3)')
const hlQuickWeight = computed(() => !healthFull.value ? '600' : '500')
const hlFullBg = computed(() => healthFull.value ? 'var(--panel)' : 'transparent')
const hlFullColor = computed(() => healthFull.value ? 'var(--text)' : 'var(--text-3)')
const hlFullWeight = computed(() => healthFull.value ? '600' : '500')

const gPair = 'repeat(auto-fit, minmax(280px, 1fr))'
const gComponents = 'repeat(auto-fill, minmax(220px, 1fr))'

onMounted(() => {
  ui.set({ title: tr('nav.health') || tr('nav.systemHealth') || 'System health', live: true })
  load(false)
})
</script>

<style scoped>
.d2-health-root { display: flex; flex-direction: column; }
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-hl-refresh:hover { background: var(--panel-2); }
@media (max-width:900px) {
  .d2-health-banner { display:grid !important;grid-template-columns:36px minmax(0,1fr) auto;gap:10px !important;padding:12px !important;align-items:center !important;border-radius:12px !important; }
  .d2-health-banner > div:first-child { width:36px !important;height:36px !important;border-radius:10px !important; }
  .d2-health-summary { grid-column:2 / 4;min-width:0; }
  .d2-health-summary > div:first-child { font-size:14px !important;line-height:1.3; }
  .d2-health-summary > div:last-child { font-size:11px !important;line-height:1.35; }
  .d2-health-summary > div { word-break:normal !important;overflow-wrap:normal; }
  .d2-health-mode { grid-column:1 / 3;width:100%; }
  .d2-health-mode button { flex:1;min-height:32px;padding:4px 8px !important; }
  .d2-health-banner > .d2-hl-refresh { grid-column:3 / 4;width:auto;height:34px !important;justify-self:end; }
  .d2-health-pair { grid-template-columns:1fr !important; }
  .d2-health-pair > div { padding:14px !important;border-radius:12px !important; }
  .d2-health-issue > div { min-width:0; }
  .d2-health-components { grid-template-columns:1fr !important; }
  .d2-health-component { min-width:0;padding:10px 11px !important;border-radius:9px !important; }
  .d2-health-component > span:first-child { width:8px !important;height:8px !important; }
  .d2-health-event { display:grid !important;grid-template-columns:auto 1fr;gap:7px 9px !important;padding:10px 14px !important; }
  .d2-health-event > span:last-child { grid-column:1 / -1; }
}
</style>
