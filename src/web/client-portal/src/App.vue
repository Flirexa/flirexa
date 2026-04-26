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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Layout from './components/Layout.vue'
import axios from 'axios'

const route = useRoute()
const router = useRouter()

// Wait for router to be ready before deciding layout to avoid flash-mounting
// Layout before the route meta is resolved (causes /features 401 → redirect loop)
const routerReady = ref(false)
router.isReady().then(() => { routerReady.value = true })

const layout = computed(() => {
  if (!routerReady.value) return 'auth'
  return route.meta?.layout || 'client'
})

// Load branding on app mount
onMounted(async () => {
  try {
    const baseUrl = window.location.port === '10090' ? `${window.location.protocol}//${window.location.hostname}:10086` : ''
    const { data } = await axios.get(`${baseUrl}/api/v1/public/branding`)
    window.__branding = data

    // Apply title
    if (data.branding_app_name) {
      document.title = data.branding_app_name
    }
    // Apply primary color
    if (data.branding_primary_color) {
      document.documentElement.style.setProperty('--brand-primary', data.branding_primary_color)
    }
    // Apply favicon
    if (data.branding_favicon_url) {
      let link = document.querySelector("link[rel~='icon']")
      if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link) }
      link.href = data.branding_favicon_url
    }
  } catch (e) {
    // Use defaults
  }
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
