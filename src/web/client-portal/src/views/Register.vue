<template>
  <div class="fx-login-shell" :class="theme === 'dark' ? 'theme-dark' : 'theme-light'">
    <button class="fx-login-theme-toggle" :title="$t(theme === 'dark' ? 'nav.lightMode' : 'nav.darkMode')"
            @click="toggleTheme">
      <FxIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
    </button>

    <main class="fx-login-card">
      <div class="fx-login-brand">
        <div class="fx-login-logo"><img :src="brandLogo" alt="" /></div>
        <h1 class="fx-login-title">{{ $t('auth.signUp') }}</h1>
        <p class="fx-login-sub">{{ $t('auth.signUpSub') }}</p>
      </div>

      <form class="fx-login-form" @submit.prevent="handleRegister" novalidate>
        <div class="fx-field">
          <label for="r-email">{{ $t('auth.email') }}</label>
          <div class="fx-field-input">
            <FxIcon name="mail" :size="16" />
            <input id="r-email" v-model="form.email" type="email" placeholder="your@email.com"
                   autocomplete="email" required />
          </div>
        </div>

        <div class="fx-field">
          <label for="r-username">{{ $t('auth.username') }}</label>
          <div class="fx-field-input">
            <FxIcon name="users" :size="16" />
            <input id="r-username" v-model="form.username" type="text" placeholder="username"
                   autocomplete="username" minlength="3" required />
          </div>
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
        <router-link to="/login" class="fx-login-link">{{ $t('auth.signInLink') }}</router-link>
      </div>
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
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import FxIcon from '../components/FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'

const router = useRouter()
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

const form = ref({ email: '', username: '', full_name: '', password: '' })
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
    const response = await portalApi.register(form.value)
    localStorage.setItem('client_access_token', response.data.access_token)
    localStorage.setItem('client_user', JSON.stringify(response.data.user))
    router.push('/')
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
