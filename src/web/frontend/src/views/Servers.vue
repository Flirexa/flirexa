<template>
  <div class="servers-page">
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-4 mobile-toolbar">
      <h6 class="mb-0">{{ $t('servers.count', { count: store.servers.length }) }}</h6>
      <div class="d-flex gap-2 mobile-toolbar__actions">
        <button class="btn btn-outline-primary btn-sm" @click="showDiscoverModal = true">{{ $t('servers.discover') }}</button>
        <button class="btn btn-primary btn-sm" @click="showAddModal = true">{{ $t('servers.addServer') }}</button>
      </div>
    </div>

    <!-- ── Unreachable-agent banner ─────────────────────────────
         Surfaces servers whose agent circuit-breaker is open. The breaker
         opens after 3 consecutive ConnectTimeouts, and while it's open the
         backend short-circuits agent calls — which means panel pages stay
         fast, but the user has no idea WHY their server "looks fine but
         doesn't respond". This banner makes the cause + the one-click fix
         (Switch to SSH) explicit. -->
    <div v-if="brokenAgents.length" class="agent-breaker-banner">
      <div class="agent-breaker-banner__icon"><i class="mdi mdi-alert-circle-outline"></i></div>
      <div class="agent-breaker-banner__body">
        <div class="agent-breaker-banner__title">
          {{ $tc('servers.agentBannerTitle', brokenAgents.length, { count: brokenAgents.length }) }}
        </div>
        <div class="agent-breaker-banner__text">
          {{ $t('servers.agentBannerBody', { names: brokenAgents.map(s => s.name).join(', ') }) }}
        </div>
        <ul class="agent-breaker-banner__list">
          <li v-for="bs in brokenAgents" :key="bs.id">
            <strong>{{ bs.name }}</strong>
            <span class="agent-breaker-banner__since">
              · {{ formatBreakerSince(bs.agent_breaker?.opened_seconds_ago) }}
            </span>
            <button class="btn btn-sm btn-warning ms-2"
              @click="switchAgentToSsh(bs)" :disabled="breakerActing[bs.id]">
              <i class="mdi mdi-swap-horizontal me-1"></i>{{ $t('servers.agentSwitchToSsh') || 'Switch to SSH' }}
            </button>
            <button class="btn btn-sm btn-outline-secondary ms-1"
              @click="retryAgentNow(bs)" :disabled="breakerActing[bs.id]">
              <i class="mdi mdi-refresh me-1"></i>{{ $t('servers.agentRetryNow') || 'Retry now' }}
            </button>
          </li>
        </ul>
      </div>
    </div>

    <!-- ── Server grid ──────────────────────────────────────── -->
    <div v-if="store.servers.length" class="srv-grid" @click="openMenuId = null">
      <div v-for="server in store.servers" :key="server.id" class="srv-card">

        <!-- Header: name + badges + status + menu -->
        <div class="srv-card__head">
          <div class="srv-card__identity">
            <span class="srv-card__name">{{ server.name }}</span>
            <span v-if="server.display_name" class="srv-display-name" :title="$t('servers.displayNameTitle') || 'Shown to clients'">
              <i class="mdi mdi-eye-outline me-1"></i>{{ server.display_name }}
            </span>
            <div class="srv-card__badges">
              <span v-if="server.server_type === 'amneziawg'" class="srv-proto srv-proto--awg"><i class="mdi mdi-shield-outline me-1"></i>AWG</span>
              <span v-else-if="server.server_type === 'hysteria2'" class="srv-proto srv-proto--hy2"><i class="mdi mdi-web me-1"></i>HY2</span>
              <span v-else-if="server.server_type === 'tuic'" class="srv-proto srv-proto--tuic"><i class="mdi mdi-web me-1"></i>TUIC</span>
              <span v-if="server.is_default" class="srv-proto srv-proto--default"><i class="mdi mdi-star me-1"></i>Default</span>
              <button v-if="server.agent_mode === 'agent'"
                class="srv-agent-badge"
                :class="{ 'srv-agent-badge--down': server.agent_breaker?.open }"
                @click.stop="openAgentMenu(server)"
                :title="server.agent_breaker?.open ? ($t('servers.agentUnreachable') || 'Agent unreachable') : 'Manage agent'">
                <i class="mdi mdi-robot-outline"></i>
                <span v-if="checkingStatus[server.id]" class="spinner-border spinner-border-sm" style="width:.6em;height:.6em;border-width:1.5px"></span>
                <i v-else-if="server.agent_breaker?.open" class="mdi mdi-alert-circle text-danger" style="font-size:.6em"></i>
                <i v-else-if="agentStatuses[server.id]" :class="agentStatuses[server.id].healthy ? 'mdi mdi-circle text-success' : 'mdi mdi-circle text-danger'" style="font-size:.6em"></i>
              </button>
              <span v-else-if="server.is_remote" class="srv-agent-badge">SSH</span>
            </div>
          </div>

          <div class="srv-card__head-right">
            <span class="srv-status" :class="isOnline(server) ? 'srv-status--on' : 'srv-status--off'">
              <span class="srv-status__dot"></span>
              {{ isOnline(server) ? $t('common.online') : $t('common.offline') }}
            </span>
            <!-- Three-dot dropdown -->
            <div class="srv-menu" @click.stop>
              <button class="srv-menu__btn" @click="toggleMenu(server.id)" :title="$t('common.actions') || 'Actions'">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="2.2"/><circle cx="12" cy="12" r="2.2"/><circle cx="12" cy="19" r="2.2"/>
                </svg>
              </button>
              <div v-if="openMenuId === server.id" class="srv-menu__drop">
                <button v-if="!isOnline(server)" class="srv-menu__item srv-menu__item--ok"
                  @click="menuAction(() => serverAction(server.id, 'start'))"><i class="mdi mdi-play me-1"></i>{{ $t('common.start') }}</button>
                <template v-if="isOnline(server)">
                  <button class="srv-menu__item" @click="menuAction(() => serverAction(server.id, 'restart'))"><i class="mdi mdi-restart me-1"></i>{{ $t('common.restart') }}</button>
                  <button class="srv-menu__item" @click="menuAction(() => serverAction(server.id, 'stop'))"><i class="mdi mdi-stop me-1"></i>{{ $t('common.stop') }}</button>
                </template>
                <div class="srv-menu__sep"></div>
                <button class="srv-menu__item" @click="menuAction(() => saveConfig(server.id))"><i class="mdi mdi-content-save-outline me-1"></i>{{ $t('servers.saveConfig') }}</button>
                <button class="srv-menu__item" @click="menuAction(() => backupServer(server))" :disabled="backingUp[server.id]"><i class="mdi mdi-tray-arrow-down me-1"></i>{{ $t('servers.backup') || 'Backup' }}</button>
                <button class="srv-menu__item" @click="menuAction(() => triggerRestore(server))"><i class="mdi mdi-tray-arrow-up me-1"></i>{{ $t('servers.restore') || 'Restore' }}</button>
                <div class="srv-menu__sep"></div>
                <button v-if="server.server_type !== 'amneziawg' && server.server_category !== 'proxy'"
                  class="srv-menu__item" @click="menuAction(() => toggleSplitTunnel(server))" :disabled="togglingTunnel[server.id]">
                  <i class="mdi mdi-call-split me-1"></i>Split {{ server.split_tunnel_support ? 'ON' : 'OFF' }}
                </button>
                <button v-if="!server.is_default" class="srv-menu__item"
                  @click="menuAction(() => setDefaultServer(server.id))"><i class="mdi mdi-star-outline me-1"></i>{{ $t('servers.setDefault') }}</button>
                <template v-if="server.server_category !== 'proxy' && server.agent_mode !== 'mikrotik'">
                  <button v-if="server.agent_mode === 'agent'" class="srv-menu__item"
                    @click="menuAction(() => openAgentMenu(server))"><i class="mdi mdi-robot-outline me-1"></i>{{ $t('servers.manageAgent') || 'Manage Agent' }}</button>
                  <button v-else class="srv-menu__item" @click="menuAction(() => openInstallModal(server.id))"
                    :disabled="installingAgent[server.id]"><i class="mdi mdi-robot-outline me-1"></i>{{ $t('servers.installAgent') || 'Install Agent' }}</button>
                  <button v-if="server.ssh_host" class="srv-menu__item"
                    @click="menuAction(() => openInstallProxyModal(server))"><i class="mdi mdi-web me-1"></i>{{ $t('servers.installProxy') || 'Install Proxy' }}</button>
                  <button v-if="server.ssh_host && server.server_type !== 'amneziawg'" class="srv-menu__item"
                    @click="menuAction(() => openInstallAwgModal(server))"><i class="mdi mdi-shield-lock-outline me-1"></i>{{ $t('servers.installAwg') || 'Install AmneziaWG' }}</button>
                </template>
                <div class="srv-menu__sep"></div>
                <button class="srv-menu__item" @click="menuAction(() => openRenameModal(server))"><i class="mdi mdi-pencil-outline me-1"></i>{{ $t('servers.rename') || 'Rename (display)' }}</button>
                <template v-if="server.server_category !== 'proxy'">
                  <div class="srv-menu__sep"></div>
                  <button v-if="server.agent_mode !== 'mikrotik'" class="srv-menu__item" @click="menuAction(() => openExpandPool(server))"><i class="mdi mdi-arrow-expand-horizontal me-1"></i>{{ $t('servers.expandPool') || 'Expand address pool' }}</button>
                  <button class="srv-menu__item" @click="menuAction(() => openExportKeypair(server))"><i class="mdi mdi-key-outline me-1"></i>{{ $t('servers.exportKeypair') || 'Export keypair' }}</button>
                  <button v-if="server.server_type === 'amneziawg'" class="srv-menu__item"
                    @click="menuAction(() => openEditObfuscationModal(server))">
                    <i class="mdi mdi-tune-vertical me-1"></i>{{ $t('servers.editObfuscation') || 'Edit obfuscation params' }}
                  </button>
                  <button v-if="server.agent_mode !== 'mikrotik'" class="srv-menu__item" @click="menuAction(() => openMigrateClients(server))"><i class="mdi mdi-account-switch-outline me-1"></i>{{ $t('servers.migrateClients') || 'Migrate clients' }}</button>
                </template>
                <template v-if="!server.is_default">
                  <div class="srv-menu__sep"></div>
                  <button class="srv-menu__item srv-menu__item--danger"
                    @click="menuAction(() => confirmDeleteServer(server))"><i class="mdi mdi-trash-can-outline me-1"></i>{{ server.server_category === 'proxy' ? ($t('servers.uninstallProxy') || 'Uninstall Proxy') : ($t('common.delete') || 'Delete') }}</button>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Endpoint -->
        <div class="srv-card__endpoint">
          <code>{{ server.endpoint }}</code>
        </div>

        <!-- Stats row -->
        <div class="srv-card__stats">
          <div class="srv-stat">
            <span class="srv-stat__val">{{ server.total_clients ?? 0 }}<span class="srv-stat__of">/{{ server.max_clients }}</span></span>
            <span class="srv-stat__lbl">{{ $t('servers.clientsLabel') }}</span>
          </div>
          <div v-if="server.location" class="srv-stat">
            <span class="srv-stat__val srv-stat__val--md">{{ server.location }}</span>
            <span class="srv-stat__lbl">{{ $t('servers.location') }}</span>
          </div>
          <div v-if="bwData[server.id]" class="srv-stat srv-stat--clickable" @click.stop="openBwSettings(server)" :title="$t('servers.bandwidthSettings') || 'Set bandwidth limit'">
            <span class="srv-stat__val srv-stat__val--md">
              {{ (bwData[server.id].total_rate_mbps ?? 0).toFixed(1) }}<span class="srv-stat__unit"> Mbps</span>
            </span>
            <span class="srv-stat__lbl">{{ $t('servers.bandwidth') || 'Bandwidth' }}</span>
          </div>
        </div>

        <!-- Client capacity bar -->
        <div class="srv-bar-wrap">
          <div class="srv-bar">
            <div class="srv-bar__fill" :style="{ width: clientPct(server) + '%' }"></div>
          </div>
          <span class="srv-bar__label">{{ clientPct(server) }}%</span>
        </div>

        <!-- Bandwidth bar (only when limit is set) -->
        <div v-if="bwData[server.id] && server.max_bandwidth_mbps" class="srv-bar-wrap">
          <div class="srv-bar">
            <div class="srv-bar__fill" :class="bwBarClass(server)" :style="{ width: bwBarWidth(server) + '%' }"></div>
          </div>
          <span class="srv-bar__label">{{ $t('servers.bandwidth') || 'BW' }}</span>
        </div>

        <!-- Collapsible details -->
        <details class="srv-details">
          <summary class="srv-details__toggle">
            <svg class="srv-details__chevron" xmlns="http://www.w3.org/2000/svg" width="11" height="11"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            {{ $t('servers.showDetails') || 'Details' }}
          </summary>
          <div class="srv-details__body">
            <div v-if="server.server_category !== 'proxy'" class="srv-detail-row">
              <span class="srv-detail-key">{{ $t('servers.interface') }}</span>
              <code class="srv-detail-val">{{ server.interface }}</code>
            </div>
            <div class="srv-detail-row">
              <span class="srv-detail-key">{{ $t('servers.port') }}</span>
              <code class="srv-detail-val">{{ server.listen_port }}</code>
            </div>
            <template v-if="server.server_category === 'proxy'">
              <div v-if="server.proxy_tls_mode" class="srv-detail-row">
                <span class="srv-detail-key">TLS</span>
                <code class="srv-detail-val">{{ server.proxy_tls_mode }}</code>
              </div>
              <div v-if="server.proxy_domain" class="srv-detail-row">
                <span class="srv-detail-key">Domain</span>
                <code class="srv-detail-val">{{ server.proxy_domain }}</code>
              </div>
            </template>
            <div v-if="server.ssh_host" class="srv-detail-row">
              <span class="srv-detail-key">SSH</span>
              <code class="srv-detail-val">{{ server.ssh_user }}@{{ server.ssh_host }}:{{ server.ssh_port }}</code>
            </div>
            <div v-if="bwData[server.id]?.peer_rates?.length" class="srv-consumers">
              <div class="srv-consumers__label">{{ $t('servers.topConsumers') || 'Top consumers' }}</div>
              <div v-for="peer in bwData[server.id].peer_rates.slice(0, 5)" :key="peer.public_key" class="srv-consumer">
                <span>{{ peer.client_name }}</span>
                <span class="srv-consumer__rate">↓{{ peer.rx_rate_mbps }} ↑{{ peer.tx_rate_mbps }} Mbps</span>
              </div>
            </div>
          </div>
        </details>

        <!-- Primary actions -->
        <div class="srv-card__actions">
          <button class="btn btn-primary btn-sm" @click="viewClients(server.id)">
            <i class="mdi mdi-account-group-outline me-1"></i>{{ $t('servers.viewClients') }}
          </button>
          <button v-if="server.agent_mode === 'agent'"
            class="btn btn-outline-secondary btn-sm"
            @click="checkAgentStatus(server.id, true)"
            :disabled="checkingStatus[server.id]">
            <span v-if="checkingStatus[server.id]" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="mdi mdi-power-plug-outline me-1"></i>{{ checkingStatus[server.id] ? ($t('servers.testing') || 'Testing...') : ($t('servers.testConnection') || 'Test') }}
          </button>
        </div>

        <!-- Hidden restore file input -->
        <input type="file" :ref="el => { if (el) restoreInputs[server.id] = el }"
          accept=".json" style="display:none" @change="restoreServer(server, $event)" />
      </div>
    </div>

    <!-- Empty state -->
    <div class="srv-empty" v-if="store.servers.length === 0 && !store.loading">
      <div class="srv-empty__icon"><i class="mdi mdi-server-network"></i></div>
      <h5 class="srv-empty__title">{{ $t('servers.noServers') }}</h5>
      <p class="srv-empty__desc">{{ $t('servers.noServersDesc') }}</p>
      <button class="btn btn-primary" @click="showAddModal = true">{{ $t('servers.addServer') }}</button>
    </div>

    <!-- Add Server Modal -->
    <div class="modal fade" :class="{ show: showAddModal }" :style="{ display: showAddModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('servers.addTitle') }}</h5>
            <button type="button" class="btn-close" @click="showAddModal = false"></button>
          </div>
          <div class="modal-body px-3 py-3">

            <!-- Step 1: Category -->
            <div class="mb-4">
              <label class="form-label fw-semibold mb-2">{{ $t('servers.category') }}</label>
              <div class="d-flex gap-2 align-items-stretch">
                <div class="add-card flex-fill" style="cursor:pointer"
                     :class="newServer.server_category === 'vpn' ? 'add-card--active-blue' : ''"
                     @click="selectCategory('vpn')">
                  <div class="d-flex align-items-center gap-2 mb-2">
                    <i class="mdi mdi-shield-outline"></i><strong>VPN</strong>
                  </div>
                  <ul class="mb-0 ps-3 text-muted" style="font-size:0.78em">
                    <li>{{ $t('servers.vpnFeature1') }}</li>
                    <li>{{ $t('servers.vpnFeature2') }}</li>
                  </ul>
                </div>
                <div class="add-card flex-fill" style="cursor:pointer"
                     :class="newServer.server_category === 'proxy' ? 'add-card--active-amber' : ''"
                     @click.self="selectCategory('proxy')">
                  <div class="d-flex align-items-center gap-2 mb-2">
                    <i class="mdi mdi-web"></i>
                    <strong @click="selectCategory('proxy')">Proxy</strong>
                    <HelpTooltip :text="$t('servers.protocolMatrixHint')" />
                  </div>
                  <ul class="mb-0 ps-3 text-muted" style="font-size:0.78em" @click="selectCategory('proxy')">
                    <li>{{ $t('servers.proxyFeature1') }}</li>
                    <li>{{ $t('servers.proxyFeature2') }}</li>
                  </ul>
                </div>
              </div>
            </div>

            <!-- Step 2: Protocol -->
            <div class="mb-4">
              <label class="form-label fw-semibold mb-2">{{ $t('servers.protocol') }}</label>
              <!-- VPN protocols -->
              <div v-if="newServer.server_category === 'vpn'" class="d-flex gap-2 align-items-stretch">
                <div class="add-card proto-card flex-fill"
                     :class="newServer.server_type === 'wireguard' ? 'add-card--active-blue' : ''"
                     @click="newServer.server_type = 'wireguard'; onProtocolChange()">
                  <strong class="proto-card__name">WireGuard</strong>
                  <span class="proto-badge proto-badge--blue mt-1">{{ $t('servers.wgTag') }}</span>
                  <div class="proto-card__desc">{{ $t('servers.wgDesc') }}</div>
                </div>
                <div class="add-card proto-card flex-fill"
                     :class="newServer.server_type === 'amneziawg' ? 'add-card--active-blue' : ''"
                     @click="newServer.server_type = 'amneziawg'; onProtocolChange()">
                  <div class="d-flex align-items-center gap-1">
                    <strong class="proto-card__name">AmneziaWG</strong>
                    <HelpTooltip :text="$t('help.awgType')" />
                  </div>
                  <span class="proto-badge proto-badge--cyan mt-1">{{ $t('servers.awgTag') }}</span>
                  <div class="proto-card__desc">{{ $t('servers.awgDesc') }}</div>
                </div>
              </div>
              <!-- Proxy protocols -->
              <div v-if="newServer.server_category === 'proxy'" class="d-flex gap-2 align-items-stretch">
                <div class="add-card proto-card flex-fill"
                     :class="newServer.server_type === 'hysteria2' ? 'add-card--active-amber' : ''"
                     @click="newServer.server_type = 'hysteria2'; onProtocolChange()">
                  <div class="d-flex align-items-center gap-1">
                    <strong class="proto-card__name">Hysteria 2</strong>
                    <HelpTooltip :text="$t('help.hysteria2')" />
                  </div>
                  <span class="proto-badge proto-badge--amber mt-1">{{ $t('servers.hy2Tag') }}</span>
                  <div class="proto-card__desc">{{ $t('servers.hy2Desc') }}</div>
                </div>
                <div class="add-card proto-card flex-fill"
                     :class="newServer.server_type === 'tuic' ? 'add-card--active-amber' : ''"
                     @click="newServer.server_type = 'tuic'; onProtocolChange()">
                  <div class="d-flex align-items-center gap-1">
                    <strong class="proto-card__name">TUIC</strong>
                    <HelpTooltip :text="$t('help.tuic')" />
                  </div>
                  <span class="proto-badge proto-badge--amber mt-1">{{ $t('servers.tuicTag') }}</span>
                  <div class="proto-card__desc">{{ $t('servers.tuicDesc') }}</div>
                </div>
              </div>
            </div>

            <!-- Essential fields -->
            <div class="row g-3 mb-3">
              <div class="col-12 col-sm-6">
                <label class="form-label mb-1 small fw-medium">{{ $t('common.name') }}</label>
                <input v-model="newServer.name" type="text" class="form-control"
                       :placeholder="$t('servers.serverNamePlaceholder')"
                       @input="nameAutoGenerated = false" />
              </div>
              <div class="col-12 col-sm-6">
                <label class="form-label mb-1 small fw-medium d-flex align-items-center gap-1">
                  {{ $t('servers.endpoint') }}
                  <HelpTooltip :text="$t('servers.addressHelp')" />
                </label>
                <div class="position-relative">
                  <input v-model="newServer.endpoint" type="text" class="form-control"
                         :placeholder="detectingPublicIp ? $t('servers.detectingIp') : $t('servers.addressPlaceholder')"
                         :class="endpointError ? 'is-invalid' : ''"
                         :disabled="detectingPublicIp"
                         @input="validateEndpoint" @blur="validateEndpoint" />
                  <span v-if="detectingPublicIp" class="position-absolute end-0 top-50 translate-middle-y pe-2">
                    <span class="spinner-border spinner-border-sm text-secondary" role="status"></span>
                  </span>
                </div>
                <div v-if="endpointError" class="invalid-feedback">{{ $t('servers.endpointInvalid') }}</div>
                <div v-else class="form-text">{{ $t('servers.addressHelpText') }}</div>
              </div>
            </div>
            <div class="row g-3 mb-4">
              <div class="col-6 col-sm-4" v-if="newServer.server_category === 'vpn'">
                <label class="form-label mb-1 small fw-medium">{{ $t('servers.interface') }}</label>
                <input v-model="newServer.interface" type="text" class="form-control" />
              </div>
              <div :class="newServer.server_category === 'proxy' ? 'col-6' : 'col-6 col-sm-4'">
                <label class="form-label mb-1 small fw-medium">{{ $t('servers.listenPort') }}</label>
                <input v-model.number="newServer.listen_port" type="number" class="form-control" />
              </div>
              <div :class="newServer.server_category === 'proxy' ? 'col-6' : 'col-6 col-sm-4'">
                <label class="form-label mb-1 small fw-medium">{{ $t('servers.maxClients') }}</label>
                <input v-model.number="newServer.max_clients" type="number" class="form-control" />
              </div>
            </div>

            <!-- VPN-only fields -->
            <div v-if="newServer.server_category === 'vpn'" class="mb-4">
              <div class="row g-3 mb-3">
                <div class="col-12 col-sm-6">
                  <label class="form-label mb-1 small fw-medium">{{ $t('servers.addressPool') }}</label>
                  <input v-model="newServer.address_pool_ipv4" type="text" class="form-control"
                         :placeholder="$t('servers.addressPoolPlaceholder')" />
                </div>
                <div class="col-12 col-sm-6">
                  <label class="form-label mb-1 small fw-medium">{{ $t('servers.dns') }}</label>
                  <input v-model="newServer.dns" type="text" class="form-control" />
                </div>
              </div>
              <div v-if="newServer.server_type === 'amneziawg'" class="info-pill mb-2">
                <i class="mdi mdi-shield-outline me-1"></i>{{ $t('servers.awgAutoParams') }}
              </div>
              <div v-if="newServer.server_type === 'wireguard'" class="d-flex align-items-center gap-2">
                <input class="form-check-input mt-0" type="checkbox" v-model="newServer.split_tunnel_support" id="splitTunnelNew"
                       role="switch" style="flex-shrink:0;width:2em;height:1em;cursor:pointer" />
                <label class="small mb-0" for="splitTunnelNew" style="cursor:pointer">Split tunneling</label>
                <HelpTooltip :text="$t('help.splitTunnel')" />
              </div>
              <div v-if="newServer.server_category === 'vpn'" class="d-flex align-items-center gap-2 mt-2">
                <input class="form-check-input mt-0" type="checkbox" v-model="newServer.ipv4_only" id="ipv4OnlyNew"
                       role="switch" style="flex-shrink:0;width:2em;height:1em;cursor:pointer" />
                <label class="small mb-0" for="ipv4OnlyNew" style="cursor:pointer">{{ $t('servers.ipv4OnlyLabel') || 'IPv4 only (no IPv6 in client configs)' }}</label>
                <HelpTooltip :text="$t('servers.ipv4OnlyHint') || 'Strips the IPv6 Address line from generated client configs. Useful where IPv6 isn\'t fully tunneled and could leak DNS.'" />
              </div>
            </div>

            <!-- Proxy Quick Start hint -->
            <div v-if="newServer.server_category === 'proxy'" class="quick-start mb-3">
              <span class="quick-start__icon"><i class="mdi mdi-flash"></i></span>
              <div>
                <div class="quick-start__title">{{ $t('servers.quickStart') }}</div>
                <div class="quick-start__steps">
                  {{ $t('servers.quickStep1') }} → {{ $t('servers.quickStep2') }} → {{ $t('servers.quickStep3') }}
                </div>
              </div>
            </div>

            <!-- Proxy TLS section -->
            <div v-if="newServer.server_category === 'proxy'" class="mb-4">

              <!-- TLS mode: segmented control -->
              <div class="mb-3">
                <label class="form-label mb-2 small fw-medium d-flex align-items-center gap-1">
                  {{ $t('servers.tlsMode') }}
                  <HelpTooltip :text="$t('servers.tlsModeHint')" />
                </label>
                <div class="tls-seg" role="group">
                  <button type="button" class="tls-seg__btn"
                          :class="{ 'tls-seg__btn--warn': newServer.proxy_tls_mode === 'self_signed' }"
                          @click="newServer.proxy_tls_mode = 'self_signed'">
                    <i class="mdi mdi-alert me-1"></i>{{ $t('servers.tlsLabelTest') }}
                  </button>
                  <button type="button" class="tls-seg__btn"
                          :class="{ 'tls-seg__btn--ok': newServer.proxy_tls_mode === 'acme' }"
                          @click="newServer.proxy_tls_mode = 'acme'">
                    <i class="mdi mdi-lock me-1"></i>{{ $t('servers.tlsLabelAuto') }}
                  </button>
                  <button type="button" class="tls-seg__btn"
                          :class="{ 'tls-seg__btn--ok': newServer.proxy_tls_mode === 'manual' }"
                          @click="newServer.proxy_tls_mode = 'manual'">
                    <i class="mdi mdi-shield-key-outline me-1"></i>{{ $t('servers.tlsLabelCustom') }}
                  </button>
                </div>
                <!-- Dynamic hint under control -->
                <div class="tls-hint" :class="{
                  'tls-hint--warn': newServer.proxy_tls_mode === 'self_signed',
                  'tls-hint--ok':   newServer.proxy_tls_mode !== 'self_signed'
                }">
                  <span v-if="newServer.proxy_tls_mode === 'self_signed'"><i class="mdi mdi-alert me-1"></i>{{ $t('servers.tlsOnelinerTest') }}</span>
                  <span v-if="newServer.proxy_tls_mode === 'acme'"><i class="mdi mdi-information-outline me-1"></i>{{ $t('servers.tlsOnelinerAuto') }}</span>
                  <span v-if="newServer.proxy_tls_mode === 'manual'"><i class="mdi mdi-check-circle me-1 text-success"></i>{{ $t('servers.tlsOnelinerCustom') }}</span>
                </div>
              </div>

              <!-- ACME requirements banner -->
              <div v-if="newServer.proxy_tls_mode === 'acme'" class="acme-banner mb-3">
                <div class="acme-banner__title"><i class="mdi mdi-lock me-1"></i>{{ acmeBannerTitle }}</div>
                <ul class="acme-banner__list">
                  <li v-html="acmeReqDomain"></li>
                  <li v-html="acmeReqPort80"></li>
                  <li>{{ acmeReqAutoIssue }}</li>
                </ul>
              </div>

              <!-- Domain field — required for ACME, optional otherwise -->
              <div class="mb-3">
                <label class="form-label mb-1 small fw-medium d-flex align-items-center gap-1">
                  {{ newServer.proxy_tls_mode === 'acme' ? $t('servers.proxyDomainRequired') : $t('servers.proxyDomain') }}
                  <span v-if="newServer.proxy_tls_mode === 'acme'" class="text-danger">*</span>
                  <span v-else class="text-muted" style="font-weight:400">({{ $t('common.optional') }})</span>
                  <HelpTooltip :text="$t('servers.proxyDomainHint')" />
                </label>
                <input ref="domainInputRef" v-model="newServer.proxy_domain" type="text" class="form-control"
                       placeholder="proxy.example.com"
                       :class="acmeDomainError ? 'is-invalid' : ''" />
                <div v-if="acmeDomainError" class="invalid-feedback">{{ $t('servers.acmeDomainRequired') }}</div>
              </div>

              <!-- Manual cert paths -->
              <div v-if="newServer.proxy_tls_mode === 'manual'" class="row g-3 mb-2">
                <div class="col-12 col-sm-6">
                  <label class="form-label mb-1 small fw-medium">{{ $t('servers.certPath') }}</label>
                  <input v-model="newServer.proxy_cert_path" type="text" class="form-control" placeholder="/etc/ssl/cert.pem" />
                </div>
                <div class="col-12 col-sm-6">
                  <label class="form-label mb-1 small fw-medium">{{ $t('servers.keyPath') }}</label>
                  <input v-model="newServer.proxy_key_path" type="text" class="form-control" placeholder="/etc/ssl/key.pem" />
                </div>
              </div>
            </div>

            <!-- Advanced settings: custom collapsible -->
            <div class="mb-3">
              <button type="button" class="advanced-toggle" @click="toggleAdvanced">
                <span class="d-flex align-items-center gap-1">
                  <svg class="advanced-chevron" :class="{ 'advanced-chevron--open': advancedOpen }"
                       xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                  {{ $t('servers.advancedSettings') }}
                </span>
              </button>
              <div class="advanced-body" :class="{ 'advanced-body--open': advancedOpen }">
                <div class="pt-3">

                  <!-- OBFS field (Hysteria2 only) — empty = disabled, filled = enabled -->
                  <div v-if="newServer.server_type === 'hysteria2'" class="mb-3">
                    <label class="form-label mb-1 small fw-medium d-flex align-items-center gap-1">
                      {{ $t('servers.obfsLabel') }}
                      <HelpTooltip :text="$t('servers.obfsTooltip')" />
                    </label>
                    <input v-model="newServer.proxy_obfs_password" type="text" class="form-control"
                           :placeholder="$t('servers.obfsPasswordPlaceholder')" />
                    <div class="form-text">{{ $t('servers.obfsHelp') }}</div>
                  </div>

                  <!-- AmneziaWG: reuse obfuscation params from existing server.
                       Same use case as "Reuse private key" — when migrating an
                       AWG server to a new box, paste the old box's h1-h4 (and
                       optionally jc/jmin/jmax/s1/s2) so issued client configs
                       keep handshaking. Blank fields → backend auto-generates. -->
                  <div v-if="newServer.server_type === 'amneziawg'" class="mb-3">
                    <button type="button" class="advanced-toggle" @click="reuseObfuscationOpen = !reuseObfuscationOpen">
                      <span class="d-flex align-items-center gap-1">
                        <svg class="advanced-chevron" :class="{ 'advanced-chevron--open': reuseObfuscationOpen }"
                             xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                             fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                        {{ $t('servers.reuseObfuscation') || 'Reuse obfuscation params (for migration)' }}
                      </span>
                    </button>
                    <div class="advanced-body" :class="{ 'advanced-body--open': reuseObfuscationOpen }">
                      <div class="pt-2 small text-muted mb-2">
                        {{ $t('servers.reuseObfuscationHint') || "Leave blank to auto-generate. Paste values from the old AWG server here to keep existing client configs working after migration — they must match exactly to handshake." }}
                      </div>
                      <!-- Pick-source dropdown — when migrating with both old+new
                           rows in the panel, single click instead of paste. -->
                      <div v-if="addAwgSourceCandidates.length > 0"
                           class="mb-3 p-2 rounded" style="background:rgba(34,197,94,.06);border:1px solid rgba(34,197,94,.22)">
                        <div class="d-flex align-items-center gap-2 mb-2">
                          <i class="mdi mdi-source-branch"></i>
                          <span class="small fw-bold">{{ $t('servers.copyFromAnotherAwg') || 'Copy from another AWG server in this panel' }}</span>
                        </div>
                        <div class="d-flex gap-2">
                          <select v-model="addCopyFromServerId" class="form-select form-select-sm" style="flex:1">
                            <option :value="null" disabled>{{ $t('servers.selectSourceServer') || 'Select source server…' }}</option>
                            <option v-for="s in addAwgSourceCandidates" :key="s.id" :value="s.id">
                              {{ s.name }}<template v-if="s.endpoint"> · {{ s.endpoint }}</template>
                            </option>
                          </select>
                          <button type="button" class="btn btn-sm btn-success" :disabled="!addCopyFromServerId" @click="copyObfuscationFromServerForAdd">
                            <i class="mdi mdi-content-copy me-1"></i>{{ $t('servers.copy') || 'Copy' }}
                          </button>
                        </div>
                        <div v-if="addCopyFromMessage" class="small mt-2"
                             :class="addCopyFromOk ? 'text-success' : 'text-danger'">
                          <i class="mdi me-1" :class="addCopyFromOk ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"></i>
                          {{ addCopyFromMessage }}
                        </div>
                      </div>
                      <!-- Smart-fill: paste working client config, we extract values -->
                      <div class="mb-3 p-2 rounded" style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.18)">
                        <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none d-flex align-items-center gap-1"
                                @click="addDetectOpen = !addDetectOpen">
                          <svg class="advanced-chevron" :class="{ 'advanced-chevron--open': addDetectOpen }"
                               xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
                               fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                          <i class="mdi mdi-magnify-scan"></i>
                          {{ $t('servers.detectFromClientConfig') || 'Auto-fill from a working client config' }}
                        </button>
                        <div v-if="addDetectOpen" class="pt-2">
                          <textarea v-model="addDetectInput" rows="5" class="form-control form-control-sm font-monospace"
                                    :placeholder="`[Interface]\nPrivateKey = ...\nJc = 4\nJmin = 50\nJmax = 100\nS1 = 80\nS2 = 40\nH1 = ...\nH2 = ...\nH3 = ...\nH4 = ...`"></textarea>
                          <div class="d-flex align-items-center gap-2 mt-2">
                            <button type="button" class="btn btn-sm btn-primary" @click="detectObfuscationForNewServer">
                              <i class="mdi mdi-auto-fix me-1"></i>{{ $t('servers.detectAndFill') || 'Detect & fill' }}
                            </button>
                            <span v-if="addDetectMessage" class="small"
                                  :class="addDetectOk ? 'text-success' : 'text-danger'">
                              <i class="mdi me-1" :class="addDetectOk ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"></i>
                              {{ addDetectMessage }}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div class="row g-2 mb-2">
                        <div class="col-6 col-sm-3">
                          <label class="form-label small mb-1">H1</label>
                          <input v-model.number="newServer.awg_h1" type="number" min="1" class="form-control form-control-sm font-monospace" placeholder="auto">
                        </div>
                        <div class="col-6 col-sm-3">
                          <label class="form-label small mb-1">H2</label>
                          <input v-model.number="newServer.awg_h2" type="number" min="1" class="form-control form-control-sm font-monospace" placeholder="auto">
                        </div>
                        <div class="col-6 col-sm-3">
                          <label class="form-label small mb-1">H3</label>
                          <input v-model.number="newServer.awg_h3" type="number" min="1" class="form-control form-control-sm font-monospace" placeholder="auto">
                        </div>
                        <div class="col-6 col-sm-3">
                          <label class="form-label small mb-1">H4</label>
                          <input v-model.number="newServer.awg_h4" type="number" min="1" class="form-control form-control-sm font-monospace" placeholder="auto">
                        </div>
                      </div>
                      <div class="row g-2">
                        <div class="col-4 col-sm-2"><label class="form-label small mb-1">JC</label>
                          <input v-model.number="newServer.awg_jc" type="number" min="1" max="128" class="form-control form-control-sm font-monospace" placeholder="4"></div>
                        <div class="col-4 col-sm-2"><label class="form-label small mb-1">JMin</label>
                          <input v-model.number="newServer.awg_jmin" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace" placeholder="50"></div>
                        <div class="col-4 col-sm-2"><label class="form-label small mb-1">JMax</label>
                          <input v-model.number="newServer.awg_jmax" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace" placeholder="100"></div>
                        <div class="col-6 col-sm-3"><label class="form-label small mb-1">S1</label>
                          <input v-model.number="newServer.awg_s1" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace" placeholder="80"></div>
                        <div class="col-6 col-sm-3"><label class="form-label small mb-1">S2</label>
                          <input v-model.number="newServer.awg_s2" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace" placeholder="40"></div>
                      </div>
                    </div>
                  </div>

                  <!-- Location -->
                  <div class="mb-3">
                    <label class="form-label mb-1 small fw-medium">{{ $t('servers.locationOptional') }}</label>
                    <input v-model="newServer.location" type="text" class="form-control"
                           :placeholder="$t('servers.locationPlaceholder')" />
                  </div>

                  <!-- Connection mode selector. Mikrotik option is only
                       shown for plain WireGuard servers — RouterOS doesn't
                       support AmneziaWG (Linux-kernel-specific) and isn't
                       a Hysteria2/TUIC server. -->
                  <div class="ssh-section-label mb-2">{{ connectionModeLabel }}</div>
                  <div class="btn-group mb-3 w-100" role="group">
                    <button type="button"
                            class="btn"
                            :class="newServer.agent_mode === 'ssh' ? 'btn-primary' : 'btn-outline-secondary'"
                            @click="newServer.agent_mode = 'ssh'">
                      <i class="mdi mdi-console me-1"></i>SSH
                    </button>
                    <button v-if="mikrotikOptionAvailable"
                            type="button"
                            class="btn"
                            :class="newServer.agent_mode === 'mikrotik' ? 'btn-primary' : 'btn-outline-secondary'"
                            @click="newServer.agent_mode = 'mikrotik'">
                      <i class="mdi mdi-router-network me-1"></i>Mikrotik (RouterOS API)
                    </button>
                  </div>

                  <!-- SSH credentials (mode = ssh) -->
                  <template v-if="newServer.agent_mode === 'ssh'">
                    <div class="row g-3 mb-3">
                      <div class="col-12 col-sm-6">
                        <label class="form-label mb-1 small fw-medium">{{ $t('servers.sshHost') }}</label>
                        <input v-model="newServer.ssh_host" type="text" class="form-control"
                               :placeholder="$t('servers.sshHostPlaceholder')" />
                      </div>
                      <div class="col-4 col-sm-2">
                        <label class="form-label mb-1 small fw-medium">{{ $t('servers.sshPort') }}</label>
                        <input v-model.number="newServer.ssh_port" type="number" class="form-control" />
                      </div>
                      <div class="col-8 col-sm-4">
                        <label class="form-label mb-1 small fw-medium">{{ $t('servers.sshUser') }}</label>
                        <input v-model="newServer.ssh_user" type="text" class="form-control" />
                      </div>
                    </div>
                    <div class="mb-1">
                      <label class="form-label mb-1 small fw-medium">{{ $t('servers.sshPassword') }}</label>
                      <input v-model="newServer.ssh_password" type="password" class="form-control"
                             :placeholder="$t('servers.sshPasswordPlaceholder')" />
                    </div>
                  </template>

                  <!-- Mikrotik RouterOS REST credentials (mode = mikrotik) -->
                  <template v-if="newServer.agent_mode === 'mikrotik'">
                    <div class="alert alert-info py-2 small mb-3">
                      <i class="mdi mdi-information-outline me-1"></i>
                      {{ mikrotikHint }}
                    </div>
                    <div class="mb-3">
                      <label class="form-label mb-1 small fw-medium">{{ mikrotikUrlLabel }} *</label>
                      <input v-model="newServer.mikrotik_url" type="url" class="form-control"
                             placeholder="http://192.168.88.1" required />
                      <div class="form-text small">{{ mikrotikUrlHint }}</div>
                    </div>
                    <div class="row g-3 mb-1">
                      <div class="col-6">
                        <label class="form-label mb-1 small fw-medium">{{ mikrotikUserLabel }} *</label>
                        <input v-model="newServer.mikrotik_username" type="text" class="form-control"
                               placeholder="admin" required />
                      </div>
                      <div class="col-6">
                        <label class="form-label mb-1 small fw-medium">{{ mikrotikPassLabel }} *</label>
                        <input v-model="newServer.mikrotik_password" type="password" class="form-control"
                               required />
                      </div>
                    </div>
                  </template>

                  <!-- Reuse-keypair toggle for the "replace a dead server" workflow.
                       Most users never need this — keep it collapsed by default so
                       the form stays simple. Click expands a single Private Key field. -->
                  <div class="mt-3 pt-3 border-top">
                    <button type="button"
                            class="btn btn-link btn-sm p-0 text-decoration-none d-flex align-items-center gap-1"
                            @click="reuseKeyOpen = !reuseKeyOpen"
                            style="color: var(--vxy-primary, #5865f2)">
                      <i class="mdi" :class="reuseKeyOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
                      {{ $t('servers.reuseKeyToggle') || 'Replacing a broken server? Reuse its private key' }}
                    </button>
                    <div v-if="reuseKeyOpen" class="mt-2">
                      <label class="form-label mb-1 small fw-medium">{{ $t('servers.privateKeyLabel') || 'Server private key (optional)' }}</label>
                      <input v-model="newServer.private_key" type="password" class="form-control font-monospace"
                             :placeholder="$t('servers.privateKeyPlaceholder') || '44-character base64 WireGuard private key'"
                             maxlength="44" minlength="44" />
                      <div class="form-text small">
                        {{ $t('servers.privateKeyHint') || 'Paste here the key from the broken server (Servers → ⋯ → Export keypair). The new box will inherit the same identity, so existing client configs keep working without re-issuing.' }}
                      </div>
                    </div>
                  </div>

                </div>
              </div>
            </div>

            <div class="alert alert-danger py-2 small" v-if="addError">{{ addError }}</div>

            <!-- Bootstrap progress: simple text for VPN, scrollable log for proxy -->
            <div v-if="addingServer && !bootstrapTaskId && installProgress" class="alert alert-info py-2 small">
              <span class="spinner-border spinner-border-sm me-2"></span>
              {{ installProgress }}
            </div>
            <div v-if="bootstrapTaskId" class="bootstrap-log-box">
              <div class="bootstrap-log-box__header">
                <span v-if="addingServer" class="spinner-border spinner-border-sm me-2"></span>
                <i v-else class="mdi mdi-check-circle text-success me-2"></i>
                <span class="fw-semibold small">{{ addingServer ? (installProgress || 'Installing...') : 'Done' }}</span>
              </div>
              <div class="bootstrap-log-box__body" ref="logBoxRef">
                <div v-for="(line, i) in bootstrapLogs" :key="i" class="bootstrap-log-line">{{ line }}</div>
                <div v-if="!bootstrapLogs.length" class="text-muted small fst-italic">Waiting for server...</div>
              </div>
            </div>
          </div>

          <!-- Sticky footer -->
          <div class="modal-footer modal-footer--sticky">
            <button type="button" class="btn btn-outline-secondary" @click="showAddModal = false" :disabled="addingServer">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary btn-create-server" @click="addServer"
                    :disabled="addingServer || !isFormValid">
              <span class="spinner-border spinner-border-sm me-2" v-if="addingServer"></span>
              {{ addingServer ? (installProgress || $t('common.loading')) : $t('servers.addServer') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showAddModal"></div>

    <!-- Server created toast -->
    <div v-if="serverCreatedToast" class="server-toast">
      <span><i class="mdi mdi-check-circle text-success me-1"></i>{{ $t('servers.serverCreated', { name: serverCreatedToast.name }) }}</span>
      <div class="d-flex align-items-center gap-2 ms-auto">
        <button class="btn btn-sm btn-primary" @click="goCreateClient(serverCreatedToast.id)">
          {{ $t('servers.createClientNow') }}
        </button>
        <button class="btn-close btn-close-white" style="font-size:0.7em" @click="serverCreatedToast = null"></button>
      </div>
    </div>

    <!-- Discover Modal -->
    <div class="modal fade" :class="{ show: showDiscoverModal }" :style="{ display: showDiscoverModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('servers.discoverTitle') }}</h5>
            <button type="button" class="btn-close" @click="showDiscoverModal = false"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted mb-3">{{ $t('servers.discoverDesc') }}</p>
            <div class="row">
              <div class="col-8 mb-3">
                <label class="form-label">{{ $t('servers.sshHost') }}</label>
                <input v-model="discoverData.ssh_host" type="text" class="form-control" placeholder="your.server.ip" />
              </div>
              <div class="col-4 mb-3">
                <label class="form-label">{{ $t('servers.sshPort') }}</label>
                <input v-model.number="discoverData.ssh_port" type="number" class="form-control" />
              </div>
            </div>
            <div class="row">
              <div class="col-6 mb-3">
                <label class="form-label">{{ $t('servers.sshUser') }}</label>
                <input v-model="discoverData.ssh_user" type="text" class="form-control" />
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">{{ $t('servers.sshPassword') }}</label>
                <input v-model="discoverData.ssh_password" type="password" class="form-control" />
              </div>
            </div>
            <div class="row">
              <div class="col-6 mb-3">
                <label class="form-label">{{ $t('servers.interface') }}</label>
                <input v-model="discoverData.interface" type="text" class="form-control" />
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">{{ $t('servers.serverName') }}</label>
                <input v-model="discoverData.server_name" type="text" class="form-control" :placeholder="$t('servers.serverNamePlaceholder')" />
              </div>
            </div>
            <div class="alert alert-danger" v-if="discoverError">{{ discoverError }}</div>
            <div class="alert alert-success" v-if="discoverResult">
              {{ discoverResult }}
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showDiscoverModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="discoverServer" :disabled="discovering">
              <span v-if="discovering" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('servers.discover') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showDiscoverModal"></div>

    <!-- Server Clients Modal -->
    <div class="modal fade" :class="{ show: showClientsModal }" :style="{ display: showClientsModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('servers.clientsOnServer', { name: clientsServerName }) }}</h5>
            <button type="button" class="btn-close" @click="showClientsModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="table-responsive">
              <table class="table table-sm">
                <thead>
                  <tr><th>{{ $t('common.name') }}</th><th>{{ $t('servers.ip') }}</th><th>{{ $t('servers.status') }}</th><th>{{ $t('servers.traffic') }}</th></tr>
                </thead>
                <tbody>
                  <tr v-for="c in serverClients" :key="c.id">
                    <td>{{ c.name }}</td>
                    <td><code>{{ c.ipv4 }}</code></td>
                    <td>
                      <span class="badge" :class="c.enabled ? 'badge-online' : 'badge-offline'">
                        {{ c.enabled ? $t('common.online') : $t('common.offline') }}
                      </span>
                    </td>
                    <td>{{ formatBytes((c.traffic_used_rx || 0) + (c.traffic_used_tx || 0)) }}</td>
                  </tr>
                  <tr v-if="serverClients.length === 0">
                    <td colspan="4" class="text-center text-muted">{{ $t('servers.noClientsOnServer') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showClientsModal"></div>

    <!-- Agent Installation Modal -->
    <div class="modal fade" :class="{ show: showInstallModal }" :style="{ display: showInstallModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title d-flex align-items-center gap-2"><i class="mdi mdi-robot-outline"></i>{{ $t('servers.installAgent') || 'Install Agent' }}<HelpTooltip :text="$t('help.agentMode')" /></h5>
            <button type="button" class="btn-close" @click="showInstallModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-info mb-3">
              <strong>{{ $t('servers.agentModeInfo') || 'Agent Mode Benefits:' }}</strong>
              <ul class="mb-0 mt-2">
                <li>{{ $t('servers.agentSpeed') || '⚡ 10-20x faster operations via HTTP API' }}</li>
                <li>{{ $t('servers.agentReliable') || '✅ More reliable than SSH' }}</li>
                <li>{{ $t('servers.agentNoPassword') || '🔒 No SSH password required' }}</li>
              </ul>
            </div>

            <!-- Installation Mode Selection -->
            <div class="mb-3">
              <label class="form-label fw-bold">{{ $t('servers.installMode') || 'Installation Mode' }}</label>
              <div class="btn-group w-100" role="group">
                <button
                  type="button"
                  class="btn"
                  :class="installMode === 'auto' ? 'btn-primary' : 'btn-outline-primary'"
                  @click="installMode = 'auto'"
                >
                  <i class="mdi mdi-rocket-launch-outline me-1"></i>{{ $t('servers.autoInstall') || 'Automatic' }}
                </button>
                <button
                  type="button"
                  class="btn"
                  :class="installMode === 'manual' ? 'btn-primary' : 'btn-outline-primary'"
                  @click="installMode = 'manual'"
                >
                  <i class="mdi mdi-cog-outline me-1"></i>{{ $t('servers.manualInstall') || 'Custom Port' }}
                </button>
              </div>
            </div>

            <!-- Auto Mode Info -->
            <div v-if="installMode === 'auto'" class="alert alert-success">
              <strong>{{ $t('servers.autoInstallInfo') || 'Automatic Installation' }}</strong>
              <p class="mb-0 mt-2">
                {{ $t('servers.autoInstallDesc') || 'Agent will be installed on port 8001 with automatic firewall configuration.' }}
              </p>
            </div>

            <!-- Manual Mode - Port Selection -->
            <div v-if="installMode === 'manual'" class="card">
              <div class="card-body">
                <label class="form-label">{{ $t('servers.selectPort') || 'Select Agent Port' }}</label>
                <input
                  type="number"
                  class="form-control mb-3"
                  v-model.number="customPort"
                  min="1"
                  max="65535"
                  placeholder="8001"
                />

                <div class="alert alert-warning">
                  <strong>{{ $t('servers.portRecommendations') || 'Port Recommendations:' }}</strong>
                  <div class="mt-2">
                    <button class="btn btn-sm btn-outline-secondary me-2 mb-1" @click="customPort = 8001">8001 ({{ $t('servers.portDefault') || 'Default' }})</button>
                    <button class="btn btn-sm btn-outline-secondary me-2 mb-1" @click="customPort = 80">80 (HTTP)</button>
                    <button class="btn btn-sm btn-outline-secondary me-2 mb-1" @click="customPort = 443">443 (HTTPS)</button>
                    <button class="btn btn-sm btn-outline-secondary mb-1" @click="customPort = 8080">8080</button>
                  </div>
                  <small class="d-block mt-2">
                    {{ $t('servers.portNote') || '⚠️ Some hosting providers block non-standard ports. Ports 80 and 443 are usually open.' }}
                  </small>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showInstallModal = false">
              {{ $t('common.cancel') || 'Cancel' }}
            </button>
            <button
              type="button"
              class="btn btn-success"
              @click="installAgent(selectedServerId, installMode === 'manual' ? customPort : 8001)"
            >
              <i class="mdi mdi-rocket-launch-outline me-1"></i>{{ $t('servers.startInstallation') || 'Start Installation' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showInstallModal"></div>

    <!-- Agent Menu Modal -->
    <div class="modal fade" :class="{ show: showAgentModal }" :style="{ display: showAgentModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="mdi mdi-robot-outline me-2"></i>Agent: {{ agentServer?.name }}</h5>
            <button type="button" class="btn-close" @click="showAgentModal = false"></button>
          </div>
          <div class="modal-body">
            <!-- Connection Status -->
            <div class="mb-3">
              <div class="d-flex align-items-center mb-2">
                <strong class="me-2">{{ $t('servers.connectionStatus') || 'Status' }}:</strong>
                <span v-if="checkingStatus[agentServer?.id]" class="spinner-border spinner-border-sm"></span>
                <span v-else-if="agentStatuses[agentServer?.id]?.healthy" class="badge bg-success"><i class="mdi mdi-circle me-1" style="font-size:.55em"></i>Online</span>
                <span v-else class="badge bg-danger"><i class="mdi mdi-circle me-1" style="font-size:.55em"></i>Offline</span>
              </div>
              <table class="table table-sm mb-0">
                <tbody>
                  <tr>
                    <td class="text-muted" style="width: 35%">URL</td>
                    <td><code>{{ agentServer?.agent_url || '-' }}</code></td>
                  </tr>
                  <tr>
                    <td class="text-muted">{{ $t('servers.mode') || 'Mode' }}</td>
                    <td>{{ agentServer?.agent_mode }}</td>
                  </tr>
                  <tr>
                    <td class="text-muted">SSH Host</td>
                    <td><code>{{ agentServer?.ssh_host }}:{{ agentServer?.ssh_port }}</code></td>
                  </tr>
                  <tr v-if="agentStatuses[agentServer?.id]?.lastCheck">
                    <td class="text-muted">{{ $t('servers.lastCheck') || 'Last Check' }}</td>
                    <td>{{ new Date(agentStatuses[agentServer?.id].lastCheck).toLocaleTimeString() }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Actions -->
            <div class="d-flex flex-column gap-2">
              <button
                class="btn btn-outline-primary btn-sm"
                @click="checkAgentStatus(agentServer.id, true)"
                :disabled="checkingStatus[agentServer?.id]"
              >
                <span v-if="checkingStatus[agentServer?.id]" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="mdi mdi-power-plug-outline me-1"></i>{{ $t('servers.testConnection') || 'Test Connection' }}
              </button>
              <button
                class="btn btn-outline-warning btn-sm"
                @click="reinstallAgentFromMenu()"
                :disabled="installingAgent[agentServer?.id]"
              >
                <span v-if="installingAgent[agentServer?.id]" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="mdi mdi-restart me-1"></i>{{ $t('servers.reinstallAgent') || 'Reinstall Agent' }}
              </button>
              <button
                class="btn btn-outline-danger btn-sm"
                @click="uninstallAgent(agentServer?.id)"
                :disabled="uninstallingAgent"
              >
                <span v-if="uninstallingAgent" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="mdi mdi-trash-can-outline me-1"></i>{{ $t('servers.deleteAgent') || 'Delete Agent (switch to SSH)' }}
              </button>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="showAgentModal = false">{{ $t('common.close') || 'Close' }}</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showAgentModal"></div>

    <!-- Install Proxy Modal -->
    <div class="modal fade" :class="{ show: showInstallProxyModal }" :style="{ display: showInstallProxyModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="mdi mdi-web me-2"></i>Install Proxy on {{ installProxyServer?.name }}</h5>
            <button type="button" class="btn-close" @click="cancelInstallProxy"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small mb-3">Installs Hysteria2 or TUIC on this server's machine via SSH, creating a new proxy server record.</p>

            <div class="mb-3">
              <label class="form-label">Protocol</label>
              <div class="btn-group w-100">
                <button type="button" class="btn" :class="installProxyForm.protocol === 'hysteria2' ? 'btn-primary' : 'btn-outline-primary'" @click="installProxyForm.protocol = 'hysteria2'">Hysteria2</button>
                <button type="button" class="btn" :class="installProxyForm.protocol === 'tuic' ? 'btn-primary' : 'btn-outline-primary'" @click="installProxyForm.protocol = 'tuic'">TUIC</button>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">TLS Mode</label>
              <div class="btn-group w-100">
                <button type="button" class="btn" :class="installProxyForm.tls_mode === 'self_signed' ? 'btn-warning' : 'btn-outline-secondary'" @click="installProxyForm.tls_mode = 'self_signed'">Self-signed</button>
                <button v-if="installProxyForm.protocol === 'hysteria2'" type="button" class="btn" :class="installProxyForm.tls_mode === 'acme' ? 'btn-success' : 'btn-outline-secondary'" @click="installProxyForm.tls_mode = 'acme'">ACME (Let's Encrypt)</button>
                <button type="button" class="btn" :class="installProxyForm.tls_mode === 'manual' ? 'btn-success' : 'btn-outline-secondary'" @click="installProxyForm.tls_mode = 'manual'">Manual</button>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">Domain <span v-if="installProxyForm.tls_mode === 'acme'" class="text-danger">*</span><span v-else class="text-muted">(optional, for SNI)</span></label>
              <input v-model="installProxyForm.domain" type="text" class="form-control" placeholder="your.domain.com" />
            </div>

            <div class="mb-3">
              <label class="form-label">Port <span class="text-muted small">(default: {{ installProxyForm.protocol === 'hysteria2' ? 8443 : 8444 }})</span></label>
              <input v-model.number="installProxyForm.port" type="number" class="form-control" :placeholder="installProxyForm.protocol === 'hysteria2' ? '8443' : '8444'" />
            </div>

            <div v-if="installProxyForm.protocol === 'hysteria2'" class="mb-3">
              <label class="form-label">OBFS Password <span class="text-muted small">(optional)</span></label>
              <input v-model="installProxyForm.obfs_password" type="text" class="form-control" placeholder="Leave empty to disable OBFS" />
            </div>

            <!-- Progress log -->
            <div v-if="installingProxy" class="bootstrap-log-box mt-3">
              <div class="bootstrap-log-box__header">
                <span class="spinner-border spinner-border-sm me-2"></span>
                <span class="fw-semibold small">Installing {{ installProxyForm.protocol }}...</span>
              </div>
              <div class="bootstrap-log-box__body" ref="proxyLogBoxRef">
                <div v-for="(line, i) in proxyInstallLogs" :key="i" class="bootstrap-log-line">{{ line }}</div>
                <div v-if="!proxyInstallLogs.length" class="text-muted small fst-italic">Waiting for server...</div>
              </div>
            </div>
            <div v-if="installProxyError" class="alert alert-danger small mt-2">{{ installProxyError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="cancelInstallProxy">
              <span v-if="cancellingProxy" class="spinner-border spinner-border-sm me-1"></span>
              {{ installingProxy ? ($t('servers.cancelInstall') || 'Cancel install') : $t('common.cancel') }}
            </button>
            <button type="button" class="btn btn-success" @click="doInstallProxy" :disabled="installingProxy || (installProxyForm.tls_mode === 'acme' && !installProxyForm.domain)">
              <span v-if="installingProxy" class="spinner-border spinner-border-sm me-1"></span>
              <i class="mdi mdi-web me-1"></i>Install
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showInstallProxyModal"></div>

    <!-- Install AWG Modal -->
    <div class="modal fade" :class="{ show: showInstallAwgModal }" :style="{ display: showInstallAwgModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="mdi mdi-shield-lock-outline me-2"></i>{{ $t('servers.installAwgTitle') || 'Install AmneziaWG on' }} {{ installAwgServer?.name }}</h5>
            <button type="button" class="btn-close" @click="cancelInstallAwg"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small mb-3">{{ $t('servers.installAwgHint') || 'Provisions AmneziaWG (obfuscated WireGuard) on this server\'s machine via SSH alongside its existing protocol. The new AWG server is managed via SSH — the existing WireGuard agent stays untouched.' }}</p>

            <div class="mb-3">
              <label class="form-label">{{ $t('servers.interface') }}</label>
              <input v-model="installAwgForm.interface" type="text" class="form-control" :placeholder="installAwgForm.interfacePlaceholder || 'awg1 (auto)'" />
              <small class="text-muted">{{ $t('servers.installAwgIfaceHint') || 'Leave blank to auto-pick the next free awgN' }}</small>
            </div>

            <div class="mb-3">
              <label class="form-label">{{ $t('servers.port') }} <span class="text-muted small">(default: 51821)</span></label>
              <input v-model.number="installAwgForm.listen_port" type="number" class="form-control" placeholder="51821" />
            </div>

            <div class="mb-3">
              <label class="form-label">IPv4 pool</label>
              <input v-model="installAwgForm.address_pool_ipv4" type="text" class="form-control" placeholder="10.66.66.0/24" />
            </div>

            <!-- Progress log -->
            <div v-if="installingAwg" class="bootstrap-log-box mt-3">
              <div class="bootstrap-log-box__header">
                <span class="spinner-border spinner-border-sm me-2"></span>
                <span class="fw-semibold small">{{ $t('servers.installingAwg') || 'Installing AmneziaWG…' }}</span>
              </div>
              <div class="bootstrap-log-box__body" ref="awgLogBoxRef">
                <div v-for="(line, i) in awgInstallLogs" :key="i" class="bootstrap-log-line">{{ line }}</div>
                <div v-if="!awgInstallLogs.length" class="text-muted small fst-italic">{{ $t('servers.waitingForServer') || 'Waiting for server...' }}</div>
              </div>
            </div>
            <div v-if="installAwgError" class="alert alert-danger small mt-2">{{ installAwgError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="cancelInstallAwg">
              <span v-if="cancellingAwg" class="spinner-border spinner-border-sm me-1"></span>
              {{ installingAwg ? ($t('servers.cancelInstall') || 'Cancel install') : $t('common.cancel') }}
            </button>
            <button type="button" class="btn btn-success" @click="doInstallAwg" :disabled="installingAwg">
              <span v-if="installingAwg" class="spinner-border spinner-border-sm me-1"></span>
              <i class="mdi mdi-shield-lock-outline me-1"></i>{{ $t('common.install') || 'Install' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showInstallAwgModal"></div>

    <!-- Bandwidth Settings Modal -->
    <div class="modal fade" :class="{ show: showBwModal }" :style="{ display: showBwModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('servers.bandwidthSettings') || 'Bandwidth Limit' }}</h5>
            <button type="button" class="btn-close" @click="showBwModal = false"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted mb-3">{{ bwServerName }}</p>
            <label class="form-label">{{ $t('servers.maxBandwidth') || 'Max bandwidth (Mbps)' }}</label>
            <input type="number" class="form-control" v-model.number="bwLimit" min="0" placeholder="0 = unlimited" />
            <small class="text-muted">{{ $t('servers.bandwidthHint') || 'Set to 0 or leave empty for unlimited' }}</small>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="showBwModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary btn-sm" @click="saveBwLimit" :disabled="savingBwLimit">
              <span v-if="savingBwLimit" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('common.save') || 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showBwModal"></div>

    <!-- Rename (Display Name) Modal -->
    <div class="modal fade" :class="{ show: showRenameModal }" :style="{ display: showRenameModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('servers.rename') || 'Display Name' }}</h5>
            <button type="button" class="btn-close" @click="showRenameModal = false"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small mb-3">{{ renameServerInternalName }}</p>
            <label class="form-label">{{ $t('servers.displayNameLabel') || 'Display name for clients' }}</label>
            <input type="text" class="form-control" v-model="renameDisplayName"
              :placeholder="$t('servers.displayNamePlaceholder') || 'e.g. Amsterdam #1'"
              maxlength="100" @keyup.enter="saveDisplayName" />
            <small class="text-muted">{{ $t('servers.displayNameHint') || 'Shown instead of the real server name and IP in client portal. Leave empty to show internal name.' }}</small>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="showRenameModal = false">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-primary btn-sm" @click="saveDisplayName" :disabled="savingDisplayName">
              <span v-if="savingDisplayName" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('common.save') || 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showRenameModal"></div>

    <!-- ════════ Expand Address Pool Modal ════════ -->
    <div class="modal fade" :class="{ show: showExpandPoolModal }"
         :style="{ display: showExpandPoolModal ? 'block' : 'none' }" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="mdi mdi-arrow-expand-horizontal me-1"></i>{{ $t('servers.expandPool') || 'Expand address pool' }}
            </h5>
            <button type="button" class="btn-close" @click="closeExpandPool"></button>
          </div>
          <div class="modal-body" v-if="expandPoolServer">
            <div class="expand-pool-server">
              <i class="mdi mdi-server-network"></i>
              <strong>{{ expandPoolServer.name }}</strong>
            </div>

            <div class="row g-2 mb-3 expand-pool-grid">
              <div class="col-12 col-sm-6">
                <div class="text-muted small">{{ $t('servers.expandPool_current') || 'Current pool' }}</div>
                <div class="font-monospace fw-semibold">{{ expandPoolServer.address_pool_ipv4 }}</div>
                <div class="text-muted small">{{ expandPoolCurrentHosts }} hosts</div>
              </div>
              <div class="col-12 col-sm-6">
                <div class="text-muted small">{{ $t('servers.expandPool_existingClients') || 'Existing clients' }}</div>
                <div class="font-monospace fw-semibold">{{ expandPoolServer.total_clients ?? '?' }}</div>
                <div class="text-muted small">{{ $t('servers.expandPool_keepIPs') || 'keep their IPs' }}</div>
              </div>
            </div>

            <label class="form-label fw-semibold">{{ $t('servers.expandPool_newCidr') || 'New address pool (CIDR)' }}</label>
            <div class="input-group">
              <input type="text" class="form-control font-monospace" v-model="expandPoolInput"
                     placeholder="10.0.0.0/20" :disabled="expandingPool" @keyup.enter="submitExpandPool" />
            </div>
            <div class="form-text">
              {{ $t('servers.expandPool_hint') || 'Pick a wider CIDR (smaller prefix length) that contains the current pool. Common: /24 → /20 = 4094 hosts, /20 → /16 = 65534 hosts.' }}
            </div>

            <div class="expand-pool-presets mt-2">
              <button v-for="p in expandPoolPresets" :key="p" type="button"
                      class="btn btn-outline-secondary btn-sm" :disabled="expandingPool"
                      @click="expandPoolInput = p">{{ p }}</button>
            </div>

            <div v-if="expandPoolError" class="alert alert-danger mt-3 py-2 small mb-0">
              {{ expandPoolError }}
              <div v-if="expandPoolSuggested" class="mt-1">
                <button type="button" class="btn btn-sm btn-outline-warning"
                        @click="expandPoolInput = expandPoolSuggested; expandPoolError = ''; expandPoolSuggested = ''">
                  Use {{ expandPoolSuggested }}
                </button>
              </div>
            </div>
            <div v-if="expandPoolResult" class="alert alert-success mt-3 py-2 small mb-0">
              <strong>{{ $t('servers.expandPool_done') || 'Done.' }}</strong>
              {{ expandPoolResult.old_pool }} → {{ expandPoolResult.new_pool }}.
              {{ expandPoolResult.host_capacity }} hosts available.
              <span v-if="!expandPoolResult.interface_bounced" class="text-warning d-block mt-1">
                <i class="mdi mdi-alert-outline"></i>
                {{ $t('servers.expandPool_bounceWarn') || 'Database updated, but the interface didn\'t bounce cleanly. Restart the server from the menu when convenient.' }}
              </span>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="closeExpandPool" :disabled="expandingPool">
              {{ expandPoolResult ? ($t('common.close') || 'Close') : ($t('common.cancel') || 'Cancel') }}
            </button>
            <button v-if="!expandPoolResult" type="button" class="btn btn-warning btn-sm"
                    @click="submitExpandPool" :disabled="expandingPool || !expandPoolInput">
              <span v-if="expandingPool" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('servers.expandPool_apply') || 'Expand pool' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showExpandPoolModal"></div>

    <!-- ════════ Export Keypair Modal ════════ -->
    <div v-if="exportKeypairServer" class="modal fade show" style="display:block" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="mdi mdi-key-outline me-2"></i>{{ $t('servers.exportKeypair') || 'Export keypair' }}
            </h5>
            <button type="button" class="btn-close" @click="closeExportKeypair"></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-warning d-flex gap-2 align-items-start mb-3">
              <i class="mdi mdi-alert-outline" style="font-size:1.25rem"></i>
              <div class="small">
                <strong>{{ $t('servers.keypairWarning') || 'Treat this as a secret.' }}</strong>
                <div class="text-muted">{{ $t('servers.keypairWarningHint') || 'Anyone with this private key can impersonate the VPN server. Use it only to seed a replacement box where you want existing client configs to keep working.' }}</div>
              </div>
            </div>

            <div v-if="!keypairData && !keypairError" class="text-center py-3">
              <button class="btn btn-primary" @click="confirmRevealKeypair" :disabled="loadingKeypair">
                <span v-if="loadingKeypair" class="spinner-border spinner-border-sm me-2"></span>
                <i v-else class="mdi mdi-eye-outline me-1"></i>
                {{ $t('servers.revealKeys') || 'I understand — reveal keys' }}
              </button>
            </div>

            <div v-if="keypairError" class="alert alert-danger">{{ keypairError }}</div>

            <div v-if="keypairData">
              <div class="mb-3">
                <label class="form-label small fw-bold">Public key</label>
                <div class="input-group input-group-sm">
                  <input :value="keypairData.public_key" readonly class="form-control font-monospace">
                  <button class="btn btn-outline-secondary" @click="copyToClipboard(keypairData.public_key, 'pub')">
                    <i class="mdi" :class="copiedField === 'pub' ? 'mdi-check text-success' : 'mdi-content-copy'"></i>
                  </button>
                </div>
              </div>
              <div class="mb-3">
                <label class="form-label small fw-bold">Private key</label>
                <div class="input-group input-group-sm">
                  <input :value="keypairData.private_key" readonly class="form-control font-monospace">
                  <button class="btn btn-outline-secondary" @click="copyToClipboard(keypairData.private_key, 'priv')">
                    <i class="mdi" :class="copiedField === 'priv' ? 'mdi-check text-success' : 'mdi-content-copy'"></i>
                  </button>
                </div>
              </div>
              <div class="row g-2 small">
                <div class="col-6"><span class="text-muted">Interface:</span> <code>{{ keypairData.interface }}</code></div>
                <div class="col-6"><span class="text-muted">Listen port:</span> <code>{{ keypairData.listen_port }}</code></div>
                <div class="col-6"><span class="text-muted">Endpoint:</span> <code>{{ keypairData.endpoint }}</code></div>
                <div class="col-6"><span class="text-muted">Subnet:</span> <code>{{ keypairData.address_pool_ipv4 }}</code></div>
              </div>
              <div v-if="keypairData.awg_params" class="mt-3 p-2 rounded" style="background:rgba(99,102,241,.06)">
                <div class="small fw-bold mb-1">AmneziaWG obfuscation params (must match on the new server)</div>
                <pre class="small mb-0" style="white-space:pre-wrap">{{ formatAwgParams(keypairData.awg_params) }}</pre>
              </div>
              <div class="alert alert-info small mt-3 mb-0">
                <strong>{{ $t('servers.keypairUseHint') || 'How to use:' }}</strong>
                {{ $t('servers.keypairUseHintBody') || 'Add a new server in this panel and paste the Private key into the corresponding field. The new box will accept all existing client configs without re-issuing them.' }}
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeExportKeypair">{{ $t('common.close') }}</button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="exportKeypairServer"></div>

    <!-- ════════ Edit AWG Obfuscation Params Modal ════════ -->
    <!-- Lets the operator paste obfuscation headers from another AWG box
         (e.g. when migrating servers with the same private key) so existing
         client configs keep handshaking after the swap. Save → DB update +
         config rewrite on disk + interface restart in one atomic step. -->
    <div v-if="editObfuscationServer" class="modal fade show" style="display:block" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="mdi mdi-tune-vertical me-2"></i>{{ $t('servers.editObfuscationTitle') || 'Edit AmneziaWG obfuscation params' }}
            </h5>
            <button type="button" class="btn-close" @click="closeEditObfuscationModal"></button>
          </div>
          <div class="modal-body">
            <p class="small text-muted mb-3">
              {{ $t('servers.editObfuscationHint') || "Existing client configs reference these exact values to handshake. Paste the values from the old AWG server here, save, and the interface will be restarted so existing clients reconnect without re-issuing configs." }}
            </p>

            <div class="alert alert-warning small d-flex gap-2 align-items-start mb-3">
              <i class="mdi mdi-alert-outline" style="font-size:1.1rem"></i>
              <div>
                {{ $t('servers.editObfuscationWarn') || 'Saving restarts the AmneziaWG interface. Active clients will reconnect within a few seconds.' }}
              </div>
            </div>

            <!-- Smart-fill: two paths, both populate the 9 fields below.
                 Path 1 (recommended when possible): pick another AWG server
                 in this panel — usually the old one if both rows still
                 exist after migration. Zero typing, zero pasting.
                 Path 2 (fallback): paste a working client .conf — for when
                 the old server entry was already deleted from the panel. -->
            <div v-if="awgSourceCandidates.length > 0"
                 class="mb-3 p-2 rounded" style="background:rgba(34,197,94,.06);border:1px solid rgba(34,197,94,.22)">
              <div class="d-flex align-items-center gap-2 mb-2">
                <i class="mdi mdi-source-branch"></i>
                <span class="small fw-bold">{{ $t('servers.copyFromAnotherAwg') || 'Copy from another AWG server in this panel' }}</span>
              </div>
              <div class="small text-muted mb-2">
                {{ $t('servers.copyFromAnotherAwgHint') || 'Pick the old server (or any AWG server whose params you want to inherit). All 9 values copy instantly.' }}
              </div>
              <div class="d-flex gap-2">
                <select v-model="copyFromServerId" class="form-select form-select-sm" style="flex:1">
                  <option :value="null" disabled>{{ $t('servers.selectSourceServer') || 'Select source server…' }}</option>
                  <option v-for="s in awgSourceCandidates" :key="s.id" :value="s.id">
                    {{ s.name }}
                    <template v-if="s.endpoint"> · {{ s.endpoint }}</template>
                    <template v-if="editObfuscationServer && s.public_key === editObfuscationServer.public_key">
                       — {{ $t('servers.samePrivateKey') || 'same keypair' }}
                    </template>
                  </option>
                </select>
                <button class="btn btn-sm btn-success" :disabled="!copyFromServerId" @click="copyObfuscationFromServer">
                  <i class="mdi mdi-content-copy me-1"></i>{{ $t('servers.copy') || 'Copy' }}
                </button>
              </div>
              <div v-if="copyFromMessage" class="small mt-2"
                   :class="copyFromOk ? 'text-success' : 'text-danger'">
                <i class="mdi me-1" :class="copyFromOk ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"></i>
                {{ copyFromMessage }}
              </div>
            </div>

            <!-- Auto-fill from an existing client config — fallback for when
                 the old server entry was already removed from the panel. -->
            <div class="mb-3 p-2 rounded" style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.18)">
              <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none d-flex align-items-center gap-1"
                      @click="obfuscationDetectOpen = !obfuscationDetectOpen">
                <svg class="advanced-chevron" :class="{ 'advanced-chevron--open': obfuscationDetectOpen }"
                     xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
                <i class="mdi mdi-magnify-scan"></i>
                {{ awgSourceCandidates.length > 0
                    ? ($t('servers.detectFromClientConfigOr') || 'Or auto-fill from a working client config')
                    : ($t('servers.detectFromClientConfig') || 'Auto-fill from a working client config') }}
              </button>
              <div v-if="obfuscationDetectOpen" class="pt-2">
                <div class="small text-muted mb-2">
                  {{ $t('servers.detectFromClientConfigHint') || 'Paste any client .conf that still works against the old server (.conf has Jc/H1-H4 in its [Interface] section). We extract all 9 values automatically — no manual entry.' }}
                </div>
                <textarea v-model="obfuscationDetectInput" rows="6" class="form-control form-control-sm font-monospace"
                          :placeholder="`[Interface]\nPrivateKey = ...\nJc = 4\nJmin = 50\nJmax = 100\nS1 = 80\nS2 = 40\nH1 = 3251671305\nH2 = 4062148898\nH3 = 286888380\nH4 = 1301557386\n...`"></textarea>
                <div class="d-flex align-items-center gap-2 mt-2">
                  <button class="btn btn-sm btn-primary" @click="detectObfuscationFromInput">
                    <i class="mdi mdi-auto-fix me-1"></i>{{ $t('servers.detectAndFill') || 'Detect & fill' }}
                  </button>
                  <span v-if="obfuscationDetectMessage" class="small"
                        :class="obfuscationDetectOk ? 'text-success' : 'text-danger'">
                    <i class="mdi me-1" :class="obfuscationDetectOk ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"></i>
                    {{ obfuscationDetectMessage }}
                  </span>
                </div>
              </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-12"><div class="small fw-bold text-muted">{{ $t('servers.obfuscationHeaders') || 'Packet headers (h1-h4)' }}</div></div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">H1</label>
                <input v-model.number="obfuscationForm.awg_h1" type="number" min="1" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">H2</label>
                <input v-model.number="obfuscationForm.awg_h2" type="number" min="1" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">H3</label>
                <input v-model.number="obfuscationForm.awg_h3" type="number" min="1" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">H4</label>
                <input v-model.number="obfuscationForm.awg_h4" type="number" min="1" class="form-control form-control-sm font-monospace">
              </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-12"><div class="small fw-bold text-muted">{{ $t('servers.obfuscationJunk') || 'Junk + magic (jc, jmin, jmax, s1, s2)' }}</div></div>
              <div class="col-4 col-sm-2">
                <label class="form-label small mb-1">JC</label>
                <input v-model.number="obfuscationForm.awg_jc" type="number" min="1" max="128" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-4 col-sm-2">
                <label class="form-label small mb-1">JMin</label>
                <input v-model.number="obfuscationForm.awg_jmin" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-4 col-sm-2">
                <label class="form-label small mb-1">JMax</label>
                <input v-model.number="obfuscationForm.awg_jmax" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">S1</label>
                <input v-model.number="obfuscationForm.awg_s1" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace">
              </div>
              <div class="col-6 col-sm-3">
                <label class="form-label small mb-1">S2</label>
                <input v-model.number="obfuscationForm.awg_s2" type="number" min="0" max="65535" class="form-control form-control-sm font-monospace">
              </div>
            </div>

            <div v-if="obfuscationError" class="alert alert-danger small mb-0">{{ obfuscationError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeEditObfuscationModal" :disabled="savingObfuscation">
              {{ $t('common.cancel') || 'Cancel' }}
            </button>
            <button class="btn btn-primary" @click="saveObfuscationParams" :disabled="savingObfuscation">
              <span v-if="savingObfuscation" class="spinner-border spinner-border-sm me-2"></span>
              <i v-else class="mdi mdi-content-save-outline me-1"></i>
              {{ $t('servers.saveAndApply') || 'Save & restart interface' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="editObfuscationServer"></div>

    <!-- ════════ Migrate Clients Modal ════════ -->
    <div v-if="migrateSourceServer" class="modal fade show" style="display:block" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="mdi mdi-account-switch-outline me-2"></i>{{ $t('servers.migrateClients') || 'Migrate clients' }}
            </h5>
            <button type="button" class="btn-close" @click="closeMigrateClients"></button>
          </div>
          <div class="modal-body">
            <p class="small text-muted mb-3">
              {{ $t('servers.migrateClientsHint') || 'Move every WG client from this server to another. Client configs will keep working as long as the destination uses the same private key (use "Export keypair" → reuse on a new server).' }}
            </p>

            <div class="mb-3">
              <label class="form-label small fw-bold">From</label>
              <input :value="migrateSourceServer.name + ' (' + (migrateSourceServer.endpoint || '') + ')'" readonly class="form-control form-control-sm">
            </div>

            <div class="mb-3">
              <label class="form-label small fw-bold">To</label>
              <select v-model="migrateTargetId" class="form-select form-select-sm">
                <option :value="null" disabled>{{ $t('servers.selectTargetServer') || 'Select target server…' }}</option>
                <option v-for="s in migrateCandidateServers" :key="s.id" :value="s.id"
                        :disabled="migrateSourceServer && s.public_key !== migrateSourceServer.public_key">
                  {{ s.name }} · {{ s.server_type }} · {{ s.endpoint || 'local' }}
                  <template v-if="migrateSourceServer && s.public_key !== migrateSourceServer.public_key">
                    — {{ $t('servers.migrateDiffKeypair') || 'different keypair' }}
                  </template>
                </option>
              </select>
              <small v-if="!migrateCandidateServers.length" class="text-muted">
                {{ $t('servers.migrateNoTargets') || 'No other server with the same protocol available.' }}
              </small>
              <small v-else-if="migrateCandidateServers.length && !migrateAnyKeypairMatches" class="text-warning d-block mt-1">
                <i class="mdi mdi-alert-circle-outline me-1"></i>
                {{ $t('servers.migrateNoKeypairMatch') || 'No target server has the same WireGuard keypair as the source. Recreate one with Add Server → "Reuse private key", or migrate by manually re-issuing client configs.' }}
              </small>
            </div>

            <div class="form-check mb-2">
              <input class="form-check-input" type="checkbox" id="syncRemote" v-model="migrateSyncRemote">
              <label class="form-check-label small" for="syncRemote">
                {{ $t('servers.migrateSyncRemote') || 'Push peers to the new server\'s WireGuard (recommended)' }}
              </label>
            </div>
            <div class="form-check mb-2">
              <input class="form-check-input" type="checkbox" id="removeOld"
                     v-model="migrateRemoveFromOld" :disabled="migrateKeepOnSource">
              <label class="form-check-label small" for="removeOld">
                {{ $t('servers.migrateRemoveOld') || 'Remove peers from the old server\'s WireGuard' }}
              </label>
            </div>
            <!-- Dual-active copy mode: keeps clients on the source AND adds them
                 to the destination, for the DNS-propagation transition window. -->
            <div class="form-check mb-3">
              <input class="form-check-input" type="checkbox" id="keepOnSource" v-model="migrateKeepOnSource">
              <label class="form-check-label small" for="keepOnSource">
                {{ $t('servers.migrateKeepOnSource') || 'Keep clients on source server (dual-active during DNS propagation)' }}
              </label>
              <div v-if="migrateKeepOnSource" class="form-text small ms-4 mt-1" style="color: var(--bs-info-text-emphasis)">
                <i class="mdi mdi-information-outline me-1"></i>
                {{ $t('servers.migrateKeepOnSourceHint') || "Source keeps the clients in its panel and on its live WireGuard. Destination gets the same peers added — clients can connect to either endpoint during the cutover. When DNS has finished propagating, run a regular migrate (this checkbox off) to complete the move." }}
              </div>
            </div>

            <!-- Selective migration: list of clients with checkboxes.
                 Default = all selected → behaves like old bulk-migrate.
                 Uncheck any → API call switches to subset path. -->
            <div class="mb-3">
              <div class="d-flex align-items-center justify-content-between mb-1">
                <label class="form-label small fw-bold mb-0">
                  {{ $t('servers.migrateClientsToPick') || 'Clients to migrate' }}
                  <span class="text-muted fw-normal">
                    ({{ migrateSelectedIds.size }} / {{ migrateClientsList.length }})
                  </span>
                </label>
                <div v-if="migrateClientsList.length" class="btn-group btn-group-sm" role="group">
                  <button type="button" class="btn btn-link btn-sm p-0 me-2"
                          :disabled="migrateSelectionMode === 'all'"
                          @click="selectAllMigrateClients">
                    {{ $t('servers.migrateSelectAll') || 'All' }}
                  </button>
                  <button type="button" class="btn btn-link btn-sm p-0"
                          :disabled="migrateSelectionMode === 'none'"
                          @click="deselectAllMigrateClients">
                    {{ $t('servers.migrateSelectNone') || 'None' }}
                  </button>
                </div>
              </div>

              <div v-if="loadingMigrateClients" class="d-flex align-items-center small text-muted gap-2 py-2">
                <span class="spinner-border spinner-border-sm"></span>
                {{ $t('servers.migrateLoadingClients') || 'Loading clients…' }}
              </div>

              <div v-else-if="!migrateClientsList.length" class="small text-muted py-2">
                {{ $t('servers.migrateNoClients') || 'No clients on this server.' }}
              </div>

              <div v-else>
                <input v-model="migrateClientsFilter" type="search"
                       class="form-control form-control-sm mb-2"
                       :placeholder="$t('servers.migrateFilterPlaceholder') || 'Filter by name, IP or ID…'">
                <div class="border rounded" style="max-height: 220px; overflow-y: auto;">
                  <div v-for="c in migrateFilteredClients" :key="c.id"
                       class="form-check ps-4 py-1 px-2 border-bottom"
                       style="border-color: var(--bs-border-color-translucent) !important">
                    <input class="form-check-input" type="checkbox"
                           :id="'mig-c-' + c.id"
                           :checked="migrateSelectedIds.has(c.id)"
                           @change="toggleMigrateClient(c.id)">
                    <label class="form-check-label small d-flex justify-content-between gap-2 w-100"
                           :for="'mig-c-' + c.id">
                      <span class="text-truncate">{{ c.name }}</span>
                      <span class="text-muted font-monospace small">{{ c.ipv4 }}</span>
                    </label>
                  </div>
                  <div v-if="!migrateFilteredClients.length" class="small text-muted p-2 text-center">
                    {{ $t('servers.migrateFilterNoMatch') || 'No clients match the filter.' }}
                  </div>
                </div>
                <div v-if="migrateSelectionMode === 'subset'" class="form-text small mt-1">
                  <i class="mdi mdi-information-outline me-1"></i>
                  {{ $t('servers.migrateSubsetHint') || 'Subset selected — only the checked clients will move. Useful for canary moves.' }}
                </div>
              </div>
            </div>

            <div v-if="migrateResult" class="alert" :class="migrateResult.failed && migrateResult.failed.length ? 'alert-warning' : 'alert-success'">
              <strong>{{ migrateResult.message }}</strong>
              <div v-if="migrateResult.failed && migrateResult.failed.length" class="small mt-2">
                Failed:
                <ul class="mb-0">
                  <li v-for="(f, i) in migrateResult.failed" :key="i">{{ f.client }}: {{ f.error }}</li>
                </ul>
              </div>
            </div>
            <div v-if="migrateError" class="alert alert-danger">{{ migrateError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeMigrateClients">{{ $t('common.close') }}</button>
            <button class="btn btn-primary" @click="runMigrate"
                    :disabled="!migrateTargetId || migrating || migrateResult || migrateSelectionMode === 'none' || loadingMigrateClients">
              <span v-if="migrating" class="spinner-border spinner-border-sm me-2"></span>
              {{ migrateSelectionMode === 'subset'
                  ? ($t('servers.migrateSelected') || 'Migrate selected')
                  : ($t('servers.migrateNow') || 'Migrate now') }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="migrateSourceServer"></div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useServersStore } from '../stores/servers'
import { useLicenseStore } from '../stores/license'
import { serversApi, systemApi } from '../api'

const { t } = useI18n()
const store = useServersStore()
const license = useLicenseStore()

// ── i18n-safe labels (try/catch + literal fallback) ─────────
// Inline $t() inside templates can crash the route on first paint when the
// locale module hits a transient state. Wrapping in computed + try/catch
// returns a hard-coded English fallback instead of taking the whole page
// down. See feedback_jsx_safe_i18n_patterns.
const acmeBannerTitle    = computed(() => { try { return t('servers.acmeBannerTitle')    || "Let's Encrypt — requirements" } catch { return "Let's Encrypt — requirements" } })
const acmeReqDomain      = computed(() => { try { return t('servers.acmeReqDomain')      || "Domain <strong>must</strong> point to this server's IP (A record)" } catch { return "Domain <strong>must</strong> point to this server's IP (A record)" } })
const acmeReqPort80      = computed(() => { try { return t('servers.acmeReqPort80')      || "Port <strong>80</strong> must be open (HTTP-01 challenge)" } catch { return "Port <strong>80</strong> must be open (HTTP-01 challenge)" } })
const acmeReqAutoIssue   = computed(() => { try { return t('servers.acmeReqAutoIssue')   || "Certificate is issued automatically on startup — the full process is visible in the logs" } catch { return "Certificate is issued automatically on startup — the full process is visible in the logs" } })

const connectionModeLabel = computed(() => { try { return t('servers.connectionMode') || 'Connection' } catch { return 'Connection' } })

// Mikrotik adapter only manages plain WireGuard interfaces. AmneziaWG is a
// Linux-kernel-only protocol, and Hysteria2/TUIC are entirely different
// proxy services — neither runs on RouterOS. Also gated by the
// `mikrotik_adapter` license feature (Pro tier or higher). Hide the
// button when any of these don't hold so operators can't pick an
// unsupported / unlicensed combination.
const mikrotikOptionAvailable = computed(() => {
  return newServer.value.server_type === 'wireguard'
      && newServer.value.server_category !== 'proxy'
      && license.has('mikrotik_adapter')
})
const mikrotikHint        = computed(() => { try { return t('servers.mikrotikHint') || 'The server must already have a WireGuard interface configured on the router. We connect to its REST API to add and remove peers.' } catch { return 'The server must already have a WireGuard interface configured on the router. We connect to its REST API to add and remove peers.' } })
const mikrotikUrlLabel    = computed(() => { try { return t('servers.mikrotikUrl') || 'RouterOS URL' } catch { return 'RouterOS URL' } })
const mikrotikUrlHint     = computed(() => { try { return t('servers.mikrotikUrlHint') || 'Include scheme and port if non-default: http://1.2.3.4 or https://router.example.com:443' } catch { return 'Include scheme and port if non-default: http://1.2.3.4 or https://router.example.com:443' } })
const mikrotikUserLabel   = computed(() => { try { return t('servers.mikrotikUser') || 'API username' } catch { return 'API username' } })
const mikrotikPassLabel   = computed(() => { try { return t('servers.mikrotikPass') || 'API password' } catch { return 'API password' } })

// ── Server card helpers ────────────────────────────────────
const openMenuId = ref(null)
function isOnline(s) { return s.status === 'ONLINE' || s.status === 'online' }
function clientPct(s) { return s.max_clients ? Math.round((s.total_clients || 0) / s.max_clients * 100) : 0 }
function toggleMenu(id) { openMenuId.value = openMenuId.value === id ? null : id }
function menuAction(fn) { openMenuId.value = null; fn() }

// ── Broken-agent banner ────────────────────────────────────
// Servers whose agent circuit-breaker is open (>=3 consecutive
// ConnectTimeouts). Drives the page-top banner that nudges the user toward
// Switch-to-SSH / Retry-now so a dead box stops being a mystery.
const brokenAgents = computed(() =>
  (store.servers || []).filter(s => s.agent_breaker?.open)
)
const breakerActing = reactive({})

function formatBreakerSince(seconds) {
  if (seconds == null) return ''
  const s = Math.floor(seconds)
  if (s < 60) return t('servers.agentSinceSeconds', { seconds: s })
  return t('servers.agentSinceMinutes', { minutes: Math.floor(s / 60) })
}

async function switchAgentToSsh(server) {
  if (!server) return
  breakerActing[server.id] = true
  try {
    await serversApi.switchAgentMode(server.id, 'ssh')
    // The server tile flipping from "agent" to "ssh" + the banner item
    // disappearing is enough confirmation; no toast needed.
    await store.fetchServers()
  } catch (err) {
    alert((err.response?.data?.detail || err.message))
  } finally {
    breakerActing[server.id] = false
  }
}

async function retryAgentNow(server) {
  if (!server) return
  breakerActing[server.id] = true
  try {
    await serversApi.resetAgentBreaker(server.id)
    // Probe the agent once so the next /servers refresh reflects the result.
    try { await serversApi.checkAgentStatus(server.id) } catch (_) { /* surface via banner */ }
    await store.fetchServers()
  } catch (err) {
    alert((err.response?.data?.detail || err.message))
  } finally {
    breakerActing[server.id] = false
  }
}

const showAddModal = ref(false)
const addError = ref('')
const addingServer = ref(false)
const acmeDomainError = ref(false)
const endpointError = ref(false)
const advancedOpen = ref(localStorage.getItem('vms_advanced_open') === 'true')
// obfsEnabled removed — field empty = OBFS off, filled = OBFS on
const nameAutoGenerated = ref(false)
const serverCreatedToast = ref(null) // { name, id }
const domainInputRef = ref(null)
const logBoxRef = ref(null)

const isFormValid = computed(() => {
  if (!newServer.value.endpoint?.trim()) return false
  if (endpointError.value) return false
  if (newServer.value.server_category === 'proxy' &&
      newServer.value.proxy_tls_mode === 'acme' &&
      !newServer.value.proxy_domain?.trim()) return false
  return true
})

watch(() => newServer.value.endpoint, (val) => {
  if (!nameAutoGenerated.value && newServer.value.name) return
  if (val && val.trim()) {
    newServer.value.name = `Server ${val.trim()}`
    nameAutoGenerated.value = true
  }
})

// Reactive ACME domain validation — show error before submit
watch(() => newServer.value.proxy_tls_mode, (mode) => {
  if (mode !== 'acme') {
    acmeDomainError.value = false
  } else if (!newServer.value.proxy_domain?.trim()) {
    acmeDomainError.value = true
  }
})

// If the user picks AWG or a proxy protocol after having selected
// Mikrotik connection-mode, flip the mode back to SSH — Mikrotik can't
// run those.
watch([
  () => newServer.value.server_type,
  () => newServer.value.server_category,
], () => {
  if (newServer.value.agent_mode === 'mikrotik' && !mikrotikOptionAvailable.value) {
    newServer.value.agent_mode = 'ssh'
  }
})
watch(() => newServer.value.proxy_domain, (val) => {
  if (newServer.value.proxy_tls_mode === 'acme') {
    acmeDomainError.value = !val?.trim()
  }
})

function validateEndpoint() {
  const val = newServer.value.endpoint?.trim()
  if (!val) { endpointError.value = false; return }
  const ipRe = /^(\d{1,3}\.){3}\d{1,3}$/
  const hostRe = /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$/
  endpointError.value = !ipRe.test(val) && !hostRe.test(val)
}

function toggleAdvanced() {
  advancedOpen.value = !advancedOpen.value
  localStorage.setItem('vms_advanced_open', String(advancedOpen.value))
}

function goCreateClient(serverId) {
  serverCreatedToast.value = null
  // Navigate to clients page - use router if available, else fallback
  window.location.hash = '#/clients?server=' + serverId
}

// Agent installation modal
const showInstallModal = ref(false)
const selectedServerId = ref(null)
const installMode = ref('auto') // 'auto' or 'manual'
const customPort = ref(8001)

// Agent status tracking
const agentStatuses = ref({}) // { serverId: { healthy: true/false, checking: false } }
const checkingStatus = ref({})

// Agent menu modal
const showAgentModal = ref(false)
const agentServer = ref(null)
const uninstallingAgent = ref(false)
const installProgress = ref('')
const bootstrapLogs = ref([])
const bootstrapTaskId = ref('')
let bootstrapPollingHandle = null

// Auto-scroll log box as new lines arrive
watch(bootstrapLogs, () => {
  nextTick(() => {
    if (logBoxRef.value) {
      logBoxRef.value.scrollTop = logBoxRef.value.scrollHeight
    }
  })
}, { deep: true })

function stopBootstrapPolling() {
  if (bootstrapPollingHandle) {
    clearInterval(bootstrapPollingHandle)
    bootstrapPollingHandle = null
  }
}

async function pollBootstrapLogs(taskId) {
  let since = 0
  bootstrapPollingHandle = setInterval(async () => {
    try {
      const { data } = await serversApi.getBootstrapLogs(taskId, since)
      if (data.logs?.length) {
        bootstrapLogs.value.push(...data.logs)
        since = data.next_index
      }
      if (data.complete) {
        stopBootstrapPolling()
      }
    } catch (_e) { /* ignore transient poll errors */ }
  }, 1200)
}

const newServer = ref({
  name: '',
  endpoint: '',
  interface: 'wg1',
  listen_port: 51821,
  address_pool_ipv4: '10.0.1.0/24',
  dns: '1.1.1.1,8.8.8.8',
  max_clients: 250,
  location: '',
  ssh_host: '',
  ssh_port: 22,
  ssh_user: 'root',
  ssh_password: '',
  server_type: 'wireguard',
  server_category: 'vpn',
  split_tunnel_support: false,
  ipv4_only: false,
  // Connection mode: 'ssh' (default, install agent over SSH) or 'mikrotik'
  // (manage an existing RouterOS device via its REST API — no SSH, no
  // agent install).
  agent_mode: 'ssh',
  mikrotik_url: '',
  mikrotik_username: 'admin',
  mikrotik_password: '',
  // Proxy fields
  proxy_domain: '',
  proxy_tls_mode: 'self_signed',
  proxy_cert_path: '',
  proxy_key_path: '',
  proxy_obfs_password: '',
  private_key: '',
  // AmneziaWG obfuscation params — empty means "auto-generate on the backend".
  // Filled when the operator is migrating from another AWG box and needs the
  // new server to use the old box's headers so existing client configs work.
  awg_jc: null,
  awg_jmin: null,
  awg_jmax: null,
  awg_s1: null,
  awg_s2: null,
  awg_h1: null,
  awg_h2: null,
  awg_h3: null,
  awg_h4: null,
})

const reuseKeyOpen = ref(false)
const reuseObfuscationOpen = ref(false)
const addDetectOpen = ref(false)
const addDetectInput = ref('')
const addDetectMessage = ref('')
const addDetectOk = ref(false)

// ── Edit AWG Obfuscation Params modal state ──────────────────────────────
const editObfuscationServer = ref(null)
const obfuscationForm = ref({
  awg_jc: null, awg_jmin: null, awg_jmax: null, awg_s1: null, awg_s2: null,
  awg_h1: null, awg_h2: null, awg_h3: null, awg_h4: null,
})
const savingObfuscation = ref(false)
const obfuscationError = ref('')
// Auto-fill panel inside the modal: collapsible textarea where the operator
// pastes a working client .conf, we extract Jc/Jmin/Jmax/S1/S2/H1-H4.
const obfuscationDetectOpen = ref(false)
const obfuscationDetectInput = ref('')
const obfuscationDetectMessage = ref('')
const obfuscationDetectOk = ref(false)
// Copy-from-another-server dropdown state (Edit modal)
const copyFromServerId = ref(null)
const copyFromMessage = ref('')
const copyFromOk = ref(false)
// Copy-from-another-server dropdown state (Add form)
const addCopyFromServerId = ref(null)
const addCopyFromMessage = ref('')
const addCopyFromOk = ref(false)

const showDiscoverModal = ref(false)
const discoverError = ref('')
const discoverResult = ref('')
const discovering = ref(false)
const discoverData = ref({
  ssh_host: '',
  ssh_port: 22,
  ssh_user: 'root',
  ssh_password: '',
  interface: 'wg0',
  server_name: '',
})

const showClientsModal = ref(false)
const serverClients = ref([])
const clientsServerName = ref('')

const installingAgent = ref({})

const detectingPublicIp = ref(false)
const autoDetectedPanelIp = ref('')

function autoDetectPublicIp() {
  // Pulls the host's public IPv4 and pre-fills the endpoint field. Skipped
  // when the user has explicitly typed something or when this is a remote
  // (ssh-managed) install. Used both from selectCategory(...) and from the
  // modal-opened watcher so the "Add" button is enabled out of the gate
  // regardless of which category the user starts with.
  if (newServer.value.ssh_host || newServer.value.endpoint) return
  detectingPublicIp.value = true
  systemApi.getPublicIp().then(res => {
    if (res.data?.public_ip && !newServer.value.endpoint) {
      newServer.value.endpoint = res.data.public_ip
      autoDetectedPanelIp.value = res.data.public_ip
    }
  }).catch(() => {}).finally(() => { detectingPublicIp.value = false })
}

// When user fills ssh_host for a REMOTE server, the endpoint must point to
// that remote host — not the panel host. If endpoint is still the
// panel-IP we auto-pre-filled (or empty), mirror ssh_host into it. We don't
// overwrite a deliberately-edited endpoint (e.g. a DNS name).
watch(() => newServer.value.ssh_host, (val) => {
  const sshHost = (val || '').trim()
  if (!sshHost) return
  const ep = (newServer.value.endpoint || '').trim()
  if (!ep || ep === autoDetectedPanelIp.value) {
    newServer.value.endpoint = sshHost
  }
})

function selectCategory(cat) {
  newServer.value.server_category = cat
  if (cat === 'vpn') {
    newServer.value.server_type = 'wireguard'
    newServer.value.listen_port = 51821
    newServer.value.interface = 'wg1'
  } else {
    newServer.value.server_type = 'hysteria2'
    newServer.value.listen_port = 8443
    newServer.value.interface = 'proxy-hy20'
  }
  autoDetectPublicIp()
}

// Fire IP detection as soon as the modal opens so the endpoint pre-fills
// whether the user starts on VPN (default) or Proxy. Without this, the
// "Add" button stayed disabled until the user toggled to Proxy and back.
watch(() => showAddModal.value, (open) => {
  if (open) autoDetectPublicIp()
})

function onProtocolChange() {
  const type = newServer.value.server_type
  // Default subnets per protocol — different ranges so a user adding both
  // WG and AWG on the same host doesn't get a routing collision (both
  // interfaces claiming 10.0.1.0/24 → kernel routes via the last one up,
  // older interface's clients lose return traffic). Backend has a parallel
  // auto-shift safety net for API callers who don't pick a free subnet.
  const WG_DEFAULT_POOL  = '10.0.1.0/24'
  const AWG_DEFAULT_POOL = '10.66.66.0/24'

  if (type === 'amneziawg') {
    if (!newServer.value.interface.startsWith('awg')) {
      const num = newServer.value.interface.replace(/\D/g, '') || '0'
      newServer.value.interface = `awg${num}`
    }
    if ([51820, 51821].includes(newServer.value.listen_port)) newServer.value.listen_port = 51820
    // Switch the default pool unless the user has already typed a custom one
    if ([WG_DEFAULT_POOL, AWG_DEFAULT_POOL].includes(newServer.value.address_pool_ipv4)) {
      newServer.value.address_pool_ipv4 = AWG_DEFAULT_POOL
    }
  } else if (type === 'wireguard') {
    if (!newServer.value.interface.startsWith('wg')) {
      const num = newServer.value.interface.replace(/\D/g, '') || '1'
      newServer.value.interface = `wg${num}`
    }
    if ([51820].includes(newServer.value.listen_port)) newServer.value.listen_port = 51821
    if ([WG_DEFAULT_POOL, AWG_DEFAULT_POOL].includes(newServer.value.address_pool_ipv4)) {
      newServer.value.address_pool_ipv4 = WG_DEFAULT_POOL
    }
  } else if (type === 'hysteria2') {
    newServer.value.listen_port = 8443
  } else if (type === 'tuic') {
    newServer.value.listen_port = 8444
  }
}

// Bandwidth monitoring
const bwData = reactive({})
let bwInterval = null
const showBwModal = ref(false)
const bwServerId = ref(null)
const bwServerName = ref('')
const bwLimit = ref(0)
const savingBwLimit = ref(false)

// Rename (display name)
const showRenameModal = ref(false)
const renameServerId = ref(null)
const renameServerInternalName = ref('')
const renameDisplayName = ref('')
const savingDisplayName = ref(false)

// Export keypair modal
const exportKeypairServer = ref(null)
const keypairData = ref(null)
const keypairError = ref('')
const loadingKeypair = ref(false)
const copiedField = ref('')

// Migrate clients modal
const migrateSourceServer = ref(null)
const migrateTargetId = ref(null)
const migrateSyncRemote = ref(true)
const migrateRemoveFromOld = ref(true)
const migrateKeepOnSource = ref(false)

// When the operator turns on dual-active "keep on source" mode, the
// "remove peers from old WG" toggle is conceptually a contradiction —
// drop its checkmark immediately so the UI matches the actual behaviour
// the backend will execute. (One-way: turning keep_on_source OFF later
// does NOT auto-re-tick remove_from_old, so the operator can still leave
// it unchecked if that's what they want.)
watch(migrateKeepOnSource, (val) => {
    if (val) migrateRemoveFromOld.value = false
})
const migrating = ref(false)
const migrateResult = ref(null)
const migrateError = ref('')
// Selective migration: list loaded when modal opens, all selected by default.
// If the user unchecks any → API call passes a `client_ids` subset; if all
// remain checked → we omit `client_ids` so the backend takes the bulk path.
const migrateClientsList = ref([])
const migrateSelectedIds = ref(new Set())
const loadingMigrateClients = ref(false)
const migrateClientsFilter = ref('')

// Backup/Restore
const backingUp = ref({})
const restoreInputs = ref({})
const togglingTunnel = ref({})

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

async function serverAction(id, action) {
  try {
    await store.serverAction(id, action)
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function setDefaultServer(id) {
  try {
    await serversApi.setDefault(id)
    await store.fetchServers()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function confirmDeleteServer(server) {
  // Field is `total_clients` from ServerResponse, NOT `client_count` —
  // earlier check was always 0 because of the wrong key, so the warning
  // never showed for servers with active clients.
  const clientCount = server.total_clients ?? server.client_count ?? 0
  let msg
  if (server.server_category === 'proxy') {
    msg = `Uninstall proxy "${server.name}"?\n\nThis will stop and remove the ${server.server_type === 'hysteria2' ? 'Hysteria 2' : 'TUIC'} service from the remote server and delete this server record.`
    if (clientCount > 0) {
      msg += `\n\n⚠ This server has ${clientCount} client(s) — they will all be deleted along with the server.`
    }
  } else {
    msg = `Delete server "${server.name}"?`
    if (clientCount > 0) {
      msg += (
        `\n\n⚠ THIS SERVER HAS ${clientCount} CLIENT(S).\n\n` +
        `All ${clientCount} client(s) and their VPN configs will be permanently removed. ` +
        `Active connections will drop. This cannot be undone.\n\n` +
        `Type the server name to confirm:`
      )
      const typed = prompt(msg, '')
      if (typed === null) return
      if (typed.trim() !== server.name) {
        alert(`Aborted — you typed "${typed}", expected "${server.name}".`)
        return
      }
    } else if (!confirm(msg)) {
      return
    }
  }
  if (server.server_category === 'proxy' && !confirm(msg)) return
  try {
    await serversApi.delete(server.id, true)
    await store.fetchServers()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function saveConfig(id) {
  try {
    await store.saveConfig(id)
    alert(t('servers.configSaved'))
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function viewClients(id) {
  const server = store.servers.find((s) => s.id === id)
  clientsServerName.value = server?.name || ''
  try {
    const { data } = await serversApi.getClients(id)
    serverClients.value = data.clients || data
    showClientsModal.value = true
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  }
}

async function addServer() {
  addError.value = ''
  acmeDomainError.value = false
  addingServer.value = true
  installProgress.value = ''
  bootstrapLogs.value = []
  bootstrapTaskId.value = ''
  stopBootstrapPolling()

  const payload = { ...newServer.value }
  const isMikrotik = payload.agent_mode === 'mikrotik'
  const isRemote = isMikrotik || !!payload.ssh_host
  const isProxy = payload.server_category === 'proxy'

  // Mikrotik mode: the WG interface and its keypair live on the router.
  // public_key and listen_port get probed and stamped by the backend from
  // the router's REST API; drop whatever the user typed. Endpoint stays
  // (user types the public-facing IP/host that clients dial — separate
  // from the management URL).
  if (isMikrotik) {
    delete payload.public_key
    delete payload.private_key
    delete payload.listen_port
  }

  // Proxy servers: backend auto-generates the interface name (proxy-hy20, proxy-tui0)
  // Frontend default 'proxy-hy20' would fail backend VPN interface validation
  if (isProxy) {
    delete payload.interface
  }

  // Endpoint validation
  validateEndpoint()
  if (endpointError.value) {
    addingServer.value = false
    return
  }

  // ACME requires a domain
  if (isProxy && payload.proxy_tls_mode === 'acme' && !payload.proxy_domain?.trim()) {
    acmeDomainError.value = true
    addingServer.value = false
    domainInputRef.value?.focus()
    return
  }


  // Auto-generate name if empty
  if (!payload.name || !payload.name.trim()) {
    const host = payload.ssh_host || payload.endpoint?.split(':')[0] || payload.interface
    payload.name = `Server ${host || new Date().toISOString().slice(0,10)}`
  }

  // For proxy servers, endpoint is just the IP (port comes from listen_port)
  if (isProxy && payload.endpoint && !payload.endpoint.includes(':')) {
    payload.endpoint = payload.endpoint  // keep as-is, API will add port
  }

  // Clean empty proxy fields
  if (!payload.proxy_domain) delete payload.proxy_domain
  if (!payload.proxy_cert_path) delete payload.proxy_cert_path
  if (!payload.proxy_key_path) delete payload.proxy_key_path
  if (!payload.proxy_obfs_password) delete payload.proxy_obfs_password

  // Reuse-keypair: API requires exactly 44 chars when present, so strip
  // an empty value rather than sending "" and tripping pydantic.
  if (!payload.private_key || !payload.private_key.trim()) {
    delete payload.private_key
  } else {
    payload.private_key = payload.private_key.trim()
  }

  // AmneziaWG obfuscation params: blank/null = "let the backend auto-generate".
  // Pydantic's ge=1 validators would reject `null` / `""` outright, so drop
  // them rather than sending falsy values that turn into 422s.
  for (const k of ['awg_jc','awg_jmin','awg_jmax','awg_s1','awg_s2','awg_h1','awg_h2','awg_h3','awg_h4']) {
    const v = payload[k]
    if (v === null || v === '' || (typeof v === 'number' && !Number.isFinite(v))) {
      delete payload[k]
    }
  }

  if (!payload.ssh_host) {
    delete payload.ssh_host
    delete payload.ssh_port
    delete payload.ssh_user
    delete payload.ssh_password
  }

  // Mikrotik mode: drop SSH fields entirely; keep mikrotik_* for the API.
  // SSH mode (or default): drop mikrotik_* so they don't show up as empty
  // strings in the payload (pydantic would still accept them but it's noise).
  if (payload.agent_mode === 'mikrotik') {
    delete payload.ssh_host
    delete payload.ssh_port
    delete payload.ssh_user
    delete payload.ssh_password
  } else {
    delete payload.mikrotik_url
    delete payload.mikrotik_username
    delete payload.mikrotik_password
  }

  try {
    // For proxy servers, attach a task_id for live progress streaming
    if (isProxy) {
      const tid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)
      bootstrapTaskId.value = tid
      payload.task_id = tid
      installProgress.value = t('servers.connecting') || 'Connecting...'
      pollBootstrapLogs(tid)
    } else if (isMikrotik) {
      installProgress.value = t('servers.connectingMikrotik') || 'Probing RouterOS API…'
    } else if (isRemote) {
      installProgress.value = t('servers.connectingSSH') || 'Connecting via SSH...'
    }

    const newServerData = await store.createServer(payload)

    // Stop polling, do one final sweep for any remaining log lines
    stopBootstrapPolling()
    if (bootstrapTaskId.value) {
      try {
        const finalSince = bootstrapLogs.value.length
        const { data } = await serversApi.getBootstrapLogs(bootstrapTaskId.value, finalSince)
        if (data.logs?.length) bootstrapLogs.value.push(...data.logs)
      } catch (_e) { /* ignore */ }
    }

    // For VPN remote servers, show agent installation progress (existing behaviour)
    if (isRemote && !isProxy && newServerData) {
      installProgress.value = t('servers.installingAgent') || 'Installing agent...'

      // Wait a bit for agent to start
      await new Promise(resolve => setTimeout(resolve, 2000))

      // Check agent status
      try {
        const { data } = await serversApi.get(newServerData.id)
        if (data.agent_mode === 'agent') {
          installProgress.value = t('servers.agentOnline') || '✅ Agent online!'
        } else {
          installProgress.value = t('servers.sshFallback') || '⚠️ Using SSH mode (agent install failed)'
        }
      } catch (e) {
        // Ignore status check error
      }

      // Wait to show result
      await new Promise(resolve => setTimeout(resolve, 1500))
    }

    // For proxy servers with logs — pause so user can read the output
    if (isProxy && bootstrapLogs.value.length) {
      await new Promise(resolve => setTimeout(resolve, 2500))
    }

    showAddModal.value = false
    installProgress.value = ''
    bootstrapLogs.value = []
    bootstrapTaskId.value = ''
    nameAutoGenerated.value = false
    newServer.value.private_key = ''
    reuseKeyOpen.value = false
    reuseObfuscationOpen.value = false
    addDetectOpen.value = false
    addDetectInput.value = ''
    addDetectMessage.value = ''
    addDetectOk.value = false
    addCopyFromServerId.value = null
    addCopyFromMessage.value = ''
    addCopyFromOk.value = false
    for (const k of ['awg_jc','awg_jmin','awg_jmax','awg_s1','awg_s2','awg_h1','awg_h2','awg_h3','awg_h4']) {
      newServer.value[k] = null
    }
    // Show success toast
    const createdName = newServerData?.name || payload.name || t('servers.addServer')
    const createdId = newServerData?.id
    serverCreatedToast.value = { name: createdName, id: createdId }
    setTimeout(() => { serverCreatedToast.value = null }, 8000)

  } catch (err) {
    stopBootstrapPolling()
    addError.value = err.response?.data?.detail || err.message
  } finally {
    addingServer.value = false
  }
}

async function discoverServer() {
  discoverError.value = ''
  discoverResult.value = ''
  discovering.value = true

  try {
    const { data } = await serversApi.discover(discoverData.value)
    discoverResult.value = `${data.message}. ${t('servers.clientsImported')}: ${data.clients_imported}`
    store.fetchServers()
  } catch (err) {
    discoverError.value = err.response?.data?.detail || err.message
  } finally {
    discovering.value = false
  }
}

function openInstallModal(serverId) {
  selectedServerId.value = serverId
  installMode.value = 'auto'
  customPort.value = 8001
  showInstallModal.value = true
}

async function checkAgentStatus(serverId, showAlert = false) {
  if (!serverId) return

  checkingStatus.value[serverId] = true

  try {
    const { data } = await serversApi.checkAgentStatus(serverId)

    agentStatuses.value[serverId] = {
      healthy: data.agent_healthy === true,
      mode: data.mode,
      agentUrl: data.agent_url,
      lastCheck: new Date()
    }

    // Show alert if requested (when user clicks Test Connection button)
    if (showAlert) {
      if (data.agent_healthy) {
        alert(`✅ ${t('servers.agentOnline') || 'Agent is online and responding!'}\n\n${data.agent_url}`)
      } else {
        alert(`❌ ${t('servers.agentOffline') || 'Agent is not responding'}\n\n${data.agent_url || 'No agent URL'}`)
      }
    }
  } catch (err) {
    agentStatuses.value[serverId] = {
      healthy: false,
      error: err.message,
      lastCheck: new Date()
    }

    if (showAlert) {
      alert(`❌ ${t('servers.agentCheckFailed') || 'Failed to check agent status'}\n\n${err.message}`)
    }
  } finally {
    checkingStatus.value[serverId] = false
  }
}

async function checkAllAgentStatuses() {
  // Check status for all servers in agent mode
  for (const server of store.servers) {
    if (server.agent_mode === 'agent') {
      await checkAgentStatus(server.id)
    }
  }
}

async function installAgent(serverId, port = 8001) {
  installingAgent.value[serverId] = true
  showInstallModal.value = false

  try {
    const { data} = await serversApi.installAgent(serverId, port)

    if (data.success) {
      // Show success message with port info
      const portInfo = data.port && data.port !== 8001 ? ` (port ${data.port})` : ''
      alert(t('servers.agentInstalled') || `✅ Agent installed successfully! Server is now 10x faster.${portInfo}`)

      // Refresh server list to update badge
      await store.fetchServers()

      // Check agent status after installation
      setTimeout(() => {
        checkAgentStatus(serverId)
      }, 2000)
    } else {
      // Show failure message
      alert(t('servers.agentInstallFailed') || `⚠️ Agent installation failed: ${data.message}`)
    }
  } catch (err) {
    const errorMsg = err.response?.data?.detail || err.message
    alert(t('servers.agentInstallError') || `❌ Error: ${errorMsg}`)
  } finally {
    installingAgent.value[serverId] = false
  }
}

function openAgentMenu(server) {
  agentServer.value = server
  showAgentModal.value = true
  // Auto-check status when opening
  if (!agentStatuses.value[server.id]) {
    checkAgentStatus(server.id)
  }
}

// ── Install Proxy on existing server ──────────────────────────────────────────
const showInstallProxyModal = ref(false)
const installProxyServer = ref(null)
const installingProxy = ref(false)
const cancellingProxy = ref(false)
const installProxyError = ref('')
const proxyInstallLogs = ref([])
const proxyLogBoxRef = ref(null)
let proxyPollingHandle = null
let proxyAbortController = null

const installProxyForm = reactive({
  protocol: 'hysteria2',
  tls_mode: 'self_signed',
  domain: '',
  port: null,
  obfs_password: '',
})

watch(proxyInstallLogs, () => {
  nextTick(() => {
    if (proxyLogBoxRef.value) {
      proxyLogBoxRef.value.scrollTop = proxyLogBoxRef.value.scrollHeight
    }
  })
}, { deep: true })

function openInstallProxyModal(server) {
  installProxyServer.value = server
  installProxyError.value = ''
  proxyInstallLogs.value = []
  installProxyForm.protocol = 'hysteria2'
  installProxyForm.tls_mode = 'self_signed'
  installProxyForm.domain = ''
  installProxyForm.port = null
  installProxyForm.obfs_password = ''
  showInstallProxyModal.value = true
}

async function doInstallProxy() {
  if (!installProxyServer.value) return
  installingProxy.value = true
  cancellingProxy.value = false
  installProxyError.value = ''
  proxyInstallLogs.value = []
  if (proxyPollingHandle) clearInterval(proxyPollingHandle)

  proxyAbortController = new AbortController()
  const tid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)

  // Start polling
  let since = 0
  proxyPollingHandle = setInterval(async () => {
    if (proxyAbortController?.signal?.aborted) {
      clearInterval(proxyPollingHandle); proxyPollingHandle = null
      return
    }
    try {
      const { data } = await serversApi.getBootstrapLogs(tid, since)
      if (data.logs?.length) {
        proxyInstallLogs.value.push(...data.logs)
        since = data.next_index
      }
      if (data.complete) {
        clearInterval(proxyPollingHandle)
        proxyPollingHandle = null
      }
    } catch (_e) {}
  }, 1200)

  try {
    const payload = {
      protocol: installProxyForm.protocol,
      tls_mode: installProxyForm.tls_mode,
      domain: installProxyForm.domain || undefined,
      port: installProxyForm.port || undefined,
      obfs_password: installProxyForm.obfs_password || undefined,
      task_id: tid,
    }
    await serversApi.installProxy(installProxyServer.value.id, payload, {
      signal: proxyAbortController.signal,
    })
    clearInterval(proxyPollingHandle)
    proxyPollingHandle = null
    // Final log sweep
    try {
      const { data } = await serversApi.getBootstrapLogs(tid, since)
      if (data.logs?.length) proxyInstallLogs.value.push(...data.logs)
    } catch (_e) {}

    await store.fetchServers()
    showInstallProxyModal.value = false
    const srvName = `${installProxyServer.value.name} — ${installProxyForm.protocol.toUpperCase()}`
    serverCreatedToast.value = { name: srvName, id: null }
    setTimeout(() => { serverCreatedToast.value = null }, 6000)
  } catch (err) {
    clearInterval(proxyPollingHandle)
    proxyPollingHandle = null
    if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED' || proxyAbortController?.signal?.aborted) {
      installProxyError.value = ''
      showInstallProxyModal.value = false
      setTimeout(() => { store.fetchServers() }, 5000)
    } else {
      installProxyError.value = err.response?.data?.detail || err.message
    }
  } finally {
    installingProxy.value = false
    cancellingProxy.value = false
    proxyAbortController = null
  }
}

function cancelInstallProxy() {
  if (!installingProxy.value) {
    showInstallProxyModal.value = false
    return
  }
  cancellingProxy.value = true
  if (proxyAbortController) {
    try { proxyAbortController.abort() } catch (_e) {}
  }
  if (proxyPollingHandle) {
    clearInterval(proxyPollingHandle)
    proxyPollingHandle = null
  }
}

// ── Install AWG on existing server ────────────────────────────────────────────
const showInstallAwgModal = ref(false)
const installAwgServer = ref(null)
const installingAwg = ref(false)
const cancellingAwg = ref(false)
const installAwgError = ref('')
const awgInstallLogs = ref([])
const awgLogBoxRef = ref(null)
let awgPollingHandle = null
let awgAbortController = null

const installAwgForm = reactive({
  interface: '',
  listen_port: null,
  address_pool_ipv4: '10.66.66.0/24',
  interfacePlaceholder: 'awg1 (auto)',
})

watch(awgInstallLogs, () => {
  nextTick(() => {
    if (awgLogBoxRef.value) {
      awgLogBoxRef.value.scrollTop = awgLogBoxRef.value.scrollHeight
    }
  })
}, { deep: true })

function openInstallAwgModal(server) {
  installAwgServer.value = server
  installAwgError.value = ''
  awgInstallLogs.value = []
  installAwgForm.interface = ''
  installAwgForm.listen_port = null
  installAwgForm.address_pool_ipv4 = '10.66.66.0/24'
  showInstallAwgModal.value = true
}

async function doInstallAwg() {
  if (!installAwgServer.value) return
  installingAwg.value = true
  cancellingAwg.value = false
  installAwgError.value = ''
  awgInstallLogs.value = []
  if (awgPollingHandle) clearInterval(awgPollingHandle)

  // AbortController so the user's Cancel button can actually interrupt
  // the in-flight install request. Backend will continue running its
  // bootstrap thread, but its except-block rolls back the partial DB row
  // on completion, so the panel won't show an orphan server.
  awgAbortController = new AbortController()

  const tid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)

  let since = 0
  awgPollingHandle = setInterval(async () => {
    if (awgAbortController?.signal?.aborted) {
      clearInterval(awgPollingHandle); awgPollingHandle = null
      return
    }
    try {
      const { data } = await serversApi.getBootstrapLogs(tid, since)
      if (data.logs?.length) {
        awgInstallLogs.value.push(...data.logs)
        since = data.next_index
      }
      if (data.complete) {
        clearInterval(awgPollingHandle)
        awgPollingHandle = null
      }
    } catch (_e) {}
  }, 1200)

  try {
    const payload = {
      interface: installAwgForm.interface || undefined,
      listen_port: installAwgForm.listen_port || undefined,
      address_pool_ipv4: installAwgForm.address_pool_ipv4 || undefined,
      task_id: tid,
    }
    await serversApi.installAwg(installAwgServer.value.id, payload, {
      signal: awgAbortController.signal,
    })
    clearInterval(awgPollingHandle)
    awgPollingHandle = null
    try {
      const { data } = await serversApi.getBootstrapLogs(tid, since)
      if (data.logs?.length) awgInstallLogs.value.push(...data.logs)
    } catch (_e) {}

    await store.fetchServers()
    showInstallAwgModal.value = false
    const srvName = `${installAwgServer.value.name} — AmneziaWG`
    serverCreatedToast.value = { name: srvName, id: null }
    setTimeout(() => { serverCreatedToast.value = null }, 6000)
  } catch (err) {
    clearInterval(awgPollingHandle)
    awgPollingHandle = null
    if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED' || awgAbortController?.signal?.aborted) {
      // User cancelled — backend will roll back the partial server record
      // when its install thread finishes. Just close the modal.
      installAwgError.value = ''
      showInstallAwgModal.value = false
      // Refresh in 5s to pick up any cleanup the backend did.
      setTimeout(() => { store.fetchServers() }, 5000)
    } else {
      installAwgError.value = err.response?.data?.detail || err.message
    }
  } finally {
    installingAwg.value = false
    cancellingAwg.value = false
    awgAbortController = null
  }
}

function cancelInstallAwg() {
  // If install is in flight, abort the request and tell the user the
  // backend is still cleaning up. Otherwise just close the modal as a
  // normal Cancel.
  if (!installingAwg.value) {
    showInstallAwgModal.value = false
    return
  }
  cancellingAwg.value = true
  if (awgAbortController) {
    try { awgAbortController.abort() } catch (_e) {}
  }
  if (awgPollingHandle) {
    clearInterval(awgPollingHandle)
    awgPollingHandle = null
  }
}

async function reinstallAgentFromMenu() {
  if (!agentServer.value) return
  showAgentModal.value = false
  openInstallModal(agentServer.value.id)
}

async function uninstallAgent(serverId) {
  if (!serverId) return
  if (!confirm(t('servers.deleteAgentConfirm') || 'Delete agent? Server will switch to SSH mode.')) return

  uninstallingAgent.value = true
  try {
    await serversApi.uninstallAgent(serverId)
    alert(t('servers.agentDeleted') || 'Agent deleted. Server switched to SSH mode.')
    await store.fetchServers()
    showAgentModal.value = false
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    uninstallingAgent.value = false
  }
}

// --- Bandwidth monitoring functions ---

async function fetchBandwidth(serverId) {
  try {
    const { data } = await serversApi.getBandwidth(serverId)
    bwData[serverId] = data
  } catch {
    // Server may be offline — silently skip
  }
}

async function fetchAllBandwidth() {
  const onlineServers = store.servers.filter(
    s => s.status === 'ONLINE' || s.status === 'online'
  )
  await Promise.allSettled(onlineServers.map(s => fetchBandwidth(s.id)))
}

function bwBarWidth(server) {
  const d = bwData[server.id]
  if (!d) return 0
  const rate = d.total_rate_mbps || 0
  if (server.max_bandwidth_mbps && server.max_bandwidth_mbps > 0) {
    return Math.min(100, (rate / server.max_bandwidth_mbps) * 100)
  }
  // No limit set — show a thin bar proportional to rate (cap at 100 Mbps visual)
  return Math.min(100, (rate / 100) * 100)
}

function bwBarClass(server) {
  const d = bwData[server.id]
  if (!d || !server.max_bandwidth_mbps) return 'bg-info'
  const pct = ((d.total_rate_mbps || 0) / server.max_bandwidth_mbps) * 100
  if (pct >= 90) return 'bg-danger'
  if (pct >= 70) return 'bg-warning'
  return 'bg-success'
}

async function toggleSplitTunnel(server) {
  togglingTunnel.value[server.id] = true
  try {
    await serversApi.update(server.id, { split_tunnel_support: !server.split_tunnel_support })
    await store.fetchServers()
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    togglingTunnel.value[server.id] = false
  }
}

function openBwSettings(server) {
  bwServerId.value = server.id
  bwServerName.value = server.name
  bwLimit.value = server.max_bandwidth_mbps || 0
  showBwModal.value = true
}

async function saveBwLimit() {
  if (!bwServerId.value) return
  savingBwLimit.value = true
  try {
    await serversApi.update(bwServerId.value, {
      max_bandwidth_mbps: bwLimit.value > 0 ? bwLimit.value : null
    })
    await store.fetchServers()
    showBwModal.value = false
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    savingBwLimit.value = false
  }
}

// --- Rename (display name) ---

function openRenameModal(server) {
  renameServerId.value = server.id
  renameServerInternalName.value = server.name
  renameDisplayName.value = server.display_name || ''
  showRenameModal.value = true
}

async function saveDisplayName() {
  if (!renameServerId.value) return
  savingDisplayName.value = true
  try {
    await serversApi.update(renameServerId.value, {
      display_name: renameDisplayName.value.trim() || null
    })
    await store.fetchServers()
    showRenameModal.value = false
  } catch (err) {
    alert('Error: ' + (err.response?.data?.detail || err.message))
  } finally {
    savingDisplayName.value = false
  }
}

// --- Expand address pool (grow CIDR without disrupting current clients) ---

const showExpandPoolModal = ref(false)
const expandPoolServer = ref(null)
const expandPoolInput = ref('')
const expandPoolError = ref('')
const expandPoolSuggested = ref('')
const expandPoolResult = ref(null)
const expandingPool = ref(false)

const expandPoolCurrentHosts = computed(() => {
  if (!expandPoolServer.value || !expandPoolServer.value.address_pool_ipv4) return '?'
  const m = String(expandPoolServer.value.address_pool_ipv4).match(/\/(\d+)$/)
  if (!m) return '?'
  const prefix = parseInt(m[1], 10)
  const total = Math.pow(2, 32 - prefix)
  return Math.max(0, total - 2).toLocaleString()
})

// Suggested presets that progressively widen common pool sizes. Filtered
// at render time to ones STRICTLY wider than the current pool.
const expandPoolPresets = computed(() => {
  if (!expandPoolServer.value) return []
  const cur = String(expandPoolServer.value.address_pool_ipv4 || '')
  const m = cur.match(/^(\d+)\.(\d+)\.(\d+)\.\d+\/(\d+)$/)
  if (!m) return []
  const [, a, b, c, p] = m
  const curPrefix = parseInt(p, 10)
  // Build candidates by zeroing the appropriate octets and dropping the prefix.
  const candidates = []
  if (curPrefix > 20) candidates.push(`${a}.${b}.${c & 0xf0 ? c : 0}.0/20`.replace(/\.\d+\.\d+\.0\/20$/, m => {
    // canonicalise third octet to its /20 boundary
    const c3 = parseInt(c, 10) & 0xf0
    return `.${b}.${c3}.0/20`
  }))
  // Simpler: just suggest /20, /16, /12 anchored at the current /a.b.0.0
  if (curPrefix > 20) candidates.push(`${a}.${b}.0.0/20`)
  if (curPrefix > 16) candidates.push(`${a}.${b}.0.0/16`)
  if (curPrefix > 12) candidates.push(`${a}.0.0.0/12`)
  // De-dupe
  return [...new Set(candidates)]
})

function openExpandPool(server) {
  expandPoolServer.value = server
  expandPoolInput.value = ''
  expandPoolError.value = ''
  expandPoolSuggested.value = ''
  expandPoolResult.value = null
  showExpandPoolModal.value = true
}
function closeExpandPool() {
  showExpandPoolModal.value = false
  // Don't clear `expandPoolServer` here — Vue's transition still references
  // it during the fade-out. It gets overwritten on next open.
}

async function submitExpandPool() {
  if (!expandPoolServer.value || !expandPoolInput.value.trim()) return
  expandingPool.value = true
  expandPoolError.value = ''
  expandPoolSuggested.value = ''
  try {
    const { data } = await serversApi.expandPool(
      expandPoolServer.value.id,
      expandPoolInput.value.trim()
    )
    expandPoolResult.value = data
    // Refresh server list so the new pool shows everywhere
    await store.fetchServers()
  } catch (err) {
    const detail = err.response?.data?.detail
    if (detail && typeof detail === 'object') {
      expandPoolError.value = detail.message || JSON.stringify(detail)
      if (detail.suggested) expandPoolSuggested.value = detail.suggested
    } else {
      expandPoolError.value = detail || err.message || String(err)
    }
  } finally {
    expandingPool.value = false
  }
}

// --- Export keypair (for cloning a server with the same WG identity) ---

function openExportKeypair(server) {
  exportKeypairServer.value = server
  keypairData.value = null
  keypairError.value = ''
  copiedField.value = ''
}
function closeExportKeypair() {
  exportKeypairServer.value = null
  keypairData.value = null
  keypairError.value = ''
}
async function confirmRevealKeypair() {
  if (!exportKeypairServer.value) return
  loadingKeypair.value = true
  keypairError.value = ''
  try {
    const { data } = await serversApi.getKeypair(exportKeypairServer.value.id)
    keypairData.value = data
  } catch (err) {
    keypairError.value = err.response?.data?.detail || err.message || 'Failed to fetch keypair'
  } finally {
    loadingKeypair.value = false
  }
}
async function copyToClipboard(text, field) {
  try {
    await navigator.clipboard.writeText(text || '')
    copiedField.value = field
    setTimeout(() => { if (copiedField.value === field) copiedField.value = '' }, 1500)
  } catch (_e) { /* ignore — admin can select manually */ }
}
function formatAwgParams(params) {
  if (!params) return ''
  return ['jc','jmin','jmax','s1','s2','h1','h2','h3','h4','mtu']
    .filter(k => params[k] != null)
    .map(k => `${k.padEnd(5)} = ${params[k]}`)
    .join('\n')
}

// --- Source-server candidates for "Copy from another AWG server" --------
// Edit-modal: list every OTHER AWG server in the panel that has at least
// h1-h4 populated. Sort same-keypair matches first since those are the
// "obvious right answer" for a migration.
const awgSourceCandidates = computed(() => {
  if (!editObfuscationServer.value) return []
  const self = editObfuscationServer.value
  return store.servers
    .filter(s =>
      s.id !== self.id &&
      (s.server_type || '') === 'amneziawg' &&
      s.awg_h1 != null && s.awg_h2 != null && s.awg_h3 != null && s.awg_h4 != null
    )
    .sort((a, b) => {
      // Same private/public keypair first (likely the migration source).
      const aMatch = a.public_key === self.public_key ? 0 : 1
      const bMatch = b.public_key === self.public_key ? 0 : 1
      if (aMatch !== bMatch) return aMatch - bMatch
      return (a.name || '').localeCompare(b.name || '')
    })
})

// Add-form: any AWG server with populated obfuscation params.
const addAwgSourceCandidates = computed(() => {
  return store.servers
    .filter(s =>
      (s.server_type || '') === 'amneziawg' &&
      s.awg_h1 != null && s.awg_h2 != null && s.awg_h3 != null && s.awg_h4 != null
    )
    .sort((a, b) => (a.name || '').localeCompare(b.name || ''))
})

function _copyAwgFromServer(srv, target) {
  // Returns count of fields copied. `target` is a reactive object (form).
  const mapping = {
    awg_jc: 'awg_jc', awg_jmin: 'awg_jmin', awg_jmax: 'awg_jmax',
    awg_s1: 'awg_s1', awg_s2: 'awg_s2',
    awg_h1: 'awg_h1', awg_h2: 'awg_h2', awg_h3: 'awg_h3', awg_h4: 'awg_h4',
  }
  let n = 0
  for (const [src, dest] of Object.entries(mapping)) {
    if (srv[src] != null) { target[dest] = srv[src]; n++ }
  }
  return n
}

function copyObfuscationFromServer() {
  copyFromMessage.value = ''
  copyFromOk.value = false
  const srv = store.servers.find(s => s.id === copyFromServerId.value)
  if (!srv) {
    copyFromMessage.value = t('servers.copyFailed') || 'Source server not found.'
    return
  }
  const n = _copyAwgFromServer(srv, obfuscationForm.value)
  copyFromOk.value = true
  copyFromMessage.value = (t('servers.copyOk') || 'Copied {n} values from {name} — review and save.')
    .replace('{n}', n).replace('{name}', srv.name)
}

function copyObfuscationFromServerForAdd() {
  addCopyFromMessage.value = ''
  addCopyFromOk.value = false
  const srv = store.servers.find(s => s.id === addCopyFromServerId.value)
  if (!srv) {
    addCopyFromMessage.value = t('servers.copyFailed') || 'Source server not found.'
    return
  }
  const n = _copyAwgFromServer(srv, newServer.value)
  addCopyFromOk.value = true
  addCopyFromMessage.value = (t('servers.copyOk') || 'Copied {n} values from {name} — review and Add Server.')
    .replace('{n}', n).replace('{name}', srv.name)
}

// --- Edit AWG obfuscation params ----------------------------------------
// The server response already carries awg_jc/jmin/jmax/s1/s2/h1-h4, so we
// can pre-fill the form directly from the card data — no extra fetch.
function openEditObfuscationModal(server) {
  editObfuscationServer.value = server
  obfuscationForm.value = {
    awg_jc:   server.awg_jc   ?? null,
    awg_jmin: server.awg_jmin ?? null,
    awg_jmax: server.awg_jmax ?? null,
    awg_s1:   server.awg_s1   ?? null,
    awg_s2:   server.awg_s2   ?? null,
    awg_h1:   server.awg_h1   ?? null,
    awg_h2:   server.awg_h2   ?? null,
    awg_h3:   server.awg_h3   ?? null,
    awg_h4:   server.awg_h4   ?? null,
  }
  obfuscationError.value = ''
  savingObfuscation.value = false
  obfuscationDetectOpen.value = false
  obfuscationDetectInput.value = ''
  obfuscationDetectMessage.value = ''
  obfuscationDetectOk.value = false
  copyFromServerId.value = null
  copyFromMessage.value = ''
  copyFromOk.value = false
}
function closeEditObfuscationModal() {
  if (savingObfuscation.value) return
  editObfuscationServer.value = null
  obfuscationError.value = ''
  obfuscationDetectInput.value = ''
  obfuscationDetectMessage.value = ''
  copyFromServerId.value = null
  copyFromMessage.value = ''
}

// Extract AmneziaWG obfuscation params from any AWG .conf text — works
// for both client AND server configs since both put Jc/Jmin/Jmax/S1/S2/
// H1-H4 in the [Interface] section. We only read up to the first [Peer]
// to avoid picking up stray digits from peer comments.
function parseAwgConfig(text) {
  if (!text || typeof text !== 'string') return null
  const ifaceSection = text.split(/^\s*\[Peer\]/m)[0]
  const keys = ['Jc','Jmin','Jmax','S1','S2','H1','H2','H3','H4']
  const out = {}
  for (const k of keys) {
    const re = new RegExp(`^\\s*${k}\\s*=\\s*(\\d+)\\s*$`, 'mi')
    const m = ifaceSection.match(re)
    if (m) out[k] = parseInt(m[1], 10)
  }
  // Need at least H1-H4 to be useful — those are the per-server-unique
  // bits. Jc/Jmin/Jmax/S1/S2 are constant defaults across most installs.
  if (out.H1 == null || out.H2 == null || out.H3 == null || out.H4 == null) return null
  return out
}

function detectObfuscationForNewServer() {
  addDetectMessage.value = ''
  addDetectOk.value = false
  const parsed = parseAwgConfig(addDetectInput.value)
  if (!parsed) {
    addDetectMessage.value = t('servers.detectFailed')
      || 'No H1-H4 found in [Interface] section. Make sure you pasted an AmneziaWG client config (not plain WireGuard).'
    return
  }
  const mapping = { Jc:'awg_jc', Jmin:'awg_jmin', Jmax:'awg_jmax', S1:'awg_s1', S2:'awg_s2',
                    H1:'awg_h1', H2:'awg_h2', H3:'awg_h3', H4:'awg_h4' }
  let filled = 0
  for (const [src, dest] of Object.entries(mapping)) {
    if (parsed[src] != null) { newServer.value[dest] = parsed[src]; filled++ }
  }
  addDetectOk.value = true
  addDetectMessage.value = (t('servers.detectOk') || 'Detected {n} values — review and Add Server.')
    .replace('{n}', filled)
}

function detectObfuscationFromInput() {
  obfuscationDetectMessage.value = ''
  obfuscationDetectOk.value = false
  const parsed = parseAwgConfig(obfuscationDetectInput.value)
  if (!parsed) {
    obfuscationDetectMessage.value = t('servers.detectFailed')
      || 'No H1-H4 found in [Interface] section. Make sure you pasted an AmneziaWG client config (not plain WireGuard).'
    return
  }
  // Map AWG config-style keys (H1) → form-style keys (awg_h1). Only
  // overwrite if the parser found a value — partial configs (just H1-H4)
  // keep the existing Jc/Jmin/etc.
  const mapping = { Jc:'awg_jc', Jmin:'awg_jmin', Jmax:'awg_jmax', S1:'awg_s1', S2:'awg_s2',
                    H1:'awg_h1', H2:'awg_h2', H3:'awg_h3', H4:'awg_h4' }
  let filled = 0
  for (const [src, dest] of Object.entries(mapping)) {
    if (parsed[src] != null) { obfuscationForm.value[dest] = parsed[src]; filled++ }
  }
  obfuscationDetectOk.value = true
  obfuscationDetectMessage.value = (t('servers.detectOk') || 'Detected {n} values — review and Save.')
    .replace('{n}', filled)
}
async function saveObfuscationParams() {
  if (!editObfuscationServer.value) return
  // Send every field — empty values are validated as "required" since
  // having one missing on the box would break handshakes. The backend
  // refuses h1-h4 < 1, so a 0/null value will be rejected with a clear
  // error before we touch the interface.
  const required = ['awg_h1','awg_h2','awg_h3','awg_h4','awg_jc','awg_jmin','awg_jmax','awg_s1','awg_s2']
  for (const k of required) {
    const v = obfuscationForm.value[k]
    if (v === null || v === '' || (typeof v === 'number' && !Number.isFinite(v))) {
      obfuscationError.value = (t('servers.obfuscationFieldRequired') || 'All fields must be set — leaving one blank would break handshakes.')
      return
    }
  }
  savingObfuscation.value = true
  obfuscationError.value = ''
  try {
    await store.updateServer(editObfuscationServer.value.id, { ...obfuscationForm.value })
    await store.fetchServers()
    editObfuscationServer.value = null
  } catch (err) {
    obfuscationError.value = err.response?.data?.detail || err.message || 'Failed to save obfuscation params'
  } finally {
    savingObfuscation.value = false
  }
}

// --- Migrate clients (move every client from server X to server Y) ---

const migrateCandidateServers = computed(() => {
  if (!migrateSourceServer.value) return []
  const srcType = migrateSourceServer.value.server_type || 'wireguard'
  return store.servers.filter(s =>
    s.id !== migrateSourceServer.value.id &&
    (s.server_type || 'wireguard') === srcType &&
    s.server_category !== 'proxy'
  )
})

// True if at least one candidate server shares the source's WireGuard
// keypair — we use this to surface a clear warning when none do, since
// migrating to a different-keypair host would silently break every
// client's existing config.
const migrateAnyKeypairMatches = computed(() => {
  if (!migrateSourceServer.value) return false
  const srcKey = migrateSourceServer.value.public_key
  return migrateCandidateServers.value.some(s => s.public_key === srcKey)
})

async function openMigrateClients(server) {
  migrateSourceServer.value = server
  migrateTargetId.value = null
  migrateSyncRemote.value = true
  migrateRemoveFromOld.value = true
  migrateKeepOnSource.value = false
  migrating.value = false
  migrateResult.value = null
  migrateError.value = ''
  migrateClientsFilter.value = ''
  migrateClientsList.value = []
  migrateSelectedIds.value = new Set()
  loadingMigrateClients.value = true
  try {
    const { data } = await serversApi.getClients(server.id)
    const clients = Array.isArray(data) ? data : (data.clients || [])
    migrateClientsList.value = clients
    // Default: every client selected so the modal behaves like the old
    // bulk-migrate when you just hit "Migrate now" without touching the list.
    migrateSelectedIds.value = new Set(clients.map(c => c.id))
  } catch (err) {
    migrateError.value = err.response?.data?.detail || err.message || 'Failed to load clients'
  } finally {
    loadingMigrateClients.value = false
  }
}
function closeMigrateClients() {
  migrateSourceServer.value = null
  migrateTargetId.value = null
  migrateResult.value = null
  migrateError.value = ''
  migrateClientsList.value = []
  migrateSelectedIds.value = new Set()
}

// Subset-vs-bulk: decide what to send.
const migrateSelectionMode = computed(() => {
  const total = migrateClientsList.value.length
  const sel = migrateSelectedIds.value.size
  if (total === 0 || sel === 0) return 'none'
  if (sel === total) return 'all'
  return 'subset'
})

const migrateFilteredClients = computed(() => {
  const q = migrateClientsFilter.value.trim().toLowerCase()
  if (!q) return migrateClientsList.value
  return migrateClientsList.value.filter(c =>
    (c.name || '').toLowerCase().includes(q) ||
    (c.ipv4 || '').toLowerCase().includes(q) ||
    String(c.id).includes(q)
  )
})

function toggleMigrateClient(id) {
  // Set is reactive in Vue 3 only via reassignment.
  const next = new Set(migrateSelectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  migrateSelectedIds.value = next
}
function selectAllMigrateClients() {
  migrateSelectedIds.value = new Set(migrateClientsList.value.map(c => c.id))
}
function deselectAllMigrateClients() {
  migrateSelectedIds.value = new Set()
}

async function runMigrate() {
  if (!migrateSourceServer.value || !migrateTargetId.value) return
  if (migrateSelectionMode.value === 'none') return
  migrating.value = true
  migrateError.value = ''
  try {
    const payload = {
      target_server_id: migrateTargetId.value,
      sync_to_remote: migrateSyncRemote.value,
      remove_from_old: migrateRemoveFromOld.value,
      keep_on_source: migrateKeepOnSource.value,
    }
    // Pass `client_ids` only when the user picked a subset — sending all IDs
    // explicitly would defeat the bulk-path's "no clients matched" early
    // exit and is harmless either way, but the subset case is the only one
    // the API treats specially.
    if (migrateSelectionMode.value === 'subset') {
      payload.client_ids = Array.from(migrateSelectedIds.value)
    }
    const { data } = await serversApi.migrateClients(migrateSourceServer.value.id, payload)
    migrateResult.value = data
    await store.fetchServers()
  } catch (err) {
    migrateError.value = err.response?.data?.detail || err.message || 'Migration failed'
  } finally {
    migrating.value = false
  }
}

// --- Backup/Restore ---

async function backupServer(server) {
  backingUp.value[server.id] = true
  try {
    const { data } = await serversApi.backup(server.id)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backup_${server.name}_${new Date().toISOString().slice(0,10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    alert('Backup error: ' + (err.response?.data?.detail || err.message))
  } finally {
    backingUp.value[server.id] = false
  }
}

function triggerRestore(server) {
  const input = restoreInputs.value[server.id]
  if (input) {
    input.value = ''
    input.click()
  }
}

async function restoreServer(server, event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!confirm(t('servers.restoreConfirm') || `Restore clients to "${server.name}" from backup?`)) return
  try {
    const { data } = await serversApi.restore(server.id, file)
    alert(data.message)
    await store.fetchServers()
  } catch (err) {
    alert('Restore error: ' + (err.response?.data?.detail || err.message))
  }
}

onMounted(async () => {
  await store.fetchServers()
  checkAllAgentStatuses()
  // Start bandwidth monitoring (every 5 seconds)
  fetchAllBandwidth()
  bwInterval = setInterval(fetchAllBandwidth, 5000)
})

onUnmounted(() => {
  if (bwInterval) {
    clearInterval(bwInterval)
    bwInterval = null
  }
  stopBootstrapPolling()
  if (proxyPollingHandle) {
    clearInterval(proxyPollingHandle)
    proxyPollingHandle = null
  }
})
</script>

<style scoped>
/* ── Bootstrap log box ──────────────────────────────────── */
.bootstrap-log-box {
  border: 1px solid var(--vxy-border, #dee2e6);
  border-radius: 8px;
  overflow: hidden;
  font-size: 0.78rem;
}
.bootstrap-log-box__header {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  background: var(--vxy-surface-hover, #f8f9fa);
  border-bottom: 1px solid var(--vxy-border, #dee2e6);
  color: var(--vxy-text, #212529);
}
.bootstrap-log-box__body {
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 12px;
  background: #0f172a;
  color: #94a3b8;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  scroll-behavior: smooth;
}
[data-theme="light"] .bootstrap-log-box__body {
  background: #1e293b;
  color: #cbd5e1;
}
.bootstrap-log-line {
  padding: 1px 0;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

/* ═══════════════════════════════════════════════════════
   SERVER CARD TOKENS
   ═══════════════════════════════════════════════════════ */

.srv-grid {
  --sc-bg:      #ffffff;
  --sc-border:  #e2e8f0;
  --sc-shadow:  0 1px 3px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.04);
  --sc-text:    #1e293b;
  --sc-muted:   #64748b;
  --sc-radius:  14px;
  --sc-bar-bg:  #e8ecf0;
}
[data-theme="dark"] .srv-grid {
  --sc-bg:      #1e293b;
  --sc-border:  rgba(255,255,255,.07);
  --sc-shadow:  0 1px 4px rgba(0,0,0,.35), 0 6px 20px rgba(0,0,0,.2);
  --sc-text:    #e2e8f0;
  --sc-muted:   #8892a4;
  --sc-bar-bg:  rgba(255,255,255,.08);
}

/* ── Grid layout ──────────────────────────────────────── */
.srv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

/* ── Card ─────────────────────────────────────────────── */
.srv-card {
  background: var(--sc-bg);
  border: 1px solid var(--sc-border);
  border-radius: var(--sc-radius);
  box-shadow: var(--sc-shadow);
  padding: 18px 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 11px;
  transition: box-shadow .18s, border-color .18s;
  position: relative;
}
.srv-card:hover { box-shadow: 0 4px 24px rgba(0,0,0,.09); }
[data-theme="dark"] .srv-card:hover { border-color: rgba(255,255,255,.12); }

/* ── Card header ──────────────────────────────────────── */
.srv-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.srv-card__identity { flex: 1; min-width: 0; }
.srv-card__name {
  font-size: .9375rem;
  font-weight: 600;
  color: var(--sc-text);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.srv-display-name {
  display: block;
  font-size: .75rem;
  color: var(--sc-text-muted, #6c757d);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}
.srv-card__badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 5px;
}
.srv-card__head-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* ── Protocol badges ──────────────────────────────────── */
.srv-proto {
  display: inline-flex;
  align-items: center;
  font-size: .67em;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  letter-spacing: .01em;
  line-height: 1.4;
}
.srv-proto--awg     { background: rgba(111,66,193,.13); color: #7c3aed; }
.srv-proto--hy2     { background: rgba(253,126,20,.13);  color: #c05621; }
.srv-proto--tuic    { background: rgba(32,201,151,.13);  color: #047857; }
.srv-proto--default { background: rgba(115,103,240,.12); color: var(--vxy-primary); }
[data-theme="dark"] .srv-proto--awg     { background: rgba(139,92,246,.18); color: #a78bfa; }
[data-theme="dark"] .srv-proto--hy2     { background: rgba(245,158,11,.18); color: #fcd34d; }
[data-theme="dark"] .srv-proto--tuic    { background: rgba(52,211,153,.18); color: #6ee7b7; }
[data-theme="dark"] .srv-proto--default { background: rgba(115,103,240,.18); color: #a5b4fc; }

/* ── Agent badge ──────────────────────────────────────── */
.srv-agent-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: .7em;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(115,103,240,.1);
  color: var(--vxy-primary);
  border: none;
  cursor: pointer;
  line-height: 1.4;
  transition: background .15s;
}
.srv-agent-badge:hover { background: rgba(115,103,240,.18); }
[data-theme="dark"] .srv-agent-badge { background: rgba(115,103,240,.18); }

/* Open circuit-breaker — agent is unreachable. The red wash plus the alert
   icon should be impossible to miss when scanning the server grid. */
.srv-agent-badge--down {
  background: rgba(234, 84, 85, 0.14);
  color: #d04848;
  animation: srv-agent-pulse 2.4s ease-in-out infinite;
}
.srv-agent-badge--down:hover { background: rgba(234, 84, 85, 0.22); }
[data-theme="dark"] .srv-agent-badge--down {
  background: rgba(234, 84, 85, 0.22);
  color: #ff7d7d;
}
@keyframes srv-agent-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(234, 84, 85, 0.0); }
  50%      { box-shadow: 0 0 0 4px rgba(234, 84, 85, 0.18); }
}

/* ── Unreachable-agent banner ─────────────────────────────
   Sits above the server grid; one line per dead agent with two action
   buttons (Switch to SSH / Retry now). Uses the page's warning palette. */
.agent-breaker-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  margin: 0 0 18px;
  background: rgba(255, 159, 67, 0.10);
  border: 1px solid rgba(255, 159, 67, 0.35);
  border-left: 4px solid #ff9f43;
  border-radius: 6px;
  color: var(--bs-body-color);
}
.agent-breaker-banner__icon {
  font-size: 1.4rem;
  color: #ff9f43;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}
.agent-breaker-banner__body { flex: 1; min-width: 0; }
.agent-breaker-banner__title {
  font-weight: 600;
  margin-bottom: 4px;
}
.agent-breaker-banner__text {
  font-size: .92em;
  opacity: 0.85;
  margin-bottom: 8px;
}
.agent-breaker-banner__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.agent-breaker-banner__list li {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.agent-breaker-banner__since {
  font-size: .85em;
  opacity: 0.7;
  margin-right: 6px;
}
[data-theme="dark"] .agent-breaker-banner {
  background: rgba(255, 159, 67, 0.12);
  border-color: rgba(255, 159, 67, 0.30);
}

/* ── Status badge ─────────────────────────────────────── */
.srv-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: .72em;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 20px;
  white-space: nowrap;
}
.srv-status__dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.srv-status--on { background: rgba(40,199,111,.12); color: var(--vxy-success); }
.srv-status--on .srv-status__dot {
  background: var(--vxy-success);
  box-shadow: 0 0 0 2px rgba(40,199,111,.25);
}
.srv-status--off { background: rgba(234,84,85,.1); color: var(--vxy-danger); }
.srv-status--off .srv-status__dot { background: var(--vxy-danger); }

/* ── Endpoint ─────────────────────────────────────────── */
.srv-card__endpoint {
  font-size: .82em;
  color: var(--sc-muted);
  margin-top: -4px;
}
.srv-card__endpoint code {
  background: transparent;
  padding: 0;
  font-size: inherit;
  color: inherit;
}

/* ── Stats row ────────────────────────────────────────── */
.srv-card__stats { display: flex; gap: 20px; flex-wrap: wrap; }
.srv-stat { display: flex; flex-direction: column; gap: 1px; }
.srv-stat--clickable { cursor: pointer; }
.srv-stat--clickable:hover .srv-stat__val { color: var(--vxy-primary); }
.srv-stat__val {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--sc-text);
  line-height: 1.2;
}
.srv-stat__val--md { font-size: .875rem; font-weight: 600; }
.srv-stat__of   { font-size: .65em; font-weight: 500; color: var(--sc-muted); }
.srv-stat__unit { font-size: .65em; font-weight: 500; color: var(--sc-muted); }
.srv-stat__lbl  { font-size: .72em; color: var(--sc-muted); }

/* ── Progress bars ────────────────────────────────────── */
.srv-bar-wrap { display: flex; align-items: center; gap: 8px; }
.srv-bar {
  flex: 1;
  height: 5px;
  background: var(--sc-bar-bg);
  border-radius: 3px;
  overflow: hidden;
}
.srv-bar__fill {
  height: 100%;
  background: var(--vxy-primary);
  border-radius: 3px;
  transition: width .4s ease;
  min-width: 2px;
}
.srv-bar__fill.bg-info    { background: var(--vxy-info); }
.srv-bar__fill.bg-success { background: var(--vxy-success); }
.srv-bar__fill.bg-warning { background: var(--vxy-warning); }
.srv-bar__fill.bg-danger  { background: var(--vxy-danger); }
.srv-bar__label { font-size: .72em; color: var(--sc-muted); white-space: nowrap; min-width: 2.6em; text-align: right; }

/* ── Details collapse ─────────────────────────────────── */
.srv-details { margin-top: -2px; }
.srv-details__toggle {
  list-style: none;
  cursor: pointer;
  font-size: .78em;
  color: var(--sc-muted);
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 0;
  user-select: none;
  transition: color .15s;
}
.srv-details__toggle::-webkit-details-marker { display: none; }
.srv-details__toggle:hover { color: var(--sc-text); }
.srv-details__chevron { flex-shrink: 0; transition: transform .2s ease; }
details[open] .srv-details__chevron { transform: rotate(180deg); }
.srv-details__body { display: flex; flex-direction: column; gap: 5px; padding: 8px 0 2px; }
.srv-detail-row { display: flex; align-items: baseline; gap: 10px; font-size: .8em; }
.srv-detail-key { color: var(--sc-muted); min-width: 60px; flex-shrink: 0; font-size: .92em; }
.srv-detail-val { color: var(--sc-text); background: transparent; padding: 0; font-size: inherit; }
.srv-consumers { margin-top: 4px; }
.srv-consumers__label { font-size: .76em; color: var(--sc-muted); margin-bottom: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: .02em; }
.srv-consumer { display: flex; justify-content: space-between; font-size: .78em; color: var(--sc-text); padding: 1px 0; }
.srv-consumer__rate { color: var(--sc-muted); }

/* ── Card actions ─────────────────────────────────────── */
.srv-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid var(--sc-border);
  margin-top: 1px;
}
.srv-card__actions .btn-sm { font-size: .8125em; }

/* ── Three-dot dropdown ───────────────────────────────── */
.srv-menu { position: relative; }
.srv-menu__btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--sc-muted);
  cursor: pointer;
  transition: background .15s, color .15s;
  flex-shrink: 0;
}
.srv-menu__btn:hover { background: rgba(0,0,0,.06); color: var(--sc-text); }
[data-theme="dark"] .srv-menu__btn:hover { background: rgba(255,255,255,.08); }
.srv-menu__drop {
  position: absolute;
  right: 0; top: calc(100% + 4px);
  background: var(--sc-bg);
  border: 1px solid var(--sc-border);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0,0,0,.13);
  min-width: 178px;
  z-index: 100;
  padding: 4px;
  animation: menu-in .12s ease;
}
[data-theme="dark"] .srv-menu__drop { box-shadow: 0 8px 32px rgba(0,0,0,.45); }
@keyframes menu-in {
  from { opacity: 0; transform: scale(.95) translateY(-4px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
.srv-menu__item {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: .82em;
  color: var(--sc-text);
  text-align: left;
  cursor: pointer;
  gap: 7px;
  transition: background .1s;
  white-space: nowrap;
}
.srv-menu__item:hover:not(:disabled) { background: rgba(0,0,0,.05); }
[data-theme="dark"] .srv-menu__item:hover:not(:disabled) { background: rgba(255,255,255,.07); }
.srv-menu__item:disabled { opacity: .45; cursor: default; }
.srv-menu__item--ok     { color: var(--vxy-success); }
.srv-menu__item--danger { color: var(--vxy-danger); }
.srv-menu__sep { height: 1px; background: var(--sc-border); margin: 3px 4px; }

/* ── Empty state ──────────────────────────────────────── */
.srv-empty {
  text-align: center;
  padding: 60px 20px;
}
.srv-empty__icon  { font-size: 2.5rem; margin-bottom: 12px; }
.srv-empty__title { font-size: 1.05rem; font-weight: 600; color: var(--sc-text, var(--vxy-heading)); margin-bottom: 8px; }
.srv-empty__desc  { color: var(--vxy-muted); font-size: .9rem; margin-bottom: 20px; }

/* ── Mobile ───────────────────────────────────────────── */
@media (max-width: 575px) {
  .srv-grid { grid-template-columns: 1fr; gap: 12px; }
  .srv-card { padding: 14px 14px 12px; gap: 10px; }
  .srv-stat__val { font-size: 1rem; }
  .srv-menu__drop { right: 0; min-width: 164px; }
}

/* ═══════════════════════════════════════════════════════
   LIGHT THEME (default)
   ═══════════════════════════════════════════════════════ */

/* ── Category / Protocol cards ────────────────────────── */
.add-card {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1.5px solid #e2e8f0;
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}
.add-card:hover { border-color: #a0aec0; }
.add-card--active-blue {
  border-color: #3b82f6;
  background: #eff6ff;
  box-shadow: 0 0 0 3px rgba(59,130,246,0.12);
}
.add-card--active-amber {
  border-color: #f59e0b;
  background: #fffbeb;
  box-shadow: 0 0 0 3px rgba(245,158,11,0.12);
}

/* ── Protocol card layout ─────────────────────────────── */
.proto-card { display: flex; flex-direction: column; cursor: pointer; }
.proto-card__name { line-height: 1.3; }
.proto-card__desc { margin-top: 6px; font-size: 0.78em; color: #6b7280; line-height: 1.4; }

/* ── Protocol badges ──────────────────────────────────── */
.proto-badge {
  display: inline-block;
  font-size: 0.68em;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.proto-badge--blue  { background: rgba(59,130,246,0.14); color: #1d4ed8; }
.proto-badge--cyan  { background: rgba(6,182,212,0.14);  color: #0e7490; }
.proto-badge--amber { background: rgba(245,158,11,0.18); color: #92400e; }

/* ── TLS segmented control ────────────────────────────── */
.tls-seg {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1.5px solid #d1d5db;
  background: #f9fafb;
}
.tls-seg__btn {
  flex: 1;
  padding: 11px 6px;
  border: none;
  background: transparent;
  font-size: 0.82em;
  font-weight: 500;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, transform 0.1s;
  border-right: 1px solid #d1d5db;
  line-height: 1.2;
}
.tls-seg__btn:last-child { border-right: none; }
.tls-seg__btn:hover:not(.tls-seg__btn--warn):not(.tls-seg__btn--ok) {
  background: #f0f2f4; color: #374151;
}
.tls-seg__btn--warn { background: #d97706; color: #fff; font-weight: 600; transform: scaleY(1.02); }
.tls-seg__btn--ok   { background: #059669; color: #fff; font-weight: 600; transform: scaleY(1.02); }

/* ── TLS dynamic hint ─────────────────────────────────── */
.tls-hint {
  margin-top: 5px;
  font-size: 0.77em;
  padding: 4px 8px;
  border-radius: 6px;
  line-height: 1.4;
}
.tls-hint--warn { background: #fef3c7; color: #92400e; }
.tls-hint--ok   { background: #f0fdf4; color: #166534; }

/* ── ACME requirements banner ─────────────────────────── */
.acme-banner {
  background: #eff6ff;
  border: 1px solid #93c5fd;
  border-left: 4px solid #3b82f6;
  border-radius: 6px;
  padding: 10px 14px;
}
.acme-banner__title {
  font-weight: 600;
  font-size: 0.82rem;
  color: #1e40af;
  margin-bottom: 5px;
}
.acme-banner__list {
  margin: 0;
  padding-left: 18px;
  font-size: 0.78rem;
  color: #1e3a8a;
  line-height: 1.6;
}
[data-theme="dark"] .acme-banner {
  background: rgba(59,130,246,0.1);
  border-color: rgba(59,130,246,0.4);
}
[data-theme="dark"] .acme-banner__title { color: #93c5fd; }
[data-theme="dark"] .acme-banner__list  { color: #bfdbfe; }

/* ── Quick Start ──────────────────────────────────────── */
.quick-start {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 9px 12px;
}
.quick-start__icon { font-size: 1em; flex-shrink: 0; line-height: 1.6; }
.quick-start__title {
  font-size: 0.78em;
  font-weight: 600;
  color: #0369a1;
  margin-bottom: 2px;
}
.quick-start__steps {
  font-size: 0.75em;
  color: #374151;
  line-height: 1.5;
}

/* ── Advanced collapsible ─────────────────────────────── */
.advanced-toggle {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 13px;
  background: #f8fafc;
  border: 1.5px dashed #cbd5e1;
  border-radius: 8px;
  font-size: 0.82em;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  user-select: none;
}
.advanced-toggle:hover { background: #f1f5f9; border-color: #94a3b8; }
.advanced-chevron { transition: transform 0.25s ease; color: #94a3b8; flex-shrink: 0; }
.advanced-chevron--open { transform: rotate(180deg); }
.advanced-body { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
.advanced-body--open { max-height: 700px; }

/* ── SSH section label ────────────────────────────────── */
.ssh-section-label {
  font-size: 0.78em;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ── Misc ──────────────────────────────────────────────── */
.info-pill {
  display: inline-block;
  background: #f0f9ff;
  color: #0369a1;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.8em;
}

/* ── Sticky modal footer ──────────────────────────────── */
.modal-footer--sticky {
  position: sticky;
  bottom: 0;
  z-index: 5;
  background: #fff;
  box-shadow: 0 -1px 0 rgba(0,0,0,0.07);
}
.btn-create-server {
  min-width: 155px;
  padding: 10px 20px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(115,103,240,0.35);
  transition: box-shadow 0.15s, transform 0.1s;
}
.btn-create-server:not(:disabled):hover {
  box-shadow: 0 4px 14px rgba(115,103,240,0.45);
  transform: translateY(-1px);
}
.btn-create-server:disabled { box-shadow: none; }

/* ── Success toast ─────────────────────────────────────── */
.server-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1090;
  background: #1e293b;
  color: #fff;
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.9em;
  box-shadow: 0 8px 32px rgba(0,0,0,0.25);
  min-width: 280px;
  max-width: 92vw;
  animation: toast-in 0.25s ease;
}
@keyframes toast-in {
  from { opacity: 0; transform: translateX(-50%) translateY(12px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* ── Touch targets (mobile) ───────────────────────────── */
@media (max-width: 575px) {
  .form-control { min-height: 44px; }
  .tls-seg__btn { min-height: 44px; }
  .add-card { padding: 12px; }
  .advanced-toggle { min-height: 44px; }
}

/* ═══════════════════════════════════════════════════════
   DARK THEME OVERRIDES
   ═══════════════════════════════════════════════════════ */

/* ── Cards ────────────────────────────────────────────── */
[data-theme="dark"] .add-card {
  background: #1e2a40;
  border-color: rgba(255,255,255,0.08);
}
[data-theme="dark"] .add-card:hover {
  border-color: rgba(255,255,255,0.18);
}
[data-theme="dark"] .add-card--active-blue {
  background: rgba(59,130,246,0.1);
  border-color: rgba(96,165,250,0.5);
  box-shadow: 0 0 0 3px rgba(59,130,246,0.08);
}
[data-theme="dark"] .add-card--active-amber {
  background: rgba(245,158,11,0.08);
  border-color: rgba(251,191,36,0.45);
  box-shadow: 0 0 0 3px rgba(245,158,11,0.07);
}
[data-theme="dark"] .proto-card__desc { color: #8892a4; }

/* ── Protocol badges ──────────────────────────────────── */
[data-theme="dark"] .proto-badge--blue  { background: rgba(59,130,246,0.18); color: #93c5fd; }
[data-theme="dark"] .proto-badge--cyan  { background: rgba(6,182,212,0.18);  color: #67e8f9; }
[data-theme="dark"] .proto-badge--amber { background: rgba(245,158,11,0.18); color: #fcd34d; }

/* ── TLS segmented control ────────────────────────────── */
[data-theme="dark"] .tls-seg {
  background: #1e2a40;
  border-color: rgba(255,255,255,0.1);
}
[data-theme="dark"] .tls-seg__btn {
  color: #8892a4;
  border-right-color: rgba(255,255,255,0.08);
}
[data-theme="dark"] .tls-seg__btn:hover:not(.tls-seg__btn--warn):not(.tls-seg__btn--ok) {
  background: rgba(255,255,255,0.05);
  color: #b4b7bd;
}

/* ── TLS hints ────────────────────────────────────────── */
[data-theme="dark"] .tls-hint--warn { background: rgba(146,64,14,0.25); color: #fcd34d; }
[data-theme="dark"] .tls-hint--ok   { background: rgba(6,95,70,0.25);   color: #6ee7b7; }

/* ── Quick Start ──────────────────────────────────────── */
[data-theme="dark"] .quick-start {
  background: rgba(3,105,161,0.12);
  border-color: rgba(147,197,253,0.15);
}
[data-theme="dark"] .quick-start__title { color: #7dd3fc; }
[data-theme="dark"] .quick-start__steps { color: #8892a4; }

/* ── Advanced toggle ──────────────────────────────────── */
[data-theme="dark"] .advanced-toggle {
  background: #1e2a40;
  border-color: rgba(255,255,255,0.1);
  color: #8892a4;
}
[data-theme="dark"] .advanced-toggle:hover {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.18);
}
[data-theme="dark"] .advanced-chevron { color: #676d7d; }

/* ── SSH section label ────────────────────────────────── */
[data-theme="dark"] .ssh-section-label { color: #676d7d; }

/* ── Info pill ────────────────────────────────────────── */
[data-theme="dark"] .info-pill {
  background: rgba(3,105,161,0.18);
  color: #7dd3fc;
}

/* ── Modal footer ─────────────────────────────────────── */
[data-theme="dark"] .modal-footer--sticky {
  background: #283046;
  box-shadow: 0 -1px 0 rgba(255,255,255,0.06);
}
.expand-pool-server { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: rgba(13, 110, 253, 0.06); border-radius: 8px; margin-bottom: 14px; font-size: 0.92rem; }
.expand-pool-server .mdi { color: #0d6efd; opacity: 0.8; }
.expand-pool-grid > div { padding: 10px 12px; background: rgba(0, 0, 0, 0.025); border-radius: 8px; }
.expand-pool-presets { display: flex; flex-wrap: wrap; gap: 6px; }
.expand-pool-presets .btn { font-family: 'JetBrains Mono', 'Menlo', monospace; font-size: 0.78rem; padding: 3px 10px; }

[data-theme="dark"] .expand-pool-server { background: rgba(99, 132, 253, 0.10); }
[data-theme="dark"] .expand-pool-server .mdi { color: #93b5ff; }
[data-theme="dark"] .expand-pool-grid > div { background: rgba(255, 255, 255, 0.04); }
[data-theme="dark"] .expand-pool-grid > div .text-muted { color: #adb5bd !important; }
</style>
