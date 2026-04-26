<template>
  <div class="client-layout">
    <!-- Header -->
    <header class="client-header">
      <div class="client-header-inner">
        <div class="client-brand">
          <img v-if="brandLogo" :src="brandLogo" alt="" style="height: 28px;" />
          <span v-else class="brand-icon">🛡️</span>
          <span class="brand-text">{{ brandName }}</span>
        </div>
        <nav class="client-nav d-none d-md-flex">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="client-nav-link"
            :class="{ active: $route.path === item.path }"
          >
            <i :class="'mdi mdi-' + item.mdi"></i>
            <span>{{ $t(item.labelKey) }}</span>
          </router-link>
        </nav>
        <div class="client-header-actions">
          <!-- Theme toggle -->
          <button class="header-icon-btn theme-toggle-btn" @click="cycleTheme" :title="themeLabel">
            <i :class="currentTheme === 'dark' ? 'mdi mdi-weather-sunny' : 'mdi mdi-weather-night'"></i>
          </button>
          <!-- Language picker -->
          <div class="lang-dropdown">
            <button class="header-icon-btn" @click="langOpen = !langOpen">
              <span style="font-size:.7rem;font-weight:700">{{ currentLangFlag }}</span>
            </button>
            <div class="lang-menu" v-if="langOpen" @mouseleave="langOpen = false">
              <button
                v-for="l in languages"
                :key="l.code"
                class="lang-item"
                :class="{ active: currentLang === l.code }"
                @click="setLang(l.code)"
              >
                <span>{{ l.flag }}</span>
                <span>{{ l.name }}</span>
              </button>
            </div>
          </div>
          <span class="user-name d-none d-sm-inline">{{ userName }}</span>
          <button class="header-icon-btn" @click="logout" :title="$t('nav.logout')">
            <i class="mdi mdi-logout"></i>
          </button>
        </div>
      </div>
    </header>

    <!-- Mobile Nav -->
    <nav class="client-mobile-nav d-md-none">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="mobile-nav-item"
        :class="{ active: $route.path === item.path }"
      >
        <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi" style="font-size:1.3rem"></i></span>
        <span class="nav-label">{{ $t(item.labelKey) }}</span>
      </router-link>
    </nav>

    <!-- Content -->
    <main class="client-content">
      <div class="container-xl py-4">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api/index.js'

const router = useRouter()
const { locale } = useI18n()

const langOpen = ref(false)

// Branding from global window.__branding (set in App.vue)
const brandName = computed(() => window.__branding?.branding_app_name || 'VPN Manager')
const brandLogo = computed(() => {
  const url = window.__branding?.branding_logo_url
  if (!url) return ''
  // If logo is from admin panel, construct full URL
  if (url.startsWith('/')) {
    const adminPort = '10086'
    return `${window.location.protocol}//${window.location.hostname}:${adminPort}${url}`
  }
  return url
})

// Theme toggle: light ↔ dark
const currentTheme = ref('light')

const themeIcon = computed(() => {
  return currentTheme.value === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'
})
const themeLabel = computed(() => {
  return currentTheme.value === 'dark' ? 'Light mode' : 'Dark mode'
})

function applyTheme(theme) {
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

function initTheme() {
  let saved = localStorage.getItem('sb_theme') || 'light'
  if (saved !== 'light' && saved !== 'dark') saved = 'light'
  currentTheme.value = saved
  applyTheme(saved)
}

let _switching = false
function cycleTheme() {
  if (_switching) return
  _switching = true
  setTimeout(() => { _switching = false }, 300)
  const next = currentTheme.value === 'light' ? 'dark' : 'light'
  currentTheme.value = next
  localStorage.setItem('sb_theme', next)
  applyTheme(next)
}

// Apply theme synchronously so there's no flash on load
initTheme()

const featureFlags = ref({ corp_networks: true })

const navItems = computed(() => {
  const items = [
    { path: '/',          mdi: 'view-dashboard-outline',  labelKey: 'nav.dashboard' },
    { path: '/plans',     mdi: 'diamond-outline',         labelKey: 'nav.plans' },
    { path: '/payments',  mdi: 'credit-card-outline',     labelKey: 'nav.payments' },
    { path: '/support',   mdi: 'message-text-outline',    labelKey: 'nav.support' },
  ]
  if (featureFlags.value.corp_networks) {
    items.splice(3, 0, { path: '/corporate', mdi: 'office-building-outline', labelKey: 'nav.corporate' })
  }
  return items
})

const languages = [
  { code: 'en', flag: 'EN', name: 'English' },
  { code: 'ru', flag: 'RU', name: 'Русский' },
  { code: 'de', flag: 'DE', name: 'Deutsch' },
  { code: 'fr', flag: 'FR', name: 'Français' },
  { code: 'es', flag: 'ES', name: 'Español' },
]

const currentLang = computed(() => locale.value)
const currentLangFlag = computed(() => {
  const l = languages.find(l => l.code === locale.value)
  return l ? l.flag : 'EN'
})

function setLang(code) {
  locale.value = code
  localStorage.setItem('sb_lang', code)
  langOpen.value = false
}

const userName = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem('client_user') || '{}')
    return user.username || user.email || ''
  } catch {
    return ''
  }
})

const logout = () => {
  localStorage.removeItem('client_access_token')
  localStorage.removeItem('client_user')
  router.push('/login')
}

async function loadFeatures() {
  if (!localStorage.getItem('client_access_token')) return
  try {
    const { data } = await portalApi.getFeatures()
    featureFlags.value = {
      corp_networks: !!data?.features?.corp_networks,
    }
  } catch {
    // Keep the last/default feature state; layout must not become unusable
    // due to a transient feature check error.
  }
}

onMounted(loadFeatures)
</script>

<style scoped>
/* ── Vuexy-style Client Layout ─────────────────────────────── */
.client-layout { min-height: 100vh; background: var(--vxy-body-bg); }

/* Header */
.client-header {
  background: var(--vxy-header-bg);
  color: #fff;
  position: sticky; top: 0; z-index: 100;
  box-shadow: 0 2px 20px rgba(44,49,82,.35);
}
.client-header-inner {
  max-width: 1320px; margin: 0 auto;
  padding: 0 1.5rem; height: 64px;
  display: flex; align-items: center; justify-content: space-between;
}
.client-brand {
  display: flex; align-items: center; gap: .5rem;
  font-weight: 700; font-size: 1.1rem; color: #fff;
  text-decoration: none;
}
.brand-icon { font-size: 1.4rem; }

/* Desktop nav */
.client-nav { display: flex; gap: .25rem; }
.client-nav-link {
  color: rgba(255,255,255,.65);
  text-decoration: none;
  padding: .45rem .875rem;
  border-radius: .375rem;
  font-size: .875rem; font-weight: 500;
  display: flex; align-items: center; gap: .4rem;
  transition: all .15s;
}
.client-nav-link:hover { color: #fff; background: rgba(255,255,255,.1); }
.client-nav-link.active {
  color: #fff;
  background: linear-gradient(118deg, rgba(115,103,240,.7), rgba(115,103,240,.5));
  box-shadow: 0 0 8px rgba(115,103,240,.4);
  font-weight: 600;
}

/* Header actions */
.client-header-actions { display: flex; align-items: center; gap: .5rem; }
.user-name { font-size: .8rem; opacity: .7; }

/* Icon buttons in header */
.header-icon-btn {
  width: 36px; height: 36px; border-radius: .375rem;
  border: 1px solid rgba(255,255,255,.15);
  background: transparent; color: rgba(255,255,255,.75);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s; font-size: 1rem;
  touch-action: manipulation; user-select: none; -webkit-tap-highlight-color: transparent;
}
.header-icon-btn:hover { background: rgba(255,255,255,.12); color: #fff; }

/* Lang dropdown */
.lang-dropdown { position: relative; }
.lang-menu {
  position: absolute; top: calc(100% + 8px); right: 0;
  background: var(--vxy-card-bg);
  border: 1px solid var(--vxy-border);
  border-radius: .5rem;
  box-shadow: 0 8px 24px rgba(0,0,0,.15);
  z-index: 9999; min-width: 140px; padding: .4rem;
}
.lang-item {
  display: flex; align-items: center; gap: .5rem;
  width: 100%; padding: .45rem .75rem;
  border: none; background: none; cursor: pointer;
  font-size: .85rem; color: var(--vxy-text);
  border-radius: .375rem; transition: background .15s;
}
.lang-item:hover { background: var(--vxy-hover-bg); color: var(--vxy-primary); }
.lang-item.active { background: var(--vxy-primary-light); color: var(--vxy-primary); font-weight: 600; }

/* Mobile bottom nav */
.client-mobile-nav {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: var(--vxy-card-bg);
  border-top: 1px solid var(--vxy-border);
  display: flex; z-index: 100; padding: .2rem 0;
  box-shadow: 0 -4px 20px rgba(0,0,0,.06);
}
.mobile-nav-item {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; padding: .4rem 0;
  font-size: .625rem; color: var(--vxy-muted);
  text-decoration: none; transition: all .15s;
  min-height: 50px; justify-content: center; position: relative;
}
.mobile-nav-item::before {
  content: ''; position: absolute;
  top: 0; left: 50%; transform: translateX(-50%) scaleX(0);
  width: 32px; height: 3px; border-radius: 0 0 3px 3px;
  background: var(--vxy-primary);
  transition: transform .2s cubic-bezier(.4,0,.2,1);
}
.mobile-nav-item .nav-icon { font-size: 1.2rem; margin-bottom: .1rem; transition: transform .15s; }
.mobile-nav-item.active { color: var(--vxy-primary); font-weight: 600; }
.mobile-nav-item.active::before { transform: translateX(-50%) scaleX(1); }
.mobile-nav-item.active .nav-icon { transform: scale(1.1); }

.client-content {
  padding-bottom: 80px;
  /* iOS safe area */
  padding-bottom: calc(64px + env(safe-area-inset-bottom, 0px));
}
@media (min-width: 768px) { .client-content { padding-bottom: 2rem; } }

@media (max-width: 768px) {
  .client-header-inner { padding: 0 .75rem; height: 56px; }
  .client-brand { font-size: .95rem; }
  /* Smaller gap between header actions on mobile */
  .client-header-actions { gap: .35rem; }
  .header-icon-btn { width: 34px; height: 34px; }
}

@media (max-width: 480px) {
  /* On very small screens hide language text, keep icon style */
  .client-header-actions .user-name { display: none !important; }
  .brand-text { max-width: 120px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
}

@media (max-width: 400px) { .brand-text { display: none; } }

/* Mobile bottom nav improvements */
.client-mobile-nav {
  /* Taller touch targets */
  min-height: 54px;
  /* iOS safe area */
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.mobile-nav-item {
  /* Ensure 44px+ touch target */
  min-height: 54px;
}
@media (max-width: 360px) { .mobile-nav-item .nav-label { display: none; } }
</style>
