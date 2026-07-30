<template>
  <div v-if="isLoginPage">
    <router-view />
  </div>
  <!-- NEW design variant (default) — full shell + router content -->
  <template v-else-if="design.isNew">
    <D2App />
    <UpgradeBanner />
    <UpgradeModal />
  </template>
  <!-- Legacy variant — unchanged -->
  <div v-else class="app-wrapper" :class="{ 'sidebar-collapsed': system.sidebarCollapsed }">
    <Sidebar />
    <div class="sidebar-overlay" :class="{ active: system.sidebarOpen }" @click="system.closeSidebar()"></div>
    <div class="main-content">
      <Navbar :show-donate="showLegacyDonate" @open-donate="donateOpen = true" />
      <div class="content-area">
        <router-view />
      </div>
    </div>
    <DonateModal v-if="showLegacyDonate" v-model="donateOpen" />
    <UpgradeBanner />
    <UpgradeModal />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import Navbar from './components/Navbar.vue'
import DonateModal from './components/DonateModal.vue'
import UpgradeBanner from './components/UpgradeBanner.vue'
import UpgradeModal from './components/UpgradeModal.vue'
import D2App from './design2/D2App.vue'
import { useDesignMode } from './stores/designMode'
import { useSystemStore } from './stores/system'
import { useBrandingStore } from './stores/branding'
import { useLicenseStore } from './stores/license'

const route = useRoute()
const design = useDesignMode()
const system = useSystemStore()
const branding = useBrandingStore()
const license = useLicenseStore()

const isLoginPage = computed(() => route.name === 'Login')

const donateOpen = ref(false)
// The old donation surface belongs only to the legacy FREE UI. The new shell
// owns its own design2 modal, and paid operators must never see either one.
const showLegacyDonate = computed(() =>
  !design.isNew && license.loaded && !license.isPaid
)

onMounted(() => {
  system.initTheme()
  branding.fetchBranding()
  // Load license features once at app startup so feature-gated UI bits
  // (Mikrotik connection mode in Add Server, etc.) can read them
  // without each view having to remember to call `license.load()`.
  // Skip on the login page — /api/v1/system/license requires auth and
  // would just 401 anyway; will get loaded after login by the watcher below.
  if (!isLoginPage.value && !license.loaded) license.load()
})

// When the user navigates away from the login page (i.e. just logged
// in), pull the license features. Without this, post-login renders use
// the empty default and feature-gated UI stays hidden until the next
// full-page reload.
watch(isLoginPage, (onLogin) => {
  if (!onLogin && !license.loaded) license.load()
})

watch(showLegacyDonate, (allowed) => {
  if (!allowed) donateOpen.value = false
})
</script>
