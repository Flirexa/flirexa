<template>
  <div>
    <!-- Inline feedback -->
    <div v-if="botActionMsg" class="alert alert-success alert-dismissible fade show">
      {{ botActionMsg }}
      <button type="button" class="btn-close" @click="botActionMsg = null"></button>
    </div>
    <div v-if="botActionError" class="alert alert-danger alert-dismissible fade show">
      {{ botActionError }}
      <button type="button" class="btn-close" @click="botActionError = null"></button>
    </div>

    <div class="row g-4">
      <!-- Admin Bot -->
      <div class="col-lg-6">
        <div class="stat-card">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <h5 class="mb-1">&#x1F916; {{ $t('bots.adminBot') }}</h5>
              <small class="text-muted">{{ $t('bots.adminBotDesc') }}</small>
            </div>
            <span class="badge" :class="adminBot?.is_running ? 'badge-online' : 'badge-offline'">
              {{ adminBot?.is_running ? $t('bots.running') : $t('bots.stopped') }}
            </span>
          </div>

          <div class="mb-3" v-if="adminBot">
            <div class="d-flex justify-content-between mb-1">
              <span class="text-muted">{{ $t('bots.service') }}:</span>
              <span>{{ adminBot.service_name || 'wg-bot' }}</span>
            </div>
            <div class="d-flex justify-content-between mb-1" v-if="adminBot.uptime">
              <span class="text-muted">{{ $t('bots.uptime') }}:</span>
              <span>{{ adminBot.uptime }}</span>
            </div>
            <div class="d-flex justify-content-between mb-1" v-if="adminBot.pid">
              <span class="text-muted">{{ $t('bots.pid') }}:</span>
              <span>{{ adminBot.pid }}</span>
            </div>
          </div>

          <div class="bot-actions">
            <button
              class="btn btn-success btn-sm"
              @click="botAction('admin', 'start')"
              :disabled="adminBot?.is_running || botActionLoading['admin_start']"
            >
              <span v-if="botActionLoading['admin_start']" class="spinner-border spinner-border-sm me-1"></span>
              &#x25B6; {{ $t('common.start') }}
            </button>
            <button
              class="btn btn-danger btn-sm"
              @click="botAction('admin', 'stop')"
              :disabled="!adminBot?.is_running || botActionLoading['admin_stop']"
            >
              <span v-if="botActionLoading['admin_stop']" class="spinner-border spinner-border-sm me-1"></span>
              &#x23F9; {{ $t('common.stop') }}
            </button>
            <button
              class="btn btn-warning btn-sm"
              @click="botAction('admin', 'restart')"
              :disabled="botActionLoading['admin_restart']"
            >
              <span v-if="botActionLoading['admin_restart']" class="spinner-border spinner-border-sm me-1"></span>
              &#x1F504; {{ $t('common.restart') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Client Bot -->
      <div class="col-lg-6">
        <div class="stat-card">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <h5 class="mb-1">&#x1F465; {{ $t('bots.clientBot') }}</h5>
              <small class="text-muted">{{ $t('bots.clientBotDesc') }}</small>
            </div>
            <span class="badge" :class="clientBot?.is_running ? 'badge-online' : 'badge-offline'">
              {{ clientBot?.is_running ? $t('bots.running') : $t('bots.stopped') }}
            </span>
          </div>

          <div class="mb-3" v-if="clientBot">
            <div class="d-flex justify-content-between mb-1">
              <span class="text-muted">{{ $t('bots.service') }}:</span>
              <span>{{ clientBot.service_name || 'client-bot' }}</span>
            </div>
            <div class="d-flex justify-content-between mb-1" v-if="clientBot.uptime">
              <span class="text-muted">{{ $t('bots.uptime') }}:</span>
              <span>{{ clientBot.uptime }}</span>
            </div>
            <div class="d-flex justify-content-between mb-1" v-if="clientBot.pid">
              <span class="text-muted">{{ $t('bots.pid') }}:</span>
              <span>{{ clientBot.pid }}</span>
            </div>
          </div>

          <div class="bot-actions">
            <button
              class="btn btn-success btn-sm"
              @click="botAction('client', 'start')"
              :disabled="clientBot?.is_running || botActionLoading['client_start']"
            >
              <span v-if="botActionLoading['client_start']" class="spinner-border spinner-border-sm me-1"></span>
              &#x25B6; {{ $t('common.start') }}
            </button>
            <button
              class="btn btn-danger btn-sm"
              @click="botAction('client', 'stop')"
              :disabled="!clientBot?.is_running || botActionLoading['client_stop']"
            >
              <span v-if="botActionLoading['client_stop']" class="spinner-border spinner-border-sm me-1"></span>
              &#x23F9; {{ $t('common.stop') }}
            </button>
            <button
              class="btn btn-warning btn-sm"
              @click="botAction('client', 'restart')"
              :disabled="botActionLoading['client_restart']"
            >
              <span v-if="botActionLoading['client_restart']" class="spinner-border spinner-border-sm me-1"></span>
              &#x1F504; {{ $t('common.restart') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Bot Logs -->
    <div class="row g-4 mt-2">
      <div class="col-12">
        <div class="stat-card">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <h5 class="mb-0">&#x1F4CB; Bot Logs</h5>
            <div class="d-flex gap-2 align-items-center">
              <select v-model="logComponent" class="form-select form-select-sm" style="width: auto">
                <option value="worker">Worker (bots)</option>
                <option value="api">API</option>
              </select>
              <div class="form-check form-switch mb-0">
                <input class="form-check-input" type="checkbox" v-model="logErrorsOnly" id="errorsSwitch" />
                <label class="form-check-label small" for="errorsSwitch">Errors only</label>
              </div>
              <button class="btn btn-outline-secondary btn-sm" @click="loadLogs" :disabled="logsLoading">
                <span v-if="logsLoading" class="spinner-border spinner-border-sm me-1"></span>
                Refresh
              </button>
            </div>
          </div>
          <div v-if="logsError" class="text-muted small py-2">{{ logsError }}</div>
          <div v-else-if="logEntries.length === 0 && !logsLoading" class="text-muted small py-2 text-center">No log entries found</div>
          <div v-else class="log-viewer">
            <div
              v-for="(entry, i) in logEntries"
              :key="i"
              class="log-line"
              :class="entry.level === 'ERROR' || entry.level === 'CRITICAL' ? 'log-error' : entry.level === 'WARNING' ? 'log-warn' : ''"
            >
              <span class="log-time">{{ entry.timestamp?.slice(0, 19).replace('T', ' ') }}</span>
              <span class="log-level" :class="'log-level-' + (entry.level || '').toLowerCase()">{{ entry.level }}</span>
              <span class="log-msg">{{ entry.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bot Configuration -->
    <div class="row g-4 mt-2">
      <div class="col-12">
        <div class="stat-card">
          <h5 class="mb-3">&#x2699; {{ $t('bots.botConfig') }}</h5>

          <div v-if="configAlert" class="alert" :class="configAlert.type === 'success' ? 'alert-success' : 'alert-danger'" role="alert">
            {{ configAlert.message }}
          </div>

          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label">{{ $t('bots.adminBotToken') }}</label>
              <input
                type="text"
                class="form-control"
                v-model="configForm.admin_bot_token"
                :placeholder="botConfig?.admin_bot_token_masked || $t('bots.enterAdminBotToken')"
              />
              <small class="text-muted">{{ $t('bots.tokenFormat') }}</small>
            </div>
            <div class="col-md-6">
              <label class="form-label">{{ $t('bots.adminAllowedUsers') }}</label>
              <input
                type="text"
                class="form-control"
                v-model="configForm.admin_allowed_users"
                :placeholder="botConfig?.admin_allowed_users || $t('bots.commaSeparatedIds')"
              />
              <small class="text-muted">{{ $t('bots.commaSeparatedTelegramIds') }}</small>
            </div>
            <div class="col-md-6">
              <label class="form-label">{{ $t('bots.clientBotToken') }}</label>
              <input
                type="text"
                class="form-control"
                v-model="configForm.client_bot_token"
                :placeholder="botConfig?.client_bot_token_masked || $t('bots.enterClientBotToken')"
              />
              <small class="text-muted">{{ $t('bots.tokenFormat') }}</small>
            </div>
            <div class="col-md-6">
              <label class="form-label d-block">{{ $t('bots.clientBotEnabled') }}</label>
              <div class="form-check form-switch mt-2">
                <input
                  class="form-check-input"
                  type="checkbox"
                  role="switch"
                  v-model="configForm.client_bot_enabled"
                  :id="'clientBotSwitch'"
                />
                <label class="form-check-label" for="clientBotSwitch">
                  {{ configForm.client_bot_enabled ? $t('common.enabled') : $t('common.disabled') }}
                </label>
              </div>
            </div>
          </div>

          <div class="mt-3">
            <button class="btn btn-primary" @click="saveConfig" :disabled="configSaving">
              {{ configSaving ? $t('common.saving') : $t('bots.saveConfiguration') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { botsApi, systemApi } from '../api'

const { t } = useI18n()
const adminBot = ref(null)
const clientBot = ref(null)
const botActionLoading = ref({})
const botActionMsg = ref(null)
const botActionError = ref(null)

// Logs
const logComponent = ref('worker')
const logErrorsOnly = ref(false)
const logEntries = ref([])
const logsLoading = ref(false)
const logsError = ref('')

async function loadLogs() {
  logsLoading.value = true
  logsError.value = ''
  try {
    const { data } = await systemApi.getAppLogs({ component: logComponent.value, errors_only: logErrorsOnly.value, lines: 100 })
    logEntries.value = data.entries || data || []
  } catch (err) {
    logsError.value = 'Failed to load logs: ' + (err.response?.data?.detail || err.message)
    logEntries.value = []
  } finally {
    logsLoading.value = false
  }
}

watch([logComponent, logErrorsOnly], loadLogs)

const botConfig = ref(null)
const configSaving = ref(false)
const configAlert = ref(null)
const configForm = ref({
  admin_bot_token: '',
  admin_allowed_users: '',
  client_bot_token: '',
  client_bot_enabled: false,
})

async function loadStatuses() {
  try {
    const [admin, client] = await Promise.all([
      botsApi.getAdminStatus(),
      botsApi.getClientStatus(),
    ])
    adminBot.value = admin.data
    clientBot.value = client.data
  } catch (err) {
    console.error('Error loading bot statuses:', err)
  }
}

async function loadConfig() {
  try {
    const { data } = await botsApi.getConfig()
    botConfig.value = data
    configForm.value.client_bot_enabled = data.client_bot_enabled
  } catch (err) {
    console.error('Error loading bot config:', err)
  }
}

async function botAction(bot, action) {
  const key = `${bot}_${action}`
  botActionLoading.value[key] = true
  botActionMsg.value = null
  botActionError.value = null
  try {
    if (action === 'start') {
      bot === 'admin' ? await botsApi.startAdmin() : await botsApi.startClient()
    } else if (action === 'stop') {
      bot === 'admin' ? await botsApi.stopAdmin() : await botsApi.stopClient()
    } else {
      bot === 'admin' ? await botsApi.restartAdmin() : await botsApi.restartClient()
    }
    botActionMsg.value = `${bot === 'admin' ? 'Admin' : 'Client'} bot: ${action} successful`
    setTimeout(() => botActionMsg.value = null, 3000)
    setTimeout(loadStatuses, 2000)
  } catch (err) {
    botActionError.value = 'Error: ' + (err.response?.data?.detail || err.message)
    setTimeout(() => botActionError.value = null, 5000)
  } finally {
    botActionLoading.value[key] = false
  }
}

async function saveConfig() {
  configSaving.value = true
  configAlert.value = null

  try {
    const payload = {}
    if (configForm.value.admin_bot_token) {
      payload.admin_bot_token = configForm.value.admin_bot_token
    }
    if (configForm.value.admin_allowed_users) {
      payload.admin_allowed_users = configForm.value.admin_allowed_users
    }
    if (configForm.value.client_bot_token) {
      payload.client_bot_token = configForm.value.client_bot_token
    }
    payload.client_bot_enabled = configForm.value.client_bot_enabled

    const { data } = await botsApi.updateConfig(payload)

    configAlert.value = { type: 'success', message: data.message }

    // Clear token fields after save
    configForm.value.admin_bot_token = ''
    configForm.value.client_bot_token = ''
    configForm.value.admin_allowed_users = ''

    // Reload config to show updated masked tokens
    await loadConfig()
    setTimeout(loadStatuses, 2000)
  } catch (err) {
    configAlert.value = {
      type: 'error',
      message: err.response?.data?.detail || err.message,
    }
  } finally {
    configSaving.value = false
  }
}

onMounted(() => {
  loadStatuses()
  loadConfig()
  loadLogs()
})
</script>

<style scoped>
/* Keep status badge anchored on mobile when title wraps */
.stat-card .d-flex > .badge {
  flex-shrink: 0;
  align-self: flex-start;
  white-space: nowrap;
}

.log-viewer {
  max-height: 300px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 0.78em;
  background: var(--vxy-code-bg);
  border-radius: 6px;
  padding: 8px;
}
.log-line {
  display: flex;
  gap: 8px;
  padding: 1px 0;
  border-bottom: 1px solid var(--vxy-border);
}
.log-time { color: #6c757d; white-space: nowrap; }
.log-level { min-width: 52px; font-weight: 600; }
.log-level-error, .log-level-critical { color: #dc3545; }
.log-level-warning { color: #fd7e14; }
.log-level-info { color: #0d6efd; }
.log-level-debug { color: #6c757d; }
.log-msg { flex: 1; word-break: break-all; }
.log-error { background: rgba(220,53,69,0.06); }
.log-warn { background: rgba(253,126,20,0.06); }
</style>
