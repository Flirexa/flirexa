<template>
  <div>
    <!-- Stats Cards — Row 1 -->
    <div class="row g-3 mb-3">
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--primary">
            <i class="mdi mdi-account-multiple"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.totalClients') }}</div>
            <div class="metric-value">{{ stats.clients?.total ?? '-' }}</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--success">
            <i class="mdi mdi-account-check"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.activeClients') }}</div>
            <div class="metric-value metric-value--success">{{ stats.clients?.active ?? '-' }}</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--info">
            <i class="mdi mdi-server"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.servers') }}</div>
            <div class="metric-value">
              {{ stats.servers?.total ?? '-' }}
              <span class="metric-sub">/ {{ stats.servers?.online ?? 0 }} online</span>
            </div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--warning">
            <i class="mdi mdi-chart-line"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.totalTraffic') }}</div>
            <div class="metric-value">{{ stats.traffic?.total_formatted ?? '-' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Stats Cards — Row 2 (Revenue) -->
    <div class="row g-3 mb-4">
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--success">
            <i class="mdi mdi-cash-multiple"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.revenue30d') || '30-day Revenue' }}</div>
            <div class="metric-value">${{ revenue.revenue_30d ?? 0 }}</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--primary">
            <i class="mdi mdi-currency-usd"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.revenue') || 'Total Revenue' }}</div>
            <div class="metric-value">${{ revenue.total_revenue ?? 0 }}</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="metric-card">
          <div class="metric-icon metric-icon--warning">
            <i class="mdi mdi-star-circle"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.activeSubs') || 'Active Subs' }}</div>
            <div class="metric-value metric-value--success">{{ revenue.active_subscriptions ?? 0 }}</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <router-link to="/portal-users" class="metric-card metric-card--link text-decoration-none">
          <div class="metric-icon metric-icon--info">
            <i class="mdi mdi-account-group"></i>
          </div>
          <div class="metric-body">
            <div class="metric-label">{{ $t('dashboard.portalUsers') || 'Portal Users' }}</div>
            <div class="metric-value">{{ revenue.total_users ?? 0 }}</div>
          </div>
        </router-link>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="row g-4 mb-4">
      <!-- Revenue Trend -->
      <div class="col-lg-8">
        <div class="table-card">
          <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
            <div>
              <h6 class="mb-0 fw-bold">{{ $t('dashboard.revenueTrend') || 'Revenue Trend' }}</h6>
              <small class="text-muted">{{ $t('dashboard.last30Days') || 'Last 30 days' }}</small>
            </div>
            <div class="d-flex gap-3">
              <div class="text-end">
                <div class="fw-bold text-success">${{ revenue.revenue_7d ?? 0 }}</div>
                <div class="stat-label">7-day</div>
              </div>
              <div class="text-end">
                <div class="fw-bold">${{ revenue.revenue_30d ?? 0 }}</div>
                <div class="stat-label">30-day</div>
              </div>
            </div>
          </div>
          <div class="px-2 pb-2">
            <apexchart
              type="area"
              height="220"
              :options="revenueChartOptions"
              :series="revenueChartSeries"
            />
          </div>
        </div>
      </div>

      <!-- Subscription Distribution -->
      <div class="col-lg-4">
        <div class="table-card h-100">
          <div class="p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.subscriptions') || 'Subscriptions' }}</h6>
            <small class="text-muted">{{ $t('dashboard.activeByTier') || 'Active by tier' }}</small>
          </div>
          <div class="d-flex flex-column align-items-center px-2 pb-2">
            <apexchart
              type="donut"
              height="200"
              :options="subDonutOptions"
              :series="subDonutSeries"
            />
            <div class="w-100 px-3 pb-2">
              <div v-for="(val, key) in charts.sub_distribution" :key="key"
                class="d-flex justify-content-between align-items-center mb-1">
                <div class="d-flex align-items-center gap-2">
                  <span class="donut-dot" :style="{ background: tierColor(key) }"></span>
                  <span class="small text-capitalize">{{ key }}</span>
                </div>
                <span class="fw-bold small">{{ val }}</span>
              </div>
              <div v-if="!Object.keys(charts.sub_distribution || {}).length"
                class="text-center text-muted small py-2">—</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- User Growth + Payment Methods -->
    <div class="row g-4 mb-4">
      <div class="col-lg-8">
        <div class="table-card">
          <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
            <div>
              <h6 class="mb-0 fw-bold">{{ $t('dashboard.userGrowth') || 'User Registrations' }}</h6>
              <small class="text-muted">{{ $t('dashboard.last30Days') || 'Last 30 days' }}</small>
            </div>
            <div class="d-flex gap-3">
              <div class="text-end">
                <div class="fw-bold text-primary">{{ revenue.total_users ?? 0 }}</div>
                <div class="stat-label">{{ $t('dashboard.totalUsers') || 'Total' }}</div>
              </div>
            </div>
          </div>
          <div class="px-2 pb-2">
            <apexchart
              type="bar"
              height="200"
              :options="userBarOptions"
              :series="userBarSeries"
            />
          </div>
        </div>
      </div>

      <!-- Payment Stats + Methods -->
      <div class="col-lg-4">
        <div class="table-card h-100">
          <div class="p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.paymentStats') || 'Payments' }}</h6>
          </div>
          <div class="p-3">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <span class="text-muted small">{{ $t('dashboard.completedPayments') || 'Completed' }}</span>
              <span class="badge-pill bg-success-light text-success fw-bold">{{ revenue.completed_payments ?? 0 }}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center mb-3">
              <span class="text-muted small">{{ $t('dashboard.pendingPayments') || 'Pending' }}</span>
              <span class="badge-pill bg-warning-light text-warning fw-bold">{{ revenue.pending_payments ?? 0 }}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center mb-3">
              <span class="text-muted small">{{ $t('dashboard.totalPayments') || 'Total' }}</span>
              <span class="badge-pill bg-primary-light text-primary fw-bold">{{ revenue.total_payments ?? 0 }}</span>
            </div>
            <hr class="my-2">
            <div class="small text-muted mb-2">{{ $t('dashboard.revenueByMethod') || 'By Method' }}</div>
            <div v-for="(val, method) in charts.payment_methods" :key="method"
              class="d-flex justify-content-between mb-1">
              <span class="text-muted small text-capitalize">{{ method }}</span>
              <span class="fw-medium small">{{ val }} {{ $t('common.payments') || 'payments' }}</span>
            </div>
            <div v-for="(amount, method) in revenue.by_method" :key="'r-' + method"
              class="d-flex justify-content-between mb-1">
              <span class="text-muted small text-capitalize">{{ method }}</span>
              <span class="fw-medium small text-success">${{ amount }}</span>
            </div>
            <div v-if="!Object.keys(revenue.by_method || {}).length && !Object.keys(charts.payment_methods || {}).length"
              class="text-center text-muted small">—</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Alerts -->
    <div class="row g-4 mb-4" v-if="stats.expiry?.expiring_week > 0 || stats.traffic?.exceeded_count > 0">
      <div class="col-12">
        <div class="alert alert-warning mb-0" v-if="stats.expiry?.expiring_week > 0">
          <strong>&#x26A0; {{ $t('dashboard.expiringSoon') }}</strong>
          {{ $t('dashboard.expiringSoonMsg', { count: stats.expiry?.expiring_week }) }}
          <span v-if="stats.expiry?.expiring_today > 0">({{ $t('dashboard.expiringToday', { count: stats.expiry?.expiring_today }) }})</span>
        </div>
        <div class="alert alert-danger mb-0 mt-2" v-if="stats.traffic?.exceeded_count > 0">
          <strong>&#x26D4; {{ $t('dashboard.trafficExceeded') }}</strong>
          {{ $t('dashboard.trafficExceededMsg', { count: stats.traffic.exceeded_count }) }}
        </div>
      </div>
    </div>

    <!-- Client Map -->
    <div class="row g-4 mb-4">
      <div class="col-12">
        <div class="table-card">
          <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.clientMap') }}</h6>
            <small class="text-muted" v-if="mapStats.servers > 0 || mapStats.clients > 0">
              {{ mapStats.servers }} server{{ mapStats.servers !== 1 ? 's' : '' }},
              {{ mapStats.clients }} client{{ mapStats.clients !== 1 ? 's' : '' }}
            </small>
          </div>
          <div id="client-map" ref="mapContainer"></div>
        </div>
      </div>
    </div>

    <div class="row g-4">
      <!-- Recent Clients -->
      <div class="col-lg-8">
        <div class="table-card">
          <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.clientsOverview') }}</h6>
            <router-link to="/clients" class="btn btn-sm btn-outline-primary">{{ $t('dashboard.viewAll') }}</router-link>
          </div>
          <div class="table-responsive">
            <table class="table table-hover">
              <thead>
                <tr>
                  <th>{{ $t('common.name') }}</th>
                  <th>{{ $t('dashboard.ip') }}</th>
                  <th>{{ $t('common.status') }}</th>
                  <th>{{ $t('dashboard.traffic') }}</th>
                  <th class="d-none d-sm-table-cell">{{ $t('dashboard.bandwidth') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="client in clients.slice(0, 10)" :key="client.id">
                  <td class="fw-medium">{{ client.name }}</td>
                  <td><code>{{ client.ipv4 }}</code></td>
                  <td>
                    <span class="badge" :class="client.enabled ? 'badge-online' : 'badge-offline'">
                      {{ client.enabled ? $t('common.online') : $t('common.offline') }}
                    </span>
                  </td>
                  <td>{{ formatBytes((client.traffic_used_rx || 0) + (client.traffic_used_tx || 0)) }}</td>
                  <td class="d-none d-sm-table-cell">{{ client.bandwidth_limit ? client.bandwidth_limit + ' ' + $t('dashboard.mbps') : $t('common.unlimited') }}</td>
                </tr>
                <tr v-if="clients.length === 0">
                  <td colspan="5" class="text-center text-muted py-4">{{ $t('dashboard.noClients') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Server Status -->
      <div class="col-lg-4">
        <div class="table-card">
          <div class="d-flex justify-content-between align-items-center p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.servers') }}</h6>
            <router-link to="/servers" class="btn btn-sm btn-outline-primary">{{ $t('dashboard.manage') }}</router-link>
          </div>
          <div class="p-3" v-if="servers.length === 0">
            <div class="text-center text-muted py-3">{{ $t('dashboard.noServers') }}</div>
          </div>
          <div class="list-group list-group-flush" v-else>
            <div
              class="list-group-item d-flex justify-content-between align-items-center"
              v-for="server in servers"
              :key="server.id"
            >
              <div>
                <div class="fw-medium">{{ server.name }}</div>
                <small class="text-muted">{{ server.endpoint }}</small>
              </div>
              <span class="badge" :class="(server.status || '').toLowerCase() === 'online' ? 'badge-online' : 'badge-offline'">
                {{ (server.status || '').toLowerCase() === 'online' ? $t('common.online') : $t('common.offline') }}
              </span>
            </div>
          </div>
        </div>

        <!-- System Health -->
        <div class="table-card mt-4">
          <div class="p-3 border-bottom">
            <h6 class="mb-0 fw-bold">{{ $t('dashboard.systemHealth') }}</h6>
          </div>
          <div class="px-1 pb-1">
            <apexchart
              type="radialBar"
              height="260"
              :options="systemRadialOptions"
              :series="systemRadialSeries"
            />
          </div>
          <div class="px-3 pb-3">
            <div class="d-flex justify-content-around text-center">
              <div>
                <div class="fw-bold" :style="{ color: sysColor(stats.system?.cpu_percent) }">
                  {{ stats.system?.cpu_percent ?? 0 }}%
                </div>
                <div class="stat-label">{{ $t('dashboard.cpu') }}</div>
              </div>
              <div>
                <div class="fw-bold" :style="{ color: sysColor(stats.system?.memory_percent) }">
                  {{ stats.system?.memory_percent ?? 0 }}%
                </div>
                <div class="stat-label">{{ $t('dashboard.memory') }}</div>
              </div>
              <div>
                <div class="fw-bold" :style="{ color: sysColor(stats.system?.disk_percent) }">
                  {{ stats.system?.disk_percent ?? 0 }}%
                </div>
                <div class="stat-label">{{ $t('dashboard.disk') }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { systemApi, clientsApi, serversApi, portalUsersApi } from '../api'
import { formatBytes } from '../utils'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const stats = ref({})
const clients = ref([])
const servers = ref([])
const revenue = ref({})
const charts = ref({ revenue_trend: [], user_trend: [], sub_distribution: {}, payment_methods: {} })
const mapContainer = ref(null)
const mapStats = reactive({ servers: 0, clients: 0 })

// ── Chart helpers ──────────────────────────────────────────
const TIER_COLORS = ['#7367F0', '#28C76F', '#FF9F43', '#00CFE8', '#EA5455']
function tierColor(tier) {
  const map = { free: '#b9b9c3', basic: '#00CFE8', standard: '#7367F0', premium: '#FF9F43', pro: '#FF9F43', enterprise: '#EA5455', ultimate: '#28C76F' }
  return map[tier?.toLowerCase()] || TIER_COLORS[0]
}
function sysColor(val) {
  if (!val) return '#28C76F'
  if (val > 90) return '#EA5455'
  if (val > 70) return '#FF9F43'
  return '#28C76F'
}

const CHART_BASE = {
  toolbar: { show: false },
  zoom: { enabled: false },
  fontFamily: 'Inter, system-ui, sans-serif',
  animations: { enabled: true, speed: 600 },
}

// Revenue area chart
const revenueChartOptions = computed(() => ({
  chart: { ...CHART_BASE, type: 'area', id: 'revenue-trend' },
  colors: ['#7367F0'],
  stroke: { curve: 'smooth', width: 2.5 },
  fill: {
    type: 'gradient',
    gradient: { shade: 'dark', type: 'vertical', shadeIntensity: 0.3, gradientToColors: ['#7367F0'], opacityFrom: 0.5, opacityTo: 0.02, stops: [0, 100] }
  },
  dataLabels: { enabled: false },
  grid: { borderColor: 'var(--vxy-border)', strokeDashArray: 4, padding: { left: 0, right: 0 } },
  xaxis: {
    categories: charts.value.revenue_trend.map(d => d.date),
    tickAmount: 6,
    axisBorder: { show: false },
    axisTicks: { show: false },
    labels: { style: { colors: '#B9B9C3', fontSize: '11px' }, rotate: 0 }
  },
  yaxis: { labels: { style: { colors: '#B9B9C3', fontSize: '11px' }, formatter: v => `$${Math.round(v)}` } },
  tooltip: { theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light', y: { formatter: v => `$${Math.round(v)}` } },
  markers: { size: 0, hover: { size: 4 } },
}))

const revenueChartSeries = computed(() => ([
  { name: 'Revenue', data: charts.value.revenue_trend.map(d => d.amount) }
]))

// User bar chart
const userBarOptions = computed(() => ({
  chart: { ...CHART_BASE, type: 'bar', id: 'user-trend' },
  colors: ['#7367F0'],
  plotOptions: { bar: { borderRadius: 4, borderRadiusApplication: 'end', columnWidth: '60%' } },
  dataLabels: { enabled: false },
  grid: { borderColor: 'var(--vxy-border)', strokeDashArray: 4, padding: { left: 0, right: 0 } },
  fill: {
    type: 'gradient',
    gradient: { shade: 'light', type: 'vertical', shadeIntensity: 0.1, gradientToColors: ['#9e95f5'], opacityFrom: 1, opacityTo: 0.8 }
  },
  xaxis: {
    categories: charts.value.user_trend.map(d => d.date),
    tickAmount: 6,
    axisBorder: { show: false },
    axisTicks: { show: false },
    labels: { style: { colors: '#B9B9C3', fontSize: '11px' }, rotate: 0 }
  },
  yaxis: { labels: { style: { colors: '#B9B9C3', fontSize: '11px' }, formatter: v => Math.round(v) } },
  tooltip: { theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light' },
}))

const userBarSeries = computed(() => ([
  { name: 'New Users', data: charts.value.user_trend.map(d => d.count) }
]))

// Donut chart
const subDonutOptions = computed(() => {
  const keys = Object.keys(charts.value.sub_distribution || {})
  return {
    chart: { ...CHART_BASE, type: 'donut', id: 'sub-dist' },
    colors: keys.map(k => tierColor(k)),
    labels: keys.map(k => k.charAt(0).toUpperCase() + k.slice(1)),
    legend: { show: false },
    dataLabels: { enabled: keys.length > 0, formatter: (val) => `${Math.round(val)}%` },
    plotOptions: { pie: { donut: { size: '60%', labels: { show: keys.length > 0, total: { show: true, label: 'Total', fontSize: '12px', fontWeight: 600, color: '#5e5873', formatter: w => w.globals.seriesTotals.reduce((a, b) => a + b, 0) } } } } },
    stroke: { show: false },
    noData: { text: 'No subscriptions yet', style: { color: '#b9b9c3', fontSize: '13px' } },
    tooltip: { theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light' },
  }
})

const subDonutSeries = computed(() => Object.values(charts.value.sub_distribution || {}))

// System radial bar
const systemRadialOptions = computed(() => ({
  chart: { ...CHART_BASE, type: 'radialBar', id: 'sys-health' },
  colors: [
    sysColor(stats.value.system?.cpu_percent),
    sysColor(stats.value.system?.memory_percent),
    sysColor(stats.value.system?.disk_percent),
  ],
  plotOptions: {
    radialBar: {
      hollow: { margin: 5, size: '25%' },
      track: { background: 'var(--vxy-progress-bg)', strokeWidth: '97%', margin: 6 },
      dataLabels: {
        show: true,
        name: { fontSize: '11px', fontWeight: 500, offsetY: 4 },
        value: { show: false },
        total: { show: true, label: 'Health', fontSize: '12px', fontWeight: 600, color: '#5e5873', formatter: w => {
          const avg = w.globals.seriesTotals.reduce((a, b) => a + b, 0) / w.globals.series.length
          return `${Math.round(100 - avg)}%`
        }}
      }
    }
  },
  stroke: { lineCap: 'round' },
  labels: ['CPU', 'RAM', 'Disk'],
  legend: { show: false },
  tooltip: { enabled: false },
}))

const systemRadialSeries = computed(() => [
  stats.value.system?.cpu_percent ?? 0,
  stats.value.system?.memory_percent ?? 0,
  stats.value.system?.disk_percent ?? 0,
])

let map = null
let markersLayer = null
let linesLayer = null
let mapRefreshTimer = null

function getTierBadge(tier) {
  const map = { basic: 'bg-info', premium: 'bg-primary', ultimate: 'bg-warning text-dark', free: 'bg-secondary' }
  return map[tier?.toLowerCase()] || 'bg-secondary'
}

function getProgressColor(val) {
  if (!val) return 'bg-success'
  if (val > 90) return 'bg-danger'
  if (val > 70) return 'bg-warning'
  return 'bg-success'
}

function initMap() {
  if (map) return

  map = L.map('client-map', {
    center: [30, 10],
    zoom: 2,
    minZoom: 2,
    maxZoom: 12,
    zoomControl: true,
    attributionControl: false,
  })

  // Dark tiles
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map)

  // Attribution (small, bottom-right)
  L.control.attribution({ prefix: false, position: 'bottomright' })
    .addAttribution('&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/copyright">OSM</a>')
    .addTo(map)

  markersLayer = L.layerGroup().addTo(map)
  linesLayer = L.layerGroup().addTo(map)
}

function updateMapMarkers(data) {
  if (!map || !markersLayer) return

  markersLayer.clearLayers()
  linesLayer.clearLayers()

  const serverCoords = {}

  // Server markers (blue, larger)
  for (const srv of data.servers) {
    if (srv.lat == null || srv.lon == null) continue
    serverCoords[srv.name] = [srv.lat, srv.lon]

    const marker = L.circleMarker([srv.lat, srv.lon], {
      radius: 10,
      fillColor: '#4a9eff',
      color: '#fff',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.9,
    })

    marker.bindPopup(`
      <div style="min-width:160px">
        <strong>${srv.name}</strong><br>
        <span style="color:#888">${srv.city}${srv.city && srv.country ? ', ' : ''}${srv.country}</span><br>
        <code style="font-size:11px">${srv.ip}</code><br>
        <span style="color:#4a9eff">&#9679;</span> ${srv.clients_count} client${srv.clients_count !== 1 ? 's' : ''} connected
      </div>
    `)

    markersLayer.addLayer(marker)
  }

  // Client markers (green=active, orange=inactive)
  for (const cl of data.clients) {
    if (cl.lat == null || cl.lon == null) continue

    const isActive = cl.active
    const color = isActive ? '#22c55e' : '#f59e0b'

    const marker = L.circleMarker([cl.lat, cl.lon], {
      radius: 6,
      fillColor: color,
      color: 'rgba(255,255,255,0.6)',
      weight: 1,
      opacity: 1,
      fillOpacity: 0.85,
    })

    marker.bindPopup(`
      <div style="min-width:160px">
        <strong>${cl.name}</strong>
        <span style="color:${color};font-size:10px"> &#9679; ${isActive ? 'active' : 'idle'}</span><br>
        <span style="color:#888">${cl.city}${cl.city && cl.country ? ', ' : ''}${cl.country}</span><br>
        <code style="font-size:11px">${cl.ip}</code><br>
        Traffic: <strong>${cl.traffic_formatted}</strong><br>
        Server: ${cl.server}
      </div>
    `)

    markersLayer.addLayer(marker)

    // Dashed line to server
    const srvCoord = serverCoords[cl.server]
    if (srvCoord) {
      const line = L.polyline([[cl.lat, cl.lon], srvCoord], {
        color: color,
        weight: 1,
        opacity: 0.25,
        dashArray: '4 6',
      })
      linesLayer.addLayer(line)
    }
  }

  mapStats.servers = data.servers.filter(s => s.lat != null).length
  mapStats.clients = data.clients.length
}

async function loadMapData() {
  try {
    const res = await clientsApi.getMapData()
    updateMapMarkers(res.data)
  } catch (e) {
    // Silently fail — map is optional
  }
}

onMounted(async () => {
  try {
    const [statusRes, clientsRes, serversRes, revenueRes, chartsRes] = await Promise.all([
      systemApi.getStatus(),
      clientsApi.getAll(),
      serversApi.getAll(),
      portalUsersApi.getRevenueStats().catch(() => ({ data: {} })),
      portalUsersApi.getChartData().catch(() => ({ data: { revenue_trend: [], user_trend: [], sub_distribution: {}, payment_methods: {} } })),
    ])
    stats.value = statusRes.data
    const cData = clientsRes.data
    clients.value = (cData && cData.items) ? cData.items : (Array.isArray(cData) ? cData : [])
    const sData = serversRes.data
    servers.value = (sData && sData.items) ? sData.items : (Array.isArray(sData) ? sData : [])
    revenue.value = revenueRes.data
    charts.value = chartsRes.data
  } catch (err) {
    console.error('Dashboard load error:', err)
  }

  // Init map after DOM is ready
  await nextTick()
  initMap()
  loadMapData()

  // Refresh map markers every 30s
  mapRefreshTimer = setInterval(loadMapData, 30000)
})

onUnmounted(() => {
  if (mapRefreshTimer) clearInterval(mapRefreshTimer)
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.donut-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}

.badge-pill {
  padding: .2rem .6rem; border-radius: 20px; font-size: .8rem;
}
.bg-success-light { background: rgba(40,199,111,.12); }
.bg-warning-light { background: rgba(255,159,67,.12); }
.bg-primary-light { background: rgba(115,103,240,.12); }

#client-map {
  height: 400px; width: 100%;
  background: var(--vxy-card-bg);
  border-radius: 0 0 var(--vxy-card-radius) var(--vxy-card-radius);
  z-index: 0;
}
#client-map :deep(.leaflet-control-zoom) { z-index: 400 !important; }

:deep(.leaflet-popup-content-wrapper) {
  background: var(--vxy-card-bg); color: var(--vxy-text);
  border-radius: .5rem; box-shadow: 0 4px 20px rgba(0,0,0,.3);
}
:deep(.leaflet-popup-tip) { background: var(--vxy-card-bg); }
:deep(.leaflet-popup-content) { margin: 10px 14px; font-size: 13px; line-height: 1.6; }
:deep(.leaflet-popup-content code) {
  color: var(--vxy-muted); background: var(--vxy-hover-bg);
  padding: 1px 4px; border-radius: 3px;
}
:deep(.leaflet-popup-close-button) { color: var(--vxy-muted) !important; }
:deep(.leaflet-control-attribution) {
  background: rgba(0,0,0,.4) !important; color: var(--vxy-muted) !important; font-size: 10px !important;
}
:deep(.leaflet-control-attribution a) { color: var(--vxy-muted) !important; }
</style>
