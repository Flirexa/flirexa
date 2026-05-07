<template>
  <div class="ou-page">
    <!-- Header: title + counter + Live picker -->
    <div class="ou-header">
      <div class="ou-title-block">
        <h2 class="ou-title">{{ $t('onlineUsers.title') }}</h2>
        <p class="ou-sub">{{ $t('onlineUsers.subtitle') }}</p>
      </div>
      <div class="ou-actions">
        <div class="ou-counter" :class="{ 'has-online': onlineCount > 0 }">
          <span class="ou-counter-dot" :class="{ pulse: onlineCount > 0 }"></span>
          <span class="ou-counter-num">{{ onlineCount }}</span>
          <span class="ou-counter-lbl">{{ $t('onlineUsers.connected') }}</span>
        </div>
        <LiveIndicator :live="isLivePoll" v-model:intervalMs="livePollInterval" />
      </div>
    </div>

    <!-- Per-server breakdown chips -->
    <div v-if="byServer.length" class="ou-servers">
      <div v-for="s in byServer" :key="s.id" class="ou-server-chip">
        <i class="mdi mdi-server-network"></i>
        <span class="name">{{ s.name }}</span>
        <span class="dot">·</span>
        <span class="count">{{ s.count }}</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && onlineCount === 0" class="ou-empty">
      <div class="ou-empty-icon"><i class="mdi mdi-access-point-off"></i></div>
      <div class="ou-empty-title">{{ $t('onlineUsers.empty') }}</div>
      <div class="ou-empty-hint">{{ $t('onlineUsers.emptyHint') }}</div>
    </div>

    <!-- Desktop: table -->
    <div v-else class="ou-table-wrap d-none d-md-block">
      <table class="ou-table">
        <thead>
          <tr>
            <th>{{ $t('onlineUsers.colClient') }}</th>
            <th>{{ $t('onlineUsers.colServer') }}</th>
            <th>{{ $t('onlineUsers.colAddress') }}</th>
            <th class="ou-col-time">{{ $t('onlineUsers.colHandshake') }}</th>
            <th class="ou-col-speed">{{ $t('onlineUsers.colSpeed') }}</th>
            <th class="ou-col-traffic">{{ $t('onlineUsers.colTraffic') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in onlineList" :key="c.id">
            <td>
              <div class="ou-client">
                <div class="ou-avatar" :style="{ background: avatarBg(c.name) }">{{ initial(c.name) }}</div>
                <div class="ou-client-name-wrap">
                  <span class="ou-client-name">{{ c.name }}</span>
                  <span class="ou-online-pulse" :title="$t('common.online')"></span>
                </div>
              </div>
            </td>
            <td class="ou-server-name">{{ serverName(c.server_id) }}</td>
            <td class="ou-mono">{{ c.ipv4 || '—' }}</td>
            <td class="ou-time">{{ relativeTime(c.last_handshake) }}</td>
            <td class="ou-speed">
              <span v-if="hasSpeed(c)" class="ou-speed-pair">
                <span class="ou-speed-down" :title="$t('onlineUsers.download')">
                  <i class="mdi mdi-arrow-down-thin"></i>{{ formatRate(rateOf(c).rx) }}
                </span>
                <span class="ou-speed-up" :title="$t('onlineUsers.upload')">
                  <i class="mdi mdi-arrow-up-thin"></i>{{ formatRate(rateOf(c).tx) }}
                </span>
              </span>
              <span v-else class="ou-speed-idle">{{ $t('onlineUsers.idle') }}</span>
            </td>
            <td class="ou-traffic">{{ formatTraffic(c) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Mobile: card list -->
    <div class="ou-cards d-md-none">
      <div v-for="c in onlineList" :key="c.id" class="ou-card">
        <div class="ou-card-top">
          <div class="ou-avatar" :style="{ background: avatarBg(c.name) }">{{ initial(c.name) }}</div>
          <div class="ou-card-main">
            <div class="ou-card-name-row">
              <span class="ou-client-name">{{ c.name }}</span>
              <span class="ou-online-pulse"></span>
            </div>
            <div class="ou-card-meta">
              <i class="mdi mdi-server"></i>
              <span>{{ serverName(c.server_id) }}</span>
              <span class="ou-card-meta-sep">·</span>
              <span class="ou-mono">{{ c.ipv4 || '—' }}</span>
            </div>
          </div>
          <div class="ou-card-time">{{ relativeTime(c.last_handshake) }}</div>
        </div>
        <div v-if="hasSpeed(c)" class="ou-card-speed">
          <span class="ou-speed-down" :title="$t('onlineUsers.download')">
            <i class="mdi mdi-arrow-down-thin"></i>{{ formatRate(rateOf(c).rx) }}
          </span>
          <span class="ou-speed-up" :title="$t('onlineUsers.upload')">
            <i class="mdi mdi-arrow-up-thin"></i>{{ formatRate(rateOf(c).tx) }}
          </span>
        </div>
        <div v-if="formatTraffic(c)" class="ou-card-traffic">
          <i class="mdi mdi-swap-vertical"></i>
          <span>{{ formatTraffic(c) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { clientsApi, serversApi } from '../api'
// rateMap is keyed by client.public_key → { rx, tx } in Mbps
import LiveIndicator from '../components/LiveIndicator.vue'
import { useLivePoll, usePersistedInterval } from '../composables/useLivePoll'
import { formatBytes } from '../utils'

const { t } = useI18n()

const clients = ref([])
const servers = ref([])
const loading = ref(true)
// Per-client live speed snapshot. Refreshed each poll alongside clients/servers.
// Keyed by public_key (the only pubkey present on both bandwidth and clients
// payloads). On the very first poll values may be 0 because the backend's
// bandwidth_monitor needs two snapshots to compute a delta — that's why the
// UI shows "idle" rather than "0.00 Mbps" for zero rates.
const rateMap = ref({})

function rateOf(c) { return rateMap.value[c.public_key] || { rx: 0, tx: 0 } }
function hasSpeed(c) {
  const r = rateOf(c)
  return (r.rx + r.tx) > 0.005   // 5 kbps cutoff so background-keepalive doesn't show as "active"
}
function formatRate(mbps) {
  if (!mbps || mbps < 0.005) return '0'
  if (mbps < 1)   return (mbps * 1000).toFixed(0) + ' kbps'
  if (mbps < 100) return mbps.toFixed(1) + ' Mbps'
  return Math.round(mbps) + ' Mbps'
}
// Tick every second so "X seconds ago" updates between polls without extra
// network calls. Keeps the screen feeling alive between 5s/15s/30s polls.
const _now = ref(Date.now())
setInterval(() => { _now.value = Date.now() }, 1000)

const ONLINE_WINDOW_MS = 3 * 60 * 1000  // 3 minutes — same threshold as Clients page

function isOnline(c) {
  if (!c.last_handshake) return false
  return _now.value - new Date(c.last_handshake).getTime() < ONLINE_WINDOW_MS
}

const onlineList = computed(() =>
  clients.value
    .filter(isOnline)
    // most recent handshake first
    .sort((a, b) => new Date(b.last_handshake).getTime() - new Date(a.last_handshake).getTime())
)
const onlineCount = computed(() => onlineList.value.length)

const byServer = computed(() => {
  const map = new Map()
  for (const c of onlineList.value) {
    const sid = c.server_id
    map.set(sid, (map.get(sid) || 0) + 1)
  }
  return Array.from(map.entries())
    .map(([id, count]) => ({ id, count, name: serverName(id) }))
    .sort((a, b) => b.count - a.count)
})

function serverName(id) {
  const s = servers.value.find(x => x.id === id)
  return s ? s.name : `#${id}`
}

function initial(name) {
  return ((name || '?').trim()[0] || '?').toUpperCase()
}

// Stable hash → hue, so each name keeps the same colour across refreshes.
function avatarBg(name) {
  let h = 0
  const s = name || ''
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xfffffff
  const hue = h % 360
  return `linear-gradient(135deg, hsl(${hue}, 65%, 52%), hsl(${(hue + 40) % 360}, 60%, 42%))`
}

function relativeTime(iso) {
  if (!iso) return '—'
  const diff = _now.value - new Date(iso).getTime()
  const sec = Math.max(0, Math.floor(diff / 1000))
  if (sec < 5)   return t('onlineUsers.justNow') || 'just now'
  if (sec < 60)  return `${sec}s ${t('onlineUsers.ago') || 'ago'}`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${t('onlineUsers.ago') || 'ago'}`
  const hr = Math.floor(min / 60)
  return `${hr}h ${t('onlineUsers.ago') || 'ago'}`
}

function formatTraffic(c) {
  const rx = c.traffic_rx || 0
  const tx = c.traffic_tx || 0
  if (!rx && !tx) return ''
  return `↓ ${formatBytes(rx)} · ↑ ${formatBytes(tx)}`
}

// Live polling: monitoring page deserves a tighter default cadence (5 s)
const livePollInterval = usePersistedInterval('vmm.live.online-users', 5_000)

async function refresh() {
  try {
    const [cRes, sRes] = await Promise.all([
      clientsApi.getAll(),
      serversApi.getAll(),
    ])
    const cData = cRes.data
    clients.value = (cData && cData.items) ? cData.items : (Array.isArray(cData) ? cData : [])
    const sData = sRes.data
    servers.value = (sData && sData.items) ? sData.items : (Array.isArray(sData) ? sData : [])

    // Fan-out to /servers/{id}/bandwidth for every active server in parallel.
    // Each server with online peers contributes its rates; circuit breaker on
    // the backend ensures one unreachable agent doesn't drag the whole call.
    // We don't fail the whole refresh if a single server's bandwidth fetch
    // errors — the corresponding peers just show "idle" until the next poll.
    const targets = servers.value.filter(s => {
      const cat = s.server_category || 'vpn'
      const t = s.server_type || 'wireguard'
      return cat !== 'proxy' && t !== 'hysteria2' && t !== 'tuic'
    })
    const bwResults = await Promise.allSettled(
      targets.map(s => serversApi.getBandwidth(s.id))
    )
    const next = {}
    bwResults.forEach((res, i) => {
      if (res.status !== 'fulfilled') return
      const peers = res.value?.data?.peer_rates || []
      for (const p of peers) {
        next[p.public_key] = { rx: p.rx_rate_mbps || 0, tx: p.tx_rate_mbps || 0 }
      }
    })
    rateMap.value = next
  } catch (e) {
    console.warn('OnlineUsers refresh failed:', e)
  } finally {
    loading.value = false
  }
}

const { isLive: isLivePoll } = useLivePoll(refresh, livePollInterval)

onMounted(refresh)
</script>

<style scoped>
.ou-page {
  padding: 0 0 60px;
}

/* ── Header ─────────────────────────────────────────── */
.ou-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.ou-title-block { min-width: 0; flex: 1; }
.ou-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}
.ou-sub {
  margin: 0;
  font-size: 0.875rem;
  color: var(--bs-secondary-color, #6c757d);
}
.ou-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ── Big counter pill ─────────────────────────────────── */
.ou-counter {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(108, 117, 125, 0.08);
  border: 1px solid rgba(108, 117, 125, 0.18);
  border-radius: 999px;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.ou-counter.has-online {
  background: rgba(40, 167, 69, 0.10);
  border-color: rgba(40, 167, 69, 0.25);
}
.ou-counter-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #adb5bd;
  align-self: center;
}
.ou-counter-dot.pulse {
  background: #28a745;
  box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.55);
  animation: ou-pulse 2s ease-out infinite;
}
.ou-counter-num {
  font-size: 1.4rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #1e7a34;
  line-height: 1;
}
.ou-counter:not(.has-online) .ou-counter-num { color: #6c757d; }
.ou-counter-lbl {
  font-size: 0.78rem;
  color: var(--bs-secondary-color, #6c757d);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}
@keyframes ou-pulse {
  0%   { box-shadow: 0 0 0 0    rgba(40, 167, 69, 0.55); }
  70%  { box-shadow: 0 0 0 10px rgba(40, 167, 69, 0);    }
  100% { box-shadow: 0 0 0 0    rgba(40, 167, 69, 0);    }
}

/* ── Per-server chips ────────────────────────────────── */
.ou-servers {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.ou-server-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: rgba(13, 110, 253, 0.07);
  border: 1px solid rgba(13, 110, 253, 0.18);
  border-radius: 999px;
  font-size: 0.82rem;
  color: #0a58ca;
}
.ou-server-chip .mdi { font-size: 0.95rem; opacity: 0.7; }
.ou-server-chip .name { font-weight: 500; }
.ou-server-chip .dot { opacity: 0.4; margin: 0 -2px; }
.ou-server-chip .count { font-weight: 700; font-variant-numeric: tabular-nums; }

/* ── Empty state ─────────────────────────────────────── */
.ou-empty {
  text-align: center;
  padding: 80px 24px;
  background: rgba(108, 117, 125, 0.04);
  border: 1px dashed rgba(108, 117, 125, 0.25);
  border-radius: 14px;
  color: var(--bs-secondary-color, #6c757d);
}
.ou-empty-icon {
  font-size: 3rem;
  opacity: 0.4;
  margin-bottom: 12px;
}
.ou-empty-title {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--bs-body-color);
}
.ou-empty-hint {
  font-size: 0.875rem;
  max-width: 320px;
  margin: 0 auto;
}

/* ── Desktop table ───────────────────────────────────── */
.ou-table-wrap {
  background: var(--bs-body-bg);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 14px;
  overflow: hidden;
}
.ou-table {
  width: 100%;
  border-collapse: collapse;
}
.ou-table th {
  text-align: left;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--bs-secondary-color, #6c757d);
  font-weight: 600;
  padding: 12px 18px;
  background: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.ou-table td {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  font-size: 0.92rem;
  vertical-align: middle;
}
.ou-table tr:last-child td { border-bottom: none; }
.ou-table tr:hover td { background: rgba(13, 110, 253, 0.02); }
.ou-col-time { width: 130px; }
.ou-col-speed { width: 170px; }
.ou-col-traffic { width: 180px; }

/* Speed cell — desktop and mobile share these */
.ou-speed-pair {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-variant-numeric: tabular-nums;
  font-size: 0.86rem;
}
.ou-speed-down, .ou-speed-up {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.ou-speed-down { color: #16a34a; }
.ou-speed-up   { color: #2563eb; }
.ou-speed-down .mdi, .ou-speed-up .mdi { font-size: 1rem; }
.ou-speed-idle {
  color: var(--bs-secondary-color, #6c757d);
  font-size: 0.78rem;
  font-style: italic;
  opacity: 0.65;
}
.ou-card-speed {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 0.84rem;
  font-variant-numeric: tabular-nums;
}
.ou-card-speed + .ou-card-traffic { margin-top: 6px; padding-top: 6px; border-top: none; }

.ou-client {
  display: flex; align-items: center; gap: 12px;
  min-width: 0;
}
.ou-avatar {
  flex-shrink: 0;
  width: 34px; height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center; justify-content: center;
  color: white;
  font-weight: 600;
  font-size: 0.95rem;
  letter-spacing: -0.01em;
  user-select: none;
}
.ou-client-name-wrap {
  display: flex; align-items: center; gap: 8px;
  min-width: 0;
}
.ou-client-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ou-online-pulse {
  flex-shrink: 0;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #28a745;
  box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.55);
  animation: ou-pulse 2s ease-out infinite;
}
.ou-server-name { color: var(--bs-secondary-color, #6c757d); font-size: 0.88rem; }
.ou-mono { font-family: 'JetBrains Mono', 'Menlo', 'Monaco', monospace; font-size: 0.84rem; }
.ou-time { font-size: 0.85rem; color: var(--bs-secondary-color, #6c757d); font-variant-numeric: tabular-nums; }
.ou-traffic { font-size: 0.82rem; color: var(--bs-secondary-color, #6c757d); font-variant-numeric: tabular-nums; }

/* ── Mobile cards ────────────────────────────────────── */
.ou-cards { display: flex; flex-direction: column; gap: 10px; }
.ou-card {
  background: var(--bs-body-bg);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.ou-card:active { transform: scale(0.99); }
.ou-card-top {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.ou-card-main { flex: 1; min-width: 0; }
.ou-card-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.ou-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  color: var(--bs-secondary-color, #6c757d);
  margin-top: 2px;
  min-width: 0;
}
.ou-card-meta .mdi { font-size: 0.92rem; opacity: 0.6; flex-shrink: 0; }
.ou-card-meta-sep { opacity: 0.4; flex-shrink: 0; }
.ou-card-meta > span:not(.ou-card-meta-sep) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.ou-card-time {
  flex-shrink: 0;
  font-size: 0.78rem;
  color: var(--bs-secondary-color, #6c757d);
  font-variant-numeric: tabular-nums;
  text-align: right;
  align-self: flex-start;
  padding-top: 3px;
}
.ou-card-traffic {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--bs-secondary-color, #6c757d);
  font-variant-numeric: tabular-nums;
}
.ou-card-traffic .mdi { opacity: 0.6; }

/* Dark theme — applied via the panel's manual theme toggle (data-theme="dark"
   on <html>), NOT prefers-color-scheme. The earlier prefers-color-scheme
   block was DEAD CODE because the app sets the theme attribute manually,
   so muted text was rendering at light-mode contrast on a dark background
   and ended up basically invisible. */
[data-theme="dark"] .ou-page,
[data-theme="dark"] .ou-title,
[data-theme="dark"] .ou-empty-title { color: #e9ecef; }

/* Lighter muted greys — Bootstrap's gray-400 (#ced4da) reads cleanly on
   the panel's dark surface; gray-500 (#adb5bd) for slightly less
   important text. Anything dimmer than #adb5bd disappears. */
[data-theme="dark"] .ou-sub,
[data-theme="dark"] .ou-empty-hint,
[data-theme="dark"] .ou-server-name,
[data-theme="dark"] .ou-mono,
[data-theme="dark"] .ou-time,
[data-theme="dark"] .ou-traffic,
[data-theme="dark"] .ou-card-meta,
[data-theme="dark"] .ou-card-time,
[data-theme="dark"] .ou-card-traffic { color: #adb5bd; }

[data-theme="dark"] .ou-counter-lbl { color: #ced4da; }

/* "0 connected" pill when nobody is online — was unreadable charcoal-on-charcoal */
[data-theme="dark"] .ou-counter:not(.has-online) {
  background: rgba(173, 181, 189, 0.10);
  border-color: rgba(173, 181, 189, 0.20);
}
[data-theme="dark"] .ou-counter:not(.has-online) .ou-counter-num { color: #ced4da; }
[data-theme="dark"] .ou-counter.has-online {
  background: rgba(40, 167, 69, 0.18);
  border-color: rgba(40, 167, 69, 0.35);
}
[data-theme="dark"] .ou-counter.has-online .ou-counter-num { color: #4ddf6e; }

/* Per-server chips — blue glow on dark works only if both fg and bg are bumped */
[data-theme="dark"] .ou-server-chip {
  background: rgba(99, 132, 253, 0.14);
  border-color: rgba(99, 132, 253, 0.30);
  color: #93b5ff;
}

/* Cards / table — borrow the surface colour from the panel's theme tokens
   when present, fallback to a hard value matching the rest of the panel.  */
[data-theme="dark"] .ou-table-wrap,
[data-theme="dark"] .ou-card {
  background: var(--vxy-card-bg, #1f232a);
  border-color: var(--vxy-border, rgba(255, 255, 255, 0.08));
}
[data-theme="dark"] .ou-table th {
  background: rgba(255, 255, 255, 0.04);
  border-bottom-color: rgba(255, 255, 255, 0.08);
  color: #adb5bd;   /* the small-caps column headers were bordering invisible */
}
[data-theme="dark"] .ou-table td { border-bottom-color: rgba(255, 255, 255, 0.06); }
[data-theme="dark"] .ou-table tr:hover td { background: rgba(99, 132, 253, 0.05); }

[data-theme="dark"] .ou-empty {
  background: rgba(255, 255, 255, 0.025);
  border-color: rgba(255, 255, 255, 0.12);
}
[data-theme="dark"] .ou-card-traffic,
[data-theme="dark"] .ou-card-speed { border-top-color: rgba(255, 255, 255, 0.08); }

/* Speed arrows: green/blue scaled up so the cell pops out of the row */
[data-theme="dark"] .ou-speed-down { color: #4ade80; }
[data-theme="dark"] .ou-speed-up   { color: #60a5fa; }
[data-theme="dark"] .ou-speed-idle { color: #6c757d; }

/* Belt-and-suspenders: also keep the prefers-color-scheme variant so
   browsers in OS-dark with default theme=light still get readable greys.
   Same selectors at media level — duplicated, but small. */
@media (prefers-color-scheme: dark) {
  .ou-sub, .ou-empty-hint, .ou-server-name, .ou-mono,
  .ou-time, .ou-traffic, .ou-card-meta, .ou-card-time, .ou-card-traffic { color: #adb5bd; }
  .ou-counter-lbl { color: #ced4da; }
}

/* Tighter spacing on phones */
@media (max-width: 600px) {
  .ou-title { font-size: 1.25rem; }
  .ou-counter { padding: 8px 14px; }
  .ou-counter-num { font-size: 1.2rem; }
  .ou-actions { width: 100%; justify-content: space-between; }
}

@media (prefers-reduced-motion: reduce) {
  .ou-counter-dot.pulse, .ou-online-pulse { animation: none; }
}
</style>
