<!-- Clients — his exact table markup (bulk bar, filters, sortable cols, proto
     badges, traffic bar, switch toggle, row actions) + pagination, reproduced
     1:1. Wired to useClientsStore + clientsApi + segmentsApi. Search + "New
     client" primary go through the topbar (d2ui). Modals reuse the functional
     D2Modal primitives (his modal markup is a later pass). -->
<template>
  <div>
    <!-- bulk bar -->
    <div v-if="selectedIds.size" style="display:flex;align-items:center;gap:12px;background:var(--panel);border:1px solid var(--border-strong);border-radius:11px;box-shadow:var(--shadow);padding:10px 14px;margin-bottom:12px">
      <span style="font-size:13px;font-weight:600">{{ selectedIds.size }} {{ tr('common.selected') || 'selected' }}</span>
      <button @click="selectedIds = new Set()" class="d2-lnkbtn">{{ tr('common.clear') || 'Clear' }}</button>
      <div style="display:flex;gap:8px;margin-left:auto;flex-wrap:wrap;align-items:center">
        <select :value="bulkSegmentId" @change="bulkSegmentId = $event.target.value; bulkAssignSegment()" class="d2-sel-sm"><option value="">{{ tr('clients.assignSegment') || 'Assign segment…' }}</option><option value="__remove__">— {{ tr('clients.removeSegment') || 'Remove' }}</option><option v-for="s in segments" :key="s.id" :value="s.id">{{ s.name }}</option></select>
        <button @click="bulkEnable" class="d2-btn-sm">{{ tr('common.enable') || 'Enable' }}</button>
        <button @click="bulkDisable" class="d2-btn-sm">{{ tr('common.disable') || 'Disable' }}</button>
        <button @click="bulkDelete" style="height:32px;padding:0 12px;border:none;background:var(--red-soft);color:var(--red);border-radius:8px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('common.delete') || 'Delete' }}</button>
      </div>
    </div>

    <!-- filters -->
    <div class="d2-clients-filters" style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
      <div style="font-size:12.5px;color:var(--text-3)">{{ orderedClients.length }} {{ tr('nav.clients') || 'clients' }}</div>
      <select v-model="filterStatus" class="d2-sel"><option value="">{{ tr('clients.allStatuses') || 'All statuses' }}</option><option value="enabled">{{ tr('common.enabled') || 'Enabled' }}</option><option value="disabled">{{ tr('common.disabled') || 'Disabled' }}</option><option value="online">{{ tr('common.online') || 'Online' }}</option><option value="offline">{{ tr('common.offline') || 'Offline' }}</option><option value="expiring">{{ tr('clients.expiringSoon') || 'Expiring soon' }}</option></select>
      <select v-model="filterServer" class="d2-sel"><option value="">{{ tr('clients.allServers') || 'All servers' }}</option><option v-for="s in servers" :key="s.id" :value="s.id">{{ s.name }}</option></select>
      <select v-if="segments.length" v-model="filterSegment" class="d2-sel"><option value="">{{ tr('clients.allSegments') || 'All segments' }}</option><option v-for="s in segments" :key="s.id" :value="s.id">{{ s.name }}</option></select>
      <button @click="openSegments" style="margin-left:auto;display:flex;align-items:center;gap:7px;height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2-hoverpanel2"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 6h18M3 12h18M3 18h18"></path></svg>{{ tr('clients.segments.title') || 'Segments' }}</button>
      <details class="d2-client-card-options">
        <summary><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h7M15 18h5"></path><circle cx="16" cy="6" r="2"></circle><circle cx="8" cy="12" r="2"></circle><circle cx="13" cy="18" r="2"></circle></svg>{{ tr('clients.mobileFields') || 'Card fields' }}</summary>
        <div class="d2-client-card-options-menu">
          <div class="d2-client-card-options-title">{{ tr('clients.mobileFieldsHint') || 'Show before opening the card' }}</div>
          <label v-for="option in mobileFieldOptions" :key="option.key"><input type="checkbox" :checked="isMobilePrimary(option.key)" @change="toggleMobileField(option.key)"><span>{{ option.label }}</span></label>
        </div>
      </details>
    </div>

    <!-- empty -->
    <div v-if="!orderedClients.length && !store.loading" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:56px 24px;text-align:center">
      <div style="width:54px;height:54px;border-radius:14px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;margin:0 auto 14px"><Icon name="users" :size="26" /></div>
      <div style="font-size:15px;font-weight:600">{{ tr('dashboard.noClients') || 'No clients yet' }}</div>
      <div style="font-size:13px;color:var(--text-3);margin-top:4px">{{ tr('clients.emptyHint') || 'Create your first client to get started.' }}</div>
    </div>

    <!-- table -->
    <div v-else class="d2-clients-list" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div class="d2-clients-desktop" style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left">
            <th style="padding:11px 12px 11px 20px;width:36px"><input type="checkbox" :checked="allPageSelected" @change="toggleSelectAll" style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent)"></th>
            <th @click="toggleSort('name')" class="d2-th srt">{{ tr('clients.name') || 'Name' }} {{ sortIcon('name') }}</th>
            <th @click="toggleSort('server')" class="d2-th srt">{{ tr('clients.server') || 'Server' }} {{ sortIcon('server') }}</th>
            <th class="d2-th">{{ tr('clients.protocol') || 'Protocol' }}</th>
            <th @click="toggleSort('traffic')" class="d2-th srt">{{ tr('clients.traffic') || 'Traffic' }} {{ sortIcon('traffic') }}</th>
            <th class="d2-th">{{ tr('clients.bandwidth') || 'Bandwidth' }}</th>
            <th class="d2-th">{{ tr('clients.segment') || 'Segment' }}</th>
            <th @click="toggleSort('expiry')" class="d2-th srt">{{ tr('clients.expiry') || 'Expires' }} {{ sortIcon('expiry') }}</th>
            <th class="d2-th">{{ tr('clients.status') || 'Status' }}</th>
            <th class="d2-th" style="padding:11px 20px;text-align:right">{{ tr('common.actions') || 'Actions' }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="c in rows" :key="c.id" :class="{ hot: c.id === highlightedClientId }" style="border-top:1px solid var(--border)">
              <td data-mhide style="padding:12px 12px 12px 20px"><input type="checkbox" :checked="selectedIds.has(c.id)" @change="toggleSelect(c.id)" style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent)"></td>
              <td data-mhead style="padding:12px 12px"><div style="display:flex;align-items:center;gap:8px"><span :title="c.statusTitle" :style="{ width:'7px', height:'7px', borderRadius:'50%', background:c.dotColor, flex:'none' }"></span><div><div style="font-weight:550">{{ c.name }}</div><div class="mono d2-client-head-ip" :class="{ keep: isMobilePrimary('ip') }" style="font-size:11.5px;color:var(--text-3)">{{ c.ip }}</div></div></div></td>
              <td :data-label="tr('clients.server') || 'Server'" :data-mprimary="isMobilePrimary('server') ? '' : null" style="padding:12px 12px;color:var(--text-2)">{{ c.server }}</td>
              <td :data-label="tr('clients.protocol') || 'Protocol'" :data-mprimary="isMobilePrimary('protocol') ? '' : null" style="padding:12px 12px"><span :style="{ display:'inline-flex', alignItems:'center', fontSize:'11.5px', fontWeight:600, padding:'3px 8px', borderRadius:'7px', color:c.protoColor, background:c.protoBg }">{{ c.protoLabel }}</span></td>
              <td :data-label="tr('clients.traffic') || 'Traffic'" :data-mprimary="isMobilePrimary('traffic') ? '' : null" style="padding:12px 12px"><div class="mono" style="font-size:11.5px;color:var(--text-2)">{{ c.trafficLabel }}</div><div v-if="c.hasLimit" style="height:4px;border-radius:3px;background:var(--panel-3);overflow:hidden;margin-top:4px;width:96px"><div :style="{ height:'100%', borderRadius:'3px', background:c.trafficBarColor, width:c.trafficPct }"></div></div></td>
              <td :data-label="tr('clients.bandwidth') || 'Bandwidth'" :data-mprimary="isMobilePrimary('bandwidth') ? '' : null" class="mono" style="padding:12px 12px;font-size:12px;color:var(--text-2)">{{ c.bwLabel }}</td>
              <td :data-label="tr('clients.segment') || 'Segment'" :data-mprimary="isMobilePrimary('segment') ? '' : null" style="padding:12px 12px"><span v-if="c.segment" :style="{ display:'inline-flex', alignItems:'center', gap:'5px', fontSize:'11px', fontWeight:600, padding:'2px 8px', borderRadius:'6px', color:'#fff', background:c.segColor }">{{ c.segment }}</span><span v-else style="font-size:12px;color:var(--text-3)">—</span></td>
              <td :data-label="tr('clients.expiry') || 'Expires'" :data-mprimary="isMobilePrimary('expiry') ? '' : null" style="padding:12px 12px;font-size:12px" :style="{ color: c.expiresColor }">{{ c.expiresLabel }}</td>
              <td :data-label="tr('clients.status') || 'Status'" :data-mprimary="isMobilePrimary('status') ? '' : null" style="padding:12px 12px"><button @click="toggleClient(c._raw)" :title="c.toggleTitle" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background: c.enabled ? 'var(--accent)' : 'var(--border-strong)' }"><span :style="{ position:'absolute', top:'2px', left: c.enabled ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button></td>
              <td data-mfull style="padding:12px 20px"><div style="display:flex;gap:4px;justify-content:flex-end">
                <button @click="showConfig(c._raw)" :title="tr('clients.tipConfig') || 'Config'" class="d2-rowbtn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg></button>
                <button @click="generateShareLink(c._raw)" :title="tr('clients.shareLinkTitle') || 'Share link'" class="d2-rowbtn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 007 0l2-2a5 5 0 00-7-7l-1 1"></path><path d="M14 11a5 5 0 00-7 0l-2 2a5 5 0 007 7l1-1"></path></svg></button>
                <button @click="editClient(c._raw)" :title="tr('clients.tipEdit') || 'Edit'" class="d2-rowbtn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"></path></svg></button>
                <button @click="removeClient(c._raw)" :title="tr('clients.tipDelete') || 'Delete'" class="d2-rowbtn del"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="d2-clients-mobile">
        <div v-for="c in rows" :key="c.id" class="d2-client-mobile-row" :class="{ hot: c.id === highlightedClientId }">
          <input type="checkbox" :checked="selectedIds.has(c.id)" :aria-label="c.name" @change="toggleSelect(c.id)">
          <button type="button" class="d2-client-mobile-main" @click="openMobileClient(c)">
            <span class="d2-client-mobile-title"><i :style="{ background:c.dotColor }"></i><b>{{ c.name }}</b></span>
            <span class="d2-client-mobile-primary">
              <span v-if="isMobilePrimary('server')">{{ c.server }}</span>
              <span v-if="isMobilePrimary('protocol')" :style="{ color:c.protoColor, background:c.protoBg }">{{ c.protoLabel }}</span>
              <span v-if="isMobilePrimary('ip')" class="mono">{{ c.ip }}</span>
              <span v-if="isMobilePrimary('traffic')">{{ c.trafficLabel }}</span>
              <span v-if="isMobilePrimary('bandwidth')">{{ c.bwLabel }}</span>
              <span v-if="isMobilePrimary('segment') && c.segment">{{ c.segment }}</span>
              <span v-if="isMobilePrimary('expiry')">{{ c.expiresLabel }}</span>
              <span v-if="isMobilePrimary('status')">{{ c.statusTitle }}</span>
            </span>
          </button>
          <button type="button" class="d2-client-mobile-more" :aria-label="tr('clients.tipMore') || 'More'" @click="openMobileClient(c)">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>
          </button>
        </div>
      </div>
      <div v-if="totalPages > 1" style="display:flex;align-items:center;gap:12px;padding:12px 20px;border-top:1px solid var(--border)">
        <div style="font-size:12px;color:var(--text-3)">{{ currentPage }} / {{ totalPages }}</div>
        <div style="margin-left:auto;display:flex;gap:6px"><button @click="currentPage > 1 && currentPage--" class="d2-btn-sm">{{ tr('common.prev') || 'Prev' }}</button><button @click="currentPage < totalPages && currentPage++" class="d2-btn-sm">{{ tr('common.next') || 'Next' }}</button></div>
      </div>
    </div>

    <D2MobileSheet :open="!!mobileClient" :title="mobileClient?.name || ''" :close-label="tr('common.close') || 'Close'" @close="mobileClient = null">
      <template v-if="mobileClient">
        <div class="d2-client-sheet-status"><span :style="{ background:mobileClient.dotColor }"></span>{{ mobileClient.statusTitle }}</div>
        <dl class="d2-client-sheet-details">
          <div><dt>{{ tr('clients.server') || 'Server' }}</dt><dd>{{ mobileClient.server }}</dd></div>
          <div><dt>{{ tr('clients.protocol') || 'Protocol' }}</dt><dd>{{ mobileClient.protoLabel }}</dd></div>
          <div><dt>IP</dt><dd class="mono">{{ mobileClient.ip }}</dd></div>
          <div><dt>{{ tr('clients.traffic') || 'Traffic' }}</dt><dd>{{ mobileClient.trafficLabel }}</dd></div>
          <div><dt>{{ tr('clients.bandwidth') || 'Bandwidth' }}</dt><dd>{{ mobileClient.bwLabel }}</dd></div>
          <div><dt>{{ tr('clients.segment') || 'Segment' }}</dt><dd>{{ mobileClient.segment || '—' }}</dd></div>
          <div><dt>{{ tr('clients.expiry') || 'Expires' }}</dt><dd :style="{ color:mobileClient.expiresColor }">{{ mobileClient.expiresLabel }}</dd></div>
        </dl>
        <div class="d2-client-sheet-actions">
          <button type="button" @click="mobileClientAction('toggle')">{{ mobileClient.enabled ? (tr('common.disable') || 'Disable') : (tr('common.enable') || 'Enable') }}</button>
          <button type="button" @click="mobileClientAction('config')">{{ tr('clients.tipConfig') || 'Config' }}</button>
          <button type="button" @click="mobileClientAction('share')">{{ tr('clients.shareLinkTitle') || 'Share link' }}</button>
          <button type="button" @click="mobileClientAction('edit')">{{ tr('clients.tipEdit') || 'Edit' }}</button>
          <button type="button" class="danger" @click="mobileClientAction('delete')">{{ tr('common.delete') || 'Delete' }}</button>
        </div>
      </template>
    </D2MobileSheet>

    <!-- modals (functional; his modal markup is a later pass) -->
    <D2Modal :open="showCreateModal" :title="tr('clients.createTitle') || 'Create client'" @close="showCreateModal = false">
      <div style="display:flex;flex-direction:column;gap:14px">
        <!-- name -->
        <div><label class="d2-flabel">{{ tr('clients.clientName') || 'Name' }}</label><input v-model="newClient.name" :placeholder="tr('clients.clientNamePlaceholder') || 'e.g. Alice · iPhone'" class="d2-finput" /></div>
        <!-- server (create only) -->
        <div><label class="d2-flabel">{{ tr('clients.server') || 'Server' }}</label><select v-model.number="newClient.server_id" class="d2-fselect"><option v-for="s in servers" :key="s.id" :value="s.id">{{ s.name }}</option></select></div>
        <!-- email -->
        <div><label class="d2-flabel">{{ tr('clients.customerEmail') || 'Customer email' }}</label><input v-model="newClient.customer_email" placeholder="customer@example.com" class="d2-finput" /><div style="font-size:11px;color:var(--text-3);margin-top:5px">{{ tr('clients.customerEmailHint') || 'Optional — used for share-link delivery & billing.' }}</div></div>
        <!-- segment -->
        <div v-if="segments.length"><label class="d2-flabel">{{ tr('clients.segment') || 'Segment' }}</label><select v-model="newClient.segment_id" class="d2-fselect"><option :value="null">{{ tr('clients.segments.none') || '— No segment —' }}</option><option v-for="s in segments" :key="s.id" :value="s.id">{{ s.name }}</option></select></div>
        <!-- bandwidth (vpn only) -->
        <div v-if="!newClientIsProxy">
          <label class="d2-flabel">{{ tr('clients.bandwidthLimit') || 'Bandwidth limit (Mbps)' }}</label>
          <div class="d2-chiprow"><button v-for="p in bwPresets" :key="'nbw'+p.v" type="button" @click="newClient.bandwidth_limit = p.v" class="d2-chip" :class="{ on: Number(newClient.bandwidth_limit) === p.v }">{{ p.label }}</button></div>
          <input v-model="newClient.bandwidth_limit" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" />
        </div>
        <!-- traffic (vpn only) -->
        <div v-if="!newClientIsProxy">
          <label class="d2-flabel">{{ tr('clients.trafficLimitMb') || 'Traffic limit (MB)' }}</label>
          <div class="d2-chiprow"><button v-for="p in trafficPresets" :key="'ntr'+p.v" type="button" @click="newClient.traffic_limit_mb = p.v" class="d2-chip" :class="{ on: Number(newClient.traffic_limit_mb) === p.v }">{{ p.label }}</button></div>
          <input v-model="newClient.traffic_limit_mb" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" />
        </div>
        <!-- expiry -->
        <div>
          <label class="d2-flabel">{{ tr('clients.expiryLabel') || 'Expiry' }}</label>
          <div class="d2-chiprow"><button v-for="p in expiryPresets" :key="'nex'+p.v" type="button" @click="setNewExpiryDays(p.v)" class="d2-chip" :class="{ on: Number(newClient.expiry_days) === p.v }">{{ p.label }}</button></div>
          <div style="display:flex;gap:10px">
            <div style="width:110px"><input v-model.number="newClient.expiry_days" inputmode="numeric" :placeholder="tr('clients.expiryDays') || 'days'" class="d2-finput mono" /></div>
            <input v-model="newExpiryDate" type="date" class="d2-finput mono" style="flex:1" />
          </div>
        </div>
        <!-- peer visibility -->
        <D2Toggle v-model="newClient.peer_visibility">{{ tr('clients.peerVisibility') || 'Peer visibility' }}<template #help><D2HelpTip :text="tr('help.peerVisibility') || 'Devices of the same user can see each other.'" /></template></D2Toggle>
        <div v-if="createError" style="color:var(--red);font-size:13px">{{ createError }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="showCreateModal = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="creating" @click="createClient">{{ tr('common.create') || 'Create' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="shareModal.show" :title="''" @close="closeShareModal">
      <template #header><div><div v-if="shareModal.mode === 'post-create'" style="display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--green);margin-bottom:4px"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('clients.shareModal.created') || 'Client created' }}</div><h3 style="font-size:18px;font-weight:700;margin:0">{{ shareModal.client?.name || '—' }}</h3></div></template>
      <div v-if="shareModal.proxyUri" style="background:var(--panel-2);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:12px">
        <div style="font-size:12.5px;font-weight:600;color:var(--text-2);margin-bottom:8px">{{ tr('clients.proxyLink') || 'Proxy link. Paste into your app (v2rayN / sing-box / Hiddify)' }}</div>
        <div style="display:flex;gap:8px"><input :value="shareModal.proxyUri" readonly @focus="$event.target.select()" class="mono" style="flex:1;min-width:0;padding:8px 11px;border-radius:9px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text);font-size:12.5px" /><D2Button size="sm" :icon="shareModal.proxyCopied ? 'check' : 'content-copy'" @click="copyShareProxyUri">{{ shareModal.proxyCopied ? (tr('clients.shareModal.copied') || 'Copied') : (tr('common.copy') || 'Copy') }}</D2Button></div>
      </div>
      <div style="background:var(--panel-2);border:1px solid var(--border);border-radius:12px;padding:14px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px"><span style="font-size:12.5px;font-weight:600;color:var(--text-2)">{{ tr('clients.shareModal.linkLabel') || 'Time-limited download link' }}</span><D2Countdown v-if="shareModal.expiresAt" :expiresAt="shareModal.expiresAt" :expiredText="tr('clients.shareModal.expired') || 'Expired'" /></div>
        <div v-if="shareModal.loading" style="font-size:13px;color:var(--text-3)">{{ tr('clients.shareModal.generating') || 'Generating…' }}</div>
        <template v-else><div style="display:flex;gap:8px"><input :value="shareModal.url" readonly @focus="$event.target.select()" class="mono" style="flex:1;min-width:0;padding:8px 11px;border-radius:9px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text);font-size:12.5px" /><D2Button size="sm" :icon="shareModal.copied ? 'check' : 'content-copy'" @click="copyShareUrl">{{ shareModal.copied ? (tr('clients.shareModal.copied') || 'Copied') : (tr('common.copy') || 'Copy') }}</D2Button></div><div style="font-size:12px;color:var(--text-3);margin-top:8px">{{ tr('clients.shareModal.hint') || 'Send this link — customer downloads the .conf without logging in.' }}</div></template>
      </div>
      <div v-if="shareModal.client && !shareModal.loading" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">
        <D2Button variant="secondary" size="sm" icon="tray-arrow-down" :loading="shareModal.downloading" @click="downloadFromShare">{{ tr('clients.shareModal.downloadConfig') || 'Download config' }}</D2Button>
        <D2Button variant="secondary" size="sm" :icon="shareModal.showQR ? 'chevron-up' : 'qrcode'" @click="toggleShareQR">{{ shareModal.showQR ? 'Hide QR' : 'Show QR' }}</D2Button>
      </div>
      <div v-if="shareModal.showQR && shareModal.qrSrc" style="margin-top:14px;text-align:center"><img :src="shareModal.qrSrc" style="max-width:220px;border-radius:10px;background:#fff;padding:8px" /></div>
    </D2Modal>

    <D2Modal :open="showEditModal" :title="(tr('clients.editTitle') || 'Edit') + (editingClient ? ' · ' + editingClient.name : '')" @close="showEditModal = false">
      <div style="display:flex;flex-direction:column;gap:14px">
        <!-- name -->
        <div><label class="d2-flabel">{{ tr('clients.clientName') || 'Name' }}</label><input v-model="editForm.name" class="d2-finput" /></div>
        <!-- segment -->
        <div v-if="segments.length"><label class="d2-flabel">{{ tr('clients.segment') || 'Segment' }}</label><select v-model="editForm.segment_id" class="d2-fselect"><option :value="null">{{ tr('clients.segments.none') || '— No segment —' }}</option><option v-for="s in segments" :key="s.id" :value="s.id">{{ s.name }}</option></select></div>
        <!-- bandwidth (vpn only) -->
        <div v-if="!editIsProxy">
          <label class="d2-flabel">{{ tr('clients.bandwidthLimit') || 'Bandwidth limit (Mbps)' }}</label>
          <div class="d2-chiprow"><button v-for="p in bwPresets" :key="'ebw'+p.v" type="button" @click="editForm.bandwidth = p.v" class="d2-chip" :class="{ on: Number(editForm.bandwidth) === p.v }">{{ p.label }}</button></div>
          <input v-model="editForm.bandwidth" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" />
        </div>
        <!-- traffic (vpn only) -->
        <div v-if="!editIsProxy">
          <label class="d2-flabel">{{ tr('clients.trafficLimitMb') || 'Traffic limit (MB)' }}</label>
          <div class="d2-chiprow"><button v-for="p in trafficPresets" :key="'etr'+p.v" type="button" @click="editForm.trafficLimit = p.v" class="d2-chip" :class="{ on: Number(editForm.trafficLimit) === p.v }">{{ p.label }}</button></div>
          <input v-model="editForm.trafficLimit" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" />
        </div>
        <!-- expiry -->
        <div>
          <label class="d2-flabel">{{ tr('clients.expiryLabel') || 'Expiry' }}</label>
          <div class="d2-chiprow"><button v-for="p in expiryPresets" :key="'eex'+p.v" type="button" @click="setEditExpiryDays(p.v)" class="d2-chip">{{ p.label }}</button></div>
          <input v-model="editExpiryDate" type="date" class="d2-finput mono" />
          <div style="font-size:11px;color:var(--text-3);margin-top:5px">{{ tr('clients.expiryKeepHint') || 'Leave empty to keep current.' }}</div>
        </div>
        <!-- reset traffic (edit only) -->
        <button type="button" @click="resetTrafficNow" style="display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:10px;font:inherit;font-size:13px;font-weight:550;cursor:pointer" class="d2-hoverpanel2"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0115-6.7L21 8"></path><path d="M21 3v5h-5"></path></svg>{{ tr('clients.resetTraffic') || 'Reset traffic counter' }}</button>
      </div>
      <template #footer><D2Button variant="secondary" @click="showEditModal = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button @click="saveEdit">{{ tr('common.save') || 'Save' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="showConfigModal" :title="(tr('clients.configTitle') || 'Config') + (configClient ? ' · ' + configClient.name : '')" @close="closeConfigModal">
      <div v-if="!isProxyConfig" style="display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-bottom:14px"><div v-if="qrUrl" style="text-align:center"><img :src="qrUrl" style="max-width:200px;border-radius:10px;background:#fff;padding:8px" /></div><div v-if="qrAmneziaVpnUrl" style="text-align:center"><img :src="qrAmneziaVpnUrl" style="max-width:200px;border-radius:10px;background:#fff;padding:8px" /></div></div>
      <pre v-if="!isProxyConfig && clientConfig" class="mono" style="background:var(--panel-2);border:1px solid var(--border);border-radius:10px;padding:12px;font-size:12px;color:var(--text-2);overflow-x:auto;white-space:pre-wrap;max-height:300px">{{ clientConfig }}</pre>
      <template v-if="isProxyConfig && proxyConfig">
        <div v-if="proxyConfig.uri" style="margin-bottom:12px">
          <div style="font-size:12px;color:var(--text-3);margin-bottom:5px">{{ tr('clients.proxyLink') || 'Proxy link. Paste into your app (v2rayN / sing-box / Hiddify)' }}</div>
          <div style="display:flex;gap:8px"><input :value="proxyConfig.uri" readonly @focus="$event.target.select()" class="mono" style="flex:1;min-width:0;padding:9px 11px;border-radius:9px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text);font-size:12.5px" /><D2Button size="sm" :icon="proxyCopied ? 'check' : 'content-copy'" @click="copyProxyUri">{{ proxyCopied ? (tr('clients.shareModal.copied') || 'Copied') : (tr('common.copy') || 'Copy') }}</D2Button></div>
        </div>
        <div v-if="qrUrl" style="text-align:center;margin-bottom:12px"><img :src="qrUrl" style="max-width:200px;border-radius:10px;background:#fff;padding:8px" /></div>
      </template>
      <pre v-if="isProxyConfig && proxyConfig" class="mono" style="background:var(--panel-2);border:1px solid var(--border);border-radius:10px;padding:12px;font-size:12px;color:var(--text-2);white-space:pre-wrap;max-height:300px">{{ proxyConfig.config_text }}</pre>
      <template #footer><D2Button variant="secondary" @click="closeConfigModal">{{ tr('common.close') || 'Close' }}</D2Button><D2Button icon="tray-arrow-down" @click="downloadConfig">{{ tr('clients.download') || 'Download' }}</D2Button></template>
    </D2Modal>

    <!-- SEGMENTS MANAGER MODAL — his 760px manager: create/edit form (name, color,
         bw, traffic, expiry, auto-rule, notes) + inline add-rule + segments table -->
    <D2Modal :open="showSegmentsModal" :title="tr('clients.segments.title') || 'Segments'" size="lg" @close="showSegmentsModal = false">
      <div style="display:flex;flex-direction:column;gap:18px">
        <!-- form -->
        <div style="border:1px solid var(--border);border-radius:13px;padding:16px 18px;background:var(--panel-2)">
          <div style="font-weight:600;font-size:13.5px;margin-bottom:14px">{{ segEditingId ? (tr('clients.segments.editTitle') || 'Edit segment') : (tr('clients.segments.newTitle') || 'New segment') }}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px">
            <div><label class="d2-flabel">{{ tr('clients.segments.name') || 'Name' }}</label><input v-model="segForm.name" placeholder="Premium" class="d2-finput" /></div>
            <div><label class="d2-flabel">{{ tr('clients.segments.color') || 'Color' }}</label><div style="display:flex;align-items:center;gap:8px"><input v-model="segForm.color" type="color" style="width:40px;height:42px;border:1px solid var(--border);border-radius:9px;padding:2px;background:var(--panel);cursor:pointer;flex:none" /><input v-model="segForm.color" class="d2-finput mono" style="flex:1" /></div></div>
            <div><label class="d2-flabel">{{ tr('clients.segments.bandwidthLimit') || 'Bandwidth (Mbps)' }}</label><input v-model="segForm.bandwidth_limit" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" /></div>
            <div><label class="d2-flabel">{{ tr('clients.segments.trafficLimit') || 'Traffic (MB)' }}</label><input v-model="segForm.traffic_limit_mb" inputmode="numeric" placeholder="0 = ∞" class="d2-finput mono" /></div>
            <div><label class="d2-flabel">{{ tr('clients.segments.expiryDate') || 'Expiry' }}</label><input v-model="segForm.expiry_date" type="date" class="d2-finput mono" /></div>
            <div><label class="d2-flabel">{{ tr('clients.segments.autoRule') || 'Auto-bandwidth rule' }}</label><div style="display:flex;gap:6px"><select v-model="segForm.auto_bandwidth_rule_id" class="d2-fselect" style="flex:1"><option :value="null">{{ tr('clients.segments.ruleNone') || '— None —' }}</option><option v-for="r in trafficRules" :key="r.id" :value="r.id">{{ r.name }}</option></select><button type="button" @click="showSegRuleForm = !showSegRuleForm" style="width:42px;height:42px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex:none" class="d2-hoverpanel2"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg></button></div></div>
          </div>
          <div style="margin-top:13px"><label class="d2-flabel">{{ tr('clients.segments.notes') || 'Notes' }}</label><input v-model="segForm.notes" :placeholder="tr('clients.segments.notesPlaceholder') || 'Optional description'" class="d2-finput" /></div>

          <!-- inline add-rule -->
          <div v-if="showSegRuleForm" style="margin-top:14px;border:1px dashed var(--border-strong);border-radius:11px;padding:13px;background:var(--panel)">
            <div style="font-size:12px;font-weight:600;margin-bottom:10px">{{ tr('clients.segments.addRule') || 'Add traffic rule' }}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:9px">
              <input v-model="segRuleForm.name" :placeholder="tr('clients.segments.ruleName') || 'Rule name'" class="d2-finput-sm" />
              <select v-model="segRuleForm.period" class="d2-fselect-sm"><option value="day">{{ tr('traffic.day') || 'Day' }}</option><option value="week">{{ tr('traffic.week') || 'Week' }}</option><option value="month">{{ tr('traffic.month') || 'Month' }}</option></select>
              <input v-model="segRuleForm.threshold_mb" inputmode="numeric" :placeholder="tr('clients.segments.threshold') || 'Threshold MB'" class="d2-finput-sm mono" />
              <input v-model="segRuleForm.bandwidth_limit_mbps" inputmode="numeric" placeholder="Mbps" class="d2-finput-sm mono" />
            </div>
            <div style="display:flex;gap:8px;margin-top:10px"><button type="button" @click="createSegRule" :disabled="creatingSegRule" style="height:32px;padding:0 13px;border:none;background:var(--accent);color:#fff;border-radius:8px;font:inherit;font-size:12px;font-weight:600;cursor:pointer">{{ tr('common.create') || 'Create' }}</button><button type="button" @click="showSegRuleForm = false" style="height:32px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">{{ tr('common.cancel') || 'Cancel' }}</button></div>
          </div>

          <div style="display:flex;gap:8px;margin-top:16px"><button type="button" @click="saveSegment" :disabled="segSaving" style="display:flex;align-items:center;gap:7px;height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer"><span v-if="segSaving" style="width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ segEditingId ? (tr('common.save') || 'Save') : (tr('common.create') || 'Create') }}</button><button v-if="segEditingId" type="button" @click="resetSegForm" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2-hoverpanel2">{{ tr('common.cancel') || 'Cancel' }}</button></div>
        </div>

        <!-- list -->
        <div v-if="!segments.length" style="padding:32px;text-align:center;font-size:13px;color:var(--text-3)">{{ tr('clients.segments.empty') || 'No segments yet.' }}</div>
        <div v-else style="border:1px solid var(--border);border-radius:13px;overflow:hidden"><div style="overflow-x:auto">
          <table data-rtab style="width:100%;border-collapse:collapse;font-size:12.5px">
            <thead><tr style="text-align:left">
              <th class="d2-segth" style="padding:10px 16px">{{ tr('clients.segments.name') || 'Name' }}</th>
              <th class="d2-segth">{{ tr('clients.segments.members') || 'Members' }}</th>
              <th class="d2-segth">{{ tr('dashboard.bandwidth') || 'Bandwidth' }}</th>
              <th class="d2-segth">{{ tr('clients.segments.trafficLimit') || 'Traffic' }}</th>
              <th class="d2-segth">{{ tr('clients.expiry') || 'Expiry' }}</th>
              <th class="d2-segth" style="padding:10px 16px;text-align:right">{{ tr('common.actions') || 'Actions' }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="sg in segments" :key="sg.id" style="border-top:1px solid var(--border)" class="d2-hoverpanel2">
                <td data-mhead style="padding:11px 16px"><div style="display:flex;align-items:center;gap:9px"><span :style="{ width:'10px', height:'10px', borderRadius:'50%', background: sg.color || '#6B7280', flex:'none' }"></span><div><div style="font-weight:600">{{ sg.name }}</div><div style="font-size:11px;color:var(--text-3)">{{ sg.notes || '—' }}</div></div></div></td>
                <td :data-label="tr('clients.segments.members') || 'Members'" class="mono" style="padding:11px 10px;color:var(--text-2)">{{ sg.member_count ?? '—' }}</td>
                <td :data-label="tr('dashboard.bandwidth') || 'Bandwidth'" class="mono" style="padding:11px 10px;color:var(--text-2)">{{ sg.bandwidth_limit ? sg.bandwidth_limit + ' Mbps' : '∞' }}</td>
                <td :data-label="tr('clients.segments.trafficLimit') || 'Traffic'" class="mono" style="padding:11px 10px;color:var(--text-2)">{{ sg.traffic_limit_mb ? formatMB(sg.traffic_limit_mb) : '∞' }}</td>
                <td :data-label="tr('clients.expiry') || 'Expiry'" style="padding:11px 10px;color:var(--text-3)">{{ sg.expiry_date ? fmtDate(sg.expiry_date) : '∞' }}</td>
                <td data-mfull style="padding:11px 16px"><div style="display:flex;gap:3px;justify-content:flex-end">
                  <button type="button" @click="applySegment(sg)" :title="tr('clients.segments.apply') || 'Apply'" style="height:28px;padding:0 9px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font:inherit;font-size:11.5px;font-weight:550;cursor:pointer" class="d2-hoverpanel2">{{ tr('clients.segments.apply') || 'Apply' }}</button>
                  <button type="button" @click="enableSegment(sg)" :title="tr('clients.segments.enableAll') || 'Enable all'" style="width:28px;height:28px;border-radius:7px;border:none;background:transparent;color:var(--green);cursor:pointer;display:flex;align-items:center;justify-content:center" class="d2-hoverpanel3"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"></path></svg></button>
                  <button type="button" @click="disableSegment(sg)" :title="tr('clients.segments.disableAll') || 'Disable all'" style="width:28px;height:28px;border-radius:7px;border:none;background:transparent;color:var(--text-3);cursor:pointer;display:flex;align-items:center;justify-content:center" class="d2-hoverpanel3"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>
                  <button type="button" @click="editSegment(sg)" :title="tr('common.edit') || 'Edit'" style="width:28px;height:28px;border-radius:7px;border:none;background:transparent;color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center" class="d2-hoverpanel3"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"></path></svg></button>
                  <button type="button" @click="deleteSegment(sg)" :title="tr('common.delete') || 'Delete'" style="width:28px;height:28px;border-radius:7px;border:none;background:transparent;color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center" class="d2-rowbtn del"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
                </div></td>
              </tr>
            </tbody>
          </table>
        </div></div>
      </div>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { useClientsStore } from '../../stores/clients'
import { useRoute } from 'vue-router'
import { clientsApi, serversApi, segmentsApi, trafficApi } from '../../api'
import { formatBytes } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'
import Icon from '../ui/Icon.vue'
import D2Modal from '../ui/D2Modal.vue'
import D2Toggle from '../ui/D2Toggle.vue'
import D2Button from '../ui/D2Button.vue'
import D2HelpTip from '../ui/D2HelpTip.vue'
import D2Countdown from '../ui/D2Countdown.vue'
import D2MobileSheet from '../ui/D2MobileSheet.vue'

const { t } = useI18n({ useScope: 'global' })
function tr(k, p) { try { const v = t(k, p || {}); return v === k ? '' : v } catch (_) { return '' } }
const store = useClientsStore()
const ui = useD2Ui()
const route = useRoute()

// his preset chips ({ v: value, label })
const bwPresets = [ { v: 0, label: '∞' }, { v: 10, label: '10' }, { v: 25, label: '25' }, { v: 50, label: '50' }, { v: 100, label: '100' }, { v: 1000, label: '1G' } ]
const trafficPresets = [ { v: 0, label: '∞' }, { v: 1024, label: '1G' }, { v: 5120, label: '5G' }, { v: 10240, label: '10G' }, { v: 51200, label: '50G' }, { v: 102400, label: '100G' }, { v: 512000, label: '500G' } ]
const expiryPresets = [ { v: 0, label: '∞' }, { v: 7, label: '7d' }, { v: 14, label: '14d' }, { v: 30, label: '30d' }, { v: 60, label: '60d' }, { v: 90, label: '90d' }, { v: 180, label: '180d' }, { v: 365, label: '1y' } ]

const search = ref('')
const filterStatus = ref(''); const filterServer = ref(''); const filterSegment = ref('')
const servers = ref([]); const segments = ref([])
const bulkSegmentId = ref(''); const selectedIds = ref(new Set())
const currentPage = ref(1); const pageSize = 50
const sortKey = ref(''); const sortDir = ref('asc')
const MOBILE_FIELDS_KEY = 'flirexa:d2:clients-mobile-fields'
const MOBILE_FIELDS_DEFAULT = ['server', 'protocol']
function loadMobileFields() {
  try {
    const saved = JSON.parse(localStorage.getItem(MOBILE_FIELDS_KEY) || 'null')
    return Array.isArray(saved) ? saved.filter(Boolean) : [...MOBILE_FIELDS_DEFAULT]
  } catch (_) { return [...MOBILE_FIELDS_DEFAULT] }
}
const mobileFields = ref(loadMobileFields())
const mobileClient = ref(null)
const mobileFieldOptions = computed(() => [
  { key: 'ip', label: 'IP' },
  { key: 'server', label: tr('clients.server') || 'Server' },
  { key: 'protocol', label: tr('clients.protocol') || 'Protocol' },
  { key: 'traffic', label: tr('clients.traffic') || 'Traffic' },
  { key: 'bandwidth', label: tr('clients.bandwidth') || 'Bandwidth' },
  { key: 'segment', label: tr('clients.segment') || 'Segment' },
  { key: 'expiry', label: tr('clients.expiry') || 'Expires' },
  { key: 'status', label: tr('clients.status') || 'Status' },
])
function isMobilePrimary(key) { return mobileFields.value.includes(key) }
function toggleMobileField(key) {
  const next = new Set(mobileFields.value)
  if (next.has(key)) next.delete(key); else next.add(key)
  mobileFields.value = [...next]
  try { localStorage.setItem(MOBILE_FIELDS_KEY, JSON.stringify(mobileFields.value)) } catch (_) {}
}
function openMobileClient(client) { mobileClient.value = client }
function mobileClientAction(action) {
  const row = mobileClient.value
  if (!row) return
  mobileClient.value = null
  if (action === 'toggle') toggleClient(row._raw)
  else if (action === 'config') showConfig(row._raw)
  else if (action === 'share') generateShareLink(row._raw)
  else if (action === 'edit') editClient(row._raw)
  else if (action === 'delete') removeClient(row._raw)
}

// ── create/share/edit/config: reuse verified logic ──
const showCreateModal = ref(false); const creating = ref(false); const createError = ref('')
const newClient = ref({ name: '', server_id: null, bandwidth_limit: 0, expiry_days: 0, peer_visibility: false, customer_email: '', segment_id: null })
const newClientIsProxy = computed(() => isProxyBySrvId(newClient.value.server_id))
const newExpiryDate = ref('')
// keep the create modal's days-field and date-field in sync (his dual input)
function setNewExpiryDays(days) { newClient.value.expiry_days = days; newExpiryDate.value = days > 0 ? daysToDate(days) : '' }
watch(newExpiryDate, (iso) => { if (iso) newClient.value.expiry_days = dateToDays(iso) })
function openCreate() { createError.value = ''; newExpiryDate.value = ''; newClient.value = { name: '', server_id: servers.value[0]?.id ?? null, bandwidth_limit: 0, traffic_limit_mb: 0, expiry_days: 0, peer_visibility: false, customer_email: '', segment_id: null }; showCreateModal.value = true }
async function createClient() {
  creating.value = true; createError.value = ''
  try {
    const seg = newClient.value.segment_id
    const created = await store.createClient(newClient.value)
    showCreateModal.value = false
    if (created?.id != null && seg) { try { await segmentsApi.addMembers(Number(seg), [created.id]) } catch (_) {}; loadSegments() }
    await store.fetchClients(_params())
    if (created?.id != null) { highlightJustCreated(created.id); const fresh = store.clients.find(c => c.id === created.id) || created; await openShareModal(fresh, 'post-create') }
  } catch (err) { const d = err.response?.data?.detail; createError.value = (typeof d === 'string') ? d : (d?.message || err.message) } finally { creating.value = false }
}
const shareModal = ref({ show: false, mode: 'share', client: null, url: '', expiresAt: null, loading: false, copied: false, downloading: false, showQR: false, qrSrc: '' })
async function openShareModal(client, mode = 'share') {
  if (shareModal.value.qrSrc) { try { URL.revokeObjectURL(shareModal.value.qrSrc) } catch (_) {} }
  shareModal.value = { show: true, mode, client, url: '', expiresAt: null, loading: true, copied: false, downloading: false, showQR: false, qrSrc: '', proxyUri: '', proxyCopied: false }
  if (isProxyClient(client)) { try { const { data } = await clientsApi.getConfig(client.id); if (data?.uri) shareModal.value.proxyUri = data.uri } catch (_) {} }
  try { const { data } = await clientsApi.createShareLink(client.id); shareModal.value.url = data.url; shareModal.value.expiresAt = data.expires_at } catch (_) {} finally { shareModal.value.loading = false }
}
function generateShareLink(c) { openShareModal(c, 'share') }
function closeShareModal() { shareModal.value.show = false; if (shareModal.value.qrSrc) { try { URL.revokeObjectURL(shareModal.value.qrSrc) } catch (_) {}; shareModal.value.qrSrc = '' } }
async function toggleShareQR() { if (shareModal.value.showQR) { shareModal.value.showQR = false; return } shareModal.value.showQR = true; if (shareModal.value.qrSrc) return; try { const { data } = await clientsApi.getQR(shareModal.value.client.id); shareModal.value.qrSrc = URL.createObjectURL(data) } catch (_) { shareModal.value.showQR = false } }
// navigator.clipboard only exists in a secure context (https/localhost); many
// panels are reached over plain http or a self-signed IP, where it's undefined
// and the copy silently failed. Fall back to a hidden-textarea execCommand.
async function copyText(text) {
  const t = String(text || '')
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(t); return true } } catch (_) {}
  try {
    const ta = document.createElement('textarea')
    ta.value = t; ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'; ta.style.top = '0'; ta.style.left = '-9999px'
    document.body.appendChild(ta); ta.focus(); ta.select()
    try { ta.setSelectionRange(0, t.length) } catch (_) {}
    const ok = document.execCommand('copy'); document.body.removeChild(ta); return ok
  } catch (_) { return false }
}
async function copyShareUrl() { if (await copyText(shareModal.value.url)) { shareModal.value.copied = true; setTimeout(() => shareModal.value.copied = false, 2200) } }
async function copyProxyUri() { if (await copyText(proxyConfig.value?.uri)) { proxyCopied.value = true; setTimeout(() => proxyCopied.value = false, 2200) } }
async function copyShareProxyUri() { if (await copyText(shareModal.value.proxyUri)) { shareModal.value.proxyCopied = true; setTimeout(() => shareModal.value.proxyCopied = false, 2200) } }
async function downloadFromShare() { const c = shareModal.value.client; if (!c) return; shareModal.value.downloading = true; try { const { data } = await clientsApi.getConfigDownload(c.id); const url = URL.createObjectURL(new Blob([data])); const a = document.createElement('a'); a.href = url; a.download = (c.name || 'client').replace(/[^A-Za-z0-9._-]/g, '_') + '.conf'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1500) } catch (_) {} finally { shareModal.value.downloading = false } }

const highlightedClientId = ref(null); let _hl = null
function highlightJustCreated(id) { if (_hl) clearTimeout(_hl); highlightedClientId.value = id; currentPage.value = 1; _hl = setTimeout(() => { highlightedClientId.value = null }, 60000) }

const showEditModal = ref(false); const editingClient = ref(null)
const editForm = ref({ name: '', bandwidth: 0, trafficLimit: 0, segment_id: null }); const editInitial = ref({}); const editExpiryDate = ref('')
const editIsProxy = computed(() => isProxyClient(editingClient.value))
function editClient(c) { editingClient.value = c; editForm.value = { name: c.name || '', bandwidth: c.bandwidth_limit || 0, trafficLimit: c.traffic_limit_mb || 0, segment_id: c.segment_id || null }; editInitial.value = { ...editForm.value }; editExpiryDate.value = ''; showEditModal.value = true }
async function setEditExpiryDays(days) { editExpiryDate.value = days > 0 ? daysToDate(days) : '' }
async function resetTrafficNow() { const c = editingClient.value; if (!c) return; if (!await d2confirm(tr('clients.resetTrafficConfirm', { name: c.name }) || `Reset traffic counter for "${c.name}"?`)) return; try { await store.resetTraffic(c.id); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function saveEdit() {
  const c = editingClient.value
  try {
    const px = isProxyClient(c); const nm = (editForm.value.name || '').trim()
    if (nm && nm !== editInitial.value.name) await store.renameClient(c.id, nm)
    if (!px && editForm.value.bandwidth !== editInitial.value.bandwidth) await store.setBandwidth(c.id, editForm.value.bandwidth)
    if (!px && editForm.value.trafficLimit !== editInitial.value.trafficLimit) await store.setTrafficLimit(c.id, editForm.value.trafficLimit)
    if (editExpiryDate.value) { const days = dateToDays(editExpiryDate.value); await store.setExpiry(c.id, days) }
    if ((editForm.value.segment_id || null) !== (editInitial.value.segment_id || null)) { try { if (editForm.value.segment_id) await segmentsApi.addMembers(Number(editForm.value.segment_id), [c.id]); else if (editInitial.value.segment_id) await segmentsApi.removeMembers(Number(editInitial.value.segment_id), [c.id]) } catch (_) {}; loadSegments() }
    showEditModal.value = false; await store.fetchClients(_params())
  } catch (err) { alert(err.response?.data?.detail || err.message) }
}

const showConfigModal = ref(false); const configClient = ref(null); const clientConfig = ref(''); const qrUrl = ref(null); const qrAmneziaVpnUrl = ref(null); const isProxyConfig = ref(false); const proxyConfig = ref(null); const proxyCopied = ref(false)
function revokeQrs() { if (qrUrl.value) { try { URL.revokeObjectURL(qrUrl.value) } catch (_) {}; qrUrl.value = null } if (qrAmneziaVpnUrl.value) { try { URL.revokeObjectURL(qrAmneziaVpnUrl.value) } catch (_) {}; qrAmneziaVpnUrl.value = null } }
function closeConfigModal() { showConfigModal.value = false; revokeQrs() }
async function showConfig(c) { configClient.value = c; proxyConfig.value = null; isProxyConfig.value = false; revokeQrs(); try { const { data } = await clientsApi.getConfig(c.id); if (data.category === 'proxy') { isProxyConfig.value = true; proxyConfig.value = data } else clientConfig.value = data.config || data; showConfigModal.value = true; try { const q = await clientsApi.getQR(c.id); qrUrl.value = URL.createObjectURL(q.data) } catch (_) {} if (data.protocol === 'amneziawg') { try { const r = await clientsApi.getQR(c.id, 'amneziavpn'); qrAmneziaVpnUrl.value = URL.createObjectURL(r.data) } catch (_) {} } } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function downloadConfig() { const safe = (configClient.value?.name || 'client').replace(/[^A-Za-z0-9._-]/g, '_'); let text = clientConfig.value, ext = 'conf'; if (isProxyConfig.value) { text = proxyConfig.value?.config_text || ''; ext = proxyConfig.value?.protocol === 'hysteria2' ? 'yaml' : 'json' } const url = URL.createObjectURL(new Blob([text])); const a = document.createElement('a'); a.href = url; a.download = safe + '.' + ext; a.click(); URL.revokeObjectURL(url) }

async function toggleClient(c) { try { await store.toggleClient(c.id, !c.enabled) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function removeClient(c) { if (!await d2confirm(tr('clients.deleteConfirm', { name: c.name }) || `Delete "${c.name}"?`)) return; try { await store.deleteClient(c.id); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }

// bulk
function toggleSelect(id) { const s = new Set(selectedIds.value); s.has(id) ? s.delete(id) : s.add(id); selectedIds.value = s }
async function toggleSelectAll() { const s = new Set(selectedIds.value); if (allPageSelected.value) pagedClients.value.forEach(c => s.delete(c.id)); else pagedClients.value.forEach(c => s.add(c.id)); selectedIds.value = s }
async function bulkEnable() { const ids = [...selectedIds.value]; try { await Promise.all(ids.map(id => store.toggleClient(id, true))); await store.fetchClients(_params()); selectedIds.value = new Set() } catch (_) {} }
async function bulkDisable() { const ids = [...selectedIds.value]; try { await Promise.all(ids.map(id => store.toggleClient(id, false))); await store.fetchClients(_params()); selectedIds.value = new Set() } catch (_) {} }
async function bulkDelete() { if (!await d2confirm(`Delete ${selectedIds.value.size} client(s)?`)) return; const ids = [...selectedIds.value]; try { await Promise.all(ids.map(id => store.deleteClient(id))); await store.fetchClients(_params()); selectedIds.value = new Set() } catch (_) {} }
async function bulkAssignSegment() { const val = bulkSegmentId.value; if (!val || !selectedIds.value.size) { bulkSegmentId.value = ''; return } const ids = [...selectedIds.value]; try { if (val === '__remove__') await Promise.all(ids.map(id => { const c = store.clients.find(x => x.id === id); return c?.segment_id ? segmentsApi.removeMembers(c.segment_id, [id]).catch(() => {}) : Promise.resolve() })); else await segmentsApi.addMembers(Number(val), ids); await store.fetchClients(_params()); loadSegments(); selectedIds.value = new Set() } finally { bulkSegmentId.value = '' } }

// filter/sort/paginate
function _params() { const p = {}; const q = (search.value || '').trim(); if (q) p.q = q; return p }
let _sd = null
watch(search, () => { if (_sd) clearTimeout(_sd); _sd = setTimeout(() => store.fetchClients(_params()), 250) })
watch([filterStatus, filterServer, filterSegment], () => { currentPage.value = 1 })
function toggleSort(k) { if (sortKey.value === k) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; else { sortKey.value = k; sortDir.value = 'asc' } }
function sortIcon(k) { return sortKey.value === k ? (sortDir.value === 'asc' ? '↑' : '↓') : '' }
const filteredClients = computed(() => {
  let r = store.clients
  if (filterStatus.value === 'enabled') r = r.filter(c => c.enabled); else if (filterStatus.value === 'disabled') r = r.filter(c => !c.enabled)
  else if (filterStatus.value === 'online') r = r.filter(c => isOnline(c)); else if (filterStatus.value === 'offline') r = r.filter(c => !isOnline(c))
  else if (filterStatus.value === 'expiring') r = r.filter(c => isExpiringSoon(c))
  if (filterServer.value) r = r.filter(c => c.server_id === Number(filterServer.value))
  if (filterSegment.value) r = r.filter(c => c.segment_id === Number(filterSegment.value))
  if (sortKey.value) { const d = sortDir.value === 'asc' ? 1 : -1; r = [...r].sort((a, b) => { let va, vb; switch (sortKey.value) { case 'name': va = (a.name || '').toLowerCase(); vb = (b.name || '').toLowerCase(); return va < vb ? -d : va > vb ? d : 0; case 'server': va = srvName(a.server_id); vb = srvName(b.server_id); return va < vb ? -d : va > vb ? d : 0; case 'traffic': return (((a.traffic_used_rx || 0) + (a.traffic_used_tx || 0)) - ((b.traffic_used_rx || 0) + (b.traffic_used_tx || 0))) * d; case 'expiry': va = a.expiry_date ? new Date(a.expiry_date).getTime() : Infinity; vb = b.expiry_date ? new Date(b.expiry_date).getTime() : Infinity; return (va - vb) * d; default: return 0 } }) }
  return r
})
const orderedClients = computed(() => { const list = filteredClients.value, hid = highlightedClientId.value; if (!hid) return list; const i = list.findIndex(c => c.id === hid); if (i <= 0) return list; return [list[i], ...list.slice(0, i), ...list.slice(i + 1)] })
const totalPages = computed(() => Math.max(1, Math.ceil(orderedClients.value.length / pageSize)))
const pagedClients = computed(() => orderedClients.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const allPageSelected = computed(() => pagedClients.value.length > 0 && pagedClients.value.every(c => selectedIds.value.has(c.id)))

// adapter → his row shape
const PROTO = { wireguard: { label: 'WireGuard', color: 'var(--blue)', bg: 'var(--blue-soft)' }, amneziawg: { label: 'AmneziaWG', color: 'var(--purple)', bg: 'var(--purple-soft)' }, hysteria2: { label: 'Hysteria2', color: 'var(--amber)', bg: 'var(--amber-soft)' }, tuic: { label: 'TUIC', color: 'var(--amber)', bg: 'var(--amber-soft)' }, 'vless-reality': { label: 'VLESS-Reality', color: 'var(--amber)', bg: 'var(--amber-soft)' } }
const rows = computed(() => pagedClients.value.map(c => {
  const srv = servers.value.find(s => s.id === c.server_id); const ptype = srv?.server_type || 'wireguard'; const pr = PROTO[ptype] || PROTO.wireguard
  const used = (c.traffic_used_rx || 0) + (c.traffic_used_tx || 0); const limitMb = c.traffic_limit_mb || 0
  const pct = limitMb ? Math.min(100, (used / (limitMb * 1048576)) * 100) : 0
  return {
    id: c.id, _raw: c, name: c.name, ip: c.ipv4 || '—', server: srvName(c.server_id), enabled: c.enabled,
    dotColor: c.enabled ? (isOnline(c) ? 'var(--green)' : 'var(--text-3)') : 'var(--red)',
    statusTitle: c.enabled ? (isOnline(c) ? 'Online' : 'Offline') : 'Disabled',
    protoLabel: pr.label, protoColor: pr.color, protoBg: pr.bg,
    trafficLabel: formatBytes(used), hasLimit: !!limitMb, trafficPct: pct + '%', trafficBarColor: pct > 90 ? 'var(--red)' : pct > 70 ? 'var(--amber)' : 'var(--accent)',
    bwLabel: c.bandwidth_limit ? c.bandwidth_limit + ' Mbps' : '∞',
    segment: c.segment_id ? (segments.value.find(s => s.id === c.segment_id)?.name || '') : '',
    segColor: c.segment_id ? (segments.value.find(s => s.id === c.segment_id)?.color || 'var(--accent)') : 'var(--accent)',
    expiresLabel: c.expiry_date ? fmtDate(c.expiry_date) : '∞', expiresColor: isExpiringSoon(c) ? 'var(--red)' : 'var(--text-2)',
    toggleTitle: c.enabled ? 'Disable' : 'Enable',
  }
}))

function srvName(id) { return servers.value.find(s => s.id === id)?.name || '—' }
function isProxyBySrvId(id) { const s = servers.value.find(x => x.id === id); return s?.server_category === 'proxy' || s?.server_type === 'hysteria2' || s?.server_type === 'tuic' }
function isProxyClient(c) { return c ? isProxyBySrvId(c.server_id) : false }
function isOnline(c) { return c.last_handshake ? (Date.now() - new Date(c.last_handshake).getTime() < 180000) : false }
function isExpiringSoon(c) { return c.expiry_date ? (new Date(c.expiry_date) - new Date() < 7 * 864e5) : false }
function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—' }
function dateToDays(iso) { if (!iso) return 0; const tt = new Date(iso + 'T00:00:00'); const n = new Date(); n.setHours(0, 0, 0, 0); const diff = Math.round((tt - n) / 864e5); return diff > 0 ? diff : 0 }
function daysToDate(days) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + Number(days || 0)); const m = String(d.getMonth() + 1).padStart(2, '0'); const dd = String(d.getDate()).padStart(2, '0'); return `${d.getFullYear()}-${m}-${dd}` }
function formatMB(mb) { const n = Number(mb) || 0; if (n >= 1048576) return (n / 1048576).toFixed(1) + ' TB'; if (n >= 1024) return (n / 1024).toFixed(1) + ' GB'; return n + ' MB' }
async function loadSegments() { try { const r = await segmentsApi.list(); const d = r.data; segments.value = Array.isArray(d) ? d : (d?.items || []) } catch (_) { segments.value = [] } }

// ── Segments Manager modal (his 760px manager) ──
const showSegmentsModal = ref(false); const segSaving = ref(false); const segEditingId = ref(null)
const trafficRules = ref([]); const showSegRuleForm = ref(false); const creatingSegRule = ref(false)
function emptySegForm() { return { name: '', color: '#6B7280', notes: '', bandwidth_limit: 0, traffic_limit_mb: 0, expiry_date: '', auto_bandwidth_rule_id: null } }
function emptySegRuleForm() { return { name: '', period: 'month', threshold_mb: null, bandwidth_limit_mbps: null } }
const segForm = ref(emptySegForm()); const segRuleForm = ref(emptySegRuleForm())
function resetSegForm() { segEditingId.value = null; segForm.value = emptySegForm(); showSegRuleForm.value = false; segRuleForm.value = emptySegRuleForm() }
async function openSegments() { resetSegForm(); showSegmentsModal.value = true; await Promise.all([loadSegments(), loadTrafficRules()]) }
async function loadTrafficRules() { try { const r = await trafficApi.getRules(); const d = r.data; trafficRules.value = Array.isArray(d) ? d : (d?.items || []) } catch (_) { trafficRules.value = [] } }
function editSegment(sg) { segEditingId.value = sg.id; segForm.value = { name: sg.name || '', color: sg.color || '#6B7280', notes: sg.notes || '', bandwidth_limit: sg.bandwidth_limit || 0, traffic_limit_mb: sg.traffic_limit_mb || 0, expiry_date: sg.expiry_date ? String(sg.expiry_date).split('T')[0] : '', auto_bandwidth_rule_id: sg.auto_bandwidth_rule_id || null } }
async function saveSegment() {
  segSaving.value = true
  try {
    const payload = { ...segForm.value }
    payload.bandwidth_limit = Number(payload.bandwidth_limit) || null
    payload.traffic_limit_mb = Number(payload.traffic_limit_mb) || null
    if (!payload.expiry_date) payload.expiry_date = null
    if (segEditingId.value) await segmentsApi.update(segEditingId.value, payload); else await segmentsApi.create(payload)
    resetSegForm(); await loadSegments(); await store.fetchClients(_params())
  } catch (err) { alert(err.response?.data?.detail || err.message) } finally { segSaving.value = false }
}
async function deleteSegment(sg) { if (!await d2confirm(tr('clients.segments.deleteConfirm', { name: sg.name }) || `Delete segment "${sg.name}"?`)) return; try { await segmentsApi.remove(sg.id); await loadSegments(); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function applySegment(sg) { try { await segmentsApi.apply(sg.id); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function enableSegment(sg) { try { await segmentsApi.enable(sg.id); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function disableSegment(sg) { try { await segmentsApi.disable(sg.id); await store.fetchClients(_params()) } catch (err) { alert(err.response?.data?.detail || err.message) } }
async function createSegRule() {
  const r = segRuleForm.value
  if (!r.name || !r.threshold_mb || !r.bandwidth_limit_mbps) { alert(tr('clients.segments.ruleIncomplete') || 'Fill in rule name, threshold and limit'); return }
  creatingSegRule.value = true
  try {
    const res = await trafficApi.createRule({ name: r.name, period: r.period, threshold_mb: Number(r.threshold_mb), bandwidth_limit_mbps: Number(r.bandwidth_limit_mbps), client_id: null })
    await loadTrafficRules()
    const newId = res.data?.id ?? res.data?.rule?.id; if (newId) segForm.value.auto_bandwidth_rule_id = newId
    showSegRuleForm.value = false; segRuleForm.value = emptySegRuleForm()
  } catch (err) { alert(err.response?.data?.detail || err.message) } finally { creatingSegRule.value = false }
}

onMounted(async () => {
  // Deep-link from the Dashboard "expiring soon" banner → land pre-filtered on
  // exactly the clients whose term is within 7 days (isExpiringSoon). The user
  // can clear it via the status dropdown.
  if (route.query.expiring) filterStatus.value = 'expiring'
  ui.set({ title: tr('nav.clients') || 'Clients', searchPh: tr('clients.searchPlaceholder') || 'Search name or IP…', onSearch: v => { search.value = v }, primary: { label: tr('clients.newClient') || 'New client', onClick: openCreate } })
  await Promise.all([
    store.fetchClients(_params()),
    serversApi.getAll().then(res => { const sd = res.data; servers.value = sd?.items || (Array.isArray(sd) ? sd : []) }),
    loadSegments(),
  ])
})
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-th.srt { cursor: pointer; user-select: none; }
.d2-th.srt:hover { color: var(--text-2); }
.d2-sel { height: 34px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 9px; padding: 0 9px; font: inherit; font-size: 12.5px; outline: none; cursor: pointer; }
.d2-sel-sm { height: 32px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 8px; padding: 0 9px; font: inherit; font-size: 12.5px; outline: none; cursor: pointer; }
.d2-btn-sm { height: 32px; padding: 0 12px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 8px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.d2-btn-sm:hover { background: var(--panel-2); }
.d2-lnkbtn { height: 28px; padding: 0 10px; border: none; background: transparent; color: var(--text-3); border-radius: 7px; font: inherit; font-size: 12px; font-weight: 500; cursor: pointer; }
.d2-lnkbtn:hover { background: var(--panel-2); color: var(--text-2); }
.d2-rowbtn { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-rowbtn:hover { background: var(--panel-3); color: var(--text); }
.d2-rowbtn.del:hover { background: var(--red-soft); color: var(--red); }
tr.hot td { background: var(--green-soft); animation: d2hot 60s ease-out forwards; }
@keyframes d2hot { 0% { background: rgba(40,167,69,.20); } 100% { background: rgba(40,167,69,.03); } }

/* generic hover helpers reused across modals / rows */
.d2-hoverpanel2:hover { background: var(--panel-2); }
.d2-hoverpanel3:hover { background: var(--panel-3); }

/* his form primitives (create/edit/segments modals) */
.d2-flabel { display: block; font-size: 12.5px; font-weight: 550; margin-bottom: 7px; }
.d2-finput { width: 100%; height: 42px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 13px; font: inherit; font-size: 13.5px; outline: none; box-sizing: border-box; }
.d2-finput:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-finput.mono { font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.d2-fselect { width: 100%; height: 42px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 11px; font: inherit; font-size: 13.5px; outline: none; cursor: pointer; box-sizing: border-box; }
.d2-fselect:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2-finput-sm { height: 38px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 9px; padding: 0 11px; font: inherit; font-size: 12.5px; outline: none; box-sizing: border-box; }
.d2-finput-sm:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); }
.d2-finput-sm.mono { font-family: 'JetBrains Mono', monospace; }
.d2-fselect-sm { height: 38px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 9px; padding: 0 9px; font: inherit; font-size: 12.5px; outline: none; cursor: pointer; box-sizing: border-box; }

/* preset chip row (bandwidth / traffic / expiry) */
.d2-chiprow { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; }
.d2-chip { height: 30px; padding: 0 11px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 8px; font: inherit; font-size: 11.5px; font-family: 'JetBrains Mono', monospace; cursor: pointer; }
.d2-chip:hover { background: var(--panel-2); }
.d2-chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }

.d2-client-card-options { display:none; position:relative; }
.d2-client-card-options summary { list-style:none; display:flex;align-items:center;gap:7px;height:34px;padding:0 12px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font-size:12.5px;font-weight:550;cursor:pointer; }
.d2-client-card-options summary::-webkit-details-marker { display:none; }
.d2-client-card-options-menu { position:absolute;right:0;top:40px;z-index:25;width:min(260px, calc(100vw - 48px));padding:10px;background:var(--panel);border:1px solid var(--border);border-radius:11px;box-shadow:var(--shadow-lg); }
.d2-client-card-options-title { padding:3px 4px 8px;font-size:11px;color:var(--text-3); }
.d2-client-card-options-menu label { display:flex;align-items:center;gap:9px;padding:8px 6px;font-size:13px;color:var(--text-2);cursor:pointer; }
.d2-client-card-options-menu input { accent-color:var(--accent);width:16px;height:16px; }
.d2-clients-mobile { display:none; }
.d2-client-sheet-status { display:flex;align-items:center;gap:7px;margin-bottom:12px;color:var(--text-2);font-size:12px;font-weight:600; }
.d2-client-sheet-status span { width:8px;height:8px;border-radius:50%; }
.d2-client-sheet-details { margin:0;border:1px solid var(--border);border-radius:12px;overflow:hidden; }
.d2-client-sheet-details > div { display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 12px;border-top:1px solid var(--border); }
.d2-client-sheet-details > div:first-child { border-top:0; }
.d2-client-sheet-details dt { color:var(--text-3);font-size:11.5px; }
.d2-client-sheet-details dd { margin:0;min-width:0;text-align:right;overflow-wrap:anywhere;color:var(--text-2);font-size:12.5px;font-weight:550; }
.d2-client-sheet-actions { display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px; }
.d2-client-sheet-actions button { min-height:40px;padding:8px 11px;border:1px solid var(--border-strong);border-radius:10px;background:var(--panel-2);color:var(--text-2);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer; }
.d2-client-sheet-actions button.danger { color:var(--red);background:var(--red-soft);border-color:transparent; }

@media (max-width:900px) {
  .d2-clients-filters { display:grid !important;grid-template-columns:1fr 1fr;align-items:center !important; }
  .d2-clients-filters > div:first-child { grid-column:1 / -1; }
  .d2-clients-filters .d2-sel { width:100%;min-width:0; }
  .d2-clients-filters > .d2-hoverpanel2 { margin-left:0 !important;justify-content:center; }
  .d2-client-card-options { display:block; }
  .d2-clients-list { background:transparent !important;border:0 !important;box-shadow:none !important;overflow:visible !important; }
  .d2-clients-desktop { display:none; }
  .d2-clients-mobile { display:block;background:var(--panel);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow);overflow:hidden; }
  .d2-client-mobile-row { display:flex;align-items:center;gap:9px;min-height:64px;padding:8px 9px 8px 12px;border-top:1px solid var(--border);background:var(--panel); }
  .d2-client-mobile-row:first-child { border-top:0; }
  .d2-client-mobile-row.hot { background:var(--green-soft); }
  .d2-client-mobile-row > input { width:16px;height:16px;flex:none;accent-color:var(--accent); }
  .d2-client-mobile-main { display:block;flex:1;min-width:0;padding:3px 0;border:0;background:transparent;color:var(--text);font:inherit;text-align:left;cursor:pointer; }
  .d2-client-mobile-title { display:flex;align-items:center;gap:7px;min-width:0; }
  .d2-client-mobile-title i { width:7px;height:7px;border-radius:50%;flex:none; }
  .d2-client-mobile-title b { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13.5px;font-weight:650; }
  .d2-client-mobile-primary { display:flex;align-items:center;gap:5px;min-width:0;margin-top:5px;overflow:hidden;color:var(--text-3);font-size:10.5px; }
  .d2-client-mobile-primary > span { flex:none;max-width:42%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
  .d2-client-mobile-primary > span + span::before { content:'·';margin-right:5px;color:var(--text-3); }
  .d2-client-mobile-primary > span[style] { padding:2px 5px;border-radius:5px;font-weight:600; }
  .d2-client-mobile-primary > span[style]::before { content:none; }
  .d2-client-mobile-more { width:38px;height:38px;display:grid;place-items:center;flex:none;border:0;border-radius:10px;background:transparent;color:var(--text-3);cursor:pointer; }
  .d2-client-mobile-more:active { background:var(--panel-2);color:var(--text); }
}

/* segments manager table headers */
.d2-segth { padding: 10px 10px; font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }

@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
