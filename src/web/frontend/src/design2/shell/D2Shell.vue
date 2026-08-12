<!-- App shell — reproduced 1:1 from the designer's markup (sidebar brand +
     nav groups + user footer; topbar title/subtitle + search + live + theme +
     donate + account + contextual primary action). Nav/theme/logout/branding
     reuse the existing stores. Router routes point directly to D2 screens. -->
<template>
  <div style="display:flex;height:100vh;overflow:hidden;background:var(--bg)">
    <!-- mobile backdrop -->
    <div v-if="system.sidebarOpen" @click="system.closeSidebar()" style="position:fixed;inset:0;background:rgba(10,11,14,.45);z-index:65" class="d2-only-mobile-block"></div>

    <!-- SIDEBAR -->
    <aside class="d2-aside" :class="{ open: system.sidebarOpen }">
      <div style="display:flex;align-items:center;gap:11px;padding:18px 16px 16px">
        <div style="width:32px;height:32px;border-radius:9px;background:var(--accent);display:flex;align-items:center;justify-content:center;flex:none;overflow:hidden;box-shadow:0 2px 8px var(--accent-ring)">
          <img v-if="branding.logoUrl" :src="branding.logoUrl" alt="" style="width:100%;height:100%;object-fit:cover" />
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.2-2.9 7.6-7 8.6C7.9 18.6 5 15.2 5 11V6z"></path></svg>
        </div>
        <div style="line-height:1.15;flex:1;min-width:0">
          <div style="font-weight:680;font-size:14.5px;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ branding.appName || 'VPN Panel' }}</div>
          <div style="font-size:11px;color:var(--text-3)">{{ branding.companyName || 'Admin' }}</div>
        </div>
      </div>

      <nav style="flex:1;overflow-y:auto;overflow-x:hidden;padding:6px 12px 12px">
        <div v-for="grp in sections" :key="grp.label" style="margin-top:14px">
          <div style="font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);padding:0 10px 6px">{{ tr('navgrp.' + grp.key) || grp.label }}</div>
          <div style="display:flex;flex-direction:column;gap:1px">
            <router-link v-for="it in grp.items" :key="it.path" :to="it.path" @click="system.closeSidebar()"
              class="d2-navi" :class="{ active: isActive(it) }" :title="tr('nav.' + it.key) || it.label">
              <span style="display:flex;flex:none"><Icon :name="it.icon" :size="18" /></span>
              <span style="flex:1">{{ tr('nav.' + it.key) || it.label }}</span>
            </router-link>
          </div>
        </div>
      </nav>

      <div style="border-top:1px solid var(--border);padding:12px">
        <div style="display:flex;align-items:center;gap:10px;padding:6px 8px">
          <div style="width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:650;flex:none">{{ initials }}</div>
          <div style="flex:1;line-height:1.2;min-width:0">
            <div style="font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ userName }}</div>
            <div style="font-size:11px;color:var(--text-3)">{{ tr('applications.roleAdmin') || 'Administrator' }}</div>
          </div>
          <button @click="logout" :title="tr('navbar.logout') || 'Logout'" class="d2-footbtn"><Icon name="logout" :size="16" v-if="hasIcon('logout')" /><svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"></path><path d="M16 17l5-5-5-5M21 12H9"></path></svg></button>
        </div>
      </div>
    </aside>

    <!-- MAIN -->
    <main style="flex:1;min-width:0;display:flex;flex-direction:column;height:100vh;overflow-y:auto">
      <header class="d2-topbar" style="position:sticky;top:0;z-index:40;background:var(--bg);border-bottom:1px solid var(--border);padding:13px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;row-gap:9px">
        <button @click="system.toggleSidebar && system.toggleSidebar()" class="d2-menu-btn d2-only-mobile"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"></path></svg></button>
        <div class="d2-titleblock" style="min-width:0">
          <div class="d2-title" style="display:flex;align-items:center;font-weight:650;font-size:18px;letter-spacing:-.015em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ ui.title || pageTitle }}</div>
          <div v-if="ui.subtitle" class="d2-subtitle" style="font-size:12.5px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ ui.subtitle }}</div>
        </div>

        <div class="d2-top-actions d2-desktop-actions" style="margin-left:auto;display:flex;align-items:center;gap:9px;flex-wrap:wrap;justify-content:flex-end">
          <div v-if="ui.onSearch" style="position:relative;width:200px" class="d2-searchwrap">
            <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--text-3);display:flex"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4-4"></path></svg></span>
            <input :value="ui.search" @input="ui.search = $event.target.value; ui.onSearch($event.target.value)" :placeholder="ui.searchPh || (tr('common.search') || 'Search…')" class="d2-search-in" />
          </div>
          <button v-if="ui.live" @click="ui.live.toggle()" class="d2-topbtn2" :title="tr('common.live') || 'Live'"><span style="width:7px;height:7px;border-radius:50%;flex:none" :style="{ background: ui.live.on ? 'var(--green)' : 'var(--text-3)' }"></span><span>{{ tr('common.live') || 'Live' }}</span></button>
          <div style="position:relative" @click.stop="langOpen = !langOpen">
            <button class="d2-topbtn2" :title="tr('common.language') || 'Language'"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18"></path><path d="M12 3a15 15 0 010 18M12 3a15 15 0 000 18"></path></svg><span style="font-weight:600">{{ curLang }}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg></button>
            <div v-if="langOpen" @click.stop class="d2-acctmenu">
              <button v-for="l in LOCALES" :key="l.code" class="d2-acctitem" :style="{ color: l.code === curLangCode ? 'var(--accent)' : 'var(--text-2)', fontWeight: l.code === curLangCode ? 600 : 500 }" @click="setLang(l.code)">{{ l.label }}</button>
            </div>
          </div>
          <router-link v-if="updateBadge.available" to="/updates" class="d2-topbtn d2-upd-btn" :title="updateBadge.title" style="text-decoration:none;position:relative">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"></path><path d="M7 9l5-5 5 5"></path><path d="M4 20h16"></path></svg>
            <span class="d2-upd-dot"></span>
          </router-link>
          <a v-if="showProjectAttribution" href="https://github.com/Flirexa/flirexa" target="_blank" rel="noopener noreferrer" class="d2-topbtn" title="GitHub" style="text-decoration:none;color:var(--text-2)"><svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.73.5.7 5.53.7 11.8c0 5.02 3.26 9.28 7.78 10.78.57.1.78-.25.78-.55v-2.1c-3.17.69-3.84-1.35-3.84-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.25 3.33.96.1-.74.4-1.25.72-1.54-2.53-.29-5.2-1.27-5.2-5.63 0-1.24.44-2.26 1.17-3.06-.12-.29-.51-1.45.11-3.02 0 0 .96-.31 3.15 1.17a10.9 10.9 0 015.74 0c2.18-1.48 3.14-1.17 3.14-1.17.62 1.57.23 2.73.11 3.02.73.8 1.17 1.82 1.17 3.06 0 4.37-2.67 5.34-5.22 5.62.41.36.78 1.05.78 2.12v3.14c0 .3.21.66.79.55A11.3 11.3 0 0023.3 11.8C23.3 5.53 18.27.5 12 .5z"/></svg></a>
          <button @click="toggleTheme" class="d2-topbtn" :title="system.darkMode ? 'Light' : 'Dark'"><Icon :name="system.darkMode ? 'sun' : 'moon'" :size="17" v-if="hasIcon(system.darkMode ? 'sun' : 'moon')" /><span v-else>{{ system.darkMode ? '☀' : '🌙' }}</span></button>
          <button v-if="showDonate" @click="donate" class="d2-donate" :title="tr('donate.tooltip') || 'Support the author'"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A3.5 3.5 0 0 0 12 5.5 3.5 3.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7z"></path></svg></button>
          <div style="position:relative" @click.stop="acctOpen = !acctOpen">
            <button class="d2-topbtn"><Icon name="user" :size="18" /></button>
            <div v-if="acctOpen" @click.stop class="d2-acctmenu">
              <button class="d2-acctitem" @click="logout"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"></path><path d="M16 17l5-5-5-5M21 12H9"></path></svg>{{ tr('navbar.logout') || 'Logout' }}</button>
            </div>
          </div>
          <button v-if="ui.primary" :disabled="ui.primary.disabled" @click="!ui.primary.disabled && ui.primary.onClick()" class="d2-primary" :class="{ busy:ui.primary.loading }"><span v-if="ui.primary.loading" class="d2-primary-spinner"></span><svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg><span>{{ ui.primary.label }}</span></button>
        </div>

        <div class="d2-mobile-actions">
          <button v-if="ui.onSearch" type="button" class="d2-mobile-headbtn" :class="{ active:mobileSearchOpen }" :title="tr('common.search') || 'Search'" @click="mobileSearchOpen = !mobileSearchOpen">
            <Icon name="search" :size="17" />
          </button>
          <router-link v-if="updateBadge.available" to="/updates" class="d2-mobile-headbtn d2-mobile-update" :title="updateBadge.title">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"></path><path d="M7 9l5-5 5 5"></path><path d="M4 20h16"></path></svg><span></span>
          </router-link>
          <button v-if="ui.primary" type="button" class="d2-mobile-primary" :class="{ busy:ui.primary.loading }" :disabled="ui.primary.disabled" :title="ui.primary.label" @click="!ui.primary.disabled && ui.primary.onClick()">
            <span v-if="ui.primary.loading" class="d2-primary-spinner"></span>
            <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg>
            <span>{{ ui.primary.label }}</span>
          </button>
          <div class="d2-mobile-language-wrap" @click.stop>
            <button type="button" class="d2-mobile-headbtn d2-mobile-language-btn" :class="{ active:mobileLangOpen }" :aria-expanded="mobileLangOpen" :title="tr('common.language') || 'Language'" @click="mobileLangOpen = !mobileLangOpen; mobileMenuOpen = false">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18"/></svg>
              <span>{{ curLang }}</span>
            </button>
            <div v-if="mobileLangOpen" class="d2-mobile-language-popover">
              <button v-for="l in LOCALES" :key="l.code" type="button" :class="{ active:l.code === curLangCode }" @click="setLang(l.code)"><span>{{ l.code.toUpperCase() }}</span>{{ l.label }}</button>
            </div>
          </div>
          <a v-if="showProjectAttribution" href="https://github.com/Flirexa/flirexa" target="_blank" rel="noopener noreferrer" class="d2-mobile-headbtn d2-mobile-github" title="GitHub">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.73.5.7 5.53.7 11.8c0 5.02 3.26 9.28 7.78 10.78.57.1.78-.25.78-.55v-2.1c-3.17.69-3.84-1.35-3.84-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.25 3.33.96.1-.74.4-1.25.72-1.54-2.53-.29-5.2-1.27-5.2-5.63 0-1.24.44-2.26 1.17-3.06-.12-.29-.51-1.45.11-3.02 0 0 .96-.31 3.15 1.17a10.9 10.9 0 015.74 0c2.18-1.48 3.14-1.17 3.14-1.17.62 1.57.23 2.73.11 3.02.73.8 1.17 1.82 1.17 3.06 0 4.37-2.67 5.34-5.22 5.62.41.36.78 1.05.78 2.12v3.14c0 .3.21.66.79.55A11.3 11.3 0 0023.3 11.8C23.3 5.53 18.27.5 12 .5z"/></svg>
          </a>
          <button type="button" class="d2-mobile-headbtn d2-mobile-theme" :title="system.darkMode ? (tr('themes.light') || 'Light theme') : (tr('themes.dark') || 'Dark theme')" @click="toggleTheme(); mobileMenuOpen = false; mobileLangOpen = false">
            <Icon :name="system.darkMode ? 'sun' : 'moon'" :size="16" />
          </button>
          <div class="d2-mobile-menu-wrap" @click.stop>
            <button type="button" class="d2-mobile-headbtn" :class="{ active:mobileMenuOpen }" :aria-expanded="mobileMenuOpen" :title="tr('common.actions') || 'Actions'" @click="mobileMenuOpen = !mobileMenuOpen; mobileLangOpen = false">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>
            </button>
            <div v-if="mobileMenuOpen" class="d2-mobile-menu">
              <div class="d2-mobile-menu-user">
                <span>{{ initials }}</span>
                <div><b>{{ userName }}</b><small>{{ tr('applications.roleAdmin') || 'Administrator' }}</small></div>
              </div>
              <button v-if="showDonate" type="button" class="d2-mobile-menu-item" @click="donate(); mobileMenuOpen = false">
                <Icon name="heart" :size="17" /><span>{{ tr('donate.tooltip') || 'Support the author' }}</span>
              </button>
              <button type="button" class="d2-mobile-menu-item danger" @click="logout">
                <Icon name="logout" :size="17" /><span>{{ tr('navbar.logout') || 'Logout' }}</span>
              </button>
            </div>
          </div>
        </div>

        <div v-if="ui.onSearch && mobileSearchOpen" class="d2-mobile-search">
          <Icon name="search" :size="16" />
          <input :value="ui.search" autofocus @input="ui.search = $event.target.value; ui.onSearch($event.target.value)" :placeholder="ui.searchPh || (tr('common.search') || 'Search…')" />
          <button type="button" :aria-label="tr('common.close') || 'Close'" @click="mobileSearchOpen = false"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
        </div>
      </header>

      <div class="d2-content" style="flex:1;min-width:0;padding:22px">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </div>
    </main>

    <DonateModal v-model="donateOpen" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSystemStore } from '../../stores/system'
import { useBrandingStore } from '../../stores/branding'
import { useLicenseStore } from '../../stores/license'
import { useD2Ui } from '../../stores/d2ui'
import { NAV_SECTIONS } from '../nav.js'
import Icon from '../ui/Icon.vue'
import DonateModal from './D2DonateModal.vue'
import api from '../../api'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()
const branding = useBrandingStore()
const license = useLicenseStore()
const ui = useD2Ui()
const sections = NAV_SECTIONS
const acctOpen = ref(false)
const donateOpen = ref(false)
const langOpen = ref(false)
const mobileMenuOpen = ref(false)
const mobileLangOpen = ref(false)
const mobileSearchOpen = ref(false)
// Fail closed while licence state is loading. FREE/trial keep the optional
// support button; every purchased tier hides it without a paid-user flash.
const showDonate = computed(() => license.loaded && !license.isPaid)
// i18n has en/ru/de/fr/es (see i18n/index.js); persist choice in sb_lang like Legacy.
const LOCALES = [
  { code: 'en', label: 'English' }, { code: 'ru', label: 'Русский' },
  { code: 'de', label: 'Deutsch' }, { code: 'fr', label: 'Français' }, { code: 'es', label: 'Español' },
]

const i18n = useI18n()
function tr(k) { try { const v = i18n.t(k); return v === k ? '' : v } catch (_) { return '' } }
const ICONSET = new Set(['grid', 'activity', 'users', 'layers', 'server', 'pulse', 'heart', 'card', 'receipt', 'trendup', 'wallet', 'crown', 'user', 'tag', 'chat', 'bell', 'bot', 'gauge', 'lock', 'box', 'database', 'download', 'gear', 'list', 'terminal', 'sun', 'moon', 'logout', 'search', 'plus'])
function hasIcon(n) { return ICONSET.has(n) }

function isActive(it) { return it.path === '/' ? route.path === '/' : route.path.startsWith(it.path) }
const pageTitle = computed(() => {
  const all = NAV_SECTIONS.flatMap(s => s.items)
  const hit = all.find(it => isActive(it))
  return hit ? (tr('nav.' + hit.key) || hit.label) : ''
})
const userName = computed(() => branding.appName ? (localStorage.getItem('sb_username') || 'Admin') : (localStorage.getItem('sb_username') || 'Admin'))
const initials = computed(() => (userName.value || 'A').trim().slice(0, 2).toUpperCase())
const showProjectAttribution = computed(() => branding.poweredBy !== false)
function toggleTheme() { system.setTheme(system.theme === 'dark' ? 'light' : 'dark') }
function donate() { donateOpen.value = true }
const curLangCode = computed(() => i18n.locale.value || 'en')
const curLang = computed(() => curLangCode.value.toUpperCase())
function setLang(code) { i18n.locale.value = code; try { localStorage.setItem('sb_lang', code) } catch (_) {}; langOpen.value = false; mobileLangOpen.value = false; mobileMenuOpen.value = false }
function logout() { mobileMenuOpen.value = false; mobileLangOpen.value = false; try { localStorage.removeItem('sb_token'); localStorage.removeItem('sb_refresh_token') } catch (_) {}; router.push('/login') }
function onDoc() { acctOpen.value = false; langOpen.value = false; mobileLangOpen.value = false; mobileMenuOpen.value = false }
function onMobileTableClick(e) {
  if (window.innerWidth > 900) return
  const head = e.target?.closest?.('td[data-mhead]')
  if (!head) return
  const table = head.closest('table[data-rcollapse]')
  if (!table) return
  if (e.target.closest('button,a,input,select,textarea,label')) return
  const row = head.closest('tr')
  if (!row) return
  row.toggleAttribute('data-mx')
}
// ── Update-available topbar badge ──────────────────────────────────────────────
// Polls /updates/status every 60s + on tab focus + on route change, so a newer
// version on the channel surfaces a pulsing indicator without the operator
// opening the Updates page. Clicking navigates there. Ported from the legacy
// Navbar's update badge, restyled for the new shell.
const updateBadge = ref({ available: false, title: '' })
let _updTimer = null
async function refreshUpdateBadge() {
  try {
    // Background-only: /updates/status serves the last verified manifest and
    // refreshes it asynchronously. A slow route must never interrupt unrelated
    // operator work with the global request-timeout toast.
    const r = await api.get('/updates/status', { timeout: 10000, silent: true })
    const av = r.data?.available_update
    updateBadge.value = av
      ? { available: true, title: (tr('updates.newVersionAvailable') || 'New version available') + ': ' + av.version }
      : { available: false, title: '' }
  } catch (_) { /* silent — never block the shell on an update-check failure */ }
}
function _updOnFocus() { if (!document.hidden) refreshUpdateBadge() }
watch(() => route.fullPath, () => { mobileMenuOpen.value = false; mobileLangOpen.value = false; mobileSearchOpen.value = false; refreshUpdateBadge() })

onMounted(() => {
  document.addEventListener('click', onDoc)
  document.addEventListener('click', onMobileTableClick, true)
  document.addEventListener('visibilitychange', _updOnFocus)
  if (!license.loaded) license.load()
  refreshUpdateBadge()
  _updTimer = setInterval(refreshUpdateBadge, 60 * 1000)
})
watch(showDonate, (allowed) => {
  if (!allowed) donateOpen.value = false
})
onUnmounted(() => {
  document.removeEventListener('click', onDoc)
  document.removeEventListener('click', onMobileTableClick, true)
  document.removeEventListener('visibilitychange', _updOnFocus)
  if (_updTimer) clearInterval(_updTimer)
})
</script>

<style scoped>
.d2-aside { width: 248px; flex: none; background: var(--panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh; overflow: hidden; }
.d2-navi { display: flex; align-items: center; gap: 11px; width: 100%; padding: 8px 10px; border: none; border-radius: 8px; background: transparent; color: var(--text-2); font: inherit; font-size: 13.5px; font-weight: 500; cursor: pointer; text-align: left; }
.d2-navi:hover { background: var(--panel-2); text-decoration: none; color: var(--text-2); }
.d2-navi.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.d2-footbtn { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-3); cursor: pointer; display: flex; align-items: center; justify-content: center; flex: none; }
.d2-footbtn:hover { background: var(--panel-2); color: var(--red); }
.d2-topbtn { width: 38px; height: 38px; border-radius: 9px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; flex: none; }
.d2-topbtn:hover { background: var(--panel-2); color: var(--text); }
.d2-upd-btn { color: var(--amber); border-color: var(--amber-soft); }
.d2-upd-btn:hover { color: var(--amber); background: var(--amber-soft); }
.d2-upd-dot { position: absolute; top: 6px; right: 6px; width: 8px; height: 8px; border-radius: 50%; background: var(--red); box-shadow: 0 0 0 2px var(--panel); animation: d2pulse 1.8s ease-in-out infinite; }
.d2-topbtn2 { display: flex; align-items: center; gap: 7px; height: 38px; padding: 0 12px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 10px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.d2-topbtn2:hover { background: var(--panel-2); }
.d2-donate { display: flex; align-items: center; height: 38px; padding: 0 11px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--accent); border-radius: 10px; cursor: pointer; flex: none; }
.d2-donate:hover { background: var(--accent-soft); border-color: var(--accent); }
.d2-primary { display: flex; align-items: center; gap: 7px; height: 38px; padding: 0 14px; border: none; background: var(--accent); color: #fff; border-radius: 10px; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; flex: none; box-shadow: 0 1px 3px var(--accent-ring); }
.d2-primary:hover { background: var(--accent-2); }
.d2-primary:disabled,.d2-mobile-primary:disabled { cursor:default;opacity:.75; }
.d2-primary-spinner { width:15px;height:15px;display:block !important;flex:none;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:d2-primary-spin .7s linear infinite; }
@keyframes d2-primary-spin { to { transform:rotate(360deg); } }
.d2-search-in { width: 100%; height: 38px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 12px 0 34px; font: inherit; font-size: 13px; outline: none; }
.d2-search-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-acctmenu { position: absolute; right: 0; top: 44px; z-index: 56; min-width: 170px; background: var(--panel); border: 1px solid var(--border); border-radius: 11px; box-shadow: var(--shadow-lg); padding: 5px; }
.d2-acctitem { display: flex; align-items: center; gap: 9px; width: 100%; padding: 9px 11px; border: none; border-radius: 8px; background: none; color: var(--text); font: inherit; font-size: 13px; cursor: pointer; text-align: left; }
.d2-acctitem:hover { background: var(--panel-2); }
.d2-menu-btn { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; flex: none; }
.d2-only-mobile, .d2-only-mobile-block, .d2-mobile-actions, .d2-mobile-search { display: none; }
@media (max-width: 900px) {
  .d2-aside { position: fixed; z-index: 66; transform: translateX(-100%); transition: transform .2s ease; box-shadow: var(--shadow-lg); }
  .d2-aside.open { transform: translateX(0); }
  .d2-only-mobile { display: flex; } .d2-only-mobile-block { display: block; }
  .d2-topbar { display:grid !important;grid-template-columns:34px minmax(0,1fr) auto;padding:8px 10px !important;align-items:center !important;gap:8px !important;flex-wrap:nowrap !important;row-gap:8px !important;min-height:52px; }
  .d2-menu-btn { width:34px;height:34px;border-radius:9px; }
  .d2-titleblock { min-width:0;max-width:none; }
  .d2-title { display:block !important;font-size:17px !important;line-height:1.2 !important;white-space:nowrap !important;overflow:hidden !important;text-overflow:ellipsis !important;word-break:normal; }
  .d2-subtitle { display:none; }
  .d2-desktop-actions { display:none !important; }
  .d2-mobile-actions { display:flex;align-items:center;gap:4px;justify-self:end;min-width:0; }
  .d2-mobile-headbtn,
  .d2-mobile-primary { width:34px;height:34px;display:grid;place-items:center;flex:none;padding:0;border:1px solid var(--border);border-radius:9px;background:var(--panel);color:var(--text-2);font:inherit;cursor:pointer;text-decoration:none;box-shadow:none; }
  .d2-mobile-headbtn.active { color:var(--accent);border-color:var(--accent);background:var(--accent-soft); }
  .d2-mobile-primary { border-color:var(--accent);background:var(--accent);color:#fff; }
  .d2-mobile-primary > span { display:none; }
  .d2-mobile-update { position:relative;color:var(--accent); }
  .d2-mobile-update > span { position:absolute;top:5px;right:5px;width:6px;height:6px;border-radius:50%;background:var(--red);box-shadow:0 0 0 2px var(--panel); }
  .d2-mobile-language-wrap { position:relative;flex:none; }
  .d2-mobile-language-btn { position:relative; }
  .d2-mobile-language-btn > span { position:absolute;right:2px;bottom:1px;min-width:14px;height:11px;padding:0 2px;display:grid;place-items:center;border-radius:4px;background:var(--panel);color:var(--text-3);font-size:7px;font-weight:750;line-height:1; }
  .d2-mobile-language-btn.active > span { background:var(--accent-soft);color:var(--accent); }
  .d2-mobile-language-popover { position:absolute;right:0;top:40px;z-index:82;width:190px;max-width:none !important;padding:6px;border:1px solid var(--border);border-radius:12px;background:var(--panel);box-shadow:var(--shadow-lg); }
  .d2-mobile-language-popover button { width:100%;height:37px;display:grid;grid-template-columns:32px minmax(0,1fr);align-items:center;gap:7px;padding:0 8px;border:0;border-radius:8px;background:transparent;color:var(--text-2);font:inherit;font-size:12px;text-align:left;cursor:pointer; }
  .d2-mobile-language-popover button > span { color:var(--text-3);font-size:9px;font-weight:700; }
  .d2-mobile-language-popover button.active { background:var(--accent-soft);color:var(--accent);font-weight:620; }
  .d2-mobile-language-popover button.active > span { color:var(--accent); }
  .d2-mobile-menu-wrap { position:relative;flex:none; }
  .d2-mobile-menu { position:absolute;right:0;top:40px;z-index:80;width:260px;max-width:calc(100vw - 20px) !important;padding:7px;background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow-lg); }
  .d2-mobile-menu-user { display:flex;align-items:center;gap:10px;padding:8px 8px 11px;border-bottom:1px solid var(--border); }
  .d2-mobile-menu-user > span { width:32px;height:32px;display:grid;place-items:center;flex:none;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:700; }
  .d2-mobile-menu-user > div { min-width:0;display:flex;flex-direction:column; }
  .d2-mobile-menu-user b { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px;font-weight:650; }
  .d2-mobile-menu-user small { color:var(--text-3);font-size:10.5px; }
  .d2-mobile-menu-label { padding:10px 8px 5px;color:var(--text-3);font-size:9.5px;font-weight:650;text-transform:uppercase;letter-spacing:.05em; }
  .d2-mobile-languages { display:grid;grid-template-columns:repeat(5,1fr);gap:4px;padding:0 4px 7px; }
  .d2-mobile-languages button { height:30px;padding:0;border:1px solid var(--border);border-radius:7px;background:var(--panel-2);color:var(--text-3);font:inherit;font-size:10px;font-weight:650;cursor:pointer; }
  .d2-mobile-languages button.active { border-color:var(--accent);background:var(--accent-soft);color:var(--accent); }
  .d2-mobile-menu-item { width:100%;min-height:38px;display:flex;align-items:center;gap:10px;padding:0 9px;border:0;border-radius:8px;background:transparent;color:var(--text-2);font:inherit;font-size:12.5px;font-weight:550;text-align:left;text-decoration:none;cursor:pointer; }
  .d2-mobile-menu-item:active { background:var(--panel-2); }
  .d2-mobile-menu-item.danger { color:var(--red); }
  .d2-mobile-search { grid-column:1 / -1;position:relative;height:38px;display:flex;align-items:center;gap:8px;padding:0 8px 0 11px;border:1px solid var(--border-strong);border-radius:10px;background:var(--panel); }
  .d2-mobile-search > svg { flex:none;color:var(--text-3); }
  .d2-mobile-search input { flex:1;min-width:0;border:0;outline:0;background:transparent;color:var(--text);font:inherit;font-size:12.5px; }
  .d2-mobile-search button { width:28px;height:28px;display:grid;place-items:center;flex:none;border:0;border-radius:7px;background:transparent;color:var(--text-3);cursor:pointer; }
  .d2-content { padding: 14px 12px 72px !important; overflow-x: hidden; }
}
@media (max-width: 430px) {
  .d2-topbar { grid-template-columns:32px minmax(48px,1fr) auto !important;padding-left:8px !important;padding-right:8px !important;gap:6px !important; }
  .d2-menu-btn { width:32px;height:32px; }
  .d2-mobile-actions { gap:3px; }
  .d2-mobile-headbtn,.d2-mobile-primary { width:31px;height:31px;border-radius:8px; }
  .d2-mobile-language-popover,.d2-mobile-menu { top:37px; }
}
@media (max-width: 350px) {
  .d2-mobile-github { display:none; }
}
@media (min-width:600px) and (max-width:900px) {
  .d2-mobile-primary { width:auto;display:flex;gap:6px;padding:0 11px; }
  .d2-mobile-primary > span { display:inline;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px;font-weight:650; }
}
</style>
