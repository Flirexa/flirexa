<template>
  <div class="fx-page fx-simple-devices">
    <div class="fx-page-head fx-simple-page-head">
      <div>
        <h1 class="fx-page-title">{{ $t('simpleDevices.title') }}</h1>
        <p class="fx-page-sub">{{ $t('simpleDevices.subtitle') }}</p>
      </div>
      <button class="fx-btn fx-btn-primary" :disabled="atLimit || creating" @click="openCreate">
        <FxIcon name="plus" :size="15" />
        {{ $t('simpleDevices.add') }}
      </button>
    </div>

    <div v-if="atLimit" class="fx-simple-notice">
      <FxIcon name="info" :size="17" />
      <div>
        <strong>{{ $t('simpleDevices.limitTitle') }}</strong>
        <span>{{ $t('simpleDevices.limitHint', { used: slots.length, max: maxDevices }) }}</span>
      </div>
      <router-link to="/plans">{{ $t('simpleDevices.viewPlans') }}</router-link>
    </div>

    <div v-if="loading" class="fx-simple-grid">
      <div v-for="n in 2" :key="n" class="fx-card fx-simple-skeleton" />
    </div>

    <div v-else-if="!slots.length" class="fx-card fx-simple-empty">
      <span class="fx-simple-empty-icon"><FxIcon name="phone" :size="25" /></span>
      <h2>{{ $t('simpleDevices.emptyTitle') }}</h2>
      <p>{{ $t('simpleDevices.emptyText') }}</p>
      <button class="fx-btn fx-btn-primary" @click="openCreate">
        <FxIcon name="plus" :size="15" /> {{ $t('simpleDevices.addFirst') }}
      </button>
    </div>

    <div v-else class="fx-simple-grid">
      <article v-for="slot in slots" :key="slot.id" class="fx-card fx-simple-card">
        <div class="fx-simple-card-head">
          <span class="fx-simple-device-icon"><FxIcon name="phone" :size="20" /></span>
          <div class="fx-simple-device-copy">
            <input
              v-if="renamingId === slot.id"
              v-model="renameValue"
              class="fx-input fx-simple-rename"
              maxlength="64"
              @keyup.enter="saveRename(slot)"
              @keyup.esc="renamingId = null"
              @blur="saveRename(slot)"
            />
            <template v-else>
              <h2>{{ slot.label }}</h2>
              <span>{{ locationName(slot) }}</span>
            </template>
          </div>
          <button class="fx-simple-more" :aria-expanded="menuId === slot.id" @click="menuId = menuId === slot.id ? null : slot.id">
            <span></span><span></span><span></span>
          </button>
          <div v-if="menuId === slot.id" class="fx-simple-menu">
            <button @click="startRename(slot)"><FxIcon name="edit" :size="14" />{{ $t('simpleDevices.rename') }}</button>
            <button v-if="slot.is_bound" @click="releaseDevice(slot)"><FxIcon name="unlink" :size="14" />{{ $t('simpleDevices.useNewDevice') }}</button>
            <button class="danger" @click="openDelete(slot)"><FxIcon name="trash" :size="14" />{{ $t('common.delete') }}</button>
          </div>
        </div>

        <div class="fx-simple-location">
          <label :for="`location-${slot.id}`">{{ $t('simpleDevices.location') }}</label>
          <div class="fx-simple-select-wrap">
            <CountryFlag
              :code="activeServer(slot)?.country_code"
              :location="activeServer(slot)?.server_location"
              :name="activeServer(slot)?.server_display_name || activeServer(slot)?.server_name"
              :size="28"
            />
            <select
              :id="`location-${slot.id}`"
              :value="slot.active_server_id || ''"
              :disabled="switchingId === slot.id"
              @change="changeLocation(slot, $event.target.value)"
            >
              <option v-for="server in slot.servers" :key="server.server_id" :value="server.server_id">
                {{ server.server_display_name || server.server_name }}
              </option>
            </select>
            <FxIcon name="chevronDown" :size="14" />
          </div>
          <small v-if="switchingId === slot.id">{{ $t('simpleDevices.changingLocation') }}</small>
          <small v-else>{{ $t('simpleDevices.locationHint') }}</small>
        </div>

        <div v-if="features.dns_protection && dnsStates[slot.id]?.enabled" class="fx-simple-protection">
          <label :for="`dns-${slot.id}`">
            <span><FxIcon name="shield" :size="15" />{{ $t('simpleDevices.protection') }}</span>
            <small v-if="dnsStates[slot.id]?.forced">{{ $t('simpleDevices.managed') }}</small>
          </label>
          <select
            :id="`dns-${slot.id}`"
            :value="dnsStates[slot.id]?.effective_profile_id || ''"
            :disabled="dnsSaving === slot.id || dnsStates[slot.id]?.forced || !dnsStates[slot.id]?.customer_choice_enabled"
            @change="changeDns(slot, $event.target.value)"
          >
            <option v-for="profile in dnsStates[slot.id]?.profiles || []" :key="profile.id" :value="profile.id">{{ profile.name }}</option>
          </select>
        </div>

        <div class="fx-simple-card-actions">
          <button class="fx-btn fx-btn-primary" @click="openSetup(slot)">
            <FxIcon name="qr" :size="15" /> {{ $t('simpleDevices.setup') }}
          </button>
          <span class="fx-simple-ready"><i></i>{{ $t('simpleDevices.ready') }}</span>
        </div>
      </article>
    </div>

    <div v-if="showCreate" class="fx-modal-overlay" @click.self="closeCreate">
      <div class="fx-modal-box fx-simple-modal">
        <div class="fx-modal-header">
          <div>
            <h3>{{ $t('simpleDevices.addTitle') }}</h3>
            <p>{{ $t('simpleDevices.addSubtitle') }}</p>
          </div>
          <button class="fx-icon-btn-sm" @click="closeCreate"><FxIcon name="close" :size="15" /></button>
        </div>
        <div class="fx-modal-body">
          <label class="fx-form-label">{{ $t('simpleDevices.deviceName') }}</label>
          <input v-model="newLabel" class="fx-input" maxlength="64" :placeholder="$t('simpleDevices.devicePlaceholder')" />
          <label class="fx-form-label fx-simple-field-gap">{{ $t('simpleDevices.chooseLocation') }}</label>
          <div class="fx-simple-location-list">
            <button
              v-for="server in availableServers"
              :key="server.id"
              type="button"
              :class="{ active: Number(newServerId) === Number(server.id) }"
              @click="newServerId = server.id"
            >
              <CountryFlag :code="server.country_code" :location="server.location" :name="server.name" :size="34" />
              <span class="fx-simple-location-copy">
                <strong>{{ server.location || server.name }}</strong>
                <small>{{ protocolLabel(server.server_type) }}</small>
              </span>
              <FxIcon v-if="Number(newServerId) === Number(server.id)" name="checkCircle" :size="17" />
            </button>
          </div>
        </div>
        <div class="fx-modal-footer">
          <button class="fx-btn fx-btn-ghost" :disabled="creating" @click="closeCreate">{{ $t('common.cancel') }}</button>
          <button class="fx-btn fx-btn-primary" :disabled="creating || !newLabel.trim() || !newServerId" @click="createDevice">
            <FxIcon v-if="creating" name="refresh" :size="14" class="fx-spin" />
            {{ creating ? $t('simpleDevices.preparing') : $t('simpleDevices.create') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="setupSlot" class="fx-modal-overlay" @click.self="closeSetup">
      <div class="fx-modal-box fx-simple-modal fx-setup-modal">
        <div class="fx-modal-header">
          <div>
            <span class="fx-simple-modal-kicker">{{ $t('simpleDevices.setupReady') }}</span>
            <h3>{{ setupSlot.label }}</h3>
            <p>{{ setupLocationName }}</p>
          </div>
          <button class="fx-icon-btn-sm" @click="closeSetup"><FxIcon name="close" :size="15" /></button>
        </div>
        <div class="fx-modal-body fx-setup-body">
          <div v-if="features.qr" class="fx-setup-qr">
            <div v-if="qrLoading" class="fx-setup-qr-loading"><FxIcon name="refresh" :size="22" class="fx-spin" /></div>
            <img v-else-if="qrUrl" :src="qrUrl" :alt="$t('simpleDevices.qrAlt')" />
            <div v-else class="fx-setup-qr-loading"><FxIcon name="warning" :size="21" /></div>
          </div>
          <div class="fx-setup-copy">
            <h4>{{ features.qr ? $t('simpleDevices.scanTitle') : $t('simpleDevices.downloadTitle') }}</h4>
            <p>{{ features.qr ? $t('simpleDevices.scanText') : $t('simpleDevices.downloadText') }}</p>
            <ol>
              <li>{{ $t('simpleDevices.stepOpen') }}</li>
              <li>{{ features.qr ? $t('simpleDevices.stepScan') : $t('simpleDevices.stepImport') }}</li>
              <li>{{ $t('simpleDevices.stepConnect') }}</li>
            </ol>
            <button v-if="features.config_download" class="fx-btn fx-btn-secondary" @click="downloadActiveConfig(setupSlot)">
              <FxIcon name="download" :size="15" /> {{ $t('simpleDevices.downloadConfig') }}
            </button>
          </div>
        </div>
        <div class="fx-modal-footer">
          <span>{{ $t('simpleDevices.keepPrivate') }}</span>
          <button class="fx-btn fx-btn-primary" @click="closeSetup">{{ $t('simpleDevices.done') }}</button>
        </div>
      </div>
    </div>

    <div v-if="deleteTarget" class="fx-modal-overlay" @click.self="closeDelete">
      <div class="fx-modal-box fx-simple-modal">
        <div class="fx-modal-header">
          <div><h3>{{ $t('simpleDevices.deleteTitle') }}</h3><p>{{ $t('simpleDevices.deleteText', { name: deleteTarget.label }) }}</p></div>
          <button class="fx-icon-btn-sm" @click="closeDelete"><FxIcon name="close" :size="15" /></button>
        </div>
        <div class="fx-modal-body">
          <label class="fx-form-label">{{ $t('simpleDevices.password') }}</label>
          <input v-model="deletePassword" class="fx-input" type="password" autocomplete="current-password" @keyup.enter="deleteDevice" />
          <p v-if="deleteError" class="fx-simple-error">{{ deleteError }}</p>
        </div>
        <div class="fx-modal-footer">
          <button class="fx-btn fx-btn-ghost" @click="closeDelete">{{ $t('common.cancel') }}</button>
          <button class="fx-btn fx-btn-danger" :disabled="deleting || !deletePassword" @click="deleteDevice">{{ $t('common.delete') }}</button>
        </div>
      </div>
    </div>

    <div class="fx-toast-wrap">
      <transition-group name="fx-toast-fade">
        <div v-for="item in toasts" :key="item.id" class="fx-toast" :class="item.type">{{ item.message }}</div>
      </transition-group>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { portalApi } from '../api/index.js'
import FxIcon from '../components/FxIcon.vue'
import CountryFlag from '../components/CountryFlag.vue'
import { apiErrorMessage } from '../utils.js'

const { t } = useI18n()
const router = useRouter()
const loading = ref(true)
const creating = ref(false)
const switchingId = ref(null)
const dnsSaving = ref(null)
const slots = ref([])
const servers = ref([])
const subscription = ref({})
const features = ref({ config_download: true, qr: true, dns_protection: false })
const dnsStates = ref({})
const menuId = ref(null)
const renamingId = ref(null)
const renameValue = ref('')
const showCreate = ref(false)
const newLabel = ref('')
const newServerId = ref(null)
const setupSlot = ref(null)
const qrUrl = ref('')
const qrLoading = ref(false)
const deleteTarget = ref(null)
const deletePassword = ref('')
const deleteError = ref('')
const deleting = ref(false)
const toasts = ref([])
let toastId = 0

const maxDevices = computed(() => Number(subscription.value.max_devices || 0))
const atLimit = computed(() => maxDevices.value > 0 && slots.value.length >= maxDevices.value)
const hasActiveSubscription = computed(() => subscription.value.status === 'active' || subscription.value.is_active === true)
const availableServers = computed(() => servers.value.filter(server => {
  const category = String(server.server_category || 'vpn').toLowerCase()
  const type = String(server.server_type || 'wireguard').toLowerCase()
  return category === 'vpn' && ['wireguard', 'amneziawg'].includes(type)
}))
const setupLocationName = computed(() => setupSlot.value ? locationName(setupSlot.value) : '')

function toast(message, type = 'info') {
  const id = ++toastId
  toasts.value.push({ id, message: String(message || ''), type })
  window.setTimeout(() => {
    const index = toasts.value.findIndex(item => item.id === id)
    if (index >= 0) toasts.value.splice(index, 1)
  }, type === 'error' ? 6500 : 3200)
}

function activeServer(slot) {
  return (slot.servers || []).find(server => Number(server.server_id) === Number(slot.active_server_id)) || slot.servers?.[0] || null
}

function locationName(slot) {
  const server = activeServer(slot)
  return server?.server_display_name || server?.server_name || t('simpleDevices.locationUnavailable')
}

function protocolLabel(value) {
  const protocol = String(value || 'wireguard').toLowerCase()
  if (protocol === 'amneziawg') return 'AmneziaWG'
  if (protocol === 'vless_reality') return 'VLESS Reality'
  return protocol === 'wireguard' ? 'WireGuard' : protocol
}

async function loadData() {
  loading.value = true
  try {
    const [slotResponse, subscriptionResponse, serverResponse, featureResponse] = await Promise.all([
      portalApi.listSlots(),
      portalApi.getSubscription(),
      portalApi.getServers(),
      portalApi.getFeatures(),
    ])
    slots.value = Array.isArray(slotResponse.data) ? slotResponse.data : []
    subscription.value = subscriptionResponse.data || {}
    servers.value = Array.isArray(serverResponse.data) ? serverResponse.data : []
    features.value = { ...features.value, ...(featureResponse.data?.features || {}) }
    if (features.value.dns_protection) await loadDnsStates()
  } catch (error) {
    if (error.response?.status === 401) router.push('/login')
    else toast(apiErrorMessage(error, t('common.loadError')), 'error')
  } finally {
    loading.value = false
  }
}

async function loadDnsStates() {
  await Promise.all(slots.value.map(async slot => {
    try {
      const { data } = await portalApi.getSlotDns(slot.id)
      dnsStates.value = { ...dnsStates.value, [slot.id]: data }
    } catch { /* the operator may have disabled the feature */ }
  }))
}

function openCreate() {
  menuId.value = null
  if (!hasActiveSubscription.value) {
    router.push('/plans')
    return
  }
  if (atLimit.value) return
  newLabel.value = t('simpleDevices.defaultDeviceName')
  newServerId.value = availableServers.value[0]?.id || null
  showCreate.value = true
}

function closeCreate() {
  if (!creating.value) showCreate.value = false
}

async function createDevice() {
  if (creating.value || !newLabel.value.trim() || !newServerId.value) return
  creating.value = true
  try {
    const { data } = await portalApi.createSlot({ label: newLabel.value.trim(), initial_server_id: Number(newServerId.value) })
    showCreate.value = false
    await loadData()
    const created = slots.value.find(slot => Number(slot.id) === Number(data?.id)) || data
    if (created) await openSetup(created)
    toast(t('simpleDevices.created'), 'success')
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.createError')), 'error')
  } finally {
    creating.value = false
  }
}

async function changeLocation(slot, serverId) {
  const target = Number(serverId)
  if (!target || target === Number(slot.active_server_id)) return
  switchingId.value = slot.id
  try {
    const { data } = await portalApi.switchSlotServer(slot.id, target)
    const index = slots.value.findIndex(item => item.id === slot.id)
    if (index >= 0) slots.value.splice(index, 1, data)
    toast(t('simpleDevices.locationChanged'), 'success')
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.locationError')), 'error')
    await loadData()
  } finally {
    switchingId.value = null
  }
}

async function changeDns(slot, profileId) {
  dnsSaving.value = slot.id
  try {
    const { data } = await portalApi.setSlotDns(slot.id, profileId)
    dnsStates.value = { ...dnsStates.value, [slot.id]: data }
    toast(t('simpleDevices.protectionChanged'), 'success')
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.protectionError')), 'error')
  } finally {
    dnsSaving.value = null
  }
}

function startRename(slot) {
  menuId.value = null
  renamingId.value = slot.id
  renameValue.value = slot.label
}

async function saveRename(slot) {
  if (renamingId.value !== slot.id) return
  const label = renameValue.value.trim()
  renamingId.value = null
  if (!label || label === slot.label) return
  try {
    const { data } = await portalApi.renameSlot(slot.id, label)
    const index = slots.value.findIndex(item => item.id === slot.id)
    if (index >= 0) slots.value.splice(index, 1, data)
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.renameError')), 'error')
  }
}

async function releaseDevice(slot) {
  menuId.value = null
  try {
    const { data } = await portalApi.releaseSlotDevice(slot.id)
    const index = slots.value.findIndex(item => item.id === slot.id)
    if (index >= 0) slots.value.splice(index, 1, data)
    toast(t('simpleDevices.released'), 'success')
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.releaseError')), 'error')
  }
}

async function openSetup(slot) {
  menuId.value = null
  if (slot.is_bound) {
    toast(t('simpleDevices.releaseBeforeSetup'), 'info')
    return
  }
  setupSlot.value = slot
  qrUrl.value = ''
  if (!features.value.qr) return
  const server = activeServer(slot)
  if (!server) return
  qrLoading.value = true
  try {
    const { data } = await portalApi.getSlotServerQr(slot.id, server.server_id)
    qrUrl.value = URL.createObjectURL(data)
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.qrError')), 'error')
  } finally {
    qrLoading.value = false
  }
}

function closeSetup() {
  setupSlot.value = null
  if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
  qrUrl.value = ''
}

async function downloadActiveConfig(slot) {
  const server = activeServer(slot)
  if (!server) return
  try {
    const { data } = await portalApi.getSlotServerConfig(slot.id, server.server_id)
    const config = typeof data === 'string' ? data : (data?.config || data?.config_text || '')
    if (!config) throw new Error(t('simpleDevices.configError'))
    const blobUrl = URL.createObjectURL(new Blob([config], { type: 'text/plain' }))
    const link = document.createElement('a')
    const filename = String(server.server_display_name || server.server_name || 'vpn').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 15)
    link.href = blobUrl
    link.download = `${filename || 'vpn'}.conf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(blobUrl)
  } catch (error) {
    toast(apiErrorMessage(error, t('simpleDevices.configError')), 'error')
  }
}

function openDelete(slot) {
  menuId.value = null
  deleteTarget.value = slot
  deletePassword.value = ''
  deleteError.value = ''
}

function closeDelete() {
  if (deleting.value) return
  deleteTarget.value = null
  deletePassword.value = ''
  deleteError.value = ''
}

async function deleteDevice() {
  if (!deleteTarget.value || deleting.value || !deletePassword.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await portalApi.verifyPassword(deletePassword.value)
    await portalApi.deleteSlot(deleteTarget.value.id)
    deleteTarget.value = null
    deletePassword.value = ''
    deleteError.value = ''
    await loadData()
    toast(t('simpleDevices.deleted'), 'success')
  } catch (error) {
    deleteError.value = error.response?.status === 400 || error.response?.status === 401
      ? t('simpleDevices.passwordWrong')
      : apiErrorMessage(error, t('simpleDevices.deleteError'))
  } finally {
    deleting.value = false
  }
}

function closeMenus(event) {
  if (!event.target.closest('.fx-simple-more') && !event.target.closest('.fx-simple-menu')) menuId.value = null
}

onMounted(() => {
  loadData()
  document.addEventListener('pointerdown', closeMenus)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', closeMenus)
  if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
})
</script>

<style scoped>
.fx-simple-page-head { align-items:flex-end; }
.fx-simple-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--gap); }
.fx-simple-card { position:relative;padding:20px;overflow:visible; }
.fx-simple-card-head { display:grid;grid-template-columns:42px minmax(0,1fr) 32px;gap:12px;align-items:center;position:relative; }
.fx-simple-device-icon { width:42px;height:42px;display:grid;place-items:center;border:1px solid var(--border-strong);border-radius:12px;color:var(--accent);background:var(--panel); }
.fx-simple-device-copy { min-width:0; }
.fx-simple-device-copy h2 { margin:0;font-size:16px;line-height:1.2;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.fx-simple-device-copy span { display:block;margin-top:4px;color:var(--text-3);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.fx-simple-rename { height:36px; }
.fx-simple-more { width:32px;height:32px;border:1px solid transparent;border-radius:9px;background:transparent;display:flex;align-items:center;justify-content:center;gap:3px;cursor:pointer;color:var(--text-3); }
.fx-simple-more:hover,.fx-simple-more[aria-expanded="true"] { border-color:var(--border);background:var(--panel-2);color:var(--text); }
.fx-simple-more span { width:3px;height:3px;border-radius:50%;background:currentColor; }
.fx-simple-menu { position:absolute;z-index:15;right:0;top:38px;width:210px;padding:5px;border:1px solid var(--border);border-radius:11px;background:var(--bg-elev);box-shadow:var(--shadow-lg); }
.fx-simple-menu button { width:100%;border:0;background:transparent;color:var(--text-2);height:36px;padding:0 10px;border-radius:8px;display:flex;align-items:center;gap:9px;font:inherit;font-size:12px;cursor:pointer;text-align:left; }
.fx-simple-menu button:hover { background:var(--panel-2);color:var(--text); }
.fx-simple-menu button.danger:hover { background:var(--danger-soft);color:var(--danger); }
.fx-simple-location { margin-top:20px;padding:14px;border:1px solid var(--border);border-radius:12px;background:var(--panel-2); }
.fx-simple-location > label { display:block;font-size:11px;font-weight:650;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px; }
.fx-simple-select-wrap { display:grid;grid-template-columns:28px minmax(0,1fr) 16px;align-items:center;gap:9px;color:var(--text-3); }
.fx-simple-select-wrap select { width:100%;appearance:none;border:0;background:transparent;color:var(--text);font:inherit;font-size:14px;font-weight:600;outline:0;min-width:0;cursor:pointer; }
.fx-simple-location small { display:block;color:var(--text-3);font-size:10.5px;line-height:1.4;margin:8px 0 0 37px; }
.fx-simple-protection { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:12px 14px;border:1px solid var(--border);border-radius:12px; }
.fx-simple-protection label span { display:flex;align-items:center;gap:7px;color:var(--text-2);font-size:12px;font-weight:600; }
.fx-simple-protection label small { display:block;color:var(--text-3);font-size:10px;margin-top:3px; }
.fx-simple-protection select { min-width:150px;max-width:52%;height:34px;border:1px solid var(--border-strong);border-radius:8px;background:var(--panel);color:var(--text);font:inherit;font-size:11.5px;padding:0 8px; }
.fx-simple-card-actions { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:18px; }
.fx-simple-card-actions .fx-btn { min-width:150px; }
.fx-simple-ready { display:inline-flex;align-items:center;gap:6px;color:var(--text-3);font-size:11px; }
.fx-simple-ready i { width:7px;height:7px;border-radius:50%;background:var(--success); }
.fx-simple-notice { display:flex;align-items:center;gap:11px;margin-bottom:var(--gap);padding:13px 15px;border:1px solid var(--border);border-radius:12px;background:var(--panel);color:var(--text-2); }
.fx-simple-notice > div { flex:1;min-width:0;display:flex;flex-direction:column;gap:2px; }
.fx-simple-notice strong { font-size:12.5px;color:var(--text); }
.fx-simple-notice span,.fx-simple-notice a { font-size:11px;color:var(--text-3); }
.fx-simple-notice a { color:var(--accent);font-weight:650;white-space:nowrap; }
.fx-simple-empty { min-height:320px;padding:44px 20px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center; }
.fx-simple-empty-icon { width:54px;height:54px;border:1px solid var(--border-strong);border-radius:15px;display:grid;place-items:center;color:var(--accent); }
.fx-simple-empty h2 { margin:17px 0 6px;font-size:18px;color:var(--text); }
.fx-simple-empty p { max-width:430px;margin:0 0 20px;color:var(--text-3);font-size:13px;line-height:1.55; }
.fx-simple-skeleton { min-height:260px;background:linear-gradient(90deg,var(--panel) 25%,var(--panel-2) 50%,var(--panel) 75%);background-size:200% 100%;animation:fx-simple-shimmer 1.3s infinite; }
@keyframes fx-simple-shimmer { to { background-position:-200% 0; } }
.fx-simple-modal { width:min(600px,calc(100vw - 28px)); }
.fx-simple-modal .fx-modal-header { align-items:flex-start; }
.fx-simple-modal .fx-modal-header h3 { margin:0; }
.fx-simple-modal .fx-modal-header p { margin:5px 0 0;color:var(--text-3);font-size:12px;line-height:1.45; }
.fx-simple-field-gap { margin-top:16px; }
.fx-simple-location-list { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:290px;overflow:auto;padding:1px; }
.fx-simple-location-list button { display:grid;grid-template-columns:34px minmax(0,1fr) 18px;column-gap:10px;align-items:center;text-align:left;padding:11px;border:1px solid var(--border);border-radius:11px;background:var(--bg-elev);color:var(--text);cursor:pointer;font:inherit;min-width:0;transition:border-color .15s,box-shadow .15s,transform .15s; }
.fx-simple-location-list button:hover { border-color:var(--border-strong);box-shadow:var(--shadow-sm);transform:translateY(-1px); }
.fx-simple-location-copy { min-width:0;display:flex;flex-direction:column;gap:3px;overflow:hidden; }
.fx-simple-location-list button strong { display:block;min-width:0;font-size:12.5px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.fx-simple-location-list button small { display:block;max-width:100%;color:var(--text-3);font-size:10.5px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none; }
.fx-simple-location-list button > svg { grid-column:3;color:var(--accent); }
.fx-simple-location-list button.active { border-color:var(--accent);background:var(--bg-elev);box-shadow:0 0 0 1px var(--accent) inset; }
.fx-simple-modal-kicker { display:block;color:var(--success);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px; }
.fx-setup-body { display:grid;grid-template-columns:210px minmax(0,1fr);gap:24px;align-items:center; }
.fx-setup-qr { width:210px;height:210px;padding:12px;border:1px solid var(--border);border-radius:15px;background:#fff; }
.fx-setup-qr img { width:100%;height:100%;display:block;object-fit:contain;image-rendering:pixelated; }
.fx-setup-qr-loading { width:100%;height:100%;display:grid;place-items:center;color:#697386; }
.fx-setup-copy h4 { margin:0 0 6px;font-size:16px;color:var(--text); }
.fx-setup-copy p { margin:0;color:var(--text-3);font-size:12.5px;line-height:1.5; }
.fx-setup-copy ol { margin:14px 0 16px;padding-left:20px;color:var(--text-2);font-size:12px;line-height:1.7; }
.fx-setup-modal .fx-modal-footer > span { flex:1;color:var(--text-3);font-size:10.5px; }
.fx-simple-error { margin:9px 0 0;color:var(--danger);font-size:12px; }

@media (max-width:760px) {
  .fx-simple-grid { grid-template-columns:1fr; }
  .fx-simple-page-head { align-items:flex-start; }
  .fx-simple-page-head .fx-btn { width:auto; }
  .fx-simple-location-list { grid-template-columns:1fr; }
  .fx-setup-body { grid-template-columns:1fr;text-align:center; }
  .fx-setup-qr { margin:0 auto;width:min(230px,72vw);height:min(230px,72vw); }
  .fx-setup-copy ol { display:inline-block;text-align:left; }
  .fx-setup-copy .fx-btn { width:100%;justify-content:center; }
}
@media (max-width:480px) {
  .fx-simple-devices .fx-modal-overlay { align-items:flex-end;padding:0; }
  .fx-simple-card { padding:16px; }
  .fx-simple-protection { align-items:flex-start;flex-direction:column; }
  .fx-simple-protection select { width:100%;max-width:none; }
  .fx-simple-card-actions .fx-btn { flex:1;min-width:0;justify-content:center; }
  .fx-simple-notice { align-items:flex-start;flex-wrap:wrap; }
  .fx-simple-notice a { margin-left:28px; }
  .fx-simple-modal { width:100%;max-width:none;max-height:min(92vh,760px);border-radius:16px 16px 0 0; }
  .fx-simple-modal .fx-modal-footer { padding-bottom:calc(14px + env(safe-area-inset-bottom,0px)); }
  .fx-simple-location-list { max-height:min(42vh,320px); }
  .fx-simple-location-list button { grid-template-columns:34px minmax(0,1fr) 18px;padding:10px; }
}
</style>
