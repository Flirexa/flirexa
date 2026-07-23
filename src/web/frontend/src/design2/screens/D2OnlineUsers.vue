<!-- Online Users — his exact 1:1 layout: 3 stat cards / server chips + live pulse +
     poll-interval select / table (avatar+name·server·IP·speed·total·since) with empty state.
     Wired to clientsApi.getAll + serversApi.getAll + serversApi.getBandwidth (per-peer live rates). -->
<template>
  <div class="d2-ou-root">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px">
      <div v-for="s in onlineStats" :key="s.label" style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ s.label }}</div>
        <div :style="{ fontSize:'26px', fontWeight:680, letterSpacing:'-.02em', marginTop:'8px', color:s.color }">{{ s.value }}</div>
      </div>
    </div>

    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px;align-items:center">
      <button v-for="ch in serverChips" :key="ch.key" @click="ch.on" :style="{ height:'32px', padding:'0 13px', border:'1px solid '+ch.border, background:ch.bg, color:ch.color, borderRadius:'8px', font:'inherit', fontSize:'12.5px', fontWeight:ch.weight, cursor:'pointer' }">{{ ch.label }}</button>
      <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--text-3)"><span style="width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s ease-in-out infinite"></span>{{ tr('onlineUsers.live') || 'Live' }}</span>
        <select :value="onlineInterval" @change="onOnlineInterval" style="height:32px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;padding:0 8px;font:inherit;font-size:12.5px;outline:none;cursor:pointer"><option value="5">5 {{ tr('onlineUsers.sec') || 'sec' }}</option><option value="10">10 {{ tr('onlineUsers.sec') || 'sec' }}</option><option value="30">30 {{ tr('onlineUsers.sec') || 'sec' }}</option><option value="60">60 {{ tr('onlineUsers.sec') || 'sec' }}</option></select>
      </div>
    </div>

    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div v-if="!onlineUsers.length" style="padding:56px 24px;text-align:center"><div style="width:54px;height:54px;border-radius:14px;background:var(--gray-soft);color:var(--text-3);display:flex;align-items:center;justify-content:center;margin:0 auto 14px"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 12h4l2-5 4 10 2-5h6"></path></svg></div><div style="font-size:15px;font-weight:600">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('onlineUsers.emptyTitle') || 'No one online') }}</div><div style="font-size:13px;color:var(--text-3);margin-top:4px">{{ tr('onlineUsers.emptySub') || 'Active clients will appear here in real time' }}</div></div>

      <div v-else style="overflow-x:auto">
        <table data-rtab data-rcollapse style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left">
            <th style="padding:11px 20px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('onlineUsers.client') || 'Client' }}</th>
            <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('onlineUsers.server') || 'Server' }}</th>
            <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">IP</th>
            <th style="padding:11px 12px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('onlineUsers.speed') || 'Speed' }}</th>
            <th style="padding:11px 12px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('onlineUsers.total') || 'Total' }}</th>
            <th style="padding:11px 20px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('onlineUsers.since') || 'Since' }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="u in onlineUsers" :key="u.id" class="d2-ou-row" style="border-top:1px solid var(--border)">
              <td data-mhead style="padding:12px 20px"><div style="display:flex;align-items:center;gap:10px"><div style="position:relative;flex:none"><span style="width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:650">{{ u.initials }}</span><span style="position:absolute;right:-1px;bottom:-1px;width:9px;height:9px;border-radius:50%;background:var(--green);border:2px solid var(--panel);animation:pulse 2s ease-in-out infinite"></span></div><div style="min-width:0"><div style="font-weight:550">{{ u.name }}</div><div style="font-size:11.5px;color:var(--text-3)">{{ u.email }}</div></div></div></td>
              <td :data-label="tr('onlineUsers.server') || 'Server'" style="padding:12px 12px;color:var(--text-2)">{{ u.server }}</td>
              <td data-label="IP" style="padding:12px 12px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2)">{{ u.ip }}</td>
              <td :data-label="tr('onlineUsers.speed') || 'Speed'" style="padding:12px 12px;text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px"><span style="color:var(--green)">↓{{ u.rx }}</span> <span style="color:var(--blue)">↑{{ u.tx }}</span></td>
              <td :data-label="tr('onlineUsers.total') || 'Total'" style="padding:12px 12px;text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2)">{{ u.total }}</td>
              <td :data-label="tr('onlineUsers.since') || 'Since'" style="padding:12px 20px;text-align:right;color:var(--text-3);font-size:12px">{{ u.since }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { clientsApi, serversApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const clients = ref([])
const servers = ref([])
const rateMap = ref({})
const loading = ref(true)
const filterServer = ref(null)
const onlineInterval = ref(5)
let timer = null, inflight = false

function isOnline(c) { return c.last_handshake ? (Date.now() - new Date(c.last_handshake).getTime() < 180000) : false }
const onlineAll = computed(() => clients.value.filter(isOnline))
const onlineList = computed(() => filterServer.value ? onlineAll.value.filter(c => c.server_id === filterServer.value) : onlineAll.value)
const serversWithOnline = computed(() => servers.value.filter(s => onlineAll.value.some(c => c.server_id === s.id)))
function countFor(id) { return onlineAll.value.filter(c => c.server_id === id).length }
function srvName(id) { return servers.value.find(s => s.id === id)?.name || '—' }
function rate(c) { return rateMap.value[c.public_key] || { rx: 0, tx: 0 } }
function rel(d) { const m = Math.floor((Date.now() - new Date(d).getTime()) / 60000); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; return `${Math.floor(m / 60)}h ago` }

async function refresh() {
  if (inflight) return; inflight = true
  try {
    // getOnline() = server-side handshake filter; payload scales with the
    // online count, not total clients (this poll runs every 5s; getAll()
    // re-downloaded every row each tick). getAll() fallback covers a
    // mixed-version deploy mid-update.
    const [cRes, sRes] = await Promise.all([clientsApi.getOnline().catch(() => clientsApi.getAll()), serversApi.getAll()])
    const cd = cRes.data; clients.value = (cd && cd.items) ? cd.items : (Array.isArray(cd) ? cd : [])
    const sd = sRes.data; servers.value = (sd && sd.items) ? sd.items : (Array.isArray(sd) ? sd : [])
    const targets = servers.value.filter(s => (s.server_category || 'vpn') !== 'proxy' && !['hysteria2', 'tuic'].includes(s.server_type || 'wireguard'))
    const bw = await Promise.allSettled(targets.map(s => serversApi.getBandwidth(s.id)))
    const next = {}
    bw.forEach(r => { if (r.status !== 'fulfilled') return; for (const p of (r.value?.data?.peer_rates || [])) next[p.public_key] = { rx: p.rx_rate_mbps || 0, tx: p.tx_rate_mbps || 0 } })
    rateMap.value = next
  } catch (e) { console.warn('online refresh failed', e) } finally { loading.value = false; inflight = false }
}
function startTimer() { if (timer) clearInterval(timer); timer = setInterval(refresh, onlineInterval.value * 1000) }
function onOnlineInterval(e) { onlineInterval.value = Number(e.target.value) || 5; startTimer() }

// ── adapters onto his markup field names ──────────────────────────────────
function initialsOf(name) { const parts = String(name || '?').trim().split(/\s+/); return ((parts[0]?.[0] || '') + (parts[1]?.[0] || parts[0]?.[1] || '')).toUpperCase() || '?' }
function fmtGb(bytes) { const b = Number(bytes || 0); if (b >= 1e9) return (b / 1e9).toFixed(2) + ' GB'; if (b >= 1e6) return (b / 1e6).toFixed(1) + ' MB'; return (b / 1e3).toFixed(0) + ' KB' }

const onlineStats = computed(() => {
  const dl = onlineAll.value.reduce((a, c) => a + rate(c).rx, 0)
  const ul = onlineAll.value.reduce((a, c) => a + rate(c).tx, 0)
  return [
    { label: tr('onlineUsers.onlineNow') || 'Online now', value: onlineAll.value.length, color: 'var(--green)' },
    { label: tr('onlineUsers.download') || 'Download', value: dl.toFixed(1) + ' Mbps', color: 'var(--text)' },
    { label: tr('onlineUsers.upload') || 'Upload', value: ul.toFixed(1) + ' Mbps', color: 'var(--blue)' },
  ]
})

const serverChips = computed(() => {
  const chips = [{
    key: 'all',
    label: (tr('onlineUsers.showAll') || 'All servers') + ' (' + onlineAll.value.length + ')',
    on: () => { filterServer.value = null },
    active: !filterServer.value,
  }]
  for (const s of serversWithOnline.value) {
    const active = filterServer.value === s.id
    chips.push({ key: s.id, label: s.name + ' (' + countFor(s.id) + ')', on: () => { filterServer.value = s.id }, active })
  }
  return chips.map(ch => ({
    ...ch,
    border: ch.active ? 'var(--accent)' : 'var(--border-strong)',
    bg: ch.active ? 'var(--accent-soft)' : 'var(--panel)',
    color: ch.active ? 'var(--accent)' : 'var(--text-2)',
    weight: ch.active ? 600 : 500,
  }))
})

const onlineUsers = computed(() => onlineList.value.map(c => {
  const r = rate(c)
  return {
    id: c.id,
    initials: initialsOf(c.name),
    name: c.name || '—',
    email: c.email || c.telegram_username || '',
    server: srvName(c.server_id),
    ip: c.ipv4 || '—',
    rx: r.rx.toFixed(2),
    tx: r.tx.toFixed(2),
    total: fmtGb((c.total_rx_bytes || 0) + (c.total_tx_bytes || 0)),
    since: c.last_handshake ? rel(c.last_handshake) : '—',
  }
}))

onMounted(() => {
  ui.set({ title: tr('nav.onlineUsers') || 'Online users' })
  refresh(); startTimer()
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-ou-row:hover { background: var(--panel-2); }
</style>

<!-- His live dots use `animation:pulse` inline (not scope-rewritten), so the
     keyframes must be global. design2 defines no @keyframes pulse anywhere. -->
<style>
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
</style>
