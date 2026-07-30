<!-- Updates — his exact 1:1 handoff: current version + channel chip + check
     button / available-update card with changelog + install / auto-apply toggle
     + restart-services / update history table (log + rollback). Wired to
     /updates/* endpoints. Update-log kept functional via D2Modal. -->
<template>
  <div class="d2-root">
    <div :style="{ display:'grid', gridTemplateColumns: gDashMain, gap:'14px', alignItems:'start', marginBottom:'14px' }">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px">
          <div>
            <div style="font-size:11px;color:var(--text-3)">{{ tr('updates.currentVersion') || 'Current version' }}</div>
            <div style="font-size:22px;font-weight:680;font-family:'JetBrains Mono',monospace">{{ updCurrent }}</div>
          </div>
          <span style="display:inline-flex;align-items:center;font-size:11px;font-weight:600;padding:3px 9px;border-radius:7px;color:var(--text-2);background:var(--gray-soft)">{{ channel }}<D2HelpTip :text="tr('help.updateChannel') || 'Stable: tested releases. Beta: newer features, may have bugs. Switch to stable if you encounter issues after a beta update.'" /></span>
          <div style="margin-left:auto;display:flex;gap:8px">
            <button @click="check" style="display:flex;align-items:center;gap:7px;height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2u-ghost">
              <span v-if="checking" style="width:13px;height:13px;border:2px solid var(--border-strong);border-top-color:var(--accent);border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ tr('updates.check') || 'Check for updates' }}
            </button>
          </div>
        </div>
        <div v-if="updateAvailable" style="padding:14px 16px;border:1px solid var(--accent-soft);background:var(--accent-soft);border-radius:12px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <span style="font-weight:650;font-size:14px;color:var(--accent)">{{ tr('updates.newVersionAvailable') || 'New version available' }} · {{ availVersion }}</span>
            <button @click="apply" :disabled="applying" style="margin-left:auto;height:34px;padding:0 14px;border:none;background:var(--accent);color:#fff;border-radius:8px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2u-accent">{{ applying ? (tr('updates.installing') || 'Installing…') : (tr('updates.applyNow') || 'Update now') }}</button>
          </div>
          <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:7px">{{ tr('updates.changelog') || 'Changelog' }}</div>
          <div style="display:flex;flex-direction:column;gap:5px">
            <div v-for="(c, i) in updChangelog" :key="i" style="display:flex;gap:8px;font-size:12.5px;color:var(--text-2)"><span style="color:var(--accent)">·</span>{{ c }}</div>
          </div>
        </div>
        <div v-if="!updateAvailable" style="display:flex;align-items:center;gap:10px;padding:14px 16px;border:1px solid var(--green-soft);background:var(--green-soft);border-radius:12px">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4 4L19 7"></path></svg>
          <span style="font-size:13px;color:var(--green);font-weight:550">{{ tr('updates.upToDate') || 'You are on the latest version' }}</span>
        </div>
      </div>
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px">
        <div style="display:flex;align-items:center;gap:11px;margin-bottom:16px">
          <button @click="onToggleAutoApply" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background: autoApply ? 'var(--accent)' : 'var(--border-strong)', transition:'background .15s', flex:'none' }">
            <span :style="{ position:'absolute', top:'2px', left: autoApply ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span>
          </button>
          <span style="font-size:13px;color:var(--text-2);display:inline-flex;align-items:center">{{ tr('updates.autoApply') || 'Auto-apply updates' }}<D2HelpTip :text="tr('updates.autoApplyHelp') || 'When enabled, the panel installs updates from the current channel as soon as they appear. Turn off to apply manually.'" /></span>
        </div>
        <button @click="restartServices" style="width:100%;height:38px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2u-ghost">{{ tr('updates.restartServices') || 'Restart services' }}</button>
      </div>
    </div>

    <!-- ── Live install progress — real, polled from /updates/progress/{id}:
         animated striped bar + step counter + streaming log. ── -->
    <div v-if="installRec && isActive(installRec.status)" style="background:var(--panel);border:1px solid var(--accent-soft);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px;margin-bottom:14px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
        <span style="width:16px;height:16px;border:2px solid var(--accent-soft);border-top-color:var(--accent);border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block;flex:none"></span>
        <span style="font-weight:650;font-size:14px;color:var(--accent)">{{ installRec.status === 'rolling_back' ? (tr('updates.rollingBack') || 'Rolling back') : (tr('updates.installing') || 'Installing update') }}</span>
        <span v-if="installRec.step" style="font-size:12.5px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">· {{ installRec.step }}</span>
        <span class="mono" style="margin-left:auto;font-size:12px;color:var(--text-3);flex:none">{{ installRec.step_number || 0 }}/{{ installRec.total_steps || 11 }}</span>
      </div>
      <div style="height:10px;border-radius:6px;background:var(--panel-3);overflow:hidden;margin-bottom:12px">
        <div class="d2-progbar" :style="{ width: installPct + '%' }"></div>
      </div>
      <div v-if="installRec.log && installRec.log.length" ref="logBox" class="d2u-log">
        <div v-for="(l, i) in installRec.log" :key="i" style="white-space:pre-wrap;word-break:break-word">{{ l }}</div>
      </div>
    </div>

    <!-- Terminal result of the last install/rollback -->
    <div v-if="installRec && isTerminal(installRec.status)" :style="{ background:'var(--panel)', border:'1px solid '+termColor(installRec.status).border, borderRadius:'14px', boxShadow:'var(--shadow)', padding:'18px 20px', marginBottom:'14px' }">
      <div style="display:flex;align-items:center;gap:10px">
        <svg v-if="installRec.status === 'success'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M8 12l3 3 5-6"></path></svg>
        <svg v-else-if="installRec.status === 'failed'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M15 9l-6 6M9 9l6 6"></path></svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"></path><path d="M3 13a9 9 0 1 0 3-7.7L3 8"></path></svg>
        <span :style="{ fontWeight:650, fontSize:'14px', color: termColor(installRec.status).text }">{{ termLabel(installRec.status) }}</span>
        <span v-if="installRec.error" style="font-size:12.5px;color:var(--red)">· {{ installRec.error }}</span>
        <button @click="dismissInstall" style="margin-left:auto;height:30px;padding:0 12px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2u-ghost">{{ tr('common.dismiss') || 'Dismiss' }}</button>
      </div>
      <div v-if="installRec.log && installRec.log.length" class="d2u-log" style="margin-top:12px">
        <div v-for="(l, i) in installRec.log" :key="i" style="white-space:pre-wrap;word-break:break-word">{{ l }}</div>
      </div>
    </div>

    <!-- Post-success restart wait -->
    <div v-if="restarting" style="display:flex;align-items:center;gap:10px;margin-bottom:14px;font-size:13px;color:var(--accent);background:var(--accent-soft);padding:11px 14px;border-radius:11px">
      <span style="width:15px;height:15px;border:2px solid var(--accent-soft);border-top-color:var(--accent);border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block;flex:none"></span>
      {{ tr('updates.waitingRestart') || 'Update applied — waiting for the panel to come back…' }}
    </div>

    <div v-if="progress" style="margin-bottom:14px;font-size:13px;color:var(--accent);background:var(--accent-soft);padding:9px 12px;border-radius:9px">{{ progress }}</div>

    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div style="font-weight:600;font-size:14px;padding:16px 20px 12px">{{ tr('updates.history') || 'Update history' }}</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;border-top:1px solid var(--border)">
          <th style="padding:9px 20px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('updates.version') || 'Version' }}</th>
          <th style="padding:9px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('updates.date') || 'Date' }}</th>
          <th style="padding:9px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('updates.result') || 'Status' }}</th>
          <th style="padding:9px 20px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('common.actions') || 'Actions' }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="(h, i) in rows" :key="h.id ?? i" style="border-top:1px solid var(--border)">
            <td style="padding:11px 20px;font-family:'JetBrains Mono',monospace;font-weight:600">{{ h.version }}</td>
            <td style="padding:11px 12px;font-family:'JetBrains Mono',monospace;color:var(--text-3)">{{ h.date }}</td>
            <td style="padding:11px 12px"><span :style="{ fontSize:'11px', fontWeight:600, padding:'2px 8px', borderRadius:'6px', color: h.statusColor, background: h.statusBg }">{{ h.statusLabel }}</span></td>
            <td style="padding:11px 20px"><div style="display:flex;gap:5px;justify-content:flex-end">
              <button @click="openLog(h)" style="height:28px;padding:0 10px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2u-ghost">{{ tr('updates.log') || 'Log' }}</button>
              <button v-if="h.canRollback" @click="rollback(h)" style="height:28px;padding:0 10px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2u-ghost">{{ tr('updates.rollbackNow') || 'Roll back' }}</button>
            </div></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="4" style="text-align:center;color:var(--text-3);padding:24px">{{ tr('updates.noHistory') || 'No update history' }}</td></tr>
        </tbody>
      </table>
    </div>

    <D2Modal :open="logModal.show" size="md" @close="logModal.show = false">
      <template #header><h3 style="font-weight:650;font-size:16px;margin:0">{{ tr('updates.logTitle') || 'Update log' }} · {{ logModal.version }}</h3></template>
      <pre style="background:var(--panel-2);border:1px solid var(--border);border-radius:11px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2);overflow-x:auto;white-space:pre-wrap;word-break:break-word;margin:0">{{ logModal.log || (tr('updates.noLog') || 'No log available.') }}</pre>
    </D2Modal>

    <D2Modal :open="rollbackModal.show" :title="tr('updates.confirmRollback') || 'Confirm rollback'" size="sm" @close="rollbackModal.show = false">
      <p style="font-size:13px;color:var(--text-3);margin:0 0 10px">{{ tr('help.rollback') || 'Reverts to the previous version if the current update caused problems. Only one rollback level is available.' }}</p>
      <p>{{ tr('updates.rollbackTo') || 'Roll back to' }} <b>{{ rollbackModal.version }}</b>?</p>
      <template #footer>
        <D2Button variant="secondary" @click="rollbackModal.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button variant="danger" :loading="rollingBack" @click="doRollback">{{ tr('updates.rollbackNow') || 'Roll back now' }}</D2Button>
      </template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import api from '../../api'
import { formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'
import D2Button from '../ui/D2Button.vue'
import D2Modal from '../ui/D2Modal.vue'
import D2HelpTip from '../ui/D2HelpTip.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const status = ref({})
const history = ref([])
const autoApply = ref(false)
const channel = computed(() => status.value.channel || 'stable')
const availVersion = computed(() => status.value.available_update?.version || null)
const updateAvailable = computed(() => !!status.value.available_update)
const checking = ref(false)
const applying = ref(false)
const rollingBack = ref(false)
const progress = ref('')
const rollbackModal = ref({ show: false, version: '', id: null })
const vw = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
function onResize() { vw.value = window.innerWidth }
const gDashMain = computed(() => vw.value <= 820 ? '1fr' : '1.6fr 1fr')

async function loadStatus() { try { const { data } = await api.get('/updates/status'); status.value = data } catch (_) {} }
async function loadHistory() { try { const { data } = await api.get('/updates/history?limit=20'); history.value = data.history || data.items || (Array.isArray(data) ? data : []) } catch (_) {} }
async function loadAutoApply() { try { const { data } = await api.get('/updates/auto-apply'); autoApply.value = !!(data.enabled ?? data.auto_apply) } catch (_) {} }
async function saveAutoApply(v) { try { await api.post('/updates/auto-apply', { enabled: v }) } catch (e) { alert(e.response?.data?.detail || 'Error'); autoApply.value = !v } }
async function check() { checking.value = true; progress.value = tr('updates.checking') || 'Checking…'; try { await api.post('/updates/check'); await loadStatus(); progress.value = '' } catch (e) { progress.value = e.response?.data?.detail || 'Error' } finally { checking.value = false } }
// ── Live install-progress engine (real, polled from /updates/progress/{id}) ──
const installRec = ref(null)   // live progress object: { status, step, step_number, total_steps, log[], error }
const restarting = ref(false)
const logBox = ref(null)
let installPoll = null, pollStart = 0, restartStart = 0
const POLL_MAX_MS = 30 * 60 * 1000
const RESTART_MAX_MS = 3 * 60 * 1000
const ACTIVE = new Set(['pending', 'downloading', 'applying', 'in_progress', 'rolling_back'])
const TERMINAL = new Set(['success', 'failed', 'rolled_back'])
function isActive(s) { return ACTIVE.has(s) }
function isTerminal(s) { return TERMINAL.has(s) }
const installPct = computed(() => {
  const p = installRec.value; if (!p) return 0
  const { step_number, total_steps } = p
  if (!step_number || !total_steps) return 5
  return Math.max(5, Math.round((step_number / total_steps) * 100))
})
function termColor(s) {
  if (s === 'success' || s === 'rolled_back') return { border: 'var(--green-soft)', text: 'var(--green)' }
  if (s === 'failed') return { border: 'var(--red-soft)', text: 'var(--red)' }
  return { border: 'var(--border)', text: 'var(--text-2)' }
}
function termLabel(s) {
  return tr('updates.status_' + s) || ({ success: 'Update complete', failed: 'Update failed', rolled_back: 'Rolled back' }[s] || s)
}
function scrollLog() { const el = logBox.value; if (el) el.scrollTop = el.scrollHeight }
async function loadProgress(id) {
  try { const { data } = await api.get(`/updates/progress/${id}`); installRec.value = data; await nextTick(); scrollLog(); return data } catch (_) { return null }
}
function stopInstallPoll() { if (installPoll) { clearInterval(installPoll); installPoll = null } }
function startInstallPoll(id) {
  stopInstallPoll(); pollStart = Date.now()
  installPoll = setInterval(async () => {
    const p = await loadProgress(id)
    if (p && isTerminal(p.status)) { stopInstallPoll(); applying.value = false; if (p.status === 'success') beginRestartWait() }
    else if (Date.now() - pollStart > POLL_MAX_MS) { stopInstallPoll(); applying.value = false }
  }, 2000)
}
// After a successful apply the panel restarts services; poll /updates/status
// until the API answers again, then hard-reload so the new build/version loads.
function beginRestartWait() {
  restarting.value = true; restartStart = Date.now()
  const t = setInterval(async () => {
    try { await api.get('/updates/status', { timeout: 4000, silent: true }); clearInterval(t); restarting.value = false; window.location.reload() }
    catch (_) { if (Date.now() - restartStart > RESTART_MAX_MS) { clearInterval(t); restarting.value = false } }
  }, 3000)
}
async function dismissInstall() { installRec.value = null }
async function apply() {
  if (!await d2confirm(tr('updates.applyConfirm') || 'Apply the update now? The panel will restart.')) return
  applying.value = true; progress.value = ''
  installRec.value = { status: 'in_progress', step: tr('updates.starting') || 'Starting…', step_number: 1, total_steps: 11, log: [] }
  try {
    const { data } = await api.post('/updates/apply')
    if (data.update_id) startInstallPoll(data.update_id)
  } catch (e) { progress.value = e.response?.data?.detail || 'Error'; applying.value = false; installRec.value = null }
}
function rollback(h) { rollbackModal.value = { show: true, version: h.to_version || h.version, id: h.id } }
async function doRollback() { rollingBack.value = true; try { await api.post(`/updates/rollback/${rollbackModal.value.id}`); rollbackModal.value.show = false; progress.value = tr('updates.rollingBack') || 'Rolling back…' } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { rollingBack.value = false } }
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }

// ── adapters + his restart-services / update-log wiring (real /updates/* endpoints) ──
const updCurrent = computed(() => status.value.current_version || status.value.version || '—')
const updProgressPct = computed(() => (status.value.progress != null ? status.value.progress : 40) + '%')
const updChangelog = computed(() => {
  const cl = status.value.available_update?.changelog ?? status.value.changelog ?? []
  if (Array.isArray(cl)) return cl
  return String(cl).split('\n').map(s => s.trim()).filter(Boolean)
})
const US = {
  success: ['var(--green)', 'var(--green-soft)'], installed: ['var(--green)', 'var(--green-soft)'],
  failed: ['var(--red)', 'var(--red-soft)'], error: ['var(--red)', 'var(--red-soft)'],
}
function statusLabel(s) { const k = String(s || 'ok').toLowerCase(); return tr('updates.status_' + k) || (k.charAt(0).toUpperCase() + k.slice(1)) }
const rows = computed(() => history.value.map((h, i) => {
  const st = String(h.status || '').toLowerCase()
  const [c, b] = US[st] || ['var(--amber)', 'var(--amber-soft)']
  return { id: h.id ?? i, version: h.to_version || h.version, date: h.started_at ? fmtDate(h.started_at) : '—', statusColor: c, statusBg: b, statusLabel: statusLabel(h.status), canRollback: !!h.rollback_available && i === 0, log: h.log }
}))

const logModal = ref({ show: false, version: '', log: '' })
async function openLog(h) {
  logModal.value = { show: true, version: h.version, log: h.log || '' }
  try { const { data } = await api.get(`/updates/log/${h.id}`); logModal.value.log = data.log || logModal.value.log } catch (_) {}
}
async function onToggleAutoApply() { autoApply.value = !autoApply.value; saveAutoApply(autoApply.value) }
async function restartServices() {
  if (!await d2confirm(tr('updates.restartConfirm') || 'Restart all services now?')) return
  progress.value = tr('updates.restarting') || 'Restarting services…'
  try { await api.post('/updates/restart') } catch (e) { progress.value = e.response?.data?.detail || 'Error' }
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  ui.set({ title: tr('nav.updates') || 'Updates' })
  await loadStatus(); loadHistory(); loadAutoApply()
  // Resume a live install if one is already running (e.g. page was reopened).
  if (status.value.update_in_progress && status.value.active_update_id) {
    applying.value = true
    await loadProgress(status.value.active_update_id)
    if (installRec.value && isActive(installRec.value.status)) startInstallPoll(status.value.active_update_id)
  }
})
onBeforeUnmount(() => { window.removeEventListener('resize', onResize); stopInstallPoll() })
</script>

<style scoped>
.d2u-ghost:hover { background: var(--panel-2) !important; }
.d2u-accent:hover { background: var(--accent-2) !important; }
.mono { font-family: 'JetBrains Mono', monospace; }
/* Marching-stripes progress bar (d2spin/d2stripes keyframes live in base.css,
   global — inline/scoped animation refs need a non-scoped keyframe). */
.d2-progbar {
  height: 100%; border-radius: 6px; transition: width .4s ease;
  background-image: repeating-linear-gradient(45deg, var(--accent) 0, var(--accent) 8px, var(--accent-2) 8px, var(--accent-2) 16px);
  background-size: 32px 32px; animation: d2stripes 1s linear infinite;
}
.d2u-log {
  max-height: 190px; overflow-y: auto; background: var(--panel-2); border: 1px solid var(--border);
  border-radius: 10px; padding: 11px 13px; font-family: 'JetBrains Mono', monospace;
  font-size: 11.5px; color: var(--text-2); line-height: 1.55;
}
</style>
