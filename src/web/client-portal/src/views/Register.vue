<template>
  <div class="auth-page">
    <div class="auth-container">
      <div class="auth-card">
        <div class="auth-logo">
          <h2>{{ appName }}</h2>
          <p class="text-muted">{{ $t('auth.signUpTitle') }}</p>
        </div>

        <form @submit.prevent="handleRegister">
          <div class="mb-3">
            <label for="email" class="form-label">{{ $t('auth.email') }}</label>
            <input type="email" class="form-control" id="email" v-model="form.email" required placeholder="your@email.com">
          </div>

          <div class="mb-3">
            <label for="username" class="form-label">{{ $t('auth.username') }}</label>
            <input type="text" class="form-control" id="username" v-model="form.username" required placeholder="username" minlength="3">
          </div>

          <div class="mb-3">
            <label for="full_name" class="form-label">{{ $t('auth.fullName') }}</label>
            <input type="text" class="form-control" id="full_name" v-model="form.full_name" placeholder="John Doe">
          </div>

          <div class="mb-3">
            <label for="password" class="form-label">{{ $t('auth.password') }}</label>
            <input type="password" class="form-control" id="password" v-model="form.password" required placeholder="••••••••" minlength="8">
          </div>

          <div class="mb-3">
            <label for="password_confirm" class="form-label">{{ $t('auth.confirmPassword') }}</label>
            <input type="password" class="form-control" id="password_confirm" v-model="passwordConfirm" required placeholder="••••••••">
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>

          <button type="submit" class="btn btn-primary w-100 mb-3" :disabled="loading">
            <span v-if="loading">
              <span class="spinner-border spinner-border-sm me-2"></span>
              {{ $t('auth.creatingAccount') }}
            </span>
            <span v-else>{{ $t('auth.signUp') }}</span>
          </button>

          <div class="text-center">
            <p class="text-muted">
              {{ $t('auth.haveAccount') }}
              <router-link to="/login" class="text-primary">{{ $t('auth.signInLink') }}</router-link>
            </p>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'

const router = useRouter()
const { t } = useI18n()

const appName = ref(window.__branding?.branding_app_name || 'VPN Manager')
const form = ref({ email: '', username: '', full_name: '', password: '' })
const passwordConfirm = ref('')
const loading = ref(false)
const error = ref(null)

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
@media (max-width: 576px) {
  .auth-container { padding: 1rem; }
  .auth-card { padding: 1.75rem 1.25rem; }
}
</style>
