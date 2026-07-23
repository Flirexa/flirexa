<!-- Soft-tinted status pill. tone: accent|green|blue|amber|purple|red|gray. -->
<template>
  <span class="d2-badge" :class="`t-${tone}`"><slot /></span>
</template>

<script setup>
defineProps({ tone: { type: String, default: 'gray' } })
</script>

<style scoped>
.d2-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 9px; border-radius: 999px;
  font-size: 12px; font-weight: 600; line-height: 1.4; white-space: nowrap;
}
.t-accent { background: var(--d2-accent-soft); color: var(--d2-accent); }
.t-green  { background: var(--d2-green-soft);  color: var(--d2-green); }
.t-blue   { background: var(--d2-blue-soft);   color: var(--d2-blue); }
.t-amber  { background: var(--d2-amber-soft);  color: var(--d2-amber); }
.t-purple { background: var(--d2-purple-soft); color: var(--d2-purple); }
.t-red    { background: var(--d2-red-soft);    color: var(--d2-red); }
.t-gray   { background: var(--d2-gray-soft);   color: var(--d2-text-2); }
</style>
