<!-- App shell — reproduced 1:1 from the designer's markup (sidebar brand +
     nav groups + user footer; topbar title/subtitle + search + live + theme +
     donate + account + contextual primary action). Nav/theme/logout/branding
     reuse the existing stores. Content swaps to a registered D2 screen for the
     current route, else the Legacy view (fallback). -->
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
      <header style="position:sticky;top:0;z-index:40;background:var(--bg);border-bottom:1px solid var(--border);padding:13px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;row-gap:9px">
        <button @click="system.toggleSidebar && system.toggleSidebar()" class="d2-menu-btn d2-only-mobile"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"></path></svg></button>
        <div style="min-width:0">
          <div style="display:flex;align-items:center;font-weight:650;font-size:18px;letter-spacing:-.015em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ ui.title || pageTitle }}</div>
          <div v-if="ui.subtitle" style="font-size:12.5px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ ui.subtitle }}</div>
        </div>

        <div style="margin-left:auto;display:flex;align-items:center;gap:9px;flex-wrap:wrap;justify-content:flex-end">
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
          <button v-if="ui.primary" @click="ui.primary.onClick" class="d2-primary"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg><span>{{ ui.primary.label }}</span></button>
        </div>
      </header>

      <div style="flex:1;min-width:0;padding:22px">
        <router-view v-slot="{ Component, route: r }">
          <component :is="screenFor(r) || Component" />
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
import { useD2Ui } from '../../stores/d2ui'
import { NAV_SECTIONS } from '../nav.js'
import { D2_SCREENS } from '../screens/registry.js'
import Icon from '../ui/Icon.vue'
import DonateModal from './D2DonateModal.vue'
import api, { systemApi } from '../../api'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()
const branding = useBrandingStore()
const ui = useD2Ui()
const sections = NAV_SECTIONS
const acctOpen = ref(false)
const donateOpen = ref(false)
const langOpen = ref(false)
// Paid operators never see donation promotion; FREE/trial retains it.
const showDonate = ref(true)
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
function screenFor(r) { return (r && r.name && D2_SCREENS[r.name]) || null }
function toggleTheme() { system.setTheme(system.theme === 'dark' ? 'light' : 'dark') }
function donate() { donateOpen.value = true }
const curLangCode = computed(() => i18n.locale.value || 'en')
const curLang = computed(() => curLangCode.value.toUpperCase())
function setLang(code) { i18n.locale.value = code; try { localStorage.setItem('sb_lang', code) } catch (_) {}; langOpen.value = false }
function logout() { try { localStorage.removeItem('sb_token'); localStorage.removeItem('sb_refresh_token') } catch (_) {}; router.push('/login') }
function onDoc() { acctOpen.value = false; langOpen.value = false }
function isLicensed(l) {
  l = l || {}
  const tier = String(l.tier || l.license_tier || '').toLowerCase()
  return !!(l.valid || l.is_valid || l.lifetime || l.lifetime_protected ||
    String(l.status || '').toLowerCase() === 'active' ||
    (tier && !['', 'none', 'free', 'trial', 'unlicensed'].includes(tier)))
}
async function refreshDonateVisibility() {
  try {
    const l = await systemApi.getLicense().then(r => r.data).catch(() => ({}))
    // A paid license already supports the project, so paid operators never see
    // the donation button or modal. Free/trial installs keep the support entry.
    showDonate.value = !isLicensed(l)
  } catch (_) { /* keep visible on error */ }
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
    const r = await api.get('/updates/status', { timeout: 4000 })
    const av = r.data?.available_update
    updateBadge.value = av
      ? { available: true, title: (tr('updates.newVersionAvailable') || 'New version available') + ': ' + av.version }
      : { available: false, title: '' }
  } catch (_) { /* silent — never block the shell on an update-check failure */ }
}
function _updOnFocus() { if (!document.hidden) refreshUpdateBadge() }
watch(() => route.fullPath, () => refreshUpdateBadge())

onMounted(() => {
  document.addEventListener('click', onDoc)
  document.addEventListener('visibilitychange', _updOnFocus)
  refreshDonateVisibility()
  refreshUpdateBadge()
  _updTimer = setInterval(refreshUpdateBadge, 60 * 1000)
})
onUnmounted(() => {
  document.removeEventListener('click', onDoc)
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
.d2-search-in { width: 100%; height: 38px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 12px 0 34px; font: inherit; font-size: 13px; outline: none; }
.d2-search-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-acctmenu { position: absolute; right: 0; top: 44px; z-index: 56; min-width: 170px; background: var(--panel); border: 1px solid var(--border); border-radius: 11px; box-shadow: var(--shadow-lg); padding: 5px; }
.d2-acctitem { display: flex; align-items: center; gap: 9px; width: 100%; padding: 9px 11px; border: none; border-radius: 8px; background: none; color: var(--text); font: inherit; font-size: 13px; cursor: pointer; text-align: left; }
.d2-acctitem:hover { background: var(--panel-2); }
.d2-menu-btn { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; flex: none; }
.d2-only-mobile, .d2-only-mobile-block { display: none; }
@media (max-width: 900px) {
  .d2-aside { position: fixed; z-index: 66; transform: translateX(-100%); transition: transform .2s ease; box-shadow: var(--shadow-lg); }
  .d2-aside.open { transform: translateX(0); }
  .d2-only-mobile { display: flex; } .d2-only-mobile-block { display: block; }
}
</style>
