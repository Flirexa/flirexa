<!-- Device Slots — designer 1:1 handoff (SLOTS screen). Search + refresh +
     bulk-delete row, then a card-wrapped table of slots with an expandable
     per-peer sub-table and RX/TX/last-switch totals. Wired to the existing
     clientsApi.listSlots / deleteSlot / releaseSlotDevice via a computed
     adapter that shapes each slot into his `sl.*` / `pe.*` view-model. -->
<template>
  <div class="d2-root">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <div style="position:relative;width:260px"><span style="position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-3);display:flex"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4-4"></path></svg></span><input :value="slotSearch" @input="onSlotSearch" :placeholder="tr('slots.search') || 'Search slots…'" class="d2-search-in" style="width:100%;height:34px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:9px;padding:0 11px 0 32px;font:inherit;font-size:12.5px;outline:none"></div>
      <button @click="refreshSlots" class="d2-hoverpanel" style="height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('common.refresh') || 'Refresh' }}</button>
      <button v-if="slotBulk" @click="bulkDeleteSlots" style="height:34px;padding:0 13px;border:none;background:var(--red-soft);color:var(--red);border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ slotBulkLabel }}</button>
    </div>

    <div v-if="loading && !slots.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
    <div v-else-if="!slots.length" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:56px;text-align:center;color:var(--text-3)">{{ tr('slots.noSlots') || 'No slots' }}</div>

    <div v-else style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div style="overflow-x:auto">
      <table data-rtab style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left">
          <th style="padding:11px 12px 11px 20px;width:36px"><input type="checkbox" :checked="slotAllSel" @change="toggleSlotAll" style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent)"></th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.owner') || 'Owner' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.device') || 'Device' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.active') || 'Active' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.regions') || 'Regions' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.total') || 'Total' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.created') || 'Created' }}</th>
          <th style="padding:11px 20px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('common.actions') || 'Actions' }}</th>
        </tr></thead>
        <tbody>
          <template v-for="sl in rows" :key="sl.id">
            <tr class="d2-hoverrow" style="border-top:1px solid var(--border)">
              <td data-mhide style="padding:12px 12px 12px 20px"><input type="checkbox" :checked="sl.selected" @change="sl.onSelect" style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent)"></td>
              <td data-mhead style="padding:12px 12px"><button @click="sl.onExpand" style="display:flex;align-items:center;gap:8px;border:none;background:transparent;cursor:pointer;font:inherit;color:var(--text);text-align:left;padding:0"><span :style="{ display:'flex', transform: sl.chevron, transition:'transform .15s', color:'var(--text-3)' }"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"></path></svg></span><span style="font-weight:550">{{ sl.owner }}</span></button></td>
              <td :data-label="tr('slots.device') || 'Device'" style="padding:12px 12px"><div style="font-size:12.5px">{{ sl.label }}</div><div style="font-size:11px;color:var(--text-3);font-family:'JetBrains Mono',monospace">{{ sl.device }}</div></td>
              <td :data-label="tr('slots.active') || 'Active'" style="padding:12px 12px"><span style="display:inline-flex;align-items:center;gap:6px;color:var(--text-2)">{{ sl.active }}<span :style="{ fontSize:'10px', fontWeight:600, padding:'1px 6px', borderRadius:'5px', color: sl.boundColor, background: sl.boundBg }">{{ sl.boundLabel }}</span></span></td>
              <td :data-label="tr('slots.regions') || 'Regions'" style="padding:12px 12px;font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ sl.regions }}</td>
              <td :data-label="tr('slots.total') || 'Total'" style="padding:12px 12px;font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ sl.totalLabel }}</td>
              <td :data-label="tr('slots.created') || 'Created'" style="padding:12px 12px;font-size:12px;color:var(--text-3);font-family:'JetBrains Mono',monospace">{{ sl.created }}</td>
              <td data-mfull style="padding:12px 20px"><div style="display:flex;gap:5px;justify-content:flex-end">
                <button v-if="sl.bound" @click="sl.onRelease" :title="tr('slots.releaseDevice') || 'Release'" class="d2-hoverpanel" style="height:30px;padding:0 11px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">{{ tr('slots.releaseDevice') || 'Release' }}</button>
                <button @click="sl.onDelete" :title="tr('common.delete') || 'Delete'" class="d2-delbtn" style="width:30px;height:30px;border-radius:7px;border:none;background:transparent;color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
              </div></td>
            </tr>
            <tr v-if="sl.expanded" style="border-top:1px solid var(--border);background:var(--panel-2)"><td data-mhide></td><td data-mfull colspan="7" style="padding:6px 20px 14px">
              <div style="font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin:6px 0 8px">{{ tr('slots.peers') || 'Peers' }}</div>
              <div style="border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--panel)">
                <table data-rtab style="width:100%;border-collapse:collapse;font-size:12px">
                  <thead><tr style="text-align:left"><th style="padding:7px 12px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.active') || 'Active' }}</th><th style="padding:7px 12px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">IP</th><th style="padding:7px 12px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.enabled') || 'Enabled' }}</th><th style="padding:7px 12px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('slots.handshake') || 'Handshake' }}</th><th style="padding:7px 12px;text-align:right;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">RX</th><th style="padding:7px 12px;text-align:right;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">TX</th></tr></thead>
                  <tbody>
                    <tr v-for="pe in sl.peers" :key="pe.id" style="border-top:1px solid var(--border)"><td data-mhead style="padding:8px 12px;font-weight:550">{{ pe.server }}</td><td data-label="IP" style="padding:8px 12px;font-family:'JetBrains Mono',monospace;color:var(--text-3)">{{ pe.ip }}</td><td :data-label="tr('slots.enabled') || 'Enabled'" style="padding:8px 12px"><span :style="{ display:'inline-flex', alignItems:'center', gap:'5px', fontSize:'11px', fontWeight:600, color: pe.enColor }"><span :style="{ width:'6px', height:'6px', borderRadius:'50%', background: pe.enColor }"></span>{{ pe.enLabel }}</span></td><td :data-label="tr('slots.handshake') || 'Handshake'" style="padding:8px 12px;font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ pe.handshake }}</td><td data-label="RX" style="padding:8px 12px;text-align:right;font-family:'JetBrains Mono',monospace;color:var(--green)">↓{{ pe.rx }}</td><td data-label="TX" style="padding:8px 12px;text-align:right;font-family:'JetBrains Mono',monospace;color:var(--blue)">↑{{ pe.tx }}</td></tr>
                  </tbody>
                </table>
              </div>
              <div style="display:flex;gap:24px;margin-top:11px;padding:0 2px">
                <div><span style="font-size:10.5px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">Total RX</span> <span style="font-family:'JetBrains Mono',monospace;font-size:12.5px;font-weight:600;color:var(--green);margin-left:5px">↓{{ sl.totalRx }}</span></div>
                <div><span style="font-size:10.5px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">Total TX</span> <span style="font-family:'JetBrains Mono',monospace;font-size:12.5px;font-weight:600;color:var(--blue);margin-left:5px">↑{{ sl.totalTx }}</span></div>
                <div><span style="font-size:10.5px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em">{{ tr('slots.lastSwitch') || 'Last switch' }}</span> <span style="font-family:'JetBrains Mono',monospace;font-size:12.5px;color:var(--text-2);margin-left:5px">{{ sl.lastSwitch }}</span></div>
              </div>
            </td></tr>
          </template>
        </tbody>
      </table>
    </div></div>

    <D2Modal :open="!!slotAddModal" :title="tr('slots.addTitle') || 'Add slot'" size="sm" @close="closeAddSlot">
      <div style="display:flex;flex-direction:column;gap:14px">
        <div style="position:relative">
          <label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('slots.addOwner') || 'Owner' }}</label>
          <input :value="slotAddModal ? slotAddModal.owner : ''" @input="onAddSlotOwner" :placeholder="tr('slots.ownerSearch') || 'Search customer…'" class="d2-slotf" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font:inherit;font-size:13.5px;outline:none">
          <div v-if="slotCandShow" style="position:absolute;left:0;right:0;top:70px;z-index:5;max-height:200px;overflow-y:auto;background:var(--panel);border:1px solid var(--border);border-radius:11px;box-shadow:var(--shadow-lg);padding:5px">
            <button v-for="c in slotCandidates" :key="c.id" @click="c.on" class="d2-hoverpanel" style="display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border:none;border-radius:8px;background:transparent;cursor:pointer;font:inherit;text-align:left">
              <span style="width:28px;height:28px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:650;flex:none">{{ c.initials }}</span>
              <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:550">{{ c.name }}</div><div style="font-size:11px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ c.sub }}</div></div>
              <span :style="{ fontSize:'10px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', color: c.tierColor, background: c.tierBg }">{{ c.tier }}</span>
            </button>
            <div v-if="slotNoCand" style="padding:12px;text-align:center;font-size:12.5px;color:var(--text-3)">{{ tr('slots.noCandidates') || 'No matching customers' }}</div>
          </div>
        </div>
        <div>
          <label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('slots.addLabel') || 'Device label' }}</label>
          <input :value="slotAddModal ? slotAddModal.label : ''" @input="onAddSlotLabel" placeholder="iPhone 15 Pro" class="d2-slotf" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font:inherit;font-size:13.5px;outline:none">
        </div>
      </div>
      <template #footer>
        <D2Button variant="secondary" @click="closeAddSlot">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button @click="submitAddSlot">{{ tr('slots.add') || 'Add' }}</D2Button>
      </template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { clientsApi, portalUsersApi } from '../../api'
import { formatBytes } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'
import D2Modal from '../ui/D2Modal.vue'
import D2Button from '../ui/D2Button.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const slots = ref([])
const loading = ref(false)
const expanded = ref({})
const selected = ref({})
const slotSearch = ref('')
const slotAddModal = ref(null)
const boundCount = computed(() => slots.value.filter(s => s.is_bound || s.device_id).length)
const peerTotal = computed(() => slots.value.reduce((a, s) => a + (s.peers || []).length, 0))

async function loadSlots() {
  loading.value = true
  try { const r = await clientsApi.listSlots(); const d = r.data; slots.value = Array.isArray(d) ? d : (d?.items || []) }
  catch (e) { console.error(e) } finally { loading.value = false }
}
async function deleteOne(s) {
  if (!await d2confirm(tr('slots.deleteConfirm') || `Delete slot "${s.label || s.id}"?`)) return
  try { await clientsApi.deleteSlot(s.id); await loadSlots() } catch (e) { alert(e.response?.data?.detail || 'Error') }
}
async function releaseDevice(s) {
  if (!await d2confirm(tr('slots.releaseDeviceConfirm') || 'Release the device bind on this slot?')) return
  try { await clientsApi.releaseSlotDevice(s.id); await loadSlots() } catch (e) { alert(e.response?.data?.detail || 'Error') }
}
function fmtBytes(b) { return formatBytes(b || 0) }
function rel(d) {
  const m = Math.floor((Date.now() - new Date(d).getTime()) / 60000)
  if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// --- Designer view-model adapter -------------------------------------------
function refreshSlots() { loadSlots() }
function onSlotSearch(e) { slotSearch.value = e && e.target ? e.target.value : (e || '') }
function fmtCreated(d) {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString(undefined, { year: '2-digit', month: 'short', day: 'numeric' }) } catch (_) { return String(d) }
}
function ownerOf(s) { const u = s.client_user || {}; return u.username || u.email || (u.id ? ('user #' + u.id) : (tr('slots.freeOwner') || 'Free slot')) }
function deviceIdShort(s) { const id = s.device_id; return id ? (String(id).length > 12 ? String(id).slice(0, 12) + '…' : String(id)) : (tr('slots.unbound') || 'unbound') }

const filteredSlots = computed(() => {
  const q = slotSearch.value.trim().toLowerCase()
  if (!q) return slots.value
  return slots.value.filter(s => (ownerOf(s) + ' ' + (s.label || '') + ' ' + (s.device_id || '')).toLowerCase().includes(q))
})

const rows = computed(() => filteredSlots.value.map(s => {
  const bound = !!(s.is_bound || s.device_id)
  const peers = (s.peers || []).map(p => ({
    id: p.client_id,
    server: p.server_display || p.server_name,
    ip: p.ipv4 || '—',
    enColor: p.enabled ? 'var(--green)' : 'var(--text-3)',
    enLabel: p.enabled ? (tr('slots.on') || 'on') : (tr('slots.off') || 'off'),
    handshake: p.last_handshake ? rel(p.last_handshake) : '—',
    rx: fmtBytes(p.traffic_used_rx),
    tx: fmtBytes(p.traffic_used_tx),
  }))
  const totals = s.totals || {}
  const active = (s.peers || []).find(p => p.is_active)
  return {
    id: s.id,
    selected: !!selected.value[s.id],
    onSelect: () => { selected.value = { ...selected.value, [s.id]: !selected.value[s.id] } },
    expanded: !!expanded.value[s.id],
    onExpand: () => { expanded.value = { ...expanded.value, [s.id]: !expanded.value[s.id] } },
    chevron: expanded.value[s.id] ? 'rotate(90deg)' : 'rotate(0deg)',
    owner: ownerOf(s),
    label: s.label || ('Slot ' + s.id),
    device: deviceIdShort(s),
    active: active ? (active.server_display || active.server_name) : '—',
    bound,
    boundColor: bound ? 'var(--blue)' : 'var(--text-3)',
    boundBg: bound ? 'var(--blue-soft)' : 'var(--gray-soft)',
    boundLabel: bound ? (tr('slots.bound') || 'bound') : (tr('slots.free') || 'free'),
    regions: (totals.regions != null ? totals.regions : peers.length),
    totalLabel: fmtBytes(totals.traffic_total_bytes),
    created: fmtCreated(s.created_at),
    peers,
    totalRx: fmtBytes(totals.traffic_rx_bytes),
    totalTx: fmtBytes(totals.traffic_tx_bytes),
    lastSwitch: s.last_switched_at ? rel(s.last_switched_at) : '—',
    onRelease: () => releaseDevice(s),
    onDelete: () => deleteOne(s),
  }
}))

const slotAllSel = computed(() => filteredSlots.value.length > 0 && filteredSlots.value.every(s => selected.value[s.id]))
function toggleSlotAll() {
  const all = slotAllSel.value
  const next = { ...selected.value }
  filteredSlots.value.forEach(s => { next[s.id] = !all })
  selected.value = next
}
const selectedIds = computed(() => filteredSlots.value.filter(s => selected.value[s.id]).map(s => s.id))
const slotBulk = computed(() => selectedIds.value.length > 0)
const slotBulkLabel = computed(() => (tr('slots.deleteSelected') || 'Delete selected') + ' (' + selectedIds.value.length + ')')
async function bulkDeleteSlots() {
  const ids = selectedIds.value
  if (!ids.length) return
  if (!await d2confirm((tr('slots.bulkDeleteConfirm') || 'Delete selected slots?') + ' (' + ids.length + ')')) return
  try { for (const id of ids) await clientsApi.deleteSlot(id); selected.value = {}; await loadSlots() }
  catch (e) { alert(e.response?.data?.detail || 'Error') }
}

// Add-slot modal — owner autocomplete (portalUsersApi.list) + create via
// portalUsersApi.addDeviceSlot (POST /portal-users/{id}/devices).
const TIER_COLORS = {
  free: ['var(--text-3)', 'var(--gray-soft)'],
  starter: ['var(--blue)', 'var(--blue-soft)'],
  pro: ['var(--accent)', 'var(--accent-soft)'],
  business: ['var(--purple)', 'var(--purple-soft)'],
  ultimate: ['var(--amber)', 'var(--amber-soft)'],
  premium: ['var(--accent)', 'var(--accent-soft)'],
}
function tierPair(t) { return TIER_COLORS[String(t || '').toLowerCase()] || TIER_COLORS.free }
function initialsOf(name) {
  const parts = String(name || '?').trim().split(/[\s@]+/).filter(Boolean)
  return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || '?'
}
const slotCandList = ref([])
function openAddSlot() { slotAddModal.value = { owner: '', ownerId: null, label: '' } }
function closeAddSlot() { slotAddModal.value = null; slotCandList.value = [] }
async function onAddSlotOwner(v) {
  if (!slotAddModal.value) return
  const val = v && v.target ? v.target.value : v
  slotAddModal.value.owner = val
  slotAddModal.value.ownerId = null
  const q = String(val || '').trim()
  if (!q) { slotCandList.value = []; return }
  try { const r = await portalUsersApi.list({ search: q, limit: 8 }); const d = r.data; slotCandList.value = Array.isArray(d) ? d : (d?.items || d?.users || []) }
  catch (_) { slotCandList.value = [] }
}
function onAddSlotLabel(v) { if (slotAddModal.value) slotAddModal.value.label = v && v.target ? v.target.value : v }
function pickCandidate(u) {
  if (!slotAddModal.value) return
  slotAddModal.value.owner = u.username || u.email || ('user #' + u.id)
  slotAddModal.value.ownerId = u.id
  slotCandList.value = []
}
const slotCandidates = computed(() => slotCandList.value.map(u => ({
  id: u.id,
  initials: initialsOf(u.full_name || u.username || u.email),
  name: u.full_name || u.username || u.email || ('user #' + u.id),
  sub: u.email || (u.username ? '@' + u.username : '—'),
  tier: u.tier || u.subscription_tier || 'free',
  tierColor: tierPair(u.tier || u.subscription_tier)[0],
  tierBg: tierPair(u.tier || u.subscription_tier)[1],
  on: () => pickCandidate(u),
})))
const slotCandShow = computed(() => !!(slotAddModal.value && !slotAddModal.value.ownerId && slotAddModal.value.owner && slotAddModal.value.owner.trim()))
const slotNoCand = computed(() => slotCandShow.value && slotCandidates.value.length === 0)
async function submitAddSlot() {
  const m = slotAddModal.value
  if (!m) return
  if (!m.ownerId) { alert(tr('slots.pickOwner') || 'Select a customer from the list'); return }
  try {
    await portalUsersApi.addDeviceSlot(m.ownerId, { label: (m.label || '').trim() || undefined })
    closeAddSlot(); await loadSlots()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
}

onMounted(() => {
  ui.set({
    title: tr('nav.slots') || 'Slots',
    subtitle: tr('slots.subtitle') || 'Multi-region customer devices',
    primary: { label: tr('slots.add') || 'Add slot', onClick: openAddSlot },
  })
  loadSlots()
})
</script>

<style scoped>
.d2-hoverrow:hover { background: var(--panel-2); }
.d2-hoverpanel:hover { background: var(--panel-2); }
.d2-search-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-slotf:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-delbtn:hover { background: var(--red-soft); color: var(--red); }
</style>
