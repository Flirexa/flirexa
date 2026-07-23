<!-- Admin login — ported 1:1 from the designer's LOGIN screen (.dc.html 93-142).
     Wrapped in `.d2-root` so the design2 tokens + white-label accent apply here
     too (branding.applyBrandAccent targets .d2-root). Branding drives the logo,
     title, subtitle and footer, so re-skinning the panel also re-skins login.
     All auth logic (setup detection, login, first-run setup) is unchanged. -->
<template>
  <div class="d2-root d2-login">
    <div class="d2lg-page">
      <!-- top-right: language · GitHub · theme -->
      <div class="d2lg-top">
        <div style="position:relative" @click.stop="langOpen = !langOpen">
          <button class="d2lg-ibtn" :title="tr('common.language') || 'Language'"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18"></path><path d="M12 3a15 15 0 010 18M12 3a15 15 0 000 18"></path></svg><span style="font-weight:600;font-size:12px">{{ curLang }}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"></path></svg></button>
          <div v-if="langOpen" @click.stop class="d2lg-langmenu">
            <button v-for="l in LOCALES" :key="l.code" class="d2lg-langitem" :style="{ color: l.code === curLangCode ? 'var(--accent)' : 'var(--text-2)', fontWeight: l.code === curLangCode ? 600 : 500 }" @click="setLang(l.code)">{{ l.label }}</button>
          </div>
        </div>
        <a href="https://github.com/Flirexa/flirexa" target="_blank" rel="noopener noreferrer" class="d2lg-ibtn d2lg-sq" title="GitHub"><svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.73.5.7 5.53.7 11.8c0 5.02 3.26 9.28 7.78 10.78.57.1.78-.25.78-.55v-2.1c-3.17.69-3.84-1.35-3.84-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.25 3.33.96.1-.74.4-1.25.72-1.54-2.53-.29-5.2-1.27-5.2-5.63 0-1.24.44-2.26 1.17-3.06-.12-.29-.51-1.45.11-3.02 0 0 .96-.31 3.15 1.17a10.9 10.9 0 015.74 0c2.18-1.48 3.14-1.17 3.14-1.17.62 1.57.23 2.73.11 3.02.73.8 1.17 1.82 1.17 3.06 0 4.37-2.67 5.34-5.22 5.62.41.36.78 1.05.78 2.12v3.14c0 .3.21.66.79.55A11.3 11.3 0 0023.3 11.8C23.3 5.53 18.27.5 12 .5z"/></svg></a>
        <button @click="toggleTheme" class="d2lg-ibtn d2lg-sq" :title="system.darkMode ? 'Light' : 'Dark'">
          <svg v-if="system.darkMode" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"></path></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"></path></svg>
        </button>
      </div>

      <div class="d2lg-wrap">
        <!-- brand header -->
        <div style="display:flex;flex-direction:column;align-items:center;margin-bottom:26px">
          <div class="d2lg-logo">
            <img v-if="branding.logoUrl" :src="branding.logoUrl" alt="" style="width:100%;height:100%;object-fit:contain" />
            <svg v-else width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.2-2.9 7.6-7 8.6C7.9 18.6 5 15.2 5 11V6z"></path><path d="M9.5 12l1.8 1.8L15 10"></path></svg>
          </div>
          <div style="font-weight:680;font-size:20px;letter-spacing:-.02em">{{ pageTitle }}</div>
          <div style="font-size:13px;color:var(--text-3);margin-top:3px">{{ isSetup ? (tr('login.createAdmin') || 'Create the admin account') : (tr('login.signInContinue') || 'Sign in to continue') }}</div>
        </div>

        <!-- card -->
        <div class="d2lg-card">
          <div v-if="loading" style="display:flex;justify-content:center;padding:18px 0">
            <span class="d2lg-spin d2lg-spin-lg"></span>
          </div>
          <form v-else @submit.prevent="isSetup ? handleSetup() : handleLogin()" style="display:flex;flex-direction:column;gap:16px">
            <div>
              <label class="d2lg-label">{{ tr('login.username') || 'Username' }}</label>
              <input v-model="form.username" type="text" autocomplete="username" :placeholder="'admin'" class="d2lg-in" required minlength="3" maxlength="50" @focus="onFocus" @blur="onBlur" />
            </div>
            <div>
              <label class="d2lg-label">{{ tr('login.password') || 'Password' }}</label>
              <input v-model="form.password" type="password" :autocomplete="isSetup ? 'new-password' : 'current-password'" :placeholder="isSetup ? (tr('login.min8') || 'min 8 characters') : '••••••••'" class="d2lg-in" required :minlength="isSetup ? 8 : undefined" maxlength="100" @focus="onFocus" @blur="onBlur" />
            </div>
            <div v-if="isSetup">
              <label class="d2lg-label">{{ tr('login.confirmPassword') || 'Repeat password' }}</label>
              <input v-model="form.password2" type="password" autocomplete="new-password" placeholder="••••••••" class="d2lg-in" required minlength="8" @focus="onFocus" @blur="onBlur" />
            </div>

            <div v-if="error" class="d2lg-err">{{ error }}</div>

            <button type="submit" :disabled="submitting" class="d2lg-cta">
              <span v-if="submitting" class="d2lg-spin"></span>
              {{ submitting ? (isSetup ? (tr('login.creating') || 'Creating…') : (tr('login.signingIn') || 'Signing in…')) : (isSetup ? (tr('login.createAdminAccount') || 'Create admin account') : (tr('login.signIn') || 'Sign in')) }}
            </button>
          </form>
        </div>

        <div v-if="branding.footerText" style="text-align:center;font-size:12px;color:var(--text-3);margin-top:16px">{{ branding.footerText }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { authApi } from '../api/index.js'
import { useBrandingStore } from '../stores/branding'
import { useSystemStore } from '../stores/system'
// Design2 tokens + base — the login route is rendered bare (outside D2App), so
// it must load the token/reset stylesheets itself for `.d2-root` to resolve.
import '../design2/tokens.css'
import '../design2/base.css'

const i18n = useI18n()
function tr(k) { try { const v = i18n.t(k); return v === k ? '' : v } catch (_) { return '' } }
const router = useRouter()
const branding = useBrandingStore()
const system = useSystemStore()

const isSetup = ref(false)
const loading = ref(true)
const submitting = ref(false)
const error = ref(null)
const form = ref({ username: '', password: '', password2: '' })

const pageTitle = computed(() => branding.loginTitle || branding.appName || 'Admin Panel')

// language switcher (same set + persistence as the shell)
const langOpen = ref(false)
const LOCALES = [
  { code: 'en', label: 'English' }, { code: 'ru', label: 'Русский' },
  { code: 'de', label: 'Deutsch' }, { code: 'fr', label: 'Français' }, { code: 'es', label: 'Español' },
]
const curLangCode = computed(() => i18n.locale.value || 'en')
const curLang = computed(() => curLangCode.value.toUpperCase())
function setLang(code) { i18n.locale.value = code; try { localStorage.setItem('sb_lang', code) } catch (_) {}; langOpen.value = false }
function toggleTheme() { system.setTheme(system.theme === 'dark' ? 'light' : 'dark') }
function onDoc() { langOpen.value = false }
function onFocus(e) { const s = e.target.style; s.borderColor = 'var(--accent)'; s.boxShadow = '0 0 0 3px var(--accent-ring)'; s.background = 'var(--panel)' }
function onBlur(e) { const s = e.target.style; s.borderColor = 'var(--border-strong)'; s.boxShadow = 'none'; s.background = 'var(--panel-2)' }

onMounted(async () => {
  document.addEventListener('click', onDoc)
  const token = localStorage.getItem('sb_token')
  if (token) {
    try { await authApi.me(); router.replace('/'); return } catch { localStorage.removeItem('sb_token') }
  }
  try { const res = await authApi.setupStatus(); isSetup.value = res.data.needs_setup } catch { /* assume login */ }
  loading.value = false
})

const handleLogin = async () => {
  submitting.value = true; error.value = null
  try {
    const res = await authApi.login({ username: form.value.username, password: form.value.password })
    localStorage.setItem('sb_token', res.data.access_token)
    if (res.data.refresh_token) localStorage.setItem('sb_refresh_token', res.data.refresh_token)
    router.push('/')
  } catch (err) {
    const detail = err.response?.data?.detail
    if (err.response?.status === 429) error.value = detail || 'Too many attempts. Wait 5 minutes.'
    else if (err.response?.status === 423) error.value = detail || 'Account locked. Try again later.'
    else error.value = detail || (tr('login.failed') || 'Login failed')
  } finally { submitting.value = false }
}

const handleSetup = async () => {
  if (form.value.password !== form.value.password2) { error.value = tr('login.passwordsDoNotMatch') || 'Passwords do not match'; return }
  submitting.value = true; error.value = null
  try {
    const res = await authApi.setup({ username: form.value.username, password: form.value.password })
    localStorage.setItem('sb_token', res.data.access_token)
    if (res.data.refresh_token) localStorage.setItem('sb_refresh_token', res.data.refresh_token)
    router.push('/')
  } catch (err) { error.value = err.response?.data?.detail || 'Setup failed' } finally { submitting.value = false }
}
</script>

<style scoped>
.d2-login { min-height: 100vh; background: var(--bg); }
.d2lg-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; position: relative; }
.d2lg-top { position: absolute; top: 18px; right: 20px; display: flex; align-items: center; gap: 8px; }
.d2lg-ibtn { display: flex; align-items: center; gap: 6px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 8px; font: inherit; cursor: pointer; text-decoration: none; }
.d2lg-ibtn:hover { background: var(--panel-2); color: var(--text); }
.d2lg-sq { width: 32px; padding: 0; justify-content: center; }
.d2lg-langmenu { position: absolute; top: 38px; right: 0; z-index: 56; width: 150px; background: var(--panel); border: 1px solid var(--border); border-radius: 11px; box-shadow: var(--shadow-lg); padding: 5px; }
.d2lg-langitem { display: block; width: 100%; padding: 8px 11px; border: none; border-radius: 8px; background: none; font: inherit; font-size: 13px; cursor: pointer; text-align: left; }
.d2lg-langitem:hover { background: var(--panel-2); }
.d2lg-wrap { width: 400px; max-width: 100%; animation: d2lgUp .4s ease; }
.d2lg-logo { width: 50px; height: 50px; border-radius: 14px; background: var(--accent); display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px var(--accent-ring); margin-bottom: 16px; overflow: hidden; }
.d2lg-card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow-md); padding: 24px; }
.d2lg-label { display: block; font-size: 12.5px; font-weight: 550; margin-bottom: 7px; color: var(--text); }
.d2lg-in { width: 100%; height: 44px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 11px; padding: 0 14px; font: inherit; font-size: 14px; outline: none; }
.d2lg-cta { display: flex; align-items: center; justify-content: center; gap: 8px; height: 46px; border: none; background: var(--accent); color: #fff; border-radius: 11px; font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 4px; box-shadow: 0 2px 8px var(--accent-ring); }
.d2lg-cta:hover:not(:disabled) { background: var(--accent-2); }
.d2lg-cta:disabled { opacity: .75; cursor: default; }
.d2lg-err { font-size: 12.5px; color: var(--red); background: var(--red-soft); border-radius: 9px; padding: 9px 12px; }
.d2lg-spin { width: 16px; height: 16px; border: 2px solid rgba(255, 255, 255, .4); border-top-color: #fff; border-radius: 50%; animation: d2spin .6s linear infinite; display: inline-block; }
.d2lg-spin-lg { width: 26px; height: 26px; border-color: var(--accent-soft); border-top-color: var(--accent); }
@keyframes d2lgUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
</style>
