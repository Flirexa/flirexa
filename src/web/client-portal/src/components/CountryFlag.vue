<template>
  <span
    class="fx-country-flag"
    :class="{ 'is-fallback': !flag }"
    :title="resolvedCode || undefined"
    aria-hidden="true"
  >
    <span v-if="flag" class="fx-country-emoji">{{ flag }}</span>
    <FxIcon v-else name="globe" :size="iconSize" />
  </span>
</template>

<script setup>
import { computed } from 'vue'
import FxIcon from './FxIcon.vue'
import { countryCodeFromLocation, countryFlagEmoji } from '../utils.js'

const props = defineProps({
  code: { type: String, default: '' },
  location: { type: String, default: '' },
  name: { type: String, default: '' },
  size: { type: [Number, String], default: 30 },
})

const resolvedCode = computed(() => {
  const explicit = String(props.code || '').trim().toUpperCase()
  return /^[A-Z]{2}$/.test(explicit)
    ? explicit
    : countryCodeFromLocation(props.location, props.name)
})
const flag = computed(() => countryFlagEmoji(resolvedCode.value))
const iconSize = computed(() => Math.max(14, Math.round(Number(props.size || 30) * .5)))
const flagSize = computed(() => `${Number(props.size || 30)}px`)
</script>

<style scoped>
.fx-country-flag {
  width: v-bind(flagSize);
  height: v-bind(flagSize);
  min-width: v-bind(flagSize);
  display: inline-grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: var(--bg-elev);
  color: var(--text-3);
  line-height: 1;
  box-shadow: var(--shadow-sm);
}
.fx-country-emoji {
  display: block;
  font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;
  font-size: calc(v-bind(flagSize) * .62);
  line-height: 1;
  transform: translateY(-.02em);
}
.fx-country-flag.is-fallback { box-shadow: none; }
</style>
