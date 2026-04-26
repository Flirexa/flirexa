<template>
  <div class="support-page">
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
      <h4 class="mb-0">{{ $t('support.title') }}</h4>
      <button class="btn btn-primary" @click="showNewTicket = true" v-if="!showNewTicket">
        {{ $t('support.newMessage') }}
      </button>
    </div>

    <!-- New Ticket Form -->
    <div class="card mb-4" v-if="showNewTicket">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h6 class="mb-0">{{ $t('support.newMessage') }}</h6>
        <button class="btn-close" @click="showNewTicket = false"></button>
      </div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">{{ $t('support.subject') }}</label>
          <input type="text" class="form-control" v-model="newSubject" :placeholder="$t('support.subjectPlaceholder')" maxlength="255">
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('support.message') }}</label>
          <textarea class="form-control" rows="4" v-model="newMessage" :placeholder="$t('support.messagePlaceholder')" maxlength="4000"></textarea>
        </div>
        <div class="alert alert-danger" v-if="sendError">{{ sendError }}</div>
        <button class="btn btn-primary" @click="sendNewTicket" :disabled="sending || !newSubject.trim() || !newMessage.trim()">
          <span v-if="sending" class="spinner-border spinner-border-sm me-1"></span>
          {{ $t('support.send') }}
        </button>
      </div>
    </div>

    <!-- Tickets List -->
    <div v-if="!selectedTicket">
      <div class="card" v-if="tickets.length">
        <div class="list-group list-group-flush">
          <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-start"
            v-for="ticket in tickets" :key="ticket.id"
            @click="selectTicket(ticket)" style="cursor: pointer;">
            <div class="flex-grow-1">
              <div class="d-flex align-items-center gap-2 mb-1">
                <strong>{{ ticket.subject }}</strong>
                <span class="badge" :class="statusClass(ticket.status)">{{ $t('support.status_' + ticket.status) }}</span>
                <span class="badge bg-danger" v-if="unreadReplies(ticket) > 0">{{ unreadReplies(ticket) }} new</span>
              </div>
              <p class="mb-1 text-muted small text-truncate" style="max-width: 500px;">{{ ticket.message }}</p>
              <small class="text-muted">{{ formatDate(ticket.created_at) }} · {{ ticket.replies.length }} {{ $t('support.replies') }}</small>
            </div>
            <span class="text-muted">→</span>
          </div>
        </div>
      </div>
      <div class="text-center py-5 text-muted" v-else-if="!loading">
        <div style="font-size: 3rem; margin-bottom: 1rem;">💬</div>
        <p>{{ $t('support.noTickets') }}</p>
        <button class="btn btn-primary" @click="showNewTicket = true">{{ $t('support.newMessage') }}</button>
      </div>
      <div class="text-center py-5" v-else>
        <div class="spinner-border text-primary"></div>
      </div>
    </div>

    <!-- Ticket Detail / Conversation -->
    <div v-if="selectedTicket" class="card">
      <div class="card-header">
        <div class="d-flex align-items-center flex-wrap gap-2">
          <button class="btn btn-sm btn-outline-secondary" @click="selectedTicket = null">&larr; {{ $t('support.back') }}</button>
          <strong class="text-truncate" style="max-width: 200px;">{{ selectedTicket.subject }}</strong>
          <span class="badge" :class="statusClass(selectedTicket.status)">{{ $t('support.status_' + selectedTicket.status) }}</span>
        </div>
      </div>
      <div class="card-body conversation-body">
        <!-- Original message -->
        <div class="message-bubble user-message">
          <div class="message-text">{{ selectedTicket.message }}</div>
          <div class="message-meta">{{ formatDateTime(selectedTicket.created_at) }}</div>
        </div>

        <!-- Replies -->
        <div v-for="reply in selectedTicket.replies" :key="reply.id"
          class="message-bubble" :class="reply.direction === 'admin' ? 'admin-message' : 'user-message'">
          <div class="message-sender" v-if="reply.direction === 'admin'">{{ $t('support.adminReply') }}</div>
          <div class="message-text">{{ reply.message }}</div>
          <div class="message-meta">{{ formatDateTime(reply.created_at) }}</div>
        </div>
      </div>

      <!-- Reply form -->
      <div class="card-footer" v-if="selectedTicket.status !== 'closed'">
        <div class="alert alert-danger small py-2 mb-2" v-if="replyError">{{ replyError }}</div>
        <div class="reply-form">
          <textarea class="form-control" rows="2" v-model="replyText" :placeholder="$t('support.replyPlaceholder')" maxlength="4000"
            @keydown.ctrl.enter="sendReply"></textarea>
          <button class="btn btn-primary reply-send-btn" @click="sendReply" :disabled="replying || !replyText.trim()">
            <span v-if="replying" class="spinner-border spinner-border-sm"></span>
            <span v-else>{{ $t('support.send') }}</span>
          </button>
        </div>
      </div>
      <div class="card-footer text-muted text-center small" v-else>
        {{ $t('support.ticketClosed') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { formatDate, formatDateTime } from '../utils'

const { t } = useI18n()

const tickets = ref([])
const loading = ref(true)
const showNewTicket = ref(false)
const selectedTicket = ref(null)
const newSubject = ref('')
const newMessage = ref('')
const sending = ref(false)
const sendError = ref(null)
const replyText = ref('')
const replying = ref(false)
const replyError = ref(null)

const loadTickets = async () => {
  loading.value = true
  try {
    const { data } = await portalApi.getSupportMessages()
    tickets.value = data
  } catch (e) { /* ignore */ }
  loading.value = false
}

const sendNewTicket = async () => {
  sending.value = true
  sendError.value = null
  try {
    await portalApi.sendSupportMessage({ subject: newSubject.value.trim(), message: newMessage.value.trim() })
    newSubject.value = ''
    newMessage.value = ''
    showNewTicket.value = false
    await loadTickets()
  } catch (e) {
    sendError.value = e.response?.data?.detail || t('common.error')
  }
  sending.value = false
}

const selectTicket = (ticket) => {
  selectedTicket.value = ticket
  replyText.value = ''
}

const sendReply = async () => {
  if (!replyText.value.trim() || !selectedTicket.value) return
  replying.value = true
  try {
    await portalApi.replySupportTicket(selectedTicket.value.id, { message: replyText.value.trim() })
    replyText.value = ''
    await loadTickets()
    // Re-select the same ticket
    const updated = tickets.value.find(t => t.id === selectedTicket.value.id)
    if (updated) selectedTicket.value = updated
  } catch (e) {
    replyError.value = t('common.error') + ': ' + (e.response?.data?.detail || e.message)
    setTimeout(() => { replyError.value = null }, 4000)
  }
  replying.value = false
}

const unreadReplies = (ticket) => ticket.replies.filter(r => r.direction === 'admin' && !r.is_read).length

const statusClass = (status) => {
  switch (status) {
    case 'open': return 'bg-primary'
    case 'answered': return 'bg-success'
    case 'closed': return 'bg-secondary'
    default: return 'bg-secondary'
  }
}

let pollInterval = null

watch(selectedTicket, (ticket) => {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  if (ticket && ticket.status !== 'closed') {
    pollInterval = setInterval(async () => {
      try {
        const { data } = await portalApi.getSupportMessages()
        tickets.value = data
        const updated = data.find(t => t.id === ticket.id)
        if (updated) selectedTicket.value = updated
      } catch { /* ignore */ }
    }, 5000)
  }
})

onMounted(loadTickets)

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<style scoped>
.conversation-body {
  max-height: 500px; overflow-y: auto;
  display: flex; flex-direction: column; gap: .75rem;
  padding: 1.5rem;
}

.message-bubble {
  max-width: 80%; padding: .75rem 1rem;
  border-radius: .75rem;
  word-break: break-word; white-space: pre-wrap;
}
.user-message {
  align-self: flex-end;
  background: var(--vxy-primary-light);
  color: var(--vxy-text);
  border-bottom-right-radius: 4px;
}
.admin-message {
  align-self: flex-start;
  background: var(--vxy-hover-bg);
  color: var(--vxy-text);
  border-bottom-left-radius: 4px;
}
.message-sender { font-weight: 600; font-size: .75rem; color: var(--vxy-primary); margin-bottom: .25rem; }
.message-meta { font-size: .7rem; color: var(--vxy-muted); margin-top: .35rem; text-align: right; }
.message-text { font-size: .9rem; line-height: 1.4; color: var(--vxy-text); }

.reply-form { display: flex; gap: .5rem; }
.reply-send-btn { align-self: flex-end; white-space: nowrap; }

@media (max-width: 576px) {
  .conversation-body { max-height: 350px; padding: 1rem; }
  .message-bubble { max-width: 90%; padding: .6rem .8rem; }
  .reply-form { flex-direction: column; }
  .reply-send-btn { align-self: stretch; }
}
</style>
