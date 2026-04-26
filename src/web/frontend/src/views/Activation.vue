<template>
  <div class="activation-page d-flex align-items-center justify-content-center min-vh-100 bg-light">
    <div class="card shadow-sm" style="max-width: 520px; width: 100%;">
      <div class="card-body p-4 p-md-5">

        <!-- Header -->
        <div class="text-center mb-4">
          <div class="mb-3">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="currentColor"
                 class="text-primary" viewBox="0 0 16 16">
              <path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2m3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2"/>
            </svg>
          </div>
          <h4 class="fw-bold mb-1">{{ t('activation.title') }}</h4>
          <p class="text-muted small">{{ t('activation.subtitle') }}</p>
        </div>

        <!-- Alert from backend -->
        <div v-if="backendMessage" class="alert alert-warning small py-2">
          {{ backendMessage }}
        </div>

        <!-- Step 1: Activation Code -->
        <div class="mb-4">
          <label class="form-label fw-semibold small text-uppercase text-muted">
            {{ t('activation.yourCode') }}
          </label>
          <div class="input-group">
            <input
              type="text"
              class="form-control font-monospace"
              :value="activationCode"
              readonly
            />
            <button class="btn btn-outline-secondary" @click="copyCode" :title="t('activation.copy')">
              <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1z"/>
                <path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0z"/>
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="text-success" viewBox="0 0 16 16">
                <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0"/>
              </svg>
            </button>
          </div>
          <div class="form-text">
            {{ t('activation.codeHint') }}
          </div>
        </div>

        <!-- Step 2: Enter License Key -->
        <div class="mb-3">
          <label class="form-label fw-semibold small text-uppercase text-muted">
            {{ t('activation.enterKey') }}
          </label>
          <textarea
            v-model="licenseKey"
            class="form-control font-monospace"
            rows="3"
            :placeholder="t('activation.keyPlaceholder')"
            :disabled="activating"
          />
        </div>

        <div v-if="error" class="alert alert-danger small py-2">{{ error }}</div>
        <div v-if="success" class="alert alert-success small py-2">{{ success }}</div>

        <button
          class="btn btn-primary w-100"
          @click="activate"
          :disabled="activating || !licenseKey.trim()"
        >
          <span v-if="activating" class="spinner-border spinner-border-sm me-2"></span>
          {{ activating ? t('activation.activating') : t('activation.activate') }}
        </button>

        <div class="text-center mt-3">
          <small class="text-muted">
            {{ t('activation.contact') }}
          </small>
        </div>

      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import axios from 'axios'

export default {
  name: 'Activation',

  setup() {
    const activationCode = ref(window.__activationCode || '')
    const licenseKey     = ref('')
    const activating     = ref(false)
    const copied         = ref(false)
    const error          = ref('')
    const success        = ref('')
    const backendMessage = ref(window.__activationMessage || '')

    // i18n minimal inline (reuse existing i18n if available)
    const msgs = {
      title:        'Product Activation',
      subtitle:     'Send your activation code to the vendor to receive a license key.',
      yourCode:     'Your Activation Code',
      copy:         'Copy',
      codeHint:     'Send this code to your vendor. The license key will be bound to this machine.',
      enterKey:     'License Key',
      keyPlaceholder: 'Paste your license key here…',
      activate:     'Activate',
      activating:   'Activating…',
      contact:      'Contact support if you do not have a license key.',
    }

    function t(key) {
      const k = key.replace('activation.', '')
      // Try vue-i18n if available
      try {
        if (window.__i18n) return window.__i18n.global.t(`activation.${k}`) || msgs[k] || k
      } catch {}
      return msgs[k] || k
    }

    async function loadCode() {
      if (activationCode.value) return
      try {
        const r = await axios.get('/api/v1/system/activation')
        activationCode.value = r.data.activation_code || ''
      } catch {
        // ignore — code shown from stored 403 response if available
      }
    }

    async function activate() {
      error.value   = ''
      success.value = ''
      activating.value = true
      try {
        await axios.post('/api/v1/system/license', { license_key: licenseKey.value.trim() })
        success.value = 'License activated successfully! Redirecting…'
        setTimeout(() => { window.location.href = '/' }, 1500)
      } catch (e) {
        const msg = e.response?.data?.detail || 'Activation failed. Check your license key.'
        error.value = msg
      } finally {
        activating.value = false
      }
    }

    async function copyCode() {
      try {
        await navigator.clipboard.writeText(activationCode.value)
        copied.value = true
        setTimeout(() => { copied.value = false }, 2000)
      } catch {}
    }

    onMounted(loadCode)

    return { activationCode, licenseKey, activating, copied, error, success, backendMessage, t, activate, copyCode }
  }
}
</script>

<style scoped>
.activation-page { background: #f0f2f5; }
.font-monospace { font-family: 'Courier New', monospace; font-size: 0.85rem; letter-spacing: 0.03em; }
</style>
