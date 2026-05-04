<template>
  <div class="fx-page">
    <div v-if="!selectedTicket" class="fx-page-head" style="display:block; text-align:left">
      <h1 class="fx-page-title">{{ $t('support.headline') }}</h1>
      <p class="fx-page-sub">{{ $t('support.headlineSub') }}</p>
    </div>

    <!-- ─── List view ─── -->
    <template v-if="!selectedTicket">
      <!-- Search -->
      <div style="position:relative; margin-bottom:28px">
        <FxIcon name="search" :size="16" style="position:absolute; left:16px; top:50%; transform:translateY(-50%); color:var(--text-3)" />
        <input v-model="search" class="fx-search-input" :placeholder="$t('support.searchPlaceholder')" />
      </div>

      <div class="fx-support-grid">
        <!-- Tiles -->
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: var(--gap); align-content:start">
          <button class="fx-support-tile" @click="startNewTicket">
            <div class="fx-support-tile-icon"><FxIcon name="chat" :size="18" /></div>
            <h3>{{ $t('support.tileChat') }}</h3>
            <p>{{ $t('support.tileChatHint') }}</p>
            <span class="fx-badge fx-badge-success" style="margin-top:12px; align-self:flex-start">
              <span class="fx-dot fx-dot-online"></span> {{ $t('support.online') }}
            </span>
          </button>
          <a class="fx-support-tile" :href="emailHref">
            <div class="fx-support-tile-icon"><FxIcon name="mail" :size="18" /></div>
            <h3>{{ $t('support.tileEmail') }}</h3>
            <p>{{ supportEmail }}</p>
            <span style="margin-top:12px; font-size:11px; color:var(--text-3)">{{ $t('support.emailHint') }}</span>
          </a>
          <a class="fx-support-tile" :href="docsUrl" target="_blank" rel="noreferrer">
            <div class="fx-support-tile-icon"><FxIcon name="book" :size="18" /></div>
            <h3>{{ $t('support.tileDocs') }}</h3>
            <p>{{ $t('support.tileDocsHint') }}</p>
          </a>
          <a class="fx-support-tile" :href="statusUrl" target="_blank" rel="noreferrer">
            <div class="fx-support-tile-icon"><FxIcon name="speed" :size="18" /></div>
            <h3>{{ $t('support.tileStatus') }}</h3>
            <p>{{ $t('support.tileStatusHint') }}</p>
          </a>
        </div>

        <!-- FAQ accordion -->
        <div class="fx-card">
          <div style="padding:var(--pad-card) var(--pad-card) 0">
            <h3 class="fx-section-title">{{ $t('support.faqTitle') }}</h3>
          </div>
          <div style="margin-top:10px">
            <div v-for="(f, i) in filteredFaqs" :key="i" class="fx-faq-item">
              <div class="fx-faq-q" @click="openFaq = openFaq === i ? -1 : i">
                <span>{{ f.q }}</span>
                <FxIcon name="chevronDown" :size="16"
                        :style="{ color: 'var(--text-3)', transform: openFaq === i ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }" />
              </div>
              <div v-if="openFaq === i" class="fx-faq-a">{{ f.a }}</div>
            </div>
            <div v-if="!filteredFaqs.length" class="fx-empty" style="padding:36px 20px">
              <p class="fx-empty-sub">{{ $t('support.noResults') }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Tickets list -->
      <div style="margin-top: var(--gap-lg)">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; gap:12px; flex-wrap:wrap">
          <div>
            <h2 class="fx-section-title" style="font-size:15px">{{ $t('support.yourTickets') }}</h2>
            <div style="font-size:12px; color:var(--text-3); margin-top:2px">{{ $t('support.yourTicketsHint') }}</div>
          </div>
          <button class="fx-btn fx-btn-primary" @click="startNewTicket">
            <FxIcon name="plus" :size="14" /> {{ $t('support.newMessage') }}
          </button>
        </div>

        <div v-if="ticketsLoading" class="fx-empty">
          <div class="fx-empty-icon"><FxIcon name="refresh" :size="22" /></div>
          <p class="fx-empty-sub">{{ $t('common.loading') }}</p>
        </div>
        <div v-else-if="!tickets.length" class="fx-card fx-empty">
          <div class="fx-empty-icon"><FxIcon name="chat" :size="22" /></div>
          <h3 class="fx-empty-title">{{ $t('support.noTickets') }}</h3>
          <p class="fx-empty-sub">{{ $t('support.noTicketsHint') }}</p>
        </div>
        <div v-else class="fx-card" style="overflow:hidden">
          <div v-for="(ticket, i) in tickets" :key="ticket.id"
               style="padding:14px var(--pad-card); cursor:pointer; display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center;"
               :style="{ borderBottom: i === tickets.length - 1 ? '0' : '1px solid var(--border)' }"
               @click="selectTicket(ticket)">
            <div style="min-width:0">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:4px">
                <strong style="font-size:13px; color:var(--text)">{{ ticket.subject }}</strong>
                <span class="fx-badge" :class="statusBadgeClass(ticket.status)">{{ $t('support.status_' + ticket.status) }}</span>
                <span v-if="unreadReplies(ticket) > 0" class="fx-badge fx-badge-danger">{{ unreadReplies(ticket) }} {{ $t('support.new') }}</span>
              </div>
              <div style="font-size:12px; color:var(--text-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{{ ticket.message }}</div>
              <div style="font-size:11px; color:var(--text-4); margin-top:4px; font-family:var(--mono)">
                {{ formatDate(ticket.created_at) }} · {{ ticket.replies.length }} {{ $t('support.replies') }}
              </div>
            </div>
            <FxIcon name="chevron" :size="16" style="color:var(--text-3)" />
          </div>
        </div>
      </div>
    </template>

    <!-- ─── Ticket detail ─── -->
    <template v-else>
      <div class="fx-page-head" style="margin-bottom:14px">
        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap">
          <button class="fx-btn fx-btn-ghost fx-btn-sm" @click="selectedTicket = null">
            <FxIcon name="chevronLeft" :size="14" /> {{ $t('support.back') }}
          </button>
          <h1 class="fx-page-title" style="font-size:20px">{{ selectedTicket.subject }}</h1>
          <span class="fx-badge" :class="statusBadgeClass(selectedTicket.status)">
            {{ $t('support.status_' + selectedTicket.status) }}
          </span>
        </div>
      </div>

      <div class="fx-card" style="overflow:hidden; display:flex; flex-direction:column; max-height:70vh">
        <div class="fx-conversation-body">
          <div class="fx-msg fx-msg-user">
            <div class="fx-msg-text">{{ selectedTicket.message }}</div>
            <div class="fx-msg-meta">{{ formatDateTime(selectedTicket.created_at) }}</div>
          </div>
          <div v-for="reply in selectedTicket.replies" :key="reply.id"
               class="fx-msg" :class="reply.direction === 'admin' ? 'fx-msg-admin' : 'fx-msg-user'">
            <div v-if="reply.direction === 'admin'" class="fx-msg-sender">{{ $t('support.adminReply') }}</div>
            <div class="fx-msg-text">{{ reply.message }}</div>
            <div class="fx-msg-meta">{{ formatDateTime(reply.created_at) }}</div>
          </div>
        </div>
        <div v-if="selectedTicket.status !== 'closed'" style="padding:14px var(--pad-card); border-top:1px solid var(--border)">
          <div v-if="replyError" class="fx-toast error" style="margin-bottom:10px; max-width:100%">{{ replyError }}</div>
          <div style="display:flex; gap:8px; align-items:flex-end">
            <textarea class="fx-textarea" rows="2" v-model="replyText"
                      :placeholder="$t('support.replyPlaceholder')" maxlength="4000"
                      @keydown.ctrl.enter="sendReply" style="flex:1"></textarea>
            <button class="fx-btn fx-btn-primary" @click="sendReply" :disabled="replying || !replyText.trim()">
              <FxIcon name="send" :size="14" /> {{ $t('support.send') }}
            </button>
          </div>
        </div>
        <div v-else style="padding:18px; text-align:center; color:var(--text-3); font-size:13px; border-top:1px solid var(--border)">
          {{ $t('support.ticketClosed') }}
        </div>
      </div>
    </template>

    <!-- New ticket modal -->
    <transition name="fx-modal-fade">
      <div v-if="showNewTicket" class="fx-modal-overlay" @click.self="showNewTicket = false">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ $t('support.newMessage') }}</h3>
            <button class="fx-icon-btn-sm" @click="showNewTicket = false"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <label class="fx-label">{{ $t('support.subject') }}</label>
            <input class="fx-input" v-model="newSubject" :placeholder="$t('support.subjectPlaceholder')" maxlength="255" style="margin-bottom:12px" />
            <label class="fx-label">{{ $t('support.message') }}</label>
            <textarea class="fx-textarea" rows="5" v-model="newMessage"
                      :placeholder="$t('support.messagePlaceholder')" maxlength="4000"></textarea>
            <div v-if="sendError" style="color:var(--danger); font-size:12px; margin-top:10px">{{ sendError }}</div>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="showNewTicket = false">{{ $t('common.close') }}</button>
            <button class="fx-btn fx-btn-primary" @click="sendNewTicket" :disabled="sending || !newSubject.trim() || !newMessage.trim()">
              <FxIcon name="send" :size="14" /> {{ $t('support.send') }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import { formatDate, formatDateTime } from '../utils'
import FxIcon from '../components/FxIcon.vue'

const { t } = useI18n()

const tickets = ref([])
const ticketsLoading = ref(true)
const showNewTicket = ref(false)
const selectedTicket = ref(null)
const newSubject = ref('')
const newMessage = ref('')
const sending = ref(false)
const sendError = ref(null)
const replyText = ref('')
const replying = ref(false)
const replyError = ref(null)
const search = ref('')
const openFaq = ref(0)

// Branding-configurable links. Defaults point at the canonical flirexa.biz
// surfaces; admins can override via the public branding endpoint.
const supportEmail = computed(() =>
  window.__branding?.branding_support_email || 'support@flirexa.biz')
const emailHref = computed(() => `mailto:${supportEmail.value}`)
const docsUrl = computed(() =>
  window.__branding?.branding_docs_url || 'https://flirexa.biz')
const statusUrl = computed(() =>
  window.__branding?.branding_status_url || 'https://flirexa.biz')

const FAQS = computed(() => [
  { q: t('support.faq1.q'), a: t('support.faq1.a') },
  { q: t('support.faq2.q'), a: t('support.faq2.a') },
  { q: t('support.faq3.q'), a: t('support.faq3.a') },
  { q: t('support.faq4.q'), a: t('support.faq4.a') },
  { q: t('support.faq5.q'), a: t('support.faq5.a') },
])

const filteredFaqs = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return FAQS.value
  return FAQS.value.filter(f => f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q))
})

const startNewTicket = () => {
  newSubject.value = ''
  newMessage.value = ''
  sendError.value = null
  showNewTicket.value = true
}

const loadTickets = async () => {
  ticketsLoading.value = true
  try {
    const { data } = await portalApi.getSupportMessages()
    tickets.value = data
  } catch { /* ignore */ }
  ticketsLoading.value = false
}

const sendNewTicket = async () => {
  sending.value = true
  sendError.value = null
  try {
    await portalApi.sendSupportMessage({
      subject: newSubject.value.trim(),
      message: newMessage.value.trim(),
    })
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
    const updated = tickets.value.find(x => x.id === selectedTicket.value.id)
    if (updated) selectedTicket.value = updated
  } catch (e) {
    replyError.value = t('common.error') + ': ' + (e.response?.data?.detail || e.message)
    setTimeout(() => { replyError.value = null }, 4000)
  }
  replying.value = false
}

const unreadReplies = (ticket) =>
  ticket.replies.filter(r => r.direction === 'admin' && !r.is_read).length

const statusBadgeClass = (status) => {
  if (status === 'open') return 'fx-badge-info'
  if (status === 'answered') return 'fx-badge-success'
  if (status === 'closed') return 'fx-badge-neutral'
  return 'fx-badge-neutral'
}

let pollInterval = null
watch(selectedTicket, (ticket) => {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  if (ticket && ticket.status !== 'closed') {
    pollInterval = setInterval(async () => {
      try {
        const { data } = await portalApi.getSupportMessages()
        tickets.value = data
        const updated = data.find(x => x.id === ticket.id)
        if (updated) selectedTicket.value = updated
      } catch { /* ignore */ }
    }, 5000)
  }
})

onMounted(loadTickets)
onUnmounted(() => { if (pollInterval) clearInterval(pollInterval) })
</script>

<style scoped>
.fx-conversation-body {
  padding: var(--pad-card);
  display: flex; flex-direction: column; gap: 12px;
  overflow-y: auto;
  flex: 1;
}
.fx-msg {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: var(--r-md);
  word-break: break-word; white-space: pre-wrap;
  font-size: 13px;
}
.fx-msg-user {
  align-self: flex-end;
  background: var(--accent-soft);
  color: var(--text);
}
.fx-msg-admin {
  align-self: flex-start;
  background: var(--bg-subtle);
  color: var(--text);
}
.fx-msg-sender {
  font-weight: 600; font-size: 11px;
  color: var(--accent); margin-bottom: 4px;
}
.fx-msg-meta {
  font-size: 10px; color: var(--text-3);
  margin-top: 6px; text-align: right;
  font-family: var(--mono);
}
.fx-msg-text { line-height: 1.45; }
.fx-modal-fade-enter-active, .fx-modal-fade-leave-active { transition: opacity .2s ease; }
.fx-modal-fade-enter-from, .fx-modal-fade-leave-to { opacity: 0; }

@media (max-width: 760px) {
  .fx-msg { max-width: 92%; }
}
</style>
