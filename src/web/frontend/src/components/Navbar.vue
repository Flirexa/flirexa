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

      <!-- Refresh — hidden on very small screens to save space -->
      <button class="topbar-icon-btn d-none d-sm-flex" @click="refreshData" title="Refresh">
        <i class="mdi mdi-refresh"></i>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSystemStore } from '../stores/system'

const route = useRoute()
const system = useSystemStore()
const { locale } = useI18n()

const langOpen = ref(false)

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
