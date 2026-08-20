<!-- Support inbox — his exact 1:1 handoff layout: ticket list (search + filter
     chips) + conversation pane with inline reply. Wired to portalUsersApi
     (getSupportMessages / getSupportTicket / replySupportTicket / close /
     reopen / unread). Adapter computeds map API rows to his field names. -->
<template>
  <div class="d2-support-layout" :style="{ display:'grid', gridTemplateColumns: gSupport, gap:'14px', alignItems:'start', height:'calc(100vh - 150px)' }">
    <!-- Ticket list column -->
    <div class="d2-support-list" :class="{'d2-support-hidden-mobile': supOpen}" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden;height:100%">
      <div style="padding:12px;border-bottom:1px solid var(--border)">
        <div style="position:relative;margin-bottom:8px">
          <span style="position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-3);display:flex"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4-4"></path></svg></span>
          <input :value="supSearch" @input="onSupSearch" :placeholder="tr('support.search') || 'Search tickets…'" class="d2-supsearch" style="width:100%;height:34px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:9px;padding:0 11px 0 32px;font:inherit;font-size:12.5px;outline:none">
        </div>
        <div style="display:flex;gap:5px">
          <button v-for="f in supFilters" :key="f.key" @click="f.on" :style="{ height:'28px', padding:'0 10px', border:'1px solid '+f.border, background:f.bg, color:f.color, borderRadius:'7px', font:'inherit', fontSize:'11.5px', fontWeight:f.weight, cursor:'pointer' }">{{ f.label }}</button>
        </div>
      </div>
      <div style="flex:1;overflow-y:auto">
        <button v-for="tk in ticketList" :key="tk.id" @click="tk.onSelect" class="d2-tkbtn" :style="{ display:'block', width:'100%', textAlign:'left', padding:'13px 16px', border:'none', borderBottom:'1px solid var(--border)', borderLeft:'3px solid '+tk.activeBar, background:tk.bg, cursor:'pointer' }">
          <div style="display:flex;align-items:center;gap:8px"><span style="font-weight:600;font-size:13px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)">{{ tk.user }}</span><span v-if="tk.unread" style="width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none"></span><span style="font-size:11px;color:var(--text-3)">{{ tk.updated }}</span></div>
          <div style="font-size:12.5px;color:var(--text-2);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ tk.subject }}</div>
          <div style="display:flex;align-items:center;gap:7px;margin-top:7px"><span :style="{ display:'inline-block', fontSize:'10.5px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', color:tk.statusColor, background:tk.statusBg }">{{ tk.statusLabel }}</span><span style="display:inline-flex;align-items:center;gap:4px;font-size:10.5px;color:var(--text-3)"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h16v11H9l-4 3z"></path></svg>{{ tk.replies }}</span></div>
        </button>
      </div>
    </div>

    <!-- Conversation column -->
    <div class="d2-support-thread" :class="{'d2-support-hidden-mobile': supEmpty}" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden;height:100%">
      <div v-if="supEmpty" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text-3)"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" style="margin-bottom:12px"><path d="M4 5h16v11H9l-4 3z"></path></svg><div style="font-size:14px">{{ tr('support.selectTicket') || 'Select a ticket to view the conversation' }}</div></div>
      <template v-if="supOpen">
        <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px">
          <button @click="selected = null" class="d2-mobile-only d2-support-back" :aria-label="tr('common.back') || 'Back'">‹</button>
          <div style="flex:1;min-width:0"><div style="font-weight:650;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ supThread.subject }}</div><div style="font-size:12px;color:var(--text-3)">{{ supThread.user }} · #{{ supThread.id }}</div></div>
          <button v-if="supThread.isClosed" @click="supReopen" class="d2-headbtn" style="height:32px;padding:0 12px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('support.reopen') || 'Reopen' }}</button>
          <button v-if="supThread.notClosed" @click="supClose" class="d2-headbtn" style="height:32px;padding:0 12px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('support.close') || 'Close' }}</button>
          <button @click="supDelete" class="d2-delbtn" style="width:32px;height:32px;border-radius:8px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
        </div>
        <div ref="convRef" style="flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px">
          <div v-for="(m, i) in supThreadMsgs" :key="i" :style="{ display:'flex', justifyContent:m.justify }"><div :style="{ maxWidth:'78%', padding:'10px 13px', borderRadius:'12px', background:m.bg, color:m.color, fontSize:'13px', lineHeight:'1.45' }"><div>{{ m.text }}</div><div style="font-size:10.5px;opacity:.7;margin-top:4px;text-align:right">{{ m.time }}</div></div></div>
        </div>
        <div style="padding:14px 18px;border-top:1px solid var(--border);display:flex;gap:10px;align-items:flex-end">
          <textarea :value="supReply" @input="onSupReply" @keydown.ctrl.enter="sendSupReply" @keydown.meta.enter="sendSupReply" :placeholder="tr('support.replyPlaceholder') || tr('support.typeReply') || 'Type a reply… (Ctrl+Enter to send)'" class="d2-supta" style="flex:1;min-height:42px;max-height:120px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;font-size:13px;outline:none"></textarea>
          <button @click="sendSupReply" :disabled="!supReply.trim() || replying" class="d2-sendbtn" style="height:42px;padding:0 16px;border:none;background:var(--accent);color:#fff;border-radius:10px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;flex:none;display:flex;align-items:center;gap:7px"><span v-if="replying" style="width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ tr('support.send') || 'Send' }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { portalUsersApi } from '../../api'
import { formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n({ useScope: 'global' })
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const tickets = ref([])
const selected = ref(null)
const replyText = ref('')
const replying = ref(false)
const loading = ref(false)
const unreadCount = ref(0)
const statusFilter = ref('')
const supSearch = ref('')
const convRef = ref(null)

const messages = computed(() => {
  const s = selected.value
  if (!s) return []
  const root = (s.message != null) ? [{ message: s.message, direction: s.direction || 'user', created_at: s.created_at }] : []
  return [...root, ...(s.replies || s.messages || s.thread || [])]
})

async function load() {
  loading.value = true
  try { const params = { limit: 100 }; if (statusFilter.value) params.status = statusFilter.value; const { data } = await portalUsersApi.getSupportMessages(params); tickets.value = data.items || (Array.isArray(data) ? data : []) }
  catch (e) { console.error(e) } finally { loading.value = false }
  loadUnread()
}
async function loadUnread() { try { const { data } = await portalUsersApi.getSupportUnread(); unreadCount.value = data.unread ?? data.unread_count ?? data.count ?? 0 } catch (_) {} }
async function open(tk) {
  try { const { data } = await portalUsersApi.getSupportTicket(tk.id); selected.value = data; await nextTick(); scrollDown(); if (tk.unread_count) { tk.unread_count = 0; loadUnread() } }
  catch (e) { alert(e.response?.data?.detail || 'Error') }
}
async function reply() {
  if (!replyText.value.trim()) return
  replying.value = true
  try { await portalUsersApi.replySupportTicket(selected.value.id, { message: replyText.value.trim() }); replyText.value = ''; await open(selected.value) }
  catch (e) { alert(e.response?.data?.detail || 'Error') } finally { replying.value = false }
}
async function close() { try { await portalUsersApi.closeSupportTicket(selected.value.id); await open(selected.value); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function reopen() { try { await portalUsersApi.reopenSupportTicket(selected.value.id); await open(selected.value); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
function isAdmin(m) { return m.direction === 'admin' || !!(m.is_admin ?? m.from_admin ?? m.is_staff) }
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }
function scrollDown() { if (convRef.value) convRef.value.scrollTop = convRef.value.scrollHeight }

// ── Adapter to his markup field names ────────────────────────────────────
const SC = { open: ['var(--green)', 'var(--green-soft)'], answered: ['var(--blue)', 'var(--blue-soft)'], closed: ['var(--text-3)', 'var(--panel-3)'] }
function statusMeta(s) { return SC[String(s || '').toLowerCase()] || ['var(--text-3)', 'var(--panel-3)'] }
function statusLabel(s) { const k = String(s || '').toLowerCase(); return (k && (tr('support.status_' + k) || tr('support.' + k))) || (k ? k.charAt(0).toUpperCase() + k.slice(1) : '') }
function ticketUser(tk) { return tk.username || tk.email || ('#' + tk.id) }
function replyCount(tk) { return tk.reply_count ?? tk.replies_count ?? (Array.isArray(tk.replies) ? tk.replies.length : 0) }

const gSupport = '340px 1fr'

const supFilters = computed(() => {
  const opts = [
    { key: '', label: tr('support.allStatuses') || 'All' },
    { key: 'open', label: tr('support.status_open') || 'Open' },
    { key: 'answered', label: tr('support.status_answered') || 'Answered' },
    { key: 'closed', label: tr('support.status_closed') || 'Closed' },
  ]
  return opts.map(o => {
    const active = statusFilter.value === o.key
    return {
      key: o.key,
      label: o.label,
      on: () => { statusFilter.value = o.key; load() },
      border: active ? 'var(--accent)' : 'var(--border-strong)',
      bg: active ? 'var(--accent-soft)' : 'var(--panel)',
      color: active ? 'var(--accent)' : 'var(--text-2)',
      weight: active ? 600 : 500,
    }
  })
})

const ticketList = computed(() => {
  const q = supSearch.value.trim().toLowerCase()
  let rows = tickets.value
  if (q) rows = rows.filter(tk => (ticketUser(tk) + ' ' + (tk.subject || '') + ' #' + tk.id).toLowerCase().includes(q))
  return rows.map(tk => {
    const [sc, sbg] = statusMeta(tk.status)
    const on = selected.value?.id === tk.id
    return {
      id: tk.id,
      user: ticketUser(tk),
      unread: (tk.unread_count || 0) > 0,
      updated: tk.updated_at ? fmtDate(tk.updated_at) : (tk.created_at ? fmtDate(tk.created_at) : ''),
      subject: tk.subject || (tr('support.noSubject') || 'No subject'),
      statusColor: sc,
      statusBg: sbg,
      statusLabel: statusLabel(tk.status),
      replies: replyCount(tk),
      activeBar: on ? 'var(--accent)' : 'transparent',
      bg: on ? 'var(--accent-soft)' : 'transparent',
      onSelect: () => open(tk),
    }
  })
})

const supEmpty = computed(() => !selected.value)
const supOpen = computed(() => !!selected.value)
const supThread = computed(() => {
  const s = selected.value
  if (!s) return { subject: '', user: '', id: '', isClosed: false, notClosed: false }
  const closed = String(s.status || '').toLowerCase() === 'closed'
  return {
    subject: s.subject || (tr('support.noSubject') || 'No subject'),
    user: s.username || s.email || '',
    id: s.id,
    isClosed: closed,
    notClosed: !closed,
  }
})
const supThreadMsgs = computed(() => messages.value.map(m => {
  const admin = isAdmin(m)
  return {
    text: m.message || m.body || m.text,
    time: m.created_at ? fmtDate(m.created_at) : '',
    justify: admin ? 'flex-end' : 'flex-start',
    bg: admin ? 'var(--accent)' : 'var(--panel-2)',
    color: admin ? '#fff' : 'var(--text)',
  }
}))

const supReply = computed(() => replyText.value)
function onSupReply(e) { replyText.value = e.target.value }
function onSupSearch(e) { supSearch.value = e.target.value }
function sendSupReply() { reply() }
function supClose() { close() }
async function supReopen() { reopen() }
async function supDelete() {
  if (!selected.value) return
  if (!await d2confirm((tr('support.deleteConfirm') || 'Delete this ticket?'))) return
  try {
    if (portalUsersApi.deleteSupportTicket) { await portalUsersApi.deleteSupportTicket(selected.value.id) }
    else if (portalUsersApi.closeSupportTicket) { await portalUsersApi.closeSupportTicket(selected.value.id) }
    selected.value = null
    await load()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
}

onMounted(() => { ui.set({ title: tr('nav.support') || 'Support' }); load() })
</script>

<style scoped>
.d2-tkbtn:hover { background: var(--panel-2) !important; }
.d2-headbtn:hover { background: var(--panel-2); }
.d2-delbtn:hover { background: var(--red-soft); color: var(--red); border-color: var(--red-soft); }
.d2-sendbtn:hover { background: var(--accent-2); }
.d2-sendbtn:disabled { opacity: .55; cursor: not-allowed; }
.d2-supsearch:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-supta:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-support-back { width:32px;height:32px;border:1px solid var(--border-strong);border-radius:8px;background:var(--panel);color:var(--text);font:inherit;font-size:24px;line-height:1; }
@media (max-width:900px) {
  .d2-support-layout { display:block !important;height:calc(100dvh - 86px) !important; }
  .d2-support-list,.d2-support-thread { height:100% !important; }
  .d2-support-hidden-mobile { display:none !important; }
  .d2-support-thread textarea { min-width:0; }
}
@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
