<template>
  <div class="auth-page">
    <div class="auth-container">
      <div class="auth-card">
        <div class="auth-logo">
          <div class="auth-logo-icon">🛡️</div>
          <h2>{{ appName }}</h2>
          <p class="text-muted">{{ showForgot ? $t('auth.resetPassword') : $t('auth.signInTitle') }}</p>
        </div>

        <!-- Login Form -->
        <form v-if="!showForgot && !showReset" @submit.prevent="handleLogin">
          <div class="mb-3">
            <label for="email" class="form-label">{{ $t('auth.email') }}</label>
            <input type="email" class="form-control" id="email" v-model="form.email" required placeholder="your@email.com">
          </div>

          <div class="mb-3">
            <label for="password" class="form-label">{{ $t('auth.password') }}</label>
            <input type="password" class="form-control" id="password" v-model="form.password" required placeholder="••••••••">
          </div>

          <div class="mb-3 d-flex justify-content-between align-items-center">
            <div class="form-check">
              <input type="checkbox" class="form-check-input" id="remember" v-model="remember">
              <label class="form-check-label" for="remember">{{ $t('auth.rememberMe') }}</label>
            </div>
            <a href="#" class="small text-primary" @click.prevent="showForgot = true">{{ $t('auth.forgotPassword') }}</a>
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>
          <div class="alert alert-success" v-if="success">{{ success }}</div>

          <button type="submit" class="btn btn-primary w-100 mb-3" :disabled="loading">
            <span v-if="loading">
              <span class="spinner-border spinner-border-sm me-2"></span>
              {{ $t('auth.signingIn') }}
            </span>
            <span v-else>{{ $t('auth.signIn') }}</span>
          </button>

          <div class="text-center">
            <p class="text-muted">
              {{ $t('auth.noAccount') }}
              <router-link to="/register" class="text-primary">{{ $t('auth.signUpLink') }}</router-link>
            </p>
          </div>
        </form>

        <!-- Forgot Password Form -->
        <form v-if="showForgot" @submit.prevent="handleForgotPassword">
          <div class="mb-3">
            <label for="resetEmail" class="form-label">{{ $t('auth.email') }}</label>
            <input type="email" class="form-control" id="resetEmail" v-model="forgotEmail" required placeholder="your@email.com">
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>
          <div class="alert alert-success" v-if="success">{{ success }}</div>

          <button type="submit" class="btn btn-primary w-100 mb-3" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2"></span>
            {{ $t('auth.sendResetLink') }}
          </button>

          <div class="text-center">
            <a href="#" class="text-primary" @click.prevent="showForgot = false; showReset = true">{{ $t('auth.haveResetToken') }}</a>
            <span class="mx-2 text-muted">|</span>
            <a href="#" class="text-muted" @click.prevent="showForgot = false">{{ $t('auth.backToLogin') }}</a>
          </div>
        </form>

        <!-- Reset Password with Token Form -->
        <form v-if="showReset" @submit.prevent="handleResetPassword">
          <div class="mb-3">
            <label for="resetToken" class="form-label">{{ $t('auth.resetToken') }}</label>
            <input type="text" class="form-control" id="resetToken" v-model="resetForm.token" required>
          </div>
          <div class="mb-3">
            <label for="newPassword" class="form-label">{{ $t('auth.newPassword') }}</label>
            <input type="password" class="form-control" id="newPassword" v-model="resetForm.new_password" required minlength="8">
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>
          <div class="alert alert-success" v-if="success">{{ success }}</div>

          <button type="submit" class="btn btn-primary w-100 mb-3" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2"></span>
            {{ $t('auth.resetPassword') }}
          </button>

          <div class="text-center">
            <a href="#" class="text-muted" @click.prevent="showReset = false">{{ $t('auth.backToLogin') }}</a>
          </div>
        </form>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const appName = ref(window.__branding?.branding_app_name || 'VPN Manager')
const form = ref({ email: '', password: '' })
const remember = ref(false)
const loading = ref(false)
const error = ref(null)
const success = ref(null)
const showForgot = ref(false)
const showReset = ref(false)
const forgotEmail = ref('')
const resetForm = ref({ token: '', new_password: '' })

onMounted(() => {
  const resetToken = route.query.reset_token
  if (typeof resetToken === 'string' && resetToken.trim()) {
    showForgot.value = false
    showReset.value = true
    resetForm.value.token = resetToken.trim()
  }
})

const handleLogin = async () => {
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
  error.value = null
  success.value = null
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
  error.value = null
  success.value = null
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
/* ── Vuexy Auth Layout ─────────────────────────────────────── */
.auth-page {
  min-height: 100vh;
  display: flex;
  background: #2C3152;
  overflow: hidden;
}

.auth-page::before {
  content: '';
  position: fixed;
  top: -200px; left: -200px;
  width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(115,103,240,.4) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}
.auth-page::after {
  content: '';
  position: fixed;
  bottom: -150px; right: 30%;
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(0,207,232,.2) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}

.auth-container {
  position: relative; z-index: 1;
  width: 100%; max-width: 420px;
  margin: auto;
  padding: 2rem;
}

.auth-card {
  background: #fff;
  border-radius: 1rem;
  padding: 2.5rem;
  box-shadow: 0 20px 60px rgba(0,0,0,.35);
}

.auth-logo { text-align: center; margin-bottom: 2rem; }
.auth-logo-icon {
  width: 56px; height: 56px; border-radius: 14px;
  background: linear-gradient(135deg, #7367F0, #9e95f5);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 1.6rem; margin-bottom: .75rem;
  box-shadow: 0 6px 20px rgba(115,103,240,.4);
}
.auth-logo h2 { font-size: 1.5rem; font-weight: 700; color: #5E5873; margin-bottom: .375rem; }
.auth-logo p { color: #B9B9C3 !important; font-size: .9rem; }

.form-label { color: #5E5873; font-size: .875rem; font-weight: 500; }
.form-control {
  border: 1px solid #D8D6DE; color: #6E6B7B;
  border-radius: .375rem; padding: .6rem .875rem;
  transition: border-color .15s, box-shadow .15s;
}
.form-control:focus {
  border-color: #7367F0;
  box-shadow: 0 3px 10px rgba(115,103,240,.2);
  color: #6E6B7B;
}
.form-control::placeholder { color: #B9B9C3; }
.form-check-label { font-size: .875rem; color: #6E6B7B; }

.btn-primary {
  padding: .7rem; border-radius: .375rem; font-weight: 600;
  background: #7367F0; border-color: #7367F0;
  box-shadow: 0 4px 16px rgba(115,103,240,.4);
  transition: all .2s;
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(115,103,240,.55);
  background: #5e50ee; border-color: #5e50ee;
}

.text-primary { color: #7367F0 !important; }
a.text-primary:hover { color: #5e50ee !important; }
.text-muted { color: #B9B9C3 !important; }

.alert-danger { background: rgba(234,84,85,.12); border: none; color: #EA5455; border-radius: .5rem; font-size: .875rem; }
.alert-success { background: rgba(40,199,111,.12); border: none; color: #28C76F; border-radius: .5rem; font-size: .875rem; }

@media (max-width: 576px) {
  .auth-container { padding: 1rem; }
  .auth-card { padding: 1.75rem 1.25rem; }
}
</style>
