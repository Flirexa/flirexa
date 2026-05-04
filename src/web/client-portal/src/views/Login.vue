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
          <div class="fx-login-logo"><img :src="brandLogo" alt="" /></div>
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
          <div class="fx-login-logo"><img :src="brandLogo" alt="" /></div>
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
          <div class="fx-login-logo"><img :src="brandLogo" alt="" /></div>
          <h1 class="fx-login-title">{{ brandName }}</h1>
          <p class="fx-login-sub">{{ $t('auth.signInSub') }}</p>
        </div>

        <form class="fx-login-form" @submit.prevent="handleLogin" novalidate>
          <div class="fx-field">
            <label for="email">{{ $t('auth.email') }}</label>
            <div class="fx-field-input" :class="{ error: emailError }">
              <FxIcon name="mail" :size="16" />
              <input id="email" v-model="form.email" type="email" autocomplete="email"
                     placeholder="your@email.com" required @input="emailError = false" />
            </div>
            <span v-if="emailError" class="fx-field-error">{{ $t('auth.invalidEmail') }}</span>
          </div>

          <div class="fx-field">
            <label for="password">{{ $t('auth.password') }}</label>
            <div class="fx-field-input has-toggle" :class="{ error: passwordError }">
              <FxIcon name="lock" :size="16" />
              <input id="password" v-model="form.password" :type="showPw ? 'text' : 'password'"
                     autocomplete="current-password" placeholder="••••••••" minlength="6" required
                     @input="passwordError = false" />
              <button type="button" class="fx-pw-toggle" :aria-label="$t('auth.toggleVisibility')"
                      @click="showPw = !showPw">
                <FxIcon name="eye" :size="16" />
              </button>
            </div>
            <span v-if="passwordError" class="fx-field-error">{{ $t('auth.passwordTooShort') }}</span>
          </div>

          <div class="fx-login-row">
            <label class="fx-check">
              <input type="checkbox" v-model="remember" />
              <span class="fx-check-box"><FxIcon name="check" :size="11" :stroke-width="3" /></span>
              <span>{{ $t('auth.rememberMe') }}</span>
            </label>
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
          <router-link to="/register" class="fx-login-link">{{ $t('auth.signUpLink') }}</router-link>
        </div>
      </template>
    </main>

    <div class="fx-login-meta">
      <a href="#" @click.prevent>{{ $t('footer.privacy') }}</a>
      <span class="sep">·</span>
      <a href="#" @click.prevent>{{ $t('footer.terms') }}</a>
      <span class="sep">·</span>
      <router-link to="/support">{{ $t('nav.support') }}</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import FxIcon from '../components/FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const brandName = computed(() => window.__branding?.branding_app_name || 'Flirexa VPN')
const brandLogo = computed(() => {
  const url = window.__branding?.branding_logo_url
  if (!url) return bundledLogo
  if (url.startsWith('/')) {
    const adminPort = '10086'
    return `${window.location.protocol}//${window.location.hostname}:${adminPort}${url}`
  }
  return url
})

const form = ref({ email: '', password: '' })
const remember = ref(true)
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

const validateEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e || '')

const handleLogin = async () => {
  emailError.value = !validateEmail(form.value.email)
  passwordError.value = (form.value.password || '').length < 6
  if (emailError.value || passwordError.value) return

  loading.value = true
  error.value = null
  try {
    const response = await portalApi.login(form.value)
    localStorage.setItem('client_access_token', response.data.access_token)
    localStorage.setItem('client_user', JSON.stringify(response.data.user))
    if (remember.value) localStorage.setItem('remember_me', 'true')
    router.push('/')
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
    error.value = err.response?.data?.detail || t('common.error')
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
    error.value = err.response?.data?.detail || t('common.error')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* All visual styles for the login shell live in design-tokens.css
   so Login + Register can share the same atoms without duplication. */
</style>
