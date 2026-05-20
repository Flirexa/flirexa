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
          {{ $t('devices.activeServer') || 'Active server' }}
        </div>
        <div class="fx-slot-server-grid">
          <button v-for="srv in slot.servers"
                  :key="srv.server_id"
                  class="fx-slot-server-btn"
                  :class="{
                    'active': srv.is_active,
                    'disabled': switching === slot.id,
                  }"
                  :disabled="switching === slot.id || srv.is_active"
                  @click="switchServer(slot, srv.server_id)">
            <div class="fx-slot-server-name">
              {{ srv.server_display_name || srv.server_name }}
            </div>
            <div class="fx-slot-server-meta">
              <span v-if="srv.is_active" class="fx-badge fx-badge-success">
                {{ $t('devices.active') || 'Active' }}
              </span>
              <span v-else class="fx-badge fx-badge-neutral">
                {{ $t('devices.standby') || 'Standby' }}
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
      <div class="fx-slot-section">
        <div class="fx-slot-section-title">
          {{ $t('devices.configs') || 'Download config' }}
        </div>
        <p class="fx-slot-config-hint">
          {{ $t('devices.configsHint') ||
            "Import all regions into your VPN app once. Only the active region accepts traffic — switching above is enough; you don't need to re-import." }}
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
      <div class="fx-modal">
        <div class="fx-modal-head">
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
        <div class="fx-modal-foot">
          <button class="fx-btn fx-btn-ghost" @click="showCreate = false">
            {{ $t('common.cancel') }}
          </button>
          <button class="fx-btn fx-btn-primary"
                  :disabled="creating || !newLabel.trim()"
                  @click="doCreate">
            {{ creating ? $t('common.loading') : ($t('devices.add') || 'Add device') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirm delete (password-gated to prevent accidental removal) -->
    <div v-if="showDeleteConfirm" class="fx-modal-overlay" @click.self="cancelDeleteConfirm">
      <div class="fx-modal">
        <div class="fx-modal-head">
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
        <div class="fx-modal-foot">
          <button class="fx-btn fx-btn-ghost" @click="cancelDeleteConfirm">{{ $t('common.cancel') }}</button>
          <button class="fx-btn fx-btn-danger" @click="confirmDeleteWithPassword"
                  :disabled="deleting || !deletePassword">
            {{ deleting ? $t('common.loading') : $t('dash.deletePasswordSubmit') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Toasts -->
    <div class="fx-toast-wrap">
      <transition-group name="fx-toast-fade">
        <div v-for="t in toasts" :key="t.id" class="fx-toast" :class="t.type">{{ t.message }}</div>
      </transition-group>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { portalApi } from '../api/index.js'
import FxIcon from '../components/FxIcon.vue'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const creating = ref(false)
const switching = ref(null)  // slot_id currently being switched
const slots = ref([])
const subscription = ref({})
const servers = ref([])

const showCreate = ref(false)
const newLabel = ref('Phone')
const newInitialServer = ref(null)

const editingLabelId = ref(null)
const editingLabel = ref('')
const labelInput = ref(null)

const toasts = ref([])
const cooldownText = ref({})  // slot_id -> human countdown string

// Password-gated slot delete — same pattern as the dashboard, prevents
// an accidental tap from wiping a working VPN config.
const showDeleteConfirm = ref(false)
const deleteTarget = ref(null)
const deletePassword = ref('')
const deleteError = ref(null)
const deleting = ref(false)
const deleteTargetName = computed(() => deleteTarget.value?.label || '')

let toastId = 0
const toast = (message, type = 'info') => {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    const i = toasts.value.findIndex(x => x.id === id)
    if (i >= 0) toasts.value.splice(i, 1)
  }, 3500)
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
  } catch (e) {
    if (e.response?.status === 401) router.push('/login')
    else toast(e.response?.data?.detail || e.message, 'error')
  } finally {
    loading.value = false
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
    toast(t('devices.switched') || 'Region switched', 'success')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : detail?.message || e.message
    toast(msg || 'Error', 'error')
  } finally {
    switching.value = null
  }
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
  // Verify password by replaying login — stateless JWT means the new
  // token is harmless. Avoids adding a one-off verify endpoint.
  let userEmail = ''
  try {
    const u = JSON.parse(localStorage.getItem('client_user') || '{}')
    userEmail = u.email || ''
  } catch { /* ignore */ }
  if (!userEmail) {
    deleteError.value = t('common.error')
    deleting.value = false
    return
  }
  try {
    await portalApi.login({ email: userEmail, password: deletePassword.value })
  } catch (verifyErr) {
    if (verifyErr.response?.status === 400 || verifyErr.response?.status === 401) {
      deleteError.value = t('dash.deletePasswordWrong')
      deleting.value = false
      return
    }
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

onMounted(loadSlots)
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
