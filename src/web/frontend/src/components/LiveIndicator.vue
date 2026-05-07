<template>
  <div class="live-wrap" v-click-outside="close">
    <button
      type="button"
      class="live-indicator"
      :class="{ 'is-live': effectiveLive, 'is-paused': !effectiveLive, 'is-off': isOff }"
      :title="badgeTitle"
      :aria-haspopup="!!intervalMs"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="dot" />
      <span class="label">
        {{ statusLabel }}
        <span v-if="intervalMs && !isOff" class="period">· {{ formatInterval(intervalMs) }}</span>
      </span>
      <i v-if="intervalMs !== undefined" class="mdi mdi-chevron-down chevron" :class="{ rot: open }" />
    </button>

    <!-- Picker dropdown -->
    <div v-if="open && intervalMs !== undefined" class="picker" role="menu">
      <div class="picker-title">{{ t('common.refreshInterval') }}</div>
      <button
        v-for="opt in options"
        :key="opt.value"
        type="button"
        class="picker-opt"
        :class="{ selected: opt.value === intervalMs }"
        role="menuitemradio"
        :aria-checked="opt.value === intervalMs"
        @click="pick(opt.value)"
      >
        <span>{{ opt.label }}</span>
        <i v-if="opt.value === intervalMs" class="mdi mdi-check check" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  live: { type: Boolean, default: true },
  intervalMs: { type: Number, default: undefined },
})
const emit = defineEmits(['update:intervalMs'])

const { t } = useI18n()
const open = ref(false)

const isOff = computed(() => props.intervalMs === 0)
const effectiveLive = computed(() => props.live && !isOff.value)

const statusLabel = computed(() => {
  if (isOff.value) return t('common.off')
  return effectiveLive.value ? t('common.live') : t('common.paused')
})

const badgeTitle = computed(() => {
  if (isOff.value) return t('common.liveOffHint')
  if (effectiveLive.value) return t('common.liveActive')
  return t('common.livePaused')
})

// Discrete options that round-trip cleanly with formatInterval.
const options = computed(() => [
  { value: 0,        label: t('common.off') },
  { value: 5_000,    label: '5s' },
  { value: 15_000,   label: '15s' },
  { value: 30_000,   label: '30s' },
  { value: 60_000,   label: '1m' },
  { value: 300_000,  label: '5m' },
])

function formatInterval(ms) {
  if (!ms) return t('common.off')
  if (ms < 60_000) return Math.round(ms / 1000) + 's'
  return Math.round(ms / 60_000) + 'm'
}

function toggle() {
  if (props.intervalMs === undefined) return  // read-only badge mode
  open.value = !open.value
}
function close() { open.value = false }
function pick(v) {
  emit('update:intervalMs', v)
  close()
}

// Click-outside directive — small inline implementation, no extra dep.
const vClickOutside = {
  mounted(el, binding) {
    el._cohandler = (e) => { if (!el.contains(e.target)) binding.value(e) }
    document.addEventListener('click', el._cohandler, true)
  },
  unmounted(el) {
    document.removeEventListener('click', el._cohandler, true)
  },
}
</script>

<style scoped>
.live-wrap { position: relative; display: inline-block; }

.live-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 3px 8px 3px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  background: transparent;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}
.live-indicator:hover { filter: brightness(1.04); }
.live-indicator:focus-visible { outline: 2px solid rgba(13, 110, 253, 0.5); outline-offset: 2px; }

.live-indicator .dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.live-indicator .period {
  opacity: 0.78; margin-left: 2px; font-variant-numeric: tabular-nums;
  text-transform: none; letter-spacing: 0;
}
.live-indicator .chevron { font-size: 0.85rem; transition: transform 0.18s ease; }
.live-indicator .chevron.rot { transform: rotate(180deg); }

/* Active */
.live-indicator.is-live {
  background: rgba(40, 167, 69, 0.10);
  border-color: rgba(40, 167, 69, 0.25);
  color: #1e7a34;
}
.live-indicator.is-live .dot {
  background: #28a745;
  box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.55);
  animation: live-pulse 2s ease-out infinite;
}

/* Paused (tab hidden) */
.live-indicator.is-paused {
  background: rgba(108, 117, 125, 0.08);
  border-color: rgba(108, 117, 125, 0.20);
  color: #6c757d;
}
.live-indicator.is-paused .dot { background: #adb5bd; }

/* Off (user disabled polling) */
.live-indicator.is-off {
  background: rgba(108, 117, 125, 0.05);
  border-color: rgba(108, 117, 125, 0.18);
  color: #868e96;
}
.live-indicator.is-off .dot { background: #ced4da; box-shadow: none; animation: none; }

@keyframes live-pulse {
  0%   { box-shadow: 0 0 0 0    rgba(40, 167, 69, 0.55); }
  70%  { box-shadow: 0 0 0 8px  rgba(40, 167, 69, 0);    }
  100% { box-shadow: 0 0 0 0    rgba(40, 167, 69, 0);    }
}

/* Picker dropdown */
.picker {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 156px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.10);
  padding: 6px;
  z-index: 1000;
  font-size: 0.85rem;
}
.picker-title {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #6c757d;
  padding: 4px 10px 6px;
}
.picker-opt {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}
.picker-opt:hover { background: rgba(13, 110, 253, 0.07); }
.picker-opt.selected { background: rgba(40, 167, 69, 0.10); color: #1e7a34; font-weight: 500; }
.picker-opt .check { font-size: 0.95rem; }

/* Dark theme — panel uses [data-theme="dark"] (manual toggle), so the
   prefers-color-scheme variant alone left this component looking like
   a white pill on a dark page. */
[data-theme="dark"] .live-indicator.is-live { background: rgba(40, 167, 69, 0.18); color: #4ddf6e; }
[data-theme="dark"] .live-indicator.is-paused { background: rgba(173, 181, 189, 0.12); color: #ced4da; }
[data-theme="dark"] .live-indicator.is-off { background: rgba(173, 181, 189, 0.08); color: #adb5bd; }
[data-theme="dark"] .live-indicator:focus-visible { outline-color: rgba(99, 132, 253, 0.6); }

[data-theme="dark"] .picker {
  background: var(--vxy-card-bg, #2b2f33);
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
  color: #e9ecef;
}
[data-theme="dark"] .picker-title { color: #adb5bd; }
[data-theme="dark"] .picker-opt { color: #e9ecef; }
[data-theme="dark"] .picker-opt:hover { background: rgba(255, 255, 255, 0.07); }
[data-theme="dark"] .picker-opt.selected { background: rgba(40, 167, 69, 0.18); color: #4ddf6e; }

/* Belt-and-suspenders for OS-dark with default light-theme attribute */
@media (prefers-color-scheme: dark) {
  .live-indicator.is-live { background: rgba(40, 167, 69, 0.18); color: #4ddf6e; }
}

@media (prefers-reduced-motion: reduce) {
  .live-indicator.is-live .dot { animation: none; }
}
</style>
