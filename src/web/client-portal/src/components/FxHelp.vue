<template>
  <span class="fx-help" tabindex="0"
        @mouseenter="open = true" @mouseleave="open = false"
        @focus="open = true" @blur="open = false"
        @click.stop="open = !open">
    <span class="fx-help-mark" aria-label="Help">?</span>
    <transition name="fx-help-pop">
      <span v-if="open" class="fx-help-bubble" :class="placement">
        <slot>{{ text }}</slot>
      </span>
    </transition>
  </span>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  text: { type: String, default: '' },
  placement: { type: String, default: 'top' },
})

const open = ref(false)
</script>

<style scoped>
.fx-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin-left: 6px;
  cursor: help;
  outline: none;
}
.fx-help-mark {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-3, color-mix(in oklab, var(--text) 8%, transparent));
  color: var(--text-2);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  font-family: var(--font-sans, inherit);
  transition: background .15s, color .15s;
  user-select: none;
}
.fx-help:hover .fx-help-mark,
.fx-help:focus .fx-help-mark {
  background: var(--accent-soft, color-mix(in oklab, var(--accent) 16%, transparent));
  color: var(--accent);
}
.fx-help-bubble {
  position: absolute;
  z-index: 50;
  width: max-content;
  max-width: 280px;
  padding: 8px 11px;
  border-radius: var(--r-md, 8px);
  background: var(--bg-card, var(--bg-2));
  color: var(--text);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.45;
  text-transform: none;
  letter-spacing: 0;
  white-space: normal;
  border: 1px solid var(--border);
  box-shadow:
    0 8px 24px -8px rgba(0, 0, 0, .35),
    0 0 0 1px color-mix(in oklab, var(--accent) 6%, transparent);
  pointer-events: none;
}
.fx-help-bubble.top {
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
}
.fx-help-bubble.bottom {
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
}
.fx-help-bubble.right {
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
}
.fx-help-bubble.left {
  right: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
}
.fx-help-pop-enter-active, .fx-help-pop-leave-active {
  transition: opacity .15s ease, transform .15s ease;
}
.fx-help-pop-enter-from, .fx-help-pop-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
.fx-help-bubble.right.fx-help-pop-enter-from,
.fx-help-bubble.right.fx-help-pop-leave-to {
  transform: translateY(-50%) translateX(4px);
}
.fx-help-bubble.left.fx-help-pop-enter-from,
.fx-help-bubble.left.fx-help-pop-leave-to {
  transform: translateY(-50%) translateX(-4px);
}
</style>
