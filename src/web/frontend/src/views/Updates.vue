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
            <div class="mt-2 small d-flex align-items-center gap-2 flex-wrap">
              <div class="form-check form-switch m-0">
                <input class="form-check-input" type="checkbox"
                       id="autoApplySwitch"
                       :checked="autoApply"
                       :disabled="autoApplySaving"
                       @change="onAutoApplyToggle($event.target.checked)" />
                <label class="form-check-label small" for="autoApplySwitch">
                  {{ $t('updates.autoApplyLabel') || 'Auto-apply updates' }}
                </label>
              </div>
              <HelpTooltip :text="$t('updates.autoApplyHelp') || 'When enabled, the panel installs updates from the current channel as soon as they appear. Turn off to apply manually.'" />
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

    <!-- Update in progress.
         Shown ONLY while there's both a progress record AND its status is
         in the explicit ACTIVE_STATUSES allow-list. We never show this
         card for unknown/null status — that would lie about the panel's
         state and hold the user hostage with a never-ending spinner. -->
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

    <!-- Completed update result.
         Shown ONLY when the backend says the update reached one of the
         explicit terminal states. Unknown / null / mid-flight statuses
         render NOTHING here — those are handled by the in-progress card
         above. This prevents the historic "false fail flash" + the
         current "stuck on Update in progress" issue. -->
    <div v-if="progress && isTerminalStatus(progress.status)" class="card mb-4"
         :class="terminalCardClass(progress.status)">
      <div class="card-header" :class="terminalHeaderClass(progress.status)">
        <span v-if="progress.status === 'success'"><i class="mdi mdi-check-circle me-1"></i>{{ $t('updates.success') }}</span>
        <span v-else-if="progress.status === 'rolled_back'"><i class="mdi mdi-undo-variant me-1"></i>{{ $t('updates.rolledBack') }}</span>
        <span v-else-if="progress.status === 'failed'"><i class="mdi mdi-close-circle me-1"></i>{{ $t('updates.failed') }}<span v-if="progress.error">: {{ progress.error }}</span></span>
        <span v-else><i class="mdi mdi-help-circle me-1"></i>{{ progress.status }}<span v-if="progress.error">: {{ progress.error }}</span></span>
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
const autoApply      = ref(true)
const autoApplySaving = ref(false)
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

// Final state machine for update status. Both sets are EXPLICIT —
// anything not in either is treated as "we don't know" and renders
// nothing rather than guessing.
//
// Why two explicit lists instead of "everything not terminal = active":
// the previous tries leaned on negation, which kept biting us — once
// `null/undefined → active` (1.5.23), once `null → terminal-fallback-fail`
// (1.5.17). Both are wrong. The fix is to render NOTHING for unknown
// states. Idle pages stay clean, and adding a brand-new backend status
// won't silently render either an in-progress card or a fail card.
const ACTIVE_STATUSES = new Set([
  'pending',
  'downloading',
  'downloaded',
  'verified',
  'ready_to_apply',
  'applying',
  'rolling_back',
  'rollback_required',
  'in_progress',
])
const TERMINAL_STATUSES = new Set([
  'success',
  'failed',
  'rolled_back',
  'unknown',  // backend's sentinel when it can't determine outcome
])

function isActiveStatus(s) {
  return ACTIVE_STATUSES.has(s)
}

function isTerminalStatus(s) {
  return TERMINAL_STATUSES.has(s)
}

function isFailedStatus(s) {
  return s === 'failed'
}

// ── Computed ──────────────────────────────────────────────────────────────────

// "Update in progress" iff the backend tells us so OR we have a progress
// object whose status is in the explicit active list. The progress check
// uses BOTH `progress.value` truthiness AND `isActiveStatus(...)` — the
// 1.5.23 version dropped the truthiness check, which made undefined
// status (no progress at all) look active because of how isActiveStatus
// handled null. The new isActiveStatus only returns true for known
// active strings, so this expression is now correct in all cases.
const updateInProgress = computed(() =>
  !!status.value.update_in_progress
  || (!!progress.value && isActiveStatus(progress.value.status))
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
  if (s === 'failed') return 'border-danger'
  // Unknown / not-yet-resolved — neutral colour, so a transient null
  // status doesn't paint the whole card red.
  return 'border-info'
}

function terminalHeaderClass(s) {
  if (s === 'success' || s === 'rolled_back') return 'bg-success text-white'
  if (s === 'failed') return 'bg-danger text-white'
  return 'bg-info text-white'
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

// Retry-with-backoff for status. If the call fails (e.g. nginx 502 during
// API restart, or the worker is rescheduling itself mid-update), we used
// to leave `status.value = {}` and the UI would render an empty
// "Current Version: —" pill. Now we retry up to 4 times with growing
// backoff (1s, 2s, 4s, 8s) so transient blips don't stick. Past attempts
// don't block the whole UI — they happen in the background.
async function loadStatus({ retries = 4, _delay = 1000 } = {}) {
  let lastErr
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const res = await api.get('/updates/status', { timeout: 10000 })
      status.value = res.data
      // Resync progress with whatever the backend says is current.
      //
      // Case A — status says there IS an active update. ALWAYS make sure
      // we have fresh progress AND a running poll loop. The previous
      // version only acted when progress was null, which missed the
      // important case: the panel restarted mid-apply, the browser's
      // pollTimer interval got dropped (browsers can purge intervals
      // when the network stalls long enough or the tab is backgrounded
      // during a 502 storm), and progress is left frozen on
      // "applying" forever. Re-arm both unconditionally — startPolling
      // is idempotent (calls stopPolling first), and re-fetching
      // progress is cheap.
      if (res.data.active_update_id) {
        await loadProgress(res.data.active_update_id)
        if (progress.value && isActiveStatus(progress.value.status) && !pollTimer) {
          startPolling(res.data.active_update_id)
        }
      }
      // Case B — status says NO active update, but our local progress
      // still shows an active state. The polling loop missed the
      // success/failure frame and we're stuck rendering an in-progress
      // card. Pull the latest progress for the update we WERE tracking
      // so the terminal "Update completed" card renders, then stop
      // polling. If even the final fetch can't resolve the state, drop
      // progress so the UI doesn't hang.
      if (!res.data.active_update_id && progress.value && isActiveStatus(progress.value.status)) {
        const stuck_id = progress.value.update_id
        if (stuck_id) {
          await loadProgress(stuck_id)
        }
        stopPolling()
        if (progress.value && isActiveStatus(progress.value.status)) {
          progress.value = null
        }
      }
      return
    } catch (e) {
      lastErr = e
      if (attempt + 1 < retries) {
        await new Promise(r => setTimeout(r, _delay))
        _delay = Math.min(_delay * 2, 8000)
      }
    }
  }
  console.warn('Updates status refresh failed after retries:', lastErr?.message)
  // Belt-and-suspenders: if every retry failed, try the alternate endpoint
  // (/updates/check is a force-refresh path that returns current_version
  // and available_update). It hits the upstream license server even when
  // the manifest cache is empty, so it's strictly more authoritative
  // than /status when /status was unreachable. We only do this once,
  // and only if status is still empty — otherwise we'd hammer the lic
  // server every page load.
  if (!status.value || !status.value.current_version) {
    try {
      const res = await api.post('/updates/check', {}, { timeout: 15000 })
      status.value = { ...status.value, ...res.data }
    } catch (e) {
      console.warn('Fallback /updates/check also failed:', e?.message)
    }
  }
}

async function loadHistory() {
  try {
    const res = await api.get('/updates/history?limit=20')
    history.value = res.data.history || []
  } catch {}
}

async function loadAutoApply() {
  try {
    const res = await api.get('/updates/auto-apply')
    autoApply.value = !!res.data.auto_apply
  } catch (e) {
    // Quiet on failure — Updates page is functional without it.
    console.warn('auto-apply load failed:', e?.message)
  }
}

async function onAutoApplyToggle(checked) {
  // Optimistically reflect the change so the toggle feels snappy; on
  // failure we revert and surface the message.
  const prev = autoApply.value
  autoApply.value = checked
  autoApplySaving.value = true
  try {
    await api.post('/updates/auto-apply', { enabled: checked })
  } catch (e) {
    autoApply.value = prev
    alert(`Failed to update setting: ${e?.response?.data?.detail || e?.message}`)
  } finally {
    autoApplySaving.value = false
  }
}

async function loadProgress(update_id) {
  try {
    const res = await api.get(`/updates/progress/${update_id}`)
    progress.value = res.data
    await nextTick()
    if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
  } catch (e) {
    // If progress endpoint returns 404 (e.g. orphaned ID), clear progress
    // AND stop polling so the loop doesn't keep hammering a missing record
    // until the 30-min wall-clock cap.
    if (e?.response?.status === 404) {
      progress.value = null
      stopPolling()
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
      await Promise.all([loadStatus(), loadHistory(), loadAutoApply()])
    } catch { /* still restarting */ }
  }, 2000)
}

// ── Polling ───────────────────────────────────────────────────────────────────

// Polling has TWO termination paths:
//   1. Status reaches a terminal value (success/failed/rolled_back/unknown).
//   2. Wall-clock cap — 30 minutes — so a hung apply script can't leave
//      the page polling forever. After the cap we stop and drop progress;
//      the user can refresh or wait for the auto-update-check to settle
//      the record via reconcile_inflight_updates.
const POLL_MAX_MS = 30 * 60 * 1000
let pollStartedAt = 0

function startPolling(update_id) {
  stopPolling()
  pollStartedAt = Date.now()
  pollTimer = setInterval(async () => {
    await loadProgress(update_id)
    const s = progress.value?.status
    // 1. Real terminal state — stop and refresh sidebar data.
    if (s && isTerminalStatus(s)) {
      stopPolling()
      await Promise.all([loadStatus(), loadHistory(), loadAutoApply()])
      return
    }
    // 2. Wall-clock cap — give up rather than spin forever.
    if (Date.now() - pollStartedAt > POLL_MAX_MS) {
      console.warn(`Update progress poll exceeded ${POLL_MAX_MS / 60000}m; giving up.`)
      stopPolling()
      progress.value = null
      await Promise.all([loadStatus(), loadHistory(), loadAutoApply()])
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  pollStartedAt = 0
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

// Periodic background refresh + on-focus refresh. The page can land on a
// 502 from nginx if it was opened during the panel restart that follows
// an update. The retry-with-backoff in loadStatus only spans ~15s; if the
// API isn't back by then, the page used to stay empty until the user
// clicked Check-for-updates manually. This timer + visibilitychange hook
// makes the page heal itself on its own once the API comes back.
let refreshTimer = null

function _periodicRefresh() {
  // Don't pile work on top of an in-flight update poll cycle
  if (pollTimer) return
  // Don't bother while the tab is in the background — saves API calls
  if (typeof document !== 'undefined' && document.hidden) return
  loadStatus()
}

function _onVisibility() {
  if (typeof document === 'undefined' || document.hidden) return
  // Tab just became visible: pull fresh state immediately, the user is
  // looking at it.
  loadStatus()
}

onMounted(async () => {
  await Promise.all([loadStatus(), loadHistory(), loadAutoApply()])
  // Belt-and-suspenders for "Current Version stays empty until I click
  // Check for updates" — if loadStatus came back without populating
  // current_version (or didn't run at all due to a long-tail axios bug
  // we couldn't reproduce), fire the same code path the manual button
  // uses. /updates/check returns current_version too and is what the
  // user has confirmed always works.
  if (!status.value || !status.value.current_version) {
    try {
      const res = await api.post('/updates/check', {}, { timeout: 15000 })
      status.value = { ...status.value, ...res.data }
    } catch (e) {
      console.warn('Mount-time /updates/check fallback failed:', e?.message)
    }
  }
  // Resume polling if an update is in progress
  if (status.value.active_update_id) {
    startPolling(status.value.active_update_id)
  }
  // Self-healing background refresh, lighter cadence than progress poll.
  refreshTimer = setInterval(_periodicRefresh, 60_000)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', _onVisibility)
  }
})

onUnmounted(() => {
  stopPolling()
  if (restartTimer) clearInterval(restartTimer)
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', _onVisibility)
  }
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
