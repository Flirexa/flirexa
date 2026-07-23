<!-- New-design Audit Log — his exact 1:1 handoff (lines 774-806): filter-by-action
     + filter-by-user inputs, Refresh, prev/next pager, then a card-wrapped table
     (Admin[avatar+name] / Action / Target[mono] / IP[mono] / Time[right]).
     Wired to systemApi.getLogs; a computed adapter maps our payload → his fields. -->
<template>
  <div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <input v-model="actionFilter" @input="onFilter" :placeholder="tr('logs.filterAction') || 'Filter by action…'" class="d2-loginput" style="width:200px" />
      <input v-model="userFilter" @input="onFilter" :placeholder="tr('logs.filterUser') || 'Filter by user…'" class="d2-loginput" style="width:180px" />
      <button @click="load" class="d2-logbtn">{{ tr('common.refresh') || 'Refresh' }}</button>
      <div style="margin-left:auto;display:flex;gap:6px">
        <button @click="logPrev" class="d2-logbtn">{{ tr('logs.prev') || 'Prev' }}</button>
        <button @click="logNext" class="d2-logbtn">{{ tr('logs.next') || 'Next' }}</button>
      </div>
    </div>

    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left">
          <th style="padding:11px 20px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('logs.admin') || 'Admin' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('logs.action') || 'Action' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('logs.target') || 'Target' }}</th>
          <th style="padding:11px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('logs.ip') || 'IP' }}</th>
          <th style="padding:11px 20px;text-align:right;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3)">{{ tr('logs.time') || 'Time' }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="l in logs" :key="l.id" class="d2-logrow" style="border-top:1px solid var(--border)">
            <td style="padding:12px 20px"><div style="display:flex;align-items:center;gap:9px"><span style="width:26px;height:26px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:10.5px;font-weight:650;flex:none">{{ l.who }}</span><span style="font-weight:550">{{ l.admin }}</span></div></td>
            <td style="padding:12px 12px;color:var(--text)">{{ l.action }}</td>
            <td style="padding:12px 12px;font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-3)">{{ l.target }}</td>
            <td style="padding:12px 12px;font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-3)">{{ l.ip }}</td>
            <td style="padding:12px 20px;text-align:right;font-size:12px;color:var(--text-3)">{{ l.time }}</td>
          </tr>
          <tr v-if="!logs.length"><td colspan="5" style="padding:24px;text-align:center;color:var(--text-3)">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('logs.empty') || 'No audit entries') }}</td></tr>
        </tbody>
      </table>
    </div></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { systemApi } from '../../api'
import { formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const rows = ref([])
const loading = ref(false)
const actionFilter = ref('')
const userFilter = ref('')
const page = ref(0)
const PAGE = 50

async function load() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (actionFilter.value) params.action = actionFilter.value
    const { data } = await systemApi.getLogs(params)
    rows.value = data.items || data.logs || (Array.isArray(data) ? data : [])
  } catch (e) { console.error(e) } finally { loading.value = false }
}

function initials(s) {
  const str = String(s || '').trim()
  if (!str) return '?'
  const parts = str.split(/[\s._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return str.slice(0, 2).toUpperCase()
}
function fmtDate(d) { try { return formatDate(d) } catch (_) { return String(d) } }
function targetStr(l) {
  if (l.target_name) return l.target_name
  if (l.target_type) return l.target_type + (l.target_id ? ' #' + l.target_id : '')
  return '—'
}
function ipStr(l) {
  if (l.ip_address || l.ip) return l.ip_address || l.ip
  const d = l.details
  if (d && typeof d === 'object' && (d.ip || d.ip_address)) return d.ip || d.ip_address
  return '—'
}

// Adapter: our audit payload → his field names (who/admin/action/target/ip/time)
const adapted = computed(() => rows.value.map(l => {
  const admin = l.user_name || l.username || l.user_type || 'system'
  return {
    id: l.id,
    who: initials(admin),
    admin: admin + (l.user_id ? ' #' + l.user_id : ''),
    action: l.action,
    target: targetStr(l),
    ip: ipStr(l),
    time: l.created_at ? fmtDate(l.created_at) : '—',
    _admin: admin,
  }
}))
const filtered = computed(() => {
  const u = userFilter.value.trim().toLowerCase()
  if (!u) return adapted.value
  return adapted.value.filter(l => (l._admin + ' ' + l.admin).toLowerCase().includes(u))
})
const logs = computed(() => filtered.value.slice(page.value * PAGE, page.value * PAGE + PAGE))

function onFilter() { page.value = 0 }
function logPrev() { if (page.value > 0) page.value-- }
function logNext() { if ((page.value + 1) * PAGE < filtered.value.length) page.value++ }

onMounted(() => {
  ui.set({
    title: tr('nav.logs') || 'Audit log',
    search: true,
    searchPh: tr('logs.search') || 'Search logs…',
    onSearch: v => { userFilter.value = v; page.value = 0 },
  })
  load()
})
</script>

<style scoped>
.d2-loginput { height: 34px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 9px; padding: 0 12px; font: inherit; font-size: 12.5px; outline: none; }
.d2-loginput:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-logbtn { height: 34px; padding: 0 14px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 9px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.d2-logbtn:hover { background: var(--panel-2); }
.d2-logrow:hover { background: var(--panel-2); }
</style>
