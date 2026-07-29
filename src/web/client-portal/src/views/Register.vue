<template>
  <div class="fx-login-shell" :class="theme === 'dark' ? 'theme-dark' : 'theme-light'">
    <button class="fx-login-theme-toggle" :title="$t(theme === 'dark' ? 'nav.lightMode' : 'nav.darkMode')"
            @click="toggleTheme">
      <FxIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
    </button>

    <main class="fx-login-card">
      <div class="fx-login-brand">
        <div class="fx-login-logo" :class="{ 'fx-login-logo--bare': isCustomLogo }">
          <img :src="brandLogo" alt="" />
        </div>
        <h1 class="fx-login-title">{{ $t('auth.signUp') }}</h1>
        <p class="fx-login-sub">{{ $t('auth.signUpSub') }}</p>
      </div>

      <form class="fx-login-form" @submit.prevent="handleRegister" novalidate>
        <!-- Username first since email is now optional. Putting it on top
             makes the required-vs-optional grouping obvious. -->
        <div class="fx-field">
          <label for="r-username">{{ $t('auth.username') }}</label>
          <div class="fx-field-input">
            <FxIcon name="users" :size="16" />
            <input id="r-username" v-model="form.username" type="text" placeholder="username"
                   autocomplete="username" minlength="3" required />
          </div>
        </div>

        <div class="fx-field">
          <label for="r-email">
            {{ $t('auth.email') }}
            <span class="fx-field-hint">{{ $t('auth.optional') }}</span>
          </label>
          <div class="fx-field-input">
            <FxIcon name="mail" :size="16" />
            <input id="r-email" v-model="form.email" type="email" placeholder="your@email.com"
                   autocomplete="email" />
          </div>
          <span class="fx-field-warning">
            {{ form.email ? $t('auth.emailNote') : $t('auth.emailWarning') }}
          </span>
        </div>

        <div class="fx-field">
          <label for="r-fullname">{{ $t('auth.fullName') }}</label>
          <div class="fx-field-input no-icon">
            <input id="r-fullname" v-model="form.full_name" type="text"
                   placeholder="John Doe" autocomplete="name" />
          </div>
        </div>

        <div class="fx-field">
          <label for="r-password">{{ $t('auth.password') }}</label>
          <div class="fx-field-input has-toggle">
            <FxIcon name="lock" :size="16" />
            <input id="r-password" v-model="form.password" :type="showPw ? 'text' : 'password'"
                   placeholder="••••••••" minlength="8" autocomplete="new-password" required />
            <button type="button" class="fx-pw-toggle" :aria-label="$t('auth.toggleVisibility')"
                    @click="showPw = !showPw">
              <FxIcon name="eye" :size="16" />
            </button>
          </div>
        </div>

        <div class="fx-field">
          <label for="r-password2">{{ $t('auth.confirmPassword') }}</label>
          <div class="fx-field-input">
            <FxIcon name="lock" :size="16" />
            <input id="r-password2" v-model="passwordConfirm" type="password"
                   placeholder="••••••••" autocomplete="new-password" required />
          </div>
        </div>

        <div v-if="error" class="fx-login-alert error">{{ error }}</div>

        <button type="submit" class="fx-btn fx-btn-primary fx-login-submit" :disabled="loading">
          <span v-if="loading">{{ $t('auth.creatingAccount') }}</span>
          <template v-else>
            <span>{{ $t('auth.signUp') }}</span>
            <FxIcon name="send" :size="14" />
          </template>
        </button>
      </form>

      <div class="fx-login-foot">
        {{ $t('auth.haveAccount') }}
        <router-link :to="{ path: '/login', query: $route.query.next ? { next: $route.query.next } : {} }" class="fx-login-link">{{ $t('auth.signInLink') }}</router-link>
      </div>
    </main>

    <div class="fx-login-meta">
      <a v-if="privacyUrl" :href="privacyUrl" :target="privacyExternal ? '_blank' : undefined" rel="noreferrer">{{ $t('footer.privacy') }}</a>
      <template v-if="termsUrl">
        <span v-if="privacyUrl" class="sep">·</span>
        <a :href="termsUrl" :target="termsExternal ? '_blank' : undefined" rel="noreferrer">{{ $t('footer.terms') }}</a>
      </template>
      <template v-if="supportHref">
        <span v-if="privacyUrl || termsUrl" class="sep">·</span>
        <a :href="supportHref" :target="supportExternal ? '_blank' : undefined" rel="noreferrer">{{ $t('nav.support') }}</a>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { setPortalUser } from '../session'
import FxIcon from '../components/FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'
import { brandingUrl, isExternalHref, legalDocumentHref } from '../branding'
import { safePortalPath } from '../utils.js'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const privacyUrl = computed(() => legalDocumentHref('privacy'))
const termsUrl = computed(() => legalDocumentHref('terms'))
const privacyExternal = computed(() => isExternalHref(privacyUrl.value))
const termsExternal = computed(() => isExternalHref(termsUrl.value))
const supportUrl = computed(() => brandingUrl('branding_support_url'))
const supportEmail = computed(() => String(window.__branding?.branding_support_email || '').trim())
const supportHref = computed(() => supportUrl.value || (supportEmail.value ? `mailto:${supportEmail.value}` : ''))
const supportExternal = computed(() => /^https?:/i.test(supportHref.value))

// Show only the operator's customer-facing name. Empty → hide text.
const brandName = computed(() => (
  window.__branding?.branding_customer_app_name || ''
))
const brandLogo = computed(() => {
  const url = window.__branding?.branding_customer_logo_url
            || window.__branding?.branding_logo_url
  if (!url) return bundledLogo
  return url
})
// Drop the blue accent frame only when a customer-facing logo URL was
// uploaded — see Login.vue for the rationale. The admin/platform logo
// (`branding_logo_url`) keeps the frame so fresh installs still look
// finished.
const isCustomLogo = computed(() => (
  !!window.__branding?.branding_customer_logo_url
))

const referralCode = typeof route.query.ref === 'string'
  && /^[A-Z0-9]{8}$/i.test(route.query.ref.trim())
  ? route.query.ref.trim().toUpperCase()
  : ''
const form = ref({ email: '', username: '', full_name: '', password: '', referral_code: referralCode })
const passwordConfirm = ref('')
const loading = ref(false)
const error = ref(null)
const showPw = ref(false)

const theme = ref(localStorage.getItem('sb_theme') === 'dark' ? 'dark' : 'light')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('sb_theme', theme.value)
  window.dispatchEvent(new CustomEvent('fx:theme', { detail: theme.value }))
}

const handleRegister = async () => {
  error.value = null

  if (form.value.password !== passwordConfirm.value) {
    error.value = t('auth.passwordMismatch')
    return
  }
  if (form.value.password.length < 8) {
    error.value = t('auth.passwordTooShort')
    return
  }

  loading.value = true
  try {
    // Strip blank email so backend stores NULL rather than empty
    // string (unique-index respects NULL but treats empty strings as
    // duplicates after the second username-only signup).
    const payload = { ...form.value }
    if (!payload.email || !payload.email.trim()) delete payload.email
    if (!payload.referral_code) delete payload.referral_code
    const response = await portalApi.register(payload)
    setPortalUser(response.data.user)
    // Honor ?next= so a customer who hit "Choose plan" on the
    // marketing landing (deep-link target /register?next=/plans)
    // lands on the plans picker immediately after signup, with no
    // detour through the dashboard. The shared path validator rejects
    // protocol-relative and backslash-based redirect targets.
    const nextParam = safePortalPath(route.query.next)
    router.push(nextParam)
  } catch (err) {
    if (err.response?.data?.detail) {
      if (typeof err.response.data.detail === 'string') {
        error.value = err.response.data.detail
      } else if (Array.isArray(err.response.data.detail)) {
        error.value = err.response.data.detail.map(e => e.msg).join('. ')
      } else {
        error.value = t('auth.registerFailed')
      }
    } else {
      error.value = t('auth.registerFailed')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* All visual styles for the login shell live in design-tokens.css
   so Login + Register can share the same atoms without duplication. */
</style>
