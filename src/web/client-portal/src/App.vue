<template>
  <!-- Auth layout: bare page (login, register) -->
  <div v-if="layout === 'auth'">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>

  <!-- Client layout: header + content -->
  <Layout v-else>
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </Layout>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Layout from './components/Layout.vue'
import axios from 'axios'

const route = useRoute()
const router = useRouter()

const routerReady = ref(false)
router.isReady().then(() => { routerReady.value = true })

const layout = computed(() => {
  if (!routerReady.value) return 'auth'
  return route.meta?.layout || 'client'
})

// Apply theme class on body (also class .fx-portal for tokenized baseline).
function applyTheme(theme) {
  document.body.classList.add('fx-portal')
  document.body.classList.toggle('theme-light', theme !== 'dark')
  document.body.classList.toggle('theme-dark', theme === 'dark')
  document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light')
}
function readTheme() {
  const saved = localStorage.getItem('sb_theme')
  return saved === 'dark' ? 'dark' : 'light'
}
applyTheme(readTheme())

// Listen for theme changes from Layout.vue.
window.addEventListener('storage', (e) => {
  if (e.key === 'sb_theme') applyTheme(readTheme())
})
window.addEventListener('fx:theme', (e) => applyTheme(e.detail || readTheme()))

// Inject Inter Tight + JetBrains Mono webfonts (one-time).
onMounted(() => {
  if (!document.querySelector('link[data-fx-fonts]')) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap'
    link.setAttribute('data-fx-fonts', '1')
    document.head.appendChild(link)
  }
})

// Load branding from admin panel.
onMounted(async () => {
  try {
    const baseUrl = window.location.port === '10090' ? `${window.location.protocol}//${window.location.hostname}:10086` : ''
    const { data } = await axios.get(`${baseUrl}/api/v1/public/branding`)
    window.__branding = data
    if (data.branding_app_name) document.title = data.branding_app_name
    if (data.branding_favicon_url) {
      let link = document.querySelector("link[rel~='icon']")
      if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link) }
      link.href = data.branding_favicon_url
    }
  } catch {
    // Use defaults
  }
})
</script>

<style>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
