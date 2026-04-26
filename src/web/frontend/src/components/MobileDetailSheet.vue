<template>
  <teleport to="body">
    <transition name="vxy-sheet-fade">
      <div v-if="modelValue" class="vxy-sheet-backdrop" @click="close" />
    </transition>
    <transition name="vxy-sheet-slide">
      <div v-if="modelValue" class="vxy-sheet" role="dialog" :aria-label="title">
        <div class="vxy-sheet-handle" />
        <div class="vxy-sheet-header">
          <div class="vxy-sheet-title-wrap">
            <h6 class="vxy-sheet-title">{{ title }}</h6>
            <small v-if="subtitle" class="text-muted vxy-sheet-subtitle">{{ subtitle }}</small>
          </div>
          <slot name="badge" />
          <button class="btn-close vxy-sheet-close" @click="close" />
        </div>
        <div class="vxy-sheet-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="vxy-sheet-footer">
          <slot name="footer" />
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
defineProps({
  modelValue: Boolean,
  title: String,
  subtitle: String,
})
const emit = defineEmits(['update:modelValue'])
const close = () => emit('update:modelValue', false)
</script>
