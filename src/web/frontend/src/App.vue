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
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import Navbar from './components/Navbar.vue'
import DonateModal from './components/DonateModal.vue'
import { useSystemStore } from './stores/system'
import { useBrandingStore } from './stores/branding'

const route = useRoute()
const system = useSystemStore()
const branding = useBrandingStore()

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
  if (!isLoginPage.value) maybeOpenDonateReminder()
})
</script>
