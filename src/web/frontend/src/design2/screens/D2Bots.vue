<!-- Bots — his exact 1:1 handoff (VPN Admin Panel.dc.html L731-772):
     two bot cards (icon/status/service·uptime·pid stats + start/stop/restart),
     config panel (admin token / client token / allowed IDs / client-on toggle /
     save) and an activity-log panel (svc tabs + errors filter + refresh).
     Wired to botsApi (config, status, service control and token-redacted
     systemd journal tails for both services). -->
<template>
  <div>
    <!-- ===== bot cards ===== -->
    <div class="bot-grid" style="margin-bottom:14px">
      <div v-for="b in botCards" :key="b.key" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px">
        <div style="display:flex;align-items:center;gap:11px;margin-bottom:14px">
          <div style="width:38px;height:38px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none" v-html="b.icon"></div>
          <div style="flex:1">
            <div style="font-weight:600;font-size:14px">{{ b.title }}</div>
            <span :style="{ display:'inline-flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:550, color:b.statusColor, marginTop:'2px' }"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:b.statusColor }"></span>{{ b.statusLabel }}</span>
          </div>
        </div>
        <div class="bot-metrics" style="display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:14px;padding:11px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)">
          <div><div style="font-size:10px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">{{ tr('bots.service') || 'Service' }}</div><div style="font-size:11.5px;font-family:'JetBrains Mono',monospace;color:var(--text-2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ b.service }}</div></div>
          <div><div style="font-size:10px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">{{ tr('bots.uptime') || 'Uptime' }}</div><div style="font-size:12px;font-family:'JetBrains Mono',monospace;color:var(--text-2);margin-top:2px">{{ b.uptime }}</div></div>
          <div><div style="font-size:10px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">{{ tr('bots.pid') || 'PID' }}</div><div style="font-size:12px;font-family:'JetBrains Mono',monospace;color:var(--text-2);margin-top:2px">{{ b.pid }}</div></div>
        </div>
        <div style="display:flex;gap:8px">
          <button @click="botAction(b.key,'start')" :disabled="busy[b.key+'_start'] || b.isRunning || !b.canRun" style="flex:1;height:36px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2-btn-primary">{{ tr('common.start') || 'Start' }}</button>
          <button @click="botAction(b.key,'stop')" :disabled="busy[b.key+'_stop'] || !b.isRunning" style="flex:1;height:36px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('common.stop') || 'Stop' }}</button>
          <button @click="botAction(b.key,'restart')" :disabled="busy[b.key+'_restart'] || !b.canRun" style="flex:1;height:36px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('common.restart') || 'Restart' }}</button>
        </div>
        <div v-if="!b.configured" style="font-size:11.5px;color:var(--amber);margin-top:9px">{{ tr('bots.configureFirst') || 'Configure this bot before starting it.' }}</div>
      </div>
    </div>

    <!-- ===== config + logs ===== -->
    <div class="bot-grid" style="align-items:start">
      <!-- config -->
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px">
        <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('bots.botConfig') || 'Bot configuration' }}</div>
        <div style="display:flex;flex-direction:column;gap:14px">
          <div>
            <label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('bots.adminBotToken') || 'Admin bot token' }}</label>
            <input v-model="form.admin_bot_token" type="password" autocomplete="new-password" @focus="focused='at'" @blur="focused=''" :placeholder="cfg?.admin_bot_token_masked || tr('bots.enterAdminBotToken') || 'Enter token'" :style="inputStyle('at')" />
            <div class="field-hint">{{ tr('bots.tokenHelp') || 'Create a bot with @BotFather, then paste its token here.' }}</div>
          </div>
          <div>
            <label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('bots.clientBotToken') || 'Client bot token' }}</label>
            <input v-model="form.client_bot_token" type="password" autocomplete="new-password" :disabled="cfg && !cfg.client_bot_available" @focus="focused='ct'" @blur="focused=''" :placeholder="cfg?.client_bot_token_masked || tr('bots.enterClientBotToken') || 'Enter token'" :style="inputStyle('ct')" />
          </div>
          <div>
            <label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('bots.adminAllowedUsers') || 'Admin allowed user IDs' }}</label>
            <input v-model="form.admin_allowed_users" @focus="focused='al'" @blur="focused=''" :placeholder="tr('bots.commaSeparatedIds') || 'comma-separated IDs'" :style="inputStyle('al')" />
          </div>
          <div style="display:flex;align-items:center;gap:11px">
            <button @click="form.client_bot_enabled = !form.client_bot_enabled" :disabled="cfg && !cfg.client_bot_available" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background: form.client_bot_enabled ? 'var(--accent)' : 'var(--border-strong)', transition:'background .15s', flex:'none', opacity: cfg && !cfg.client_bot_available ? .5 : 1 }"><span :style="{ position:'absolute', top:'2px', left: form.client_bot_enabled ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
            <span style="font-size:13px;color:var(--text-2)">{{ tr('bots.clientBotEnabled') || 'Client bot enabled' }}</span>
          </div>
          <div v-if="cfg && !cfg.client_bot_available" class="feature-note">{{ tr('bots.clientBotPaid') || 'The client self-service bot is available with Business and Enterprise.' }}</div>
          <div v-if="msg" style="color:var(--green);font-size:13px">{{ msg }}</div>
          <div v-if="err" style="color:var(--red);font-size:13px">{{ err }}</div>
          <button @click="saveConfig" :disabled="saving" style="align-self:flex-start;height:40px;padding:0 18px;border:none;background:var(--accent);color:#fff;border-radius:10px;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer" class="d2-btn-primary">{{ tr('bots.saveConfiguration') || 'Save configuration' }}</button>
        </div>
      </div>

      <!-- logs -->
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
        <div style="display:flex;align-items:center;gap:8px;padding:16px 20px 12px;flex-wrap:wrap">
          <div style="font-weight:600;font-size:14px;flex:1">{{ tr('bots.activityLog') || 'Activity log' }}</div>
          <div style="display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px">
            <button v-for="c in botLogTabs" :key="c.key" @click="logTab = c.key; loadLogs()" :style="{ padding:'4px 11px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'11px', fontWeight: logTab===c.key ? 600 : 500, cursor:'pointer', background: logTab===c.key ? 'var(--panel)' : 'transparent', color: logTab===c.key ? 'var(--text)' : 'var(--text-3)' }">{{ c.label }}</button>
          </div>
          <button @click="logErrorsOnly = !logErrorsOnly" :style="{ height:'30px', padding:'0 11px', border:'1px solid '+(logErrorsOnly?'var(--red-soft)':'var(--border-strong)'), background:(logErrorsOnly?'var(--red-soft)':'var(--panel)'), color:(logErrorsOnly?'var(--red)':'var(--text-2)'), borderRadius:'8px', font:'inherit', fontSize:'11.5px', fontWeight:550, cursor:'pointer' }">{{ tr('bots.errorsOnly') || 'Errors' }}</button>
          <button @click="refreshBotLogs" style="height:30px;padding:0 11px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('bots.refresh') || 'Refresh' }}</button>
        </div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;max-height:300px;overflow-y:auto">
          <div v-for="(l, i) in filteredLogs" :key="i" class="d2-bot-log-row" style="display:flex;gap:10px;align-items:baseline;padding:8px 20px;border-top:1px solid var(--border)">
            <span style="color:var(--text-3);flex:none">{{ l.ts }}</span>
            <span :style="{ flex:'none', fontWeight:600, textTransform:'uppercase', fontSize:'9.5px', letterSpacing:'.04em', color:l.levelColor, background:l.levelBg, padding:'1px 5px', borderRadius:'4px', minWidth:'42px', textAlign:'center' }">{{ l.level }}</span>
            <span style="color:var(--text-2);word-break:break-word">{{ l.msg }}</span>
          </div>
          <div v-if="!filteredLogs.length" style="padding:20px;color:var(--text-3);border-top:1px solid var(--border)">{{ tr('bots.noActivity') || 'No activity yet' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { botsApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const adminBot = ref(null)
const clientBot = ref(null)
const cfg = ref(null)
const form = ref({ admin_bot_token: '', admin_allowed_users: '', client_bot_token: '', client_bot_enabled: false })
const original = ref({ admin_allowed_users: '', client_bot_enabled: false })
const busy = reactive({})
const saving = ref(false)
const msg = ref('')
const err = ref('')
const focused = ref('')
const logTab = ref('admin')
const logErrorsOnly = ref(false)

// --- his focus/input style (border+ring on focus) ---
function inputStyle(id) {
  const on = focused.value === id
  return {
    width: '100%', height: '42px', border: '1px solid ' + (on ? 'var(--accent)' : 'var(--border-strong)'),
    background: on ? 'var(--panel)' : 'var(--panel-2)', color: 'var(--text)', borderRadius: '10px', padding: '0 13px',
    fontFamily: "'JetBrains Mono',monospace", fontSize: '12.5px', outline: 'none',
    boxShadow: on ? '0 0 0 3px var(--accent-ring)' : 'none',
  }
}

// his exact icon('lock',18,1.7) / icon('bot',18,1.7) glyphs (handoff L3169/L3171, wrapper L3206)
const ICON_ADMIN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="display:block"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 018 0v3"></path></svg>'
const ICON_CLIENT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="display:block"><rect x="5" y="8" width="14" height="11" rx="2.5"></rect><circle cx="9.5" cy="13" r="1"></circle><circle cx="14.5" cy="13" r="1"></circle><path d="M12 4v4"></path><circle cx="12" cy="3.4" r="1.1"></circle></svg>'

// --- adapter: our payload → his card fields ---
function fmtUptime(s) {
  const secs = Number(s?.uptime_seconds ?? s?.uptime ?? 0)
  if (!secs || secs <= 0) return '—'
  const d = Math.floor(secs / 86400), h = Math.floor((secs % 86400) / 3600), m = Math.floor((secs % 3600) / 60)
  if (d) return d + 'd ' + h + 'h'
  if (h) return h + 'h ' + m + 'm'
  return m + 'm'
}
function card(key, title, icon, bot, svc) {
  const on = !!bot?.is_running
  const available = key !== 'client' || cfg.value?.client_bot_available !== false
  return {
    key, title, icon,
    isRunning: on,
    configured: !!bot?.configured,
    canRun: available && !!bot?.configured && !!bot?.enabled,
    statusColor: on ? 'var(--green)' : 'var(--text-3)',
    statusLabel: on ? (tr('bots.running') || 'Running') : (tr('bots.stopped') || 'Stopped'),
    service: bot?.service || svc,
    uptime: on ? fmtUptime(bot) : '—',
    pid: bot?.pid || (on ? '—' : '—'),
  }
}
const botCards = computed(() => [
  card('admin', tr('bots.adminBot') || 'Admin bot', ICON_ADMIN, adminBot.value, 'vpnmanager-admin-bot'),
  card('client', tr('bots.clientBot') || 'Client bot', ICON_CLIENT, clientBot.value, 'vpnmanager-client-bot'),
])

const logs = ref([])
const LVL = { info: ['var(--blue)', 'var(--blue-soft)'], ok: ['var(--green)', 'var(--green-soft)'], warning: ['var(--amber)', 'var(--amber-soft)'], error: ['var(--red)', 'var(--red-soft)'] }
const botLogTabs = computed(() => [
  { key: 'admin', label: tr('bots.adminBot') || 'Admin bot' },
  { key: 'client', label: tr('bots.clientBot') || 'Client bot' },
])
const filteredLogs = computed(() => logs.value.filter(l => {
  if (logErrorsOnly.value && l.level !== 'error') return false
  return true
}))
async function refreshBotLogs() { await Promise.all([loadStatus(), loadConfig(), loadLogs()]) }

async function loadLogs() {
  try {
    const { data } = await botsApi.getLogs(logTab.value, 120)
    logs.value = (data.entries || []).map(entry => {
      const [color, bg] = LVL[entry.level] || LVL.info
      const match = entry.message.match(/^(\S+\s+\S+)/)
      return { ts: match ? match[1] : '—', level: entry.level, levelColor: color, levelBg: bg, msg: entry.message, tag: logTab.value }
    }).reverse()
  } catch (e) {
    const [color, bg] = LVL.error
    logs.value = [{ ts: '—', level: 'error', levelColor: color, levelBg: bg, msg: e.response?.data?.detail || e.message, tag: logTab.value }]
  }
}

async function loadStatus() {
  try { const [a, c] = await Promise.all([botsApi.getAdminStatus(), botsApi.getClientStatus()]); adminBot.value = a.data; clientBot.value = c.data }
  catch (e) { err.value = e.response?.data?.detail || e.message }
}
async function loadConfig() {
  try {
    const { data } = await botsApi.getConfig(); cfg.value = data
    form.value.admin_allowed_users = data.admin_allowed_users || ''
    form.value.client_bot_enabled = !!data.client_bot_enabled
    original.value = { admin_allowed_users: form.value.admin_allowed_users, client_bot_enabled: form.value.client_bot_enabled }
  } catch (e) { err.value = e.response?.data?.detail || e.message }
}
async function botAction(bot, action) {
  const key = `${bot}_${action}`; busy[key] = true; err.value = ''; msg.value = ''
  try {
    if ((action === 'stop' || action === 'restart') && !window.confirm(tr('bots.confirmServiceAction') || 'This may briefly interrupt bot service. Continue?')) return
    const fn = { admin_start: botsApi.startAdmin, admin_stop: botsApi.stopAdmin, admin_restart: botsApi.restartAdmin, client_start: botsApi.startClient, client_stop: botsApi.stopClient, client_restart: botsApi.restartClient }[key]
    await fn()
    await loadStatus()
    msg.value = tr('bots.actionDone') || 'Done'
    logs.value.unshift({ ts: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'ok', levelColor: LVL.ok[0], levelBg: LVL.ok[1], msg: `${bot} ${action}`, tag: bot })
    await loadLogs()
    setTimeout(() => msg.value = '', 2500)
  } catch (e) {
    err.value = e.response?.data?.detail || e.message
    logs.value.unshift({ ts: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'error', levelColor: LVL.error[0], levelBg: LVL.error[1], msg: `${bot} ${action}: ${err.value}`, tag: bot })
  } finally { busy[key] = false }
}
async function saveConfig() {
  saving.value = true; err.value = ''; msg.value = ''
  try {
    const payload = {}
    if (form.value.admin_allowed_users !== original.value.admin_allowed_users) payload.admin_allowed_users = form.value.admin_allowed_users
    if (cfg.value?.client_bot_available && form.value.client_bot_enabled !== original.value.client_bot_enabled) payload.client_bot_enabled = form.value.client_bot_enabled
    if (form.value.admin_bot_token) payload.admin_bot_token = form.value.admin_bot_token
    if (cfg.value?.client_bot_available && form.value.client_bot_token) payload.client_bot_token = form.value.client_bot_token
    if (!Object.keys(payload).length) { err.value = tr('bots.noChanges') || 'No changes to save'; return }
    await botsApi.updateConfig(payload)
    form.value.admin_bot_token = ''; form.value.client_bot_token = ''
    await loadConfig(); await loadStatus()
    msg.value = tr('bots.configSaved') || 'Configuration saved'
    logs.value.unshift({ ts: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'ok', levelColor: LVL.ok[0], levelBg: LVL.ok[1], msg: tr('bots.configSaved') || 'Configuration saved', tag: 'all' })
    setTimeout(() => msg.value = '', 2500)
  } catch (e) {
    err.value = e.response?.data?.detail || e.message
    logs.value.unshift({ ts: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), level: 'error', levelColor: LVL.error[0], levelBg: LVL.error[1], msg: `config: ${err.value}`, tag: 'all' })
  } finally { saving.value = false }
}

onMounted(() => {
  ui.set({ title: tr('nav.bots') || 'Bots' })
    loadStatus(); loadConfig(); loadLogs()
})
</script>

<style scoped>
.bot-grid { display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px; }
.field-hint { margin-top:6px;font-size:11.5px;line-height:1.45;color:var(--text-3); }
.feature-note { padding:10px 12px;border-radius:9px;background:var(--accent-soft);color:var(--text-2);font-size:12px;line-height:1.45; }
.d2-btn-primary:hover { background: var(--accent-2) !important; }
.d2-btn-primary:disabled { opacity: .6; cursor: default; }
.d2-btn-ghost:hover { background: var(--panel-2) !important; }
.d2-btn-ghost:disabled { opacity: .6; cursor: default; }
@media (max-width: 820px) {
  .bot-grid { grid-template-columns:minmax(0,1fr); }
  .bot-metrics { grid-template-columns:repeat(3,minmax(0,1fr)) !important; }
  .d2-bot-log-row { display:grid !important;grid-template-columns:auto auto 1fr;gap:6px 8px !important;padding:9px 13px !important; }
  .d2-bot-log-row > span:first-child { font-size:10px;white-space:normal;overflow-wrap:anywhere; }
  .d2-bot-log-row > span:last-child { grid-column:1 / -1;min-width:0;overflow-wrap:anywhere; }
}
</style>
