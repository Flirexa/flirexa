<template>
  <div class="top-bar">
    <div class="d-flex align-items-center gap-3">
      <button class="topbar-icon-btn d-lg-none" @click="system.toggleSidebar()" title="Menu">
        <i class="mdi mdi-menu"></i>
      </button>
      <button class="topbar-icon-btn d-none d-lg-flex sidebar-collapse-btn" @click="system.collapseSidebar()" :title="system.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'">
        <i :class="system.sidebarCollapsed ? 'mdi mdi-menu' : 'mdi mdi-menu-open'"></i>
      </button>
      <div>
        <h5 class="mb-0">{{ $t(`nav.${routeKey}`) }}</h5>
        <nav aria-label="breadcrumb" class="d-none d-sm-block">
          <ol class="breadcrumb mb-0" style="font-size:.78rem">
            <li class="breadcrumb-item"><a href="/">{{ $t('nav.home') || 'Home' }}</a></li>
            <li class="breadcrumb-item active">{{ $t(`nav.${routeKey}`) }}</li>
          </ol>
        </nav>
      </div>
    </div>

    <div class="d-flex align-items-center gap-2">
      <!-- Support the author — first in the right group, text + heart -->
      <button class="topbar-donate-pill" @click="$emit('open-donate')" :title="$t('donate.tooltip')">
        <i class="mdi mdi-heart"></i>
        <span class="topbar-donate-pill-label">{{ $t('donate.button') }}</span>
      </button>

      <!-- Language -->
      <div class="vxy-dropdown">
        <button class="topbar-icon-btn" @click="langOpen = !langOpen" title="Language">
          <span style="font-size:.8rem;font-weight:600">{{ currentLangFlag }}</span>
        </button>
        <div class="vxy-dropdown-menu" v-if="langOpen" @mouseleave="langOpen=false">
          <button
            v-for="l in languages" :key="l.code"
            class="vxy-dropdown-item"
            :class="{ active: currentLang === l.code }"
            @click="setLang(l.code)"
          >
            <span>{{ l.flag }}</span><span>{{ l.name }}</span>
          </button>
        </div>
      </div>

      <!-- Theme toggle -->
      <button class="topbar-icon-btn" @click="toggleTheme"
        :title="system.theme === 'dark' ? $t('themes.light') : $t('themes.dark')"
        style="touch-action:manipulation;user-select:none;-webkit-tap-highlight-color:transparent">
        <i :class="system.theme === 'dark' ? 'mdi mdi-weather-sunny' : 'mdi mdi-weather-night'"></i>
      </button>

      <!-- Update available — only when a newer version is on the channel -->
      <router-link
        v-if="updateBadge.available"
        to="/updates"
        class="topbar-icon-btn topbar-update-btn"
        :title="updateBadge.title"
      >
        <i class="mdi mdi-package-up"></i>
        <span class="topbar-update-dot"></span>
      </router-link>

      <!-- Refresh — hidden on very small screens to save space -->
      <button class="topbar-icon-btn d-none d-sm-flex" @click="refreshData" title="Refresh">
        <i class="mdi mdi-refresh"></i>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSystemStore } from '../stores/system'
import api from '../api'

defineEmits(['open-donate'])

const route = useRoute()
const system = useSystemStore()
const { locale, t } = useI18n()

const langOpen = ref(false)

// ── Update-available badge ──────────────────────────────────────────────────
// Polls /api/v1/updates/status every 60 seconds + on tab focus + on route
// change. The backend cache makes /status cheap (no upstream call unless its
// own 6h tick has elapsed), so this is just UI-side reconcile against fresh
// data without forcing the operator to click "Check for updates".
const updateBadge = ref({ available: false, title: '' })
let _updateBadgeTimer = null

async function refreshUpdateBadge() {
  try {
    const r = await api.get('/updates/status', { timeout: 3000 })
    const av = r.data?.available_update
    if (av && av.version) {
      updateBadge.value = {
        available: true,
        title: `${t('updates.newVersionAvailable') || 'New version available'}: ${av.version}`,
      }
    } else {
      updateBadge.value = { available: false, title: '' }
    }
  } catch {
    // Silent — never block the navbar render on update-check failures
  }
}

function _refreshOnFocus() { if (!document.hidden) refreshUpdateBadge() }

// Refresh whenever the user navigates between admin pages — every route change
// is a chance to surface a freshly-published version without waiting up to 60s.
watch(() => route.fullPath, () => refreshUpdateBadge())

onMounted(() => {
  refreshUpdateBadge()
  _updateBadgeTimer = setInterval(refreshUpdateBadge, 60 * 1000)
  document.addEventListener('visibilitychange', _refreshOnFocus)
})
onBeforeUnmount(() => {
  if (_updateBadgeTimer) clearInterval(_updateBadgeTimer)
  document.removeEventListener('visibilitychange', _refreshOnFocus)
})

const routeNameMap = {
  'Dashboard': 'dashboard', 'Clients': 'clients', 'Servers': 'servers',
  'Subscriptions': 'subscriptions', 'Payments': 'payments', 'Bots': 'bots',
  'TrafficRules': 'traffic', 'Settings': 'settings', 'Logs': 'logs',
  'AppLogs': 'appLogs', 'PortalUsers': 'portalUsers', 'PromoCodes': 'promoCodes',
  'SupportMessages': 'supportMessages', 'Applications': 'applications',
  'SystemHealth': 'systemHealth', 'ServerMonitoring': 'serverMonitoring',
  'Backup': 'backup', 'Updates': 'updates',
}
const routeKey = computed(() => routeNameMap[route.name] || (route.name || 'dashboard').toString().toLowerCase())

const languages = [
  { code: 'en', flag: 'EN', name: 'English' },
  { code: 'ru', flag: 'RU', name: 'Русский' },
  { code: 'de', flag: 'DE', name: 'Deutsch' },
  { code: 'fr', flag: 'FR', name: 'Français' },
  { code: 'es', flag: 'ES', name: 'Español' },
]
const currentLang = computed(() => locale.value)
const currentLangFlag = computed(() => (languages.find(l => l.code === locale.value) || languages[0]).flag)

let _switching = false
function toggleTheme() {
  if (_switching) return
  _switching = true
  setTimeout(() => { _switching = false }, 300)
  system.setTheme(system.theme === 'dark' ? 'light' : 'dark')
}
function setLang(code) { locale.value = code; localStorage.setItem('sb_lang', code); langOpen.value = false }
function refreshData() { window.location.reload() }
</script>

<style scoped>
.topbar-update-btn {
  position: relative;
  color: #f59e0b;
}
.topbar-update-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 0 2px var(--vxy-bg, #fff);
}
</style>
