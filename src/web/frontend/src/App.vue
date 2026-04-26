<template>
  <div v-if="isLoginPage">
    <router-view />
  </div>
  <div v-else class="app-wrapper" :class="{ 'sidebar-collapsed': system.sidebarCollapsed }">
    <Sidebar />
    <div class="sidebar-overlay" :class="{ active: system.sidebarOpen }" @click="system.closeSidebar()"></div>
    <div class="main-content">
      <Navbar />
      <div class="content-area">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import Navbar from './components/Navbar.vue'
import { useSystemStore } from './stores/system'
import { useBrandingStore } from './stores/branding'

const route = useRoute()
const system = useSystemStore()
const branding = useBrandingStore()

const isLoginPage = computed(() => route.name === 'Login')

onMounted(() => {
  system.initTheme()
  branding.fetchBranding()
})
</script>
