<template>
  <div v-if="isLoginPage">
    <router-view />
  </div>
  <div v-else class="app-wrapper" :class="{ 'sidebar-collapsed': system.sidebarCollapsed }">
    <Sidebar />
    <div class="sidebar-overlay" :class="{ active: system.sidebarOpen }" @click="system.closeSidebar()"></div>
    <div class="main-content">
      <Navbar @open-donate="donateOpen = true" />
      <div class="content-area">
        <router-view />
      </div>
    </div>
    <DonateModal v-model="donateOpen" @dismissed="onDonateDismissed" />
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
import { useSystemStore } from './stores/system'
import { useBrandingStore } from './stores/branding'
import { useLicenseStore } from './stores/license'

const route = useRoute()
const system = useSystemStore()
const branding = useBrandingStore()
const license = useLicenseStore()

const isLoginPage = computed(() => route.name === 'Login')

const donateOpen = ref(false)
const DONATE_DISMISS_KEY = 'flirexa_donate_dismissed_at'
const REMINDER_INTERVAL_MS = 7 * 24 * 60 * 60 * 1000

function onDonateDismissed() {
  try {
    localStorage.setItem(DONATE_DISMISS_KEY, String(Date.now()))
  } catch (_) { /* private browsing — ignore */ }
}

function maybeOpenDonateReminder() {
  let last
  try { last = localStorage.getItem(DONATE_DISMISS_KEY) } catch (_) { return }
  // First-install: never dismissed → show after a short delay so the dashboard renders first.
  if (!last) {
    setTimeout(() => { donateOpen.value = true }, 1500)
    return
  }
  const ts = parseInt(last, 10)
  if (Number.isFinite(ts) && Date.now() - ts >= REMINDER_INTERVAL_MS) {
    setTimeout(() => { donateOpen.value = true }, 1500)
  }
}

onMounted(() => {
  system.initTheme()
  branding.fetchBranding()
  // Load license features once at app startup so feature-gated UI bits
  // (Mikrotik connection mode in Add Server, etc.) can read them
  // without each view having to remember to call `license.load()`.
  // Skip on the login page — /api/v1/system/license requires auth and
  // would just 401 anyway; will get loaded after login by the watcher below.
  if (!isLoginPage.value && !license.loaded) license.load()
  if (!isLoginPage.value) maybeOpenDonateReminder()
})

// When the user navigates away from the login page (i.e. just logged
// in), pull the license features. Without this, post-login renders use
// the empty default and feature-gated UI stays hidden until the next
// full-page reload.
watch(isLoginPage, (onLogin) => {
  if (!onLogin && !license.loaded) license.load()
})
</script>
