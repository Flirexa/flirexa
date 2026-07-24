<!-- Labelled input. Label sits above the field. Optional help ("?") via the
     `help` slot, optional hint text below. v-model compatible. -->
<template>
  <div class="d2f">
    <label v-if="label" class="d2f-label">{{ label }}<slot name="help" /></label>
    <input
      class="d2f-input" :class="{ err: !!error }"
      :type="type" :value="modelValue" :placeholder="placeholder" :disabled="disabled"
      :min="min" :max="max" :minlength="minlength" :maxlength="maxlength"
      :autocomplete="autocomplete"
      @input="$emit('update:modelValue', type === 'number' ? ($event.target.value === '' ? null : Number($event.target.value)) : $event.target.value)" />
    <div v-if="error" class="d2f-err">{{ error }}</div>
    <div v-else-if="hint" class="d2f-hint">{{ hint }}</div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  modelValue: { type: [String, Number], default: '' },
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  min: { type: [String, Number], default: undefined },
  max: { type: [String, Number], default: undefined },
  minlength: { type: [String, Number], default: undefined },
  maxlength: { type: [String, Number], default: undefined },
  autocomplete: { type: String, default: undefined },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.d2f { display: flex; flex-direction: column; gap: 6px; }
.d2f-label { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: var(--d2-text-2); }
.d2f-input {
  width: 100%; padding: 9px 12px; border-radius: 10px;
  border: 1px solid var(--d2-border-strong); background: var(--d2-panel); color: var(--d2-text);
  font-family: inherit; font-size: 14px; transition: border-color .12s, box-shadow .12s;
}
.d2f-input:focus { outline: none; border-color: var(--d2-accent); box-shadow: 0 0 0 3px var(--d2-accent-ring); }
.d2f-input.err { border-color: var(--d2-red); }
.d2f-input::placeholder { color: var(--d2-text-3); }
.d2f-input:disabled { background: var(--d2-panel-2); opacity: .7; }
.d2f-hint { font-size: 12px; color: var(--d2-text-3); }
.d2f-err { font-size: 12px; color: var(--d2-red); }
</style>
