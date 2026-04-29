<template>
  <FeatureLockedCard
    v-if="locked"
    :title="title"
    :description="description"
    :tier="tier"
    :feature="feature"
  />
  <slot v-else />
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useLicenseStore } from '../stores/license'
import FeatureLockedCard from './FeatureLockedCard.vue'

const props = defineProps({
  feature:     { type: String, required: true },
  tier:        { type: String, default: 'business' },
  title:       { type: String, required: true },
  description: { type: String, required: true },
})

const license = useLicenseStore()

onMounted(() => { if (!license.loaded) license.load() })

const locked = computed(() => license.loaded && !license.has(props.feature))
</script>
