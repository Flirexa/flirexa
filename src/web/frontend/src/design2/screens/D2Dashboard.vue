<!-- Dashboard — reproduced 1:1 from the designer's markup (his stat/revenue
     cards, inline-SVG charts: revenue area+line, registration bars, subscription
     donut, payment-by-method bars, CPU/RAM/Disk radial gauges, mini Leaflet map,
     traffic bars, activity feed, recent-clients table, servers list).
     Wired to systemApi.getStatus, portalUsersApi.getRevenueStats/getChartData,
     clientsApi.getAll/getMapData, serversApi.getAll, systemApi.getLogs. -->
<template>
  <div class="d2-dash">
    <!-- banners -->
    <div v-if="showExpiryBanner || trafficExceeded > 0" style="display:flex;flex-direction:column;gap:10px;margin-bottom:14px">
      <div v-if="showExpiryBanner" style="display:flex;align-items:center;gap:10px;padding:12px 16px;border:1px solid var(--amber-soft);background:var(--amber-soft);border-radius:12px">
        <span style="color:var(--amber);display:flex;flex:none"><Icon name="bell" :size="17" /></span>
        <span style="font-size:13px;color:var(--text);font-weight:500;flex:1"><b>{{ expiringWeek }}</b> {{ tr('d.banner_expiry') || 'clients expiring within 7 days' }}</span>
        <button @click="$router.push('/clients?expiring=1')" style="border:none;background:transparent;color:var(--amber);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('d.banner_view') || 'View' }}</button>
        <button @click="dismissExpiry" :title="tr('common.dismiss') || 'Dismiss'" aria-label="Dismiss" style="border:none;background:transparent;color:var(--amber);font:inherit;font-size:17px;line-height:1;cursor:pointer;padding:0 4px;flex:none">×</button>
      </div>
      <div v-if="trafficExceeded > 0" style="display:flex;align-items:center;gap:10px;padding:12px 16px;border:1px solid var(--red-soft);background:var(--red-soft);border-radius:12px">
        <span style="color:var(--red);display:flex;flex:none"><Icon name="gauge" :size="17" /></span>
        <span style="font-size:13px;color:var(--text);font-weight:500;flex:1"><b>{{ trafficExceeded }}</b> {{ tr('d.banner_traffic') || 'clients over their traffic limit' }}</span>
        <button @click="$router.push('/clients')" style="border:none;background:transparent;color:var(--red);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('d.banner_view') || 'View' }}</button>
      </div>
    </div>

    <!-- stats -->
    <div class="d2-grid4">
      <div v-for="s in statCards" :key="s.label" class="d2-card">
        <div style="display:flex;align-items:center;justify-content:space-between"><span style="font-size:12.5px;color:var(--text-2)">{{ s.label }}</span><span v-if="s.delta" :style="{ fontSize:'10.5px', fontWeight:600, color:s.deltaColor, background:s.deltaBg, padding:'2px 7px', borderRadius:'20px' }">{{ s.delta }}</span></div>
        <div style="font-size:28px;font-weight:680;letter-spacing:-.02em;margin-top:10px">{{ s.value }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-top:2px">{{ s.sub }}</div>
      </div>
    </div>

    <!-- revenue cards -->
    <div class="d2-grid4" style="margin-top:14px">
      <div v-for="s in revCards" :key="s.label" class="d2-card">
        <div style="display:flex;align-items:center;gap:8px"><span :style="{ width:'30px', height:'30px', borderRadius:'8px', background:s.iconBg, color:s.iconColor, display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }"><Icon :name="s.icon" :size="16" /></span><span style="font-size:12.5px;color:var(--text-2)">{{ s.label }}</span></div>
        <div style="font-size:26px;font-weight:680;letter-spacing:-.02em;margin-top:10px">{{ s.value }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-top:2px">{{ s.sub }}</div>
      </div>
    </div>

    <!-- charts row -->
    <div class="d2-grid3" style="margin-top:14px">
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:2px">{{ tr('dashboard.revenueTrend') || 'Revenue trend' }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">{{ tr('d.revenue_sub') || 'last 12 months' }}</div>
        <svg viewBox="0 0 300 120" preserveAspectRatio="none" style="width:100%;height:110px;display:block"><defs><linearGradient id="revgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--accent)" stop-opacity="0.28"/><stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs><path :d="revPath.area" fill="url(#revgrad)"/><path :d="revPath.line" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/></svg>
      </div>
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:2px">{{ tr('dashboard.userGrowth') || 'Registrations' }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">{{ tr('d.reg_sub') || 'new users' }}</div>
        <div style="display:flex;align-items:flex-end;gap:5px;height:110px">
          <div v-for="(b, i) in regBars" :key="i" style="flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;height:100%;justify-content:flex-end"><div :style="{ width:'100%', borderRadius:'4px 4px 2px 2px', background:b.fill, height: b.h }"></div><span style="font-size:9px;color:var(--text-3)">{{ b.label }}</span></div>
          <div v-if="!regBars.length" style="color:var(--text-3);font-size:12px;margin:auto">{{ tr('common.noData') || 'No data' }}</div>
        </div>
      </div>
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('d.sub_dist') || 'Subscription distribution' }}</div>
        <div style="display:flex;align-items:center;gap:16px">
          <div style="position:relative;width:104px;height:104px;flex:none"><svg viewBox="0 0 36 36" style="width:104px;height:104px;transform:rotate(-90deg)"><circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--panel-3)" stroke-width="4"/><circle v-for="(d, i) in donutSegs" :key="i" cx="18" cy="18" r="15.9" fill="none" :stroke="d.color" stroke-width="4" :stroke-dasharray="d.dash" :stroke-dashoffset="d.offset"/></svg><div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center"><span style="font-size:18px;font-weight:680">{{ donutTotal }}</span></div></div>
          <div style="flex:1;display:flex;flex-direction:column;gap:8px"><div v-for="(d, i) in donutSegs" :key="i" style="display:flex;align-items:center;gap:8px;font-size:12px"><span :style="{ width:'9px', height:'9px', borderRadius:'3px', background:d.color, flex:'none' }"></span><span style="color:var(--text-2);flex:1">{{ d.label }}</span><span class="mono" style="font-weight:600">{{ d.value }}</span></div></div>
        </div>
      </div>
    </div>

    <!-- payment method + gauges + map -->
    <div class="d2-grid3" style="margin-top:14px">
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('d.pay_method') || 'Payments by method' }}</div>
        <div style="display:flex;flex-direction:column;gap:11px">
          <div v-for="(m, i) in payMethods" :key="i"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--text-2)">{{ m.label }}</span><span class="mono" style="color:var(--text-3)">{{ m.amount }}</span></div><div style="height:7px;border-radius:5px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'5px', background:m.color, width:m.pct }"></div></div></div>
          <div v-if="!payMethods.length" style="color:var(--text-3);font-size:12px">{{ tr('common.noData') || 'No data' }}</div>
        </div>
      </div>
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('d.sys_health') || 'System resources' }}</div>
        <div style="display:flex;justify-content:space-around;align-items:center">
          <div v-for="(g, i) in gauges" :key="i" style="display:flex;flex-direction:column;align-items:center;gap:7px"><div style="position:relative;width:74px;height:74px"><svg viewBox="0 0 36 36" style="width:74px;height:74px;transform:rotate(-90deg)"><circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--panel-3)" stroke-width="3.5"/><circle cx="18" cy="18" r="15.9" fill="none" :stroke="g.color" stroke-width="3.5" :stroke-dasharray="g.dash" stroke-linecap="round"/></svg><div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:680" class="mono">{{ g.value }}</div></div><span style="font-size:11.5px;color:var(--text-3)">{{ g.label }}</span></div>
        </div>
      </div>
      <div class="d2-card2">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px"><div style="font-weight:600;font-size:14px">{{ tr('d.map') || 'Client map' }}</div><span style="font-size:11px;color:var(--text-3);display:flex;align-items:center;gap:5px"><span class="d2-pulse" style="width:6px;height:6px;border-radius:50%;background:var(--green)"></span>{{ tr('d.map_live') || 'live' }}</span></div>
        <div style="position:relative">
          <div ref="mapEl" @click="openMap" style="height:120px;border-radius:11px;overflow:hidden;background:var(--panel-2);border:1px solid var(--border);z-index:0;cursor:pointer"></div>
          <button @click.stop="openMap" :title="tr('dashboard.expandMap') || 'Expand map'" style="position:absolute;bottom:8px;right:8px;z-index:1;width:30px;height:30px;border-radius:8px;border:1px solid var(--border);background:var(--panel);color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"></path></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- traffic + events -->
    <div class="d2-grid-main" style="margin-top:14px">
      <div class="d2-card2">
        <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:16px"><div><div style="font-weight:600;font-size:14px">{{ tr('d.traffic') || 'Traffic' }}</div><div style="font-size:12px;color:var(--text-3);margin-top:1px">{{ tr('d.traffic_sub') || 'total over 14 days' }}</div></div><div class="mono" style="font-size:13px;color:var(--text-2)">{{ dashTrafficTotal }}</div></div>
        <div style="display:flex;align-items:flex-end;gap:5px;height:150px">
          <div v-for="(b, i) in trafficBars" :key="i" style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;height:100%;justify-content:flex-end"><div :style="{ width:'100%', borderRadius:'5px 5px 2px 2px', background:b.fill, height:b.h }"></div><span style="font-size:9.5px;color:var(--text-3)">{{ b.label }}</span></div>
          <div v-if="!trafficBars.length" style="color:var(--text-3);font-size:12px;margin:auto">{{ tr('common.noData') || 'No data' }}</div>
        </div>
      </div>
      <div class="d2-card2">
        <div style="font-weight:600;font-size:14px;margin-bottom:4px">{{ tr('d.events') || 'Recent events' }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-bottom:14px">{{ tr('d.events_sub') || 'activity log' }}</div>
        <div style="display:flex;flex-direction:column;gap:13px">
          <div v-for="(a, i) in activity" :key="i" style="display:flex;gap:11px"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:a.color, marginTop:'6px', flex:'none' }"></span><div style="min-width:0"><div style="font-size:12.5px;color:var(--text);line-height:1.4">{{ a.text }}</div><div style="font-size:11px;color:var(--text-3);margin-top:1px">{{ a.time }}</div></div></div>
          <div v-if="!activity.length" style="color:var(--text-3);font-size:12px">{{ tr('common.noData') || 'No recent events' }}</div>
        </div>
      </div>
    </div>

    <!-- recent clients + servers -->
    <div class="d2-grid-main" style="margin-top:14px">
      <div class="d2-card2" style="padding:0;overflow:hidden">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px 12px"><div style="font-weight:600;font-size:14px">{{ tr('dashboard.clientsOverview') || 'Recent clients' }}</div><button @click="$router.push('/clients')" style="border:none;background:transparent;color:var(--accent);font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('dashboard.viewAll') || 'View all' }}</button></div>
        <div class="d2-desktop-only" style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left;border-top:1px solid var(--border)"><th class="d2-th">{{ tr('clients.name') || 'Name' }}</th><th class="d2-th">{{ tr('clients.server') || 'Server' }}</th><th class="d2-th">{{ tr('clients.traffic') || 'Traffic' }}</th><th class="d2-th">{{ tr('c.th_bw') || 'Bandwidth' }}</th><th class="d2-th">{{ tr('clients.status') || 'Status' }}</th></tr></thead>
          <tbody>
            <tr v-for="c in recentClients" :key="c.id" style="border-top:1px solid var(--border)"><td style="padding:11px 20px"><div style="font-weight:550">{{ c.name }}</div><div class="mono" style="font-size:11.5px;color:var(--text-3)">{{ c.ip }}</div></td><td style="padding:11px 12px;color:var(--text-2)">{{ c.server }}</td><td class="mono" style="padding:11px 12px;font-size:12px;color:var(--text-2)">{{ c.traffic }}</td><td class="mono" style="padding:11px 12px;font-size:12px;color:var(--text-2)">{{ c.bw }}</td><td style="padding:11px 12px"><span :style="{ display:'inline-flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:550, color:c.statusColor }"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:c.statusColor }"></span>{{ c.statusLabel }}</span></td></tr>
            <tr v-if="!recentClients.length"><td colspan="5" style="padding:20px;text-align:center;color:var(--text-3)">{{ tr('dashboard.noClients') || 'No clients' }}</td></tr>
          </tbody>
        </table></div>
        <div class="d2-mobile-only d2-mobile-list" style="padding:0 12px 12px">
          <article v-for="c in recentClients" :key="'mobile-'+c.id" class="d2-mobile-item" style="box-shadow:none">
            <div class="d2-mobile-summary">
              <span :style="{width:'8px',height:'8px',borderRadius:'50%',background:c.statusColor,flex:'none'}"></span>
              <div class="d2-mobile-main">
                <div class="d2-mobile-title">{{ c.name }}</div>
                <div class="d2-mobile-sub">{{ c.server }} · {{ c.ip }}</div>
              </div>
              <div style="text-align:right;flex:none"><div class="mono" style="font-size:12px;font-weight:600">{{ c.traffic }}</div><div style="font-size:10.5px;color:var(--text-3)">{{ c.statusLabel }}</div></div>
            </div>
          </article>
          <div v-if="!recentClients.length" style="padding:18px;text-align:center;color:var(--text-3)">{{ tr('dashboard.noClients') || 'No clients' }}</div>
        </div>
      </div>
      <div class="d2-card2">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px"><div style="font-weight:600;font-size:14px">{{ tr('dashboard.servers') || 'Servers' }}</div><button @click="$router.push('/servers')" style="border:none;background:transparent;color:var(--accent);font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('d.manage') || 'Manage' }}</button></div>
        <div style="display:flex;flex-direction:column;gap:10px">
          <div v-for="s in dashServers" :key="s.id" style="display:flex;align-items:center;gap:11px;padding:10px 12px;border:1px solid var(--border);border-radius:10px"><span :style="{ width:'8px', height:'8px', borderRadius:'50%', background:s.statusColor, flex:'none' }"></span><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ s.name }}</div><div style="font-size:11.5px;color:var(--text-3)">{{ s.region }}</div></div><div style="text-align:right;font-size:11.5px;color:var(--text-3)"><div class="mono" style="color:var(--text-2)">{{ s.clients }}</div>{{ tr('d.peers') || 'peers' }}</div></div>
          <div v-if="!dashServers.length" style="color:var(--text-3);font-size:12px">{{ tr('dashboard.noServers') || 'No servers' }}</div>
        </div>
      </div>
    </div>

    <!-- Full client map modal (his: click the mini map to expand into a big
         centered modal with the full Leaflet map + live badge). -->
    <D2Modal :open="mapModalOpen" size="xl" flush @close="closeMap">
      <template #header>
        <div style="display:flex;align-items:center;gap:10px"><h3 style="font-size:16px;font-weight:650;margin:0">{{ tr('dashboard.clientMap') || 'Client map' }}</h3></div>
        <span style="font-size:11.5px;color:var(--text-3);display:flex;align-items:center;gap:6px;margin-left:auto;margin-right:10px"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('dashboard.realtime') || 'real-time' }}</span>
      </template>
      <div ref="bigMapEl" style="width:100%;height:min(70vh,620px);background:var(--panel-2)"></div>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { systemApi, clientsApi, serversApi, portalUsersApi, silentPoll } from '../../api'
import { formatBytes } from '../../utils'
import { linePath } from '../charts.js'
import { useD2Ui } from '../../stores/d2ui'
import D2Modal from '../ui/D2Modal.vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import Icon from '../ui/Icon.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const stats = ref({}); const revenue = ref({}); const charts = ref({ revenue_trend: [], user_trend: [], sub_distribution: {}, payment_methods: {}, traffic_trend: [] })
const clients = ref([]); const servers = ref([]); const events = ref([])
const mapEl = ref(null)
const bigMapEl = ref(null)
const mapModalOpen = ref(false)

const expiringWeek = computed(() => stats.value.expiry?.expiring_week ?? 0)
const trafficExceeded = computed(() => stats.value.traffic?.exceeded_count ?? 0)

// Dismissable expiry banner. We remember the count it was dismissed at, so the
// banner stays hidden while the number is unchanged (or lower) but reappears if
// MORE clients start expiring — an increase is worth surfacing again.
const _EXPIRY_DISMISS_KEY = 'd2_dash_expiry_dismissed'
const expiryDismissedAt = ref((() => { try { return parseInt(localStorage.getItem(_EXPIRY_DISMISS_KEY) || '0', 10) || 0 } catch (_) { return 0 } })())
const showExpiryBanner = computed(() => expiringWeek.value > 0 && expiringWeek.value > expiryDismissedAt.value)
function dismissExpiry() {
  expiryDismissedAt.value = expiringWeek.value
  try { localStorage.setItem(_EXPIRY_DISMISS_KEY, String(expiringWeek.value)) } catch (_) {}
}

const statCards = computed(() => {
  const totalClients = stats.value.clients?.total ?? 0
  const activeClients = stats.value.clients?.active ?? 0
  const srvTotal = stats.value.servers?.total ?? 0
  const srvOnline = stats.value.servers?.online ?? 0
  const allServersOk = srvTotal > 0 && srvOnline === srvTotal
  return [
    { label: tr('dashboard.totalClients') || 'Total clients', value: stats.value.clients?.total ?? '—', sub: activeClients + ' ' + (tr('dashboard.activeClients') || 'active'),
      delta: activeClients ? '+' + activeClients : '', deltaColor: 'var(--green)', deltaBg: 'var(--green-soft)' },
    { label: tr('common.online') || 'Online now', value: stats.value.clients?.active ?? '—', sub: tr('d.active_conns') || 'active connections',
      delta: tr('d.live') || 'live', deltaColor: 'var(--accent)', deltaBg: 'var(--accent-soft)' },
    { label: tr('dashboard.servers') || 'Servers', value: srvOnline + ' / ' + srvTotal, sub: tr('d.online_total') || 'online / total',
      delta: allServersOk ? 'ok' : '!', deltaColor: allServersOk ? 'var(--green)' : 'var(--amber)', deltaBg: allServersOk ? 'var(--green-soft)' : 'var(--amber-soft)' },
    { label: tr('dashboard.totalTraffic') || 'Traffic (total)', value: stats.value.traffic?.total_formatted ?? '—', sub: tr('d.traffic_sub') || 'over 14 days',
      delta: '', deltaColor: 'var(--green)', deltaBg: 'var(--green-soft)' },
  ]
})
const revCards = computed(() => [
  { icon: 'trendup', iconBg: 'var(--green-soft)', iconColor: 'var(--green)', label: tr('dashboard.revenue30d') || '30-day revenue', value: '$' + (revenue.value.revenue_30d ?? 0), sub: tr('dashboard.last30Days') || 'last 30 days' },
  { icon: 'wallet', iconBg: 'var(--accent-soft)', iconColor: 'var(--accent)', label: tr('dashboard.revenue') || 'Total revenue', value: '$' + (revenue.value.total_revenue ?? 0), sub: tr('dashboard.revenue') || 'all time' },
  { icon: 'crown', iconBg: 'var(--purple-soft)', iconColor: 'var(--purple)', label: tr('d.active_subs') || 'Active subscriptions', value: revenue.value.active_subscriptions ?? 0, sub: tr('subscriptions.active') || 'paid' },
  { icon: 'users', iconBg: 'var(--blue-soft)', iconColor: 'var(--blue)', label: tr('d.portal_users') || 'Portal users', value: revenue.value.total_users ?? 0, sub: tr('nav.portalUsers') || 'registered' },
])
const revPath = computed(() => linePath((charts.value.revenue_trend || []).map(d => d.amount ?? d.value ?? 0)))
const regBars = computed(() => {
  const arr = charts.value.user_trend || []; const max = Math.max(1, ...arr.map(d => d.count ?? d.value ?? 0)); const n = arr.length
  return arr.map((d, i) => ({ h: Math.round(((d.count ?? d.value ?? 0) / max) * 100) + '%', label: i % 2 === 0 ? shortDay(d.date) : '', fill: i === n - 1 ? 'var(--accent)' : 'var(--accent-soft)' }))
})
const trafficBars = computed(() => {
  // Real per-day traffic (GB) from charts.traffic_trend; falls back to [] if the
  // backend hasn't been updated yet (older server) so the "No data" note shows
  // instead of silently plotting the wrong series.
  const arr = (charts.value.traffic_trend || []).slice(-14); const max = Math.max(0.001, ...arr.map(d => d.gb ?? 0)); const n = arr.length
  return arr.map((d, i) => ({ h: Math.round(((d.gb ?? 0) / max) * 100) + '%', label: i % 2 === 0 ? shortDay(d.date) : '', fill: i === n - 1 ? 'var(--accent)' : 'var(--accent-soft)' }))
})
// Traffic summary shown on the right of the traffic card: "<total> · <bw> Mbps".
// Bandwidth may be absent from the status payload → drop that half silently.
const dashTrafficTotal = computed(() => {
  const total = stats.value.traffic?.total_formatted
  const bw = stats.value.traffic?.bandwidth_mbps ?? stats.value.system?.bandwidth_mbps
  if (total && bw != null) return total + ' · ' + bw + ' Mbps'
  return total || ''
})
const TIER_COLORS = ['var(--accent)', 'var(--blue)', 'var(--amber)', 'var(--purple)', 'var(--green)']
const donutTotal = computed(() => Object.values(charts.value.sub_distribution || {}).reduce((a, b) => a + b, 0))
const donutSegs = computed(() => {
  const d = charts.value.sub_distribution || {}; const keys = Object.keys(d); const total = donutTotal.value || 1; let off = 0
  return keys.map((k, i) => {
    const pct = (d[k] / total) * 100; const seg = { color: TIER_COLORS[i % TIER_COLORS.length], dash: `${pct.toFixed(1)} ${(100 - pct).toFixed(1)}`, offset: (-off).toFixed(1), label: cap(k), value: d[k] }
    off += pct; return seg
  })
})
const payMethods = computed(() => {
  const d = charts.value.payment_methods || {}; const keys = Object.keys(d); const max = Math.max(1, ...keys.map(k => d[k]))
  return keys.map((k, i) => ({ label: cap(k), amount: '$' + d[k], pct: Math.round((d[k] / max) * 100) + '%', color: TIER_COLORS[i % TIER_COLORS.length] }))
})
const gauges = computed(() => {
  const sys = stats.value.system || {}
  return [
    gauge('CPU', sys.cpu_percent), gauge('RAM', sys.memory_percent), gauge('Disk', sys.disk_percent),
  ]
})
function gauge(label, v) { const val = Math.round(v ?? 0); const color = val > 90 ? 'var(--red)' : val > 70 ? 'var(--amber)' : 'var(--green)'; return { label, value: val + '%', dash: `${val} ${100 - val}`, color } }
const recentClients = computed(() => (clients.value || []).slice(0, 6).map(c => ({
  id: c.id, name: c.name, ip: c.ipv4 || '—', server: srvName(c.server_id),
  traffic: formatBytes((c.traffic_used_rx || 0) + (c.traffic_used_tx || 0)),
  bw: c.protocol === 'proxy' ? '—' : (c.bandwidth_limit || c.bandwidth ? ((c.bandwidth_limit || c.bandwidth) + ' Mbps') : '∞'),
  statusColor: c.enabled ? (isOnline(c) ? 'var(--green)' : 'var(--text-3)') : 'var(--red)',
  statusLabel: c.enabled ? (isOnline(c) ? (tr('common.online') || 'Online') : (tr('common.offline') || 'Offline')) : (tr('common.disabled') || 'Disabled'),
})))
const dashServers = computed(() => (servers.value || []).slice(0, 4).map(s => ({
  id: s.id, name: s.display_name || s.name, region: s.location || s.endpoint || '—', clients: s.total_clients ?? 0,
  statusColor: (s.is_online ?? s.online ?? s.status === 'online') ? 'var(--green)' : 'var(--text-3)',
})))
const activity = computed(() => (events.value || []).slice(0, 6).map(e => ({
  color: actionColor(e.action), text: (e.action || 'event') + (e.target_name ? ' · ' + e.target_name : ''), time: e.created_at ? rel(e.created_at) : '',
})))

function srvName(id) { return servers.value.find(s => s.id === id)?.name || '—' }
function isOnline(c) { return c.last_handshake ? (Date.now() - new Date(c.last_handshake).getTime() < 180000) : false }
function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1) }
function shortDay(d) { if (!d) return ''; const dt = new Date(d); return String(dt.getDate()) }
function actionColor(a) { const s = String(a || '').toLowerCase(); if (s.includes('delete') || s.includes('revoke')) return 'var(--red)'; if (s.includes('create') || s.includes('add')) return 'var(--green)'; return 'var(--accent)' }
function rel(d) { const m = Math.floor((Date.now() - new Date(d).getTime()) / 60000); if (m < 1) return 'just now'; if (m < 60) return m + 'm ago'; const h = Math.floor(m / 60); if (h < 24) return h + 'h ago'; return Math.floor(h / 24) + 'd ago' }

// mini map
let map = null, markers = null, lines = null, timer = null
let lastMapData = null
// big map inside the expand modal
let bigMap = null, bigMarkers = null, bigLines = null

function initMap() {
  if (map || !mapEl.value) return
  map = L.map(mapEl.value, { center: [30, 10], zoom: 1, minZoom: 1, maxZoom: 12, zoomControl: false, attributionControl: false })
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { subdomains: 'abcd', maxZoom: 19 }).addTo(map)
  markers = L.layerGroup().addTo(map); lines = L.layerGroup().addTo(map)
}
// Shared: (re)draw the server/client markers + links into a given layer pair.
// r = marker radius scale (bigger in the modal). Same colour rules as before.
function renderMarkers(markersLayer, linesLayer, data, r = 1) {
  markersLayer.clearLayers(); linesLayer.clearLayers(); const coords = {}
  for (const s of (data?.servers || [])) { if (s.lat == null) continue; coords[s.name] = [s.lat, s.lon]; L.circleMarker([s.lat, s.lon], { radius: 6 * r, fillColor: '#4a9eff', color: '#fff', weight: 1.5, fillOpacity: .9 }).addTo(markersLayer) }
  for (const c of (data?.clients || [])) { if (c.lat == null) continue; const col = c.active ? '#22c55e' : '#f59e0b'; L.circleMarker([c.lat, c.lon], { radius: 3.5 * r, fillColor: col, color: 'rgba(255,255,255,.6)', weight: .8, fillOpacity: .85 }).addTo(markersLayer); const sc = coords[c.server]; if (sc) L.polyline([[c.lat, c.lon], sc], { color: col, weight: .8, opacity: .22, dashArray: '4 6' }).addTo(linesLayer) }
}
async function loadMap() {
  try {
    const { data } = await clientsApi.getMapData(); lastMapData = data
    if (map) renderMarkers(markers, lines, data, 1)
    if (bigMap) renderMarkers(bigMarkers, bigLines, data, 1.5)
  } catch (_) {}
}
async function openMap() {
  mapModalOpen.value = true
  await nextTick()
  if (!bigMapEl.value) return
  if (!bigMap) {
    bigMap = L.map(bigMapEl.value, { center: [30, 10], zoom: 2, minZoom: 1, maxZoom: 12, zoomControl: true, attributionControl: true })
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { subdomains: 'abcd', maxZoom: 19 }).addTo(bigMap)
    bigMarkers = L.layerGroup().addTo(bigMap); bigLines = L.layerGroup().addTo(bigMap)
  }
  // Leaflet needs a size recalc after the modal paints; then draw with cached
  // data (or fetch if the mini map hasn't loaded yet).
  setTimeout(async () => {
    if (!bigMap) return
    bigMap.invalidateSize()
    if (!lastMapData) { try { lastMapData = (await clientsApi.getMapData()).data } catch (_) {} }
    if (lastMapData) renderMarkers(bigMarkers, bigLines, lastMapData, 1.5)
  }, 120)
}
function closeMap() {
  mapModalOpen.value = false
  if (bigMap) { bigMap.remove(); bigMap = null; bigMarkers = null; bigLines = null }
}

onMounted(async () => {
  ui.set({ title: tr('nav.dashboard') || 'Dashboard', subtitle: tr('dashboard.overviewSub') || '' })
  try {
    // ONE batched request (status+clients(10)+servers+revenue+charts) plus
    // the small logs call — instead of 6 parallel requests, one of which
    // (clientsApi.getAll with no limit) downloaded EVERY client row to show
    // 6. Fallback to the individual calls covers a mixed-version deploy.
    const lgP = systemApi.getLogs({ limit: 8 }).catch(() => ({ data: [] }))
    let st, cl, sv, rev, ch
    try {
      const { data } = await systemApi.getDashboard()
      st = { data: data.status }; cl = { data: data.clients }; sv = { data: data.servers }
      rev = { data: data.revenue }; ch = { data: data.charts }
    } catch (batchErr) {
      console.warn('D2Dashboard batch endpoint failed, using individual calls:', batchErr)
      ;[st, cl, sv, rev, ch] = await Promise.all([
        systemApi.getStatus(), clientsApi.getAll({ limit: 10 }), serversApi.getAll(),
        portalUsersApi.getRevenueStats().catch(() => ({ data: {} })),
        portalUsersApi.getChartData().catch(() => ({ data: {} })),
      ])
    }
    const lg = await lgP
    stats.value = st.data
    const cd = cl.data; clients.value = cd?.items || (Array.isArray(cd) ? cd : [])
    const sd = sv.data; servers.value = sd?.items || (Array.isArray(sd) ? sd : [])
    revenue.value = rev.data || {}
    charts.value = { revenue_trend: [], user_trend: [], sub_distribution: {}, payment_methods: {}, traffic_trend: [], ...(ch.data || {}) }
    const ld = lg.data; events.value = ld?.items || (Array.isArray(ld) ? ld : [])
  } catch (e) { console.error('D2Dashboard load', e) }
  await nextTick(); initMap(); loadMap()
  timer = setInterval(() => silentPoll(loadMap), 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer); if (map) { map.remove(); map = null } if (bigMap) { bigMap.remove(); bigMap = null } })
</script>

<style scoped>
.d2-dash { display: block; }
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-card { background: var(--panel); border: 1px solid var(--border); border-radius: 13px; box-shadow: var(--shadow); padding: 16px 18px; }
.d2-card2 { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); padding: 18px 20px; }
.d2-grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.d2-grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.d2-grid-main { display: grid; grid-template-columns: 1.7fr 1fr; gap: 14px; }
.d2-th { padding: 9px 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-pulse { animation: d2pulse 2s ease-in-out infinite; }
@keyframes d2pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .4; transform: scale(.85); } }
@media (max-width: 1100px) { .d2-grid4 { grid-template-columns: repeat(2, 1fr); } .d2-grid3, .d2-grid-main { grid-template-columns: 1fr; } }
@media (max-width: 600px) {
  .d2-grid4 { grid-template-columns:repeat(2,minmax(0,1fr)) !important;gap:9px !important; }
  .d2-card { padding:13px !important; }
  .d2-card > div:nth-child(2) { font-size:22px !important; }
  .d2-card2 { padding:15px !important; }
}
</style>
