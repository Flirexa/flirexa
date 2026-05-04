<template>
  <div class="fx-card fx-chart-card">
    <div class="fx-chart-head">
      <div>
        <h3 class="fx-section-title">{{ $t('chart.trafficTitle') }}</h3>
        <div style="display:flex; align-items:baseline; gap:10px; margin-top:6px">
          <span style="font-size:24px; font-weight:600; letter-spacing:-0.025em; font-variant-numeric:tabular-nums">
            {{ formatGB(summary.total_gb) }}
          </span>
          <span v-if="summary.trend_pct != null" class="fx-stat-trend"
                :class="summary.trend_pct >= 0 ? 'up' : 'down'">
            <FxIcon :name="summary.trend_pct >= 0 ? 'arrowUp' : 'arrowDown'" :size="11" />
            {{ Math.abs(summary.trend_pct).toFixed(1) }}% {{ $t('chart.vsPrev') }}
          </span>
          <span v-else style="font-size:11px; color:var(--text-3)">{{ $t('chart.noPriorData') }}</span>
        </div>
      </div>
      <div class="fx-chart-tabs">
        <button v-for="t in TABS" :key="t.key"
                :class="['fx-chart-tab', { active: range === t.key }]"
                @click="$emit('change-range', t.key)">{{ $t(t.labelKey) }}</button>
      </div>
    </div>

    <div v-if="loading" style="height:220px; display:grid; place-items:center; color:var(--text-3); font-size:12px">
      {{ $t('common.loading') }}
    </div>
    <div v-else-if="!hasData" style="height:220px; display:grid; place-items:center; color:var(--text-3); font-size:12px; text-align:center; padding:0 var(--pad-card)">
      {{ $t('chart.noTraffic') }}
    </div>
    <div v-else>
      <apexchart type="area" height="220" :options="chartOptions" :series="chartSeries" />
      <div style="display:flex; gap:18px; padding:0 var(--pad-card) 4px; font-size:11px; color:var(--text-3); flex-wrap:wrap">
        <span style="display:inline-flex; align-items:center; gap:6px">
          <span class="fx-legend-dot" :style="{ background: 'var(--accent)' }" />
          {{ $t('chart.download') }}
          <span style="color:var(--text-2); font-variant-numeric:tabular-nums">{{ formatGB(summary.total_rx_gb) }}</span>
        </span>
        <span style="display:inline-flex; align-items:center; gap:6px">
          <span class="fx-legend-dot" :style="{ background: 'var(--info)' }" />
          {{ $t('chart.upload') }}
          <span style="color:var(--text-2); font-variant-numeric:tabular-nums">{{ formatGB(summary.total_tx_gb) }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import FxIcon from './FxIcon.vue'

const props = defineProps({
  series: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({ total_rx_gb: 0, total_tx_gb: 0, total_gb: 0, trend_pct: null }) },
  range: { type: String, default: '14d' },
  loading: { type: Boolean, default: false },
})
defineEmits(['change-range'])

const TABS = [
  { key: '7d', labelKey: 'chart.range7d' },
  { key: '14d', labelKey: 'chart.range14d' },
  { key: '30d', labelKey: 'chart.range30d' },
  { key: 'all', labelKey: 'chart.rangeAll' },
]

const hasData = computed(() =>
  props.series.length >= 2 && props.series.some(p => (p.rx_gb || 0) + (p.tx_gb || 0) > 0)
)

const chartSeries = computed(() => [
  { name: 'Download', data: props.series.map(p => Number(p.rx_gb || 0)) },
  { name: 'Upload',   data: props.series.map(p => Number(p.tx_gb || 0)) },
])

const chartOptions = computed(() => {
  const cssRoot = getComputedStyle(document.body)
  const accent = cssRoot.getPropertyValue('--accent').trim() || '#4451f0'
  const info = cssRoot.getPropertyValue('--info').trim() || '#06b6d4'
  const grid = cssRoot.getPropertyValue('--grid-line').trim() || 'rgba(15,18,40,.06)'
  const text3 = cssRoot.getPropertyValue('--text-3').trim() || '#757a90'
  const elev = cssRoot.getPropertyValue('--bg-elev').trim() || '#fff'

  return {
    chart: {
      toolbar: { show: false },
      zoom: { enabled: false },
      animations: { enabled: true, speed: 400 },
      fontFamily: 'inherit',
      background: 'transparent',
    },
    colors: [accent, info],
    stroke: { curve: 'smooth', width: [2, 1.75] },
    fill: {
      type: 'gradient',
      gradient: {
        shadeIntensity: 1,
        opacityFrom: [0.32, 0.22],
        opacityTo: [0, 0],
        stops: [0, 100],
      },
    },
    dataLabels: { enabled: false },
    grid: {
      borderColor: grid,
      strokeDashArray: 3,
      padding: { left: 6, right: 6, top: 0, bottom: 0 },
      yaxis: { lines: { show: true } },
      xaxis: { lines: { show: false } },
    },
    xaxis: {
      type: 'datetime',
      categories: props.series.map(p => p.date),
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { style: { colors: text3, fontSize: '10px' }, datetimeUTC: false, format: tickFormat() },
    },
    yaxis: {
      labels: {
        style: { colors: text3, fontSize: '10px' },
        formatter: (v) => formatGB(v),
      },
    },
    tooltip: {
      shared: true,
      intersect: false,
      x: { format: 'MMM dd' },
      theme: document.body.classList.contains('theme-dark') ? 'dark' : 'light',
      y: { formatter: (v) => formatGB(v) },
    },
    markers: {
      size: 0,
      strokeColors: elev,
      strokeWidth: 2,
      hover: { size: 4 },
    },
    legend: { show: false },
  }
})

function tickFormat() {
  if (props.range === '7d' || props.range === '14d') return 'MMM dd'
  return 'MMM dd'
}

function formatGB(v) {
  const n = Number(v) || 0
  if (n >= 1024) return (n / 1024).toFixed(1) + ' TB'
  if (n >= 1) return n.toFixed(1) + ' GB'
  if (n > 0) return (n * 1024).toFixed(0) + ' MB'
  return '0 GB'
}
</script>

<style scoped>
.fx-legend-dot {
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block;
}
</style>
