<!-- Root of the NEW design (the designer's UI). Wraps everything in .d2-root
     (so his tokens/base only apply here), inlines his icon sprite once so every
     <use href="#ic-..."> resolves, and renders his shell. -->
<template>
  <div class="d2-root">
    <div class="d2-sprite" v-html="sprite"></div>
    <D2Shell />
    <!-- Global in-app confirm host — one instance backs every d2confirm() call.
         Replaces native confirm(), which browsers can silently suppress. -->
    <D2Modal :open="confirmState.open" :title="tr('common.confirm') || 'Confirm'" size="sm" @close="resolveConfirm(false)">
      <p style="font-size:13.5px;color:var(--text-2);line-height:1.55;margin:0;white-space:pre-wrap">{{ confirmState.message }}</p>
      <template #footer>
        <D2Button variant="secondary" @click="resolveConfirm(false)">{{ confirmState.cancelLabel || (tr('common.cancel') || 'Cancel') }}</D2Button>
        <D2Button :variant="confirmState.danger ? 'danger' : 'primary'" @click="resolveConfirm(true)">{{ confirmState.confirmLabel || (tr('common.confirm') || 'Confirm') }}</D2Button>
      </template>
    </D2Modal>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import './tokens.css'
import './base.css'
import './handoff.css'
import rawSprite from './icons.svg?raw'
import D2Shell from './shell/D2Shell.vue'
import D2Modal from './ui/D2Modal.vue'
import D2Button from './ui/D2Button.vue'
import { confirmState, resolveConfirm } from './ui/confirm'
const sprite = computed(() => rawSprite.replace(/<\?xml[^>]*\?>/, ''))
const { t } = useI18n()
function tr(k, p) { try { const s = t(k, p || {}); return s === k ? '' : s } catch (_) { return '' } }
</script>

<style scoped>
.d2-sprite { display: none; }
</style>
