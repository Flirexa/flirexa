<template>
  <div>
    <!-- Inline feedback -->
    <div v-if="successMsg" class="alert alert-success alert-dismissible fade show">
      {{ successMsg }}
      <button type="button" class="btn-close" @click="successMsg = null"></button>
    </div>
    <div v-if="errorMsg" class="alert alert-danger alert-dismissible fade show">
      {{ errorMsg }}
      <button type="button" class="btn-close" @click="errorMsg = null"></button>
    </div>

    <!-- Actions bar -->
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-3">
      <div class="d-flex gap-2 flex-wrap">
        <input
          v-model="search"
          type="text"
          class="form-control form-control-sm filter-input"
          :placeholder="$t('clients.searchPlaceholder')"
        />
        <select v-model="filterStatus" class="form-select form-select-sm filter-select">
          <option value="">{{ $t('clients.all') }}</option>
          <option value="enabled">{{ $t('common.enabled') }}</option>
          <option value="disabled">{{ $t('common.disabled') }}</option>
          <option value="online">{{ $t('clients.online') || 'Online' }}</option>
          <option value="offline">{{ $t('clients.offline') || 'Offline' }}</option>
        </select>
        <select v-model="filterServer" class="form-select form-select-sm filter-select-wide">
          <option value="">{{ $t('clients.allServers') }}</option>
          <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <button class="btn btn-primary btn-sm" @click="showCreateModal = true">
        {{ $t('clients.newClient') }}
      </button>
    </div>

    <!-- Bulk actions bar -->
    <div v-if="selectedIds.size > 0" class="d-flex align-items-center gap-2 mb-3 p-2 rounded border bulk-bar">
      <span class="text-muted small">{{ selectedIds.size }} selected</span>
      <button class="btn btn-outline-success btn-sm" @click="bulkEnable" :disabled="bulkLoading">Enable</button>
      <button class="btn btn-outline-secondary btn-sm" @click="bulkDisable" :disabled="bulkLoading">Disable</button>
      <button class="btn btn-outline-danger btn-sm" @click="bulkDelete" :disabled="bulkLoading">Delete</button>
      <button class="btn btn-link btn-sm text-muted" @click="selectedIds = new Set()">Clear</button>
    </div>

    <!-- Clients Table -->
    <div class="table-card">
      <div class="table-responsive clients-table-wrap">
        <table class="table table-hover clients-table">
          <thead>
            <tr>
              <th style="width: 36px">
                <input type="checkbox" class="form-check-input" :checked="allPageSelected" @change="toggleSelectAll" />
              </th>
              <th class="sortable-th" @click="toggleSort('name')">{{ $t('common.name') }}<span class="sort-arrow">{{ sortIcon('name') }}</span></th>
              <th class="d-none d-lg-table-cell sortable-th" @click="toggleSort('server')">{{ $t('clients.server') }}<span class="sort-arrow">{{ sortIcon('server') }}</span></th>
              <th class="d-none d-md-table-cell sortable-th" @click="toggleSort('ip')">{{ $t('dashboard.ip') }}<span class="sort-arrow">{{ sortIcon('ip') }}</span></th>
              <th class="d-none d-sm-table-cell sortable-th" @click="toggleSort('status')">{{ $t('common.status') }}<span class="sort-arrow">{{ sortIcon('status') }}</span></th>
              <th class="d-none d-md-table-cell sortable-th" @click="toggleSort('traffic')">{{ $t('dashboard.traffic') }}<span class="sort-arrow">{{ sortIcon('traffic') }}</span></th>
              <th class="d-none d-lg-table-cell sortable-th" @click="toggleSort('bandwidth')">{{ $t('dashboard.bandwidth') }}<span class="sort-arrow">{{ sortIcon('bandwidth') }}</span></th>
              <th class="d-none d-lg-table-cell sortable-th" @click="toggleSort('expiry')">{{ $t('clients.expiry') }}<span class="sort-arrow">{{ sortIcon('expiry') }}</span></th>
              <th>{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="client in pagedClients" :key="client.id" :class="selectedIds.has(client.id) ? 'table-active' : ''">
              <td>
                <input type="checkbox" class="form-check-input" :checked="selectedIds.has(client.id)" @change="toggleSelect(client.id)" />
              </td>
              <td class="fw-medium client-name-cell">
                <div class="d-flex align-items-center gap-1">
                  <span class="client-online-dot" :class="isClientOnline(client) ? 'online' : 'offline'" :title="isClientOnline(client) ? 'Online' : lastSeenText(client)"></span>
                  <span class="client-name">{{ client.name }}</span>
                  <span v-if="isProxyClient(client)" class="badge badge-soft-warning ms-1" style="font-size:0.6em">{{ $t('clients.proxyClientBadge') }}</span>
                </div>
                <div class="client-meta-line">
                  <small class="text-muted" :title="client.created_at">{{ $t('clients.created') }}: {{ formatDateShort(client.created_at) }}</small>
                  <small v-if="!isClientOnline(client) && client.last_handshake" class="text-muted ms-2">· {{ lastSeenText(client) }}</small>
                </div>
                <!-- xs: status badge + IP/protocol in one line (status column hidden on xs) -->
                <div class="d-flex align-items-center gap-1 mt-1 d-sm-none">
                  <span class="badge" :class="client.enabled ? 'badge-online' : 'badge-offline'"
                    style="height:auto;padding:0.1em 0.4em;border-radius:3px;font-size:0.6em;line-height:1.5">
                    {{ client.enabled ? $t('common.enabled') : $t('common.disabled') }}
                  </span>
                  <small class="text-muted text-truncate">{{ isProxyClient(client) ? getServerProtocol(client.server_id) : (client.ipv4 || '—') }}</small>
                </div>
                <!-- sm only: just IP/protocol (status column visible on sm) -->
                <small class="text-muted d-none d-sm-block d-md-none">{{ isProxyClient(client) ? getServerProtocol(client.server_id) : (client.ipv4 || '—') }}</small>
              </td>
              <td class="d-none d-lg-table-cell">
                <small class="text-muted">{{ getServerName(client.server_id) }}</small>
              </td>
              <td class="d-none d-md-table-cell">
                <span v-if="isProxyClient(client)" class="text-muted small fst-italic">{{ getServerProtocol(client.server_id) }}</span>
                <code v-else>{{ client.ipv4 }}</code>
              </td>
              <td class="d-none d-sm-table-cell">
                <span class="badge" :class="client.enabled ? 'badge-online' : 'badge-offline'">
                  {{ client.enabled ? $t('common.enabled') : $t('common.disabled') }}
                </span>
              </td>
              <td class="d-none d-md-table-cell">
                <!-- Proxy clients: traffic is not tracked at the protocol level -->
                <span v-if="isProxyClient(client)" class="text-muted small fst-italic">—</span>
                <template v-else>
                  <div>
                    {{ formatBytes((client.traffic_used_rx || 0) + (client.traffic_used_tx || 0)) }}
                    <span v-if="client.traffic_limit_mb" class="text-muted">/ {{ formatMB(client.traffic_limit_mb) }}</span>
                  </div>
                  <div class="progress traffic-progress mt-1" v-if="client.traffic_limit_mb">
                    <div
                      class="progress-bar"
                      :class="getTrafficColor(client)"
                      :style="{ width: getTrafficPercent(client) + '%' }"
                    ></div>
                  </div>
                </template>
              </td>
              <td class="d-none d-lg-table-cell">
                <span v-if="isProxyClient(client)" class="text-muted small fst-italic">—</span>
                <span v-else>{{ client.bandwidth_limit ? client.bandwidth_limit + ' Mbps' : '∞' }}</span>
              </td>
              <td class="d-none d-lg-table-cell">
                <span v-if="client.expiry_date" :class="isExpiringSoon(client) ? 'text-danger' : ''">
                  {{ formatDate(client.expiry_date) }}
                </span>
                <span v-else class="text-muted">∞</span>
              </td>
              <td>
                <!-- Desktop (sm+): connected btn-group -->
                <div class="btn-group btn-group-sm d-none d-sm-inline-flex">
                  <button class="btn btn-outline-secondary" @click="toggleClient(client)" :title="client.enabled ? 'Disable' : 'Enable'">
                    <i :class="client.enabled ? 'mdi mdi-pause' : 'mdi mdi-play'"></i>
                  </button>
                  <button class="btn btn-outline-secondary" @click="showConfig(client)" title="Config"><i class="mdi mdi-tray-arrow-down"></i></button>
                  <button class="btn btn-outline-secondary" @click="editClient(client)" title="Edit"><i class="mdi mdi-pencil-outline"></i></button>
                  <button class="btn btn-outline-danger" @click="confirmDelete(client)" title="Delete"><i class="mdi mdi-trash-can-outline"></i></button>
                </div>
                <!-- Mobile (xs): compact buttons + detail sheet -->
                <div class="d-flex gap-1 d-sm-none client-actions-mobile">
                  <button class="btn btn-sm btn-outline-secondary" @click="toggleClient(client)" :title="client.enabled ? 'Disable' : 'Enable'">
                    <i :class="client.enabled ? 'mdi mdi-pause' : 'mdi mdi-play'"></i>
                  </button>
                  <button class="btn btn-sm btn-outline-secondary" @click="showConfig(client)" title="Config"><i class="mdi mdi-tray-arrow-down"></i></button>
                  <button class="btn btn-sm btn-outline-secondary" @click="openDetail(client)" title="More"><i class="mdi mdi-dots-horizontal"></i></button>
                </div>
              </td>
            </tr>
            <tr v-if="pagedClients.length === 0" class="clients-empty-row">
              <td colspan="9" class="text-center text-muted py-4">
                {{ store.loading ? $t('common.loading') : $t('dashboard.noClients') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="d-flex justify-content-between align-items-center px-3 py-2 border-top">
        <small class="text-muted">
          {{ $t('common.showing') }} {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, filteredClients.length) }}
          {{ $t('common.entries') }} ({{ filteredClients.length }} total)
        </small>
        <div class="d-flex gap-1">
          <button class="btn btn-outline-secondary btn-sm" :disabled="currentPage === 1" @click="currentPage--">{{ $t('common.prev') }}</button>
          <span class="btn btn-sm disabled">{{ currentPage }} / {{ totalPages }}</span>
          <button class="btn btn-outline-secondary btn-sm" :disabled="currentPage === totalPages" @click="currentPage++">{{ $t('common.next') }}</button>
        </div>
      </div>
    </div>

    <!-- Create Client Modal -->
    <div class="modal fade" :class="{ show: showCreateModal }" :style="{ display: showCreateModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('clients.createTitle') }}</h5>
            <button type="button" class="btn-close" @click="showCreateModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('clients.clientName') }}</label>
              <input v-model="newClient.name" type="text" class="form-control" :placeholder="$t('clients.clientNamePlaceholder')" />
            </div>
            <div class="mb-3" v-if="servers.length > 1">
              <label class="form-label">{{ $t('clients.server') }}</label>
              <select v-model="newClient.server_id" class="form-select">
                <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </div>
            <div class="mb-3" v-if="!isProxyClient({server_id: newClient.server_id})">
              <label class="form-label">{{ $t('clients.bandwidthLimit') }}</label>
              <input v-model.number="newClient.bandwidth_limit" type="number" class="form-control" :placeholder="$t('clients.unlimitedPlaceholder')" />
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('clients.expiryDays') }}</label>
              <input v-model.number="newClient.expiry_days" type="number" class="form-control" :placeholder="$t('clients.noExpiryPlaceholder')" />
            </div>
            <div class="mb-3 form-check d-flex align-items-center gap-1">
              <input class="form-check-input" type="checkbox" v-model="newClient.peer_visibility" id="peerVisibility" />
              <label class="form-check-label" for="peerVisibility">
                Peer visibility — allow user's devices to see each other's VPN IPs
              </label>
              <HelpTooltip :text="$t('help.peerVisibility')" />
            </div>
            <div class="alert alert-danger" v-if="createError">{{ createError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showCreateModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="createClient" :disabled="creating">
              {{ creating ? $t('common.creating') : $t('common.create') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showCreateModal"></div>

    <!-- Config Modal -->
    <div class="modal fade" :class="{ show: showConfigModal }" :style="{ display: showConfigModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              {{ $t('clients.configTitle') }}: {{ configClient?.name }}
              <span v-if="isProxyConfig" class="badge bg-warning text-dark ms-2 fw-normal">{{ proxyConfig?.protocol?.toUpperCase() }}</span>
            </h5>
            <button type="button" class="btn-close" @click="showConfigModal = false"></button>
          </div>
          <div class="modal-body">

            <!-- Proxy client config -->
            <template v-if="isProxyConfig">
              <!-- Info hint -->
              <div class="alert alert-info py-2 small mb-3">
                <i class="mdi mdi-web me-1"></i>{{ $t('clients.proxyConnectHint') }}
              </div>

              <!-- URI copy box -->
              <div class="mb-3">
                <label class="form-label small fw-semibold">{{ $t('clients.proxyUriLabel') }}</label>
                <div class="input-group">
                  <input
                    type="text"
                    class="form-control form-control-sm font-monospace"
                    :value="proxyConfig?.uri"
                    readonly
                    @click="$event.target.select()"
                  />
                  <button class="btn btn-outline-secondary btn-sm" @click="copyUri">{{ $t('clients.copyUri') }}</button>
                </div>
              </div>

              <!-- QR Code -->
              <div v-if="qrUrl" class="text-center mb-3">
                <img :src="qrUrl" alt="QR Code" class="img-fluid" style="max-width: 220px" />
                <div class="text-muted small mt-1">{{ $t('clients.qrHint') }}</div>
              </div>

              <!-- Config file preview (collapsed) -->
              <details class="mt-2">
                <summary class="text-muted small" style="cursor:pointer">{{ $t('clients.proxyProtocolLabel') }}: {{ proxyConfig?.protocol }} — {{ $t('clients.downloadProxyConf') }}</summary>
                <pre class="code-block mt-2" style="max-height:200px;overflow-y:auto;font-size:0.78em">{{ proxyConfig?.config_text }}</pre>
              </details>
            </template>

            <!-- VPN client config (WireGuard / AmneziaWG) -->
            <template v-else>
              <pre class="code-block">{{ clientConfig }}</pre>
              <div class="row text-center mt-3" v-if="qrUrl || qrAmneziaVpnUrl">
                <div class="col" v-if="qrUrl">
                  <img :src="qrUrl" alt="QR" class="img-fluid" style="max-width: 220px" />
                  <div class="text-muted small mt-1">
                    <strong>WireGuard / AmneziaWG</strong>
                    <div style="font-size:0.78em">для приложений WireGuard или AmneziaWG (lite)</div>
                  </div>
                </div>
                <div class="col" v-if="qrAmneziaVpnUrl">
                  <img :src="qrAmneziaVpnUrl" alt="QR" class="img-fluid" style="max-width: 220px" />
                  <div class="text-muted small mt-1">
                    <strong>AmneziaVPN</strong>
                    <div style="font-size:0.78em">для основного приложения AmneziaVPN (Scan QR)</div>
                  </div>
                </div>
              </div>
            </template>

          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showConfigModal = false">{{ $t('common.close') }}</button>
            <button type="button" class="btn btn-primary" @click="downloadConfig">
              {{ isProxyConfig ? $t('clients.downloadProxyConf') + ' (.' + (proxyConfig?.protocol === 'hysteria2' ? 'yaml' : 'json') + ')' : $t('clients.downloadConf') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showConfigModal"></div>

    <!-- Edit Modal -->
    <div class="modal fade" :class="{ show: showEditModal }" :style="{ display: showEditModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('clients.editTitle') }}: {{ editingClient?.name }}</h5>
            <button type="button" class="btn-close" @click="showEditModal = false"></button>
          </div>
          <div class="modal-body">
            <template v-if="!isProxyClient(editingClient)">
            <div class="mb-3">
              <label class="form-label">{{ $t('clients.bandwidthLabel') }}</label>
              <div class="d-flex flex-wrap gap-1 mb-2">
                <button
                  v-for="bw in [0, 10, 20, 30, 50, 100]"
                  :key="bw"
                  class="btn btn-sm"
                  :class="editForm.bandwidth === bw ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="editForm.bandwidth = bw"
                >
                  {{ bw === 0 ? '∞' : bw + ' Mbps' }}
                </button>
              </div>
              <input
                v-model.number="editForm.bandwidth"
                type="number"
                class="form-control form-control-sm"
                min="0"
                :placeholder="$t('clients.customMbps')"
              />
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('clients.trafficLimitLabel') }}</label>
              <div class="d-flex flex-wrap gap-1 mb-2">
                <button
                  v-for="tl in [0, 512, 1024, 3072, 5120, 10240, 51200]"
                  :key="tl"
                  class="btn btn-sm"
                  :class="editForm.trafficLimit === tl ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="editForm.trafficLimit = tl"
                >
                  {{ tl === 0 ? '∞' : formatMB(tl) }}
                </button>
              </div>
              <input
                v-model.number="editForm.trafficLimit"
                type="number"
                class="form-control form-control-sm"
                min="0"
                :placeholder="$t('clients.customMB')"
              />
            </div>
            </template>
            <div class="mb-3">
              <label class="form-label">{{ $t('clients.expiryLabel') }}</label>
              <div class="d-flex flex-wrap gap-1 mb-2">
                <button
                  class="btn btn-sm"
                  :class="editForm.expiryDays === null ? 'btn-secondary' : 'btn-outline-secondary'"
                  @click="editForm.expiryDays = null"
                >
                  {{ $t('clients.keep') }}
                </button>
                <button
                  v-for="d in [0, 1, 3, 7, 15, 30, 90]"
                  :key="d"
                  class="btn btn-sm"
                  :class="editForm.expiryDays === d ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="editForm.expiryDays = d"
                >
                  {{ d === 0 ? '∞' : d + 'd' }}
                </button>
              </div>
              <input
                v-model.number="editForm.expiryDays"
                type="number"
                class="form-control form-control-sm"
                min="0"
                :placeholder="$t('clients.customDays')"
              />
            </div>
            <div class="mb-3">
              <button class="btn btn-outline-warning btn-sm" @click="resetTraffic">
                <i class="mdi mdi-refresh me-1"></i>{{ $t('clients.resetTraffic') }}
              </button>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showEditModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="saveEdit">{{ $t('clients.saveChanges') }}</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showEditModal"></div>

    <!-- Mobile Detail Sheet -->
    <MobileDetailSheet
      v-model="showDetailSheet"
      :title="detailClient?.name || ''"
      :subtitle="detailClient ? getServerName(detailClient.server_id) : ''"
    >
      <template #badge>
        <span v-if="detailClient" class="badge ms-2" :class="detailClient.enabled ? 'badge-online' : 'badge-offline'">
          {{ detailClient.enabled ? $t('common.enabled') : $t('common.disabled') }}
        </span>
      </template>

      <template v-if="detailClient">
        <!-- General info -->
        <div class="vxy-detail-row">
          <span class="vxy-detail-label">{{ $t('clients.server') }}</span>
          <span class="vxy-detail-value">{{ getServerName(detailClient.server_id) }}</span>
        </div>
        <div class="vxy-detail-row">
          <span class="vxy-detail-label">{{ $t('dashboard.ip') }} / Protocol</span>
          <span class="vxy-detail-value">
            <span v-if="isProxyClient(detailClient)" class="badge badge-soft-warning">{{ getServerProtocol(detailClient.server_id) }}</span>
            <code v-else>{{ detailClient.ipv4 || '—' }}</code>
          </span>
        </div>

        <!-- WireGuard-specific limits -->
        <template v-if="!isProxyClient(detailClient)">
          <div class="vxy-detail-row">
            <span class="vxy-detail-label">{{ $t('dashboard.bandwidth') }}</span>
            <span class="vxy-detail-value">{{ detailClient.bandwidth_limit ? detailClient.bandwidth_limit + ' Mbps' : '∞' }}</span>
          </div>
          <div class="vxy-detail-row">
            <span class="vxy-detail-label">{{ $t('dashboard.traffic') }}</span>
            <span class="vxy-detail-value">
              {{ formatBytes((detailClient.traffic_used_rx || 0) + (detailClient.traffic_used_tx || 0)) }}
              <span v-if="detailClient.traffic_limit_mb" class="text-muted"> / {{ formatMB(detailClient.traffic_limit_mb) }}</span>
            </span>
          </div>
          <div v-if="detailClient.traffic_limit_mb" class="px-1 pb-1">
            <div class="progress traffic-progress">
              <div class="progress-bar" :class="getTrafficColor(detailClient)" :style="{ width: getTrafficPercent(detailClient) + '%' }"></div>
            </div>
          </div>
        </template>
        <!-- Proxy clients: no WG-level traffic/bandwidth tracking -->
        <template v-else>
          <div class="px-1 pb-1 mt-1">
            <small class="text-muted fst-italic">{{ $t('clients.proxyNoTrafficNote') }}</small>
          </div>
        </template>

        <!-- Expiry -->
        <div class="vxy-detail-row">
          <span class="vxy-detail-label">{{ $t('clients.expiry') }}</span>
          <span class="vxy-detail-value">
            <span v-if="detailClient.expiry_date" :class="isExpiringSoon(detailClient) ? 'text-danger fw-semibold' : ''">
              {{ formatDate(detailClient.expiry_date) }}
            </span>
            <span v-else class="text-muted">∞</span>
          </span>
        </div>
      </template>

      <template #footer>
        <div class="d-flex gap-2 w-100">
          <button class="btn btn-outline-secondary btn-sm flex-fill" @click="editClient(detailClient); showDetailSheet = false">
            <i class="mdi mdi-pencil-outline me-1"></i>{{ $t('common.edit') }}
          </button>
          <button class="btn btn-outline-danger btn-sm flex-fill" @click="confirmDelete(detailClient); showDetailSheet = false">
            <i class="mdi mdi-trash-can-outline me-1"></i>{{ $t('common.delete') }}
          </button>
        </div>
      </template>
    </MobileDetailSheet>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useClientsStore } from '../stores/clients'
import { clientsApi, serversApi } from '../api'
import { formatBytes, formatMB, formatDate } from '../utils'
import MobileDetailSheet from '../components/MobileDetailSheet.vue'

const { t } = useI18n()
const store = useClientsStore()
const successMsg = ref(null)
const errorMsg = ref(null)
const search = ref('')
const filterStatus = ref('')
const filterServer = ref('')
const servers = ref([])

// Pagination
const pageSize = 50
const currentPage = ref(1)

// Sorting
const sortKey = ref('')
const sortDir = ref('asc')  // 'asc' or 'desc'

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? ' \u25B2' : ' \u25BC'
}

// Bulk selection
const selectedIds = ref(new Set())
const bulkLoading = ref(false)

// Create modal
const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref('')
const newClient = ref({ name: '', server_id: null, bandwidth_limit: 0, expiry_days: 0, peer_visibility: false })

// Config modal
const showConfigModal = ref(false)
const configClient = ref(null)
const clientConfig = ref('')
const qrUrl = ref(null)
const qrAmneziaVpnUrl = ref(null)
// Proxy config state
const proxyConfig = ref(null)   // full proxy API response {protocol, uri, config_text, ...}
const isProxyConfig = ref(false)

// Detail sheet (mobile)
const showDetailSheet = ref(false)
const detailClient = ref(null)
function openDetail(client) { detailClient.value = client; showDetailSheet.value = true }

// Edit modal
const showEditModal = ref(false)
const editingClient = ref(null)
const editForm = ref({ bandwidth: 0, trafficLimit: 0, expiryDays: null })
const editInitial = ref({ bandwidth: 0, trafficLimit: 0 })

function showSuccess(msg) {
  successMsg.value = msg
  setTimeout(() => successMsg.value = null, 3000)
}

function showError(msg) {
  errorMsg.value = msg
  setTimeout(() => errorMsg.value = null, 5000)
}

const filteredClients = computed(() => {
  let result = store.clients
  if (search.value) {
    const q = search.value.toLowerCase()
    result = result.filter(
      (c) => c.name.toLowerCase().includes(q) || c.ipv4?.includes(q)
    )
  }
  if (filterStatus.value === 'enabled') result = result.filter((c) => c.enabled)
  if (filterStatus.value === 'disabled') result = result.filter((c) => !c.enabled)
  if (filterStatus.value === 'online') result = result.filter((c) => isClientOnline(c))
  if (filterStatus.value === 'offline') result = result.filter((c) => !isClientOnline(c))
  if (filterServer.value) result = result.filter((c) => c.server_id === Number(filterServer.value))

  // Sort
  if (sortKey.value) {
    const dir = sortDir.value === 'asc' ? 1 : -1
    result = [...result].sort((a, b) => {
      let va, vb
      switch (sortKey.value) {
        case 'name':
          va = (a.name || '').toLowerCase(); vb = (b.name || '').toLowerCase()
          return va < vb ? -dir : va > vb ? dir : 0
        case 'server':
          va = getServerName(a.server_id).toLowerCase(); vb = getServerName(b.server_id).toLowerCase()
          return va < vb ? -dir : va > vb ? dir : 0
        case 'ip':
          va = a.ipv4 || ''; vb = b.ipv4 || ''
          return va.localeCompare(vb, undefined, { numeric: true }) * dir
        case 'status':
          va = a.enabled ? 1 : 0; vb = b.enabled ? 1 : 0
          return (va - vb) * dir
        case 'traffic':
          va = (a.traffic_used_rx || 0) + (a.traffic_used_tx || 0)
          vb = (b.traffic_used_rx || 0) + (b.traffic_used_tx || 0)
          return (va - vb) * dir
        case 'bandwidth':
          va = a.bandwidth_limit || 0; vb = b.bandwidth_limit || 0
          return (va - vb) * dir
        case 'expiry':
          va = a.expiry_date ? new Date(a.expiry_date).getTime() : Infinity
          vb = b.expiry_date ? new Date(b.expiry_date).getTime() : Infinity
          return (va - vb) * dir
        default: return 0
      }
    })
  }
  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredClients.value.length / pageSize)))
const pagedClients = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredClients.value.slice(start, start + pageSize)
})

const allPageSelected = computed(() =>
  pagedClients.value.length > 0 && pagedClients.value.every((c) => selectedIds.value.has(c.id))
)

// Reset page when filters or sort change
watch([search, filterStatus, filterServer, sortKey, sortDir], () => { currentPage.value = 1 })

function toggleSelect(id) {
  const s = new Set(selectedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedIds.value = s
}

function toggleSelectAll() {
  if (allPageSelected.value) {
    const s = new Set(selectedIds.value)
    pagedClients.value.forEach((c) => s.delete(c.id))
    selectedIds.value = s
  } else {
    const s = new Set(selectedIds.value)
    pagedClients.value.forEach((c) => s.add(c.id))
    selectedIds.value = s
  }
}

async function bulkEnable() {
  bulkLoading.value = true
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map((id) => store.toggleClient(id, true)))
    await store.fetchClients()
    selectedIds.value = new Set()
    showSuccess(`Enabled ${ids.length} client(s)`)
  } catch (err) {
    showError('Bulk enable error: ' + (err.response?.data?.detail || err.message))
  } finally {
    bulkLoading.value = false
  }
}

async function bulkDisable() {
  bulkLoading.value = true
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map((id) => store.toggleClient(id, false)))
    await store.fetchClients()
    selectedIds.value = new Set()
    showSuccess(`Disabled ${ids.length} client(s)`)
  } catch (err) {
    showError('Bulk disable error: ' + (err.response?.data?.detail || err.message))
  } finally {
    bulkLoading.value = false
  }
}

async function bulkDelete() {
  if (!confirm(`Delete ${selectedIds.value.size} selected client(s)? This cannot be undone.`)) return
  bulkLoading.value = true
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map((id) => store.deleteClient(id)))
    await store.fetchClients()
    selectedIds.value = new Set()
    showSuccess(`${ids.length} client(s) deleted`)
  } catch (err) {
    showError('Bulk delete error: ' + (err.response?.data?.detail || err.message))
  } finally {
    bulkLoading.value = false
  }
}

function getServerName(id) {
  return servers.value.find((s) => s.id === id)?.name || '-'
}

function getTrafficPercent(client) {
  if (!client.traffic_limit_mb) return 0
  const used = (client.traffic_used_rx || 0) + (client.traffic_used_tx || 0)
  const limitBytes = client.traffic_limit_mb * 1024 * 1024
  return Math.min(100, (used / limitBytes) * 100)
}

function getTrafficColor(client) {
  const pct = getTrafficPercent(client)
  if (pct > 90) return 'bg-danger'
  if (pct > 70) return 'bg-warning'
  return 'bg-success'
}

function isExpiringSoon(client) {
  if (!client.expiry_date) return false
  const diff = new Date(client.expiry_date) - new Date()
  return diff < 7 * 24 * 60 * 60 * 1000
}

function isClientOnline(client) {
  if (!client.last_handshake) return false
  const diff = Date.now() - new Date(client.last_handshake).getTime()
  return diff < 3 * 60 * 1000  // 3 minutes
}

function formatDateShort(d) {
  if (!d) return '—'
  const dt = new Date(d)
  return dt.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function lastSeenText(client) {
  if (!client.last_handshake) return t('clients.neverSeen') || 'Never connected'
  const diff = Date.now() - new Date(client.last_handshake).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('clients.justNow') || 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return formatDateShort(client.last_handshake)
}

async function toggleClient(client) {
  try {
    await store.toggleClient(client.id, !client.enabled)
    showSuccess(t('clients.clientToggled', { name: client.name }) || `Client "${client.name}" ${!client.enabled ? 'enabled' : 'disabled'}`)
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function createClient() {
  creating.value = true
  createError.value = ''
  try {
    await store.createClient(newClient.value)
    showCreateModal.value = false
    newClient.value = { name: '', server_id: servers.value[0]?.id, bandwidth_limit: 0, expiry_days: 0, peer_visibility: false }
    await store.fetchClients()
  } catch (err) {
    createError.value = err.response?.data?.detail || err.message
  } finally {
    creating.value = false
  }
}

function getServerProtocol(serverId) {
  const srv = servers.value.find(s => s.id === serverId)
  const t = srv?.server_type || ''
  if (t === 'hysteria2') return 'Hysteria2'
  if (t === 'tuic') return 'TUIC'
  if (t === 'amneziawg') return 'AmneziaWG'
  return 'WireGuard'
}

function isProxyClient(client) {
  if (!client) return false
  const srv = servers.value.find(s => s.id === client.server_id)
  return srv?.server_category === 'proxy' || srv?.server_type === 'hysteria2' || srv?.server_type === 'tuic'
}

async function showConfig(client) {
  configClient.value = client
  proxyConfig.value = null
  isProxyConfig.value = false
  qrUrl.value = null
  qrAmneziaVpnUrl.value = null
  try {
    const { data } = await clientsApi.getConfig(client.id)

    if (data.category === 'proxy') {
      isProxyConfig.value = true
      proxyConfig.value = data
    } else {
      clientConfig.value = data.config || data
    }
    showConfigModal.value = true

    // Plain wg-quick QR — works for WireGuard, AmneziaWG (lite app), and
    // AmneziaVPN's "Import as WireGuard config" flow.
    try {
      const qrRes = await clientsApi.getQR(client.id)
      qrUrl.value = URL.createObjectURL(qrRes.data)
    } catch {
      qrUrl.value = null
    }

    // Second QR (vpn:// share URL) for AmneziaVPN's QR-scan flow — only
    // makes sense for AmneziaWG servers.
    if (data.protocol === 'amneziawg') {
      try {
        const r = await clientsApi.getQR(client.id, 'amneziavpn')
        qrAmneziaVpnUrl.value = URL.createObjectURL(r.data)
      } catch {
        qrAmneziaVpnUrl.value = null
      }
    }
  } catch (err) {
    showError('Error getting config: ' + (err.response?.data?.detail || err.message))
  }
}

function downloadConfig() {
  if (isProxyConfig.value) {
    const text = proxyConfig.value?.config_text || ''
    const ext = proxyConfig.value?.protocol === 'hysteria2' ? 'yaml' : 'json'
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configClient.value.name}.${ext}`
    a.click()
    URL.revokeObjectURL(url)
  } else {
    const blob = new Blob([clientConfig.value], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configClient.value.name}.conf`
    a.click()
    URL.revokeObjectURL(url)
  }
}

async function copyUri() {
  const uri = proxyConfig.value?.uri
  if (!uri) return
  try {
    await navigator.clipboard.writeText(uri)
    showSuccess(t('clients.uriCopied') || 'URI copied!')
  } catch {
    // Fallback: select the input instead
    const inp = document.querySelector('.modal.show input[readonly]')
    if (inp) { inp.select(); document.execCommand('copy') }
  }
}

function editClient(client) {
  editingClient.value = client
  editForm.value = {
    bandwidth: client.bandwidth_limit || 0,
    trafficLimit: client.traffic_limit_mb || 0,
    expiryDays: null,
  }
  editInitial.value = {
    bandwidth: client.bandwidth_limit || 0,
    trafficLimit: client.traffic_limit_mb || 0,
  }
  showEditModal.value = true
}

async function saveEdit() {
  const client = editingClient.value
  try {
    const _isProxy = isProxyClient(client)
    // Only send changed values; bandwidth/traffic not supported for proxy clients
    if (!_isProxy && editForm.value.bandwidth !== editInitial.value.bandwidth) {
      await store.setBandwidth(client.id, editForm.value.bandwidth)
    }
    if (!_isProxy && editForm.value.trafficLimit !== editInitial.value.trafficLimit) {
      await store.setTrafficLimit(client.id, editForm.value.trafficLimit)
    }
    // Only change expiry if user explicitly selected a value
    if (editForm.value.expiryDays !== null) {
      await store.setExpiry(client.id, editForm.value.expiryDays)
    }
    showEditModal.value = false
    await store.fetchClients()
    showSuccess(t('clients.changesSaved') || `Changes saved for "${client.name}"`)
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function resetTraffic() {
  if (!editingClient.value) return
  try {
    await store.resetTraffic(editingClient.value.id)
    showSuccess(t('clients.trafficReset'))
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function confirmDelete(client) {
  if (!confirm(t('clients.deleteConfirm', { name: client.name }))) return
  try {
    await store.deleteClient(client.id)
    showSuccess(t('clients.clientDeleted') || `Client "${client.name}" deleted`)
  } catch (err) {
    showError('Error: ' + (err.response?.data?.detail || err.message))
  }
}

onMounted(async () => {
  await Promise.all([
    store.fetchClients(),
    serversApi.getAll().then((res) => {
      const sData = res.data
      const list = (sData && sData.items) ? sData.items : (Array.isArray(sData) ? sData : [])
      servers.value = list
      if (!newClient.value.server_id && list.length) {
        newClient.value.server_id = list[0].id
      }
    }),
  ])
})
</script>

<style scoped>
.filter-input { min-width: 160px; }
.filter-select { min-width: 110px; }
.filter-select-wide { min-width: 140px; }

/* Sortable table headers */
.sortable-th {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition: color .15s;
}
.sortable-th:hover { color: var(--vxy-primary); }
.sort-arrow {
  font-size: .65em;
  margin-left: .2em;
  opacity: .7;
}

/* Client name: prevent long names from breaking layout */
.client-name {
  display: inline-block;
  max-width: 22ch;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

/* Online/offline indicator dot */
.client-online-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  vertical-align: middle;
}
.client-online-dot.online {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, .6);
  animation: pulse-green 2s ease-in-out infinite;
}
.client-online-dot.offline {
  background: #64748b;
}
@keyframes pulse-green {
  0%, 100% { box-shadow: 0 0 4px rgba(34, 197, 94, .4); }
  50% { box-shadow: 0 0 10px rgba(34, 197, 94, .8); }
}

.client-meta-line {
  margin-top: 2px;
  line-height: 1.3;
}
.client-meta-line small {
  font-size: .7rem;
}

@media (max-width: 575.98px) {
  .filter-input,
  .filter-select,
  .filter-select-wide { min-width: 0; width: 100%; }

  /* ── Prevent the wrapper from enabling horizontal scroll ── */
  .clients-table-wrap { overflow: hidden !important; }

  /* ── Transform table into flex card-rows ───────────────── */
  .clients-table           { display: block; width: 100%; }
  .clients-table thead     { display: none; }
  .clients-table tbody     { display: block; }

  .clients-table tr {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--vxy-border);
  }
  .clients-table tr:last-child { border-bottom: none; }
  .clients-table tr.table-active { background: var(--vxy-hover-bg, rgba(0,0,0,.04)); }

  /* Hide all td by default, then selectively show */
  .clients-table td { padding: 0; border: none; display: none; }

  /* ① Checkbox */
  .clients-table td:nth-child(1) {
    display: flex;
    align-items: center;
    flex: 0 0 auto;
  }
  /* ② Name */
  .clients-table td:nth-child(2) {
    display: block;
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
  }
  /* ⑨ Actions (last child) */
  .clients-table td:last-child {
    display: block;
    flex: 0 0 auto;
  }

  /* Name text: truncate at full cell width */
  .client-name-cell .client-name {
    max-width: 100%;
    display: block;
  }

  /* Empty-state row: full width, override flex */
  .clients-table .clients-empty-row          { display: block !important; }
  .clients-table .clients-empty-row td       { display: block !important; text-align: center; padding: 1.5rem 1rem !important; }

  /* ── Mobile action buttons: compact (override global 44px) ─ */
  .client-actions-mobile .btn {
    min-height: 32px !important;
    padding: 0.2rem 0.4rem !important;
    line-height: 1.2;
    font-size: 0.82rem;
  }
}

/* Bulk-actions bar — theme-aware instead of Bootstrap bg-light */
.bulk-bar {
  background: var(--vxy-code-bg);
  border-color: var(--vxy-border) !important;
}

/* Selected row highlight — theme-aware, overrides Bootstrap table-active */
.clients-table tr.table-active,
.clients-table tr.table-active td {
  background-color: var(--vxy-selected-bg, var(--vxy-hover-bg)) !important;
  --bs-table-active-bg: var(--vxy-selected-bg, var(--vxy-hover-bg));
  --bs-table-bg: var(--vxy-selected-bg, var(--vxy-hover-bg));
}
</style>
