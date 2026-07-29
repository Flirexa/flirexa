<template>
  <div class="fx-login-shell" :class="theme === 'dark' ? 'theme-dark' : 'theme-light'">
    <button class="fx-login-theme-toggle" :title="$t(theme === 'dark' ? 'nav.lightMode' : 'nav.darkMode')"
            @click="toggleTheme">
      <FxIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
    </button>

    <main class="fx-login-card">
      <!-- Reset password (token in query) -->
      <template v-if="showReset">
        <div class="fx-login-brand">
          <div class="fx-login-logo" :class="{ 'fx-login-logo--bare': isCustomLogo }">
            <img :src="brandLogo" alt="" />
          </div>
          <h1 class="fx-login-title">{{ $t('auth.resetPassword') }}</h1>
          <p class="fx-login-sub">{{ $t('auth.resetPasswordSub') }}</p>
        </div>

        <form class="fx-login-form" @submit.prevent="handleResetPassword">
          <div class="fx-field">
            <label for="resetToken">{{ $t('auth.resetToken') }}</label>
            <div class="fx-field-input no-icon">
              <input id="resetToken" v-model="resetForm.token" type="text" required />
            </div>
          </div>
          <div class="fx-field">
            <label for="newPassword">{{ $t('auth.newPassword') }}</label>
            <div class="fx-field-input has-toggle">
              <FxIcon name="lock" :size="16" />
              <input id="newPassword" v-model="resetForm.new_password" :type="showNewPw ? 'text' : 'password'"
                     minlength="8" required />
              <button type="button" class="fx-pw-toggle" :aria-label="$t('auth.toggleVisibility')"
                      @click="showNewPw = !showNewPw">
                <FxIcon :name="showNewPw ? 'eye' : 'eye'" :size="16" />
              </button>
            </div>
          </div>

          <div v-if="error" class="fx-login-alert error">{{ error }}</div>
          <div v-if="success" class="fx-login-alert success">{{ success }}</div>

          <button type="submit" class="fx-btn fx-btn-primary fx-login-submit" :disabled="loading">
            <span v-if="loading">{{ $t('common.loading') }}</span>
            <template v-else>
              <span>{{ $t('auth.resetPassword') }}</span>
              <FxIcon name="send" :size="14" />
            </template>
          </button>

          <div class="fx-login-foot">
            <a class="fx-login-link" href="#" @click.prevent="showReset = false">{{ $t('auth.backToLogin') }}</a>
          </div>
        </form>
      </template>

      <!-- Forgot password -->
      <template v-else-if="showForgot">
        <div class="fx-login-brand">
          <div class="fx-login-logo" :class="{ 'fx-login-logo--bare': isCustomLogo }">
            <img :src="brandLogo" alt="" />
          </div>
          <h1 class="fx-login-title">{{ $t('auth.resetPassword') }}</h1>
          <p class="fx-login-sub">{{ $t('auth.forgotPasswordSub') }}</p>
        </div>

        <form class="fx-login-form" @submit.prevent="handleForgotPassword">
          <div class="fx-field">
            <label for="forgotEmail">{{ $t('auth.email') }}</label>
            <div class="fx-field-input">
              <FxIcon name="mail" :size="16" />
              <input id="forgotEmail" v-model="forgotEmail" type="email" placeholder="your@email.com" required />
            </div>
          </div>

          <div v-if="error" class="fx-login-alert error">{{ error }}</div>
          <div v-if="success" class="fx-login-alert success">{{ success }}</div>

          <button type="submit" class="fx-btn fx-btn-primary fx-login-submit" :disabled="loading">
            <span v-if="loading">{{ $t('common.loading') }}</span>
            <template v-else>
              <span>{{ $t('auth.sendResetLink') }}</span>
              <FxIcon name="send" :size="14" />
            </template>
          </button>

          <div class="fx-login-foot">
            <a class="fx-login-link" href="#" @click.prevent="showForgot = false; showReset = true">
              {{ $t('auth.haveResetToken') }}
            </a>
            <span class="sep">·</span>
            <a class="fx-login-link" href="#" @click.prevent="showForgot = false">{{ $t('auth.backToLogin') }}</a>
          </div>
        </form>
      </template>

      <!-- Sign in -->
      <template v-else>
        <div class="fx-login-brand">
          <div class="fx-login-logo" :class="{ 'fx-login-logo--bare': isCustomLogo }">
            <img :src="brandLogo" alt="" />
          </div>
          <h1 class="fx-login-title">{{ brandName }}</h1>
          <p class="fx-login-sub">{{ $t('auth.signInSub') }}</p>
        </div>

        <form class="fx-login-form" @submit.prevent="handleLogin" novalidate>
          <div class="fx-field">
            <label for="identifier">{{ $t('auth.identifier') }}</label>
            <div class="fx-field-input" :class="{ error: emailError }">
              <FxIcon name="user" :size="16" />
              <input id="identifier" v-model="form.identifier" type="text" autocomplete="username"
                     :placeholder="$t('auth.identifierPlaceholder')" required
                     :aria-invalid="emailError || null"
                     :aria-describedby="emailError ? 'identifier-error' : null"
                     @input="emailError = false" />
            </div>
            <span v-if="emailError" id="identifier-error" class="fx-field-error">{{ $t('auth.identifierRequired') }}</span>
          </div>

          <div class="fx-field">
            <label for="password">{{ $t('auth.password') }}</label>
            <div class="fx-field-input has-toggle" :class="{ error: passwordError }">
              <FxIcon name="lock" :size="16" />
              <input id="password" v-model="form.password" :type="showPw ? 'text' : 'password'"
                     autocomplete="current-password" placeholder="••••••••" minlength="6" required
                     :aria-invalid="passwordError || null"
                     :aria-describedby="passwordError ? 'password-error' : null"
                     @input="passwordError = false" />
              <button type="button" class="fx-pw-toggle" :aria-label="$t('auth.toggleVisibility')"
                      @click="showPw = !showPw">
                <FxIcon name="eye" :size="16" />
              </button>
            </div>
            <span v-if="passwordError" id="password-error" class="fx-field-error">{{ $t('auth.passwordTooShort') }}</span>
          </div>

          <div class="fx-login-row" style="justify-content:flex-end">
            <a class="fx-login-link" href="#" @click.prevent="showForgot = true">{{ $t('auth.forgotPassword') }}</a>
          </div>

          <div v-if="error" class="fx-login-alert error">{{ error }}</div>
          <div v-if="success" class="fx-login-alert success">{{ success }}</div>

          <button type="submit" class="fx-btn fx-btn-primary fx-login-submit" :disabled="loading">
            <span v-if="loading">{{ $t('auth.signingIn') }}</span>
            <template v-else>
              <span>{{ $t('auth.signIn') }}</span>
              <FxIcon name="send" :size="14" />
            </template>
          </button>
        </form>

        <div class="fx-login-foot">
          {{ $t('auth.noAccount') }}
          <router-link :to="{ path: '/register', query: $route.query.next ? { next: $route.query.next } : {} }" class="fx-login-link">{{ $t('auth.signUpLink') }}</router-link>
        </div>
      </template>
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
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { setPortalUser } from '../session'
import FxIcon from '../components/FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'
import { brandingUrl, isExternalHref, legalDocumentHref } from '../branding'
import { apiErrorMessage, safePortalPath } from '../utils.js'

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
// Drop the blue accent frame only when the operator explicitly uploaded
// a *customer-facing* logo. Treating `branding_logo_url` as "custom" too
// was wrong — that field holds the platform/admin logo (often the same
// glyph as the bundled default), and stripping the frame around it made
// fresh installs look unfinished. Bare mode is reserved for the case
// where the operator deliberately put a different artwork on the
// customer side (e.g. their own white-labelled brand) via
// `branding_customer_logo_url`.
const isCustomLogo = computed(() => (
  !!window.__branding?.branding_customer_logo_url
))

// `identifier` accepts either email or username; the backend route
// disambiguates by presence of "@".
const form = ref({ identifier: '', password: '' })
const loading = ref(false)
const error = ref(null)
const success = ref(null)
const emailError = ref(false)
const passwordError = ref(false)
const showPw = ref(false)
const showNewPw = ref(false)

const showForgot = ref(false)
const showReset = ref(false)
const forgotEmail = ref('')
const resetForm = ref({ token: '', new_password: '' })

// Theme — same store as the main shell.
const theme = ref(localStorage.getItem('sb_theme') === 'dark' ? 'dark' : 'light')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('sb_theme', theme.value)
  window.dispatchEvent(new CustomEvent('fx:theme', { detail: theme.value }))
}

onMounted(() => {
  const resetToken = route.query.reset_token
  if (typeof resetToken === 'string' && resetToken.trim()) {
    showForgot.value = false
    showReset.value = true
    resetForm.value.token = resetToken.trim()
  }
})

const handleLogin = async () => {
  emailError.value = !(form.value.identifier || '').trim()
  passwordError.value = (form.value.password || '').length < 6
  if (emailError.value || passwordError.value) return

  loading.value = true
  error.value = null
  try {
    // Backend accepts both `identifier` (preferred) and `email` (legacy
    // mobile/portal builds) — send identifier explicitly so the route
    // does not have to guess.
    const response = await portalApi.login({
      identifier: form.value.identifier.trim(),
      password: form.value.password,
    })
    setPortalUser(response.data.user)
    // Honor ?next= so the landing-site "Choose plan" deep-link
    // (→ /register?next=/plans) lands the user where they expected
    // after sign-in instead of dumping them on the dashboard.
    const nextParam = safePortalPath(route.query.next)
    router.push(nextParam)
  } catch (err) {
    if (err.response?.data?.detail) {
      error.value = typeof err.response.data.detail === 'string'
        ? err.response.data.detail
        : t('auth.invalidCredentials')
    } else {
      error.value = t('auth.loginFailed')
    }
  } finally {
    loading.value = false
  }
}

const handleForgotPassword = async () => {
  loading.value = true
  error.value = null; success.value = null
  try {
    await portalApi.forgotPassword({ email: forgotEmail.value })
    success.value = t('auth.resetEmailSent')
  } catch (err) {
    error.value = apiErrorMessage(err, t('common.error'))
  } finally {
    loading.value = false
  }
}

const handleResetPassword = async () => {
  loading.value = true
  error.value = null; success.value = null
  try {
    await portalApi.resetPassword(resetForm.value)
    success.value = t('auth.passwordResetDone')
    setTimeout(() => { showReset.value = false; success.value = null }, 2000)
  } catch (err) {
    error.value = apiErrorMessage(err, t('common.error'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* All visual styles for the login shell live in design-tokens.css
   so Login + Register can share the same atoms without duplication. */
</style>
