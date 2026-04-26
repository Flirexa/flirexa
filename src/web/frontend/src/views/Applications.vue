<template>
  <div class="accounts-page">

    <!-- Stats -->
    <div class="row g-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ accounts.length }}</div>
              <div class="stat-label">{{ $t('applications.totalAccounts') }}</div>
            </div>
            <div class="stat-icon">👥</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value text-success">{{ accounts.filter(a => a.is_active).length }}</div>
              <div class="stat-label">{{ $t('applications.activeAccounts') }}</div>
            </div>
            <div class="stat-icon">✅</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value text-primary">{{ accounts.filter(a => a.role === 'admin').length }}</div>
              <div class="stat-label">{{ $t('applications.admins') }}</div>
            </div>
            <div class="stat-icon">🔑</div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value text-warning">{{ accounts.filter(a => a.role === 'manager').length }}</div>
              <div class="stat-label">{{ $t('applications.managers') }}</div>
            </div>
            <div class="stat-icon">🛡️</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Table card -->
    <div class="table-card">
      <div class="accounts-toolbar">
        <h6 class="mb-0 fw-bold">{{ $t('applications.title') }}</h6>
        <button class="btn btn-primary btn-create" @click="openCreate">
          <span class="btn-create__icon">+</span>
          <span class="btn-create__text">{{ $t('applications.createAccount') }}</span>
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary" role="status"></div>
      </div>

      <!-- Empty -->
      <div v-else-if="accounts.length === 0" class="text-center py-5 text-muted">
        {{ $t('applications.noAccounts') }}
      </div>

      <template v-else>
        <!-- Desktop table (hidden on mobile) -->
        <div class="accounts-table-wrap d-none d-md-block">
          <table class="accounts-table">
            <colgroup>
              <col style="width:200px">
              <col style="width:140px">
              <col style="width:140px">
              <col style="width:150px">
              <col style="width:150px">
              <col>
            </colgroup>
            <thead>
              <tr>
                <th>{{ $t('applications.username') }}</th>
                <th>{{ $t('applications.role') }}</th>
                <th>{{ $t('common.status') }}</th>
                <th>{{ $t('applications.created') }}</th>
                <th>{{ $t('applications.lastLogin') }}</th>
                <th>{{ $t('common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="accounts-row">
                <td class="col-username">
                  <span class="fw-semibold">{{ acc.username }}</span>
                </td>
                <td class="col-badge">
                  <span class="acc-badge" :class="acc.role === 'admin' ? 'acc-badge--admin' : 'acc-badge--manager'">
                    {{ acc.role === 'admin' ? $t('applications.roleAdmin') : $t('applications.roleManager') }}
                  </span>
                </td>
                <td class="col-badge">
                  <span class="acc-badge" :class="acc.is_active ? 'acc-badge--active' : 'acc-badge--inactive'">
                    {{ acc.is_active ? $t('common.active') : $t('common.inactive') }}
                  </span>
                </td>
                <td class="col-date">{{ formatDate(acc.created_at) }}</td>
                <td class="col-date">{{ acc.last_login ? formatDate(acc.last_login) : '—' }}</td>
                <td class="col-actions">
                  <div class="action-group">
                    <button class="action-btn" @click="openEdit(acc)" :title="$t('applications.editAccount')">✏️</button>
                    <button class="action-btn" @click="openPermissions(acc)" :title="$t('applications.editPermissions')">🛡️</button>
                    <button class="action-btn" @click="toggleActive(acc)"
                      :title="acc.is_active ? $t('applications.disable') : $t('applications.enable')">
                      {{ acc.is_active ? '🔒' : '🔓' }}
                    </button>
                    <button class="action-btn action-btn--danger" @click="confirmDelete(acc)" :title="$t('common.delete')">🗑️</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Mobile cards (hidden on desktop) -->
        <div class="accounts-cards d-md-none">
          <div v-for="acc in accounts" :key="acc.id" class="acc-card">
            <!-- Row 1: username + status badge -->
            <div class="acc-card__top">
              <span class="acc-card__username">{{ acc.username }}</span>
              <span class="acc-badge" :class="acc.is_active ? 'acc-badge--active' : 'acc-badge--inactive'">
                {{ acc.is_active ? $t('common.active') : $t('common.inactive') }}
              </span>
            </div>
            <!-- Row 2: role badge -->
            <div class="acc-card__role">
              <span class="acc-badge" :class="acc.role === 'admin' ? 'acc-badge--admin' : 'acc-badge--manager'">
                {{ acc.role === 'admin' ? $t('applications.roleAdmin') : $t('applications.roleManager') }}
              </span>
            </div>
            <!-- Row 3: dates -->
            <div class="acc-card__meta">
              <div class="acc-card__meta-row">
                <span class="acc-card__meta-label">{{ $t('applications.created') }}</span>
                <span>{{ formatDate(acc.created_at) }}</span>
              </div>
              <div class="acc-card__meta-row">
                <span class="acc-card__meta-label">{{ $t('applications.lastLogin') }}</span>
                <span>{{ acc.last_login ? formatDate(acc.last_login) : '—' }}</span>
              </div>
            </div>
            <!-- Row 4: 2×2 action grid -->
            <div class="acc-card__actions">
              <button class="acc-card__btn" @click="openEdit(acc)">✏️ {{ $t('applications.editAccount') }}</button>
              <button class="acc-card__btn" @click="openPermissions(acc)">🛡️ {{ $t('applications.editPermissions') }}</button>
              <button class="acc-card__btn acc-card__btn--warn" @click="toggleActive(acc)">
                {{ acc.is_active ? '🔒 ' + $t('applications.disable') : '🔓 ' + $t('applications.enable') }}
              </button>
              <button class="acc-card__btn acc-card__btn--danger" @click="confirmDelete(acc)">🗑️ {{ $t('common.delete') }}</button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreateModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('applications.createAccount') }}</h5>
            <button type="button" class="btn-close" @click="showCreateModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ $t('applications.username') }}</label>
                <input v-model="form.username" type="text" class="form-control" placeholder="manager_john">
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ $t('applications.email') }}</label>
                <input v-model="form.email" type="email" class="form-control" placeholder="john@example.com">
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ $t('applications.password') }}</label>
                <div class="input-group">
                  <input v-model="form.password" :type="showPassword ? 'text' : 'password'" class="form-control" placeholder="min 6 chars">
                  <button class="btn btn-outline-secondary" type="button" @click="showPassword = !showPassword">{{ showPassword ? '🔒' : '👁' }}</button>
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">{{ $t('applications.role') }}</label>
                <select v-model="form.role" class="form-select">
                  <option value="admin">{{ $t('applications.roleAdmin') }}</option>
                  <option value="manager">{{ $t('applications.roleManager') }}</option>
                </select>
              </div>
            </div>
            <div v-if="form.role === 'manager'" class="mt-4">
              <label class="form-label fw-semibold">{{ $t('applications.permissions') }}</label>
              <div class="row g-2 mt-1">
                <div v-for="perm in availablePermissions" :key="perm.key" class="col-6 col-md-4">
                  <div class="form-check perm-check">
                    <input class="form-check-input" type="checkbox" :id="'perm_' + perm.key"
                      :value="perm.key" v-model="form.permissions">
                    <label class="form-check-label" :for="'perm_' + perm.key">{{ $t('applications.' + perm.label) }}</label>
                  </div>
                </div>
              </div>
              <div class="mt-2">
                <button class="btn btn-sm btn-outline-secondary me-2" @click="selectAllPerms">{{ $t('common.selectAll') || 'Select all' }}</button>
                <button class="btn btn-sm btn-outline-secondary" @click="form.permissions = []">{{ $t('common.clearAll') || 'Clear' }}</button>
              </div>
            </div>
            <div v-if="createError" class="alert alert-danger py-2 mt-3">{{ createError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="createAccount" :disabled="creating">
              <span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('applications.createAccount') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Modal -->
    <div v-if="showEditModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('applications.editAccount') }}: {{ selectedAccount?.username }}</h5>
            <button type="button" class="btn-close" @click="showEditModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('applications.role') }}</label>
              <select v-model="editForm.role" class="form-select">
                <option value="admin">{{ $t('applications.roleAdmin') }}</option>
                <option value="manager">{{ $t('applications.roleManager') }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('applications.newPassword') }} <small class="text-muted">({{ $t('common.optional') || 'optional' }})</small></label>
              <input v-model="editForm.password" type="password" class="form-control" placeholder="leave blank to keep">
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showEditModal = false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="saveEdit">{{ $t('common.save') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Permissions Modal -->
    <div v-if="showPermissionsModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('applications.editPermissions') }}: {{ selectedAccount?.username }}</h5>
            <button type="button" class="btn-close" @click="showPermissionsModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="row g-2">
              <div v-for="perm in availablePermissions" :key="perm.key" class="col-6 col-md-4">
                <div class="form-check perm-check">
                  <input class="form-check-input" type="checkbox" :id="'eperm_' + perm.key"
                    :value="perm.key" v-model="editPermissions">
                  <label class="form-check-label" :for="'eperm_' + perm.key">{{ $t('applications.' + perm.label) }}</label>
                </div>
              </div>
            </div>
            <div class="mt-3">
              <button class="btn btn-sm btn-outline-secondary me-2" @click="editPermissions = availablePermissions.map(p => p.key)">{{ $t('common.selectAll') || 'Select all' }}</button>
              <button class="btn btn-sm btn-outline-secondary" @click="editPermissions = []">{{ $t('common.clearAll') || 'Clear' }}</button>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showPermissionsModal = false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="savePermissions">{{ $t('common.save') }}</button>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { appAccountsApi } from '../api'

const { t } = useI18n()

const accounts = ref([])
const loading = ref(true)
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showPermissionsModal = ref(false)
const creating = ref(false)
const createError = ref('')
const showPassword = ref(false)
const selectedAccount = ref(null)
const editPermissions = ref([])

const form = ref({ email: '', username: '', password: '', role: 'admin', permissions: [] })
const editForm = ref({ role: 'admin', password: '' })

const availablePermissions = [
  { key: 'clients',  label: 'permClients' },
  { key: 'servers',  label: 'permServers' },
  { key: 'payments', label: 'permPayments' },
  { key: 'support',  label: 'permSupport' },
  { key: 'stats',    label: 'permStats' },
  { key: 'bots',     label: 'permBots' },
  { key: 'settings', label: 'permSettings' },
  { key: 'updates',  label: 'permUpdates' },
  { key: 'backup',   label: 'permBackup' },
  { key: 'logs',     label: 'permLogs' },
]

const loadAccounts = async () => {
  loading.value = true
  try {
    const { data } = await appAccountsApi.list()
    accounts.value = data
  } catch (e) {
    console.error('Failed to load accounts:', e)
  }
  loading.value = false
}

const openCreate = () => {
  form.value = { email: '', username: '', password: '', role: 'admin', permissions: [] }
  createError.value = ''
  showPassword.value = false
  showCreateModal.value = true
}

const selectAllPerms = () => {
  form.value.permissions = availablePermissions.map(p => p.key)
}

const createAccount = async () => {
  createError.value = ''
  if (!form.value.email || !form.value.username || !form.value.password) {
    createError.value = t('common.allFieldsRequired') || 'All fields are required'
    return
  }
  if (form.value.password.length < 6) {
    createError.value = 'Password must be at least 6 characters'
    return
  }
  creating.value = true
  try {
    const payload = {
      email: form.value.email,
      username: form.value.username,
      password: form.value.password,
      role: form.value.role,
    }
    if (form.value.role === 'manager') {
      payload.permissions = form.value.permissions
    }
    await appAccountsApi.create(payload)
    showCreateModal.value = false
    await loadAccounts()
  } catch (e) {
    createError.value = e.response?.data?.detail || 'Failed to create account'
  }
  creating.value = false
}

const openEdit = (acc) => {
  selectedAccount.value = acc
  editForm.value = { role: acc.role, password: '' }
  showEditModal.value = true
}

const saveEdit = async () => {
  const payload = { role: editForm.value.role }
  if (editForm.value.password) payload.password = editForm.value.password
  if (editForm.value.role === 'admin') payload.permissions = null
  try {
    await appAccountsApi.update(selectedAccount.value.id, payload)
    showEditModal.value = false
    await loadAccounts()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update account')
  }
}

const openPermissions = (acc) => {
  selectedAccount.value = acc
  editPermissions.value = acc.permissions ? [...acc.permissions] : []
  showPermissionsModal.value = true
}

const savePermissions = async () => {
  try {
    await appAccountsApi.update(selectedAccount.value.id, { permissions: editPermissions.value })
    showPermissionsModal.value = false
    await loadAccounts()
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update permissions')
  }
}

const toggleActive = async (acc) => {
  try {
    await appAccountsApi.update(acc.id, { is_active: !acc.is_active })
    await loadAccounts()
  } catch (e) {
    alert('Failed: ' + (e.response?.data?.detail || e.message))
  }
}

const confirmDelete = async (acc) => {
  if (!confirm(t('applications.deleteConfirm', { username: acc.username }))) return
  try {
    await appAccountsApi.delete(acc.id)
    await loadAccounts()
  } catch (e) {
    alert('Failed: ' + (e.response?.data?.detail || e.message))
  }
}

const formatDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—'

onMounted(loadAccounts)
</script>

<style scoped>
/* ── Toolbar ──────────────────────────────────────────────────────────────── */
.accounts-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: .875rem 1.25rem;
  border-bottom: 1px solid var(--vxy-border);
}

.btn-create {
  display: inline-flex;
  align-items: center;
  gap: .375rem;
  padding: .4rem .875rem;
  font-size: .875rem;
  font-weight: 500;
  white-space: nowrap;
  line-height: 1.4;
}
.btn-create__icon { font-size: 1rem; line-height: 1; }

/* ── Desktop table ────────────────────────────────────────────────────────── */
.accounts-table-wrap {
  overflow-x: auto;
}

.accounts-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

.accounts-table th {
  padding: .625rem 1rem;
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: var(--vxy-muted);
  background: var(--vxy-hover-bg);
  border-bottom: 1px solid var(--vxy-border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.accounts-table td {
  padding: .75rem 1rem;
  border-bottom: 1px solid var(--vxy-border);
  vertical-align: middle;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--vxy-text);
}

.accounts-row:last-child td { border-bottom: none; }

.accounts-row:hover td { background: var(--vxy-hover-bg); }

.col-username { font-weight: 600; }
.col-badge    { }
.col-date     { font-size: .875rem; color: var(--vxy-muted); }
.col-actions  { overflow: visible; }

/* ── Badges ───────────────────────────────────────────────────────────────── */
.acc-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  min-width: 72px;
  padding: 0 .625rem;
  font-size: .72rem;
  font-weight: 600;
  border-radius: 20px;
  line-height: 1;
  white-space: nowrap;
}

.acc-badge--admin    { background: rgba(115,103,240,.15); color: #7367f0; }
.acc-badge--manager  { background: rgba(255,159,67,.15);  color: #ff9f43; }
.acc-badge--active   { background: rgba(40,199,111,.15);  color: #28c76f; }
.acc-badge--inactive { background: rgba(130,134,139,.15); color: #82868b; }
.acc-badge--blocked  { background: rgba(234,84,85,.15);   color: #ea5455; }

/* ── Desktop action buttons ───────────────────────────────────────────────── */
.action-group {
  display: flex;
  align-items: center;
  gap: .25rem;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  font-size: .9rem;
  line-height: 1;
  border: 1px solid var(--vxy-border);
  border-radius: .375rem;
  background: transparent;
  color: var(--vxy-text);
  cursor: pointer;
  transition: background .15s, border-color .15s;
  flex-shrink: 0;
}
.action-btn:hover {
  background: var(--vxy-hover-bg);
  border-color: var(--vxy-primary);
}
.action-btn--danger { border-color: rgba(234,84,85,.35); }
.action-btn--danger:hover {
  background: rgba(234,84,85,.1);
  border-color: #ea5455;
}

/* ── Mobile cards ─────────────────────────────────────────────────────────── */
.accounts-cards {
  display: flex;
  flex-direction: column;
}

.acc-card {
  padding: .875rem 1rem;
  border-bottom: 1px solid var(--vxy-border);
}
.acc-card:last-child { border-bottom: none; }

/* Row 1: username + status */
.acc-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
  margin-bottom: .25rem;
}
.acc-card__username {
  font-weight: 700;
  font-size: .9375rem;
  color: var(--vxy-heading);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Row 2: role badge */
.acc-card__role {
  margin-bottom: .5rem;
}

/* Row 3: dates */
.acc-card__meta {
  display: flex;
  flex-direction: column;
  gap: .125rem;
  margin-bottom: .625rem;
}
.acc-card__meta-row {
  display: flex;
  gap: .5rem;
  font-size: .8rem;
  color: var(--vxy-text);
}
.acc-card__meta-label {
  color: var(--vxy-muted);
  min-width: 100px;
  flex-shrink: 0;
}

/* Row 4: 2×2 action grid */
.acc-card__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .375rem;
}

.acc-card__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .3rem;
  height: 36px;
  padding: 0 .5rem;
  font-size: .78rem;
  font-weight: 500;
  border-radius: .375rem;
  border: 1px solid var(--vxy-border);
  cursor: pointer;
  transition: background .15s, border-color .15s;
  background: transparent;
  color: var(--vxy-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acc-card__btn:hover {
  background: var(--vxy-hover-bg);
  border-color: var(--vxy-primary);
}
.acc-card__btn--warn {
  border-color: rgba(255,159,67,.4);
  color: #ff9f43;
}
.acc-card__btn--warn:hover {
  background: rgba(255,159,67,.1);
  border-color: #ff9f43;
}
.acc-card__btn--danger {
  border-color: rgba(234,84,85,.4);
  color: #ea5455;
}
.acc-card__btn--danger:hover {
  background: rgba(234,84,85,.1);
  border-color: #ea5455;
}

/* ── Permission checkboxes ────────────────────────────────────────────────── */
.perm-check {
  padding: .5rem .75rem;
  border: 1px solid var(--vxy-border);
  border-radius: .5rem;
  background: var(--vxy-hover-bg);
  transition: border-color .15s;
}
.perm-check:has(.form-check-input:checked) {
  border-color: var(--vxy-primary);
  background: var(--vxy-primary-light);
}
.perm-check .form-check-input { margin-top: .1rem; }
.perm-check .form-check-label { cursor: pointer; font-size: .875rem; }

/* ── Stat cards: no letter-level breaks ───────────────────────────────────── */
/* The left div must be able to shrink so the label doesn't overflow the icon */
.stat-card .d-flex > div:first-child {
  min-width: 0;
  overflow: hidden;
}
.stat-label {
  word-break: normal;
  overflow-wrap: normal;   /* critical: never break Cyrillic words mid-character */
  hyphens: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
  font-size: .8rem;
}

/* ── Mobile toolbar: button full-width below title ────────────────────────── */
@media (max-width: 767px) {
  .accounts-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: .625rem;
  }
  .btn-create {
    width: 100%;
    justify-content: center;
    height: 40px;
  }
}

/* ── Stat cards: smaller text on narrow screens ───────────────────────────── */
@media (max-width: 575px) {
  .stat-value { font-size: 1.2rem !important; }
  .stat-label { font-size: .72rem; }
}
</style>
