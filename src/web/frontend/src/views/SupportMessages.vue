<template>
  <div class="sm-app" :data-details="showDetails ? 'on' : 'off'">
    <!-- ─── Inbox column ─────────────────────────────────────── -->
    <section class="sm-inbox">
      <div class="sm-inbox-head">
        <div class="sm-inbox-title-row">
          <div class="sm-inbox-title">
            {{ $t('support.title') }}
            <span class="sm-count">{{ visibleCount }}</span>
          </div>
        </div>
        <div class="sm-search">
          <i class="mdi mdi-magnify"></i>
          <input
            ref="searchInput"
            type="search"
            v-model="search"
            :placeholder="$t('common.search') || 'Search tickets, customers, IDs…'"
            @input="onSearchInput"
          />
          <span class="sm-kbd">/</span>
        </div>
      </div>

      <div class="sm-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="sm-tab"
          :class="{ active: filter === tab.key }"
          @click="filter = tab.key; loadTickets()"
        >
          {{ tab.label }} <span class="sm-tab-badge">{{ tab.count }}</span>
        </button>
      </div>

      <div class="sm-ticket-list">
        <div v-if="loading && tickets.length === 0" class="sm-empty">
          <div class="spinner-border spinner-border-sm"></div>
        </div>

        <div v-else-if="tickets.length === 0" class="sm-empty">
          <i class="mdi mdi-magnify sm-empty-icon"></i>
          <h3>{{ $t('support.noTickets') }}</h3>
          <p>{{ $t('support.noTicketsHint') || 'Try a different filter or search.' }}</p>
        </div>

        <div
          v-else
          v-for="t in tickets"
          :key="t.id"
          class="sm-row"
          :class="{ unread: t.unread_count > 0, selected: selectedTicketId === t.id }"
          @click="selectTicket(t)"
        >
          <div class="sm-row-top">
            <div class="sm-avatar" :style="{ background: avatarColor(t.username || t.email) }">
              {{ initials(t.username || t.email) }}
            </div>
            <span class="sm-row-customer">{{ t.username || t.email }}</span>
            <span v-if="t.unread_count > 0" class="sm-unread-dot"></span>
            <span class="sm-row-time">{{ shortDate(t.last_activity_at || t.created_at) }}</span>
          </div>
          <div class="sm-row-subject">{{ t.subject }}</div>
          <div class="sm-row-meta">
            <span class="sm-row-id">{{ shortId(t.id) }}</span>
            <span class="sm-row-sep">·</span>
            <span class="sm-pill" :class="'sm-pill--' + statusKey(t.status)">
              <span class="sm-pill-dot"></span>{{ statusLabel(t.status) }}
            </span>
            <span class="sm-row-sep">·</span>
            <span>{{ t.reply_count || 0 }} {{ $t('support.replies') }}</span>
          </div>
        </div>
      </div>

      <!-- pagination -->
      <div v-if="totalPages > 1" class="sm-pager">
        <small>{{ total }} {{ $t('support.total') || 'total' }}</small>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="page--; loadTickets()">←</button>
          <button class="btn btn-outline-secondary disabled">{{ page }}/{{ totalPages }}</button>
          <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="page++; loadTickets()">→</button>
        </div>
      </div>
    </section>

    <!-- ─── Thread column ────────────────────────────────────── -->
    <section class="sm-thread">
      <div v-if="!selectedTicket" class="sm-empty sm-empty--center">
        <i class="mdi mdi-message-text-outline sm-empty-icon"></i>
        <h3>{{ $t('support.selectTicket') || 'Select a ticket' }}</h3>
        <p>{{ $t('support.selectTicketHint') || 'Pick a conversation from the list to view the thread.' }}</p>
      </div>

      <template v-else>
        <header class="sm-thread-head">
          <button class="sm-back-btn d-lg-none" @click="selectedTicket = null" aria-label="Back">
            <i class="mdi mdi-arrow-left"></i>
          </button>
          <div class="sm-avatar sm-avatar--lg" :style="{ background: avatarColor(selectedTicket.username || selectedTicket.email) }">
            {{ initials(selectedTicket.username || selectedTicket.email) }}
          </div>
          <div class="sm-thread-info">
            <div class="sm-thread-title">
              {{ selectedTicket.subject }}
              <span class="sm-pill" :class="'sm-pill--' + statusKey(selectedTicket.status)">
                <span class="sm-pill-dot"></span>{{ statusLabel(selectedTicket.status) }}
              </span>
            </div>
            <div class="sm-thread-meta">
              <span>{{ shortId(selectedTicket.id) }}</span>
              <span class="sm-row-sep">·</span>
              <span class="sm-thread-email">{{ selectedTicket.email }}</span>
              <span v-if="selectedTicket.telegram_id" class="sm-row-sep">·</span>
              <span v-if="selectedTicket.telegram_id">TG: {{ selectedTicket.telegram_id }}</span>
            </div>
          </div>
          <div class="sm-thread-actions">
            <button
              v-if="selectedTicket.status !== 'closed'"
              class="btn btn-sm btn-outline-secondary"
              @click="closeTicket"
            >
              <i class="mdi mdi-check"></i> {{ $t('support.close') }}
            </button>
            <button
              v-if="selectedTicket.status === 'closed'"
              class="btn btn-sm btn-outline-warning"
              @click="reopenTicket"
            >
              <i class="mdi mdi-reload"></i> {{ $t('support.reopen') }}
            </button>
            <button class="btn btn-sm btn-outline-danger" @click="deleteTicket" :title="$t('support.delete')">
              <i class="mdi mdi-trash-can-outline"></i>
            </button>
            <button class="sm-icon-btn" @click="showDetails = !showDetails" :title="$t('support.toggleDetails') || 'Toggle details'">
              <i class="mdi mdi-information-outline"></i>
            </button>
          </div>
        </header>

        <div ref="threadBody" class="sm-thread-body">
          <!-- Original message -->
          <div class="sm-msg">
            <div class="sm-avatar sm-avatar--md" :style="{ background: avatarColor(selectedTicket.username || selectedTicket.email) }">
              {{ initials(selectedTicket.username || selectedTicket.email) }}
            </div>
            <div class="sm-msg-content">
              <div class="sm-msg-head">
                <span class="sm-msg-author">{{ selectedTicket.username || selectedTicket.email }}</span>
                <span class="sm-msg-time">{{ formatDateTime(selectedTicket.created_at) }}</span>
              </div>
              <div class="sm-msg-bubble">{{ selectedTicket.message }}</div>
            </div>
          </div>
          <!-- Replies -->
          <div
            v-for="reply in (selectedTicket.replies || [])"
            :key="reply.id"
            class="sm-msg"
            :class="{ 'sm-msg--you': reply.direction === 'admin' }"
          >
            <div
              class="sm-avatar sm-avatar--md"
              :class="{ 'sm-avatar--you': reply.direction === 'admin' }"
              :style="reply.direction === 'admin' ? null : { background: avatarColor(selectedTicket.username || selectedTicket.email) }"
            >
              {{ reply.direction === 'admin' ? 'A' : initials(selectedTicket.username || selectedTicket.email) }}
            </div>
            <div class="sm-msg-content">
              <div class="sm-msg-head">
                <span class="sm-msg-author">{{ reply.direction === 'admin' ? ($t('support.you') || 'You · Support') : (selectedTicket.username || selectedTicket.email) }}</span>
                <span class="sm-msg-time">{{ formatDateTime(reply.created_at) }}</span>
              </div>
              <div class="sm-msg-bubble">{{ reply.message }}</div>
            </div>
          </div>

          <div v-if="selectedTicket.status === 'closed'" class="sm-system-msg">
            <span class="sm-pill sm-pill--closed"><span class="sm-pill-dot"></span>closed</span>
            <span>{{ $t('support.closedSystem') || 'Ticket closed.' }}</span>
          </div>
        </div>

        <!-- Composer -->
        <div class="sm-composer-wrap">
          <div v-if="selectedTicket.status === 'closed'" class="sm-closed-banner">
            <i class="mdi mdi-lock-outline"></i>
            <span>{{ $t('support.closedBanner') || 'Ticket closed. Customer can reply by email to reopen.' }}</span>
            <button class="btn btn-sm btn-outline-warning" @click="reopenTicket">
              <i class="mdi mdi-reload"></i> {{ $t('support.reopen') }}
            </button>
          </div>
          <div v-else class="sm-composer">
            <textarea
              ref="composerText"
              v-model="replyText"
              :placeholder="$t('support.replyPlaceholder')"
              maxlength="4000"
              @keydown.ctrl.enter="sendReply"
              @keydown.meta.enter="sendReply"
            ></textarea>
            <div class="sm-composer-foot">
              <small class="text-muted">⌘/Ctrl + Enter</small>
              <button
                class="btn btn-primary btn-sm"
                @click="sendReply"
                :disabled="replying || !replyText.trim()"
              >
                <span v-if="replying" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="mdi mdi-send me-1"></i>
                {{ $t('support.send') }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </section>

    <!-- ─── Details column ───────────────────────────────────── -->
    <aside v-if="selectedTicket && showDetails" class="sm-details">
      <header class="sm-details-head">
        <h4>{{ $t('support.customer') || 'Customer' }}</h4>
        <button class="sm-icon-btn" @click="showDetails = false" :title="$t('common.close') || 'Close'">
          <i class="mdi mdi-close"></i>
        </button>
      </header>

      <div class="sm-details-section">
        <div class="sm-details-avatar" :style="{ background: avatarColor(selectedTicket.username || selectedTicket.email) }">
          {{ initials(selectedTicket.username || selectedTicket.email) }}
        </div>
        <div class="sm-details-name">{{ selectedTicket.username || '—' }}</div>
        <div class="sm-details-email">{{ selectedTicket.email }}</div>
      </div>

      <div class="sm-details-section">
        <div class="sm-details-row">
          <span class="sm-details-key">{{ $t('support.status_' + selectedTicket.status) }}</span>
          <span class="sm-pill" :class="'sm-pill--' + statusKey(selectedTicket.status)">
            <span class="sm-pill-dot"></span>{{ statusLabel(selectedTicket.status) }}
          </span>
        </div>
        <div v-if="selectedTicket.telegram_id" class="sm-details-row">
          <span class="sm-details-key">Telegram ID</span>
          <span class="sm-details-val">{{ selectedTicket.telegram_id }}</span>
        </div>
        <div class="sm-details-row">
          <span class="sm-details-key">{{ $t('support.replies') }}</span>
          <span class="sm-details-val">{{ (selectedTicket.replies || []).length }}</span>
        </div>
        <div class="sm-details-row">
          <span class="sm-details-key">{{ $t('support.openedAt') || 'Opened' }}</span>
          <span class="sm-details-val">{{ formatDate(selectedTicket.created_at) }}</span>
        </div>
        <div v-if="selectedTicket.last_activity_at" class="sm-details-row">
          <span class="sm-details-key">{{ $t('support.lastActivity') || 'Last activity' }}</span>
          <span class="sm-details-val">{{ formatDate(selectedTicket.last_activity_at) }}</span>
        </div>
      </div>

      <div class="sm-details-section">
        <h5 class="sm-details-h5">{{ $t('support.actions') || 'Actions' }}</h5>
        <button
          v-if="selectedTicket.status !== 'closed'"
          class="btn btn-sm btn-outline-secondary w-100 mb-2"
          @click="closeTicket"
        >
          <i class="mdi mdi-check"></i> {{ $t('support.close') }}
        </button>
        <button
          v-if="selectedTicket.status === 'closed'"
          class="btn btn-sm btn-outline-warning w-100 mb-2"
          @click="reopenTicket"
        >
          <i class="mdi mdi-reload"></i> {{ $t('support.reopen') }}
        </button>
        <button class="btn btn-sm btn-outline-danger w-100" @click="deleteTicket">
          <i class="mdi mdi-trash-can-outline"></i> {{ $t('support.delete') }}
        </button>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalUsersApi } from '../api'

const { t } = useI18n()

const tickets       = ref([])
const total         = ref(0)
const page          = ref(1)
const perPage       = 20
const filter        = ref('all')           // all | open | answered | closed
const search        = ref('')
const loading       = ref(false)
const selectedTicket = ref(null)
const replyText     = ref('')
const replying      = ref(false)
const showDetails   = ref(true)
const threadBody    = ref(null)
const searchInput   = ref(null)
const composerText  = ref(null)

let searchTimeout = null

const totalPages    = computed(() => Math.ceil(total.value / perPage))
const visibleCount  = computed(() => tickets.value.length)
const selectedTicketId = computed(() => selectedTicket.value?.id)

const tabs = computed(() => [
  { key: 'all',      label: t('support.allStatuses')    || 'All',      count: total.value },
  { key: 'open',     label: t('support.status_open')    || 'Open',     count: countByStatus('open') },
  { key: 'answered', label: t('support.status_answered') || 'Replied', count: countByStatus('answered') },
  { key: 'closed',   label: t('support.status_closed')  || 'Closed',   count: countByStatus('closed') },
])

function countByStatus(s) {
  return tickets.value.filter(x => x.status === s).length
}

const loadTickets = async () => {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage }
    if (filter.value && filter.value !== 'all') params.status = filter.value
    if (search.value) params.search = search.value
    const { data } = await portalUsersApi.getSupportMessages(params)
    tickets.value = data.items || []
    total.value   = data.total || 0
  } catch (e) { /* swallow */ }
  loading.value = false
}

const selectTicket = async (ticket) => {
  try {
    const { data } = await portalUsersApi.getSupportTicket(ticket.id)
    selectedTicket.value = data
    replyText.value = ''
    const idx = tickets.value.findIndex(x => x.id === ticket.id)
    if (idx >= 0) tickets.value[idx].unread_count = 0
    await nextTick()
    if (threadBody.value) threadBody.value.scrollTop = threadBody.value.scrollHeight
  } catch (e) { /* swallow */ }
}

const sendReply = async () => {
  if (!replyText.value.trim() || !selectedTicket.value) return
  replying.value = true
  try {
    await portalUsersApi.replySupportTicket(
      selectedTicket.value.id,
      { message: replyText.value.trim() }
    )
    replyText.value = ''
    await selectTicket(selectedTicket.value)
    await loadTickets()
  } catch (e) { /* swallow */ }
  replying.value = false
}

const closeTicket = async () => {
  if (!selectedTicket.value) return
  try {
    await portalUsersApi.closeSupportTicket(selectedTicket.value.id)
    selectedTicket.value.status = 'closed'
    await loadTickets()
  } catch (e) { /* swallow */ }
}

const reopenTicket = async () => {
  if (!selectedTicket.value) return
  try {
    await portalUsersApi.reopenSupportTicket(selectedTicket.value.id)
    selectedTicket.value.status = 'open'
    await loadTickets()
  } catch (e) { /* swallow */ }
}

const deleteTicket = async () => {
  if (!selectedTicket.value) return
  if (!confirm(t('support.deleteConfirm'))) return
  try {
    await portalUsersApi.deleteSupportTicket(selectedTicket.value.id)
    selectedTicket.value = null
    await loadTickets()
  } catch (e) { /* swallow */ }
}

const onSearchInput = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => { page.value = 1; loadTickets() }, 350)
}

// Keyboard: "/" focuses search
const onKey = (e) => {
  if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
    e.preventDefault()
    searchInput.value?.focus()
  }
}

// ── Helpers ────────────────────────────────────────────────────
const initials = (name) => {
  const s = String(name || '?').trim()
  if (!s) return '?'
  const parts = s.split(/\s+|[._@]/).filter(Boolean).slice(0, 2)
  return parts.map(p => p[0]).join('').toUpperCase()
}

const avatarColor = (name) => {
  // Stable hash → HSL hue. Same name always gets the same color.
  let h = 0
  const s = String(name || '')
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  const hue = h % 360
  return `hsl(${hue}, 70%, 55%)`
}

const statusKey = (s) => s === 'answered' ? 'replied' : s
const statusLabel = (s) => {
  const map = {
    open: t('support.status_open') || 'open',
    answered: t('support.status_answered') || 'replied',
    closed: t('support.status_closed') || 'closed',
  }
  return map[s] || s
}

const shortId = (id) => {
  if (id == null) return ''
  const s = String(id)
  return s.length > 8 ? `T-${s.slice(-6).toUpperCase()}` : `T-${s}`
}

const shortDate = (d) => {
  if (!d) return ''
  const dt = new Date(d)
  const now = new Date()
  if (dt.toDateString() === now.toDateString()) {
    return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return dt.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

const formatDate     = (d) => d ? new Date(d).toLocaleDateString() : ''
const formatDateTime = (d) => d ? new Date(d).toLocaleString() : ''

onMounted(() => {
  loadTickets()
  document.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
})
</script>

<style scoped>
/* ─── Layout — 3 columns on desktop, collapses on mobile ─────── */
.sm-app {
  display: grid;
  grid-template-columns: 320px 1fr 320px;
  gap: 0;
  height: calc(100vh - var(--vxy-topbar-h, 64px) - 24px);
  background: var(--vxy-card-bg);
  border: 1px solid var(--vxy-border);
  border-radius: var(--vxy-card-radius, 0.5rem);
  overflow: hidden;
  font-size: 14px;
}
.sm-app[data-details="off"]            { grid-template-columns: 320px 1fr; }
.sm-app[data-details="off"] .sm-details { display: none; }
@media (max-width: 1100px) {
  .sm-app, .sm-app[data-details="on"] { grid-template-columns: 280px 1fr; }
  .sm-app .sm-details                 { display: none !important; }
}
@media (max-width: 768px) {
  .sm-app                  { grid-template-columns: 1fr !important; }
  .sm-app .sm-inbox        { display: block; }
  .sm-app:has(.sm-thread-head) .sm-inbox  { display: none; }
  .sm-app:not(:has(.sm-thread-head)) .sm-thread { display: none; }
}

/* ─── Inbox (left column) ──────────────────────────────────── */
.sm-inbox {
  display: flex; flex-direction: column;
  border-right: 1px solid var(--vxy-border);
  background: var(--vxy-body-bg);
  min-width: 0;
}
.sm-inbox-head {
  padding: 16px 16px 8px;
  border-bottom: 1px solid var(--vxy-border);
  flex-shrink: 0;
}
.sm-inbox-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.sm-inbox-title {
  font-weight: 600; font-size: 15px;
  color: var(--vxy-heading);
  display: flex; align-items: center; gap: 8px;
}
.sm-count {
  font-size: 11px; font-weight: 500;
  color: var(--vxy-muted);
  background: var(--vxy-hover-bg);
  padding: 2px 8px;
  border-radius: 999px;
}

.sm-search {
  position: relative;
  display: flex; align-items: center;
}
.sm-search i { position: absolute; left: 10px; color: var(--vxy-muted); font-size: 16px; }
.sm-search input {
  width: 100%;
  padding: 8px 36px 8px 32px;
  background: var(--vxy-card-bg);
  border: 1px solid var(--vxy-border);
  border-radius: 8px;
  color: var(--vxy-text);
  font-size: 13px;
  outline: none;
  transition: border-color .15s ease;
}
.sm-search input:focus { border-color: var(--vxy-primary); }
.sm-kbd {
  position: absolute; right: 8px;
  font-family: var(--bs-font-monospace, monospace);
  font-size: 10px;
  color: var(--vxy-muted);
  background: var(--vxy-hover-bg);
  padding: 2px 6px;
  border-radius: 4px;
  pointer-events: none;
}

.sm-tabs {
  display: flex; gap: 2px;
  padding: 8px 12px;
  background: var(--vxy-body-bg);
  border-bottom: 1px solid var(--vxy-border);
  flex-shrink: 0;
}
.sm-tab {
  background: transparent; border: 0;
  padding: 6px 10px;
  font-size: 12.5px; font-weight: 500;
  color: var(--vxy-muted);
  border-radius: 6px;
  display: inline-flex; gap: 4px; align-items: center;
}
.sm-tab:hover { color: var(--vxy-text); background: var(--vxy-hover-bg); }
.sm-tab.active {
  color: var(--vxy-primary);
  background: var(--vxy-primary-light);
}
.sm-tab-badge {
  font-size: 10.5px; font-weight: 500;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--vxy-hover-bg);
  color: var(--vxy-muted);
}
.sm-tab.active .sm-tab-badge {
  background: rgba(var(--vxy-primary-rgb), .2);
  color: var(--vxy-primary);
}

.sm-ticket-list {
  flex: 1; overflow-y: auto;
  padding: 4px;
}

.sm-row {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background .12s ease;
  border-left: 3px solid transparent;
}
.sm-row:hover { background: var(--vxy-hover-bg); }
.sm-row.selected {
  background: var(--vxy-selected-bg);
  border-left-color: var(--vxy-primary);
}
.sm-row.unread .sm-row-customer,
.sm-row.unread .sm-row-subject { font-weight: 600; color: var(--vxy-heading); }

.sm-row-top {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}
.sm-row-customer {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 13px;
  color: var(--vxy-text);
}
.sm-unread-dot {
  width: 7px; height: 7px;
  background: var(--vxy-primary);
  border-radius: 50%;
  flex-shrink: 0;
}
.sm-row-time {
  font-size: 11px;
  color: var(--vxy-muted);
  flex-shrink: 0;
}
.sm-row-subject {
  font-size: 13px;
  color: var(--vxy-text);
  margin-bottom: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sm-row-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 11px;
  color: var(--vxy-muted);
}
.sm-row-id { font-family: var(--bs-font-monospace, monospace); }
.sm-row-sep { opacity: .5; }

/* ─── Avatar ───────────────────────────────────────────────── */
.sm-avatar {
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%;
  font-weight: 600; font-size: 11px;
  color: #fff;
  flex-shrink: 0;
  text-transform: uppercase;
}
.sm-avatar--md { width: 36px; height: 36px; font-size: 13px; }
.sm-avatar--lg { width: 44px; height: 44px; font-size: 16px; }
.sm-avatar--you {
  background: linear-gradient(135deg, var(--vxy-primary), var(--vxy-primary-dark)) !important;
}

/* ─── Pills (status indicator) ─────────────────────────────── */
.sm-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px; font-weight: 500;
  text-transform: capitalize;
  background: var(--vxy-hover-bg);
  color: var(--vxy-muted);
}
.sm-pill-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.sm-pill--open    { background: rgba(var(--vxy-primary-rgb), .14); color: var(--vxy-primary); }
.sm-pill--replied { background: var(--vxy-success-light); color: var(--vxy-success); }
.sm-pill--closed  { background: var(--vxy-hover-bg); color: var(--vxy-muted); }

.sm-pager {
  padding: 8px 12px;
  border-top: 1px solid var(--vxy-border);
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}

/* ─── Thread (middle column) ──────────────────────────────── */
.sm-thread {
  display: flex; flex-direction: column;
  background: var(--vxy-card-bg);
  min-width: 0;
}

.sm-thread-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--vxy-border);
  flex-shrink: 0;
  background: var(--vxy-card-bg);
}
.sm-back-btn {
  background: transparent; border: 0;
  color: var(--vxy-text); font-size: 20px;
  width: 32px; height: 32px;
  border-radius: 6px;
}
.sm-back-btn:hover { background: var(--vxy-hover-bg); }

.sm-thread-info {
  flex: 1; min-width: 0;
}
.sm-thread-title {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  font-weight: 600; font-size: 15px;
  color: var(--vxy-heading);
  margin-bottom: 3px;
}
.sm-thread-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 12px;
  color: var(--vxy-muted);
}
.sm-thread-email { font-family: var(--bs-font-monospace, monospace); }
.sm-thread-actions {
  display: flex; gap: 6px; align-items: center;
  flex-shrink: 0;
}
.sm-icon-btn {
  background: transparent; border: 1px solid var(--vxy-border);
  width: 32px; height: 32px;
  border-radius: 6px;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--vxy-muted);
  font-size: 16px;
  transition: color .12s ease, border-color .12s ease;
}
.sm-icon-btn:hover { color: var(--vxy-text); border-color: var(--vxy-text); }

.sm-thread-body {
  flex: 1; overflow-y: auto;
  padding: 16px;
  background: var(--vxy-body-bg);
  display: flex; flex-direction: column; gap: 14px;
}

.sm-msg {
  display: flex; gap: 10px; align-items: flex-start;
  max-width: 78%;
}
.sm-msg--you {
  flex-direction: row-reverse;
  align-self: flex-end;
}
.sm-msg-content {
  display: flex; flex-direction: column;
  min-width: 0;
}
.sm-msg-head {
  display: flex; align-items: baseline; gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}
.sm-msg--you .sm-msg-head { justify-content: flex-end; }
.sm-msg-author {
  font-weight: 600;
  color: var(--vxy-text);
}
.sm-msg-time { color: var(--vxy-muted); font-size: 11px; }
.sm-msg-bubble {
  padding: 10px 14px;
  background: var(--vxy-card-bg);
  border: 1px solid var(--vxy-border);
  border-radius: 12px;
  border-top-left-radius: 4px;
  font-size: 14px; line-height: 1.5;
  color: var(--vxy-text);
  white-space: pre-wrap;
  word-wrap: break-word;
}
.sm-msg--you .sm-msg-bubble {
  background: var(--vxy-primary);
  color: #fff;
  border-color: var(--vxy-primary);
  border-top-left-radius: 12px;
  border-top-right-radius: 4px;
}

.sm-system-msg {
  align-self: center;
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  background: var(--vxy-hover-bg);
  border-radius: 999px;
  font-size: 12px;
  color: var(--vxy-muted);
}

.sm-composer-wrap {
  border-top: 1px solid var(--vxy-border);
  padding: 12px 16px;
  background: var(--vxy-card-bg);
  flex-shrink: 0;
}
.sm-composer textarea {
  width: 100%;
  min-height: 80px;
  resize: vertical;
  padding: 10px 12px;
  background: var(--vxy-input-bg);
  border: 1px solid var(--vxy-input-border);
  border-radius: 8px;
  color: var(--vxy-input-text);
  font-size: 14px; font-family: inherit;
  outline: none;
}
.sm-composer textarea:focus { border-color: var(--vxy-primary); }
.sm-composer-foot {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 8px;
}
.sm-closed-banner {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  background: var(--vxy-hover-bg);
  border-radius: 8px;
  font-size: 13px;
  color: var(--vxy-text);
}
.sm-closed-banner i { font-size: 18px; color: var(--vxy-muted); }

/* ─── Empty states ─────────────────────────────────────────── */
.sm-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 20px;
  text-align: center;
  color: var(--vxy-muted);
}
.sm-empty--center { flex: 1; }
.sm-empty-icon { font-size: 48px; margin-bottom: 12px; opacity: .5; }
.sm-empty h3 { font-size: 15px; margin: 0 0 4px; color: var(--vxy-heading); }
.sm-empty p { font-size: 13px; margin: 0; }

/* ─── Details panel (right column) ─────────────────────────── */
.sm-details {
  border-left: 1px solid var(--vxy-border);
  background: var(--vxy-body-bg);
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.sm-details-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--vxy-border);
}
.sm-details-head h4 {
  margin: 0;
  font-size: 13px; font-weight: 600;
  color: var(--vxy-heading);
  text-transform: uppercase;
  letter-spacing: .04em;
}
.sm-details-section {
  padding: 16px;
  border-bottom: 1px solid var(--vxy-border);
}
.sm-details-section:last-child { border-bottom: 0; }
.sm-details-avatar {
  width: 56px; height: 56px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 20px;
  margin: 0 auto 10px;
}
.sm-details-name {
  text-align: center;
  font-weight: 600; font-size: 15px;
  color: var(--vxy-heading);
}
.sm-details-email {
  text-align: center;
  font-size: 12px;
  color: var(--vxy-muted);
  font-family: var(--bs-font-monospace, monospace);
}
.sm-details-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0;
  font-size: 12.5px;
}
.sm-details-key { color: var(--vxy-muted); }
.sm-details-val { color: var(--vxy-text); font-weight: 500; }
.sm-details-h5 {
  font-size: 11px; font-weight: 600;
  color: var(--vxy-muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin: 0 0 8px;
}
</style>
