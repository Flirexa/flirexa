<template>
  <div class="auth-page">
    <div class="auth-grid"></div>
    <div class="auth-container">
      <div class="auth-card">
        <div class="auth-logo">
          <img v-if="branding.logoUrl" :src="branding.logoUrl" alt="" style="height: 48px; margin-bottom: 12px;" />
          <h2>{{ branding.loginTitle || branding.appName }}</h2>
          <p class="text-muted">{{ isSetup ? $t('login.createAdmin') : $t('login.signInContinue') }}</p>
        </div>

        <div v-if="loading" class="text-center py-4">
          <div class="spinner-border text-primary"></div>
        </div>

        <!-- SETUP FORM (first time) -->
        <form v-else-if="isSetup" @submit.prevent="handleSetup">
          <div class="mb-3">
            <label for="username" class="form-label">{{ $t("login.username") }}</label>
            <input type="text" class="form-control" id="username" v-model="form.username"
              required minlength="3" maxlength="50" autocomplete="username"
              placeholder="admin">
          </div>

          <div class="mb-3">
            <label for="password" class="form-label">{{ $t("login.password") }}</label>
            <input type="password" class="form-control" id="password" v-model="form.password"
              required minlength="8" maxlength="100" autocomplete="new-password"
              placeholder="min 8 characters">
          </div>

          <div class="mb-3">
            <label for="password2" class="form-label">{{ $t("login.confirmPassword") }}</label>
            <input type="password" class="form-control" id="password2" v-model="form.password2"
              required minlength="8" autocomplete="new-password"
              placeholder="repeat password">
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>

          <button type="submit" class="btn btn-primary w-100" :disabled="submitting">
            <span v-if="submitting">
              <span class="spinner-border spinner-border-sm me-2"></span>
              {{ $t("login.creating") }}
            </span>
            <span v-else>{{ $t("login.createAdminAccount") }}</span>
          </button>
        </form>

        <!-- LOGIN FORM -->
        <form v-else @submit.prevent="handleLogin">
          <div class="mb-3">
            <label for="username" class="form-label">{{ $t("login.username") }}</label>
            <input type="text" class="form-control" id="username" v-model="form.username"
              required autocomplete="username" placeholder="admin">
          </div>

          <div class="mb-3">
            <label for="password" class="form-label">{{ $t("login.password") }}</label>
            <input type="password" class="form-control" id="password" v-model="form.password"
              required autocomplete="current-password" placeholder="password">
          </div>

          <div class="alert alert-danger" v-if="error">{{ error }}</div>

          <button type="submit" class="btn btn-primary w-100" :disabled="submitting">
            <span v-if="submitting">
              <span class="spinner-border spinner-border-sm me-2"></span>
              {{ $t("login.signingIn") }}
            </span>
            <span v-else>{{ $t("login.signIn") }}</span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { authApi } from '../api/index.js'
import { useBrandingStore } from '../stores/branding'

const { t } = useI18n()
const router = useRouter()
const branding = useBrandingStore()

const isSetup = ref(false)
const loading = ref(true)
const submitting = ref(false)
const error = ref(null)
const form = ref({ username: '', password: '', password2: '' })

onMounted(async () => {
  // Check if already authenticated
  const token = localStorage.getItem('sb_token')
  if (token) {
    try {
      await authApi.me()
      router.replace('/')
      return
    } catch {
      localStorage.removeItem('sb_token')
    }
  }

  // Check if setup is needed
  try {
    const res = await authApi.setupStatus()
    isSetup.value = res.data.needs_setup
  } catch {
    // If fails, assume login mode
  }
  loading.value = false
})

const handleLogin = async () => {
  submitting.value = true
  error.value = null

  try {
    const res = await authApi.login({
      username: form.value.username,
      password: form.value.password,
    })
    localStorage.setItem('sb_token', res.data.access_token)
    if (res.data.refresh_token) localStorage.setItem('sb_refresh_token', res.data.refresh_token)
    router.push('/')
  } catch (err) {
    const detail = err.response?.data?.detail
    if (err.response?.status === 429) {
      error.value = detail || 'Too many attempts. Wait 5 minutes.'
    } else if (err.response?.status === 423) {
      error.value = detail || 'Account locked. Try again later.'
    } else {
      error.value = detail || 'Login failed'
    }
  } finally {
    submitting.value = false
  }
}

const handleSetup = async () => {
  if (form.value.password !== form.value.password2) {
    error.value = t('login.passwordsDoNotMatch')
    return
  }

  submitting.value = true
  error.value = null

  try {
    const res = await authApi.setup({
      username: form.value.username,
      password: form.value.password,
    })
    localStorage.setItem('sb_token', res.data.access_token)
    if (res.data.refresh_token) localStorage.setItem('sb_refresh_token', res.data.refresh_token)
    router.push('/')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Setup failed'
  } finally {
    submitting.value = false
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

/* Left decorative panel */
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

.auth-grid {
  position: fixed; inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
  background-size: 50px 50px;
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
.auth-logo .text-muted { color: #B9B9C3 !important; font-size: .9rem; }

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

.alert-danger { background: rgba(234,84,85,.12); border: none; color: #EA5455; border-radius: .5rem; font-size: .875rem; }
</style>
