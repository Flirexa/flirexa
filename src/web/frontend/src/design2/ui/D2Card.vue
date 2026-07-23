<!-- Panel card — the base surface used across the new design. -->
<template>
  <div class="d2-card" :class="{ pad: padded }">
    <div v-if="$slots.header || title" class="d2-card-head">
      <slot name="header"><span class="d2-card-title">{{ title }}</span></slot>
      <slot name="actions" />
    </div>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  padded: { type: Boolean, default: true },
})
</script>

<style scoped>
.d2-card {
  background: var(--d2-panel);
  border: 1px solid var(--d2-border);
  border-radius: 14px;
  box-shadow: var(--d2-shadow);
}
.d2-card.pad { padding: 18px 20px; }
.d2-card-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 14px;
}
.d2-card-title { font-size: 15px; font-weight: 700; color: var(--d2-text); }
</style>
