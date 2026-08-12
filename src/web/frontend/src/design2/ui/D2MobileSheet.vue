<template>
  <Transition name="d2-sheet-fade">
      <div v-if="open" class="d2-mobile-sheet-layer" role="presentation" @click.self="$emit('close')">
        <section class="d2-mobile-sheet" role="dialog" aria-modal="true" :aria-label="title">
          <div class="d2-mobile-sheet-handle" aria-hidden="true"></div>
          <header class="d2-mobile-sheet-header">
            <div class="d2-mobile-sheet-heading">
              <slot name="title"><h3>{{ title }}</h3></slot>
            </div>
            <button type="button" class="d2-mobile-sheet-close" :aria-label="closeLabel" @click="$emit('close')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </header>
          <div class="d2-mobile-sheet-body"><slot /></div>
          <footer v-if="$slots.footer" class="d2-mobile-sheet-footer"><slot name="footer" /></footer>
        </section>
      </div>
  </Transition>
</template>

<script setup>
import { onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  closeLabel: { type: String, default: 'Close' },
})
defineEmits(['close'])

let previousOverflow = ''
let bodyLocked = false
watch(() => props.open, (open) => {
  if (typeof document === 'undefined') return
  if (open && !bodyLocked) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    bodyLocked = true
  } else if (!open && bodyLocked) {
    document.body.style.overflow = previousOverflow
    bodyLocked = false
  }
}, { immediate: true })
onBeforeUnmount(() => {
  if (typeof document !== 'undefined' && bodyLocked) document.body.style.overflow = previousOverflow
})
</script>

<style scoped>
.d2-mobile-sheet-layer {
  --sheet-panel: var(--panel, #fff);
  --sheet-panel-2: var(--panel-2, #f7f8fa);
  --sheet-border: var(--border, #e5e7eb);
  --sheet-text: var(--text, #111827);
  --sheet-text-3: var(--text-3, #6b7280);
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 16px 12px max(12px, env(safe-area-inset-bottom));
  background: rgba(7, 10, 18, .44);
  backdrop-filter: blur(2px);
}
.d2-mobile-sheet {
  width: min(560px, 100%);
  max-height: min(82dvh, 760px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--sheet-text);
  background: var(--sheet-panel);
  border: 1px solid var(--sheet-border);
  border-radius: 18px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .26);
}
.d2-mobile-sheet-handle { width: 38px;height:4px;border-radius:99px;background:var(--sheet-border);margin:8px auto 2px;flex:none; }
.d2-mobile-sheet-header { display:flex;align-items:center;gap:12px;padding:10px 14px 12px;border-bottom:1px solid var(--sheet-border); }
.d2-mobile-sheet-heading { min-width:0;flex:1; }
.d2-mobile-sheet-heading h3 { margin:0;font-size:16px;font-weight:680;line-height:1.3; }
.d2-mobile-sheet-close { width:36px;height:36px;display:grid;place-items:center;flex:none;border:0;border-radius:10px;background:var(--sheet-panel-2);color:var(--sheet-text-3);cursor:pointer; }
.d2-mobile-sheet-body { min-height:0;overflow:auto;padding:14px;overscroll-behavior:contain; }
.d2-mobile-sheet-footer { display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:12px 14px max(12px, env(safe-area-inset-bottom));border-top:1px solid var(--sheet-border); }
.d2-sheet-fade-enter-active,.d2-sheet-fade-leave-active { transition:opacity .18s ease; }
.d2-sheet-fade-enter-active .d2-mobile-sheet,.d2-sheet-fade-leave-active .d2-mobile-sheet { transition:transform .2s ease; }
.d2-sheet-fade-enter-from,.d2-sheet-fade-leave-to { opacity:0; }
.d2-sheet-fade-enter-from .d2-mobile-sheet,.d2-sheet-fade-leave-to .d2-mobile-sheet { transform:translateY(24px); }
@media (min-width:901px) {
  .d2-mobile-sheet-layer { align-items:center; }
  .d2-mobile-sheet { border-radius:16px; }
}
</style>
