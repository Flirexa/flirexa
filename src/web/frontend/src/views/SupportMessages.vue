<template>
  <div class="support-messages-page">
    <div class="d-flex flex-column flex-md-row justify-content-between align-items-stretch align-items-md-center gap-2 mb-4 mobile-toolbar">
      <div class="d-flex align-items-center gap-2">
        <h4 class="mb-0"><i class="mdi mdi-message-text-outline me-2"></i>{{ $t('support.title') }}</h4>
        <span class="badge badge-offline" v-if="unreadCount > 0">{{ unreadCount }} {{ $t('support.unread') }}</span>
      </div>
      <div class="d-flex flex-wrap gap-2 mobile-filter-bar">
        <select class="form-select form-select-sm" style="min-width: 120px;" v-model="statusFilter" @change="loadTickets">
          <option value="">{{ $t('support.allStatuses') }}</option>
          <option value="open">{{ $t('support.status_open') }}</option>
          <option value="answered">{{ $t('support.status_answered') }}</option>
          <option value="closed">{{ $t('support.status_closed') }}</option>
        </select>
        <input type="text" class="form-control form-control-sm" style="min-width: 150px; flex: 1;" v-model="search"
          :placeholder="$t('common.search')" @input="debounceSearch">
      </div>
    </div>

    <!-- Two-panel layout (desktop: side-by-side, mobile: single panel) -->
    <div class="row g-4">
      <!-- Tickets List (hidden on mobile when ticket selected) -->
      <div :class="selectedTicket ? 'col-lg-4 d-none d-lg-block' : 'col-12'">
        <div class="card">
          <div class="list-group list-group-flush">
            <div class="list-group-item list-group-item-action p-3"
              v-for="ticket in tickets" :key="ticket.id"
              :class="{ active: selectedTicket?.id === ticket.id }"
              @click="selectTicket(ticket)" style="cursor: pointer;">
              <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1 overflow-hidden">
                  <div class="d-flex align-items-center gap-2 mb-1">
                    <strong class="text-truncate">{{ ticket.subject }}</strong>
                    <span class="badge" :class="statusBadge(ticket.status)">{{ $t('support.status_' + ticket.status) }}</span>
                  </div>
                  <div class="small mb-1">
                    <span class="fw-semibold">{{ ticket.username }}</span>
                    <span class="text-muted ms-1">{{ ticket.email }}</span>
                  </div>
                  <div class="d-flex gap-2 align-items-center">
                    <small class="text-muted">{{ formatDate(ticket.created_at) }}</small>
                    <small class="text-muted">· {{ ticket.reply_count }} {{ $t('support.replies') }}</small>
                    <span class="badge badge-offline" v-if="ticket.unread_count > 0">{{ ticket.unread_count }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="list-group-item text-center text-muted py-4" v-if="!tickets.length && !loading">
              {{ $t('support.noTickets') }}
            </div>
            <div class="list-group-item text-center py-4" v-if="loading">
              <div class="spinner-border spinner-border-sm text-primary"></div>
            </div>
          </div>
          <!-- Pagination -->
          <div class="card-footer d-flex justify-content-between align-items-center mobile-pagination" v-if="totalPages > 1">
            <small class="text-muted">{{ $t('support.total') }}: {{ total }}</small>
            <div class="btn-group btn-group-sm">
              <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="page--; loadTickets()">←</button>
              <button class="btn btn-outline-secondary disabled">{{ page }}/{{ totalPages }}</button>
              <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="page++; loadTickets()">→</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Ticket Detail -->
      <div :class="selectedTicket ? 'col-lg-8 col-12' : ''" v-if="selectedTicket">
        <div class="card">
          <div class="card-header">
            <div class="d-flex justify-content-between align-items-start">
              <div class="overflow-hidden">
                <h6 class="mb-0 text-truncate">{{ selectedTicket.subject }}</h6>
                <small class="text-muted">{{ selectedTicket.username }} ({{ selectedTicket.email }})</small>
                <span v-if="selectedTicket.telegram_id" class="ms-2 badge badge-soft-info">TG: {{ selectedTicket.telegram_id }}</span>
              </div>
              <div class="d-flex gap-2 flex-shrink-0 ms-2 support-messages-page__ticket-actions">
                <button class="btn btn-sm btn-outline-warning" v-if="selectedTicket.status === 'closed'" @click="reopenTicket">
                  {{ $t('support.reopen') }}
                </button>
                <button class="btn btn-sm btn-outline-secondary" v-if="selectedTicket.status !== 'closed'" @click="closeTicket">
                  {{ $t('support.close') }}
                </button>
                <button class="btn btn-sm btn-outline-danger" @click="deleteTicket">
                  {{ $t('support.delete') }}
                </button>
                <button class="btn btn-sm btn-outline-secondary" @click="selectedTicket = null">
                  <span class="d-lg-none">← {{ $t('common.back') || 'Back' }}</span>
                  <span class="d-none d-lg-inline"><i class="mdi mdi-close"></i></span>
                </button>
              </div>
            </div>
          </div>
          <div class="card-body conversation-body" ref="conversationRef">
            <!-- Original message -->
            <div class="message-bubble user-msg">
              <div class="message-text">{{ selectedTicket.message }}</div>
              <div class="message-meta">{{ formatDateTime(selectedTicket.created_at) }}</div>
            </div>
            <!-- Replies -->
            <div v-for="reply in selectedTicket.replies" :key="reply.id"
              class="message-bubble" :class="reply.direction === 'admin' ? 'admin-msg' : 'user-msg'">
              <div class="message-sender" v-if="reply.direction === 'admin'">{{ $t('support.you') }}</div>
              <div class="message-text">{{ reply.message }}</div>
              <div class="message-meta">{{ formatDateTime(reply.created_at) }}</div>
            </div>
          </div>
          <!-- Reply form -->
          <div class="card-footer">
            <div class="d-flex gap-2 support-messages-page__reply-row">
              <textarea class="form-control" rows="2" v-model="replyText" :placeholder="$t('support.replyPlaceholder')"
                maxlength="4000" @keydown.ctrl.enter="sendReply"></textarea>
              <button class="btn btn-primary align-self-end flex-shrink-0" @click="sendReply" :disabled="replying || !replyText.trim()">
                <span v-if="replying" class="spinner-border spinner-border-sm"></span>
                <span v-else>{{ $t('support.send') }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalUsersApi } from '../api'

const { t } = useI18n()

const tickets = ref([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const statusFilter = ref('')
const search = ref('')
const loading = ref(false)
const selectedTicket = ref(null)
const replyText = ref('')
const replying = ref(false)
const unreadCount = ref(0)
const conversationRef = ref(null)

let searchTimeout = null

const totalPages = computed(() => Math.ceil(total.value / perPage))

const loadTickets = async () => {
  loading.value = true
  try {
    const params = { page: page.value, per_page: perPage }
    if (statusFilter.value) params.status = statusFilter.value
    if (search.value) params.search = search.value
    const { data } = await portalUsersApi.getSupportMessages(params)
    tickets.value = data.items
    total.value = data.total
  } catch (e) { /* ignore */ }
  loading.value = false
}

const loadUnread = async () => {
  try {
    const { data } = await portalUsersApi.getSupportUnread()
    unreadCount.value = data.unread
  } catch (e) { /* ignore */ }
}

const selectTicket = async (ticket) => {
  try {
    const { data } = await portalUsersApi.getSupportTicket(ticket.id)
    selectedTicket.value = data
    replyText.value = ''
    // Update unread count in list
    const idx = tickets.value.findIndex(t => t.id === ticket.id)
    if (idx >= 0) tickets.value[idx].unread_count = 0
    loadUnread()
    await nextTick()
    if (conversationRef.value) conversationRef.value.scrollTop = conversationRef.value.scrollHeight
  } catch (e) {
    alert(t('common.error'))
  }
}

const sendReply = async () => {
  if (!replyText.value.trim() || !selectedTicket.value) return
  replying.value = true
  try {
    await portalUsersApi.replySupportTicket(selectedTicket.value.id, { message: replyText.value.trim() })
    replyText.value = ''
    await selectTicket(selectedTicket.value)
    await loadTickets()
  } catch (e) {
    alert(t('common.error') + ': ' + (e.response?.data?.detail || e.message))
  }
  replying.value = false
}

const closeTicket = async () => {
  if (!selectedTicket.value) return
  try {
    await portalUsersApi.closeSupportTicket(selectedTicket.value.id)
    selectedTicket.value.status = 'closed'
    await loadTickets()
  } catch (e) {
    alert(t('common.error'))
  }
}

const reopenTicket = async () => {
  if (!selectedTicket.value) return
  try {
    await portalUsersApi.reopenSupportTicket(selectedTicket.value.id)
    selectedTicket.value.status = 'open'
    await loadTickets()
  } catch (e) {
    alert(t('common.error'))
  }
}

const deleteTicket = async () => {
  if (!selectedTicket.value) return
  if (!confirm(t('support.deleteConfirm'))) return
  try {
    await portalUsersApi.deleteSupportTicket(selectedTicket.value.id)
    selectedTicket.value = null
    await loadTickets()
  } catch (e) {
    alert(t('common.error'))
  }
}

const debounceSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => { page.value = 1; loadTickets() }, 400)
}

const statusBadge = (status) => {
  switch (status) {
    case 'open': return 'badge-soft-primary'
    case 'answered': return 'badge-online'
    case 'closed': return 'badge-soft-secondary'
    default: return 'badge-soft-secondary'
  }
}

const formatDate = (d) => d ? new Date(d).toLocaleDateString() : ''
const formatDateTime = (d) => d ? new Date(d).toLocaleString() : ''

onMounted(() => {
  loadTickets()
  loadUnread()
})
</script>

<style scoped>
.conversation-body {
  max-height: 500px; overflow-y: auto;
  display: flex; flex-direction: column; gap: .75rem;
  padding: 1.5rem; background: var(--vxy-hover-bg);
}

.message-bubble {
  max-width: 80%; padding: .75rem 1rem; border-radius: .75rem;
  word-break: break-word; white-space: pre-wrap; color: var(--vxy-text);
}
.user-msg  { align-self: flex-start; background: var(--vxy-primary-light); border-bottom-left-radius: 4px; }
.admin-msg { align-self: flex-end;   background: var(--vxy-success-light); border-bottom-right-radius: 4px; }

.message-sender { font-weight: 600; font-size: .75rem; color: var(--vxy-success); margin-bottom: .25rem; }
.message-meta   { font-size: .7rem; color: var(--vxy-muted); margin-top: .35rem; }
.message-text   { font-size: .9rem; line-height: 1.4; color: var(--vxy-text); }

.list-group-item.active {
  background-color: var(--vxy-primary-light);
  border-color: rgba(115,103,240,.2);
  color: inherit;
}

.list-group-item-action:hover,
.list-group-item-action:focus {
  background-color: var(--vxy-hover-bg) !important;
  color: var(--vxy-text) !important;
}

.support-messages-page__reply-row .btn {
  white-space: nowrap;
}

@media (max-width: 991.98px) { .conversation-body { max-height: 60vh; padding: 1rem; } .message-bubble { max-width: 90%; } }
@media (max-width: 575.98px) {
  .conversation-body { max-height: 55vh; padding: .75rem; gap: .5rem; }
  .message-text { font-size: .85rem; }
  .support-messages-page__ticket-actions,
  .support-messages-page__reply-row {
    flex-direction: column;
    align-items: stretch;
  }
  .support-messages-page__ticket-actions .btn,
  .support-messages-page__reply-row .btn {
    width: 100%;
  }
}
</style>
