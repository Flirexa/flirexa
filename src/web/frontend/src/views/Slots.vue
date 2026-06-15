<template>
  <div class="slots-page">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h2 class="mb-1">{{ $t('slots.title') }}</h2>
        <p class="text-muted small mb-0">
          {{ $t('slots.subtitle') }}
        </p>
      </div>
      <div class="d-flex gap-2 flex-wrap">
        <button class="btn btn-outline-info btn-sm" @click="openAddSlot" :disabled="loading || actionBusy">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>
          {{ $t('portalUsers.addSlot') || 'Add Device Slot' }}
        </button>
        <button class="btn btn-outline-danger btn-sm" @click="deleteSelected"
                :disabled="!selectedIds.length || actionBusy">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6 17.5 20a2 2 0 0 1-2 1.8H8.5a2 2 0 0 1-2-1.8L5 6"/><path d="M10 11v6M14 11v6"/></svg>
          {{ $t('slots.deleteSelected') || 'Delete selected' }}
          <span v-if="selectedIds.length" class="badge bg-danger ms-1">{{ selectedIds.length }}</span>
        </button>
        <button class="btn btn-outline-secondary btn-sm" @click="loadSlots" :disabled="loading">
          <i class="mdi mdi-refresh me-1"></i>
          {{ loading ? ($t('common.loading')) : ($t('common.refresh')) }}
        </button>
      </div>
    </div>

    <div v-if="!loading && !slots.length" class="card">
      <div class="card-body text-center text-muted py-5">
        <i class="mdi mdi-cellphone-link" style="font-size:48px;opacity:0.4"></i>
        <h5 class="mt-3">{{ $t('slots.empty') }}</h5>
        <p class="small mb-0">
          {{ $t('slots.emptyHint') }}
        </p>
      </div>
    </div>

    <div v-else class="card">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover mb-0 align-middle">
            <thead>
              <tr>
                <th style="width: 38px;" class="text-center">
                  <input type="checkbox" class="form-check-input" :checked="allSelected" :indeterminate.prop="someSelected" @change="toggleAll" :title="$t('slots.selectAll') || 'Select all'" />
                </th>
                <th>{{ $t('slots.colDevice') }}</th>
                <th>{{ $t('slots.colCustomer') }}</th>
                <th>{{ $t('slots.colRegions') }}</th>
                <th>{{ $t('slots.colActive') }}</th>
                <th>{{ $t('slots.colTraffic') }}</th>
                <th>{{ $t('slots.colCreated') }}</th>
                <th class="text-end">{{ $t('common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="slot in slots" :key="slot.id">
                <tr @click="toggleExpand(slot.id)" style="cursor:pointer">
                  <td class="text-center" @click.stop>
                    <input type="checkbox" class="form-check-input" :checked="selected[slot.id]" @change="toggleOne(slot.id)" />
                  </td>
                  <td>
                    <strong>{{ slot.label }}</strong>
                    <span v-if="slot.device_id"
                          class="badge bg-warning-subtle text-warning ms-2"
                          :title="$t('slots.deviceBoundTitle') || `Bound to device ${slot.device_id}` ">
                      <i class="mdi mdi-lock" style="font-size:11px"></i>
                      {{ $t('slots.deviceBound') || 'Bound' }}
                    </span>
                    <span v-else class="badge bg-light text-muted ms-2"
                          :title="$t('slots.deviceUnboundTitle') || 'Free — next device to connect will claim it'">
                      <i class="mdi mdi-lock-open-variant" style="font-size:11px"></i>
                      {{ $t('slots.deviceUnbound') || 'Free' }}
                    </span>
                    <i class="mdi ms-1" :class="expanded[slot.id] ? 'mdi-chevron-down' : 'mdi-chevron-right'"></i>
                  </td>
                  <td>
                    <span v-if="slot.client_user.email">{{ slot.client_user.email }}</span>
                    <span v-else-if="slot.client_user.username" class="text-muted">@{{ slot.client_user.username }}</span>
                    <span v-else class="text-muted">—</span>
                    <button class="btn btn-link btn-sm p-0 ms-2"
                            :title="$t('slots.selectAllForUser') || 'Select all slots for this user'"
                            @click.stop="selectAllForUser(slot.client_user.id)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="m8 12 3 3 5-6"/></svg>
                    </button>
                  </td>
                  <td>
                    <span class="badge bg-light text-dark">{{ slot.totals.regions }}</span>
                  </td>
                  <td>
                    <span v-if="slot.active_server_name" class="badge bg-success-subtle text-success">
                      <i class="mdi mdi-circle text-success me-1" style="font-size:8px"></i>
                      {{ slot.active_server_name }}
                    </span>
                    <span v-else class="text-muted small">none</span>
                  </td>
                  <td>
                    <span style="font-family:var(--bs-font-monospace);font-size:12px">
                      {{ humanBytes(slot.totals.traffic_total_bytes) }}
                    </span>
                  </td>
                  <td>
                    <span class="text-muted small">{{ formatDate(slot.created_at) }}</span>
                  </td>
                  <td class="text-end" @click.stop>
                    <button class="btn btn-sm btn-link p-0 me-2" @click="toggleExpand(slot.id)">
                      {{ expanded[slot.id] ? ($t('common.collapse')) : ($t('common.expand')) }}
                    </button>
                    <button v-if="slot.device_id"
                            class="btn btn-sm btn-outline-warning me-1" @click="releaseDevice(slot)"
                            :disabled="actionBusy"
                            :title="$t('slots.releaseDeviceTitle') || 'Release device bind — customer can re-bind on next connect'">
                      <i class="mdi mdi-lock-open-variant" style="font-size:14px"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="deleteOne(slot)"
                            :disabled="actionBusy"
                            :title="$t('common.delete') || 'Delete'">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6 17.5 20a2 2 0 0 1-2 1.8H8.5a2 2 0 0 1-2-1.8L5 6"/></svg>
                    </button>
                  </td>
                </tr>
                <tr v-if="expanded[slot.id]" class="slot-detail-row">
                  <td colspan="8" class="bg-light">
                    <div class="p-3">
                      <h6 class="mb-3">{{ $t('slots.peersTitle') }}</h6>
                      <table class="table table-sm mb-2">
                        <thead>
                          <tr>
                            <th>{{ $t('slots.peerServer') }}</th>
                            <th>{{ $t('slots.peerIp') }}</th>
                            <th>{{ $t('slots.peerEnabled') }}</th>
                            <th>{{ $t('slots.peerHandshake') }}</th>
                            <th>{{ $t('slots.peerRx') }}</th>
                            <th>{{ $t('slots.peerTx') }}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="p in slot.peers" :key="p.client_id">
                            <td>
                              <strong v-if="p.is_active" class="text-success">{{ p.server_display || p.server_name }}</strong>
                              <span v-else>{{ p.server_display || p.server_name }}</span>
                              <span v-if="p.is_active" class="badge bg-success ms-2" style="font-size:10px">ACTIVE</span>
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ p.ipv4 || '—' }}
                            </td>
                            <td>
                              <span v-if="p.enabled" class="badge bg-success-subtle text-success">on</span>
                              <span v-else class="badge bg-secondary-subtle text-secondary">off</span>
                            </td>
                            <td class="small text-muted">
                              {{ p.last_handshake ? relativeTime(p.last_handshake) : '—' }}
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ humanBytes(p.traffic_used_rx) }}
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ humanBytes(p.traffic_used_tx) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                      <div class="d-flex gap-3 text-muted small">
                        <div v-if="slot.last_switched_at">
                          {{ $t('slots.lastSwitched') }}:
                          <strong>{{ relativeTime(slot.last_switched_at) }}</strong>
                        </div>
                        <div>
                          {{ $t('slots.totalRx') }}:
                          <strong>{{ humanBytes(slot.totals.traffic_rx_bytes) }}</strong>
                        </div>
                        <div>
                          {{ $t('slots.totalTx') }}:
                          <strong>{{ humanBytes(slot.totals.traffic_tx_bytes) }}</strong>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Add-slot modal -->
    <div v-if="showAdd" class="slots-modal-backdrop" @click.self="closeAddSlot">
      <div class="slots-modal-card">
        <header class="d-flex align-items-center justify-content-between mb-3">
          <h5 class="mb-0">{{ $t('portalUsers.addSlot') || 'Add Device Slot' }}</h5>
          <button class="btn btn-sm btn-link p-0 text-muted" @click="closeAddSlot" :aria-label="$t('common.close') || 'Close'">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </header>
        <div class="mb-3">
          <label class="form-label small">{{ $t('slots.pickUser') || 'Customer' }}</label>
          <input type="text" class="form-control form-control-sm" v-model="addSearch"
                 :placeholder="$t('slots.searchUserPh') || 'Search by username or email…'"
                 @input="onAddSearch" />
          <div v-if="addCandidates.length" class="list-group mt-2" style="max-height: 280px; overflow-y: auto;">
            <button v-for="u in addCandidates" :key="u.id" type="button"
                    class="list-group-item list-group-item-action"
                    :class="{ active: addUserId === u.id }"
                    @click="pickAddUser(u)">
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <strong>{{ u.username }}</strong>
                  <span v-if="u.email" class="text-muted ms-2">{{ u.email }}</span>
                </div>
                <span class="badge bg-light text-dark">{{ u.tier || 'free' }}</span>
              </div>
            </button>
          </div>
          <div v-else-if="addSearchTried && !addSearching" class="text-muted small mt-2">
            {{ $t('slots.noMatches') || 'No users matched.' }}
          </div>
          <div v-if="addSearching" class="text-muted small mt-2">
            <span class="spinner-border spinner-border-sm me-1"></span>
            {{ $t('common.loading') || 'Loading…' }}
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label small">{{ $t('slots.label') || 'Label' }}</label>
          <input type="text" class="form-control form-control-sm" v-model.trim="addLabel"
                 :placeholder="$t('portalUsers.addSlotDefaultLabel') || 'Device'" maxlength="64" />
        </div>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-sm btn-outline-secondary" @click="closeAddSlot" :disabled="addBusy">
            {{ $t('common.cancel') || 'Cancel' }}
          </button>
          <button class="btn btn-sm btn-primary" @click="submitAddSlot"
                  :disabled="addBusy || !addUserId || !addLabel">
            <span v-if="addBusy" class="spinner-border spinner-border-sm me-1"></span>
            {{ $t('slots.create') || 'Create' }}
          </button>
        </div>
        <p v-if="addError" class="text-danger small mt-2 mb-0">{{ addError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { clientsApi, portalUsersApi } from '../api'

const { t } = useI18n()

const slots = ref([])
const loading = ref(false)
const expanded = ref({})
const selected = ref({})           // { [slotId]: true }
const actionBusy = ref(false)

const allSelected = computed(() =>
  slots.value.length > 0 && slots.value.every(s => selected.value[s.id]))
const someSelected = computed(() =>
  slots.value.some(s => selected.value[s.id]) && !allSelected.value)
const selectedIds = computed(() =>
  slots.value.filter(s => selected.value[s.id]).map(s => s.id))

async function loadSlots() {
  loading.value = true
  try {
    const r = await clientsApi.listSlots()
    slots.value = r.data || []
    // Drop selection of rows that disappeared
    const live = new Set(slots.value.map(s => s.id))
    const next = {}
    for (const id of Object.keys(selected.value)) {
      if (live.has(+id)) next[+id] = true
    }
    selected.value = next
  } catch (e) {
    console.error('Failed to load slots', e)
  } finally {
    loading.value = false
  }
}

function toggleExpand(slotId) {
  expanded.value = { ...expanded.value, [slotId]: !expanded.value[slotId] }
}

function toggleOne(slotId) {
  selected.value = { ...selected.value, [slotId]: !selected.value[slotId] }
}

function toggleAll() {
  if (allSelected.value || someSelected.value) {
    selected.value = {}
  } else {
    const next = {}
    for (const s of slots.value) next[s.id] = true
    selected.value = next
  }
}

// "Select every slot belonging to this customer" — handy when the
// operator wants to nuke a single user's setup in one click.
function selectAllForUser(userId) {
  const next = { ...selected.value }
  for (const s of slots.value) {
    if (s.client_user.id === userId) next[s.id] = true
  }
  selected.value = next
}

async function deleteOne(slot) {
  const tpl = t('slots.deleteOneConfirm') || 'Delete slot "{label}" of user {user}? Peers on all servers will be removed.'
  const userLabel = slot.client_user.email || slot.client_user.username || `#${slot.client_user.id}`
  if (!confirm(tpl.replace('{label}', slot.label).replace('{user}', userLabel))) return
  actionBusy.value = true
  try {
    await clientsApi.deleteSlot(slot.id)
    await loadSlots()
  } catch (e) {
    alert((t('common.error') || 'Error') + ': ' + (e.response?.data?.detail || e.message))
  } finally {
    actionBusy.value = false
  }
}

async function releaseDevice(slot) {
  const tpl = t('slots.releaseDeviceConfirm')
    || 'Release device bind on "{label}"? The customer\'s next connect will re-claim the slot.'
  if (!confirm(tpl.replace('{label}', slot.label))) return
  actionBusy.value = true
  try {
    await clientsApi.releaseSlotDevice(slot.id)
    await loadSlots()
  } catch (e) {
    alert((t('common.error') || 'Error') + ': ' + (e.response?.data?.detail || e.message))
  } finally {
    actionBusy.value = false
  }
}

async function deleteSelected() {
  if (!selectedIds.value.length) return
  const tpl = t('slots.deleteManyConfirm') || 'Delete {count} slot(s)? Peers on all servers will be removed. This cannot be undone.'
  if (!confirm(tpl.replace('{count}', selectedIds.value.length))) return
  actionBusy.value = true
  let failed = 0
  for (const id of selectedIds.value) {
    try { await clientsApi.deleteSlot(id) }
    catch { failed++ }
  }
  // The sequential loop can outlive the component (user navigates away mid
  // bulk-delete). Skip the trailing reload/alert if we've already unmounted
  // so we don't write to a torn-down view.
  if (!mounted.value) return
  await loadSlots()
  actionBusy.value = false
  if (failed) {
    const failTpl = t('slots.deleteSomeFailed') || '{count} slot(s) failed to delete — check the logs.'
    alert(failTpl.replace('{count}', failed))
  }
}

// ── Add-slot modal ──────────────────────────────────────────────────────────

const showAdd = ref(false)
const addSearch = ref('')
const addCandidates = ref([])
const addSearching = ref(false)
const addSearchTried = ref(false)
const addUserId = ref(null)
const addLabel = ref('')
const addBusy = ref(false)
const addError = ref('')
let searchTimer = null

function openAddSlot() {
  addSearch.value = ''
  addCandidates.value = []
  addSearching.value = false
  addSearchTried.value = false
  addUserId.value = null
  addLabel.value = t('portalUsers.addSlotDefaultLabel') || 'Device'
  addError.value = ''
  showAdd.value = true
  // Preload the most recent 50 users so the picker is immediately
  // browseable — typing in the search field then filters further via
  // the existing debounced API call.
  loadDefaultUsers()
}

async function loadDefaultUsers() {
  addSearching.value = true
  addSearchTried.value = true
  try {
    const r = await portalUsersApi.list({ limit: 50 })
    addCandidates.value = r.data?.items || r.data || []
  } catch (e) {
    addCandidates.value = []
  } finally {
    addSearching.value = false
  }
}

function closeAddSlot() { showAdd.value = false }

function onAddSearch() {
  clearTimeout(searchTimer)
  const q = addSearch.value.trim()
  // Empty search → restore the default list. The browse-list and the
  // search results share the same dropdown; this keeps users from
  // having to close + re-open the modal to escape a typo.
  if (!q) {
    loadDefaultUsers()
    return
  }
  if (q.length < 2) return  // wait for at least 2 chars before hitting the API
  searchTimer = setTimeout(searchUsers, 280)
}

async function searchUsers() {
  addSearching.value = true
  addSearchTried.value = true
  try {
    const r = await portalUsersApi.list({ search: addSearch.value.trim(), limit: 50 })
    addCandidates.value = (r.data?.items || r.data || []).slice(0, 50)
  } catch (e) {
    addCandidates.value = []
  } finally {
    addSearching.value = false
  }
}

function pickAddUser(u) {
  addUserId.value = u.id
  addSearch.value = u.username + (u.email ? ` (${u.email})` : '')
  // Keep the list visible so the operator can swap their choice
  // without re-typing — clearing the picked user is the same as
  // clicking another row.
}

async function submitAddSlot() {
  if (!addUserId.value || !addLabel.value) return
  addBusy.value = true
  addError.value = ''
  try {
    await portalUsersApi.addDeviceSlot(addUserId.value, { label: addLabel.value })
    showAdd.value = false
    await loadSlots()
  } catch (e) {
    addError.value = e.response?.data?.detail || e.message || (t('common.error') || 'Error')
  } finally {
    addBusy.value = false
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function humanBytes(n) {
  if (!n || n < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`
}
function formatDate(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}
function relativeTime(iso) {
  if (!iso) return '—'
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 60) return `${Math.floor(diff)}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch { return iso }
}

// Tracks whether the component is still alive, so async loops (bulk delete)
// can bail out of their trailing work after teardown.
const mounted = ref(true)
onUnmounted(() => { mounted.value = false })

onMounted(loadSlots)
</script>

<style scoped>
.slots-page {
  padding: 1rem;
}
.slot-detail-row td {
  border-top: none;
}

.slots-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(8, 10, 18, .55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1080;
  padding: 16px;
}
.slots-modal-card {
  width: 100%;
  max-width: 460px;
  background: var(--vxy-card-bg, #fff);
  color: var(--vxy-text, #1a1d23);
  border: 1px solid var(--vxy-border, rgba(0,0,0,.08));
  border-radius: 14px;
  padding: 22px;
  box-shadow: 0 24px 60px rgba(0,0,0,.35);
}
[data-theme="dark"] .slots-modal-card {
  background: var(--vxy-modal-bg, #1a1a25);
  color: var(--vxy-text, #e7e9ee);
  border-color: rgba(255,255,255,.10);
}
</style>
