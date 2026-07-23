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
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.storageLocal') || 'Local' }}</div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
          <div style="flex:1;height:6px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:storagePct }"></div></div>
          <span class="mono" style="font-size:11.5px;color:var(--text-3)">{{ storageUsed }}</span>
        </div>
      </div>
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:13px;box-shadow:var(--shadow);padding:16px 18px">
        <div style="font-size:12.5px;color:var(--text-2)">{{ tr('backup.mounted') || 'Mounted' }}</div>
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
              <select v-model="backupSettings.schedule" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 11px;font:inherit;font-size:13px;outline:none;cursor:pointer">
                <option value="daily">{{ tr('backup.daily') || 'Daily' }}</option>
                <option value="weekly">{{ tr('backup.weekly') || 'Weekly' }}</option>
                <option value="off">{{ tr('backup.off') || 'Off' }}</option>
              </select>
            </div>
            <div style="display:flex;gap:11px">
              <div style="flex:1">
                <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('backup.time') || 'Time' }}</label>
                <input v-model="backupSettings.time" class="mono d2-in" style="height:40px;font-size:13px" />
              </div>
              <div style="flex:1">
                <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('backup.keep') || 'Keep copies' }}</label>
                <input v-model="backupSettings.keep" inputmode="numeric" class="mono d2-in" style="height:40px;font-size:13px" />
              </div>
            </div>
            <button @click="saveBackupSettings" :disabled="savingSettings" style="height:38px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2-btn-accent">{{ tr('backup.save') || 'Save' }}</button>
          </div>
        </template>

        <!-- Storage tab -->
        <template v-if="bkIsStorage">
          <div style="font-weight:600;font-size:14px;margin-bottom:14px">{{ tr('backup.tabStorage') || 'Storage' }}</div>
          <div style="display:flex;gap:8px;margin-bottom:13px">
            <button @click="backupSettings.storage = 'local'" :style="{ flex:'1', height:'36px', border:'1px solid '+(bkIsLocal?'var(--accent)':'var(--border-strong)'), background:(bkIsLocal?'var(--accent-soft)':'var(--panel)'), color:(bkIsLocal?'var(--accent)':'var(--text-2)'), borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }">{{ tr('backup.storageLocal') || 'Local' }}</button>
            <button @click="backupSettings.storage = 'net'" :style="{ flex:'1', height:'36px', border:'1px solid '+(bkIsNet?'var(--accent)':'var(--border-strong)'), background:(bkIsNet?'var(--accent-soft)':'var(--panel)'), color:(bkIsNet?'var(--accent)':'var(--text-2)'), borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }">{{ tr('backup.storageNet') || 'Network' }}</button>
          </div>
          <template v-if="bkIsNet">
            <div style="display:flex;flex-direction:column;gap:11px;margin-bottom:13px">
              <input v-model="backupSettings.net_host" :placeholder="tr('backup.netHost') || 'Host'" class="mono d2-in" style="height:40px;font-size:12.5px" />
              <input v-model="backupSettings.net_share" :placeholder="tr('backup.netShare') || 'Share'" class="mono d2-in" style="height:40px;font-size:12.5px" />
              <div style="display:flex;gap:11px">
                <input v-model="backupSettings.net_user" :placeholder="tr('backup.netUser') || 'Login'" class="d2-in" style="flex:1;height:40px;font-size:12.5px" />
                <input type="password" v-model="backupSettings.net_pass" :placeholder="tr('backup.netPass') || 'Password'" class="d2-in" style="flex:1;height:40px;font-size:12.5px" />
              </div>
            </div>
            <div style="display:flex;gap:7px;flex-wrap:wrap">
              <button @click="mountStorage" style="height:36px;padding:0 13px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12px;font-weight:600;cursor:pointer" class="d2-btn-accent">{{ tr('backup.mount') || 'Mount' }}</button>
              <button @click="unmountStorage" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.unmount') || 'Unmount' }}</button>
              <button @click="testWriteStorage" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12px;font-weight:550;cursor:pointer" class="d2-btn-ghost">{{ tr('backup.testWrite') || 'Test write' }}</button>
            </div>
          </template>
          <div v-if="bkIsLocal" style="font-size:12.5px;color:var(--text-3);line-height:1.5">{{ storageUsed }} / {{ storageTotal }} · {{ storageMountLabel }}</div>
        </template>
      </div>
    </div>

    <div v-if="msg" style="color:var(--green);font-size:13px;margin-top:12px">{{ msg }}</div>
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
async function create() { creating.value = true; try { await backupApi.create(); await load(); flash(tr('backup.createdOk') || 'Backup created') } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { creating.value = false } }
function fileId(b) { return b.backup_id }
function isDbOnly(b) { return !!(b.database_dump && b.env_backed_up === false) || b.type === 'db' }
async function fmtBackupSize(b) { if (b.archive_size_bytes != null) return formatBytes(b.archive_size_bytes); if (b.archive_size_mb != null) return b.archive_size_mb + ' MB'; return '—' }
async function verify(b) { try { const r = await backupApi.verify(fileId(b)); alert(r.data?.valid === false ? (tr('backup.corrupt') || 'Backup is CORRUPT') : (tr('backup.valid') || 'Backup verified OK')) } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreFull(b) { if (!await d2confirm(tr('backup.restoreFullConfirm') || 'Full restore from this backup? This overwrites current data.')) return; try { await backupApi.restoreFull(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restoreDb(b) { if (!await d2confirm(tr('backup.restoreDbConfirm') || 'Restore database only from this backup?')) return; try { await backupApi.restoreDatabase(fileId(b)); flash(tr('backup.restored') || 'Restore started') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function remove(b) { if (!await d2confirm(tr('backup.deleteConfirm') || 'Delete this backup?')) return; try { await backupApi.delete(fileId(b)); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
function flash(m) { msg.value = m; setTimeout(() => msg.value = '', 3000) }
function fmtBytes(b) { return formatBytes(b || 0) }
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }

// --- his-name aliases so the markup reads 1:1 with the handoff ---
const createBackup = create
const refreshBackups = load

// --- schedule / storage state (backupApi.getSettings/saveSettings + storage) ---
const bkTab = ref('sched')
const bkIsSched = computed(() => bkTab.value === 'sched')
const bkIsStorage = computed(() => bkTab.value === 'storage')
const backupSettings = reactive({ schedule: 'daily', time: '03:00', keep: 7, storage: 'local', net_host: '', net_share: '', net_user: '', net_pass: '' })
const bkIsLocal = computed(() => backupSettings.storage === 'local')
const bkIsNet = computed(() => backupSettings.storage === 'net')
const savingSettings = ref(false)
const storage = ref({ mounted: false, used_bytes: null, total_bytes: null })

async function loadSettings() {
  try {
    const { data } = await backupApi.getSettings()
    if (data && typeof data === 'object') {
      if (data.schedule != null) backupSettings.schedule = data.schedule
      if (data.time != null) backupSettings.time = data.time
      if (data.keep != null) backupSettings.keep = data.keep
      if (data.storage != null) backupSettings.storage = data.storage
      if (data.net_host != null) backupSettings.net_host = data.net_host
      if (data.net_share != null) backupSettings.net_share = data.net_share
      if (data.net_user != null) backupSettings.net_user = data.net_user
    }
  } catch (_) { /* settings endpoint optional */ }
}
async function loadStorage() {
  try { const { data } = await backupApi.storageStatus(); if (data && typeof data === 'object') storage.value = { ...storage.value, ...data } } catch (_) { /* optional */ }
}
async function saveBackupSettings() { savingSettings.value = true; try { await backupApi.saveSettings({ ...backupSettings, keep: Number(backupSettings.keep) || 0 }); flash(tr('backup.settingsSaved') || 'Settings saved') } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { savingSettings.value = false } }
async function mountStorage() { try { await backupApi.mount(); await loadStorage(); flash(tr('backup.mounted') || 'Mounted') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function unmountStorage() { try { await backupApi.unmount(); await loadStorage(); flash(tr('backup.unmounted') || 'Unmounted') } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function testWriteStorage() { try { const r = await backupApi.testWrite(); alert(r.data?.ok === false ? (tr('backup.testWriteFail') || 'Write test FAILED') : (tr('backup.testWriteOk') || 'Write test OK')) } catch (e) { alert(e.response?.data?.detail || 'Error') } }

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
  const u = storage.value.used_bytes, tot = storage.value.total_bytes
  if (!u || !tot) return '0%'
  return Math.min(100, Math.round((u / tot) * 100)) + '%'
})
const storageUsed = computed(() => storage.value.used_bytes != null ? fmtBytes(storage.value.used_bytes) : '—')
const storageTotal = computed(() => storage.value.total_bytes != null ? fmtBytes(storage.value.total_bytes) : '—')
const storageMountColor = computed(() => storage.value.mounted ? 'var(--green)' : 'var(--text-3)')
const storageMountLabel = computed(() => storage.value.mounted ? (tr('backup.mountedYes') || 'Mounted') : (tr('backup.mountedNo') || 'Not mounted'))

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
