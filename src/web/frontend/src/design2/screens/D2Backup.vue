<!-- Backup & Restore — designer's 1:1 handoff (design2). Stat cards (archive
     count / local storage bar / mount status), Create + Refresh actions with
     Schedule/Storage tab pills, then a 2-col grid: backups table (verified tick,
     size, type badge, verify/restore-full/restore-db/delete) on the left and the
     Schedule or Storage panel on the right. Wired to backupApi verbatim
     (create/list/verify/restoreFull/restoreDatabase/delete + settings + storage).
     Existing handlers preserved; computed adapters map to his field names. -->
<template>
  <div class="d2-root">
    <!-- stat cards -->
    <div :style="{ display:'grid', gridTemplateColumns:g3, gap:'14px', marginBottom:'14px' }">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.archive') || 'Archives' }}</div>
        <div style="font-size:24px;font-weight:680;margin-top:7px">{{ backupCount }}</div>
      </div>
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ storageTypeLabel }}</div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
          <div style="flex:1;height:6px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:storagePct }"></div></div>
          <span class="mono" style="font-size:11.5px;color:var(--text-3)">{{ storageUsed }} / {{ storageTotal }}</span>
        </div>
      </div>
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.storageStatus') || 'Storage status' }}</div>
        <div style="display:flex;align-items:center;gap:7px;margin-top:10px">
          <span :style="{ width:'9px', height:'9px', borderRadius:'50%', background:storageMountColor }"></span>
          <span style="font-size:14px;font-weight:600">{{ storageMountLabel }}</span>
        </div>
      </div>
    </div>

    <!-- action row + tab pills -->
    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <button @click="createBackup" style="display:flex;align-items:center;gap:7px;height:36px;padding:0 14px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:13px;font-weight:600;cursor:pointer" class="d2-btn-accent"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg>{{ tr('backup.createNow') || 'Create now' }}</button>
      <button @click="refreshBackups" style="height:36px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:13px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.refresh') || 'Refresh' }}</button>
      <div style="margin-left:auto;display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px">
        <button @click="bkTab = 'sched'" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'12px', fontWeight:(bkIsSched?600:500), cursor:'pointer', background:(bkIsSched?'var(--panel)':'transparent'), color:(bkIsSched?'var(--text)':'var(--text-3)') }">{{ tr('backup.tabSchedule') || 'Schedule' }}</button>
        <button @click="bkTab = 'storage'" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'12px', fontWeight:(bkIsStorage?600:500), cursor:'pointer', background:(bkIsStorage?'var(--panel)':'transparent'), color:(bkIsStorage?'var(--text)':'var(--text-3)') }">{{ tr('backup.tabStorage') || 'Storage' }}</button>
      </div>
    </div>

    <!-- table + side panel -->
    <div :style="{ display:'grid', gridTemplateColumns:gDashMain, gap:'14px', alignItems:'start' }">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left">
            <th class="d2-th" style="padding:11px 20px">{{ tr('backup.date') || 'Date' }}</th>
            <th class="d2-th">{{ tr('backup.size') || 'Size' }}</th>
            <th class="d2-th">{{ tr('backup.type') || 'Type' }}</th>
            <th class="d2-th" style="text-align:right;padding:11px 20px">{{ tr('common.actions') || 'Actions' }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="b in backupRows" :key="b.id || b.filename" style="border-top:1px solid var(--border)" class="d2-row">
              <td style="padding:12px 20px">
                <div style="display:flex;align-items:center;gap:8px">
                  <span class="mono" style="font-size:12.5px">{{ b.date }}</span>
                  <span v-if="b.verified" :title="tr('backup.verified') || 'verified'" style="color:var(--green);display:flex"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4 4L19 7"></path></svg></span>
                </div>
                <div class="mono" style="font-size:10.5px;color:var(--text-3)">{{ b.id }}</div>
              </td>
              <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ b.size }}</td>
              <td style="padding:12px 12px"><span :style="{ fontSize:'11px', fontWeight:600, padding:'2px 8px', borderRadius:'6px', color:b.typeColor, background:b.typeBg }">{{ b.typeLabel }}</span></td>
              <td style="padding:12px 20px"><div style="display:flex;gap:4px;justify-content:flex-end;flex-wrap:wrap">
                <button @click="verify(b.raw)" :title="tr('backup.verify') || 'Verify'" class="d2-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 12l2 2 4-4"></path><circle cx="12" cy="12" r="9"></circle></svg></button>
                <button @click="restoreFull(b.raw)" :title="tr('backup.restoreFull') || 'Restore full'" style="height:30px;padding:0 10px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.restoreFull') || 'Restore full' }}</button>
                <button @click="restoreDb(b.raw)" :title="tr('backup.restoreDb') || 'DB'" style="height:30px;padding:0 10px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.restoreDb') || 'DB' }}</button>
                <button @click="remove(b.raw)" :title="tr('common.delete') || 'Delete'" class="d2-ico del"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
              </div></td>
            </tr>
            <tr v-if="!backupRows.length"><td colspan="4" style="text-align:center;color:var(--text-3);padding:34px">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('backup.noBackups') || 'No backups yet') }}</td></tr>
          </tbody>
        </table>
      </div></div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px">
        <!-- Schedule tab -->
        <template v-if="bkIsSched">
          <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('backup.tabSchedule') || 'Schedule' }}</div>
          <div style="display:flex;flex-direction:column;gap:13px">
            <div>
              <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('backup.frequency') || 'Frequency' }}</label>
              <select v-model="backupSettings.backup_interval_hours" :disabled="backupSettings.backup_enabled !== 'true'" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 11px;font:inherit;font-size:13px;outline:none;cursor:pointer">
                <option value="6">{{ tr('backup.every6h') || 'Every 6 hours' }}</option>
                <option value="12">{{ tr('backup.every12h') || 'Every 12 hours' }}</option>
                <option value="24">{{ tr('backup.every24h') || 'Daily' }}</option>
                <option value="48">{{ tr('backup.every48h') || 'Every 2 days' }}</option>
                <option value="168">{{ tr('backup.weekly') || 'Weekly' }}</option>
              </select>
            </div>
            <div style="display:flex;gap:11px">
              <div style="flex:1">
                <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('backup.timeUtc') || 'Time (UTC)' }}</label>
                <select v-model="backupSettings.backup_hour_utc" :disabled="backupSettings.backup_enabled !== 'true'" class="mono d2-in" style="height:40px;font-size:13px">
                  <option v-for="hour in 24" :key="hour - 1" :value="String(hour - 1)">{{ String(hour - 1).padStart(2, '0') }}:00</option>
                </select>
              </div>
              <div style="flex:1">
                <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('backup.keep') || 'Keep copies' }}</label>
                <input v-model="backupSettings.backup_retention_count" type="number" min="1" max="100" inputmode="numeric" class="mono d2-in" style="height:40px;font-size:13px" />
              </div>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 11px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)">
              <div>
                <div style="font-size:12.5px;font-weight:600">{{ tr('backup.autoBackup') || 'Automatic backups' }}</div>
                <div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ backupSettings.backup_enabled === 'true' ? (tr('backup.scheduleOn') || 'Active') : (tr('backup.scheduleOff') || 'Disabled') }}</div>
              </div>
              <input type="checkbox" :checked="backupSettings.backup_enabled === 'true'" @change="backupSettings.backup_enabled = $event.target.checked ? 'true' : 'false'" style="width:18px;height:18px;accent-color:var(--accent);cursor:pointer" />
            </div>
            <button @click="saveBackupSettings" :disabled="savingSettings" style="height:38px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2-btn-accent">{{ tr('backup.save') || 'Save' }}</button>
          </div>
        </template>

        <!-- Storage tab -->
        <template v-if="bkIsStorage">
          <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('backup.tabStorage') || 'Storage' }}</div>
          <div style="display:flex;gap:8px;margin-bottom:13px">
            <button @click="backupSettings.backup_storage_type = 'local'" :style="{ flex:'1', height:'36px', border:'1px solid '+(bkIsLocal?'var(--accent)':'var(--border-strong)'), background:(bkIsLocal?'var(--accent-soft)':'var(--panel)'), color:(bkIsLocal?'var(--accent)':'var(--text-2)'), borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }">{{ tr('backup.storageLocal') || 'Local' }}</button>
            <button @click="backupSettings.backup_storage_type = 'network'" :style="{ flex:'1', height:'36px', border:'1px solid '+(bkIsNet?'var(--accent)':'var(--border-strong)'), background:(bkIsNet?'var(--accent-soft)':'var(--panel)'), color:(bkIsNet?'var(--accent)':'var(--text-2)'), borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }">{{ tr('backup.storageNet') || 'Network' }}</button>
          </div>
          <template v-if="bkIsNet">
            <div style="display:flex;flex-direction:column;gap:11px;margin-bottom:13px">
              <select v-model="backupSettings.backup_mount_type" class="d2-in" style="height:40px;font-size:12.5px">
                <option value="smb">SMB / CIFS</option>
                <option value="nfs">NFS</option>
              </select>
              <input v-model="backupSettings.backup_mount_address" :placeholder="backupSettings.backup_mount_type === 'nfs' ? '192.0.2.10:/backups' : '//192.0.2.10/backups'" class="mono d2-in" style="height:40px;font-size:12.5px" />
              <div style="display:flex;gap:11px">
                <input v-model="backupSettings.backup_mount_username" :disabled="backupSettings.backup_mount_type === 'nfs'" :placeholder="tr('backup.username') || 'Username'" autocomplete="off" class="d2-in" style="flex:1;height:40px;font-size:12.5px" />
                <input type="password" v-model="backupSettings.backup_mount_password" :disabled="backupSettings.backup_mount_type === 'nfs'" :placeholder="backupSettings.backup_mount_password_set ? (tr('backup.unchanged') || 'unchanged') : (tr('backup.password') || 'Password')" autocomplete="new-password" class="d2-in" style="flex:1;height:40px;font-size:12.5px" />
              </div>
              <input v-model="backupSettings.backup_mount_point" :placeholder="tr('backup.mountPoint') || 'Mount point'" class="mono d2-in" style="height:40px;font-size:12.5px" />
              <input v-model="backupSettings.backup_mount_options" :placeholder="tr('backup.extraOptions') || 'Extra options'" class="mono d2-in" style="height:40px;font-size:12.5px" />
            </div>
            <div style="display:flex;gap:7px;flex-wrap:wrap">
              <button @click="saveBackupSettings" :disabled="storageBusy" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.save') || 'Save' }}</button>
              <button @click="mountStorage" :disabled="storageBusy" style="height:36px;padding:0 13px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12px;font-weight:600;cursor:pointer" class="d2-btn-accent">{{ tr('backup.mount') || 'Mount' }}</button>
              <button @click="unmountStorage" :disabled="storageBusy" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.unmount') || 'Unmount' }}</button>
              <button @click="testWriteStorage" :disabled="storageBusy" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.testWrite') || 'Test write' }}</button>
            </div>
          </template>
          <template v-if="bkIsLocal">
            <div style="display:flex;flex-direction:column;gap:11px">
              <input v-model="backupSettings.backup_path" :placeholder="tr('backup.path') || 'Backup directory'" class="mono d2-in" style="height:40px;font-size:12.5px" />
              <div style="display:flex;gap:7px;flex-wrap:wrap">
                <button @click="saveBackupSettings" :disabled="storageBusy" style="height:36px;padding:0 13px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12px;font-weight:600;cursor:pointer" class="d2-btn-accent">{{ tr('backup.save') || 'Save' }}</button>
                <button @click="testWriteStorage" :disabled="storageBusy" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.testWrite') || 'Test write' }}</button>
              </div>
              <div style="font-size:12.5px;color:var(--text-3);line-height:1.5">{{ storageUsed }} / {{ storageTotal }} · {{ storageMountLabel }}</div>
            </div>
          </template>
        </template>
      </div>
    </div>

    <div v-if="msg" :style="{ color:msgIsError ? 'var(--red)' : 'var(--green)', fontSize:'13px', marginTop:'12px' }">{{ msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { backupApi } from '../../api'
import { formatBytes, formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const backups = ref([])
const loading = ref(false)
const creating = ref(false)
const msg = ref('')

async function load() { loading.value = true; try { const r = await backupApi.list(); const d = r.data; backups.value = d.backups || d.items || (Array.isArray(d) ? d : []) } catch (e) { console.error(e) } finally { loading.value = false } }
async function create() { creating.value = true; try { await backupApi.create(); await Promise.all([load(), loadStorage()]); flash(tr('backup.createdOk') || 'Backup created') } catch (e) { flash(errorDetail(e), true) } finally { creating.value = false } }
function fileId(b) { return b.backup_id }
function isDbOnly(b) { return !!(b.database_dump && b.env_backed_up === false) || b.type === 'db' }
function fmtBackupSize(b) { if (b.archive_size_bytes != null) return formatBytes(b.archive_size_bytes); if (b.archive_size_mb != null) return b.archive_size_mb + ' MB'; if (b.backup_size_mb != null) return b.backup_size_mb + ' MB'; return '—' }
async function verify(b) { try { const r = await backupApi.verify(fileId(b)); alert(r.data?.valid === false ? (tr('backup.corrupt') || 'Backup is CORRUPT') : (tr('backup.valid') || 'Backup verified OK')) } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreFull(b) { if (!await d2confirm(tr('backup.restoreFullConfirm') || 'Full restore from this backup? This overwrites current data.')) return; try { await backupApi.restoreFull(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreDb(b) { if (!await d2confirm(tr('backup.restoreDbConfirm') || 'Restore database only from this backup?')) return; try { await backupApi.restoreDatabase(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function remove(b) { if (!await d2confirm(tr('backup.deleteConfirm') || 'Delete this backup?')) return; try { await backupApi.delete(fileId(b)); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
const msgIsError = ref(false)
function flash(m, isError = false) { msg.value = m; msgIsError.value = isError; setTimeout(() => { msg.value = ''; msgIsError.value = false }, 4000) }
function errorDetail(e) { return e?.response?.data?.detail || e?.message || 'Error' }
function fmtBytes(b) { return formatBytes(b || 0) }
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }

// --- his-name aliases so the markup reads 1:1 with the handoff ---
const createBackup = create
const refreshBackups = load

// --- schedule / storage state (backupApi.getSettings/saveSettings + storage) ---
const bkTab = ref('sched')
const bkIsSched = computed(() => bkTab.value === 'sched')
const bkIsStorage = computed(() => bkTab.value === 'storage')
const backupSettings = reactive({
  backup_enabled: 'true',
  backup_interval_hours: '24',
  backup_hour_utc: '3',
  backup_retention_count: '7',
  backup_auto_cleanup: 'true',
  backup_storage_type: 'local',
  backup_path: '/opt/vpnmanager/backups',
  backup_mount_type: 'smb',
  backup_mount_address: '',
  backup_mount_username: '',
  backup_mount_password: '',
  backup_mount_password_set: false,
  backup_mount_point: '/mnt/vpnmanager-backup',
  backup_mount_options: '',
})
const SETTINGS_KEYS = [
  'backup_enabled', 'backup_interval_hours', 'backup_hour_utc',
  'backup_retention_count', 'backup_auto_cleanup', 'backup_storage_type',
  'backup_path', 'backup_mount_type', 'backup_mount_address',
  'backup_mount_username', 'backup_mount_password', 'backup_mount_point',
  'backup_mount_options',
]
const bkIsLocal = computed(() => backupSettings.backup_storage_type === 'local')
const bkIsNet = computed(() => backupSettings.backup_storage_type === 'network')
const savingSettings = ref(false)
const mountingStorage = ref(false)
const testingStorage = ref(false)
const storageBusy = computed(() => savingSettings.value || mountingStorage.value || testingStorage.value)
const storageLoaded = ref(false)
const storage = ref({ storage_type: 'local', mounted: null, ready: null, writable: null, target: '', usage: null })

async function loadSettings() {
  try {
    const { data } = await backupApi.getSettings()
    if (data && typeof data === 'object') {
      for (const key of SETTINGS_KEYS) {
        if (data[key] != null) backupSettings[key] = data[key]
      }
      backupSettings.backup_mount_password_set = data.backup_mount_password_set === true
    }
  } catch (e) { flash(errorDetail(e), true) }
}
async function loadStorage() {
  try {
    const { data } = await backupApi.storageStatus()
    if (data && typeof data === 'object') storage.value = { ...storage.value, ...data }
    storageLoaded.value = true
  } catch (e) {
    storageLoaded.value = false
    flash(errorDetail(e), true)
  }
}
function settingsPayload() {
  const payload = {}
  for (const key of SETTINGS_KEYS) payload[key] = backupSettings[key]
  payload.backup_retention_count = Number(backupSettings.backup_retention_count)
  payload.backup_hour_utc = Number(backupSettings.backup_hour_utc)
  payload.backup_interval_hours = Number(backupSettings.backup_interval_hours)
  if (!payload.backup_mount_password) delete payload.backup_mount_password
  return payload
}
async function persistBackupSettings(announce = true) {
  savingSettings.value = true
  try {
    const { data } = await backupApi.saveSettings(settingsPayload())
    if (data?.updated === 0) throw new Error('No backup settings were updated')
    await Promise.all([loadSettings(), loadStorage()])
    if (announce) flash(tr('backup.settingsSaved') || 'Settings saved')
    return true
  } catch (e) {
    flash(errorDetail(e), true)
    return false
  } finally {
    savingSettings.value = false
  }
}
async function saveBackupSettings() { await persistBackupSettings(true) }
async function mountStorage() {
  mountingStorage.value = true
  try {
    if (!await persistBackupSettings(false)) return
    const { data } = await backupApi.mount()
    await loadStorage()
    flash(data?.message || tr('backup.mounted') || 'Mounted')
  } catch (e) { flash(errorDetail(e), true) } finally { mountingStorage.value = false }
}
async function unmountStorage() {
  mountingStorage.value = true
  try {
    const { data } = await backupApi.unmount()
    await loadStorage()
    flash(data?.message || tr('backup.unmounted') || 'Unmounted')
  } catch (e) { flash(errorDetail(e), true) } finally { mountingStorage.value = false }
}
async function testWriteStorage() {
  testingStorage.value = true
  try {
    if (!await persistBackupSettings(false)) return
    const { data } = await backupApi.testWrite()
    await loadStorage()
    flash(data?.message || tr('backup.testWriteOk') || 'Write test OK')
  } catch (e) { flash(errorDetail(e), true) } finally { testingStorage.value = false }
}

// --- computed adapters to his field names ---
const g3 = 'repeat(3,1fr)'
const gDashMain = '1.6fr 1fr'
const backupCount = computed(() => backups.value.length)
const backupRows = computed(() => backups.value.map(b => {
  const dbOnly = isDbOnly(b)
  return {
    raw: b,
    id: b.backup_id || b.filename || '',
    filename: b.filename || b.backup_id || '',
    date: b.timestamp ? fmtDate(b.timestamp) : '—',
    size: fmtBackupSize(b),
    verified: b.verified === true || b.verified_at != null,
    typeLabel: dbOnly ? (tr('backup.typeDb') || 'DB') : (tr('backup.typeFull') || 'Full'),
    typeColor: dbOnly ? 'var(--blue)' : 'var(--accent)',
    typeBg: dbOnly ? 'var(--blue-soft)' : 'var(--accent-soft)',
  }
}))
const storagePct = computed(() => {
  const u = storage.value.usage?.used_bytes, tot = storage.value.usage?.total_bytes
  if (storage.value.usage?.percent_used != null) return Math.min(100, Number(storage.value.usage.percent_used) || 0) + '%'
  if (u == null || !tot) return '0%'
  return Math.min(100, Math.round((u / tot) * 100)) + '%'
})
const storageUsed = computed(() => storage.value.usage?.used_bytes != null ? fmtBytes(storage.value.usage.used_bytes) : '—')
const storageTotal = computed(() => storage.value.usage?.total_bytes != null ? fmtBytes(storage.value.usage.total_bytes) : '—')
const storageTypeLabel = computed(() => (storage.value.storage_type || backupSettings.backup_storage_type) === 'network' ? (tr('backup.storageNetwork') || tr('backup.storageNet') || 'Network storage') : (tr('backup.storageLocal') || 'Local disk'))
const storageMountColor = computed(() => !storageLoaded.value ? 'var(--text-3)' : (storage.value.ready ? 'var(--green)' : 'var(--red)'))
const storageMountLabel = computed(() => {
  if (!storageLoaded.value) return '—'
  if (storage.value.storage_type === 'network') return storage.value.mounted ? (tr('backup.mountedYes') || 'Mounted') : (tr('backup.mountedNo') || 'Not mounted')
  return storage.value.ready ? (tr('backup.storageReady') || 'Ready') : (tr('backup.storageUnavailable') || 'Unavailable')
})

onMounted(() => {
  ui.set({ title: tr('nav.backup') || 'Backup', primary: { label: tr('backup.create') || 'Create backup', onClick: createBackup } })
  load(); loadSettings(); loadStorage()
})
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-row:hover { background: var(--panel-2); }
.d2-ico { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-ico:hover { background: var(--panel-3); color: var(--text); }
.d2-ico.del:hover { background: var(--red-soft); color: var(--red); }
.d2-btn-accent:hover { background: var(--accent-2); }
.d2-btn-ghost:hover { background: var(--panel-2); }
.d2-in { width: 100%; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 12px; font: inherit; outline: none; }
.d2-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
</style>
