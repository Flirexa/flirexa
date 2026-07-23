<!-- Designer's Lucide-style icon. Uses his sprite (inlined once in D2App).
     <Icon name="users" :size="18" /> → <use href="#ic-users">. -->
<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" class="d2ic"><use :href="'#ic-' + name" /></svg>
</template>
<script setup>
defineProps({ name: { type: String, required: true }, size: { type: [String, Number], default: 18 } })
</script>
<style scoped>
.d2ic { display: inline-block; vertical-align: middle; flex: none; }
</style>
