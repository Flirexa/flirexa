<!-- App logs — his exact markup: component tabs (api/worker/agent) + "Errors only"
     toggle + Refresh, then a mono log panel (ts / level badge / msg).
     Wired to systemApi.getAppLogs / getAppLogsErrors (existing logic verbatim). -->
<template>
  <div>
    <div class="d2-app-log-toolbar" style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <div style="display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px">
        <button v-for="c in appLogTabs" :key="c.key" @click="c.on" :style="{ padding:'5px 13px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'12px', fontWeight:c.weight, cursor:'pointer', background:c.bg, color:c.color }">{{ c.label }}</button>
      </div>
      <button @click="toggleAppLogErrors" :style="{ display:'flex', alignItems:'center', gap:'7px', height:'34px', padding:'0 13px', border:'1px solid '+appLogErrBorder, background:appLogErrBg, color:appLogErrColor, borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }">{{ tr('appLogs.errorsOnly') || 'Errors only' }}</button>
      <button @click="refreshAppLogs" class="d2-alog-refresh" style="margin-left:auto;height:34px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('common.refresh') || 'Refresh' }}</button>
    </div>
    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden;font-family:'JetBrains Mono',monospace;font-size:12px">
      <div v-for="(l, i) in appLogs" :key="i" class="d2-alog-row" style="display:flex;gap:12px;align-items:baseline;padding:9px 18px;border-top:1px solid var(--border)">
        <span style="color:var(--text-3);flex:none">{{ l.ts }}</span>
        <span :style="{ flex:'none', fontWeight:600, textTransform:'uppercase', fontSize:'10px', letterSpacing:'.04em', color:l.levelColor, background:l.levelBg, padding:'2px 6px', borderRadius:'5px', minWidth:'46px', textAlign:'center' }">{{ l.level }}</span>
        <span style="color:var(--text-2);word-break:break-word">{{ l.msg }}</span>
      </div>
      <div v-if="!appLogs.length" style="color:var(--text-3);padding:24px;text-align:center;font-family:inherit">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('appLogs.empty') || 'No entries') }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { systemApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const entries = ref([])
const loading = ref(false)
const mode = ref('all')
const component = ref('api')
async function load() {
  loading.value = true
  try { const { data } = mode.value === 'errors' ? await systemApi.getAppLogsErrors({}) : await systemApi.getAppLogs({}); entries.value = (data.entries || data.items || (Array.isArray(data) ? data : [])).slice().reverse() }
  catch (e) { console.error(e) } finally { loading.value = false }
}
function lvl(e) { const s = String(e.level || '').toLowerCase(); if (s.includes('err') || s.includes('crit')) return 'error'; if (s.includes('warn')) return 'warn'; return 'info' }
function setAppLogComp(c) { component.value = c }
function toggleAppLogErrors() { mode.value = mode.value === 'errors' ? 'all' : 'errors'; load() }
function refreshAppLogs() { load() }

const LVL_COLOR = { info: { c: 'var(--text-2)', b: 'var(--gray-soft)' }, warn: { c: 'var(--amber)', b: 'var(--amber-soft)' }, error: { c: 'var(--red)', b: 'var(--red-soft)' } }
function compOf(e) { return String(e.component || e.comp || e.logger || '').toLowerCase() }

const appLogTabs = computed(() => [['api', 'API'], ['worker', 'Worker'], ['agent', 'Agent']].map(([k, l]) => {
  const on = k === component.value
  return { key: k, label: l, on: () => setAppLogComp(k), bg: on ? 'var(--panel)' : 'transparent', color: on ? 'var(--text)' : 'var(--text-3)', weight: on ? '600' : '500' }
}))
const appLogErrBg = computed(() => mode.value === 'errors' ? 'var(--red-soft)' : 'var(--panel)')
const appLogErrColor = computed(() => mode.value === 'errors' ? 'var(--red)' : 'var(--text-2)')
const appLogErrBorder = computed(() => mode.value === 'errors' ? 'var(--red-soft)' : 'var(--border-strong)')

const appLogs = computed(() => entries.value
  .filter(e => { const c = compOf(e); return !c || !hasComp.value || c === component.value })
  .map(e => {
    const level = lvl(e)
    return { ts: e.timestamp || e.time || e.ts || '', level, levelColor: LVL_COLOR[level].c, levelBg: LVL_COLOR[level].b, msg: e.message || e.msg || String(e) }
  }))
const hasComp = computed(() => entries.value.some(e => compOf(e)))

onMounted(() => { ui.set({ title: tr('nav.applogs') || 'App logs' }); load() })
</script>

<style scoped>
.d2-alog-row:hover { background: var(--panel-2); }
.d2-alog-refresh:hover { background: var(--panel-2); }
@media (max-width:900px) {
  .d2-app-log-toolbar { display:grid !important;grid-template-columns:1fr 1fr; }
  .d2-app-log-toolbar > div { grid-column:1 / -1;display:grid !important;grid-template-columns:repeat(3,1fr); }
  .d2-app-log-toolbar > button { width:100%;margin-left:0 !important;justify-content:center; }
  .d2-alog-row { display:grid !important;grid-template-columns:auto 1fr;gap:6px 8px !important;padding:10px 13px !important; }
  .d2-alog-row > span:first-child { min-width:0;font-size:10px;overflow-wrap:anywhere; }
  .d2-alog-row > span:nth-child(2) { justify-self:end; }
  .d2-alog-row > span:last-child { grid-column:1 / -1;min-width:0;line-height:1.45;overflow-wrap:anywhere; }
}
</style>
