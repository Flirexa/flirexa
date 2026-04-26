<template>
  <div class="backup-page">
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4 mobile-toolbar">
      <div>
        <h4 class="mb-0 d-flex align-items-center gap-2">&#x1F4BE; {{ $t('backup.header') }}<HelpTooltip :text="$t('help.backup')" /></h4>
        <small class="text-muted">{{ $t('backup.subtitle') }}</small>
      </div>
      <button class="btn btn-primary btn-sm" @click="createBackup" :disabled="creating">
        <span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
        &#x2795; Create Backup
      </button>
    </div>

    <!-- Create progress -->
    <div v-if="creating" class="alert alert-info d-flex align-items-center gap-2 mb-3">
      <span class="spinner-border spinner-border-sm"></span>
      <span>{{ $t('backup.creating') }}</span>
    </div>

    <!-- Last operation result -->
    <div v-if="lastResult" class="alert mb-3"
         :class="lastResult.ok ? 'alert-success' : 'alert-warning'">
      <strong>{{ lastResult.title }}</strong>
      <div class="small mt-1">{{ lastResult.message }}</div>
      <div v-if="lastResult.errors && lastResult.errors.length" class="mt-2">
        <div v-for="e in lastResult.errors" :key="e" class="text-danger small">&#x26A0; {{ e }}</div>
      </div>
    </div>

    <!-- Backup list -->
    <div class="card border-0 shadow-sm">
      <div class="card-header py-2 d-flex justify-content-between align-items-center">
        <span class="fw-semibold small">&#x1F4C2; {{ $t('backup.availableBackups') }}</span>
        <button class="btn btn-sm btn-outline-secondary" @click="loadBackups" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          &#x1F504; Refresh
        </button>
      </div>

      <div v-if="loading && !backups.length" class="card-body">
        <div class="placeholder-glow">
          <span class="placeholder col-12 mb-2 d-block"></span>
          <span class="placeholder col-12 mb-2 d-block"></span>
          <span class="placeholder col-8 d-block"></span>
        </div>
      </div>

      <div v-else-if="!backups.length" class="card-body text-center text-muted py-5">
        <div style="font-size:2rem">&#x1F4BE;</div>
        <div class="mt-2">{{ $t('backup.noBackups') }}</div>
      </div>

      <div v-else>
        <div class="table-responsive d-none d-sm-block">
          <table class="table table-sm table-hover mb-0" style="font-size:0.85rem">
            <thead class="table-light">
              <tr>
                <th class="ps-3">{{ $t('backup.colId') }}</th>
                <th>{{ $t('backup.colCreated') }}</th>
                <th>{{ $t('backup.colSize') }}</th>
                <th>{{ $t('backup.colContents') }}</th>
                <th>{{ $t('backup.colFormat') }}</th>
                <th class="pe-3 text-end">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in backups" :key="b.backup_id">
                <td class="ps-3">
                  <code class="small">{{ b.backup_id }}</code>
                  <span v-if="b.is_prerestore" class="badge bg-secondary ms-1" style="font-size:0.65rem">
                    {{ $t('backup.tagPreRestore') }}
                  </span>
                </td>
                <td>
                  <span v-if="b.timestamp">{{ formatTime(b.timestamp) }}</span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td>{{ formatSizeMb(b.archive_size_mb) }}</td>
                <td>
                  <span v-for="item in getBackupContents(b)" :key="item.key"
                        class="badge bg-secondary text-white me-1" style="font-size:0.7rem">
                    {{ item.label }}
                  </span>
                  <span v-if="b.errors && b.errors.length" class="badge bg-warning text-dark" style="font-size:0.7rem">
                    {{ b.errors.length }} warn
                  </span>
                </td>
                <td>
                  <span class="badge" :class="b.format === 'tar.gz' ? 'bg-success text-white' : 'bg-secondary text-white'"
                        style="font-size:0.7rem">
                    {{ b.format === 'tar.gz' ? $t('backup.fmtV2') : $t('backup.fmtV1') }}
                  </span>
                </td>
                <td class="pe-3 text-end">
                  <div class="btn-group btn-group-sm mobile-table-actions">
                    <button v-if="b.format === 'tar.gz' && !b.is_prerestore"
                            class="btn btn-outline-secondary"
                            @click="verifyBackup(b)"
                            :disabled="operating === b.backup_id"
                            title="Verify integrity">
                      <span v-if="operating === b.backup_id && opType === 'verify'"
                            class="spinner-border spinner-border-sm"></span>
                      <span v-else>&#x2714; Verify</span>
                    </button>
                    <button v-if="b.format === 'tar.gz' && !b.is_prerestore"
                            class="btn btn-outline-warning"
                            @click="confirmRestore(b, 'full')"
                            :disabled="!!operating">
                      &#x1F504; {{ $t('backup.btnFullRestore') }}<HelpTooltip :text="$t('help.fullRestore')" />
                    </button>
                    <button class="btn btn-outline-primary"
                            @click="confirmRestore(b, 'database')"
                            :disabled="!!operating">
                      {{ $t('backup.btnDbOnly') }}<HelpTooltip :text="$t('help.dbOnlyRestore')" />
                    </button>
                    <button class="btn btn-outline-danger"
                            @click="confirmDelete(b)"
                            :disabled="!!operating">
                      &#x1F5D1;
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="backup-mobile-list d-grid gap-3 d-sm-none p-3 pt-0">
          <article v-for="b in backups" :key="`${b.backup_id}-mobile`" class="card border backup-mobile-card shadow-sm">
            <div class="card-body p-3">
              <div class="d-flex align-items-start justify-content-between gap-2 mb-3">
                <div class="min-w-0 flex-grow-1">
                  <div class="text-muted text-uppercase backup-mobile-card__label">Backup ID</div>
                  <div class="d-flex align-items-center flex-wrap gap-2 mt-1">
                    <code class="backup-mobile-card__id">{{ b.backup_id }}</code>
                    <span v-if="b.is_prerestore" class="badge bg-secondary">{{ $t('backup.tagPreRestore') }}</span>
                    <span class="badge" :class="b.format === 'tar.gz' ? 'bg-success text-white' : 'bg-secondary text-white'">
                      {{ b.format === 'tar.gz' ? $t('backup.fmtV2') : $t('backup.fmtV1') }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="backup-mobile-card__meta mb-3">
                <div class="backup-mobile-card__meta-row">
                  <span class="text-muted">Created</span>
                  <strong>{{ b.timestamp ? formatTime(b.timestamp) : '—' }}</strong>
                </div>
                <div class="backup-mobile-card__meta-row">
                  <span class="text-muted">Size</span>
                  <strong>{{ formatSizeMb(b.archive_size_mb) }}</strong>
                </div>
              </div>

              <div class="mb-3">
                <div class="text-muted text-uppercase backup-mobile-card__label mb-2">Contents</div>
                <div class="backup-mobile-card__chips">
                  <span v-for="item in getBackupContents(b)" :key="item.key" class="badge bg-secondary text-white backup-mobile-card__chip">
                    {{ item.label }}
                  </span>
                  <span v-if="b.errors && b.errors.length" class="badge bg-warning text-dark backup-mobile-card__chip">
                    {{ b.errors.length }} warn
                  </span>
                </div>
              </div>

              <div class="text-muted text-uppercase backup-mobile-card__label mb-2">Actions</div>
              <div class="backup-mobile-card__actions d-grid gap-2">
                <button v-if="b.format === 'tar.gz' && !b.is_prerestore"
                        class="btn btn-warning"
                        @click="confirmRestore(b, 'full')"
                        :disabled="!!operating">
                  {{ $t('backup.btnFullRestore') }}
                </button>
                <button class="btn btn-outline-primary"
                        @click="confirmRestore(b, 'database')"
                        :disabled="!!operating">
                  {{ $t('backup.btnDbOnly') }}
                </button>
                <button v-if="b.format === 'tar.gz' && !b.is_prerestore"
                        class="btn btn-outline-secondary"
                        @click="verifyBackup(b)"
                        :disabled="operating === b.backup_id">
                  <span v-if="operating === b.backup_id && opType === 'verify'" class="spinner-border spinner-border-sm me-1"></span>
                  <span v-else>Verify</span>
                </button>
                <button class="btn btn-outline-danger"
                        @click="confirmDelete(b)"
                        :disabled="!!operating">
                  Delete
                </button>
              </div>
            </div>
          </article>
        </div>
      </div>
    </div>

    <!-- Verify result panel -->
    <div v-if="verifyResult" class="card mt-3 border-0 shadow-sm"
         :class="verifyResult.ok ? 'border-success' : 'border-warning'">
      <div class="card-header py-2 d-flex justify-content-between align-items-center"
           :class="verifyResult.ok ? 'bg-success bg-opacity-10 text-success' : 'bg-warning bg-opacity-10 text-warning'">
        <span class="fw-semibold small">
          {{ verifyResult.ok ? '✅ ' + $t('backup.verifiedOk') : '⚠️ ' + $t('backup.verifiedFail') }}
          — {{ verifyResult.backup_id }}
        </span>
        <button class="btn-close btn-sm" @click="verifyResult = null"></button>
      </div>
      <div class="card-body py-2 px-3">
        <div class="row g-2 small">
          <div class="col-auto">
            <span class="text-muted">{{ $t('backup.filesChecked') }}:</span>
            <strong class="ms-1">{{ verifyResult.files_checked }}</strong>
          </div>
          <template v-if="verifyResult.metadata">
            <div class="col-auto">
              <span class="text-muted">{{ $t('backup.version') }}:</span>
              <strong class="ms-1">{{ verifyResult.metadata.version }}</strong>
            </div>
            <div class="col-auto">
              <span class="text-muted">{{ $t('backup.hostname') }}:</span>
              <strong class="ms-1">{{ verifyResult.metadata.hostname }}</strong>
            </div>
          </template>
        </div>
        <div v-if="verifyResult.errors && verifyResult.errors.length" class="mt-2">
          <div v-for="e in verifyResult.errors" :key="e" class="text-danger small">&#x26A0; {{ e }}</div>
        </div>
        <div v-else class="text-success small mt-1">{{ $t('backup.checksumOk') }}</div>
      </div>
    </div>

    <!-- Disaster Recovery info box -->
    <div class="card border-0 shadow-sm mt-3">
      <div class="card-header py-2">
        <span class="fw-semibold small">&#x1F6A8; {{ $t('backup.disasterRecovery') }}</span>
      </div>
      <div class="card-body py-3 small">
        <p class="mb-2">{{ $t('backup.drInstructions') }}:</p>
        <ol class="mb-2 ps-3">
          <li>{{ $t('backup.drStep1') }}</li>
          <li>{{ $t('backup.drStep2') }}</li>
          <li>{{ $t('backup.drStep3') }}</li>
          <li>{{ $t('backup.drStep4') }}</li>
        </ol>
        <p class="mb-0 text-muted">{{ $t('backup.drNote') }}</p>
      </div>
    </div>

    <!-- Confirm modal -->
    <div v-if="confirmModal" class="modal d-block" style="background:rgba(0,0,0,.4)" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ confirmModal.title }}</h5>
            <button class="btn-close" @click="confirmModal = null"></button>
          </div>
          <div class="modal-body">
            <p>{{ confirmModal.message }}</p>
            <div v-if="confirmModal.type === 'full'" class="alert alert-warning py-2 small mb-0">
              <strong>Warning:</strong> This will overwrite the current database, .env file,
              and WireGuard configurations. A pre-restore snapshot will be created first.
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="confirmModal = null">Cancel</button>
            <button class="btn" :class="confirmModal.btnClass" @click="executeConfirmed" :disabled="!!operating">
              <span v-if="operating" class="spinner-border spinner-border-sm me-1"></span>
              {{ confirmModal.btnLabel }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { backupApi } from '../api'

const { t: $t } = useI18n()

const backups      = ref([])
const loading      = ref(false)
const creating     = ref(false)
const operating    = ref(null)   // backup_id currently being operated on
const opType       = ref(null)   // 'verify' | 'restore' | 'delete'
const lastResult   = ref(null)
const verifyResult = ref(null)
const confirmModal = ref(null)

// ── Load ──────────────────────────────────────────────────────────────────────

async function loadBackups() {
  loading.value = true
  try {
    const res = await backupApi.list()
    backups.value = res.data.backups || []
  } catch (e) {
    showResult(false, 'Failed to load backups', e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

// ── Create ────────────────────────────────────────────────────────────────────

async function createBackup() {
  creating.value = true
  lastResult.value = null
  try {
    const res = await backupApi.create()
    const b = res.data.backup
    const errs = b.errors || []
    showResult(
      errs.length === 0,
      `Backup created: ${b.backup_id}`,
      `${b.archive_size_mb} MB · DB: ${b.database_dump ? '✓' : '✗'} · .env: ${b.env_backed_up ? '✓' : '✗'} · ${b.server_count} servers · ${b.client_count} clients`,
      errs
    )
    await loadBackups()
  } catch (e) {
    showResult(false, 'Backup creation failed', e.response?.data?.detail || e.message)
  } finally {
    creating.value = false
  }
}

// ── Verify ────────────────────────────────────────────────────────────────────

async function verifyBackup(b) {
  operating.value = b.backup_id
  opType.value = 'verify'
  verifyResult.value = null
  try {
    const res = await backupApi.verify(b.backup_id)
    verifyResult.value = res.data
  } catch (e) {
    showResult(false, 'Verification failed', e.response?.data?.detail || e.message)
  } finally {
    operating.value = null
    opType.value = null
  }
}

// ── Restore & Delete (with confirmation) ──────────────────────────────────────

function confirmRestore(b, type) {
  if (type === 'full') {
    confirmModal.value = {
      type: 'full',
      backup: b,
      title: 'Full System Restore',
      message: `Restore from backup ${b.backup_id} (${formatTime(b.timestamp)})?`,
      btnClass: 'btn-warning',
      btnLabel: 'Restore',
    }
  } else {
    confirmModal.value = {
      type: 'database',
      backup: b,
      title: 'Restore Database',
      message: `Restore database from backup ${b.backup_id}?`,
      btnClass: 'btn-primary',
      btnLabel: 'Restore DB',
    }
  }
}

function confirmDelete(b) {
  confirmModal.value = {
    type: 'delete',
    backup: b,
    title: 'Delete Backup',
    message: `Delete backup ${b.backup_id} (${b.archive_size_mb} MB)? This cannot be undone.`,
    btnClass: 'btn-danger',
    btnLabel: 'Delete',
  }
}

async function executeConfirmed() {
  const modal = confirmModal.value
  if (!modal) return
  const b = modal.backup
  confirmModal.value = null

  operating.value = b.backup_id
  opType.value = modal.type

  try {
    if (modal.type === 'full') {
      const res = await backupApi.restoreFull(b.backup_id)
      const r = res.data.result
      showResult(
        r.database_restored,
        `Full restore completed`,
        `DB: ${r.database_restored ? '✓' : '✗'} · .env: ${r.env_restored ? '✓' : '✗'} · WG: ${(r.wireguard_restored || []).length} files · Services: ${r.services_restarted ? '✓' : '✗'} · Pre-restore: ${r.pre_restore_snapshot || 'n/a'}`,
        r.errors
      )
    } else if (modal.type === 'database') {
      await backupApi.restoreDatabase(b.backup_id)
      showResult(true, 'Database restored', `Restored from backup ${b.backup_id}`)
    } else if (modal.type === 'delete') {
      await backupApi.delete(b.backup_id)
      showResult(true, 'Backup deleted', b.backup_id)
      await loadBackups()
    }
  } catch (e) {
    showResult(false, `${modal.type} failed`, e.response?.data?.detail || e.message)
  } finally {
    operating.value = null
    opType.value = null
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function showResult(ok, title, message, errors = []) {
  lastResult.value = { ok, title, message, errors }
}

function getBackupContents(b) {
  const items = []
  if (b.database_dump) items.push({ key: 'db', label: $t('backup.tagDb') })
  if (b.env_backed_up) items.push({ key: 'env', label: $t('backup.tagEnv') })
  if (b.server_count) items.push({ key: 'servers', label: `${b.server_count} ${$t('backup.tagSrv')}` })
  if (b.client_count) items.push({ key: 'clients', label: `${b.client_count} ${$t('backup.tagClients')}` })
  return items
}

function formatSizeMb(size) {
  if (size === null || size === undefined || size === '') return '? MB'
  const value = Number(size)
  if (Number.isNaN(value)) return `${size} MB`
  return `${value.toFixed(value >= 10 ? 0 : 2)} MB`
}

function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

onMounted(loadBackups)
</script>
