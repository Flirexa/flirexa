<template>
  <div class="fx-shell">
    <!-- Header -->
    <header class="fx-header">
      <div class="fx-header-inner">
        <button
          class="fx-burger"
          :class="{ open: menuOpen }"
          aria-label="Toggle navigation"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <span class="fx-burger-bars"><span></span><span></span><span></span></span>
        </button>

        <router-link to="/" class="fx-brand">
          <img :src="brandLogo" alt="" class="fx-brand-logo" />
          <span class="fx-brand-text">{{ brandName }}</span>
          <span class="fx-badge fx-badge-neutral fx-brand-tag">VPN</span>
        </router-link>

        <nav class="fx-nav" :class="{ open: menuOpen }">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="fx-nav-item"
            :class="{ active: $route.path === item.path }"
            @click="menuOpen = false"
          >
            <FxIcon :name="item.icon" :size="15" />
            <span>{{ $t(item.labelKey) }}</span>
          </router-link>
        </nav>

        <div class="fx-nav-scrim" :class="{ open: menuOpen }" @click="menuOpen = false" aria-hidden="true" />

        <div class="fx-header-right">
          <button class="fx-icon-btn" @click="toggleTheme" :title="themeTitle">
            <FxIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
          </button>
          <button class="fx-icon-btn" :title="$t('nav.notifications')" @click="toggleNotifs" style="position:relative">
            <FxIcon name="bell" :size="16" />
            <span v-if="unreadCount > 0" class="fx-bell-dot" />
          </button>
          <div class="fx-lang-wrap">
            <button class="fx-lang-pill" @click="langOpen = !langOpen">
              <FxIcon name="globe" :size="12" /> {{ currentLangFlag }}
            </button>
            <div v-if="langOpen" class="fx-lang-menu" @mouseleave="langOpen = false">
              <button
                v-for="l in languages"
                :key="l.code"
                class="fx-lang-item"
                :class="{ active: currentLang === l.code }"
                @click="setLang(l.code)"
              >
                <span class="flag">{{ l.flag }}</span>
                <span>{{ l.name }}</span>
              </button>
            </div>
          </div>
          <div class="fx-avatar" :title="userName">{{ userInitials }}</div>
          <button class="fx-icon-btn" :title="$t('nav.logout')" @click="logout">
            <FxIcon name="logout" :size="16" />
          </button>
        </div>
      </div>

      <!-- Notifications dropdown -->
      <div v-if="notifsOpen && notifications.length" class="fx-notif-panel" @mouseleave="notifsOpen = false">
        <div class="fx-notif-head">
          <strong>{{ $t('nav.notifications') }}</strong>
          <span class="fx-text-3">{{ notifications.length }}</span>
        </div>
        <div class="fx-notif-list">
          <div v-for="n in notifications" :key="n.id" class="fx-notif-item" @click="dismissNotification(n.id)">
            <strong>{{ n.title }}</strong>
            <div class="fx-text-3" style="font-size:11px;margin-top:2px">{{ n.message }}</div>
          </div>
        </div>
      </div>
    </header>

    <main class="fx-main">
      <slot />
    </main>

    <!-- Footer with auth-gated GitHub promo -->
    <footer class="fx-footer">
      <div class="fx-footer-inner">
        <div class="fx-footer-meta">
          <span>© {{ year }} {{ brandName }}</span>
          <span style="color:var(--text-4)">·</span>
          <a href="#" @click.prevent>{{ $t('footer.privacy') }}</a>
          <a href="#" @click.prevent>{{ $t('footer.terms') }}</a>
          <a href="#" @click.prevent>{{ $t('footer.status') }}</a>
        </div>
        <a v-if="showGithub" class="fx-gh-promo" href="https://github.com/Flirexa/flirexa" target="_blank" rel="noreferrer">
          <span class="fx-gh-promo-icon"><FxIcon name="github" :size="16" /></span>
          <span class="fx-gh-promo-text">
            <b>{{ $t('footer.openSource') }}</b>
            <span>{{ $t('footer.openSourceHint') }}</span>
          </span>
          <FxIcon name="external" :size="14" style="color:var(--text-3); margin-left:4px" />
        </a>
      </div>
    </footer>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api/index.js'
import FxIcon from './FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'

const router = useRouter()
const route = useRoute()
const { locale, t } = useI18n()

const langOpen = ref(false)
const notifsOpen = ref(false)
const menuOpen = ref(false)
const notifications = ref([])
const featureFlags = ref({ corp_networks: true })

// Close the drawer when navigating or when the viewport widens past mobile.
watch(() => route.path, () => { menuOpen.value = false })
function onResize() { if (window.innerWidth > 860) menuOpen.value = false }

const brandName = computed(() => window.__branding?.branding_app_name || 'Flirexa')
const brandLogo = computed(() => {
  const url = window.__branding?.branding_logo_url
  if (!url) return bundledLogo
  if (url.startsWith('/')) {
    const adminPort = '10086'
    return `${window.location.protocol}//${window.location.hostname}:${adminPort}${url}`
  }
  return url
})

const year = new Date().getFullYear()

// Theme — body class maintained in App.vue via fx:theme event.
const theme = ref(localStorage.getItem('sb_theme') === 'dark' ? 'dark' : 'light')
const themeTitle = computed(() => theme.value === 'dark' ? t('nav.lightMode') : t('nav.darkMode'))
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('sb_theme', theme.value)
  window.dispatchEvent(new CustomEvent('fx:theme', { detail: theme.value }))
}

const navItems = computed(() => {
  const items = [
    { path: '/',          icon: 'dashboard', labelKey: 'nav.dashboard' },
    { path: '/plans',     icon: 'tag',       labelKey: 'nav.plans' },
    { path: '/payments',  icon: 'card',      labelKey: 'nav.payments' },
  ]
  if (featureFlags.value.corp_networks) {
    items.push({ path: '/corporate', icon: 'building', labelKey: 'nav.corporate' })
  }
  items.push({ path: '/support', icon: 'help', labelKey: 'nav.support' })
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
const userInitials = computed(() => {
  const n = userName.value
  if (!n) return 'FX'
  const parts = n.split(/[\s@.]/).filter(Boolean)
  if (!parts.length) return 'FX'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
})

function logout() {
  localStorage.removeItem('client_access_token')
  localStorage.removeItem('client_user')
  router.push('/login')
}

// GitHub promo: default ON. Admin can hide it via branding flag
// (window.__branding.show_github_footer === false).
const showGithub = computed(() => window.__branding?.show_github_footer !== false)

const unreadCount = computed(() => notifications.value.length)

function toggleNotifs() {
  notifsOpen.value = !notifsOpen.value
}

async function dismissNotification(id) {
  try {
    await portalApi.markNotificationRead(id)
    notifications.value = notifications.value.filter(n => n.id !== id)
  } catch { /* ignore */ }
}

async function loadFeatures() {
  if (!localStorage.getItem('client_access_token')) return
  try {
    const { data } = await portalApi.getFeatures()
    featureFlags.value = { corp_networks: !!data?.features?.corp_networks }
  } catch { /* keep defaults */ }
}

async function loadNotifications() {
  if (!localStorage.getItem('client_access_token')) return
  try {
    const { data } = await portalApi.getNotifications()
    notifications.value = Array.isArray(data) ? data : []
  } catch { /* ignore */ }
}

let notifIntervalId = null
onMounted(() => {
  loadFeatures()
  loadNotifications()
  notifIntervalId = setInterval(loadNotifications, 60000)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  if (notifIntervalId) clearInterval(notifIntervalId)
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.fx-shell {
  min-height: 100vh;
  display: flex; flex-direction: column;
}
.fx-main {
  flex: 1;
}

.fx-brand-text {
  white-space: nowrap;
}
.fx-brand-tag {
  margin-left: 4px;
  font-size: 10px;
  height: 18px;
  padding: 0 7px;
}

.fx-bell-dot {
  position: absolute;
  top: 8px; right: 8px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--danger);
  box-shadow: 0 0 0 2px var(--bg-elev);
}

/* Language dropdown */
.fx-lang-wrap { position: relative; }
.fx-lang-menu {
  position: absolute; right: 0; top: calc(100% + 6px);
  z-index: 100; min-width: 160px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  padding: 4px;
}
.fx-lang-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 8px 10px;
  border: 0; background: transparent;
  border-radius: var(--r-sm);
  font-size: 13px; color: var(--text);
  cursor: pointer; font-family: inherit;
  text-align: left;
}
.fx-lang-item:hover { background: var(--bg-hover); }
.fx-lang-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.fx-lang-item .flag {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 16px;
  background: var(--bg-subtle);
  border-radius: 3px;
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  color: var(--text-2);
}

/* Notifications panel */
.fx-notif-panel {
  position: absolute; right: 24px; top: 60px;
  z-index: 60; width: min(360px, calc(100vw - 32px));
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.fx-notif-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.fx-notif-head strong { color: var(--text); }
.fx-notif-head .fx-text-3 { color: var(--text-3); font-size: 12px; }
.fx-notif-list { max-height: 320px; overflow-y: auto; }
.fx-notif-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}
.fx-notif-item:last-child { border-bottom: 0; }
.fx-notif-item:hover { background: var(--bg-hover); }
.fx-notif-item strong { font-size: 13px; color: var(--text); }
.fx-notif-item .fx-text-3 { color: var(--text-3); }

@media (max-width: 860px) {
  /* Notif panel sits below the 56px-tall mobile header. */
  .fx-notif-panel { top: 56px; right: 12px; }
}
@media (max-width: 480px) {
  .fx-brand-text { max-width: 140px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
}
</style>
