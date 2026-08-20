<!-- New-design Activation GATE (his 1:1 handoff). Full-page license-activation
     gate. Wired to /system/activation (code) + /system/license (activate). -->
<template>
  <div class="d2-act-gate" style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px">
    <div style="width:440px;max-width:100%;animation:fadeUp .4s ease">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow-md);padding:26px">
        <div style="width:46px;height:46px;border-radius:12px;background:var(--amber-soft);color:var(--amber);display:flex;align-items:center;justify-content:center;margin-bottom:16px"><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V8a4 4 0 018 0v3"></path></svg></div>
        <div style="font-weight:650;font-size:18px;letter-spacing:-.01em">{{ tr('activation.gateTitle') || 'Activate your license' }}</div>
        <div style="font-size:13px;color:var(--text-2);margin-top:6px;line-height:1.5">{{ tr('activation.gateSub') || 'Send your activation code to obtain a license key, then paste it below to activate this panel.' }}</div>
        <div style="margin-top:18px" v-if="activationCode">
          <label style="display:block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);margin-bottom:7px">{{ tr('activation.yourCode') || 'Activation code' }}</label>
          <div style="display:flex;align-items:center;gap:8px;height:44px;border:1px solid var(--border-strong);background:var(--panel-2);border-radius:11px;padding:0 14px;font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--text-2)">{{ activationCode }}<button @click="copy" style="margin-left:auto;border:none;background:transparent;color:var(--text-3);cursor:pointer;display:flex" :title="copied ? (tr('activation.copied') || 'Copied') : (tr('activation.copy') || 'Copy')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button></div>
        </div>
        <div style="margin-top:14px">
          <label style="display:block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);margin-bottom:7px">{{ tr('activation.licenseKey') || 'License key' }}</label>
          <textarea v-model="licenseKey" :placeholder="tr('activation.pasteKey') || 'Paste your license key here'" class="d2-gate-ta" style="width:100%;min-height:84px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:11px;padding:11px 14px;font-family:'JetBrains Mono',monospace;font-size:12px;outline:none"></textarea>
        </div>
        <div v-if="error" style="color:var(--red);font-size:12.5px;margin-top:10px">{{ error }}</div>
        <div v-if="success" style="color:var(--green);font-size:12.5px;margin-top:10px">{{ success }}</div>
        <button @click="activate" :disabled="activating || !licenseKey.trim()" class="d2-gate-btn" style="display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:46px;border:none;background:var(--accent);color:#fff;border-radius:11px;font:inherit;font-size:14px;font-weight:600;cursor:pointer;margin-top:18px;box-shadow:0 2px 8px var(--accent-ring)">
          <span v-if="activating" style="width:16px;height:16px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite"></span>
          {{ tr('activation.activate') || 'Activate' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../../api'

const { t } = useI18n({ useScope: 'global' })
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const activationCode = ref('')
const licenseKey = ref('')
const activating = ref(false)
const error = ref('')
const success = ref('')
const copied = ref(false)

async function load() { try { const r = await api.get('/system/activation'); activationCode.value = r.data.activation_code || '' } catch (_) {} }
async function copy() { try { await navigator.clipboard.writeText(activationCode.value); copied.value = true; setTimeout(() => copied.value = false, 2000) } catch (_) {} }
async function activate() {
  error.value = ''; success.value = ''; activating.value = true
  try { await api.post('/system/license', { license_key: licenseKey.value.trim() }); success.value = tr('activation.activated') || 'License activated! Redirecting…'; setTimeout(() => { window.location.href = '/' }, 1500) }
  catch (e) { error.value = e.response?.data?.detail || (tr('activation.failed') || 'Activation failed. Check your license key.') } finally { activating.value = false }
}
onMounted(load)
</script>

<style scoped>
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
.d2-gate-ta:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-gate-btn:hover:not(:disabled) { background: var(--accent-2); }
.d2-gate-btn:disabled { opacity: .55; cursor: default; }
</style>
