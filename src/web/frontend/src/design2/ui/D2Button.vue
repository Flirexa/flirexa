<!-- Button — variants: primary (accent), secondary (bordered), ghost, danger.
     Sizes: sm | md. Faithful to the mockup's flat pill buttons. -->
<template>
  <button class="d2-btn" :class="[`v-${variant}`, `s-${size}`, { block, loading }]" :disabled="disabled || loading">
    <span v-if="loading" class="d2-btn-spin"></span>
    <i v-else-if="icon" :class="'mdi mdi-' + icon" class="d2-btn-ic"></i>
    <span v-if="$slots.default" class="d2-btn-lbl"><slot /></span>
  </button>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'primary' }, // primary | secondary | ghost | danger
  size: { type: String, default: 'md' },          // sm | md
  icon: { type: String, default: '' },
  block: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
</script>

<style scoped>
.d2-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  border-radius: 10px; font-family: inherit; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; transition: background .12s, border-color .12s, color .12s, opacity .12s;
  white-space: nowrap;
}
.d2-btn:disabled { opacity: .55; cursor: not-allowed; }
.d2-btn.block { width: 100%; }
.s-md { padding: 9px 16px; font-size: 14px; }
.s-sm { padding: 6px 11px; font-size: 13px; }
.d2-btn-ic { font-size: 17px; }

.v-primary { background: var(--d2-accent); color: #fff; }
.v-primary:not(:disabled):hover { filter: brightness(1.06); }
.v-secondary { background: var(--d2-panel); border-color: var(--d2-border-strong); color: var(--d2-text); }
.v-secondary:not(:disabled):hover { background: var(--d2-panel-2); }
.v-ghost { background: transparent; color: var(--d2-text-2); }
.v-ghost:not(:disabled):hover { background: var(--d2-panel-2); color: var(--d2-text); }
.v-danger { background: var(--d2-red); color: #fff; }
.v-danger:not(:disabled):hover { filter: brightness(1.06); }

.d2-btn-spin {
  width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid currentColor; border-right-color: transparent;
  animation: d2spin .6s linear infinite;
}
@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
