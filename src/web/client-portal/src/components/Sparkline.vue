<template>
  <svg
    v-if="hasPoints"
    :viewBox="`0 0 ${width} ${height}`"
    preserveAspectRatio="none"
    :style="{ width: '100%', height: height + 'px', display: 'block', overflow: 'visible' }"
  >
    <defs v-if="fill">
      <linearGradient :id="gradId" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.28" />
        <stop offset="100%" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path v-if="fill" :d="areaPath" :fill="`url(#${gradId})`" />
    <path :d="linePath" fill="none" :stroke="color" :stroke-width="strokeWidth"
          stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Array, default: () => [] },
  color: { type: String, default: 'currentColor' },
  fill: { type: Boolean, default: true },
  height: { type: Number, default: 32 },
  strokeWidth: { type: Number, default: 1.5 },
})

const width = 100
// Random id per instance — collisions break <defs> when multiple sparklines render.
const gradId = 'spk-' + Math.random().toString(36).slice(2, 8)

const hasPoints = computed(() => props.data.length >= 2)

// 2px top/bottom padding so the stroke isn't clipped at the edges.
const points = computed(() => {
  const d = props.data
  if (d.length < 2) return []
  const max = Math.max(...d)
  const min = Math.min(...d)
  const range = max - min || 1
  return d.map((v, i) => [
    (i / (d.length - 1)) * width,
    props.height - ((v - min) / range) * (props.height - 4) - 2,
  ])
})

const linePath = computed(() =>
  points.value
    .map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1))
    .join(' ')
)
const areaPath = computed(() =>
  linePath.value + ` L ${width} ${props.height} L 0 ${props.height} Z`
)
</script>
