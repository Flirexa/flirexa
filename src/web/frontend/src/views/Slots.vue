<template>
  <div class="slots-page">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h2 class="mb-1">{{ $t('slots.title') || 'Device Slots' }}</h2>
        <p class="text-muted small mb-0">
          {{ $t('slots.subtitle') ||
            "Each row is one customer device that spans every customer-visible region. The active region is the one currently accepting handshakes; toggling happens from the customer's portal." }}
        </p>
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-outline-secondary btn-sm" @click="loadSlots" :disabled="loading">
          <i class="mdi mdi-refresh me-1"></i>
          {{ loading ? ($t('common.loading') || 'Loading…') : ($t('common.refresh') || 'Refresh') }}
        </button>
      </div>
    </div>

    <div v-if="!loading && !slots.length" class="card">
      <div class="card-body text-center text-muted py-5">
        <i class="mdi mdi-cellphone-link" style="font-size:48px;opacity:0.4"></i>
        <h5 class="mt-3">{{ $t('slots.empty') || 'No device slots yet' }}</h5>
        <p class="small mb-0">
          {{ $t('slots.emptyHint') ||
            "Slots are created when a portal customer adds a device from the Devices page. Legacy single-server peers (from the old Quick Action flow) still show up in the Clients tab." }}
        </p>
      </div>
    </div>

    <div v-else class="card">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover mb-0 align-middle">
            <thead>
              <tr>
                <th>{{ $t('slots.colDevice') || 'Device' }}</th>
                <th>{{ $t('slots.colCustomer') || 'Customer' }}</th>
                <th>{{ $t('slots.colRegions') || 'Regions' }}</th>
                <th>{{ $t('slots.colActive') || 'Active' }}</th>
                <th>{{ $t('slots.colTraffic') || 'Traffic' }}</th>
                <th>{{ $t('slots.colCreated') || 'Created' }}</th>
                <th class="text-end">{{ $t('common.actions') || '' }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="slot in slots" :key="slot.id">
                <tr @click="toggleExpand(slot.id)" style="cursor:pointer">
                  <td>
                    <strong>{{ slot.label }}</strong>
                    <i class="mdi ms-1" :class="expanded[slot.id] ? 'mdi-chevron-down' : 'mdi-chevron-right'"></i>
                  </td>
                  <td>
                    <span v-if="slot.client_user.email">{{ slot.client_user.email }}</span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <span class="badge bg-light text-dark">{{ slot.totals.regions }}</span>
                  </td>
                  <td>
                    <span v-if="slot.active_server_name" class="badge bg-success-subtle text-success">
                      <i class="mdi mdi-circle text-success me-1" style="font-size:8px"></i>
                      {{ slot.active_server_name }}
                    </span>
                    <span v-else class="text-muted small">none</span>
                  </td>
                  <td>
                    <span style="font-family:var(--bs-font-monospace);font-size:12px">
                      {{ humanBytes(slot.totals.traffic_total_bytes) }}
                    </span>
                  </td>
                  <td>
                    <span class="text-muted small">{{ formatDate(slot.created_at) }}</span>
                  </td>
                  <td class="text-end" @click.stop>
                    <button class="btn btn-sm btn-link p-0" @click="toggleExpand(slot.id)">
                      {{ expanded[slot.id] ? ($t('common.collapse') || 'Hide') : ($t('common.expand') || 'Details') }}
                    </button>
                  </td>
                </tr>
                <tr v-if="expanded[slot.id]" class="slot-detail-row">
                  <td colspan="7" class="bg-light">
                    <div class="p-3">
                      <h6 class="mb-3">{{ $t('slots.peersTitle') || 'Regional peers' }}</h6>
                      <table class="table table-sm mb-2">
                        <thead>
                          <tr>
                            <th>{{ $t('slots.peerServer') || 'Server' }}</th>
                            <th>{{ $t('slots.peerIp') || 'IPv4' }}</th>
                            <th>{{ $t('slots.peerEnabled') || 'Enabled' }}</th>
                            <th>{{ $t('slots.peerHandshake') || 'Last handshake' }}</th>
                            <th>{{ $t('slots.peerRx') || 'RX' }}</th>
                            <th>{{ $t('slots.peerTx') || 'TX' }}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="p in slot.peers" :key="p.client_id">
                            <td>
                              <strong v-if="p.is_active" class="text-success">{{ p.server_display || p.server_name }}</strong>
                              <span v-else>{{ p.server_display || p.server_name }}</span>
                              <span v-if="p.is_active" class="badge bg-success ms-2" style="font-size:10px">ACTIVE</span>
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ p.ipv4 || '—' }}
                            </td>
                            <td>
                              <span v-if="p.enabled" class="badge bg-success-subtle text-success">on</span>
                              <span v-else class="badge bg-secondary-subtle text-secondary">off</span>
                            </td>
                            <td class="small text-muted">
                              {{ p.last_handshake ? relativeTime(p.last_handshake) : '—' }}
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ humanBytes(p.traffic_used_rx) }}
                            </td>
                            <td style="font-family:var(--bs-font-monospace);font-size:12px">
                              {{ humanBytes(p.traffic_used_tx) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                      <div class="d-flex gap-3 text-muted small">
                        <div v-if="slot.last_switched_at">
                          {{ $t('slots.lastSwitched') || 'Last region switch' }}:
                          <strong>{{ relativeTime(slot.last_switched_at) }}</strong>
                        </div>
                        <div>
                          {{ $t('slots.totalRx') || 'Total RX' }}:
                          <strong>{{ humanBytes(slot.totals.traffic_rx_bytes) }}</strong>
                        </div>
                        <div>
                          {{ $t('slots.totalTx') || 'Total TX' }}:
                          <strong>{{ humanBytes(slot.totals.traffic_tx_bytes) }}</strong>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { clientsApi } from '../api'

export default {
  name: 'Slots',
  data() {
    return {
      slots: [],
      loading: false,
      expanded: {},
    }
  },
  mounted() {
    this.loadSlots()
  },
  methods: {
    async loadSlots() {
      this.loading = true
      try {
        const r = await clientsApi.listSlots()
        this.slots = r.data || []
      } catch (e) {
        console.error('Failed to load slots', e)
      } finally {
        this.loading = false
      }
    },
    toggleExpand(slotId) {
      // Vue 3 reactive object — re-assign the dict so new keys become
      // reactive too (Vue 2's $set isn't available here).
      this.expanded = { ...this.expanded, [slotId]: !this.expanded[slotId] }
    },
    humanBytes(n) {
      if (!n || n < 0) return '0 B'
      const units = ['B', 'KB', 'MB', 'GB', 'TB']
      let i = 0
      let v = n
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
      return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`
    },
    formatDate(iso) {
      if (!iso) return '—'
      try { return new Date(iso).toLocaleString() } catch { return iso }
    },
    relativeTime(iso) {
      if (!iso) return '—'
      try {
        const diff = (Date.now() - new Date(iso).getTime()) / 1000
        if (diff < 60) return `${Math.floor(diff)}s ago`
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
        return `${Math.floor(diff / 86400)}d ago`
      } catch { return iso }
    },
  },
}
</script>

<style scoped>
.slots-page {
  padding: 1rem;
}
.slot-detail-row td {
  border-top: none;
}
</style>
