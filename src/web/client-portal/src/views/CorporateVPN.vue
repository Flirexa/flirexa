<template>
  <div>
    <!-- Page header -->
    <div class="d-flex flex-column flex-sm-row align-items-start align-items-sm-center justify-content-between gap-2 mb-4">
      <div>
        <h4 class="mb-0 fw-bold d-flex align-items-center gap-2">🏢 {{ $t('corpvpn.title') }}<HelpTooltip :text="$t('help.corpvpn')" /></h4>
        <p class="text-muted small mb-0">{{ $t('corpvpn.subtitle') }}</p>
      </div>
      <button v-if="!planBlocked" class="btn btn-primary" @click="showCreateNetwork = true">
        + {{ $t('corpvpn.createNetwork') }}
      </button>
      <a v-else href="/plans" class="btn btn-warning btn-sm">⬆ {{ $t('plans.upgrade') }}</a>
    </div>

    <!-- Plan upgrade notice -->
    <div v-if="planBlocked" class="alert alert-warning d-flex align-items-center gap-2">
      <span>🔒</span>
      <div>
        <strong>{{ $t('corpvpn.planRequired') }}</strong>
        <span class="ms-1">{{ $t('corpvpn.upgradeHint') }}</span>
      </div>
    </div>

    <div v-if="!loading && !planBlocked" class="alert alert-info d-flex align-items-start gap-2">
      <span>ℹ</span>
      <div class="small">
        <strong>{{ $t('corpvpn.routerModelTitle') }}</strong>
        {{ $t('corpvpn.routerModelHint') }}
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger alert-dismissible">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && networks.length === 0 && !planBlocked" class="card shadow-sm border-0">
      <div class="card-body text-center py-5">
        <div style="font-size:3rem">🌐</div>
        <h5 class="mt-3">{{ $t('corpvpn.noNetworks') }}</h5>
        <p class="text-muted">{{ $t('corpvpn.noNetworksHint') }}</p>
        <button class="btn btn-primary mt-2" @click="showCreateNetwork = true">
          + {{ $t('corpvpn.createNetwork') }}
        </button>
      </div>
    </div>

    <!-- Networks list -->
    <template v-else-if="!selectedNetwork">
      <div v-for="net in networks" :key="net.id" class="card shadow-sm border-0 mb-3">
        <div class="card-body">
          <div class="d-flex align-items-start justify-content-between">
            <div class="flex-grow-1 min-width-0">
              <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
                <span class="health-dot" :class="net.health?.health || net.status"></span>
                <h5 class="mb-0 fw-semibold">{{ net.name }}</h5>
                <span class="badge" :class="healthBadgeClass(net.health?.health || net.status)">
                  {{ net.health?.health || net.status }}
                </span>
              </div>
              <div class="text-muted small">
                <span class="me-3">🔗 {{ net.vpn_subnet }}</span>
                <span class="me-3">🖥 {{ net.active_site_count }}/{{ net.site_count }} sites</span>
                <span v-if="net.expires_at">📅 {{ formatDate(net.expires_at) }}</span>
              </div>
              <!-- Health issues preview -->
              <div v-if="net.health?.errors?.length" class="mt-1">
                <span v-for="e in net.health.errors.slice(0,2)" :key="e"
                  class="badge bg-danger-subtle text-danger me-1 small">⚠ {{ e }}</span>
              </div>
              <div v-else-if="net.health?.warnings?.length" class="mt-1">
                <span v-for="w in net.health.warnings.slice(0,2)" :key="w"
                  class="badge bg-warning-subtle text-warning-emphasis me-1 small">{{ w }}</span>
              </div>
            </div>
            <div class="d-flex gap-2 flex-shrink-0 ms-2">
              <button class="btn btn-sm btn-outline-primary" @click="openNetwork(net)">
                {{ $t('corpvpn.manage') }} →
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="confirmDeleteNetwork(net)">🗑</button>
            </div>
          </div>
          <!-- Site badges -->
          <div v-if="net.sites?.length" class="mt-2 d-flex gap-1 flex-wrap">
            <span v-for="site in net.sites" :key="site.id"
              class="badge rounded-pill d-flex align-items-center gap-1"
              :class="site.status === 'active' ? 'bg-success-subtle text-success' : 'bg-secondary-subtle text-secondary'"
              style="font-size:0.75rem">
              <span v-if="site.is_relay">⚡</span>{{ site.name }}
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- ════════ Network detail view ════════ -->
    <template v-else>
      <!-- Breadcrumb -->
      <div class="mb-3">
        <button class="btn btn-sm btn-outline-secondary" @click="closeNetwork">
          ← {{ $t('corpvpn.backToNetworks') }}
        </button>
      </div>

      <!-- Network header -->
      <div class="card shadow-sm border-0 mb-3">
        <div class="card-body">
          <div class="d-flex align-items-start justify-content-between flex-wrap gap-2">
            <div>
              <h5 class="mb-1 fw-bold d-flex align-items-center gap-2">
                <span class="health-dot lg" :class="networkHealth"></span>
                {{ selectedNetwork.name }}
              </h5>
              <div class="text-muted small">
                <span class="me-3">VPN: <code>{{ selectedNetwork.vpn_subnet }}</code></span>
                <span v-if="selectedNetwork.expires_at" class="me-3">Expires: {{ formatDate(selectedNetwork.expires_at) }}</span>
                <span class="badge" :class="statusBadge(selectedNetwork.status)">{{ selectedNetwork.status }}</span>
              </div>
            </div>
            <div class="d-flex gap-2 flex-wrap">
              <button class="btn btn-sm btn-outline-info" @click="runDiagnostics" :disabled="diagLoading">
                <span v-if="diagLoading" class="spinner-border spinner-border-sm me-1" role="status"></span>
                🩺 {{ diagLoading ? 'Running…' : ($t('corpvpn.diagnose')) }}<HelpTooltip :text="$t('help.diagnostics')" />
              </button>
              <button class="btn btn-sm btn-outline-secondary" @click="toggleEvents">
                📋 Events
              </button>
              <button class="btn btn-sm btn-primary" @click="showAddSite = true">
                + {{ $t('corpvpn.addSite') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Health summary (shows immediately from quick health or diag) -->
      <div v-if="quickHealth && (quickHealth.errors?.length || quickHealth.warnings?.length)"
        class="card shadow-sm border-0 mb-3"
        :class="quickHealth.errors?.length ? 'border-danger-subtle' : 'border-warning-subtle'">
        <div class="card-body py-3">
          <h6 class="fw-semibold mb-2">
            <span>{{ quickHealth.errors?.length ? '⛔' : '⚠️' }}</span>
            {{ $t('corpvpn.networkIssues') }}
          </h6>
          <ul class="mb-0 ps-3 small">
            <li v-for="e in quickHealth.errors" :key="e" class="text-danger mb-1">{{ e }}</li>
            <li v-for="w in quickHealth.warnings" :key="w" class="text-warning-emphasis mb-1">{{ w }}</li>
          </ul>
        </div>
      </div>

      <!-- Event log (collapsible) -->
      <div v-if="showEventLog" class="card shadow-sm border-0 mb-3">
        <div class="card-body py-3">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <h6 class="fw-semibold mb-0">📋 {{ $t('corpvpn.eventLog') }}</h6>
            <button class="btn btn-sm btn-link p-0 text-muted" @click="showEventLog = false">✕</button>
          </div>
          <div v-if="eventsLoading" class="text-center py-2">
            <div class="spinner-border spinner-border-sm"></div>
          </div>
          <div v-else-if="!events.length" class="text-muted small text-center py-2">{{ $t('corpvpn.noEventsYet') }}</div>
          <div v-else class="event-log">
            <div v-for="ev in events" :key="ev.id"
              class="event-row d-flex gap-2 align-items-start py-2 border-bottom">
              <span class="event-icon flex-shrink-0">{{ eventIcon(ev.event_type, ev.severity) }}</span>
              <div class="flex-grow-1 min-width-0">
                <div class="small">{{ localizeCorpMessage(ev.description) }}</div>
                <div class="text-muted" style="font-size:0.72rem">{{ formatDatetime(ev.created_at) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Enhanced SVG Network map -->
      <div v-if="selectedNetwork.sites?.length > 1" class="card shadow-sm border-0 mb-3">
        <div class="card-body p-0">
          <!-- Map toolbar -->
          <div class="d-flex align-items-center justify-content-between px-3 pt-3 pb-2">
            <h6 class="fw-semibold mb-0">🗺 {{ $t('corpvpn.networkMap') }}</h6>
            <div class="map-controls">
              <button class="map-ctrl-btn" @click="mapZoomBy(1.25)" title="Zoom in">+</button>
              <button class="map-ctrl-btn" @click="mapZoomBy(0.8)" title="Zoom out">−</button>
              <button class="map-ctrl-btn" @click="mapFit" title="Fit to screen">⊡</button>
              <button class="map-ctrl-btn" @click="mapReset" title="Reset">↺</button>
            </div>
          </div>

          <!-- Canvas -->
          <div class="map-canvas" ref="mapContainerRef"
            @wheel.prevent="onMapWheel"
            @mousedown="onMapMouseDown"
            @mousemove="onMapMouseMove"
            @mouseup="onMapMouseUp"
            @mouseleave="onMapMouseUp"
            @touchstart="onMapTouchStart"
            @touchend="onMapTouchEnd"
            :class="{ 'is-dragging': mapDragging }">
            <svg width="100%" height="100%"
              :viewBox="`0 0 ${MAP_W} ${MAP_H}`"
              xmlns="http://www.w3.org/2000/svg"
              preserveAspectRatio="xMidYMid meet">

              <defs>
                <pattern id="mapDots" width="32" height="32" patternUnits="userSpaceOnUse">
                  <circle cx="16" cy="16" r="1.2" fill="currentColor" fill-opacity="0.1"/>
                </pattern>
                <filter id="glow-healthy" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b"/>
                  <feColorMatrix in="b" type="matrix" values="0 0 0 0 0.1 0 0 0 0 0.83 0 0 0 0 0.33 0 0 0 0.5 0" result="c"/>
                  <feMerge><feMergeNode in="c"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <filter id="glow-warning" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b"/>
                  <feColorMatrix in="b" type="matrix" values="0 0 0 0 1 0 0 0 0 0.76 0 0 0 0 0 0 0 0 0.45 0" result="c"/>
                  <feMerge><feMergeNode in="c"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <filter id="glow-error" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b"/>
                  <feColorMatrix in="b" type="matrix" values="0 0 0 0 0.86 0 0 0 0 0.21 0 0 0 0 0.27 0 0 0 0.45 0" result="c"/>
                  <feMerge><feMergeNode in="c"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <filter id="glow-relay" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="b"/>
                  <feColorMatrix in="b" type="matrix" values="0 0 0 0 0.99 0 0 0 0 0.49 0 0 0 0 0.08 0 0 0 0.65 0" result="c"/>
                  <feMerge><feMergeNode in="c"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <filter id="glow-conn" x="-10%" y="-100%" width="120%" height="300%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="b"/>
                  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
              </defs>

              <!-- Background grid -->
              <rect width="100%" height="100%" fill="url(#mapDots)" @click="selectedNode = null" style="cursor:default"/>

              <!-- Pan/zoom group -->
              <g :transform="mapTransformStr">

                <!-- Connections (rendered below nodes) -->
                <line v-for="conn in mapConnections" :key="conn.key"
                  :x1="conn.x1" :y1="conn.y1" :x2="conn.x2" :y2="conn.y2"
                  :stroke="connStroke(conn)"
                  :stroke-width="connWidth(conn)"
                  :stroke-opacity="connOpacity(conn)"
                  :stroke-dasharray="connDash(conn)"
                  :class="{ 'relay-flow': conn.via_relay }"
                  stroke-linecap="round"
                  :filter="conn.health === 'healthy' && !conn.via_relay ? 'url(#glow-conn)' : undefined"
                />

                <!-- Nodes -->
                <g v-for="node in mapNodes" :key="node.id"
                  :transform="`translate(${node.x}, ${node.y})`"
                  class="map-node"
                  :class="{ 'map-node--sel': selectedNode?.id === node.id }"
                  @click.stop="onNodeClick(node)">

                  <!-- Relay outer dashed ring -->
                  <circle v-if="node.is_relay" r="46"
                    fill="none" stroke="#f97316" stroke-width="2"
                    stroke-dasharray="6 3" stroke-opacity="0.85"
                    filter="url(#glow-relay)"/>

                  <!-- Pulse ring (healthy/unknown) -->
                  <circle v-if="node.health === 'healthy' || node.health === 'unknown'"
                    r="36" fill="none" :stroke="nodeStrokeColor(node)"
                    stroke-width="1.5" class="pulse-ring"/>

                  <!-- Glow status ring -->
                  <circle r="34" fill="none"
                    :stroke="nodeStrokeColor(node)" stroke-width="2" stroke-opacity="0.4"
                    :filter="nodeGlowFilter(node) ? `url(#glow-${nodeGlowFilter(node)})` : undefined"/>

                  <!-- Main body -->
                  <circle r="28"
                    :fill="nodeStrokeColor(node)" fill-opacity="0.15"
                    :stroke="nodeStrokeColor(node)" stroke-width="2.5"
                    :filter="nodeGlowFilter(node) ? `url(#glow-${nodeGlowFilter(node)})` : undefined"/>

                  <!-- Selection highlight -->
                  <circle v-if="selectedNode?.id === node.id" r="28"
                    :fill="nodeStrokeColor(node)" fill-opacity="0.15"/>

                  <!-- Icon -->
                  <text y="8" text-anchor="middle" dominant-baseline="middle"
                    font-size="20" style="user-select:none;pointer-events:none">{{ node.is_relay ? '⚡' : '🖥' }}</text>

                  <!-- Status dot top-right -->
                  <circle cx="21" cy="-21" r="6"
                    :fill="nodeStatusDot(node)"
                    stroke="var(--vxy-card-bg,#fff)" stroke-width="1.5"/>

                  <!-- Name -->
                  <text y="50" text-anchor="middle" font-size="12" font-weight="600"
                    fill="currentColor" style="user-select:none;pointer-events:none">{{ node.name }}</text>

                  <!-- VPN IP -->
                  <text y="64" text-anchor="middle" font-size="9.5"
                    fill="currentColor" fill-opacity="0.55"
                    style="user-select:none;pointer-events:none;font-family:monospace">{{ node.vpn_ip }}</text>

                  <!-- RELAY badge -->
                  <g v-if="node.is_relay">
                    <rect x="-22" y="72" width="44" height="15" rx="7.5" fill="#f97316" fill-opacity="0.9"/>
                    <text x="0" y="83" text-anchor="middle" font-size="9" fill="white" font-weight="700"
                      style="user-select:none;pointer-events:none">RELAY</text>
                  </g>
                </g>

              </g>
            </svg>
          </div>

          <!-- Selected node detail panel -->
          <transition name="node-detail">
            <div v-if="selectedNode" class="map-detail-panel px-3 py-2">
              <div class="d-flex align-items-start justify-content-between gap-2">
                <div class="flex-grow-1 min-width-0">
                  <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
                    <strong class="small">{{ selectedNode.name }}</strong>
                    <span v-if="selectedNode.is_relay" class="badge bg-warning text-dark" style="font-size:.68rem">⚡ Relay</span>
                    <span class="badge" :class="healthBadgeClass(selectedNode.health)">{{ selectedNode.health || 'unknown' }}</span>
                  </div>
                  <div class="small text-muted d-flex gap-3 flex-wrap">
                    <span>VPN: <code class="small">{{ selectedNode.vpn_ip }}</code></span>
                    <span v-if="selectedNode.endpoint">Endpoint: <code class="small">{{ selectedNode.endpoint }}</code></span>
                    <span v-if="selectedNode.routing_mode && selectedNode.routing_mode !== 'auto'">Mode: {{ selectedNode.routing_mode }}</span>
                  </div>
                  <div v-if="selectedNode.local_subnets?.length" class="small mt-1">
                    <span class="text-muted me-1">Subnets:</span>
                    <code v-for="s in selectedNode.local_subnets" :key="s" class="small me-1">{{ s }}</code>
                  </div>
                </div>
                <button class="btn btn-sm btn-link text-muted p-0 flex-shrink-0" @click="selectedNode = null">✕</button>
              </div>
            </div>
          </transition>

          <!-- Legend -->
          <div class="d-flex gap-3 px-3 pb-3 pt-1 flex-wrap align-items-center">
            <span class="d-flex align-items-center gap-1"><span class="ldot" style="background:#198754"></span><span class="text-muted" style="font-size:.75rem">Healthy</span></span>
            <span class="d-flex align-items-center gap-1"><span class="ldot" style="background:#ffc107"></span><span class="text-muted" style="font-size:.75rem">Warning</span></span>
            <span class="d-flex align-items-center gap-1"><span class="ldot" style="background:#dc3545"></span><span class="text-muted" style="font-size:.75rem">Error</span></span>
            <span class="d-flex align-items-center gap-1"><span class="ldot" style="background:#6c757d"></span><span class="text-muted" style="font-size:.75rem">Unknown</span></span>
            <span class="d-flex align-items-center gap-1"><span class="ldot" style="background:#f97316"></span><span class="text-muted" style="font-size:.75rem">Relay</span></span>
            <span class="d-flex align-items-center gap-1">
              <span style="display:inline-block;width:18px;border-bottom:2px dashed #f97316;vertical-align:middle"></span>
              <span class="text-muted" style="font-size:.75rem">Via relay</span>
            </span>
            <span class="text-muted ms-auto" style="font-size:.72rem">Scroll/pinch to zoom · Drag to pan</span>
          </div>
        </div>
      </div>

      <!-- Full diagnostics results -->
      <div v-if="diagResults" class="card shadow-sm border-0 mb-3">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-3">
            <div>
              <h6 class="fw-semibold mb-0">
                🩺 Diagnostics
                <span class="badge ms-2" :class="healthBadgeClass(diagResults.health)">
                  {{ (diagResults.health || '').toUpperCase() }}
                </span>
              </h6>
              <div class="text-muted" style="font-size:0.75rem">{{ formatDatetime(diagResults.ran_at) }}</div>
            </div>
            <button class="btn btn-sm btn-outline-secondary" @click="diagResults = null">✕</button>
          </div>

          <!-- Network-level issues -->
          <div v-if="diagResults.errors?.length || diagResults.warnings?.length" class="mb-3">
            <div v-for="e in diagResults.errors" :key="e" class="diag-issue error small mb-1">⛔ {{ e }}</div>
            <div v-for="w in diagResults.warnings" :key="w" class="diag-issue warning small mb-1">⚠️ {{ w }}</div>
          </div>

          <!-- Relay topology (if relay present) -->
          <div v-if="diagResults.has_relay" class="mb-3 p-2 rounded" style="background:rgba(253,126,20,0.07);border:1px solid rgba(253,126,20,0.25)">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span>⚡</span>
              <span class="fw-semibold small">{{ $t('corpvpn.relayNodeLabel') }}: {{ diagResults.relay_site_name }}</span>
            </div>
            <div class="small text-muted">
              {{ $t('corpvpn.relaySummary') }}
            </div>
          </div>

          <!-- Per-site -->
          <div v-for="site in diagResults.sites" :key="site.site_id" class="site-diag-block mb-2">
            <div class="d-flex align-items-center gap-2 mb-1 flex-wrap">
              <span class="health-dot" :class="site.status"></span>
              <span class="fw-semibold small">{{ site.site_name }}</span>
              <span v-if="site.is_relay" class="badge bg-warning text-dark" style="font-size:0.7rem">⚡ relay</span>
              <span v-if="site.routing_mode && site.routing_mode !== 'auto'" class="badge bg-info-subtle text-info" style="font-size:0.7rem">{{ site.routing_mode }}</span>
              <span v-if="site.behind_nat" class="badge bg-secondary-subtle text-secondary" style="font-size:0.7rem">behind NAT</span>
              <code class="small">{{ site.vpn_ip }}</code>
              <span v-if="site.endpoint" class="text-muted small">{{ site.endpoint }}</span>
              <span v-if="site.endpoint_resolved_ip" class="text-success small">(→ {{ site.endpoint_resolved_ip }})</span>
              <span v-if="site.endpoint_is_private" class="badge bg-warning-subtle text-warning small">private IP</span>
            </div>
            <div class="ps-3 small">
              <div v-for="e in site.errors" :key="e" class="diag-issue error mb-1">⛔ {{ localizeCorpMessage(e) }}</div>
              <div v-for="w in site.warnings" :key="w" class="diag-issue warning mb-1">⚠️ {{ localizeCorpMessage(w) }}</div>
              <div class="mt-1 text-muted">
                <span v-if="site.config_downloaded" class="text-success me-2">✓ {{ $t('corpvpn.configDownloaded') }}</span>
                <span v-else class="text-warning me-2">⚠ {{ $t('corpvpn.configNotDownloaded') }}</span>
                <span v-if="!site.has_local_subnets" class="text-muted">{{ $t('corpvpn.noSubnetsConfigured') }}</span>
              </div>
              <!-- Peer matrix -->
              <div v-if="site.peers?.length" class="mt-2">
                <div class="text-muted mb-1" style="font-size:0.8rem">{{ $t('corpvpn.peerConnections') }}</div>
                <div v-for="peer in site.peers" :key="peer.peer_id"
                  class="d-flex align-items-center gap-2 mb-1 peer-row flex-wrap">
                  <span class="health-dot sm" :class="peer.status"></span>
                  <span>→ <strong>{{ peer.peer_name }}</strong></span>
                  <span v-if="peer.peer_is_relay" class="badge bg-warning text-dark" style="font-size:0.68rem">⚡ relay</span>
                  <span v-if="peer.uses_relay" class="badge bg-orange-subtle" style="font-size:0.68rem;background:rgba(253,126,20,0.12);color:#c85a00">via relay: {{ peer.relay_name }}</span>
                  <span v-if="peer.nat_detected && !peer.uses_relay" class="badge bg-secondary-subtle text-secondary" style="font-size:0.68rem">{{ $t('corpvpn.behindNat') }}</span>
                  <span v-if="peer.peer_has_endpoint && peer.peer_endpoint_dns_ok" class="text-success">✓ {{ $t('corpvpn.endpointOk') }}</span>
                  <span v-else-if="peer.peer_has_endpoint && !peer.peer_endpoint_dns_ok" class="text-danger">✗ {{ $t('corpvpn.dnsFail') }}</span>
                  <span v-else-if="!peer.peer_has_endpoint && !peer.uses_relay" class="text-muted">{{ $t('corpvpn.noEndpointShort') }}</span>
                  <span v-if="peer.bidirectional_endpoints" class="text-success">↔</span>
                  <span v-if="peer.issues?.length" class="text-danger" :title="peer.issues.map(localizeCorpMessage).join('; ')">⚠ {{ localizeCorpMessage(peer.issues[0]) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sites list -->
      <h6 class="fw-semibold mb-2">{{ $t('corpvpn.sites') }}</h6>

      <div v-if="!selectedNetwork.sites?.length" class="card shadow-sm border-0 mb-3">
        <div class="card-body text-center py-4 text-muted">
          <div style="font-size:2rem">🏠</div>
          <div class="mt-2">{{ $t('corpvpn.noSites') }}</div>
        </div>
      </div>

      <div v-for="site in selectedNetwork.sites" :key="site.id" class="card shadow-sm border-0 mb-2">
        <div class="card-body py-3">
          <div class="d-flex align-items-start gap-3">
            <div class="site-icon">🖥</div>
            <div class="flex-grow-1 min-width-0">
              <div class="d-flex align-items-center gap-2 flex-wrap">
                <span class="fw-semibold">{{ site.name }}</span>
                <span class="badge" :class="site.status === 'active' ? 'bg-success' : 'bg-secondary'">{{ site.status }}</span>
                <span v-if="site.is_relay" class="badge bg-warning text-dark">⚡ Relay</span>
                <span v-if="site.routing_mode && site.routing_mode !== 'auto'" class="badge bg-info-subtle text-info">{{ site.routing_mode }}</span>
                <code class="small">{{ site.vpn_ip }}</code>
                <span v-if="getSiteDiag(site.id)" class="badge" :class="healthBadgeClass(getSiteDiag(site.id).status)">
                  {{ getSiteDiag(site.id).status }}
                </span>
              </div>
              <div class="text-muted small mt-1">
                <div v-if="site.suggested_interface" class="mb-1">
                  <span class="text-muted me-1">{{ $t('corpvpn.interfaceLabel') }}:</span>
                  <code class="text-primary">{{ site.suggested_interface }}</code>
                  <span class="text-muted ms-1" style="font-size:0.78rem">{{ $t('corpvpn.interfaceSaveAs') }} <code>/etc/wireguard/{{ site.suggested_interface }}.conf</code></span>
                </div>
                <div>{{ $t('corpvpn.portLabel') }}: <code>{{ site.listen_port }}</code></div>
                <div v-if="site.endpoint">Endpoint: <code>{{ site.endpoint }}</code></div>
                <div v-else class="text-muted">{{ $t('corpvpn.endpointNotSetHint') }}</div>
                <div v-if="site.local_subnets?.length">
                  {{ $t('corpvpn.advertisesLabel') }}: <code v-for="s in site.local_subnets" :key="s" class="me-1">{{ s }}</code>
                </div>
                <div v-else class="text-muted">{{ $t('corpvpn.noAdvertisedSubnets') }}</div>
                <div v-if="site.config_downloaded_at" class="text-success">
                  ✓ {{ $t('corpvpn.configDownloaded') }} {{ formatDate(site.config_downloaded_at) }}
                </div>
                <div v-else class="text-warning">⚠ {{ $t('corpvpn.configNotDownloadedYet') }}</div>
              </div>
              <!-- Site diag errors inline (after diag run) -->
              <div v-if="getSiteDiag(site.id)?.errors?.length" class="mt-1">
                <span v-for="e in getSiteDiag(site.id).errors.slice(0,2)" :key="e"
                  class="badge bg-danger-subtle text-danger me-1 small">{{ localizeCorpMessage(e) }}</span>
              </div>
            </div>
            <div class="d-flex flex-column gap-1 flex-shrink-0">
              <button class="btn btn-sm btn-outline-primary" @click="downloadConfig(site)">⬇ Config</button>
              <button class="btn btn-sm btn-outline-secondary" @click="startEditSite(site)">✏ Edit</button>
              <button class="btn btn-sm btn-outline-warning" @click="confirmRegenKeys(site)">🔑 Regen</button>
              <button class="btn btn-sm btn-outline-danger" @click="confirmDeleteSite(site)">🗑</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="selectedNetwork.sites?.length > 1" class="alert alert-info small mt-2">
        ℹ {{ $t('corpvpn.regenNote') }}
      </div>
    </template>

    <!-- ── Modals ─────────────────────────────────────────────────────────── -->

    <!-- Create network -->
    <div v-if="showCreateNetwork" class="modal-overlay" @click.self="showCreateNetwork = false">
      <div class="modal-card">
        <h5 class="fw-bold mb-3">{{ $t('corpvpn.createNetwork') }}</h5>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.networkName') }}</label>
          <input v-model="newNetworkName" class="form-control"
            :placeholder="$t('corpvpn.networkNamePlaceholder')"
            @keyup.enter="createNetwork" />
        </div>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="showCreateNetwork = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="createNetwork" :disabled="actionLoading || !newNetworkName.trim()">
            {{ actionLoading ? '...' : ($t('corpvpn.create')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Add site -->
    <div v-if="showAddSite" class="modal-overlay" @click.self="showAddSite = false">
      <div class="modal-card" style="max-width:520px">
        <h5 class="fw-bold mb-1">{{ $t('corpvpn.addSite') }}</h5>
        <p class="text-muted small mb-3">{{ $t('corpvpn.addSiteHint') }}</p>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.siteName') }} <span class="text-muted fw-normal">{{ $t('corpvpn.optional') }}</span></label>
          <input v-model="newSite.name" class="form-control" :placeholder="$t('corpvpn.autoNamePlaceholder')" />
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold d-flex align-items-center">{{ $t('corpvpn.localSubnets') }}&nbsp;<span class="text-muted fw-normal">{{ $t('corpvpn.optional') }}</span><HelpTooltip :text="$t('help.localSubnets')" /></label>
          <div v-for="(_, i) in newSite.subnets" :key="i" class="d-flex gap-2 mb-2">
            <input v-model="newSite.subnets[i]" class="form-control form-control-sm" placeholder="192.168.1.0/24" />
            <button v-if="newSite.subnets.length > 1" class="btn btn-sm btn-outline-danger"
              @click="newSite.subnets.splice(i,1)">✕</button>
          </div>
          <button class="btn btn-sm btn-outline-secondary" @click="newSite.subnets.push('')">{{ $t('corpvpn.addSubnet') }}</button>
          <div class="form-text">{{ $t('corpvpn.subnetHint') }}</div>
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold d-flex align-items-center">{{ $t('corpvpn.endpoint') }}&nbsp;<span class="text-muted fw-normal">{{ $t('corpvpn.endpointOptionalHint') }}</span><HelpTooltip :text="$t('help.endpoint')" /></label>
          <input v-model="newSite.endpoint" class="form-control" placeholder="1.2.3.4:51821" />
          <div class="form-text">{{ $t('corpvpn.endpointHint') }}</div>
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.routingModeLabel') }}</label>
          <select v-model="newSite.routing_mode" class="form-select form-select-sm">
            <option value="auto">{{ $t('corpvpn.routingAutoNew') }}</option>
            <option value="direct">{{ $t('corpvpn.routingDirect') }}</option>
            <option value="via_relay">{{ $t('corpvpn.routingViaRelay') }}</option>
          </select>
          <div class="form-text">{{ $t('corpvpn.routingModeHint') }}</div>
        </div>
        <div class="mb-3 form-check">
          <input type="checkbox" class="form-check-input" id="newSiteRelay" v-model="newSite.is_relay" />
          <label class="form-check-label small" for="newSiteRelay">
            ⚡ {{ $t('corpvpn.relayLabel') }}<HelpTooltip :text="$t('help.relayNode')" />
            <span class="text-muted d-block" style="font-size:0.78rem">{{ $t('corpvpn.relayHint') }}</span>
          </label>
        </div>
        <div class="alert alert-info small py-2 mb-3">
          💡 {{ $t('corpvpn.autoPortHint') }}
        </div>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="showAddSite = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="addSite" :disabled="actionLoading">
            {{ actionLoading ? '...' : ($t('corpvpn.addSite')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edit site -->
    <div v-if="editSite" class="modal-overlay" @click.self="editSite = null">
      <div class="modal-card" style="max-width:520px">
        <h5 class="fw-bold mb-3">{{ $t('corpvpn.editSite') }}</h5>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.siteName') }}</label>
          <input v-model="editForm.name" class="form-control" />
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.localSubnets') }}</label>
          <div v-for="(_, i) in editForm.subnets" :key="i" class="d-flex gap-2 mb-2">
            <input v-model="editForm.subnets[i]" class="form-control form-control-sm" placeholder="192.168.1.0/24" />
            <button v-if="editForm.subnets.length > 1" class="btn btn-sm btn-outline-danger"
              @click="editForm.subnets.splice(i,1)">✕</button>
          </div>
          <button class="btn btn-sm btn-outline-secondary" @click="editForm.subnets.push('')">{{ $t('corpvpn.addSubnet') }}</button>
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.endpoint') }}</label>
          <input v-model="editForm.endpoint" class="form-control" placeholder="203.0.113.5:51820" />
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.listenPort') }}</label>
          <input v-model.number="editForm.listen_port" type="number" class="form-control" min="1" max="65535" />
        </div>
        <div class="mb-3">
          <label class="form-label small fw-semibold">{{ $t('corpvpn.routingModeLabel') }}</label>
          <select v-model="editForm.routing_mode" class="form-select form-select-sm">
            <option value="auto">{{ $t('corpvpn.routingAutoEdit') }}</option>
            <option value="direct">{{ $t('corpvpn.routingDirectEdit') }}</option>
            <option value="via_relay">{{ $t('corpvpn.routingViaRelay') }}</option>
          </select>
        </div>
        <div class="mb-3 form-check">
          <input type="checkbox" class="form-check-input" id="editSiteRelay" v-model="editForm.is_relay" />
          <label class="form-check-label small" for="editSiteRelay">
            ⚡ Relay node — acts as hub for NAT'd sites
            <span class="text-muted d-block" style="font-size:0.78rem">Requires a public endpoint. Only one relay per network.</span>
          </label>
        </div>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="editSite = null">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveSiteEdit" :disabled="actionLoading">
            {{ actionLoading ? '...' : ($t('common.save')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete network -->
    <div v-if="deleteNetworkTarget" class="modal-overlay" @click.self="deleteNetworkTarget = null">
      <div class="modal-card">
        <h5 class="fw-bold mb-2 text-danger">{{ $t('corpvpn.deleteNetwork') }}</h5>
        <p>{{ $t('corpvpn.deleteNetworkConfirm') }}</p>
        <p class="fw-semibold">{{ deleteNetworkTarget.name }}</p>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="deleteNetworkTarget = null">{{ $t('common.cancel') }}</button>
          <button class="btn btn-danger" @click="deleteNetwork" :disabled="actionLoading">
            {{ actionLoading ? '...' : ($t('common.delete')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete site -->
    <div v-if="deleteSiteTarget" class="modal-overlay" @click.self="deleteSiteTarget = null">
      <div class="modal-card">
        <h5 class="fw-bold mb-2 text-danger">{{ $t('corpvpn.deleteSite') }}</h5>
        <p>{{ $t('corpvpn.deleteSiteConfirm') }}</p>
        <p class="fw-semibold">{{ deleteSiteTarget.name }} ({{ deleteSiteTarget.vpn_ip }})</p>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="deleteSiteTarget = null">{{ $t('common.cancel') }}</button>
          <button class="btn btn-danger" @click="deleteSite" :disabled="actionLoading">{{ actionLoading ? '...' : ($t('common.delete')) }}</button>
        </div>
      </div>
    </div>

    <!-- Regen keys -->
    <div v-if="regenSiteTarget" class="modal-overlay" @click.self="regenSiteTarget = null">
      <div class="modal-card">
        <h5 class="fw-bold mb-2 d-flex align-items-center gap-2">{{ $t('corpvpn.regenKeys') }}<HelpTooltip :text="$t('help.regenKeys')" /></h5>
        <div class="alert alert-warning small mb-3">
          ⚠ {{ $t('corpvpn.regenWarning') }}
        </div>
        <p class="fw-semibold">{{ regenSiteTarget.name }}</p>
        <div class="d-flex gap-2 justify-content-end">
          <button class="btn btn-outline-secondary" @click="regenSiteTarget = null">{{ $t('common.cancel') }}</button>
          <button class="btn btn-warning" @click="regenKeys" :disabled="actionLoading">
            {{ actionLoading ? '...' : ($t('corpvpn.regenKeys')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast" class="corp-toast" :class="toast.type">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api/index.js'

const { t } = useI18n()

// ── State ─────────────────────────────────────────────────────────────────────
const networks      = ref([])
const loading       = ref(false)
const actionLoading = ref(false)
const error         = ref('')
const planBlocked   = ref(false)
const toast         = ref(null)

const selectedNetwork = ref(null)
const quickHealth     = ref(null)
const diagResults     = ref(null)
const diagLoading     = ref(false)

const showEventLog  = ref(false)
const events        = ref([])
const eventsLoading = ref(false)

const showCreateNetwork = ref(false)
const newNetworkName    = ref('')

const showAddSite = ref(false)
const newSite     = ref({ name: '', subnets: [''], endpoint: '', listen_port: 51820, is_relay: false, routing_mode: 'auto' })

const editSite = ref(null)
const editForm = ref({ name: '', subnets: [''], endpoint: '', listen_port: 51820, is_relay: false, routing_mode: 'auto' })

const relayTopology = ref(null)

// ── Map state ─────────────────────────────────────────────────────────────────
const MAP_W = 1000, MAP_H = 580
const mapContainerRef = ref(null)
const mapPan   = ref({ x: 0, y: 0 })
const mapScale = ref(1)
const mapDragging  = ref(false)
const mapDragStart = ref(null)
const mapPinchStart = ref(null)
const selectedNode = ref(null)

const mapTransformStr = computed(() =>
  `translate(${mapPan.value.x},${mapPan.value.y}) scale(${mapScale.value})`)

const deleteNetworkTarget = ref(null)
const deleteSiteTarget    = ref(null)
const regenSiteTarget     = ref(null)

// ── Computed ──────────────────────────────────────────────────────────────────
const networkHealth = computed(() => {
  if (diagResults.value) return diagResults.value.health
  if (quickHealth.value) return quickHealth.value.health
  return selectedNetwork.value?.status || 'unknown'
})

const mapNodes = computed(() => {
  if (!selectedNetwork.value?.sites) return []
  const sites = selectedNetwork.value.sites.filter(s => s.status === 'active')
  const n = sites.length
  if (n === 0) return []
  const cx = MAP_W / 2, cy = MAP_H / 2
  let positions
  if (n === 1) {
    positions = [{ x: cx, y: cy }]
  } else if (n === 2) {
    positions = [{ x: cx - 195, y: cy }, { x: cx + 195, y: cy }]
  } else {
    const r = n <= 3 ? 168 : n <= 5 ? 182 : n <= 8 ? 198 : 215
    positions = sites.map((_, i) => ({
      x: Math.round(cx + r * Math.cos((2 * Math.PI * i / n) - Math.PI / 2)),
      y: Math.round(cy + r * Math.sin((2 * Math.PI * i / n) - Math.PI / 2)),
    }))
  }
  return sites.map((site, i) => {
    const sd = getSiteDiag(site.id)
    return {
      id: site.id,
      name: site.name.length > 14 ? site.name.slice(0, 13) + '…' : site.name,
      vpn_ip: site.vpn_ip,
      is_relay: site.is_relay || false,
      health: sd ? sd.status : (site.status === 'active' ? 'unknown' : 'inactive'),
      endpoint: site.endpoint || null,
      local_subnets: site.local_subnets || [],
      routing_mode: site.routing_mode || 'auto',
      x: positions[i].x,
      y: positions[i].y,
    }
  })
})

const mapConnections = computed(() => {
  const nodes = mapNodes.value
  const conns = []
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j]
      let health = 'healthy', via_relay = false
      if (diagResults.value) {
        const aDiag = getSiteDiag(a.id)
        const bDiag = getSiteDiag(b.id)
        const aPeer = aDiag?.peers?.find(p => p.peer_id === b.id)
        const bPeer = bDiag?.peers?.find(p => p.peer_id === a.id)
        const statuses = [aPeer?.status, bPeer?.status].filter(Boolean)
        if (statuses.includes('error')) health = 'error'
        else if (statuses.includes('warning')) health = 'warning'
        if (aPeer?.uses_relay) via_relay = true
      }
      conns.push({ key: `${i}-${j}`, x1: a.x, y1: a.y, x2: b.x, y2: b.y, health, via_relay })
    }
  }
  return conns
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  toast.value = { msg, type }
  setTimeout(() => { toast.value = null }, 3000)
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatDatetime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function statusBadge(status) {
  return { active: 'bg-success', suspended: 'bg-warning', expired: 'bg-danger' }[status] || 'bg-secondary'
}

function healthBadgeClass(health) {
  return { healthy: 'bg-success', warning: 'bg-warning text-dark', error: 'bg-danger', inactive: 'bg-secondary' }[health] || 'bg-secondary'
}

function localizeCorpMessage(message) {
  if (!message) return message

  const exact = {
    "Network has no sites — add at least 2 to establish connectivity": t('corpvpn.msg.networkNoSites'),
    "Network needs at least 2 active sites for VPN connectivity": t('corpvpn.msg.networkNeedsTwoActive'),
    "No sites added yet": t('corpvpn.msg.noSitesAddedYet'),
    "Needs at least 2 active sites for VPN connectivity": t('corpvpn.msg.needsTwoActiveQuick'),
    "No sites have a public endpoint — add an endpoint to at least one site to enable connections": t('corpvpn.msg.noPublicEndpointsQuick'),
    "No public endpoint configured — peer sites cannot initiate connections here (outbound only)": t('corpvpn.msg.noPublicEndpointOutboundOnly'),
    "No local subnets configured — this site won't advertise any routes to peers": t('corpvpn.msg.noLocalSubnets'),
    "Missing WireGuard keys — regenerate keys for this site": t('corpvpn.msg.missingKeys'),
    "Config has not been downloaded yet — site is not deployed": t('corpvpn.msg.configNotDownloadedYet'),
    "Relay node must have a public endpoint — without it, NAT'd sites cannot reach the relay": t('corpvpn.msg.relayNeedsEndpoint'),
  }
  if (exact[message]) return exact[message]

  let m
  if ((m = message.match(/^Subscription expired on (\d{4}-\d{2}-\d{2})$/))) {
    return t('corpvpn.msg.subscriptionExpiredOn', { date: m[1] })
  }
  if ((m = message.match(/^Site '(.+)' has errors$/))) {
    return t('corpvpn.msg.siteHasErrors', { site: m[1] })
  }
  if ((m = message.match(/^Site '(.+)' has warnings$/))) {
    return t('corpvpn.msg.siteHasWarnings', { site: m[1] })
  }
  if ((m = message.match(/^(\d+) site\(s\) have not downloaded their config$/))) {
    return t('corpvpn.msg.sitesConfigNotDownloadedQuick', { count: m[1] })
  }
  if ((m = message.match(/^(\d+) site\(s\) config not downloaded: (.+)$/))) {
    return t('corpvpn.msg.sitesConfigNotDownloaded', { count: m[1], names: m[2] })
  }
  if ((m = message.match(/^(\d+) site\(s\) have no endpoint and no relay is configured — direct tunnels between these sites will not work$/))) {
    return t('corpvpn.msg.natSitesNoRelay', { count: m[1] })
  }
  if ((m = message.match(/^(\d+) peer connection\(s\) have configuration errors$/))) {
    return t('corpvpn.msg.peerErrors', { count: m[1] })
  }
  if ((m = message.match(/^(\d+) peer connection\(s\) have warnings$/))) {
    return t('corpvpn.msg.peerWarnings', { count: m[1] })
  }
  if ((m = message.match(/^Neither site has a public endpoint — traffic will be routed through relay '(.+)'$/))) {
    return t('corpvpn.msg.neitherSiteEndpointViaRelay', { relay: m[1] })
  }
  if (message === "Neither this site nor the peer has an endpoint and no relay is available — WireGuard tunnel cannot be established") {
    return t('corpvpn.msg.neitherSiteEndpointNoRelay')
  }
  if ((m = message.match(/^Peer '(.+)' has no public endpoint — this site cannot initiate connection to it$/))) {
    return t('corpvpn.msg.peerNoEndpoint', { peer: m[1] })
  }
  if ((m = message.match(/^Peer '(.+)' has no public endpoint — traffic routed through relay '(.+)'$/))) {
    return t('corpvpn.msg.peerNoEndpointViaRelay', { peer: m[1], relay: m[2] })
  }
  if ((m = message.match(/^Peer '(.+)' has no local subnets — only VPN IP will be routed, no LAN access through the tunnel$/))) {
    return t('corpvpn.msg.peerNoLocalSubnets', { peer: m[1] })
  }
  if ((m = message.match(/^Endpoint '(.+)' does not resolve — check hostname \/ IP address$/))) {
    return t('corpvpn.msg.endpointNotResolve', { endpoint: m[1] })
  }
  if ((m = message.match(/^Peer endpoint '(.+)' does not resolve — check hostname or IP$/))) {
    return t('corpvpn.msg.peerEndpointNotResolve', { endpoint: m[1] })
  }
  if ((m = message.match(/^Endpoint resolves to private IP (.+) — may not be reachable from remote sites \(NAT issue\?\)$/))) {
    return t('corpvpn.msg.endpointPrivateIp', { ip: m[1] })
  }
  if ((m = message.match(/^Peer endpoint resolves to private IP (.+) — may not be reachable from remote sites \(possible NAT issue\)$/))) {
    return t('corpvpn.msg.peerEndpointPrivateIp', { ip: m[1] })
  }
  if ((m = message.match(/^No public endpoint — outbound only; traffic to\/from other NAT'd sites will route through relay '(.+)'$/))) {
    return t('corpvpn.msg.noPublicEndpointViaRelay', { relay: m[1] })
  }
  if ((m = message.match(/^Network is '(.+)'$/))) {
    return t('corpvpn.msg.networkStatus', { status: m[1] })
  }
  if ((m = message.match(/^Site is '(.+)' — disabled by administrator$/))) {
    return t('corpvpn.msg.siteStatusDisabled', { status: m[1] })
  }

  return message
}

// ── Map visual helpers ────────────────────────────────────────────────────────
function nodeStrokeColor(node) {
  if (node.is_relay) return '#f97316'
  return { healthy: '#198754', warning: '#ffc107', error: '#dc3545',
           inactive: '#6c757d', unknown: 'var(--vxy-primary,#5865f2)' }[node.health] || '#6c757d'
}
function nodeStatusDot(node) {
  if (node.is_relay) return '#f97316'
  return { healthy: '#198754', warning: '#ffc107', error: '#dc3545',
           inactive: '#6c757d', unknown: '#adb5bd' }[node.health] || '#adb5bd'
}
function nodeGlowFilter(node) {
  if (node.is_relay) return 'relay'
  return { healthy: 'healthy', warning: 'warning', error: 'error' }[node.health] || null
}
function connStroke(conn) {
  if (conn.via_relay) return '#f97316'
  return { healthy: 'var(--vxy-primary,#5865f2)', warning: '#ffc107', error: '#dc3545' }[conn.health] || 'var(--vxy-primary,#5865f2)'
}
function connWidth(conn) { return conn.health === 'error' ? 2.5 : 2 }
function connOpacity(conn) {
  return conn.health === 'error' ? 0.8 : conn.health === 'warning' ? 0.65 : conn.via_relay ? 0.55 : 0.5
}
function connDash(conn) {
  if (conn.via_relay) return '10 6'
  if (conn.health === 'error') return '6 3'
  if (conn.health === 'warning') return '5 3'
  return 'none'
}

// ── Map interaction ────────────────────────────────────────────────────────────
function clientToVBox(clientX, clientY) {
  const el = mapContainerRef.value
  if (!el) return { x: clientX, y: clientY }
  const r = el.getBoundingClientRect()
  return { x: (clientX - r.left) * (MAP_W / r.width), y: (clientY - r.top) * (MAP_H / r.height) }
}
function mapZoomBy(factor, cx = MAP_W / 2, cy = MAP_H / 2) {
  const ns = Math.max(0.25, Math.min(5, mapScale.value * factor))
  const ratio = ns / mapScale.value
  mapPan.value = { x: cx - (cx - mapPan.value.x) * ratio, y: cy - (cy - mapPan.value.y) * ratio }
  mapScale.value = ns
}
function mapFit() { mapPan.value = { x: 0, y: 0 }; mapScale.value = 1 }
function mapReset() { mapPan.value = { x: 0, y: 0 }; mapScale.value = 1; selectedNode.value = null }

function onMapWheel(e) {
  const pt = clientToVBox(e.clientX, e.clientY)
  mapZoomBy(e.deltaY < 0 ? 1.12 : 0.89, pt.x, pt.y)
}
function onMapMouseDown(e) {
  if (e.button !== 0) return
  e.preventDefault()
  mapDragging.value = true
  const pt = clientToVBox(e.clientX, e.clientY)
  mapDragStart.value = { vx: pt.x, vy: pt.y, px: mapPan.value.x, py: mapPan.value.y }
}
function onMapMouseMove(e) {
  if (!mapDragging.value || !mapDragStart.value) return
  const pt = clientToVBox(e.clientX, e.clientY)
  mapPan.value = {
    x: mapDragStart.value.px + (pt.x - mapDragStart.value.vx),
    y: mapDragStart.value.py + (pt.y - mapDragStart.value.vy),
  }
}
function onMapMouseUp() { mapDragging.value = false; mapDragStart.value = null }

function onMapTouchStart(e) {
  if (e.touches.length === 1) {
    mapDragging.value = true
    const pt = clientToVBox(e.touches[0].clientX, e.touches[0].clientY)
    mapDragStart.value = { vx: pt.x, vy: pt.y, px: mapPan.value.x, py: mapPan.value.y }
  } else if (e.touches.length === 2) {
    mapDragging.value = false; mapDragStart.value = null
    const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2
    const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2
    mapPinchStart.value = {
      dist: Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY),
      scale: mapScale.value, cx, cy, px: mapPan.value.x, py: mapPan.value.y,
    }
  }
}
function onMapTouchMoveHandler(e) {
  e.preventDefault()
  if (e.touches.length === 1 && mapDragging.value && mapDragStart.value) {
    const pt = clientToVBox(e.touches[0].clientX, e.touches[0].clientY)
    mapPan.value = { x: mapDragStart.value.px + (pt.x - mapDragStart.value.vx), y: mapDragStart.value.py + (pt.y - mapDragStart.value.vy) }
  } else if (e.touches.length === 2 && mapPinchStart.value) {
    const dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY)
    const ns = Math.max(0.25, Math.min(5, mapPinchStart.value.scale * (dist / mapPinchStart.value.dist)))
    const sf = ns / mapPinchStart.value.scale
    const vp = clientToVBox(mapPinchStart.value.cx, mapPinchStart.value.cy)
    mapPan.value = { x: vp.x - (vp.x - mapPinchStart.value.px) * sf, y: vp.y - (vp.y - mapPinchStart.value.py) * sf }
    mapScale.value = ns
  }
}
function onMapTouchEnd() { mapDragging.value = false; mapDragStart.value = null; mapPinchStart.value = null }
function onNodeClick(node) { selectedNode.value = selectedNode.value?.id === node.id ? null : node }

function eventIcon(type, severity) {
  if (severity === 'error') return '❌'
  if (severity === 'warning') return '⚠️'
  return { network_created: '🌐', site_created: '🖥', site_deleted: '🗑', keys_regenerated: '🔑',
           config_downloaded: '⬇', status_changed: '🔄', diagnostics_run: '🩺' }[type] || 'ℹ️'
}

function getSiteDiag(siteId) {
  if (!diagResults.value?.sites) return null
  return diagResults.value.sites.find(s => s.site_id === siteId) || null
}

// ── API calls ─────────────────────────────────────────────────────────────────
async function loadNetworks() {
  loading.value = true
  error.value = ''
  try {
    const featureResp = await portalApi.getFeatures()
    const hasCorporateAccess = !!featureResp.data?.features?.corp_networks
    planBlocked.value = !hasCorporateAccess
    if (!hasCorporateAccess) {
      networks.value = []
      return
    }

    const resp = await portalApi.getCorporateNetworks()
    networks.value = resp.data
  } catch (e) {
    if (e.response?.status === 403) planBlocked.value = true
    else error.value = e.response?.data?.detail || 'Failed to load networks'
  } finally {
    loading.value = false
  }
}

async function openNetwork(net) {
  diagResults.value = null
  quickHealth.value = net.health || null
  showEventLog.value = false
  events.value = []
  try {
    const resp = await portalApi.getCorporateNetwork(net.id)
    selectedNetwork.value = resp.data
  } catch {
    selectedNetwork.value = net
  }
}

function closeNetwork() {
  selectedNetwork.value = null
  diagResults.value = null
  quickHealth.value = null
  showEventLog.value = false
  events.value = []
}

async function createNetwork() {
  if (!newNetworkName.value.trim()) return
  actionLoading.value = true
  try {
    const resp = await portalApi.createCorporateNetwork({ name: newNetworkName.value.trim() })
    networks.value.unshift(resp.data)
    showCreateNetwork.value = false
    newNetworkName.value = ''
    showToast('Network created!')
    openNetwork(resp.data)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to create network'
    showCreateNetwork.value = false
  } finally {
    actionLoading.value = false
  }
}

async function addSite() {
  actionLoading.value = true
  const subnets = newSite.value.subnets.filter(s => s.trim())
  try {
    const resp = await portalApi.addCorporateSite(selectedNetwork.value.id, {
      name: newSite.value.name.trim() || null,
      local_subnets: subnets.length ? subnets : null,
      endpoint: newSite.value.endpoint.trim() || null,
      listen_port: null,  // auto-assigned by backend
      is_relay: newSite.value.is_relay,
      routing_mode: newSite.value.routing_mode,
    })
    selectedNetwork.value.sites = [...(selectedNetwork.value.sites || []), resp.data]
    selectedNetwork.value.site_count++
    selectedNetwork.value.active_site_count++
    showAddSite.value = false
    newSite.value = { name: '', subnets: [''], endpoint: '', listen_port: 51820, is_relay: false, routing_mode: 'auto' }
    diagResults.value = null
    showToast('Site added!')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to add site'
  } finally {
    actionLoading.value = false
  }
}

function startEditSite(site) {
  editSite.value = site
  editForm.value = {
    name: site.name,
    subnets: site.local_subnets?.length ? [...site.local_subnets] : [''],
    endpoint: site.endpoint || '',
    listen_port: site.listen_port,
    is_relay: site.is_relay || false,
    routing_mode: site.routing_mode || 'auto',
  }
}

async function saveSiteEdit() {
  if (!editSite.value) return
  actionLoading.value = true
  const subnets = editForm.value.subnets.filter(s => s.trim())
  try {
    const resp = await portalApi.updateCorporateSite(selectedNetwork.value.id, editSite.value.id, {
      name: editForm.value.name.trim() || null,
      local_subnets: subnets.length ? subnets : [],
      endpoint: editForm.value.endpoint.trim() || null,
      listen_port: editForm.value.listen_port,
      is_relay: editForm.value.is_relay,
      routing_mode: editForm.value.routing_mode,
    })
    const idx = selectedNetwork.value.sites.findIndex(s => s.id === editSite.value.id)
    if (idx !== -1) selectedNetwork.value.sites[idx] = resp.data
    editSite.value = null
    diagResults.value = null
    showToast('Site updated!')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to update site'
  } finally {
    actionLoading.value = false
  }
}

async function downloadConfig(site) {
  try {
    const resp = await portalApi.downloadCorporateConfig(selectedNetwork.value.id, site.id)
    const blob = new Blob([resp.data], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `corp-${selectedNetwork.value.name.toLowerCase().replace(/\s+/g,'-')}-${site.name.toLowerCase().replace(/\s+/g,'-')}.conf`
    a.click()
    URL.revokeObjectURL(url)
    site.config_downloaded_at = new Date().toISOString()
    showToast('Config downloaded!')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to download config'
  }
}

function confirmDeleteNetwork(net) { deleteNetworkTarget.value = net }

async function deleteNetwork() {
  if (!deleteNetworkTarget.value) return
  actionLoading.value = true
  try {
    await portalApi.deleteCorporateNetwork(deleteNetworkTarget.value.id)
    networks.value = networks.value.filter(n => n.id !== deleteNetworkTarget.value.id)
    if (selectedNetwork.value?.id === deleteNetworkTarget.value.id) closeNetwork()
    deleteNetworkTarget.value = null
    showToast('Network deleted')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to delete network'
  } finally {
    actionLoading.value = false
  }
}

function confirmDeleteSite(site) { deleteSiteTarget.value = site }

async function deleteSite() {
  if (!deleteSiteTarget.value) return
  actionLoading.value = true
  try {
    await portalApi.deleteCorporateSite(selectedNetwork.value.id, deleteSiteTarget.value.id)
    selectedNetwork.value.sites = selectedNetwork.value.sites.filter(s => s.id !== deleteSiteTarget.value.id)
    selectedNetwork.value.site_count--
    selectedNetwork.value.active_site_count--
    deleteSiteTarget.value = null
    diagResults.value = null
    showToast('Site deleted')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to delete site'
  } finally {
    actionLoading.value = false
  }
}

function confirmRegenKeys(site) { regenSiteTarget.value = site }

async function regenKeys() {
  if (!regenSiteTarget.value) return
  actionLoading.value = true
  try {
    await portalApi.regenerateCorporateSiteKeys(selectedNetwork.value.id, regenSiteTarget.value.id)
    const resp = await portalApi.getCorporateNetwork(selectedNetwork.value.id)
    selectedNetwork.value = resp.data
    regenSiteTarget.value = null
    diagResults.value = null
    showToast('Keys regenerated — re-download configs for all sites!')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to regenerate keys'
  } finally {
    actionLoading.value = false
  }
}

async function runDiagnostics() {
  diagLoading.value = true
  diagResults.value = null
  try {
    const resp = await portalApi.diagnoseCorporateNetwork(selectedNetwork.value.id)
    diagResults.value = resp.data
    quickHealth.value = { health: resp.data.health, errors: resp.data.errors, warnings: resp.data.warnings }
    const net = networks.value.find(n => n.id === selectedNetwork.value.id)
    if (net) net.health = quickHealth.value
  } catch (e) {
    error.value = e.response?.data?.detail || 'Diagnostics failed'
  } finally {
    diagLoading.value = false
  }
}

async function toggleEvents() {
  showEventLog.value = !showEventLog.value
  if (showEventLog.value && !events.value.length) {
    eventsLoading.value = true
    try {
      const resp = await portalApi.getCorporateNetworkEvents(selectedNetwork.value.id, 50)
      events.value = resp.data
    } catch {
      events.value = []
    } finally {
      eventsLoading.value = false
    }
  }
}

// Non-passive touchmove for pinch/pan (must bypass Vue's passive default)
watch(mapContainerRef, (el) => {
  if (el) el.addEventListener('touchmove', onMapTouchMoveHandler, { passive: false })
})
onUnmounted(() => {
  mapContainerRef.value?.removeEventListener('touchmove', onMapTouchMoveHandler)
})

onMounted(loadNetworks)
</script>

<style scoped>
/* ── Status dots ──────────────────────────────────────────────────────────── */
.health-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.health-dot.lg { width: 10px; height: 10px; }
.health-dot.sm { width: 6px;  height: 6px; }
.health-dot.healthy, .health-dot.active    { background: var(--vxy-success); }
.health-dot.warning, .health-dot.suspended { background: var(--vxy-warning); }
.health-dot.error,   .health-dot.expired   { background: var(--vxy-danger); }
.health-dot.inactive,.health-dot.disabled  { background: var(--vxy-muted); }
.health-dot.unknown  { background: var(--vxy-primary); }

.site-icon { font-size: 1.5rem; line-height: 1; padding-top: 2px; }
.min-width-0 { min-width: 0; }

/* ── Network map ──────────────────────────────────────────────────────────── */
.map-canvas {
  width: 100%; height: 420px;
  overflow: hidden; position: relative;
  cursor: grab;
  touch-action: none;
  user-select: none;
  background: var(--vxy-body-bg, #f8f9fa);
  border-top: 1px solid var(--vxy-border, rgba(0,0,0,.08));
  border-bottom: 1px solid var(--vxy-border, rgba(0,0,0,.08));
}
.map-canvas.is-dragging { cursor: grabbing; }

/* Zoom/pan controls */
.map-controls { display: flex; gap: 4px; }
.map-ctrl-btn {
  width: 30px; height: 30px;
  border: 1px solid var(--vxy-border, rgba(0,0,0,.15));
  background: var(--vxy-card-bg, #fff);
  border-radius: 6px;
  font-size: 15px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--vxy-text, #333);
  transition: background .15s, color .15s, border-color .15s;
}
.map-ctrl-btn:hover {
  background: var(--vxy-primary, #5865f2);
  color: #fff; border-color: var(--vxy-primary, #5865f2);
}

/* Node animations */
.pulse-ring {
  transform-box: fill-box;
  transform-origin: center;
  animation: pulse-ring 2.8s ease-in-out infinite;
}
@keyframes pulse-ring {
  0%   { transform: scale(0.85); opacity: 0.6; }
  50%  { transform: scale(1.3);  opacity: 0.1; }
  100% { transform: scale(0.85); opacity: 0.6; }
}

/* Relay flow animation */
.relay-flow { animation: relay-dash 1.4s linear infinite; }
@keyframes relay-dash { to { stroke-dashoffset: -16; } }

/* Map nodes: pointer cursor, no default text selection */
.map-node { cursor: pointer; }
.map-node--sel circle:first-child { stroke-width: 3.5 !important; }

/* Selected node detail panel */
.map-detail-panel {
  border-top: 1px solid var(--vxy-border, rgba(0,0,0,.08));
  background: var(--vxy-card-bg, #fff);
}
.node-detail-enter-active, .node-detail-leave-active { transition: all .2s ease; }
.node-detail-enter-from, .node-detail-leave-to { opacity: 0; transform: translateY(-6px); }

/* Legend */
.ldot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

/* ── Diagnostics ──────────────────────────────────────────────────────────── */
.diag-issue { padding: .2rem .5rem; border-radius: .375rem; }
.diag-issue.error   { background: var(--vxy-danger-light);  color: var(--vxy-danger); }
.diag-issue.warning { background: var(--vxy-warning-light); color: var(--vxy-warning); }

.site-diag-block {
  background: var(--vxy-body-bg);
  border-radius: .375rem; padding: .6rem .75rem;
  border-left: 3px solid var(--vxy-border);
}

/* ── Event log ────────────────────────────────────────────────────────────── */
.event-log { max-height: 280px; overflow-y: auto; }
.event-row:last-child { border-bottom: none !important; }
.event-icon { width: 20px; }

/* ── Modals ───────────────────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(34,41,47,.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999; padding: 1rem;
}
.modal-card {
  background: var(--vxy-modal-bg, #fff);
  color: var(--vxy-text, #6E6B7B);
  border-radius: .75rem; padding: 1.5rem;
  width: 100%; max-width: 420px;
  box-shadow: 0 20px 60px rgba(0,0,0,.3);
  max-height: 90vh; overflow-y: auto;
}
.modal-card h5, .modal-card h6 { color: var(--vxy-heading, #5e5873); }
.modal-card .form-text { color: var(--vxy-muted) !important; }
.modal-card .text-muted { color: var(--vxy-muted) !important; }

/* ── Toast ────────────────────────────────────────────────────────────────── */
.corp-toast {
  position: fixed; bottom: 90px; left: 50%;
  transform: translateX(-50%);
  padding: .6rem 1.4rem; border-radius: 24px;
  font-size: .9rem; font-weight: 500;
  z-index: 99999; pointer-events: none;
  animation: fadeIn .2s ease;
  background: var(--vxy-success); color: #fff;
}
.corp-toast.error { background: var(--vxy-danger); }

@keyframes fadeIn {
  from { opacity: 0; transform: translateX(-50%) translateY(10px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* ── Mobile ───────────────────────────────────────────────────────────────── */
@media (max-width: 576px) {
  .modal-card { padding: 1rem; }
  .map-canvas { height: 270px; }
}
</style>
