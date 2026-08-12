<!-- Backup & Restore — designer's 1:1 handoff (design2). Stat cards (archive
     count / local storage bar / mount status), Create + Refresh actions with
     Schedule/Storage tab pills, then a 2-col grid: backups table (verified tick,
     size, type badge, verify/restore-full/restore-db/delete) on the left and the
     Schedule or Storage panel on the right. Wired to backupApi verbatim
     (create/list/verify/restoreFull/restoreDatabase/delete + settings + storage).
     Existing handlers preserved; computed adapters map to his field names. -->
<template>
  <div class="d2-backup-root">
    <!-- stat cards -->
    <div class="d2-backup-stats" :style="{ gridTemplateColumns:g3 }">
      <div class="d2-backup-stat">
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.archive') || 'Archives' }}</div>
        <div style="font-size:24px;font-weight:680;margin-top:7px">{{ backupCount }}</div>
      </div>
      <div class="d2-backup-stat">
        <div style="font-size:12.5px;color:var(--text-2)">{{ storageTypeLabel }}</div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
          <div style="flex:1;height:6px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:storagePct }"></div></div>
          <span class="mono" style="font-size:11.5px;color:var(--text-3)">{{ storageUsed }} / {{ storageTotal }}</span>
        </div>
      </div>
      <div class="d2-backup-stat">
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.storageStatus') || 'Storage status' }}</div>
        <div style="display:flex;align-items:center;gap:7px;margin-top:10px">
          <span :style="{ width:'9px', height:'9px', borderRadius:'50%', background:storageMountColor }"></span>
          <span style="font-size:14px;font-weight:600">{{ storageMountLabel }}</span>
        </div>
      </div>
    </div>

    <!-- action row + tab pills -->
    <div class="d2-backup-toolbar">
      <button @click="createBackup" :disabled="creating" class="d2-btn-accent d2-backup-create-inline">
        <span v-if="creating" class="d2-backup-spinner" aria-hidden="true"></span>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg>
        {{ creating ? (tr('backup.creating') || 'Creating…') : (tr('backup.createNow') || 'Create now') }}
      </button>
      <button @click="refreshBackups" :disabled="loading" class="d2-btn-ghost d2-backup-refresh-inline">{{ tr('backup.refresh') || 'Refresh' }}</button>
      <div class="d2-backup-desktop-tabs">
        <button @click="bkTab = 'sched'" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'12px', fontWeight:(bkIsSched?600:500), cursor:'pointer', background:(bkIsSched?'var(--panel)':'transparent'), color:(bkIsSched?'var(--text)':'var(--text-3)') }">{{ tr('backup.tabSchedule') || 'Schedule' }}</button>
        <button @click="bkTab = 'storage'" :style="{ padding:'5px 12px', border:'none', borderRadius:'6px', font:'inherit', fontSize:'12px', fontWeight:(bkIsStorage?600:500), cursor:'pointer', background:(bkIsStorage?'var(--panel)':'transparent'), color:(bkIsStorage?'var(--text)':'var(--text-3)') }">{{ tr('backup.tabStorage') || 'Storage' }}</button>
      </div>
    </div>

    <div v-if="creating" class="d2-backup-progress" role="status" aria-live="polite">
      <span class="d2-backup-spinner" aria-hidden="true"></span>
      <div><b>{{ tr('backup.creating') || 'Creating backup…' }}</b><small>{{ tr('backup.creatingHint') || 'This usually takes less than a minute. You can keep this page open.' }}</small></div>
    </div>

    <div class="d2-backup-mobile-tabs" role="tablist">
      <button :class="{ active:mobileTab === 'archives' }" @click="selectMobileTab('archives')">{{ tr('backup.archive') || 'Archives' }}</button>
      <button :class="{ active:mobileTab === 'sched' }" @click="selectMobileTab('sched')">{{ tr('backup.tabSchedule') || 'Schedule' }}</button>
      <button :class="{ active:mobileTab === 'storage' }" @click="selectMobileTab('storage')">{{ tr('backup.tabStorage') || 'Storage' }}</button>
    </div>

    <!-- table + side panel -->
    <div class="d2-backup-main" :class="'mobile-' + mobileTab" :style="{ gridTemplateColumns:gDashMain }">
      <div class="d2-backup-archive-panel">
        <div class="d2-backup-mobile-list-head">
          <div><b>{{ tr('backup.archive') || 'Archives' }}</b><small>{{ backupCount }}</small></div>
          <button type="button" :disabled="loading" :title="tr('backup.refresh') || 'Refresh'" @click="refreshBackups">
            <svg :class="{ spin:loading }" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 10-2.34 5.66"></path><path d="M20 4v7h-7"></path></svg>
          </button>
        </div>
        <div class="d2-backup-mobile-list">
          <button v-for="b in backupRows" :key="'mobile-'+(b.id || b.filename)" type="button" class="d2-backup-mobile-row" @click="selectedBackup = b">
            <span class="d2-backup-mobile-date"><b>{{ b.date }}</b><small class="mono">{{ b.id }}</small></span>
            <span class="d2-backup-mobile-meta"><b class="mono">{{ b.size }}</b><small :style="{ color:b.typeColor, background:b.typeBg }">{{ b.typeLabel }}</small></span>
            <span class="d2-backup-mobile-status" :class="{ verified:b.verified }" :title="b.verified ? (tr('backup.verified') || 'Verified') : (tr('backup.verify') || 'Verify')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path v-if="b.verified" d="M8 12l2.5 2.5L16 9"></path><path v-else d="M12 8v4M12 16h.01"></path></svg>
            </span>
            <svg class="d2-backup-mobile-more" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
          </button>
          <div v-if="!backupRows.length" class="d2-backup-mobile-empty">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('backup.noBackups') || 'No backups yet') }}</div>
        </div>
        <div class="d2-backup-desktop-table" style="overflow-x:auto">
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

      <div class="d2-backup-settings-panel">
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

    <D2MobileSheet :open="!!selectedBackup" :title="selectedBackup?.date || ''" :close-label="tr('common.close') || 'Close'" @close="selectedBackup = null">
      <template v-if="selectedBackup">
        <div class="d2-backup-sheet-meta">
          <div><span>{{ tr('backup.size') || 'Size' }}</span><b class="mono">{{ selectedBackup.size }}</b></div>
          <div><span>{{ tr('backup.type') || 'Type' }}</span><b>{{ selectedBackup.typeLabel }}</b></div>
          <div><span>ID</span><b class="mono">{{ selectedBackup.id }}</b></div>
        </div>
        <div class="d2-backup-sheet-actions">
          <button type="button" @click="runSelected('verify')">{{ tr('backup.verify') || 'Verify integrity' }}</button>
          <button type="button" @click="runSelected('full')">{{ tr('backup.restoreFull') || 'Full restore' }}</button>
          <button type="button" @click="runSelected('db')">{{ tr('backup.restoreDb') || 'Restore database' }}</button>
          <button type="button" class="danger" @click="runSelected('delete')">{{ tr('common.delete') || 'Delete' }}</button>
        </div>
      </template>
    </D2MobileSheet>

    <div v-if="msg" class="d2-backup-message" :class="{ error:msgIsError }">{{ msg }}</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { backupApi } from '../../api'
import { formatBytes, formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'
import D2MobileSheet from '../ui/D2MobileSheet.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const backups = ref([])
const loading = ref(false)
const creating = ref(false)
const msg = ref('')
const selectedBackup = ref(null)
const mobileTab = ref('archives')

async function load() { loading.value = true; try { const r = await backupApi.list(); const d = r.data; backups.value = d.backups || d.items || (Array.isArray(d) ? d : []) } catch (e) { console.error(e) } finally { loading.value = false } }
async function create() {
  if (creating.value) return
  creating.value = true
  syncHeaderAction()
  try {
    const { data } = await backupApi.create()
    if (data?.success === false) throw new Error(data?.message || 'Backup creation failed')
    await Promise.all([load(), loadStorage()])
    flash(tr('backup.createdOk') || 'Backup created')
  } catch (e) {
    flash(errorDetail(e), true)
  } finally {
    creating.value = false
    syncHeaderAction()
  }
}
function fileId(b) { return b.backup_id }
function isDbOnly(b) { return !!(b.database_dump && b.env_backed_up === false) || b.type === 'db' }
function fmtBackupSize(b) { if (b.archive_size_bytes != null) return formatBytes(b.archive_size_bytes); if (b.archive_size_mb != null) return b.archive_size_mb + ' MB'; if (b.backup_size_mb != null) return b.backup_size_mb + ' MB'; return '—' }
async function verify(b) { try { const r = await backupApi.verify(fileId(b)); alert(r.data?.valid === false ? (tr('backup.corrupt') || 'Backup is CORRUPT') : (tr('backup.valid') || 'Backup verified OK')) } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreFull(b) { if (!await d2confirm(tr('backup.restoreFullConfirm') || 'Full restore from this backup? This overwrites current data.')) return; try { await backupApi.restoreFull(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreDb(b) { if (!await d2confirm(tr('backup.restoreDbConfirm') || 'Restore database only from this backup?')) return; try { await backupApi.restoreDatabase(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function remove(b) { if (!await d2confirm(tr('backup.deleteConfirm') || 'Delete this backup?')) return; try { await backupApi.delete(fileId(b)); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function runSelected(action) {
  const row = selectedBackup.value
  if (!row) return
  selectedBackup.value = null
  if (action === 'verify') return verify(row.raw)
  if (action === 'full') return restoreFull(row.raw)
  if (action === 'db') return restoreDb(row.raw)
  if (action === 'delete') return remove(row.raw)
}
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
function selectMobileTab(tab) {
  mobileTab.value = tab
  if (tab === 'sched' || tab === 'storage') bkTab.value = tab
}
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

function syncHeaderAction() {
  ui.set({
    title: tr('nav.backup') || 'Backup',
    keepSearch: true,
    primary: {
      label: creating.value ? (tr('backup.creating') || 'Creating…') : (tr('backup.create') || 'Create backup'),
      onClick: createBackup,
      disabled: creating.value,
      loading: creating.value,
    },
  })
}

onMounted(() => {
  syncHeaderAction()
  load(); loadSettings(); loadStorage()
})
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-backup-root { width:100%;min-width:0; }
.d2-backup-stats { display:grid;gap:14px;margin-bottom:14px; }
.d2-backup-stat { min-width:0;background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px; }
.d2-backup-toolbar { display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap; }
.d2-backup-toolbar > button { display:flex;align-items:center;justify-content:center;gap:7px;height:36px;padding:0 14px;border-radius:9px;font:inherit;font-size:13px;font-weight:600;cursor:pointer; }
.d2-backup-toolbar .d2-btn-accent { border:0;background:var(--accent);color:#fff; }
.d2-backup-toolbar .d2-btn-ghost { border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);font-weight:550; }
.d2-backup-toolbar button:disabled { cursor:default;opacity:.62; }
.d2-backup-desktop-tabs { margin-left:auto;display:flex;gap:2px;padding:3px;background:var(--panel-2);border:1px solid var(--border);border-radius:9px; }
.d2-backup-progress { display:flex;align-items:center;gap:11px;margin:0 0 14px;padding:11px 13px;border:1px solid var(--accent);border-radius:11px;background:var(--accent-soft);color:var(--text); }
.d2-backup-progress > div { min-width:0;display:flex;flex-direction:column;gap:2px; }
.d2-backup-progress b { font-size:12.5px;font-weight:650; }
.d2-backup-progress small { color:var(--text-3);font-size:11px;line-height:1.35; }
.d2-backup-spinner,.d2-primary-spinner { width:15px;height:15px;flex:none;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:d2-backup-spin .7s linear infinite; }
@keyframes d2-backup-spin { to { transform:rotate(360deg); } }
.d2-backup-mobile-tabs,.d2-backup-mobile-list,.d2-backup-mobile-list-head { display:none; }
.d2-backup-main { display:grid;gap:14px;align-items:start; }
.d2-backup-archive-panel { min-width:0;background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden; }
.d2-backup-settings-panel { min-width:0;background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px; }
.d2-backup-message { margin-top:12px;padding:10px 12px;border-radius:9px;background:var(--green-soft);color:var(--green);font-size:13px;font-weight:550; }
.d2-backup-message.error { background:var(--red-soft);color:var(--red); }
.d2-backup-sheet-meta { display:grid;gap:8px;margin-bottom:12px; }
.d2-backup-sheet-meta > div { min-width:0;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:9px 10px;border-radius:9px;background:var(--panel-2); }
.d2-backup-sheet-meta span { color:var(--text-3);font-size:11px; }
.d2-backup-sheet-meta b { min-width:0;max-width:70%;overflow-wrap:anywhere;text-align:right;font-size:12px; }
.d2-backup-sheet-actions { display:grid;gap:7px; }
.d2-backup-sheet-actions button { min-height:42px;padding:0 12px;border:1px solid var(--border);border-radius:10px;background:var(--panel);color:var(--text);font:inherit;font-size:13px;font-weight:600;text-align:left;cursor:pointer; }
.d2-backup-sheet-actions button:active { background:var(--panel-2); }
.d2-backup-sheet-actions button.danger { color:var(--red);border-color:var(--red-soft); }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-row:hover { background: var(--panel-2); }
.d2-ico { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-ico:hover { background: var(--panel-3); color: var(--text); }
.d2-ico.del:hover { background: var(--red-soft); color: var(--red); }
.d2-btn-accent:hover { background: var(--accent-2); }
.d2-btn-ghost:hover { background: var(--panel-2); }
.d2-in { width: 100%; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 12px; font: inherit; outline: none; }
.d2-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
@media (max-width:900px) {
  .d2-backup-stats { grid-template-columns:repeat(3,minmax(0,1fr)) !important;gap:0;margin-bottom:10px;border:1px solid var(--border);border-radius:12px;background:var(--panel);box-shadow:var(--shadow);overflow:hidden; }
  .d2-backup-stat { min-height:70px;padding:10px 9px;border:0;border-right:1px solid var(--border);border-radius:0;background:transparent;box-shadow:none; }
  .d2-backup-stat:last-child { border-right:0; }
  .d2-backup-stat > div:first-child { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9.5px !important; }
  .d2-backup-stat > div:nth-child(2) { margin-top:6px !important; }
  .d2-backup-stat:first-child > div:nth-child(2) { font-size:19px !important; }
  .d2-backup-stat:nth-child(2) .mono { display:none; }
  .d2-backup-stat:nth-child(3) span:last-child { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px !important; }
  .d2-backup-toolbar { display:none; }
  .d2-backup-progress { margin-bottom:10px; }
  .d2-backup-mobile-tabs { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:3px;margin-bottom:10px;padding:3px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2); }
  .d2-backup-mobile-tabs button { height:34px;min-width:0;padding:0 6px;border:0;border-radius:7px;background:transparent;color:var(--text-3);font:inherit;font-size:11.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer; }
  .d2-backup-mobile-tabs button.active { background:var(--panel);color:var(--text);box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .d2-backup-main { display:block !important; }
  .d2-backup-main.mobile-archives .d2-backup-settings-panel { display:none; }
  .d2-backup-main:not(.mobile-archives) .d2-backup-archive-panel { display:none; }
  .d2-backup-archive-panel { border-radius:12px; }
  .d2-backup-desktop-table { display:none; }
  .d2-backup-mobile-list-head { height:44px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 10px 0 13px;border-bottom:1px solid var(--border); }
  .d2-backup-mobile-list-head > div { min-width:0;display:flex;align-items:center;gap:7px; }
  .d2-backup-mobile-list-head b { font-size:12.5px;font-weight:650; }
  .d2-backup-mobile-list-head small { display:grid;place-items:center;min-width:20px;height:20px;padding:0 6px;border-radius:99px;background:var(--panel-2);color:var(--text-3);font-size:10px;font-weight:650; }
  .d2-backup-mobile-list-head button { width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:8px;background:transparent;color:var(--text-3);cursor:pointer; }
  .d2-backup-mobile-list-head button:active { background:var(--panel-2); }
  .d2-backup-mobile-list-head .spin { animation:d2-backup-spin .7s linear infinite; }
  .d2-backup-mobile-list { display:block; }
  .d2-backup-mobile-row { width:100%;min-height:68px;display:grid;grid-template-columns:minmax(0,1fr) auto 22px;align-items:center;gap:10px;padding:10px 12px;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--text);font:inherit;text-align:left;cursor:pointer; }
  .d2-backup-mobile-row:last-child { border-bottom:0; }
  .d2-backup-mobile-row:active { background:var(--panel-2); }
  .d2-backup-mobile-date,.d2-backup-mobile-meta { min-width:0;display:flex;flex-direction:column;gap:4px; }
  .d2-backup-mobile-date b { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:650; }
  .d2-backup-mobile-date small { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-3);font-size:9.5px; }
  .d2-backup-mobile-meta { align-items:flex-end; }
  .d2-backup-mobile-meta b { font-size:11.5px;font-weight:550;color:var(--text-2); }
  .d2-backup-mobile-meta small { padding:2px 6px;border-radius:5px;font-size:9.5px;font-weight:650; }
  .d2-backup-mobile-status { display:none; }
  .d2-backup-mobile-more { color:var(--text-3); }
  .d2-backup-mobile-empty { padding:30px 16px;text-align:center;color:var(--text-3);font-size:12px; }
  .d2-backup-settings-panel { padding:14px;border-radius:12px; }
  .d2-backup-settings-panel input,.d2-backup-settings-panel select { min-width:0; }
}
@media (min-width:540px) and (max-width:900px) {
  .d2-backup-mobile-row { grid-template-columns:minmax(0,1fr) auto 28px 22px; }
  .d2-backup-mobile-status { display:flex;color:var(--text-3); }
  .d2-backup-mobile-status.verified { color:var(--green); }
}
</style>
