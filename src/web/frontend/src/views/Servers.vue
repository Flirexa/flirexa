<template>
  <div class="servers-page">
    <div class="d-flex flex-column flex-sm-row justify-content-between align-items-stretch align-items-sm-center gap-2 mb-4 mobile-toolbar">
      <h6 class="mb-0">{{ $t('servers.count', { count: store.servers.length }) }}</h6>
      <div class="d-flex gap-2 mobile-toolbar__actions">
        <button class="btn btn-outline-primary btn-sm" @click="showDiscoverModal = true">{{ $t('servers.discover') }}</button>
        <button class="btn btn-primary btn-sm" @click="showAddModal = true">{{ $t('servers.addServer') }}</button>
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
              <button v-if="server.agent_mode === 'agent'" class="srv-agent-badge" @click.stop="openAgentMenu(server)" title="Manage agent">
                <i class="mdi mdi-robot-outline"></i>
                <span v-if="checkingStatus[server.id]" class="spinner-border spinner-border-sm" style="width:.6em;height:.6em;border-width:1.5px"></span>
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
                <template v-if="server.server_category !== 'proxy'">
                  <button v-if="server.agent_mode === 'agent'" class="srv-menu__item"
                    @click="menuAction(() => openAgentMenu(server))"><i class="mdi mdi-robot-outline me-1"></i>{{ $t('servers.manageAgent') || 'Manage Agent' }}</button>
                  <button v-else class="srv-menu__item" @click="menuAction(() => openInstallModal(server.id))"
                    :disabled="installingAgent[server.id]"><i class="mdi mdi-robot-outline me-1"></i>{{ $t('servers.installAgent') || 'Install Agent' }}</button>
                  <button v-if="server.ssh_host" class="srv-menu__item"
                    @click="menuAction(() => openInstallProxyModal(server))"><i class="mdi mdi-web me-1"></i>{{ $t('servers.installProxy') || 'Install Proxy' }}</button>
                </template>
                <div class="srv-menu__sep"></div>
                <button class="srv-menu__item" @click="menuAction(() => openRenameModal(server))"><i class="mdi mdi-pencil-outline me-1"></i>{{ $t('servers.rename') || 'Rename (display)' }}</button>
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
                <div class="acme-banner__title"><i class="mdi mdi-lock me-1"></i>Let's Encrypt — требования</div>
                <ul class="acme-banner__list">
                  <li>Домен <strong>должен</strong> указывать на IP этого сервера (A-запись)</li>
                  <li>Порт <strong>80</strong> должен быть открыт (HTTP-01 challenge)</li>
                  <li>Сертификат получается автоматически при запуске — в логах будет виден весь процесс</li>
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

                  <!-- Location -->
                  <div class="mb-3">
                    <label class="form-label mb-1 small fw-medium">{{ $t('servers.locationOptional') }}</label>
                    <input v-model="newServer.location" type="text" class="form-control"
                           :placeholder="$t('servers.locationPlaceholder')" />
                  </div>

                  <!-- SSH -->
                  <div class="ssh-section-label mb-2">{{ $t('servers.sshRemote') }}</div>
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
            <button type="button" class="btn-close" @click="showInstallProxyModal = false" :disabled="installingProxy"></button>
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
            <button type="button" class="btn btn-secondary" @click="showInstallProxyModal = false" :disabled="installingProxy">{{ $t('common.cancel') }}</button>
            <button type="button" class="btn btn-success" @click="doInstallProxy" :disabled="installingProxy || (installProxyForm.tls_mode === 'acme' && !installProxyForm.domain)">
              <span v-if="installingProxy" class="spinner-border spinner-border-sm me-1"></span>
              <i class="mdi mdi-web me-1"></i>Install
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade show" v-if="showInstallProxyModal"></div>

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
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useServersStore } from '../stores/servers'
import { serversApi, systemApi } from '../api'

const { t } = useI18n()
const store = useServersStore()

// ── Server card helpers ────────────────────────────────────
const openMenuId = ref(null)
function isOnline(s) { return s.status === 'ONLINE' || s.status === 'online' }
function clientPct(s) { return s.max_clients ? Math.round((s.total_clients || 0) / s.max_clients * 100) : 0 }
function toggleMenu(id) { openMenuId.value = openMenuId.value === id ? null : id }
function menuAction(fn) { openMenuId.value = null; fn() }

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
  // Proxy fields
  proxy_domain: '',
  proxy_tls_mode: 'self_signed',
  proxy_cert_path: '',
  proxy_key_path: '',
  proxy_obfs_password: '',
})

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
    }
  }).catch(() => {}).finally(() => { detectingPublicIp.value = false })
}

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
  if (type === 'amneziawg') {
    if (!newServer.value.interface.startsWith('awg')) {
      const num = newServer.value.interface.replace(/\D/g, '') || '0'
      newServer.value.interface = `awg${num}`
    }
    if ([51820, 51821].includes(newServer.value.listen_port)) newServer.value.listen_port = 51820
  } else if (type === 'wireguard') {
    if (!newServer.value.interface.startsWith('wg')) {
      const num = newServer.value.interface.replace(/\D/g, '') || '1'
      newServer.value.interface = `wg${num}`
    }
    if ([51820].includes(newServer.value.listen_port)) newServer.value.listen_port = 51821
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
  const clientCount = server.client_count || 0
  let msg
  if (server.server_category === 'proxy') {
    msg = `Uninstall proxy "${server.name}"?\n\nThis will stop and remove the ${server.server_type === 'hysteria2' ? 'Hysteria 2' : 'TUIC'} service from the remote server and delete this server record.`
  } else {
    msg = `Delete server "${server.name}"?`
    if (clientCount > 0) {
      msg += `\n\nThis server has ${clientCount} client(s). All clients and their WireGuard configs will be permanently removed.`
    }
  }
  if (!confirm(msg)) return
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
  const isRemote = !!payload.ssh_host
  const isProxy = payload.server_category === 'proxy'

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

  if (!payload.ssh_host) {
    delete payload.ssh_host
    delete payload.ssh_port
    delete payload.ssh_user
    delete payload.ssh_password
  }

  try {
    // For proxy servers, attach a task_id for live progress streaming
    if (isProxy) {
      const tid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)
      bootstrapTaskId.value = tid
      payload.task_id = tid
      installProgress.value = t('servers.connecting') || 'Connecting...'
      pollBootstrapLogs(tid)
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
const installProxyError = ref('')
const proxyInstallLogs = ref([])
const proxyLogBoxRef = ref(null)
let proxyPollingHandle = null

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
  installProxyError.value = ''
  proxyInstallLogs.value = []
  if (proxyPollingHandle) clearInterval(proxyPollingHandle)

  const tid = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)

  // Start polling
  let since = 0
  proxyPollingHandle = setInterval(async () => {
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
    await serversApi.installProxy(installProxyServer.value.id, payload)
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
    installProxyError.value = err.response?.data?.detail || err.message
  } finally {
    installingProxy.value = false
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
</style>
