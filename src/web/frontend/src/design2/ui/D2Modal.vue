<!-- Centered modal, matched 1:1 to the designer's handoff: fixed backdrop
     (rgba(10,11,14,.5), 24px breathing room), flex-centered on BOTH axes so the
     panel sits centered with a max-height and internal scroll — never full
     vertical height. Teleported to body. Sizes sm|md|lg|xl. `flush` removes
     body padding (for the full-bleed map modal). Slots: default/header/footer. -->
<template>
  <Teleport to="body">
    <Transition name="d2m">
      <!-- .d2-root on the SCRIM (not the card) so the design tokens resolve for
           the modal content, WITHOUT the card inheriting base.css's
           `.d2-root{min-height:100vh}` — that was forcing every modal card to
           full viewport height (top-anchored, not centered). -->
      <div v-if="open" class="d2m-scrim d2-root" @click.self="$emit('close')">
        <div class="d2m-card" :class="'sz-' + size" role="dialog" aria-modal="true">
          <div class="d2m-head">
            <slot name="header"><h3 class="d2m-title">{{ title }}</h3></slot>
            <button class="d2m-x" @click="$emit('close')" aria-label="Close">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg>
            </button>
          </div>
          <div class="d2m-body" :class="{ flush }"><slot /></div>
          <div v-if="$slots.footer" class="d2m-foot"><slot name="footer" /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  size: { type: String, default: 'md' }, // sm | md | lg | xl
  flush: { type: Boolean, default: false },
})
defineEmits(['close'])
</script>

<style scoped>
.d2m-scrim {
  position: fixed; inset: 0; z-index: 1200; background: rgba(10, 11, 14, .5);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.d2m-card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
  box-shadow: var(--shadow-lg); width: 100%;
  min-height: 0; height: auto; max-height: calc(100vh - 48px);  /* content-sized, never forced full-height */
  display: flex; flex-direction: column; overflow: hidden;
}
.sz-sm { max-width: 420px; } .sz-md { max-width: 560px; }
.sz-lg { max-width: 820px; } .sz-xl { max-width: 980px; }
.d2m-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 15px 20px; border-bottom: 1px solid var(--border); flex: none;
}
.d2m-title { font-size: 16px; font-weight: 650; color: var(--text); margin: 0; letter-spacing: -.01em; }
.d2m-x {
  width: 32px; height: 32px; border-radius: 8px; border: none; background: none;
  color: var(--text-3); cursor: pointer; flex: none; display: grid; place-items: center;
}
.d2m-x:hover { background: var(--panel-2); color: var(--text); }
.d2m-body { padding: 20px; overflow-y: auto; }
.d2m-body.flush { padding: 0; overflow: hidden; display: flex; flex-direction: column; }
.d2m-foot {
  display: flex; align-items: center; justify-content: flex-end; gap: 10px;
  padding: 13px 20px; border-top: 1px solid var(--border); flex: none;
}
.d2m-enter-active, .d2m-leave-active { transition: opacity .15s; }
.d2m-enter-from, .d2m-leave-to { opacity: 0; }
.d2m-enter-active .d2m-card, .d2m-leave-active .d2m-card { transition: transform .16s ease; }
.d2m-enter-from .d2m-card, .d2m-leave-to .d2m-card { transform: translateY(8px) scale(.99); }

@media (max-width: 620px) {
  .d2m-scrim { padding: 12px; align-items: flex-end; }
  .d2m-card { max-height: calc(100vh - 24px); border-radius: 18px; }
}
</style>
