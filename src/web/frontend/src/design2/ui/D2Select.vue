<!-- Labelled select. options: [{ value, label }] or pass raw via default slot. -->
<template>
  <div class="d2f">
    <label v-if="label" class="d2f-label">{{ label }}<slot name="help" /></label>
    <div class="d2s-wrap">
      <select class="d2f-input d2s" :value="modelValue" :disabled="disabled"
              @change="$emit('update:modelValue', coerce($event.target.value))">
        <option v-if="placeholder" :value="''" disabled>{{ placeholder }}</option>
        <slot>
          <option v-for="o in options" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
        </slot>
      </select>
      <i class="mdi mdi-chevron-down d2s-caret"></i>
    </div>
    <div v-if="hint" class="d2f-hint">{{ hint }}</div>
  </div>
</template>

<script setup>
const props = defineProps({
  label: { type: String, default: '' },
  modelValue: { type: [String, Number, null], default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  hint: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  numeric: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
function coerce(v) { return props.numeric ? (v === '' ? null : Number(v)) : v }
</script>

<style scoped>
.d2f { display: flex; flex-direction: column; gap: 6px; }
.d2f-label { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: var(--d2-text-2); }
.d2s-wrap { position: relative; }
.d2f-input {
  width: 100%; padding: 9px 12px; border-radius: 10px;
  border: 1px solid var(--d2-border-strong); background: var(--d2-panel); color: var(--d2-text);
  font-family: inherit; font-size: 14px;
}
.d2s { appearance: none; padding-right: 34px; cursor: pointer; }
.d2f-input:focus { outline: none; border-color: var(--d2-accent); box-shadow: 0 0 0 3px var(--d2-accent-ring); }
.d2s-caret { position: absolute; right: 11px; top: 50%; transform: translateY(-50%); color: var(--d2-text-3); pointer-events: none; font-size: 18px; }
.d2f-hint { font-size: 12px; color: var(--d2-text-3); }
</style>
