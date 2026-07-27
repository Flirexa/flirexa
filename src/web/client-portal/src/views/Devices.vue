<template>
  <div class="fx-page">
    <div class="fx-page-head">
      <div>
        <h1 class="fx-page-title">{{ $t('devices.title') || 'My Devices' }}</h1>
        <p class="fx-page-sub">
          {{ $t('devices.sub') || 'Each device can hop between server regions without re-installing. Switch the active region here — your VPN app just keeps using the same config.' }}
        </p>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap">
        <button class="fx-btn fx-btn-secondary" @click="loadSlots" :disabled="loading">
          <FxIcon name="refresh" :size="14" />
          {{ loading ? $t('common.loading') : $t('common.refresh') }}
        </button>
        <button class="fx-btn fx-btn-primary"
                :disabled="atLimit || creating"
                @click="showCreate = true">
          <FxIcon name="plus" :size="14" />
          {{ $t('devices.add') || 'Add device' }}
        </button>
      </div>
    </div>

    <!-- At-limit notice — uses the same overlimit card style as the dashboard
         for a consistent feel across pages. -->
    <div v-if="atLimit" class="fx-overlimit-card">
      <div class="fx-overlimit-icon">
        <FxIcon name="warning" :size="18" />
      </div>
      <div class="fx-overlimit-body">
        <div class="fx-overlimit-title">
          {{ $t('devices.atLimit', { used: slots.length, max: maxDevices }) }}
        </div>
        <p class="fx-overlimit-hint">{{ $t('devices.atLimitHint') }}</p>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && !slots.length" class="fx-card" style="padding:24px; text-align:center">
      <div class="fx-empty">
        <div class="fx-empty-icon"><FxIcon name="phone" :size="22" /></div>
        <h3 class="fx-empty-title">{{ $t('devices.emptyTitle') || 'No devices yet' }}</h3>
        <p class="fx-empty-sub">{{ $t('devices.emptySub') ||
          'Add your first device to get a VPN config you can switch between regions.' }}</p>
        <button class="fx-btn fx-btn-primary"
                :disabled="creating || !hasActiveSub"
                @click="showCreate = true">
          <FxIcon name="plus" :size="14" />
          {{ $t('devices.add') || 'Add device' }}
        </button>
      </div>
    </div>

    <!-- Slot cards -->
    <div v-for="slot in slots" :key="slot.id" class="fx-card fx-slot-card">
      <div class="fx-slot-head">
        <div class="fx-slot-label-wrap">
          <input v-if="editingLabelId === slot.id"
                 v-model="editingLabel"
                 @blur="saveLabel(slot)"
                 @keyup.enter="saveLabel(slot)"
                 @keyup.esc="editingLabelId = null"
                 class="fx-slot-label-input"
                 ref="labelInput"
                 maxlength="64" />
          <h3 v-else class="fx-slot-label" @click="startRename(slot)">
            {{ slot.label }}
            <FxIcon name="edit" :size="13" style="opacity:0.6; margin-left:4px" />
          </h3>
        </div>
        <div class="fx-slot-actions">
          <!-- Release-device button. Only visible when the slot has
               been claimed by a phone via the Option B device-bind.
               One tap clears the bind so a replacement phone can take
               the slot on its next connect. -->
          <button v-if="slot.is_bound"
                  class="fx-icon-btn-sm"
                  :title="$t('devices.releaseDevice') || 'Release device — let a new phone claim this slot'"
                  @click="doReleaseDevice(slot)"
                  :disabled="releasing === slot.id">
            <FxIcon name="unlink" :size="14" />
          </button>
          <button class="fx-icon-btn-sm"
                  :title="$t('devices.delete') || 'Delete device'"
                  @click="confirmDelete(slot)">
            <FxIcon name="trash" :size="14" />
          </button>
        </div>
      </div>

      <!-- Server picker -->
      <div class="fx-slot-section">
        <div class="fx-slot-section-title">
          {{ $t('devices.activeServer') }}
          <FxHelp :text="$t('devices.activeServerHelp')" />
        </div>
        <div class="fx-slot-server-grid">
          <button v-for="srv in slot.servers"
                  :key="srv.server_id"
                  class="fx-slot-server-btn"
                  :class="{
                    'active': srv.is_active,
                    'disabled': switching === slot.id,
                    'fastest': fastestServerId === srv.server_id && !srv.is_active,
                  }"
                  :disabled="switching === slot.id || srv.is_active"
                  @click="switchServer(slot, srv.server_id)">
            <div class="fx-slot-server-name">
              {{ srv.server_display_name || srv.server_name }}
              <span v-if="fastestServerId === srv.server_id && pingResults[srv.server_id]?.rtt_ms != null"
                    class="fx-badge fx-badge-accent" style="margin-left:6px; font-size:10px">
                {{ $t('devices.fastest') }}
              </span>
            </div>
            <div class="fx-slot-server-meta">
              <span v-if="srv.is_active" class="fx-badge fx-badge-success">
                {{ $t('devices.active') }}
              </span>
              <span v-else class="fx-badge fx-badge-neutral">
                {{ $t('devices.standby') }}
              </span>
              <span class="fx-slot-server-ping" :class="pingClass(srv.server_id)">
                <template v-if="pingResults[srv.server_id]?.rtt_ms != null">
                  {{ pingResults[srv.server_id].rtt_ms }} ms
                </template>
                <template v-else-if="pingResults[srv.server_id]?.error">
                  —
                </template>
                <template v-else>…</template>
              </span>
              <span style="font-family:var(--mono); font-size:11px; color:var(--text-3); margin-left:6px">
                {{ stripCidr(srv.ipv4) }}
              </span>
            </div>
          </button>
        </div>
        <div v-if="cooldownText[slot.id]" class="fx-slot-cooldown">
          {{ cooldownText[slot.id] }}
        </div>
      </div>

      <!-- Config download row -->
      <div class="fx-slot-section" v-if="features.config_download">
        <div class="fx-slot-section-title">
          {{ $t('devices.configs') }}
          <FxHelp :text="$t('devices.configsManualHelp')" />
        </div>
        <p class="fx-slot-config-hint">
          {{ $t('devices.configsHint') }}
        </p>
        <div class="fx-slot-config-grid">
          <button v-for="srv in slot.servers"
                  :key="'cfg-'+srv.server_id"
                  class="fx-btn fx-btn-secondary fx-btn-sm"
                  @click="downloadConfig(slot, srv)">
            <FxIcon name="download" :size="13" />
            {{ srv.server_display_name || srv.server_name }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create slot modal -->
    <div v-if="showCreate" class="fx-modal-overlay" @click.self="showCreate = false">
      <div class="fx-modal-box">
        <div class="fx-modal-header">
          <h3>{{ $t('devices.addTitle') || 'Add device' }}</h3>
          <button class="fx-icon-btn-sm" @click="showCreate = false">
            <FxIcon name="close" :size="14" />
          </button>
        </div>
        <div class="fx-modal-body">
          <label class="fx-form-label">{{ $t('devices.labelLabel') || 'Device name' }}</label>
          <input v-model="newLabel" class="fx-input" maxlength="64"
                 :placeholder="$t('devices.labelPlaceholder') || 'Phone, Laptop, …'" />
          <label class="fx-form-label" style="margin-top:14px">
            {{ $t('devices.initialServerLabel') || 'Start in region (optional)' }}
          </label>
          <select v-model="newInitialServer" class="fx-input">
            <option :value="null">{{ $t('devices.defaultServer') || 'Default' }}</option>
            <option v-for="s in availableServers" :key="s.id" :value="s.id">
              {{ s.display_name || s.location || s.name }}
            </option>
          </select>
        </div>
        <div class="fx-modal-footer">
          <button class="fx-btn fx-btn-ghost" @click="showCreate = false"
                  :disabled="creating">
            {{ $t('common.cancel') }}
          </button>
          <button class="fx-btn fx-btn-primary"
                  :disabled="creating || !newLabel.trim()"
                  @click="doCreate">
            <FxIcon v-if="creating" name="refresh" :size="13" class="fx-spin" />
            {{ creating ? $t('common.loading') : $t('devices.add') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirm delete (password-gated to prevent accidental removal) -->
    <div v-if="showDeleteConfirm" class="fx-modal-overlay" @click.self="cancelDeleteConfirm">
      <div class="fx-modal-box">
        <div class="fx-modal-header">
          <h3>{{ $t('dash.deletePasswordTitle') }}</h3>
          <button class="fx-icon-btn-sm" @click="cancelDeleteConfirm">
            <FxIcon name="close" :size="14" />
          </button>
        </div>
        <div class="fx-modal-body">
          <p style="font-size:13px; color:var(--text-2); margin:0 0 12px">
            {{ $t('dash.deletePasswordHint', { name: deleteTargetName }) }}
          </p>
          <label class="fx-form-label">{{ $t('dash.deletePasswordPlaceholder') }}</label>
          <input class="fx-input" type="password" v-model="deletePassword"
                 :placeholder="$t('dash.deletePasswordPlaceholder')"
                 @keyup.enter="confirmDeleteWithPassword" />
          <div v-if="deleteError" style="color:var(--danger); font-size:12px; margin-top:10px">{{ deleteError }}</div>
        </div>
        <div class="fx-modal-footer">
          <button class="fx-btn fx-btn-ghost" @click="cancelDeleteConfirm">{{ $t('common.cancel') }}</button>
          <button class="fx-btn fx-btn-danger" @click="confirmDeleteWithPassword"
                  :disabled="deleting || !deletePassword">
            {{ deleting ? $t('common.loading') : $t('dash.deletePasswordSubmit') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Toasts. Errors collapse to a one-line "Error - tap to expand"
         pill so a 200-char stack trace doesn't take over the corner of
         the screen. Tapping toggles the full text + a Copy button.
         Success / info toasts stay verbatim — they're already short. -->
    <div class="fx-toast-wrap">
      <transition-group name="fx-toast-fade">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="fx-toast"
          :class="[t.type, { 'is-expanded': t.expanded }]"
          @click="t.type === 'error' && (t.expanded = !t.expanded)"
          :role="t.type === 'error' ? 'button' : undefined"
          :tabindex="t.type === 'error' ? 0 : undefined"
        >
          <template v-if="t.type === 'error' && !t.expanded">
            <span class="fx-toast-headline">
              {{ $t('common.errorTapToExpand') || 'Error — tap to expand' }}
            </span>
          </template>
          <template v-else-if="t.type === 'error' && t.expanded">
            <div class="fx-toast-body">{{ t.message }}</div>
            <button
              class="fx-toast-copy"
              @click.stop="copyToastMessage(t)"
              :title="$t('common.copy') || 'Copy'"
            >
              {{ t.copied ? ($t('common.copied') || 'Copied ✓') : ($t('common.copy') || 'Copy') }}
            </button>
          </template>
          <template v-else>
            {{ t.message }}
          </template>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { portalApi } from '../api/index.js'
import FxIcon from '../components/FxIcon.vue'
import FxHelp from '../components/FxHelp.vue'
import { useEscapeClose } from '../composables/useEscapeClose.js'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const creating = ref(false)
const switching = ref(null)  // slot_id currently being switched
const releasing = ref(null)  // slot_id currently being released from its device-bind
const slots = ref([])
const subscription = ref({})
// Per-operator portal gates; default ON (fail open). Backend 403 is the real gate.
const features = ref({ config_download: true, qr: true })
const servers = ref([])

const showCreate = ref(false)
const newLabel = ref('Phone')
const newInitialServer = ref(null)

const editingLabelId = ref(null)
const editingLabel = ref('')
const labelInput = ref(null)

const toasts = ref([])
const cooldownText = ref({})  // slot_id -> human countdown string

// Latency probe — portal proxies a HEAD/GET to each server's node agent
// and we display the RTT next to the server card. The number is
// panel→server, not user→server (browsers can't fire HTTPS→HTTP from a
// secure portal page), but it's a useful relative health signal and
// lights up "Fastest" on the row with the lowest RTT.
const pingResults = ref({})  // server_id -> { rtt_ms, error?, status? }
const fastestServerId = computed(() => {
  let best = null
  for (const [sid, r] of Object.entries(pingResults.value)) {
    if (r?.rtt_ms == null) continue
    if (best == null || r.rtt_ms < pingResults.value[best].rtt_ms) {
      best = Number(sid)
    }
  }
  return best
})
function pingClass(serverId) {
  const r = pingResults.value[serverId]
  if (!r) return 'unknown'
  if (r.rtt_ms == null) return 'offline'
  if (r.rtt_ms <= 60) return 'fast'
  if (r.rtt_ms <= 180) return 'mid'
  return 'slow'
}
async function probeAllServers() {
  const allIds = new Set()
  for (const slot of slots.value) {
    for (const srv of slot.servers || []) allIds.add(srv.server_id)
  }
  await Promise.all([...allIds].map(async (sid) => {
    try {
      const { data } = await portalApi.probeServer(sid)
      pingResults.value = { ...pingResults.value, [sid]: data }
    } catch {
      pingResults.value = { ...pingResults.value, [sid]: { rtt_ms: null, error: 'probe_failed' } }
    }
  }))
}

// Smart Subscription Link removed from UI — the backend endpoint
// (/sub/{token}/slot/{id}) is kept for advanced users / custom apps,
// but most mainstream WG clients don't poll subscription URLs, so the
// "switch on portal → app auto-updates" promise was misleading for the
// average customer. Will be revisited together with a custom client app.

// Password-gated slot delete — same pattern as the dashboard, prevents
// an accidental tap from wiping a working VPN config.
const showDeleteConfirm = ref(false)

// Esc dismisses modals. The delete-confirm uses its own cancel handler
// because it gates on `deleting` to avoid aborting a real in-flight
// request.
useEscapeClose(showCreate, () => { if (!creating.value) showCreate.value = false })
useEscapeClose(showDeleteConfirm, () => cancelDeleteConfirm())
const deleteTarget = ref(null)
const deletePassword = ref('')
const deleteError = ref(null)
const deleting = ref(false)
const deleteTargetName = computed(() => deleteTarget.value?.label || '')

let toastId = 0
const toast = (message, type = 'info') => {
  const id = ++toastId
  // Errors are collapsed by default with a click-to-expand affordance
  // (operator request — full stack-trace toasts felt scary).
  // Success/info toasts stay verbatim. We also give errors more time
  // on screen because the user needs to read + (maybe) expand them.
  toasts.value.push({
    id,
    message: String(message ?? ''),
    type,
    expanded: false,
    copied: false,
  })
  const ttl = type === 'error' ? 8000 : 3500
  setTimeout(() => {
    const i = toasts.value.findIndex(x => x.id === id)
    if (i >= 0) toasts.value.splice(i, 1)
  }, ttl)
}

async function copyToastMessage(t) {
  try {
    await navigator.clipboard.writeText(t.message || '')
    t.copied = true
    setTimeout(() => { t.copied = false }, 1500)
  } catch { /* clipboard blocked — silently ignore */ }
}

const hasActiveSub = computed(() => subscription.value.status === 'active')
const maxDevices = computed(() => subscription.value.max_devices || 1)
const atLimit = computed(() => slots.value.length >= maxDevices.value)

const availableServers = computed(() => servers.value.filter(s => s.customer_visible !== false))

const stripCidr = (ip) => (ip || '').split('/')[0] || '—'

const loadSlots = async () => {
  loading.value = true
  try {
    const [slotsRes, subRes, srvRes] = await Promise.all([
      portalApi.listSlots(),
      portalApi.getSubscription(),
      portalApi.getServers().catch(() => ({ data: [] })),
    ])
    slots.value = slotsRes.data || []
    subscription.value = subRes.data || {}
    servers.value = srvRes.data || []
    // Fire-and-forget RTT probe — UI does not wait for it. Failures
    // simply leave the chips in "…" state, which is fine.
    probeAllServers()
  } catch (e) {
    if (e.response?.status === 401) router.push('/login')
    else toast(e.response?.data?.detail || e.message, 'error')
  } finally {
    loading.value = false
  }
}

const doReleaseDevice = async (slot) => {
  // Clear the slot's device-bind so a replacement phone can claim it
  // on its next connect. We don't password-gate this the way delete
  // does — release is recoverable (just connect again from any phone
  // to re-bind), so the friction would be disproportionate. The
  // backend endpoint returns the refreshed slot row so we can
  // patch it back into `slots` without a full reload.
  if (releasing.value === slot.id) return
  releasing.value = slot.id
  try {
    const { data } = await portalApi.releaseSlotDevice(slot.id)
    const idx = slots.value.findIndex(s => s.id === slot.id)
    if (idx >= 0) slots.value.splice(idx, 1, data)
    toast(t('devices.released') || 'Device released. The next phone to connect will be registered to this slot.', 'success')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : detail?.message || e.message || 'Error'
    toast(msg, 'error')
  } finally {
    releasing.value = null
  }
}

const doCreate = async () => {
  creating.value = true
  try {
    await portalApi.createSlot({
      label: newLabel.value.trim() || 'Device',
      initial_server_id: newInitialServer.value,
    })
    showCreate.value = false
    newLabel.value = 'Phone'
    newInitialServer.value = null
    await loadSlots()
    toast(t('devices.created') || 'Device added', 'success')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : detail?.message || e.message || 'Error'
    toast(msg, 'error')
  } finally {
    creating.value = false
  }
}

const switchServer = async (slot, serverId) => {
  switching.value = slot.id
  try {
    const { data } = await portalApi.switchSlotServer(slot.id, serverId)
    // Replace this slot in the list with the fresh server-state.
    const idx = slots.value.findIndex(s => s.id === slot.id)
    if (idx >= 0) slots.value.splice(idx, 1, data)
    toast(t('devices.switched'), 'success')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : detail?.message || e.message
    // Backend's cooldown reply is HTTP 429 with the wait time baked into
    // the message ("Please wait 28s …"). Pull the number out and run a
    // countdown chip under the server picker so the user sees how long
    // until they can switch again instead of getting a generic toast
    // and wondering why their next click bounces.
    if (e.response?.status === 429 && typeof msg === 'string') {
      const m = msg.match(/(\d+)\s*s/)
      const secs = m ? parseInt(m[1], 10) : 30
      startCooldown(slot.id, secs)
    }
    toast(msg || 'Error', 'error')
  } finally {
    switching.value = null
  }
}

// Per-slot interval handles so a second startCooldown for the same
// slot replaces the old timer instead of stacking, and onUnmounted
// can clear everything. Without it, fast region-switching on the
// same device left N parallel 1s tickers running, and a route change
// before any of them expired leaked them all.
const _cooldownIntervals = new Map()  // slotId -> interval handle

function startCooldown(slotId, seconds) {
  // Replace any existing timer for this slot first.
  const prev = _cooldownIntervals.get(slotId)
  if (prev) clearInterval(prev)

  let remaining = seconds
  cooldownText.value = {
    ...cooldownText.value,
    [slotId]: t('devices.cooldown', { seconds: remaining }),
  }
  const id = setInterval(() => {
    remaining -= 1
    if (remaining <= 0) {
      clearInterval(id)
      _cooldownIntervals.delete(slotId)
      const next = { ...cooldownText.value }
      delete next[slotId]
      cooldownText.value = next
      return
    }
    cooldownText.value = {
      ...cooldownText.value,
      [slotId]: t('devices.cooldown', { seconds: remaining }),
    }
  }, 1000)
  _cooldownIntervals.set(slotId, id)
}

const downloadConfig = async (slot, srv) => {
  try {
    const { data } = await portalApi.getSlotServerConfig(slot.id, srv.server_id)
    // Server returns either a string body or { config: "..." } depending on
    // how admin_api renders it — handle both.
    const body = typeof data === 'string' ? data : (data.config || '')
    if (!body) {
      toast(t('devices.configError') || 'No config returned', 'error')
      return
    }
    const blob = new Blob([body], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // AmneziaWG / WireGuard mobile imports the config as a tunnel whose
    // name maps to a Linux TUN interface, capped at 15 characters. A long
    // "{label}-{server}.conf" (e.g. "phone-TexasUSA-AWG-Residential.conf")
    // gets rejected with "invalid profile" on import. Use just the server
    // identifier, truncated to 15 chars, dropping the label prefix.
    const rawName = (srv.server_display_name || srv.server_name || 'vpn')
      .replace(/[^a-zA-Z0-9_-]+/g, '_')
    a.download = `${rawName.slice(0, 15)}.conf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    toast(e.response?.data?.detail || e.message, 'error')
  }
}

const startRename = async (slot) => {
  editingLabelId.value = slot.id
  editingLabel.value = slot.label
  await nextTick()
  if (labelInput.value && labelInput.value[0]) labelInput.value[0].focus()
}

const saveLabel = async (slot) => {
  const label = (editingLabel.value || '').trim()
  editingLabelId.value = null
  if (!label || label === slot.label) return
  try {
    const { data } = await portalApi.renameSlot(slot.id, label)
    const idx = slots.value.findIndex(s => s.id === slot.id)
    if (idx >= 0) slots.value.splice(idx, 1, data)
  } catch (e) {
    toast(e.response?.data?.detail || e.message, 'error')
  }
}

const confirmDelete = (slot) => {
  deleteTarget.value = slot
  deletePassword.value = ''
  deleteError.value = null
  showDeleteConfirm.value = true
}
const cancelDeleteConfirm = () => {
  if (deleting.value) return
  showDeleteConfirm.value = false
  deleteTarget.value = null
  deletePassword.value = ''
  deleteError.value = null
}
const confirmDeleteWithPassword = async () => {
  if (!deleteTarget.value || !deletePassword.value || deleting.value) return
  deleting.value = true
  deleteError.value = null
  try {
    await portalApi.verifyPassword(deletePassword.value)
  } catch (verifyErr) {
    if (verifyErr.response?.status === 400 || verifyErr.response?.status === 401) {
      deleteError.value = t('dash.deletePasswordWrong')
    } else {
      deleteError.value = (typeof verifyErr.response?.data?.detail === 'string'
        ? verifyErr.response.data.detail
        : verifyErr.message) || t('common.error')
    }
    deleting.value = false
    return
  }
  try {
    await portalApi.deleteSlot(deleteTarget.value.id)
    slots.value = slots.value.filter(s => s.id !== deleteTarget.value.id)
    showDeleteConfirm.value = false
    deleteTarget.value = null
    deletePassword.value = ''
    toast(t('devices.deleted') || 'Device deleted', 'success')
  } catch (e) {
    deleteError.value = e.response?.data?.detail || e.message
  } finally {
    deleting.value = false
  }
}

async function loadFeatures() {
  try {
    const { data } = await portalApi.getFeatures()
    if (data && data.features) features.value = { ...features.value, ...data.features }
  } catch { /* fail open: keep defaults */ }
}
onMounted(() => { loadSlots(); loadFeatures() })
onUnmounted(() => {
  for (const id of _cooldownIntervals.values()) clearInterval(id)
  _cooldownIntervals.clear()
})
</script>

<style scoped>
.fx-slot-card {
  padding: 16px;
  margin-bottom: 12px;
}
.fx-slot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.fx-slot-label {
  margin: 0;
  font-size: 16px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.fx-slot-label-input {
  font-size: 16px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-2);
  color: var(--text);
}
.fx-slot-section {
  margin-top: 12px;
}
.fx-slot-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
.fx-slot-server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.fx-slot-server-btn {
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-2);
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}
.fx-slot-server-btn:hover:not(:disabled) {
  border-color: var(--accent);
}
.fx-slot-server-btn.active {
  border-color: var(--success);
  background: color-mix(in srgb, var(--success) 10%, var(--bg-2));
  cursor: default;
}
.fx-slot-server-btn.fastest {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: color-mix(in srgb, var(--accent) 6%, var(--bg-2));
}
.fx-slot-server-ping {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
  margin-left: 8px;
  height: 18px;
  min-width: 44px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  line-height: 1;
  letter-spacing: 0.02em;
  background: color-mix(in oklab, var(--text) 6%, transparent);
  color: var(--text-3);
  white-space: nowrap;
}
.fx-slot-server-ping.fast {
  background: color-mix(in oklab, var(--success) 18%, transparent);
  color: var(--success);
}
.fx-slot-server-ping.mid {
  background: color-mix(in oklab, var(--warning) 18%, transparent);
  color: var(--warning);
}
.fx-slot-server-ping.slow {
  background: color-mix(in oklab, var(--danger) 18%, transparent);
  color: var(--danger);
}
.fx-slot-server-ping.offline {
  background: color-mix(in oklab, var(--text-3) 14%, transparent);
  color: var(--text-3);
}
.fx-slot-server-btn.disabled {
  opacity: 0.6;
  cursor: progress;
}
.fx-slot-server-name {
  font-weight: 600;
  margin-bottom: 4px;
}
.fx-slot-server-meta {
  display: flex;
  align-items: center;
}
.fx-slot-cooldown {
  margin-top: 6px;
  font-size: 12px;
  color: var(--warn);
}
.fx-slot-config-hint {
  font-size: 12px;
  color: var(--text-3);
  margin: 0 0 10px;
}
.fx-slot-config-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.fx-form-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-3);
  margin-bottom: 4px;
}

/* Over-limit card — same shape as dashboard's so both pages feel
   consistent when the customer is past their plan's slot count. */
.fx-overlimit-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid color-mix(in oklab, var(--warning) 28%, var(--border));
  border-left: 3px solid var(--warning);
  border-radius: var(--r-md, 10px);
  background: linear-gradient(
    180deg,
    color-mix(in oklab, var(--warning) 10%, var(--bg-card, var(--bg-2))) 0%,
    var(--bg-card, var(--bg-2)) 100%
  );
}
.fx-overlimit-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--warning) 18%, transparent);
  color: var(--warning);
}
.fx-overlimit-body { flex: 1; min-width: 0; }
.fx-overlimit-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.fx-overlimit-hint {
  font-size: 12.5px;
  color: var(--text-2);
  margin: 0;
  line-height: 1.5;
}
</style>
