<!-- Switch toggle with optional inline label + help slot. v-model boolean. -->
<template>
  <label class="d2tg">
    <span class="d2tg-sw" :class="{ on: modelValue }" @click.prevent="$emit('update:modelValue', !modelValue)">
      <span class="d2tg-knob"></span>
    </span>
    <span v-if="label || $slots.default" class="d2tg-lbl"><slot>{{ label }}</slot><slot name="help" /></span>
  </label>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, default: '' },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.d2tg { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; user-select: none; }
.d2tg-sw {
  width: 38px; height: 22px; border-radius: 999px; background: var(--d2-border-strong);
  position: relative; flex-shrink: 0; transition: background .15s;
}
.d2tg-sw.on { background: var(--d2-accent); }
.d2tg-knob {
  position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.25); transition: transform .15s;
}
.d2tg-sw.on .d2tg-knob { transform: translateX(16px); }
.d2tg-lbl { display: inline-flex; align-items: center; font-size: 14px; color: var(--d2-text); }
</style>
