<!-- The "?" help tooltip. Faithful to the mockup: a 15px outlined circle that
     turns accent on hover/open and shows a dark bubble. Text via `text` prop. -->
<template>
  <span class="d2-ht" ref="trig" tabindex="0" role="button" :aria-label="text"
        @mouseenter="open" @mouseleave="close" @focus="open" @blur="close"
        @click.stop="toggle">?
  </span>
  <Teleport to="body">
    <div v-if="show" class="d2-ht-bubble" :style="pos" role="tooltip">{{ text }}</div>
  </Teleport>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
const props = defineProps({ text: { type: String, required: true } })
const trig = ref(null)
const show = ref(false)
const pos = ref({})
let showT = null, hideT = null

function place() {
  const r = trig.value?.getBoundingClientRect()
  if (!r) return
  const w = Math.min(280, window.innerWidth - 24)
  let left = r.left + r.width / 2 - w / 2 + window.scrollX
  left = Math.max(12, Math.min(left, window.scrollX + window.innerWidth - w - 12))
  const top = r.top + window.scrollY - 10
  pos.value = { left: left + 'px', top: top + 'px', width: w + 'px', transform: 'translateY(-100%)' }
}
function open() { clearTimeout(hideT); showT = setTimeout(() => { place(); show.value = true }, 120) }
function close() { clearTimeout(showT); hideT = setTimeout(() => { show.value = false }, 150) }
function toggle() { show.value ? (show.value = false) : (place(), show.value = true) }
onUnmounted(() => { clearTimeout(showT); clearTimeout(hideT) })
</script>

<style scoped>
.d2-ht {
  display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; border-radius: 50%; margin-left: 5px;
  border: 1px solid var(--d2-border-strong); color: var(--d2-text-3);
  font-size: 10px; font-weight: 700; line-height: 1; cursor: help;
  vertical-align: middle; user-select: none; transition: color .12s, border-color .12s;
}
.d2-ht:hover, .d2-ht:focus-visible { color: var(--d2-accent); border-color: var(--d2-accent); outline: none; }

/* The bubble is Teleport'd to <body>; the `pos` binding uses page (scrollX/Y)
   coordinates, so it MUST be absolutely positioned. Without this rule it fell
   into normal <body> flow → bottom-left corner. */
.d2-ht-bubble {
  position: absolute;
  z-index: 10000;
  max-width: 280px;
  padding: 8px 11px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.45;
  font-weight: 400;
  color: var(--d2-text-1, #e8e8ef);
  background: var(--d2-panel-2, #1d1d25);
  border: 1px solid var(--d2-border-strong, #3a3a46);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
  pointer-events: none;
  white-space: normal;
  word-break: break-word;
}
</style>
