<template>
  <div class="backup-page">
    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <div class="d-flex justify-content-between align-items-center mb-4 mobile-toolbar">
      <div>
        <h4 class="mb-0 d-flex align-items-center gap-2">
          <i class="mdi mdi-database-outline"></i>{{ $t('backup.header') }}
          <HelpTooltip :text="$t('help.backup')" />
        </h4>
        <small class="text-muted">{{ $t('backup.subtitle') }}</small>
      </div>
      <button class="btn btn-primary btn-sm" @click="createBackup" :disabled="creating">
        <span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="mdi mdi-plus me-1"></i>{{ $t('backup.createNow') }}
      </button>
    </div>

    <!-- ── Status overview (4 cards) ───────────────────────────────────── -->
    <div class="row g-3 mb-3">
      <div class="col-md-6 col-xl-3">
        <div class="card h-100 border-0 shadow-sm">
          <div class="card-body py-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <i :class="cfg.backup_enabled === 'true' ? 'mdi mdi-check-circle text-success' : 'mdi mdi-pause-circle text-secondary'"></i>
              <span class="small text-muted">{{ $t('backup.statusSchedule') }}</span>
            </div>
            <div class="fw-semibold" :class="cfg.backup_enabled === 'true' ? 'text-success' : 'text-secondary'">
              {{ cfg.backup_enabled === 'true' ? $t('backup.scheduleOn') : $t('backup.scheduleOff') }}
            </div>
            <div class="small text-muted">{{ nextBackupLabel }}</div>
          </div>
        </div>
      </div>

      <div class="col-md-6 col-xl-3">
        <div class="card h-100 border-0 shadow-sm">
          <div class="card-body py-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <i class="mdi mdi-harddisk"></i>
              <span class="small text-muted">{{ $t('backup.statusStorage') }}</span>
            </div>
            <div class="fw-semibold">
              {{ cfg.backup_storage_type === 'network' ? $t('backup.storageNetwork') : $t('backup.storageLocal') }}
              <span v-if="cfg.backup_storage_type === 'network'"
                    class="badge ms-1"
                    :class="storageStatus?.mounted ? 'bg-success' : 'bg-warning text-dark'">
                {{ storageStatus?.mounted ? $t('backup.mounted') : $t('backup.notMounted') }}
              </span>
            </div>
            <div class="small text-muted" v-if="storageStatus?.usage">
              {{ formatMb(storageStatus.usage.free_mb) }} {{ $t('backup.free') }} /
              {{ formatMb(storageStatus.usage.total_mb) }}
            </div>
          </div>
        </div>
      </div>

      <div class="col-md-6 col-xl-3">
        <div class="card h-100 border-0 shadow-sm">
          <div class="card-body py-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <i class="mdi mdi-folder-multiple-outline"></i>
              <span class="small text-muted">{{ $t('backup.statusTotal') }}</span>
            </div>
            <div class="fw-semibold">{{ backups.length }}</div>
            <div class="small text-muted">{{ formatMb(totalSizeMb) }} {{ $t('backup.totalSize') }}</div>
          </div>
        </div>
      </div>

      <div class="col-md-6 col-xl-3">
        <div class="card h-100 border-0 shadow-sm">
          <div class="card-body py-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <i class="mdi mdi-clock-outline"></i>
              <span class="small text-muted">{{ $t('backup.statusLatest') }}</span>
            </div>
            <div v-if="latestBackup" class="fw-semibold">{{ formatTime(latestBackup.timestamp) }}</div>
            <div v-else class="fw-semibold text-muted">{{ $t('backup.noBackupsYet') }}</div>
            <div class="small text-muted" v-if="latestBackup">
              {{ formatMb(latestBackup.archive_size_mb || latestBackup.backup_size_mb) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Result alert (last action) ──────────────────────────────────── -->
    <div v-if="creating" class="alert alert-info d-flex align-items-center gap-2 mb-3">
      <span class="spinner-border spinner-border-sm"></span>
      <span>{{ $t('backup.creating') }}</span>
    </div>
    <div v-if="lastResult" class="alert mb-3" :class="lastResult.ok ? 'alert-success' : 'alert-warning'">
      <strong>{{ lastResult.title }}</strong>
      <div class="small mt-1">{{ lastResult.message }}</div>
      <div v-if="lastResult.errors && lastResult.errors.length" class="mt-2">
        <div v-for="e in lastResult.errors" :key="e" class="text-danger small">
          <i class="mdi mdi-alert me-1"></i>{{ e }}
        </div>
      </div>
    </div>

    <!-- ── Backups list ─────────────────────────────────────────────────── -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-header py-2 d-flex justify-content-between align-items-center">
        <span class="fw-semibold small">
          <i class="mdi mdi-folder-open-outline me-1"></i>{{ $t('backup.availableBackups') }}
        </span>
        <button class="btn btn-sm btn-outline-secondary" @click="loadBackups" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="mdi mdi-refresh me-1"></i>{{ $t('common.refresh') }}
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
        <div style="font-size:2rem"><i class="mdi mdi-database-outline"></i></div>
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
                <th class="pe-3 text-end">{{ $t('common.actions') || 'Actions' }}</th>
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
                <td>{{ formatMb(b.archive_size_mb || b.backup_size_mb) }}</td>
                <td>
                  <span v-for="item in getBackupContents(b)" :key="item.key"
                        class="badge bg-secondary text-white me-1" style="font-size:0.7rem">
                    {{ item.label }}
                  </span>
                  <span v-if="b.errors && b.errors.length" class="badge bg-warning text-dark"
                        style="font-size:0.7rem">
                    {{ b.errors.length }} {{ $t('backup.warnSuffix') || 'warn' }}
                  </span>
                </td>
                <td>
                  <span class="badge"
                        :class="b.format === 'tar.gz' ? 'bg-success text-white' : 'bg-secondary text-white'"
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
                            :title="$t('backup.verifyTitle')">
                      <span v-if="operating === b.backup_id && opType === 'verify'"
                            class="spinner-border spinner-border-sm"></span>
                      <i v-else class="mdi mdi-shield-check"></i>
                    </button>
                    <button v-if="b.format === 'tar.gz'"
                            class="btn btn-outline-warning"
                            @click="confirmRestore(b, 'full')"
                            :disabled="operating === b.backup_id"
                            :title="$t('backup.restoreFullTitle')">
                      <i class="mdi mdi-backup-restore"></i>
                    </button>
                    <button class="btn btn-outline-info"
                            @click="confirmRestore(b, 'database')"
                            :disabled="operating === b.backup_id"
                            :title="$t('backup.restoreDbTitle')">
                      <i class="mdi mdi-database-import"></i>
                    </button>
                    <button class="btn btn-outline-danger"
                            @click="confirmDelete(b)"
                            :disabled="operating === b.backup_id"
                            :title="$t('backup.deleteTitle')">
                      <i class="mdi mdi-delete-outline"></i>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Mobile card layout -->
        <div class="d-sm-none">
          <div v-for="b in backups" :key="b.backup_id" class="border-bottom px-3 py-2">
            <div class="d-flex justify-content-between align-items-start mb-1">
              <code class="small">{{ b.backup_id }}</code>
              <span class="small text-muted">{{ formatMb(b.archive_size_mb || b.backup_size_mb) }}</span>
            </div>
            <div class="small text-muted mb-2">{{ formatTime(b.timestamp) }}</div>
            <div class="btn-group btn-group-sm w-100">
              <button v-if="b.format === 'tar.gz' && !b.is_prerestore"
                      class="btn btn-outline-secondary" @click="verifyBackup(b)" :disabled="operating === b.backup_id">
                <i class="mdi mdi-shield-check"></i>
              </button>
              <button v-if="b.format === 'tar.gz'"
                      class="btn btn-outline-warning" @click="confirmRestore(b, 'full')" :disabled="operating === b.backup_id">
                <i class="mdi mdi-backup-restore"></i>
              </button>
              <button class="btn btn-outline-info" @click="confirmRestore(b, 'database')" :disabled="operating === b.backup_id">
                <i class="mdi mdi-database-import"></i>
              </button>
              <button class="btn btn-outline-danger" @click="confirmDelete(b)" :disabled="operating === b.backup_id">
                <i class="mdi mdi-delete-outline"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Verify result panel ─────────────────────────────────────────── -->
    <div v-if="verifyResult" class="card mb-3 border-0 shadow-sm"
         :class="verifyResult.ok ? 'border-success' : 'border-warning'">
      <div class="card-header py-2 d-flex justify-content-between align-items-center"
           :class="verifyResult.ok ? 'bg-success bg-opacity-10 text-success' : 'bg-warning bg-opacity-10 text-warning'">
        <span class="fw-semibold small">
          <i :class="verifyResult.ok ? 'mdi mdi-check-circle me-1' : 'mdi mdi-alert me-1'"></i>
          {{ verifyResult.ok ? $t('backup.verifiedOk') : $t('backup.verifiedFail') }}
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
          <div v-for="e in verifyResult.errors" :key="e" class="text-danger small">
            <i class="mdi mdi-alert me-1"></i>{{ e }}
          </div>
        </div>
        <div v-else class="text-success small mt-1">{{ $t('backup.checksumOk') }}</div>
      </div>
    </div>

    <!-- ── Schedule section ────────────────────────────────────────────── -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-header py-2">
        <span class="fw-semibold small">
          <i class="mdi mdi-clock-time-four-outline me-1"></i>{{ $t('backup.scheduleTitle') }}
        </span>
      </div>
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-md-4">
            <label class="form-label small">{{ $t('backup.frequency') }}</label>
            <select class="form-select form-select-sm" v-model="cfg.backup_interval_hours">
              <option value="6">{{ $t('backup.every6h') }}</option>
              <option value="12">{{ $t('backup.every12h') }}</option>
              <option value="24">{{ $t('backup.every24h') }}</option>
              <option value="48">{{ $t('backup.every48h') }}</option>
              <option value="168">{{ $t('backup.weekly') }}</option>
            </select>
          </div>
          <div class="col-md-3">
            <label class="form-label small">{{ $t('backup.timeUtc') }}</label>
            <select class="form-select form-select-sm" v-model="cfg.backup_hour_utc">
              <option v-for="h in 24" :key="h-1" :value="String(h-1)">{{ String(h-1).padStart(2,'0') }}:00</option>
            </select>
          </div>
          <div class="col-md-5">
            <div class="d-flex align-items-center gap-3 flex-wrap">
              <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" id="bkEnabled"
                       :checked="cfg.backup_enabled === 'true'"
                       @change="cfg.backup_enabled = $event.target.checked ? 'true' : 'false'" />
                <label class="form-check-label small" for="bkEnabled">{{ $t('backup.autoBackup') }}</label>
              </div>
              <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" id="bkCleanup"
                       :checked="cfg.backup_auto_cleanup === 'true'"
                       @change="cfg.backup_auto_cleanup = $event.target.checked ? 'true' : 'false'" />
                <label class="form-check-label small" for="bkCleanup">{{ $t('backup.autoCleanup') }}</label>
              </div>
            </div>
          </div>
        </div>
        <div class="row g-3 mt-1" v-if="cfg.backup_auto_cleanup === 'true'">
          <div class="col-md-4">
            <label class="form-label small">{{ $t('backup.keepLast') }}</label>
            <div class="input-group input-group-sm">
              <input type="number" class="form-control" v-model="cfg.backup_retention_count" min="1" max="100" />
              <span class="input-group-text">{{ $t('backup.backupsUnit') }}</span>
            </div>
          </div>
        </div>
        <div class="mt-3">
          <button class="btn btn-primary btn-sm" @click="saveSettings" :disabled="saving">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
            {{ $t('common.save') }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── Storage section ─────────────────────────────────────────────── -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-header py-2">
        <span class="fw-semibold small">
          <i class="mdi mdi-harddisk me-1"></i>{{ $t('backup.storageTitle') }}
        </span>
      </div>
      <div class="card-body">
        <div class="d-flex gap-3 mb-3 flex-wrap">
          <div class="form-check">
            <input class="form-check-input" type="radio" name="storageType" id="stLocal" value="local"
                   v-model="cfg.backup_storage_type" />
            <label class="form-check-label" for="stLocal">{{ $t('backup.localPath') }}</label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="radio" name="storageType" id="stNetwork" value="network"
                   v-model="cfg.backup_storage_type" />
            <label class="form-check-label" for="stNetwork">{{ $t('backup.networkMount') }}</label>
          </div>
        </div>

        <!-- Local -->
        <div v-if="cfg.backup_storage_type === 'local'" class="row g-2 align-items-end">
          <div class="col-md">
            <label class="form-label small">{{ $t('backup.path') }}</label>
            <input type="text" class="form-control form-control-sm" v-model="cfg.backup_path" />
          </div>
          <div class="col-md-auto">
            <button class="btn btn-outline-info btn-sm" @click="testWrite" :disabled="testing">
              <span v-if="testing" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('backup.testWrite') }}
            </button>
          </div>
          <div class="col-md-auto">
            <button class="btn btn-primary btn-sm" @click="saveSettings" :disabled="saving">
              {{ $t('common.save') }}
            </button>
          </div>
        </div>

        <!-- Network -->
        <div v-else>
          <div class="row g-3 mb-3">
            <div class="col-md-3">
              <label class="form-label small">{{ $t('backup.protocol') }}</label>
              <select class="form-select form-select-sm" v-model="cfg.backup_mount_type">
                <option value="smb">SMB / CIFS</option>
                <option value="nfs">NFS</option>
              </select>
            </div>
            <div class="col-md-9">
              <label class="form-label small">{{ $t('backup.address') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="cfg.backup_mount_address"
                     :placeholder="cfg.backup_mount_type === 'nfs' ? '192.168.0.10:/backups' : '//192.168.0.10/backups'" />
            </div>
          </div>
          <div class="row g-3 mb-3" v-if="cfg.backup_mount_type === 'smb'">
            <div class="col-md-6">
              <label class="form-label small">{{ $t('backup.username') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="cfg.backup_mount_username"
                     placeholder="backup_user" autocomplete="off" />
            </div>
            <div class="col-md-6">
              <label class="form-label small">{{ $t('backup.password') }}</label>
              <div class="input-group input-group-sm">
                <input :type="showPass ? 'text' : 'password'" class="form-control"
                       v-model="cfg.backup_mount_password"
                       :placeholder="cfg.backup_mount_password_set ? $t('backup.unchanged') : $t('backup.password')"
                       autocomplete="new-password" />
                <button class="btn btn-outline-secondary" type="button" @click="showPass = !showPass">
                  <i :class="showPass ? 'mdi mdi-eye-off' : 'mdi mdi-eye'"></i>
                </button>
              </div>
            </div>
          </div>
          <div class="row g-3 mb-3">
            <div class="col-md-6">
              <label class="form-label small">{{ $t('backup.mountPoint') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="cfg.backup_mount_point" />
            </div>
            <div class="col-md-6">
              <label class="form-label small">{{ $t('backup.extraOptions') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="cfg.backup_mount_options"
                     placeholder="vers=3.0,iocharset=utf8" />
            </div>
          </div>

          <div class="d-flex gap-2 align-items-center flex-wrap">
            <button class="btn btn-primary btn-sm" @click="saveSettings" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('common.save') }}
            </button>
            <button class="btn btn-outline-success btn-sm" @click="mountStorage" :disabled="mounting">
              <span v-if="mounting" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="mdi mdi-link-variant me-1"></i>{{ $t('backup.mountBtn') }}
            </button>
            <button class="btn btn-outline-warning btn-sm" @click="unmountStorage" :disabled="mounting">
              <i class="mdi mdi-link-variant-off me-1"></i>{{ $t('backup.unmountBtn') }}
            </button>
            <button class="btn btn-outline-info btn-sm" @click="testWrite" :disabled="testing">
              <span v-if="testing" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('backup.testWrite') }}
            </button>
            <span class="small ms-2"
                  :class="storageStatus?.mounted ? 'text-success' : 'text-secondary'">
              <i :class="storageStatus?.mounted ? 'mdi mdi-circle text-success' : 'mdi mdi-circle-outline text-secondary'"></i>
              {{ storageStatus?.mounted ? $t('backup.mounted') : $t('backup.notMounted') }}
            </span>
          </div>
        </div>

        <div v-if="settingsAlert" class="alert py-2 small mt-3" :class="settingsAlertType">
          {{ settingsAlert }}
        </div>
      </div>
    </div>

    <!-- ── Disaster Recovery info box ──────────────────────────────────── -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-header py-2">
        <span class="fw-semibold small">
          <i class="mdi mdi-alert-circle-outline text-danger me-1"></i>{{ $t('backup.disasterRecovery') }}
        </span>
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

    <!-- ── Confirm modal ───────────────────────────────────────────────── -->
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
              <strong>{{ $t('backup.warning') }}:</strong> {{ $t('backup.fullRestoreWarn') }}
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="confirmModal = null">{{ $t('common.cancel') }}</button>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { backupApi } from '../api'
import HelpTooltip from '../components/HelpTooltip.vue'

const { t: $t } = useI18n()

// ── List + operations state ────────────────────────────────────────────────
const backups      = ref([])
const loading      = ref(false)
const creating     = ref(false)
const operating    = ref(null)
const opType       = ref(null)
const lastResult   = ref(null)
const verifyResult = ref(null)
const confirmModal = ref(null)

// ── Settings state ─────────────────────────────────────────────────────────
const cfg = reactive({
  backup_enabled:           'true',
  backup_interval_hours:    '24',
  backup_hour_utc:          '3',
  backup_retention_count:   '7',
  backup_auto_cleanup:      'true',
  backup_storage_type:      'local',
  backup_path:              '/opt/vpnmanager/backups',
  backup_mount_type:        'smb',
  backup_mount_address:     '',
  backup_mount_username:    '',
  backup_mount_password:    '',
  backup_mount_password_set: false,
  backup_mount_point:       '/mnt/vpnmanager-backup',
  backup_mount_options:     '',
})
const saving         = ref(false)
const testing        = ref(false)
const mounting       = ref(false)
const showPass       = ref(false)
const settingsAlert  = ref('')
const settingsAlertType = ref('alert-info')
const storageStatus  = ref(null)

// ── Computed ───────────────────────────────────────────────────────────────
const totalSizeMb = computed(() =>
  backups.value.reduce((sum, b) => sum + Number(b.archive_size_mb || b.backup_size_mb || 0), 0)
)
const latestBackup = computed(() => {
  // First non-prerestore backup, since the list is already newest-first
  return backups.value.find(b => !b.is_prerestore) || backups.value[0] || null
})
const nextBackupLabel = computed(() => {
  if (cfg.backup_enabled !== 'true') return $t('backup.scheduleOff')
  const h = String(cfg.backup_hour_utc || '3').padStart(2, '0')
  const interval = cfg.backup_interval_hours || '24'
  if (interval === '168') return `${h}:00 UTC · ${$t('backup.weekly')}`
  if (interval === '24')  return `${h}:00 UTC · ${$t('backup.daily')}`
  return `${$t('backup.everyN', { n: interval })} · ${h}:00 UTC`
})

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadBackups(), loadSettings(), loadStorageStatus()])
})

// ── Loaders ────────────────────────────────────────────────────────────────
async function loadBackups() {
  loading.value = true
  try {
    const res = await backupApi.list()
    backups.value = res.data.backups || []
  } catch (e) {
    showResult(false, $t('backup.loadFailed'), e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const res = await backupApi.getSettings()
    Object.assign(cfg, res.data)
  } catch (_e) { /* keep defaults */ }
}

async function loadStorageStatus() {
  try {
    const res = await backupApi.storageStatus()
    storageStatus.value = res.data
  } catch (_e) {
    storageStatus.value = null
  }
}

// ── Operations ─────────────────────────────────────────────────────────────
async function createBackup() {
  if (!confirm($t('backup.confirmCreate'))) return
  creating.value = true
  lastResult.value = null
  try {
    const res = await backupApi.create()
    const b = res.data.backup || {}
    const errs = b.errors || []
    showResult(
      errs.length === 0,
      `${$t('backup.created')}: ${b.backup_id || '?'}`,
      `${formatMb(b.archive_size_mb)} · DB: ${b.database_dump ? '✓' : '✗'} · .env: ${b.env_backed_up ? '✓' : '✗'} · ${b.server_count || 0} ${$t('backup.tagSrv')} · ${b.client_count || 0} ${$t('backup.tagClients')}`,
      errs,
    )
    await Promise.all([loadBackups(), loadStorageStatus()])
  } catch (e) {
    showResult(false, $t('backup.createFailed'), e.response?.data?.detail || e.message)
  } finally {
    creating.value = false
  }
}

async function verifyBackup(b) {
  operating.value = b.backup_id
  opType.value = 'verify'
  verifyResult.value = null
  try {
    const res = await backupApi.verify(b.backup_id)
    verifyResult.value = res.data
  } catch (e) {
    showResult(false, $t('backup.verifyFailed'), e.response?.data?.detail || e.message)
  } finally {
    operating.value = null
    opType.value = null
  }
}

function confirmRestore(b, type) {
  if (type === 'full') {
    confirmModal.value = {
      type: 'full',
      backup: b,
      title: $t('backup.fullRestore'),
      message: `${$t('backup.confirmRestoreFromBackup')} ${b.backup_id} (${formatTime(b.timestamp)})?`,
      btnClass: 'btn-warning',
      btnLabel: $t('backup.restoreBtn'),
    }
  } else {
    confirmModal.value = {
      type: 'database',
      backup: b,
      title: $t('backup.dbRestore'),
      message: `${$t('backup.confirmRestoreDbFrom')} ${b.backup_id}?`,
      btnClass: 'btn-primary',
      btnLabel: $t('backup.restoreDbBtn'),
    }
  }
}

function confirmDelete(b) {
  confirmModal.value = {
    type: 'delete',
    backup: b,
    title: $t('backup.deleteTitle'),
    message: `${$t('backup.confirmDelete')} ${b.backup_id} (${formatMb(b.archive_size_mb || b.backup_size_mb)})? ${$t('backup.cantUndo')}`,
    btnClass: 'btn-danger',
    btnLabel: $t('common.delete'),
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
        $t('backup.fullRestoreDone'),
        `DB: ${r.database_restored ? '✓' : '✗'} · .env: ${r.env_restored ? '✓' : '✗'} · WG: ${(r.wireguard_restored || []).length} · Services: ${r.services_restarted ? '✓' : '✗'}`,
        r.errors,
      )
    } else if (modal.type === 'database') {
      await backupApi.restoreDatabase(b.backup_id)
      showResult(true, $t('backup.dbRestoreDone'), `${$t('backup.restoredFrom')} ${b.backup_id}`)
    } else if (modal.type === 'delete') {
      await backupApi.deleteBackup(b.backup_id)
      showResult(true, $t('backup.deleted'), b.backup_id)
      await Promise.all([loadBackups(), loadStorageStatus()])
    }
  } catch (e) {
    showResult(false, `${modal.type} ${$t('backup.failed')}`, e.response?.data?.detail || e.message)
  } finally {
    operating.value = null
    opType.value = null
  }
}

// ── Settings actions ───────────────────────────────────────────────────────
async function saveSettings() {
  saving.value = true
  settingsAlert.value = ''
  try {
    const payload = { ...cfg }
    delete payload.backup_mount_password_set
    await backupApi.saveSettings(payload)
    settingsAlertType.value = 'alert-success'
    settingsAlert.value = $t('backup.settingsSaved')
    setTimeout(() => { settingsAlert.value = '' }, 3000)
    await loadStorageStatus()
  } catch (e) {
    settingsAlertType.value = 'alert-danger'
    settingsAlert.value = e.response?.data?.detail || String(e.message || e)
  } finally {
    saving.value = false
  }
}

async function testWrite() {
  testing.value = true
  settingsAlert.value = ''
  try {
    const res = await backupApi.testWrite()
    settingsAlertType.value = 'alert-success'
    settingsAlert.value = res.data.message
    await loadStorageStatus()
  } catch (e) {
    settingsAlertType.value = 'alert-danger'
    settingsAlert.value = e.response?.data?.detail || String(e.message || e)
  } finally {
    testing.value = false
  }
}

async function mountStorage() {
  mounting.value = true
  settingsAlert.value = ''
  try {
    // Save first so the mount call sees the latest creds
    const payload = { ...cfg }
    delete payload.backup_mount_password_set
    await backupApi.saveSettings(payload)
    const res = await backupApi.mount()
    settingsAlertType.value = 'alert-success'
    settingsAlert.value = res.data.message
    await loadStorageStatus()
  } catch (e) {
    settingsAlertType.value = 'alert-danger'
    settingsAlert.value = e.response?.data?.detail || String(e.message || e)
  } finally {
    mounting.value = false
  }
}

async function unmountStorage() {
  mounting.value = true
  settingsAlert.value = ''
  try {
    const res = await backupApi.unmount()
    settingsAlertType.value = 'alert-success'
    settingsAlert.value = res.data.message
    await loadStorageStatus()
  } catch (e) {
    settingsAlertType.value = 'alert-danger'
    settingsAlert.value = e.response?.data?.detail || String(e.message || e)
  } finally {
    mounting.value = false
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
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

function formatMb(size) {
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
</script>
