<template>
  <div class="container-fluid py-4 updates-page">
    <div class="updates-page__header">
      <h2 class="mb-0 updates-page__title"><i class="mdi mdi-arrow-up-bold-circle me-2"></i>{{ $t('nav.updates') }}</h2>
      <div class="updates-page__actions">
        <button class="btn btn-outline-secondary btn-sm updates-page__action-btn"
                @click="checkUpdates"
                :disabled="checking || updateInProgress || applying">
          <span v-if="checking" class="spinner-border spinner-border-sm me-1"></span>
          {{ checking ? $t('updates.checking') : $t('updates.checkNow') }}
        </button>
        <button class="btn btn-outline-warning btn-sm updates-page__action-btn"
                @click="restartServices"
                :disabled="restarting || updateInProgress">
          <span v-if="restarting" class="spinner-border spinner-border-sm me-1"></span>
          <i v-if="!restarting" class="mdi mdi-restart me-1"></i>{{ restarting ? $t('updates.restarting') : $t('updates.restartServices') }}
        </button>
      </div>
    </div>

    <!-- Check error alert (inline, not hidden in card) -->
    <div v-if="checkError" class="alert alert-warning alert-dismissible d-flex align-items-start gap-2 mb-3">
      <i class="mdi mdi-alert text-warning fs-5"></i>
      <div class="flex-grow-1">
        <strong>{{ $t('updates.checkFailed') }}:</strong> {{ checkError }}
      </div>
      <button type="button" class="btn-close" @click="checkError=null"></button>
    </div>

    <!-- Current state cards -->
    <div class="row g-3 mb-4">
      <!-- Current version -->
      <div class="col-md-6">
        <div class="card h-100 updates-summary-card">
          <div class="card-body">
            <h6 class="card-subtitle text-muted mb-3">{{ $t('updates.currentVersion') }}</h6>
            <div class="d-flex align-items-center gap-3 flex-wrap updates-summary-card__badges">
              <span class="badge bg-secondary fs-6 px-3 py-2">{{ status.current_version || '—' }}</span>
              <!-- Up-to-date badge -->
              <span v-if="!status.available_update && !status.check_error && status.current_version && !updateInProgress"
                    class="badge bg-success">
                <i class="mdi mdi-check me-1"></i>{{ $t('updates.upToDate') }}
              </span>
              <!-- In-progress badge -->
              <span v-if="updateInProgress" class="badge bg-primary">
                <span class="spinner-border spinner-border-sm me-1" style="width:.6rem;height:.6rem;"></span>
                {{ $t('updates.inProgress') }}
              </span>
            </div>
            <div class="mt-2 small text-muted updates-summary-card__meta" v-if="status.last_update_at">
              {{ $t('updates.lastUpdate') }}: {{ formatDate(status.last_update_at) }}
            </div>
            <div class="mt-1 small d-flex align-items-center gap-1 flex-wrap updates-summary-card__channel">
              <span class="text-muted">{{ $t('updates.channel') }}: </span>
              <span class="badge" :class="status.channel === 'test' ? 'bg-warning text-dark' : 'bg-secondary'">
                {{ status.channel || 'stable' }}
              </span>
              <HelpTooltip :text="$t('help.updateChannel')" />
            </div>
          </div>
        </div>
      </div>

      <!-- Available update -->
      <div class="col-md-6">
        <div class="card h-100 updates-summary-card" :class="availableUpdateCardClass">
          <div class="card-body">
            <h6 class="card-subtitle text-muted mb-3">{{ $t('updates.availableUpdate') }}</h6>

            <!-- No update available -->
            <div v-if="!status.available_update && !status.check_error">
              <p class="text-muted mb-0">{{ $t('updates.noUpdates') }}</p>
            </div>

            <!-- Check error (compact) -->
            <div v-else-if="status.check_error && !status.available_update">
              <div class="text-warning small"><i class="mdi mdi-alert me-1"></i>{{ status.check_error }}</div>
            </div>

            <!-- Update available -->
            <div v-else-if="status.available_update">
              <div class="d-flex align-items-center gap-2 mb-2 flex-wrap">
                <span class="badge bg-primary fs-6 px-3 py-2">{{ status.available_update.version }}</span>
                <span class="badge" :class="updateTypeBadge(status.available_update.update_type)">
                  {{ status.available_update.update_type }}
                </span>
                <span v-if="status.available_update.has_db_migrations" class="badge bg-warning text-dark">
                  {{ $t('updates.dbMigrations') }}
                </span>
                <span v-if="status.available_update.requires_restart" class="badge bg-secondary">
                  {{ $t('updates.requiresRestart') }}
                </span>
              </div>
              <div class="d-flex gap-2 mt-3 updates-available-actions">
                <button class="btn btn-sm btn-outline-info"
                        @click="showChangelog(status.available_update)"
                        :disabled="updateInProgress || applying">
                  <i class="mdi mdi-text-box-outline me-1"></i>{{ $t('updates.changelog') }}
                </button>
                <button class="btn btn-sm btn-primary"
                        @click="confirmApply"
                        :disabled="updateInProgress || applying">
                  <span v-if="applying" class="spinner-border spinner-border-sm me-1"></span>
                  <i v-else class="mdi mdi-arrow-up-bold me-1"></i>{{ $t('updates.install') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Update in progress -->
    <div v-if="progress && isActiveStatus(progress.status)" class="card mb-4 border-primary">
      <div class="card-header bg-primary text-white d-flex align-items-center gap-2">
        <span class="spinner-border spinner-border-sm"></span>
        {{ progress.status === 'in_progress' ? $t('updates.inProgress') : progress.status }} — {{ progress.step }}
      </div>
      <div class="card-body">
        <div class="progress mb-3" style="height: 20px;">
          <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary"
               :style="{width: progressPercent + '%'}">
            {{ progress.step_number }}/{{ progress.total_steps }}
          </div>
        </div>
        <div ref="logContainer" class="update-log bg-dark text-light p-3 rounded"
             style="max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.8rem;">
          <div v-for="(line, i) in progress.log" :key="i">{{ line }}</div>
        </div>
      </div>
    </div>

    <!-- Completed update result -->
    <div v-if="progress && !isActiveStatus(progress.status)" class="card mb-4"
         :class="terminalCardClass(progress.status)">
      <div class="card-header" :class="terminalHeaderClass(progress.status)">
        <span v-if="progress.status === 'success'"><i class="mdi mdi-check-circle me-1"></i>{{ $t('updates.success') }}</span>
        <span v-else-if="progress.status === 'rolled_back'"><i class="mdi mdi-undo-variant me-1"></i>{{ $t('updates.rolledBack') }}</span>
        <span v-else><i class="mdi mdi-close-circle me-1"></i>{{ $t('updates.failed') }}<span v-if="progress.error">: {{ progress.error }}</span></span>
      </div>
      <div v-if="progress.log && progress.log.length" class="card-body">
        <div class="update-log bg-dark text-light p-3 rounded"
             style="max-height: 150px; overflow-y: auto; font-family: monospace; font-size: 0.8rem;">
          <div v-for="(line, j) in progress.log" :key="j">{{ line }}</div>
        </div>
      </div>
    </div>

    <!-- Restart pending banner -->
    <div v-if="status.restart_pending && !updateInProgress" class="card mb-4 border-warning">
      <div class="card-body d-flex align-items-center justify-content-between gap-3 flex-wrap">
        <div>
          <strong><i class="mdi mdi-restart text-warning me-1"></i>{{ $t('updates.restartRequired') }}</strong>
          <div class="text-muted small mt-1">{{ $t('updates.restartNote') }}</div>
        </div>
        <button class="btn btn-warning"
                @click="restartServices"
                :disabled="restarting">
          <span v-if="restarting" class="spinner-border spinner-border-sm me-1"></span>
          {{ restarting ? $t('updates.restarting') : $t('updates.restartServices') }}
        </button>
      </div>
    </div>

    <!-- Waiting for restart -->
    <div v-if="waitingRestart" class="card mb-4 border-warning">
      <div class="card-body">
        <div class="d-flex align-items-center gap-3 mb-2">
          <span class="spinner-border spinner-border-sm text-warning flex-shrink-0"></span>
          <strong><i class="mdi mdi-restart text-warning me-1"></i>{{ $t('updates.waitingRestart') }}</strong>
        </div>
        <div class="text-muted small">
          {{ $t('updates.restartInProgress') }}
          <span v-if="restartCountdown > 0" class="ms-1">
            {{ $t('updates.restartEta', { sec: restartCountdown }) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Update History -->
    <div class="card update-history-card">
      <div class="card-header">
        <h5 class="mb-0"><i class="mdi mdi-history me-2"></i>{{ $t('updates.history') }}</h5>
      </div>
      <div class="card-body p-0">
        <div v-if="!history.length" class="text-center text-muted py-4">
          {{ $t('updates.noHistory') }}
        </div>
        <div v-else class="table-responsive updates-history-table d-none d-md-block">
          <table class="table table-hover mb-0">
            <thead class="table-light">
              <tr>
                <th>{{ $t('updates.version') }}</th>
                <th class="d-none d-sm-table-cell">{{ $t('updates.type') }}</th>
                <th>{{ $t('updates.status') }}</th>
                <th class="d-none d-md-table-cell">{{ $t('updates.date') }}</th>
                <th class="d-none d-lg-table-cell">{{ $t('updates.duration') }}</th>
                <th class="d-none d-lg-table-cell">{{ $t('updates.by') }}</th>
                <th>{{ $t('updates.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in history" :key="rec.id">
                <td>
                  <div>
                    <span class="text-muted small">{{ rec.from_version }}</span>
                    <span class="mx-1">→</span>
                    <strong>{{ rec.to_version }}</strong>
                  </div>
                  <small class="text-muted d-md-none">{{ formatDate(rec.started_at) }}</small>
                </td>
                <td class="d-none d-sm-table-cell">
                  <span v-if="rec.is_rollback" class="badge bg-info text-dark"><i class="mdi mdi-undo-variant me-1"></i>rollback</span>
                  <span v-else class="badge" :class="updateTypeBadge(rec.update_type)">{{ rec.update_type || '—' }}</span>
                </td>
                <td>
                  <span class="badge" :class="statusBadge(rec.status)">{{ rec.status }}</span>
                </td>
                <td class="d-none d-md-table-cell small text-muted">{{ formatDate(rec.started_at) }}</td>
                <td class="d-none d-lg-table-cell small text-muted">{{ formatDuration(rec.duration_seconds) }}</td>
                <td class="d-none d-lg-table-cell small">{{ rec.started_by }}</td>
                <td>
                  <button v-if="rec.has_log" class="btn btn-xs btn-outline-secondary me-1"
                          @click="viewLog(rec.id)" :title="$t('updates.updateLog')">
                    <i class="mdi mdi-file-document-outline"></i>
                  </button>
                  <button v-if="rec.rollback_available && rec.backup_path_exists && !updateInProgress"
                          class="btn btn-xs btn-outline-warning"
                          @click="confirmRollback(rec)"
                          :title="$t('updates.rollbackNow')">
                    <i class="mdi mdi-undo-variant"></i>
                  </button>
                  <span v-else-if="rec.rollback_available && !rec.backup_path_exists"
                        class="text-muted small" :title="$t('updates.backupMissing')">
                    <i class="mdi mdi-alert"></i>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="updates-history-mobile-list d-md-none">
          <div v-for="rec in history" :key="'mobile-' + rec.id" class="updates-history-mobile-card">
            <div class="updates-history-mobile-card__top">
              <div class="updates-history-mobile-card__version">
                <span class="text-muted small">{{ rec.from_version }}</span>
                <span class="mx-1">→</span>
                <strong>{{ rec.to_version }}</strong>
              </div>
              <span class="badge" :class="statusBadge(rec.status)">{{ rec.status }}</span>
            </div>

            <div class="updates-history-mobile-card__meta">
              <div class="updates-history-mobile-card__meta-row">
                <span class="text-muted">{{ $t('updates.type') }}</span>
                <span>
                  <span v-if="rec.is_rollback" class="badge bg-info text-dark"><i class="mdi mdi-undo-variant me-1"></i>rollback</span>
                  <span v-else class="badge" :class="updateTypeBadge(rec.update_type)">{{ rec.update_type || '—' }}</span>
                </span>
              </div>
              <div class="updates-history-mobile-card__meta-row">
                <span class="text-muted">{{ $t('updates.date') }}</span>
                <span>{{ formatDate(rec.started_at) }}</span>
              </div>
              <div v-if="rec.duration_seconds != null" class="updates-history-mobile-card__meta-row">
                <span class="text-muted">{{ $t('updates.duration') }}</span>
                <span>{{ formatDuration(rec.duration_seconds) }}</span>
              </div>
              <div v-if="rec.started_by" class="updates-history-mobile-card__meta-row">
                <span class="text-muted">{{ $t('updates.by') }}</span>
                <span>{{ rec.started_by }}</span>
              </div>
            </div>

            <div class="updates-history-mobile-card__actions">
              <button v-if="rec.has_log" class="btn btn-sm btn-outline-secondary"
                      @click="viewLog(rec.id)">
                <i class="mdi mdi-file-document-outline me-1"></i>{{ $t('updates.updateLog') }}
              </button>
              <button v-if="rec.rollback_available && rec.backup_path_exists && !updateInProgress"
                      class="btn btn-sm btn-outline-warning"
                      @click="confirmRollback(rec)">
                <i class="mdi mdi-undo-variant me-1"></i>{{ $t('updates.rollbackNow') }}
              </button>
              <div v-else-if="rec.rollback_available && !rec.backup_path_exists"
                   class="text-muted small updates-history-mobile-card__warning">
                <i class="mdi mdi-alert me-1"></i>{{ $t('updates.backupMissing') }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Changelog modal -->
    <div v-if="changelogModal" class="modal show d-block" tabindex="-1" @click.self="changelogModal=null">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              {{ $t('updates.changelogFor') }} {{ changelogModal.version }}
              <span class="badge ms-2" :class="updateTypeBadge(changelogModal.update_type)">{{ changelogModal.update_type }}</span>
            </h5>
            <button class="btn-close" @click="changelogModal=null"></button>
          </div>
          <div class="modal-body">
            <div v-if="changelogModal.release_date" class="text-muted small mb-3">
              <i class="mdi mdi-calendar-outline me-1"></i>{{ formatDate(changelogModal.release_date) }}
            </div>
            <pre class="bg-light p-3 rounded" style="white-space: pre-wrap; font-family: inherit;">{{ changelogModal.changelog || $t('updates.noChangelog') }}</pre>
            <div v-if="changelogModal.has_db_migrations" class="alert alert-warning mt-3 mb-0">
              <i class="mdi mdi-alert me-1"></i>{{ $t('updates.hasMigrations') }}
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="changelogModal=null">{{ $t('common.close') }}</button>
            <button class="btn btn-primary"
                    @click="confirmApply(); changelogModal=null"
                    :disabled="updateInProgress || applying">
              <i class="mdi mdi-arrow-up-bold me-1"></i>{{ $t('updates.install') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Log modal -->
    <div v-if="logModal" class="modal show d-block" tabindex="-1" @click.self="logModal=null">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('updates.updateLog') }} #{{ logModal.id }}</h5>
            <button class="btn-close" @click="logModal=null"></button>
          </div>
          <div class="modal-body p-0">
            <pre class="bg-dark text-light m-0 p-3 rounded"
                 style="max-height: 400px; overflow-y: auto; font-size: 0.8rem; white-space: pre-wrap;">{{ logModal.log || $t('updates.noLog') }}</pre>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="logModal=null">{{ $t('common.close') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm apply modal -->
    <div v-if="applyConfirm" class="modal show d-block" tabindex="-1" @click.self="applyConfirm=false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header bg-primary text-white">
            <h5 class="modal-title"><i class="mdi mdi-arrow-up-bold me-2"></i>{{ $t('updates.confirmInstall') }}</h5>
            <button class="btn-close btn-close-white" @click="applyConfirm=false"></button>
          </div>
          <div class="modal-body">
            <p>{{ $t('updates.confirmInstallMsg', {version: status.available_update?.version}) }}</p>
            <ul class="small">
              <li>{{ $t('updates.backupCreated') }}</li>
              <li>{{ $t('updates.servicesRestart') }}</li>
              <li v-if="status.available_update?.has_db_migrations">{{ $t('updates.migrationsRun') }}</li>
              <li>{{ $t('updates.rollbackAvailable') }}</li>
            </ul>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="applyConfirm=false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="applyUpdate" :disabled="applying">
              <span v-if="applying" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('updates.installNow') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm rollback modal -->
    <div v-if="rollbackTarget" class="modal show d-block" tabindex="-1" @click.self="rollbackTarget=null">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header bg-warning">
            <h5 class="modal-title d-flex align-items-center gap-2"><i class="mdi mdi-undo-variant"></i>{{ $t('updates.confirmRollback') }}<HelpTooltip :text="$t('help.rollback')" /></h5>
            <button class="btn-close" @click="rollbackTarget=null"></button>
          </div>
          <div class="modal-body">
            <p>{{ $t('updates.confirmRollbackMsg', {from: rollbackTarget.to_version, to: rollbackTarget.from_version}) }}</p>
            <div class="alert alert-warning"><i class="mdi mdi-alert me-1"></i>{{ $t('updates.rollbackWarning') }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="rollbackTarget=null">{{ $t('common.cancel') }}</button>
            <button class="btn btn-warning" @click="doRollback">{{ $t('updates.rollbackNow') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n()

const status         = ref({})
const history        = ref([])
const checking       = ref(false)
const applying       = ref(false)   // prevents double-submit on "Install Now"
const checkError     = ref(null)    // inline error for check failures
const progress       = ref(null)
const changelogModal = ref(null)
const logModal       = ref(null)
const applyConfirm   = ref(false)
const rollbackTarget = ref(null)
const logContainer   = ref(null)
const restarting        = ref(false)
const waitingRestart    = ref(false)
const restartCountdown  = ref(0)

let pollTimer       = null
let restartTimer    = null
let countdownTimer  = null

// ── Terminal states ────────────────────────────────────────────────────────────

const TERMINAL_STATUSES = new Set(['success', 'failed', 'rolled_back'])
const ACTIVE_STATUSES   = new Set(['in_progress', 'pending', 'downloading', 'applying', 'rolling_back'])

function isActiveStatus(s) {
  return ACTIVE_STATUSES.has(s)
}

// ── Computed ──────────────────────────────────────────────────────────────────

const updateInProgress = computed(() =>
  status.value.update_in_progress || isActiveStatus(progress.value?.status)
)

const progressPercent = computed(() => {
  if (!progress.value) return 0
  const { step_number, total_steps } = progress.value
  if (!step_number || !total_steps) return 5
  return Math.round((step_number / total_steps) * 100)
})

const availableUpdateCardClass = computed(() => {
  if (updateInProgress.value) return 'border-primary'
  if (status.value.available_update) return 'border-primary'
  if (status.value.check_error) return 'border-warning'
  return ''
})

// ── Visual helpers ─────────────────────────────────────────────────────────────

function updateTypeBadge(type) {
  return {
    patch: 'bg-info text-dark',
    minor: 'bg-primary',
    major: 'bg-danger',
  }[type] || 'bg-secondary'
}

function statusBadge(s) {
  return {
    success:      'bg-success',
    failed:       'bg-danger',
    rolled_back:  'bg-info text-dark',   // distinct from bg-secondary for readability
    in_progress:  'bg-primary',
    applying:     'bg-primary',
    downloading:  'bg-info text-dark',
    pending:      'bg-secondary',
    rolling_back: 'bg-warning text-dark',
  }[s] || 'bg-secondary'
}

function terminalCardClass(s) {
  if (s === 'success' || s === 'rolled_back') return 'border-success'
  return 'border-danger'
}

function terminalHeaderClass(s) {
  if (s === 'success' || s === 'rolled_back') return 'bg-success text-white'
  return 'bg-danger text-white'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function formatDuration(s) {
  if (!s && s !== 0) return '—'
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadStatus() {
  try {
    const res = await api.get('/updates/status')
    status.value = res.data
    // Reload progress if there's an active update
    if (res.data.active_update_id && !progress.value) {
      await loadProgress(res.data.active_update_id)
    }
  } catch (e) {
    // Network errors during status refresh are silent — don't disrupt UI
    console.warn('Updates status refresh failed:', e?.message)
  }
}

async function loadHistory() {
  try {
    const res = await api.get('/updates/history?limit=20')
    history.value = res.data.history || []
  } catch {}
}

async function loadProgress(update_id) {
  try {
    const res = await api.get(`/updates/progress/${update_id}`)
    progress.value = res.data
    await nextTick()
    if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
  } catch (e) {
    // If progress endpoint returns 404 (e.g. orphaned ID), clear progress
    if (e?.response?.status === 404) {
      progress.value = null
    }
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function checkUpdates() {
  checking.value = true
  checkError.value = null
  try {
    const res = await api.post('/updates/check', {}, { timeout: 20000 })
    status.value = { ...status.value, ...res.data }
    if (res.data.error) {
      checkError.value = res.data.error
    }
  } catch (e) {
    checkError.value = e.response?.data?.detail || e.message || t('updates.checkFailed')
  } finally {
    checking.value = false
  }
}

function showChangelog(update) {
  changelogModal.value = update
}

function confirmApply() {
  if (updateInProgress.value || applying.value) return
  applyConfirm.value = true
}

async function applyUpdate() {
  if (applying.value) return   // guard double-submit
  applying.value  = true
  applyConfirm.value = false
  try {
    const res = await api.post('/updates/apply')
    const update_id = res.data.update_id
    status.value = {
      ...status.value,
      update_in_progress: true,
      active_update_id:   update_id,
    }
    progress.value = {
      update_id,
      status:      'in_progress',
      step:        'Starting…',
      step_number: 0,
      total_steps: 10,
      log:         [],
      started_at:  new Date().toISOString(),
      error:       null,
    }
    startPolling(update_id)
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || 'Update failed to start'
    checkError.value = msg
  } finally {
    applying.value = false
  }
}

function confirmRollback(rec) {
  rollbackTarget.value = rec
}

async function doRollback() {
  const rec = rollbackTarget.value
  rollbackTarget.value = null
  try {
    const res = await api.post(`/updates/rollback/${rec.id}`)
    const rollback_id = res.data.rollback_id
    status.value = { ...status.value, update_in_progress: true }
    progress.value = {
      update_id:   rollback_id,
      status:      'in_progress',
      step:        'Rolling back…',
      step_number: 0,
      total_steps: 5,
      log:         [],
      started_at:  new Date().toISOString(),
      error:       null,
    }
    startPolling(rollback_id)
  } catch (e) {
    checkError.value = e.response?.data?.detail || e.message || 'Rollback failed to start'
  }
}

async function viewLog(id) {
  try {
    const res = await api.get(`/updates/log/${id}`)
    logModal.value = { id, log: res.data.log }
  } catch {}
}

async function restartServices() {
  if (restarting.value) return
  restarting.value = true
  try {
    await api.post('/updates/restart')
  } catch { /* API may already be restarting */ }
  restarting.value = false
  waitingRestart.value = true
  // Start countdown
  restartCountdown.value = 20
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    if (restartCountdown.value > 0) restartCountdown.value--
    else { clearInterval(countdownTimer); countdownTimer = null }
  }, 1000)
  // Poll until API comes back up
  if (restartTimer) clearInterval(restartTimer)
  restartTimer = setInterval(async () => {
    try {
      await api.get('/updates/status', { timeout: 3000 })
      // API responded — restart complete
      clearInterval(restartTimer)
      restartTimer = null
      if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
      restartCountdown.value = 0
      waitingRestart.value = false
      await Promise.all([loadStatus(), loadHistory()])
    } catch { /* still restarting */ }
  }, 2000)
}

// ── Polling ───────────────────────────────────────────────────────────────────

function startPolling(update_id) {
  stopPolling()
  pollTimer = setInterval(async () => {
    await loadProgress(update_id)
    const s = progress.value?.status
    // Stop polling when we reach any terminal or unknown state
    if (s && !isActiveStatus(s)) {
      stopPolling()
      await Promise.all([loadStatus(), loadHistory()])
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([loadStatus(), loadHistory()])
  // Resume polling if an update is in progress
  if (status.value.active_update_id) {
    startPolling(status.value.active_update_id)
  }
})

onUnmounted(() => {
  stopPolling()
  if (restartTimer) clearInterval(restartTimer)
})
</script>

<style scoped>
.btn-xs {
  font-size: 0.75rem;
  padding: 0.15rem 0.4rem;
}
.update-log {
  font-size: 0.78rem;
}
@media (max-width: 767.98px) {
  .update-history-card { overflow: hidden; }
}
</style>
