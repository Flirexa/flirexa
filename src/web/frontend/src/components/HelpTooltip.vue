<template>
  <span class="help-tooltip-trigger" ref="triggerRef"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @click.stop="onTap"
    @keydown.enter.stop="onTap"
    @keydown.space.prevent.stop="onTap"
    tabindex="0"
    role="button"
    :aria-label="text"
    aria-haspopup="true"
    :aria-expanded="visible">
    <svg class="help-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="8" cy="8" r="7.5" stroke="currentColor" stroke-opacity="0.5"/>
      <text x="8" y="12" text-anchor="middle" font-size="10" font-weight="700" fill="currentColor" fill-opacity="0.7" font-family="sans-serif">?</text>
    </svg>
  </span>

  <Teleport to="body">
    <Transition name="ht-fade">
      <div v-if="visible" class="help-tooltip-bubble" :style="bubbleStyle" role="tooltip">
        <div class="help-tooltip-content">{{ text }}</div>
        <div class="help-tooltip-arrow" :style="arrowStyle"></div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'

const props = defineProps({
  text: { type: String, required: true }
})

const triggerRef = ref(null)
const visible = ref(false)
const bubblePos = ref({ top: 0, left: 0, arrowLeft: 0, placement: 'top' })

let showTimer = null
let hideTimer = null

function calcPos() {
  if (!triggerRef.value) return
  const r = triggerRef.value.getBoundingClientRect()
  const bw = Math.min(280, window.innerWidth - 24)
  const bh = 80 // approx
  const margin = 8

  let placement = 'top'
  let top, left

  // Prefer top, fallback to bottom
  if (r.top - bh - margin > 0) {
    placement = 'top'
    top = r.top - bh - margin + window.scrollY
  } else {
    placement = 'bottom'
    top = r.bottom + margin + window.scrollY
  }

  // Center horizontally, clamp to viewport
  left = r.left + r.width / 2 - bw / 2 + window.scrollX
  left = Math.max(12 + window.scrollX, Math.min(left, window.scrollX + window.innerWidth - bw - 12))

  // Arrow offset relative to bubble
  const arrowLeft = Math.max(12, Math.min(r.left + r.width / 2 - left + window.scrollX, bw - 12))

  bubblePos.value = { top, left, bw, arrowLeft, placement }
}

const bubbleStyle = computed(() => ({
  top: bubblePos.value.top + 'px',
  left: bubblePos.value.left + 'px',
  width: bubblePos.value.bw + 'px',
}))

const arrowStyle = computed(() => ({
  left: bubblePos.value.arrowLeft + 'px',
  ...(bubblePos.value.placement === 'bottom' ? { top: '-5px', transform: 'rotate(180deg)' } : { bottom: '-5px' })
}))

function show() {
  clearTimeout(hideTimer)
  calcPos()
  visible.value = true
}

function hide() {
  clearTimeout(showTimer)
  visible.value = false
}

function onMouseEnter() {
  clearTimeout(hideTimer)
  showTimer = setTimeout(show, 150)
}

function onMouseLeave() {
  clearTimeout(showTimer)
  hideTimer = setTimeout(hide, 200)
}

function onTap() {
  if (visible.value) {
    hide()
  } else {
    show()
  }
}

function onOutsideClick(e) {
  if (triggerRef.value && !triggerRef.value.contains(e.target)) {
    hide()
  }
}

document.addEventListener('click', onOutsideClick, true)
onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick, true)
  clearTimeout(showTimer)
  clearTimeout(hideTimer)
})
</script>

<style>
.help-tooltip-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--vxy-muted, #6c757d);
  position: relative;
  vertical-align: middle;
  margin-left: 4px;
  flex-shrink: 0;
}

.help-tooltip-trigger::after {
  content: '';
  position: absolute;
  inset: -6px;
}

.help-tooltip-trigger:focus-visible {
  outline: 2px solid var(--vxy-primary, #7367f0);
  outline-offset: 2px;
  border-radius: 50%;
}

.help-tooltip-trigger:hover .help-icon,
.help-tooltip-trigger:focus-visible .help-icon {
  color: var(--vxy-primary, #7367f0);
}

.help-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  transition: color 0.15s;
}

.help-tooltip-bubble {
  position: absolute;
  z-index: 9999;
  background: #1e2533;
  color: #e8eaf0;
  border-radius: 8px;
  padding: 9px 13px;
  font-size: 12.5px;
  line-height: 1.55;
  box-shadow: 0 4px 20px rgba(0,0,0,0.35);
  pointer-events: none;
  max-width: 280px;
}

.help-tooltip-content {
  position: relative;
  z-index: 1;
}

.help-tooltip-arrow {
  position: absolute;
  left: 16px;
  width: 10px;
  height: 5px;
  overflow: visible;
}

.help-tooltip-arrow::after {
  content: '';
  position: absolute;
  left: 0;
  width: 10px;
  height: 10px;
  background: #1e2533;
  transform: rotate(45deg);
  bottom: -5px;
}

.ht-fade-enter-active,
.ht-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.ht-fade-enter-from,
.ht-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
