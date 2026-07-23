<!-- Payments — his exact layout: stat cards / filter chips + search / table
     (ID·user·amount·method·status·date·actions). Wired to portalUsersApi. -->
<template>
  <div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px">
      <div v-for="s in payStats" :key="s.label" style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:15px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ s.label }}</div>
        <div :style="{ fontSize:'24px', fontWeight:680, letterSpacing:'-.02em', marginTop:'7px', color:s.color }">{{ s.value }}</div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <button v-for="f in payFilters" :key="f.key" @click="filter = f.key" :style="{ height:'32px', padding:'0 13px', border:'1px solid '+(filter===f.key?'var(--accent)':'var(--border-strong)'), background:(filter===f.key?'var(--accent-soft)':'var(--panel)'), color:(filter===f.key?'var(--accent)':'var(--text-2)'), borderRadius:'8px', font:'inherit', fontSize:'12.5px', fontWeight:(filter===f.key?600:500), cursor:'pointer' }">{{ f.label }}</button>
      <div style="position:relative;margin-left:auto;width:240px"><span style="position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-3);display:flex"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4-4"></path></svg></span><input v-model="query" :placeholder="tr('payments.search') || 'Search payments…'" class="d2-search" style="width:100%;height:34px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:9px;padding:0 11px 0 32px;font:inherit;font-size:12.5px;outline:none" /></div>
    </div>

    <div v-if="loading && !payments.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
    <div v-else-if="!filtered.length" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:56px 24px;text-align:center"><div style="width:54px;height:54px;border-radius:14px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;margin:0 auto 14px"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="5" width="20" height="14" rx="2"></rect><path d="M2 10h20"></path></svg></div><div style="font-size:15px;font-weight:600">{{ tr('payments.emptyTitle') || 'No payments' }}</div><div style="font-size:13px;color:var(--text-3);margin-top:4px">{{ tr('payments.emptySub') || 'Payments will appear here' }}</div></div>

    <div v-else style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left">
          <th class="d2-th" style="padding-left:20px">ID</th><th class="d2-th">{{ tr('payments.user') || 'User' }}</th><th class="d2-th">{{ tr('payments.amount') || 'Amount' }}</th><th class="d2-th">{{ tr('payments.method') || 'Method' }}</th><th class="d2-th">{{ tr('payments.status') || 'Status' }}</th><th class="d2-th">{{ tr('payments.date') || 'Date' }}</th><th class="d2-th" style="text-align:right;padding-right:20px">{{ tr('common.actions') || 'Actions' }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="p in filtered" :key="p.id" style="border-top:1px solid var(--border)">
            <td class="mono" style="padding:12px 20px;color:var(--text-3)">#{{ p.id }}</td>
            <td style="padding:12px 12px"><div style="font-weight:550">{{ p.user }}</div><div style="font-size:11.5px;color:var(--text-3)">{{ p.email }}</div></td>
            <td style="padding:12px 12px"><div class="mono" style="font-weight:600">{{ p.amountLabel }}</div><div style="font-size:10.5px;color:var(--text-3);margin-top:1px">{{ p.tier }}</div></td>
            <td style="padding:12px 12px;color:var(--text-2)">{{ p.method }}</td>
            <td style="padding:12px 12px"><span :style="{ display:'inline-flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:550, color:p.statusColor }"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:p.statusColor }"></span>{{ p.statusLabel }}</span></td>
            <td class="mono" style="padding:12px 12px;font-size:11.5px;color:var(--text-3)">{{ p.date }}</td>
            <td style="padding:12px 20px"><div style="display:flex;gap:5px;justify-content:flex-end">
              <template v-if="p.isPending">
                <button @click="confirm(p)" :title="tr('payments.confirm') || 'Confirm'" style="width:30px;height:30px;border-radius:7px;border:none;background:var(--green-soft);color:var(--green);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4 4L19 7"></path></svg></button>
                <button @click="reject(p)" :title="tr('payments.reject') || 'Reject'" style="width:30px;height:30px;border-radius:7px;border:none;background:var(--red-soft);color:var(--red);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>
              </template>
              <button v-else @click="askDelete(p)" :title="tr('common.delete') || 'Delete'" class="d2-del"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
            </div></td>
          </tr>
        </tbody>
      </table>
    </div></div>

    <!-- Confirm modal — his CONFIRM MODAL (warning icon / title+message /
         optional reason textarea for reject / cancel + busy confirm). -->
    <D2Modal :open="!!modal" size="sm" @close="closeModal">
      <template #header><span></span></template>
      <div style="display:flex;gap:14px">
        <div :style="{ width:'42px', height:'42px', borderRadius:'11px', background:(modal && modal.iconBg) || 'var(--red-soft)', color:(modal && modal.iconColor) || 'var(--red)', display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 16H3z"></path><path d="M12 10v4M12 16.5v.01"></path></svg></div>
        <div style="flex:1;padding-top:1px"><div style="font-weight:650;font-size:16px;letter-spacing:-.01em">{{ modal ? modal.title : '' }}</div><div style="font-size:13px;color:var(--text-2);margin-top:5px;line-height:1.5">{{ modal ? modal.message : '' }}</div></div>
      </div>
      <textarea v-if="modal && modal.withReason" v-model="reason" :placeholder="tr('payments.reasonPh') || 'Reason (optional)…'" class="d2-reason" style="width:100%;margin-top:16px;min-height:70px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;font-size:13px;outline:none"></textarea>
      <template #footer>
        <button @click="closeModal" class="d2-btn-cancel" style="height:40px;padding:0 16px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:10px;font:inherit;font-size:13.5px;font-weight:550;cursor:pointer">{{ tr('common.cancel') || 'Cancel' }}</button>
        <button @click="confirmModal" :disabled="modalBusy" :style="{ display:'flex', alignItems:'center', gap:'8px', height:'40px', padding:'0 18px', border:'none', background:(modal && modal.confirmBg) || 'var(--accent)', color:'#fff', borderRadius:'10px', font:'inherit', fontSize:'13.5px', fontWeight:600, cursor: modalBusy ? 'default' : 'pointer', opacity: modalBusy ? 0.85 : 1 }"><span v-if="modalBusy" style="width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ modal ? modal.confirmText : '' }}</button>
      </template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalUsersApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'
import D2Modal from '../ui/D2Modal.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const payments = ref([]); const loading = ref(false); const filter = ref('all'); const query = ref('')
const modal = ref(null); const modalBusy = ref(false); const reason = ref('')

const SC = { completed: 'var(--green)', pending: 'var(--amber)', rejected: 'var(--red)', failed: 'var(--red)' }
function money(p) { const c = (p.currency || 'USD').toUpperCase(); const a = p.amount_usd ?? p.amount ?? 0; return c === 'USD' ? '$' + Number(a).toFixed(2) : Number(a).toFixed(2) + ' ' + c }
function fmtDate(s) { if (!s) return '—'; try { return new Date(s).toLocaleString(undefined, { year: '2-digit', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) } catch (_) { return s } }
function statusLabel(s) { const k = String(s || '').toLowerCase(); return tr('payments.status_' + k) || (k.charAt(0).toUpperCase() + k.slice(1)) }

const rows = computed(() => payments.value.map(p => {
  const st = String(p.status || '').toLowerCase()
  return { id: p.id, user: p.username || p.user || ('user #' + (p.user_id ?? '?')), email: p.email || '', amountLabel: money(p), tier: p.tier || p.plan || p.tariff_name || '', method: p.payment_method || p.method || '—', statusColor: SC[st] || 'var(--text-3)', statusLabel: statusLabel(st), status: st, date: fmtDate(p.created_at || p.date), isPending: st === 'pending' }
}))
const filtered = computed(() => {
  let r = rows.value
  if (filter.value !== 'all') r = r.filter(p => p.status === filter.value)
  const q = query.value.trim().toLowerCase()
  if (q) r = r.filter(p => (p.user + ' ' + p.email + ' ' + p.method + ' #' + p.id).toLowerCase().includes(q))
  return r
})
const payFilters = computed(() => [
  { key: 'all', label: tr('payments.all') || 'All' },
  { key: 'pending', label: tr('payments.status_pending') || 'Pending' },
  { key: 'completed', label: tr('payments.status_completed') || 'Completed' },
  { key: 'rejected', label: tr('payments.status_rejected') || 'Rejected' },
])
const payStats = computed(() => {
  const done = payments.value.filter(p => String(p.status).toLowerCase() === 'completed')
  const rev = done.reduce((a, p) => a + Number(p.amount_usd ?? p.amount ?? 0), 0)
  const pend = payments.value.filter(p => String(p.status).toLowerCase() === 'pending').length
  return [
    { label: tr('payments.totalRevenue') || 'Revenue', value: '$' + rev.toFixed(2), color: 'var(--green)' },
    { label: tr('payments.totalPayments') || 'Payments', value: payments.value.length, color: 'var(--text)' },
    { label: tr('payments.completed') || 'Completed', value: done.length, color: 'var(--accent)' },
    { label: tr('payments.pending') || 'Pending', value: pend, color: 'var(--amber)' },
  ]
})

async function load() { loading.value = true; try { const { data } = await portalUsersApi.getPayments(); payments.value = Array.isArray(data) ? data : (data.items || data.payments || []) } catch (e) { console.error(e) } finally { loading.value = false } }

function closeModal() { if (modalBusy.value) return; modal.value = null; reason.value = '' }
function confirm(p) {
  modal.value = { kind: 'confirm', id: p.id, title: tr('payments.confirmTitle') || 'Confirm payment',
    message: (tr('payments.confirmMsg') || 'Mark this payment as completed?') + ' #' + p.id,
    confirmText: tr('payments.confirm') || 'Confirm', confirmBg: 'var(--green)', iconBg: 'var(--green-soft)', iconColor: 'var(--green)' }
}
function reject(p) {
  modal.value = { kind: 'reject', id: p.id, title: tr('payments.rejectTitle') || 'Reject payment',
    message: (tr('payments.rejectMsg') || 'Reject this payment?') + ' #' + p.id, withReason: true,
    confirmText: tr('payments.reject') || 'Reject', confirmBg: 'var(--red)', iconBg: 'var(--red-soft)', iconColor: 'var(--red)' }
}
function askDelete(p) {
  modal.value = { kind: 'delete', id: p.id, title: tr('common.delete') || 'Delete',
    message: (tr('payments.deleteMsg') || 'Delete this payment record?') + ' #' + p.id,
    confirmText: tr('common.delete') || 'Delete', confirmBg: 'var(--red)', iconBg: 'var(--red-soft)', iconColor: 'var(--red)' }
}
async function confirmModal() {
  const m = modal.value; if (!m || modalBusy.value) return
  modalBusy.value = true
  try {
    if (m.kind === 'confirm') await portalUsersApi.confirmPayment(m.id)
    else if (m.kind === 'reject') await portalUsersApi.rejectPayment(m.id) // TODO: pass reason.value once rejectPayment API accepts a body
    else if (m.kind === 'delete') await portalUsersApi.deletePayment(m.id)
    modalBusy.value = false; modal.value = null; reason.value = ''
    await load()
  } catch (e) { modalBusy.value = false; alert(e.response?.data?.detail || 'Error') }
}
onMounted(() => { ui.set({ title: tr('nav.payments') || 'Payments', search: true, searchPh: tr('payments.search') || 'Search payments…', onSearch: v => { query.value = v } }); load() })
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-del { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-del:hover { background: var(--red-soft); color: var(--red); }
.d2-search:focus, .d2-reason:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-btn-cancel:hover { background: var(--panel-2); }
@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
