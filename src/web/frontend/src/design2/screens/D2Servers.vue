<!-- Servers — his exact card grid (toolbar Discover + header w/ subtitle-icon +
     status pill + type/default/pinned/hidden/version/agent badges + endpoint +
     stats + usage bar + details disclosure + top-consumers + Clients/Test
     actions + ⋮ menu), reproduced 1:1. Wired to useServersStore + serversApi
     (setDefault/rename/visibility/install-agent/delete/discover/keypair/expand-
     pool/migrate/bandwidth/install-proxy/getClients/getStats). Modals use the
     shared D2Modal primitives with his FIELDS + "?" tooltips. -->
<template>
  <div>
    <!-- toolbar: count + Discover -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
      <div style="font-size:12.5px;color:var(--text-3)">{{ store.servers.length }} {{ tr('nav.servers') || 'servers' }}</div>
      <button @click="openDiscover" style="margin-left:auto;display:flex;align-items:center;gap:7px;height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="hov-panel2"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4-4"></path></svg>{{ tr('servers.discover') || 'Import server (Discover)' }}</button>
      <button v-if="agentFleetCount > 0" @click="openReinstallAll" style="display:flex;align-items:center;gap:7px;height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="hov-panel2"><Icon name="bot" :size="15" />{{ tr('servers.reinstallAllAgents') || 'Reinstall agents' }}<span class="mono" style="font-size:11px;color:var(--text-3)">({{ agentFleetCount }})</span></button>
    </div>

    <div v-if="store.loading && !store.servers.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
    <div v-else-if="!store.servers.length" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:56px;text-align:center;color:var(--text-3)">{{ tr('servers.noServers') || 'No servers yet' }}</div>

    <div class="d2-svgrid">
      <div v-for="s in cards" :key="s.id" style="position:relative;background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:15px 16px;display:flex;flex-direction:column;gap:11px">
        <!-- header -->
        <div style="display:flex;align-items:flex-start;gap:8px">
          <div style="flex:1;min-width:0">
            <div style="font-weight:650;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ s.name }}</div>
            <div style="display:flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-3);margin-top:2px"><Icon :name="s.subIcon" :size="12" style="flex:none" /><span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-style:italic">{{ s.subtitle }}</span></div>
          </div>
          <span :style="{ display:'inline-flex', alignItems:'center', gap:'5px', fontSize:'11px', fontWeight:600, padding:'3px 9px', borderRadius:'20px', color:s.statusColor, background:s.statusBg, flex:'none' }"><span :style="{ width:'6px', height:'6px', borderRadius:'50%', background:s.statusColor }"></span>{{ s.statusLabel }}</span>
          <button @click.stop="menuFor = menuFor === s.id ? null : s.id" :style="{ width:'28px', height:'28px', borderRadius:'7px', border:'none', background: menuFor === s.id ? 'var(--panel-2)' : 'transparent', color:'var(--text-2)', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }" class="hov-panel2"><svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6"></circle><circle cx="12" cy="12" r="1.6"></circle><circle cx="12" cy="19" r="1.6"></circle></svg></button>
        </div>
        <!-- badges -->
        <div style="display:flex;flex-wrap:wrap;gap:5px">
          <span :style="{ display:'inline-flex', alignItems:'center', gap:'4px', fontSize:'10.5px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', color:s.typeColor, background:s.typeBg }"><Icon :name="s.typeIcon" :size="11" />{{ s.typeLabel }}</span>
          <span v-if="s.isDefault" style="display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;color:var(--accent);background:var(--accent-soft)"><Icon name="star" :size="11" />{{ tr('servers.default') || 'Default' }}</span>
          <span v-if="s.pinned" style="display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;color:var(--amber);background:var(--amber-soft)"><Icon name="pin" :size="11" />{{ tr('servers.pinned') || 'Pinned' }}</span>
          <span v-if="s.appOnly" style="display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;color:var(--purple);background:var(--purple-soft)"><Icon name="phone" :size="11" />{{ tr('servers.appOnly') || 'App-only' }}</span>
          <span v-if="s.hidden" style="display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;color:var(--text-3);background:var(--panel-2)"><Icon name="eyeoff" :size="11" />{{ tr('servers.hidden') || 'Hidden' }}</span>
          <span v-if="s.version" class="mono" style="display:inline-flex;align-items:center;font-size:10.5px;font-weight:500;padding:2px 7px;border-radius:6px;color:var(--text-3);background:var(--panel-2)">v{{ s.version }}</span>
          <button v-if="s.showAgentBadge" @click.stop="openAgent(s._raw)" :title="s.agentLabel" :style="{ display:'inline-flex', alignItems:'center', gap:'4px', fontSize:'10.5px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', border:'none', color:s.agentColor, background:s.agentBg, cursor:'pointer', fontFamily:'inherit' }"><Icon :name="s.agentIcon" :size="11" />{{ s.agentLabel }}</button>
        </div>
        <!-- endpoint -->
        <div class="mono" style="font-size:12.5px;color:var(--text-2)">{{ s.endpoint }}</div>
        <!-- stats -->
        <div style="display:flex;gap:14px">
          <div><div class="mono" style="font-size:15px;font-weight:680">{{ s.clients }}<span style="font-size:11px;color:var(--text-3);font-weight:500">/{{ s.maxClients }}</span></div><div style="font-size:10.5px;color:var(--text-3);margin-top:1px">{{ tr('servers.peers') || 'peers' }}</div></div>
          <div style="min-width:0"><div style="font-size:15px;font-weight:680;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ s.location }}</div><div style="font-size:10.5px;color:var(--text-3);margin-top:1px">{{ tr('servers.location') || 'location' }}</div></div>
          <div><div class="mono" style="font-size:15px;font-weight:680">{{ s.bandwidth }}<span style="font-size:10.5px;color:var(--text-3);font-weight:500"> Mbps</span></div><div style="font-size:10.5px;color:var(--text-3);margin-top:1px">{{ tr('servers.bandwidth') || 'bandwidth' }}</div></div>
        </div>
        <!-- usage bar -->
        <div style="display:flex;align-items:center;gap:9px">
          <div style="flex:1;height:5px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:s.barColor, width:s.pct }"></div></div>
          <span class="mono" style="font-size:11px;color:var(--text-3)">{{ s.pctLabel }}</span>
        </div>
        <!-- details disclosure -->
        <button @click="toggleDetails(s)" style="display:flex;align-items:center;gap:6px;border:none;background:transparent;color:var(--text-2);font:inherit;font-size:12px;font-weight:500;cursor:pointer;padding:0" class="hov-text"><span :style="{ display:'flex', transform: detailsFor === s.id ? 'rotate(90deg)' : 'none', transition:'transform .15s' }"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"></path></svg></span>{{ tr('servers.details') || 'Details' }}</button>
        <div v-if="detailsFor === s.id" style="display:flex;flex-direction:column;gap:7px;padding:11px 12px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)">
          <div v-for="d in s.detailRows" :key="d.k" style="display:flex;gap:8px;align-items:center"><span style="font-size:11.5px;color:var(--text-3);flex:none">{{ d.k }}</span><span class="mono" style="margin-left:auto;font-size:11.5px;color:var(--text-2);text-align:right;word-break:break-all">{{ d.v }}</span><button v-if="d.copy" type="button" @click.stop="copyText(d.copy)" :title="tr('common.copy') || 'Copy'" style="display:flex;flex:none;border:none;background:transparent;color:var(--text-3);cursor:pointer;padding:2px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button></div>
          <div v-if="topConsumers.length && topFor === s.id" style="margin-top:4px;padding-top:9px;border-top:1px solid var(--border)">
            <div style="font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);margin-bottom:7px">{{ tr('servers.topConsumers') || 'Top consumers' }}</div>
            <div v-for="tc in topConsumers" :key="tc.name" style="display:flex;align-items:center;gap:9px;margin-bottom:6px"><span style="font-size:11.5px;color:var(--text-2);width:90px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:none">{{ tc.name }}</span><div style="flex:1;height:5px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:tc.pct }"></div></div><span class="mono" style="font-size:11px;color:var(--text-3);width:54px;text-align:right;flex:none">{{ tc.label }}</span></div>
          </div>
        </div>
        <!-- actions -->
        <div style="display:flex;gap:8px;margin-top:1px">
          <button @click="openSvClients(s._raw)" style="flex:1;display:flex;align-items:center;justify-content:center;gap:7px;height:36px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="hov-accent2"><Icon name="users" :size="15" />{{ tr('servers.clients') || 'Clients' }}</button>
          <button @click="reconcile(s._raw)" style="flex:1;display:flex;align-items:center;justify-content:center;gap:7px;height:36px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="hov-panel2"><Icon name="pulse" :size="15" />{{ tr('servers.test') || 'Test connection' }}</button>
        </div>
        <!-- menu -->
        <template v-if="menuFor === s.id">
          <div @click.stop="menuFor = null" style="position:fixed;inset:0;z-index:48"></div>
          <div style="position:absolute;top:46px;right:14px;z-index:50;width:248px;max-height:420px;overflow-y:auto;background:var(--panel);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow-lg);padding:6px" @click.stop>
            <template v-for="(mi, i) in menuItems(s._raw)" :key="i">
              <div v-if="mi.divider" style="height:1px;background:var(--border);margin:5px 8px"></div>
              <button v-else @click="run(mi.onClick)" :style="{ display:'flex', alignItems:'center', gap:'11px', width:'100%', padding:'8px 10px', border:'none', background:'transparent', color:mi.danger ? 'var(--red)' : 'var(--text)', font:'inherit', fontSize:'13px', cursor:'pointer', textAlign:'left', borderRadius:'8px' }" class="d2-mi"><Icon :name="mi.icon" :size="16" :style="{ color: mi.danger ? 'var(--red)' : 'var(--text-2)' }" /><span style="flex:1">{{ mi.label }}</span></button>
            </template>
          </div>
        </template>
      </div>
    </div>

    <!-- ═══ modals (functional) ═══ -->
    <D2Modal :open="showAdd" :title="tr('servers.addServer') || 'Add server'" size="md" @close="showAdd = false">
      <div style="display:flex;flex-direction:column;gap:14px">
        <!-- category cards (his: title + subtitle, 2px active border) -->
        <div>
          <label style="display:block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);margin-bottom:8px">{{ tr('servers.category') || 'Category' }}</label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <button @click="setCategory('vpn')" :style="cardStyle(ns.server_category === 'vpn')"><div style="font-weight:620;font-size:13.5px">{{ tr('servers.catVpn') || 'VPN server' }}</div><div style="font-size:11.5px;color:var(--text-3);margin-top:2px">{{ tr('servers.catVpnDesc') || 'WireGuard / AmneziaWG tunnel' }}</div></button>
            <button @click="setCategory('proxy')" :style="cardStyle(ns.server_category === 'proxy')"><div style="display:flex;align-items:center;font-weight:620;font-size:13.5px">{{ tr('servers.catProxy') || 'Proxy server' }}<D2HelpTip :text="tr('help.protocolMatrix') || 'Proxy protocols (Hysteria2/TUIC) tunnel over QUIC to bypass DPI.'" /></div><div style="font-size:11.5px;color:var(--text-3);margin-top:2px">{{ tr('servers.catProxyDesc') || 'Hysteria2 / TUIC' }}</div></button>
          </div>
        </div>
        <!-- protocol cards -->
        <div>
          <label style="display:block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-3);margin-bottom:8px">{{ tr('servers.protocol') || 'Protocol' }}</label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <template v-if="ns.server_category === 'vpn'">
              <button @click="ns.server_type = 'wireguard'; onProto()" :style="cardStyle(ns.server_type === 'wireguard', true)"><div style="display:flex;align-items:center;gap:7px"><span style="font-weight:620;font-size:13px">WireGuard</span></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ tr('servers.protoWgDesc') || 'Fast classic WireGuard' }}</div></button>
              <button @click="ns.server_type = 'amneziawg'; onProto()" :style="cardStyle(ns.server_type === 'amneziawg', true)"><div style="display:flex;align-items:center;gap:7px"><span style="font-weight:620;font-size:13px">AmneziaWG</span><D2HelpTip :text="tr('help.awgType') || 'AmneziaWG — obfuscated protocol for restrictive networks.'" /></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ tr('servers.protoAwgDesc') || 'WG with obfuscation (DPI-bypass)' }}</div></button>
            </template>
            <template v-else>
              <button @click="ns.server_type = 'hysteria2'; onProto()" :style="cardStyle(ns.server_type === 'hysteria2', true)"><div style="display:flex;align-items:center;gap:7px"><span style="font-weight:620;font-size:13px">Hysteria 2</span><D2HelpTip :text="tr('help.hysteria2') || 'QUIC proxy, SOCKS5/HTTP forward.'" /></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ tr('servers.protoHy2Desc') || 'QUIC proxy, DPI-resistant' }}</div></button>
              <button @click="ns.server_type = 'tuic'; onProto()" :style="cardStyle(ns.server_type === 'tuic', true)"><div style="display:flex;align-items:center;gap:7px"><span style="font-weight:620;font-size:13px">TUIC</span><D2HelpTip :text="tr('help.tuic') || 'QUIC proxy with UDP relay.'" /></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ tr('servers.protoTuicDesc') || 'QUIC proxy with UDP relay' }}</div></button>
              <button @click="ns.server_type = 'vless-reality'; onProto()" :style="cardStyle(ns.server_type === 'vless-reality', true)"><div style="display:flex;align-items:center;gap:7px"><span style="font-weight:620;font-size:13px">VLESS-Reality</span><D2HelpTip :text="tr('help.vlessReality') || 'VLESS + Reality TLS camouflage (TCP/443).'" /></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ tr('servers.protoVlessDesc') || 'TCP/443, borrows a real TLS site' }}</div></button>
            </template>
          </div>
        </div>
        <D2Field v-model="ns.name" :label="tr('servers.name') || 'Name (optional)'" placeholder="primary-eu" />
        <!-- endpoint + autodetect -->
        <div class="d2-field"><label class="d2-flabel">{{ tr('servers.endpoint') || 'Endpoint' }}<D2HelpTip :text="tr('servers.addressHelp') || 'IP or domain clients connect to.'" /></label><div style="display:flex;gap:8px"><input class="d2f-input" v-model="ns.endpoint" placeholder="203.0.113.5" style="flex:1" /><button class="d2-pick sm" style="flex:none" :disabled="detectingIp" @click="autodetectIp">{{ detectingIp ? '…' : (tr('servers.autodetect') || 'Auto-detect') }}</button></div></div>
        <template v-if="ns.server_category === 'vpn'">
          <div class="d2-2col"><D2Field v-model="ns.interface" :label="tr('servers.interface') || 'Interface'" /><D2Field v-model="ns.listen_port" type="number" :label="tr('servers.listenPort') || 'Port'" /></div>
          <div class="d2-2col"><D2Field v-model="ns.address_pool_ipv4" :label="tr('servers.addressPool') || 'Address pool'" /><D2Field v-model="ns.max_clients" type="number" :label="tr('servers.maxClients') || 'Max clients'" /></div>
          <D2Field v-model="ns.dns" :label="tr('servers.dns') || 'DNS'" />
          <D2Toggle v-model="ns.split_tunnel_support">{{ tr('servers.splitTunnel') || 'Split tunneling' }}<template #help><D2HelpTip :text="tr('help.splitTunnel') || 'Only configured subnets go through VPN.'" /></template></D2Toggle>
          <D2Toggle v-model="ns.ipv4_only">{{ tr('servers.ipv4Only') || 'IPv4 only' }}<template #help><D2HelpTip :text="tr('servers.ipv4OnlyHint') || 'Strips IPv6 from client configs.'" /></template></D2Toggle>
        </template>
        <template v-else>
          <D2Field v-model="ns.listen_port" type="number" :label="tr('servers.listenPort') || 'Port'"><template #help><D2HelpTip :text="tr('servers.proxyPortHint') || 'Port the proxy listens on. 443 blends in as normal HTTPS, but it must be FREE on the target. Many servers already run nginx on 443. Pick another port (e.g. 8443) if 443 is taken.'" /></template></D2Field>
          <template v-if="ns.server_type !== 'vless-reality'">
            <div class="d2-field"><label class="d2-flabel">{{ tr('servers.tlsMode') || 'TLS mode' }}<D2HelpTip :text="tr('servers.tlsModeHint') || 'Self-signed / ACME / Manual.'" /></label><div style="display:flex;gap:8px"><button v-for="m in ['self_signed','acme','manual']" :key="m" class="d2-pick sm" :class="{ on: ns.proxy_tls_mode === m }" @click="ns.proxy_tls_mode = m">{{ m === 'self_signed' ? 'Self-signed' : m.toUpperCase() }}</button></div></div>
            <div v-if="ns.proxy_tls_mode === 'acme'" style="display:flex;align-items:flex-start;gap:8px;padding:9px 12px;border:1px solid var(--amber-soft);background:var(--amber-soft);border-radius:9px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8" style="margin-top:1px;flex:none"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5M12 16h.01"></path></svg><span style="font-size:12px;color:var(--text-2);line-height:1.45">{{ tr('servers.acmeDomainRequired') || 'ACME requires a public domain resolving to this server.' }}</span></div>
            <D2Field v-if="ns.proxy_tls_mode !== 'self_signed'" v-model="ns.proxy_domain" :label="tr('servers.proxyDomain') || 'Proxy domain'"><template #help><D2HelpTip :text="tr('servers.proxyDomainHint') || 'Domain for TLS SNI (required for ACME).'" /></template></D2Field>
            <D2Field v-if="ns.server_type === 'hysteria2'" v-model="ns.proxy_obfs_password" :label="tr('servers.obfs') || 'OBFS password'"><template #help><D2HelpTip :text="tr('servers.obfsTooltip') || 'Bypass DPI. Empty = disabled.'" /></template></D2Field>
          </template>
          <D2Field v-else v-model="ns.proxy_domain" :label="tr('servers.proxyDomainVless') || 'Camouflage domain (SNI)'" placeholder="www.microsoft.com"><template #help><D2HelpTip :text="tr('servers.proxyDomainVlessHint') || 'Real TLS site to impersonate. Default www.microsoft.com.'" /></template></D2Field>
        </template>
        <!-- connection -->
        <div class="d2-field"><label class="d2-flabel">{{ tr('servers.connectionMode') || 'Connection' }}<D2HelpTip :text="tr('help.agentMode') || 'Agent manages WG over SSH without storing creds.'" /></label><div style="display:flex;gap:8px"><button class="d2-pick sm" :class="{ on: ns.agent_mode !== 'mikrotik' }" @click="ns.agent_mode = 'ssh'">SSH + agent</button><button v-if="ns.server_category === 'vpn'" class="d2-pick sm" :class="{ on: ns.agent_mode === 'mikrotik' }" @click="ns.agent_mode = 'mikrotik'">MikroTik</button></div></div>
        <template v-if="ns.agent_mode === 'mikrotik'"><D2Field v-model="ns.mikrotik_url" :label="tr('servers.mikrotikUrl') || 'RouterOS URL'" placeholder="https://router.local/rest" /><div class="d2-2col"><D2Field v-model="ns.mikrotik_username" :label="tr('servers.mikrotikUser') || 'User'" /><D2Field v-model="ns.mikrotik_password" type="password" :label="tr('servers.mikrotikPass') || 'Password'" /></div></template>
        <template v-else><D2Field v-model="ns.ssh_host" :label="tr('servers.sshHost') || 'SSH host'" :placeholder="tr('servers.sshHostPlaceholder') || 'IP of the target server'"><template #help><D2HelpTip :text="ns.server_category === 'proxy' ? (tr('servers.sshHostProxyHelp') || 'IP of a SEPARATE server to install the proxy on. Blank installs on the panel host itself. Not recommended for a proxy: its port will clash with the panel.') : (tr('servers.sshHostHelp') || 'IP of the target server. Blank = install on the panel host.')" /></template></D2Field><div v-if="ns.server_category === 'proxy' && !ns.ssh_host" style="font-size:11px;color:var(--d2-warn,#d0a03a);margin:-2px 0 8px;line-height:1.4">{{ tr('servers.proxyNeedsHost') || '⚠ Installing a proxy on the panel host will clash with the panel (e.g. port 443). Enter a separate VPS above.' }}</div><div v-if="ns.ssh_host" class="d2-2col"><D2Field v-model="ns.ssh_user" :label="tr('servers.sshUser') || 'SSH user'" /><D2Field v-model="ns.ssh_port" type="number" :label="tr('servers.sshPort') || 'SSH port'" /></div><D2Field v-if="ns.ssh_host" v-model="ns.ssh_password" type="password" :label="tr('servers.sshPassword') || 'SSH password'" /></template>
        <!-- advanced -->
        <button @click="advOpen = !advOpen" style="display:flex;align-items:center;gap:7px;border:none;background:transparent;color:var(--text-2);font:inherit;font-size:12.5px;font-weight:550;cursor:pointer;padding:2px 0" class="hov-text"><span :style="{ display:'flex', transform: advOpen ? 'rotate(90deg)' : 'none', transition:'transform .15s' }"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"></path></svg></span>{{ tr('servers.advanced') || 'Advanced' }}</button>
        <template v-if="advOpen">
          <D2Toggle v-model="reuseKp">{{ tr('servers.reuseKeypair') || 'Reuse existing private key' }}</D2Toggle>
          <D2Field v-if="reuseKp" v-model="ns.private_key" class="mono" :label="tr('servers.privateKey') || 'Private key'" placeholder="base64 private key" />
          <D2Field v-model="ns.mtu" type="number" :label="'MTU'" placeholder="1420" />
        </template>
        <div v-if="installProgress" class="d2-progress">{{ installProgress }}</div>
        <div v-if="addError" style="color:var(--red);font-size:13px">{{ addError }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="showAdd = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="adding" @click="addServer">{{ tr('servers.create') || 'Create server' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="disc.show" :title="tr('servers.discover') || 'Discover'" @close="disc.show = false">
      <div style="display:flex;flex-direction:column;gap:14px">
        <D2Field v-model="disc.form.ssh_host" :label="tr('servers.sshHost') || 'SSH host'" />
        <div class="d2-2col"><D2Field v-model="disc.form.ssh_user" :label="tr('servers.sshUser') || 'SSH user'" /><D2Field v-model="disc.form.ssh_port" type="number" :label="tr('servers.sshPort') || 'SSH port'" /></div>
        <D2Field v-model="disc.form.ssh_password" type="password" :label="tr('servers.sshPassword') || 'SSH password'" />
        <div class="d2-2col"><D2Field v-model="disc.form.interface" :label="tr('servers.interface') || 'Interface'" /><D2Field v-model="disc.form.server_name" :label="tr('servers.name') || 'Name'" /></div>
        <div v-if="disc.result" class="d2-progress">{{ disc.result }}</div><div v-if="disc.error" style="color:var(--red);font-size:13px">{{ disc.error }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="disc.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="disc.busy" @click="doDiscover">{{ tr('servers.discoverRun') || 'Discover' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="showAgent" :title="tr('servers.installAgent') || 'Install agent'" size="sm" @close="agentBusy ? null : (showAgent = false)">
      <div style="display:flex;flex-direction:column;gap:12px">
        <p style="color:var(--text-3);display:inline-flex;align-items:center">{{ agentServer?.name }}<D2HelpTip :text="tr('help.agentMode') || 'Agent manages WG over SSH without storing creds.'" /></p>
        <!-- current agent state: version + reachability -->
        <div style="display:flex;align-items:center;gap:8px;font-size:12.5px">
          <span style="color:var(--text-3)">{{ tr('servers.agentCurrent') || 'Current agent' }}:</span>
          <span v-if="agentInfo.loading" style="color:var(--text-3)">{{ tr('common.loading') || 'Loading…' }}</span>
          <template v-else-if="agentInfo.version">
            <span class="mono" style="color:var(--text)">v{{ agentInfo.version }}</span>
            <span :style="{ color: agentInfo.healthy ? 'var(--green)' : 'var(--red)', fontWeight: 600 }">{{ agentInfo.healthy ? (tr('common.online') || 'online') : (tr('common.offline') || 'offline') }}</span>
          </template>
          <span v-else style="color:var(--text-3)">{{ tr('servers.agentNotInstalled') || 'not installed' }}</span>
        </div>
        <!-- port presets -->
        <div style="display:flex;gap:6px;flex-wrap:wrap"><button v-for="p in [8001,8080,9443,443]" :key="p" class="d2-pick sm mono" :class="{ on: agentPort === p }" @click="agentPort = p" :disabled="agentBusy">{{ p }}</button></div>
        <D2Field v-model="agentPort" type="number" :label="tr('servers.agentPort') || 'Agent port'" :disabled="agentBusy" />
        <!-- inline SSH password: revealed when the backend reports the server
             has no stored SSH credentials (code: ssh_credentials_missing) -->
        <template v-if="agentNeedCreds">
          <D2Field v-model="agentSshPw" type="password" :label="tr('servers.sshPassword') || 'SSH password'" :disabled="agentBusy" />
          <div style="font-size:12px;color:var(--text-3)">{{ tr('servers.sshPasswordHint') || 'The panel has no SSH access to this server. The password will be saved to the server record and used for the install.' }}</div>
        </template>
        <!-- live install log (bootstrap task stream) -->
        <div v-if="agentLog.length" ref="agentLogBox" class="mono" style="max-height:180px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:11.5px;line-height:1.65;color:var(--text-2);white-space:pre-wrap">{{ agentLog.join('\n') }}</div>
        <div v-if="agentMsg" :style="{ fontSize:'12.5px', fontWeight:600, color: agentErr ? 'var(--red)' : 'var(--green)' }">{{ agentMsg }}</div>
      </div>
      <template #footer>
        <D2Button v-if="agentServer?.agent_mode === 'agent'" variant="danger" :disabled="agentBusy" :loading="agentUninstalling" @click="doUninstallAgent" style="margin-right:auto">{{ tr('servers.uninstallAgent') || 'Uninstall agent' }}</D2Button>
        <D2Button variant="secondary" :disabled="agentBusy || agentUninstalling" @click="showAgent = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button :loading="agentBusy" :disabled="agentUninstalling" @click="doInstallAgent">{{ agentServer?.agent_mode === 'agent' ? (tr('servers.reinstall') || 'Reinstall') : (tr('servers.startInstall') || 'Start install') }}</D2Button>
      </template>
    </D2Modal>

    <!-- fleet-wide agent reinstall: one bootstrap task streams the whole rollout -->
    <D2Modal :open="ra.show" :title="tr('servers.reinstallAllAgents') || 'Reinstall agents'" size="sm" @close="ra.busy ? null : (ra.show = false)">
      <div style="display:flex;flex-direction:column;gap:12px">
        <p style="color:var(--text-3)">{{ tr('servers.reinstallAllHint') || 'Reinstalls the agent on every agent-mode server, one node at a time. Customer tunnels stay up; nodes without stored SSH credentials are skipped.' }}</p>
        <div v-if="ra.log.length" ref="raLogBox" class="mono" style="max-height:240px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:11.5px;line-height:1.65;color:var(--text-2);white-space:pre-wrap">{{ ra.log.join('\n') }}</div>
        <div v-if="ra.msg" :style="{ fontSize:'12.5px', fontWeight:600, color: ra.err ? 'var(--red)' : 'var(--green)' }">{{ ra.msg }}</div>
      </div>
      <template #footer>
        <D2Button variant="secondary" :loading="ra.busy" :disabled="ra.busy" @click="ra.show = false">{{ ra.busy ? (tr('servers.reinstallAllRunning') || 'Running…') : (tr('common.close') || 'Close') }}</D2Button>
      </template>
    </D2Modal>

    <D2Modal :open="showRename" :title="tr('servers.renameDisplay') || 'Rename (display)'" size="sm" @close="showRename = false">
      <D2Field v-model="renameVal" :label="tr('servers.displayName') || 'Display name'" :placeholder="renameInternal" />
      <template #footer><D2Button variant="secondary" @click="showRename = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="savingName" @click="saveRename">{{ tr('common.save') || 'Save' }}</D2Button></template>
    </D2Modal>

    <!-- keypair — reveal-gated, matches his EXPORT KEYPAIR modal -->
    <D2Modal :open="kp.show" :title="(tr('servers.exportKeypair') || 'Export keypair') + (kp.name ? ' · ' + kp.name : '')" size="sm" @close="kp.show = false">
      <div v-if="kp.loading" style="color:var(--text-3);text-align:center;padding:16px">{{ tr('common.loading') || 'Loading…' }}</div>
      <div v-else style="display:flex;flex-direction:column;gap:14px">
        <div style="display:flex;align-items:flex-start;gap:8px;padding:10px 13px;border:1px solid var(--red-soft);background:var(--red-soft);border-radius:10px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="1.8" style="margin-top:1px;flex:none"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 018 0v3"></path></svg><span style="font-size:12px;color:var(--text-2);line-height:1.45">{{ tr('servers.keypairWarn') || 'The private key is secret. Anyone with it can impersonate this server.' }}</span></div>
        <div class="d2-field"><label class="d2-flabel">{{ tr('servers.privateKey') || 'Private key' }}</label><input class="mono d2f-input" :value="kp.data.private_key" readonly @focus="$event.target.select()" /></div>
        <div class="d2-field"><label class="d2-flabel">{{ tr('servers.publicKey') || 'Public key' }}</label><input class="mono d2f-input" :value="kp.data.public_key" readonly @focus="$event.target.select()" /></div>
      </div>
      <template #footer><D2Button variant="secondary" @click="kp.show = false">{{ tr('common.close') || 'Close' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="ep.show" :title="tr('servers.expandPool') || 'Expand pool'" size="sm" @close="ep.show = false">
      <div style="display:flex;flex-direction:column;gap:12px">
        <div v-if="ep.current" style="padding:11px 13px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('servers.currentPool') || 'Current pool' }}</div><div class="mono" style="font-size:13px;color:var(--text-2);margin-top:3px">{{ ep.current }}</div></div>
        <D2Field v-model="ep.cidr" :label="tr('servers.newCidr') || 'New CIDR' " placeholder="10.8.0.0/15" />
        <div style="display:flex;gap:6px"><button v-for="p in ['10.8.0.0/15','10.16.0.0/14','10.0.0.0/12']" :key="p" class="d2-pick sm mono" @click="ep.cidr = p">{{ p }}</button></div>
        <div style="font-size:11.5px;color:var(--text-3)">{{ tr('servers.poolKeep') || 'Existing client IPs are preserved.' }}</div>
        <div v-if="ep.result" class="d2-progress">{{ ep.result }}</div><div v-if="ep.error" style="color:var(--red);font-size:13px">{{ ep.error }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="ep.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="ep.busy" :disabled="!ep.cidr.trim()" @click="doExpandPool">{{ tr('servers.apply') || 'Apply' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="mig.show" :title="tr('servers.migrateClients') || 'Migrate clients'" size="sm" @close="mig.show = false">
      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="d2-2col"><div class="d2-field"><label class="d2-flabel">{{ tr('servers.migrateFrom') || 'From' }}</label><div style="height:40px;border:1px solid var(--border);background:var(--panel-2);border-radius:10px;padding:0 12px;display:flex;align-items:center;font-size:13px;color:var(--text-2)">{{ mig.source?.name }}</div></div><D2Select v-model="mig.targetId" numeric :label="tr('servers.migrateTo') || 'Target server'" :options="migrateTargets" /></div>
        <D2Toggle v-model="mig.pushConfigs">{{ tr('servers.migratePush') || 'Push updated configs to devices' }}</D2Toggle>
        <D2Toggle v-model="mig.removeSource">{{ tr('servers.migrateRemove') || 'Remove peers from source' }}</D2Toggle>
        <div v-if="mig.result" class="d2-progress">{{ mig.result.message || 'Migrated' }}</div><div v-if="mig.error" style="color:var(--red);font-size:13px">{{ mig.error }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="mig.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="mig.busy" :disabled="!mig.targetId" @click="doMigrate">{{ tr('servers.migrate') || 'Migrate' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="bw.show" :title="tr('servers.bandwidthLimit') || 'Bandwidth limit'" size="sm" @close="bw.show = false">
      <D2Field v-model="bw.limit" type="number" :label="tr('servers.maxBandwidthMbps') || 'Max bandwidth (Mbps)'" :hint="tr('servers.bandwidthHint') || '0 or empty = unlimited.'" />
      <template #footer><D2Button variant="secondary" @click="bw.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="bw.busy" @click="saveBw">{{ tr('common.save') || 'Save' }}</D2Button></template>
    </D2Modal>

    <!-- OBFS (AmneziaWG H1–H4 / JC / JMin / JMax / S1 / S2) -->
    <D2Modal :open="obfs.show" :title="tr('servers.obfsSettings') || 'Obfuscation'" size="md" @close="obfs.show = false">
      <div style="display:flex;flex-direction:column;gap:12px">
        <div style="font-size:12px;color:var(--text-2)">{{ obfs.name }} · AmneziaWG H1–H4 / JC / JMin / JMax / S1 / S2</div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
          <div v-for="k in awgKeys" :key="k" class="d2-field"><label style="font-size:11px;font-weight:600;color:var(--text-3)">{{ k.replace('awg_','').toUpperCase() }}</label><input class="d2f-input mono" v-model.number="obfs.form[k]" inputmode="numeric" /></div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;padding:9px 12px;border:1px solid var(--amber-soft);background:var(--amber-soft);border-radius:9px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8"><path d="M12 9v4M12 17h.01M10.3 3.9l-8 14A2 2 0 004 21h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z"></path></svg><span style="font-size:12px;color:var(--text-2)">{{ tr('servers.obfsWarn') || 'Values must match on every client, or the tunnel will not come up.' }}</span></div>
        <div v-if="obfs.error" style="color:var(--red);font-size:13px">{{ obfs.error }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="obfs.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="obfs.busy" @click="saveObfs">{{ tr('servers.apply') || 'Apply' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="ip.show" :title="tr('servers.installProxy') || 'Install proxy'" size="sm" @close="ip.busy ? null : (ip.show = false)">
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="d2-field"><label class="d2-flabel">{{ tr('servers.protocol') || 'Protocol' }}</label><div style="display:flex;gap:8px;flex-wrap:wrap"><button v-for="p in [['vless-reality','VLESS-Reality'],['hysteria2','Hysteria2'],['tuic','TUIC']]" :key="p[0]" class="d2-pick sm" :class="{ on: ip.form.protocol === p[0] }" @click="ip.form.protocol = p[0]">{{ p[1] }}</button></div></div>
        <D2Field v-model="ip.form.name" :label="tr('servers.name') || 'Name (optional)'" :placeholder="ip.server ? (ip.server.name + ' — ' + ip.form.protocol.toUpperCase()) : ''" />
        <D2Field v-model="ip.form.port" type="number" :label="tr('servers.listenPort') || 'Port'" :placeholder="ip.form.protocol === 'vless-reality' ? '443' : (ip.form.protocol === 'hysteria2' ? '8443' : '8444')"><template #help><D2HelpTip :text="tr('servers.proxyPortHint') || 'Must be FREE on the target server (many boxes already run nginx on 443).'" /></template></D2Field>
        <D2Field v-if="ip.form.protocol === 'vless-reality'" v-model="ip.form.domain" :label="tr('servers.proxyDomainVless') || 'Camouflage domain (SNI)'" placeholder="www.microsoft.com"><template #help><D2HelpTip :text="tr('servers.proxyDomainVlessHint') || 'Real TLS site to impersonate. Default www.microsoft.com.'" /></template></D2Field>
        <template v-else>
          <div class="d2-field"><label class="d2-flabel">{{ tr('servers.tlsMode') || 'TLS mode' }}</label><div style="display:flex;gap:8px"><button v-for="m in ['self_signed','acme','manual']" :key="m" class="d2-pick sm" :class="{ on: ip.form.tls_mode === m }" @click="ip.form.tls_mode = m">{{ m === 'self_signed' ? 'Self-signed' : m.toUpperCase() }}</button></div></div>
          <D2Field v-if="ip.form.protocol === 'hysteria2'" v-model="ip.form.obfs_password" :label="tr('servers.obfs') || 'OBFS password (optional)'" />
        </template>
        <div v-if="ip.log.length" ref="ipLogBox" class="mono" style="max-height:200px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:11.5px;line-height:1.65;color:var(--text-2);white-space:pre-wrap">{{ ip.log.join('\n') }}</div>
        <div v-if="ip.msg" class="d2-progress">{{ ip.msg }}</div><div v-if="ip.error" style="color:var(--red);font-size:13px">{{ ip.error }}</div>
      </div>
      <template #footer><D2Button variant="secondary" :disabled="ip.busy" @click="ip.show = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="ip.busy" @click="doInstallProxy">{{ tr('servers.install') || 'Install' }}</D2Button></template>
    </D2Modal>

    <!-- SERVER CLIENTS -->
    <D2Modal :open="svc.show" :title="svc.title" size="lg" @close="svc.show = false">
      <div v-if="svc.loading" style="color:var(--text-3);text-align:center;padding:24px">{{ tr('common.loading') || 'Loading…' }}</div>
      <div v-else-if="svc.error" style="padding:24px;text-align:center;font-size:13px;color:var(--red)">{{ svc.error }}</div>
      <div v-else-if="!svc.rows.length" style="padding:24px;text-align:center;font-size:13px;color:var(--text-3)">{{ tr('servers.noClients') || 'No clients on this server' }}</div>
      <div v-else style="display:flex;flex-direction:column;gap:1px">
        <div v-for="r in svc.rows" :key="r.id" style="display:flex;align-items:center;gap:10px;padding:10px 4px;border-bottom:1px solid var(--border)"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:r.dot, flex:'none' }"></span><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:550">{{ r.name }}</div><div class="mono" style="font-size:11.5px;color:var(--text-3)">{{ r.ip }}</div></div><div class="mono" style="font-size:12px;color:var(--text-2)">{{ r.traffic }}</div></div>
      </div>
      <template #footer><D2Button variant="secondary" @click="svc.show = false">{{ tr('common.close') || 'Close' }}</D2Button></template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { useServersStore } from '../../stores/servers'
import { serversApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'
import Icon from '../ui/Icon.vue'
import D2Modal from '../ui/D2Modal.vue'
import D2Field from '../ui/D2Field.vue'
import D2Select from '../ui/D2Select.vue'
import D2Toggle from '../ui/D2Toggle.vue'
import D2Button from '../ui/D2Button.vue'
import D2HelpTip from '../ui/D2HelpTip.vue'

const { t } = useI18n()
function tr(k, p) { try { const v = t(k, p || {}); return v === k ? '' : v } catch (_) { return '' } }
const store = useServersStore()
const ui = useD2Ui()
const menuFor = ref(null)
const detailsFor = ref(null)
const topFor = ref(null)
const topConsumers = ref([])
const awgKeys = ['awg_jc', 'awg_jmin', 'awg_jmax', 'awg_s1', 'awg_s2', 'awg_h1', 'awg_h2', 'awg_h3', 'awg_h4']

const TYPE = {
  amneziawg: { label: 'AmneziaWG', icon: 'lock', color: 'var(--purple)', bg: 'var(--purple-soft)' },
  hysteria2: { label: 'Hysteria2', icon: 'shuffle', color: 'var(--amber)', bg: 'var(--amber-soft)' },
  tuic: { label: 'TUIC', icon: 'shuffle', color: 'var(--amber)', bg: 'var(--amber-soft)' },
  'vless-reality': { label: 'VLESS-Reality', icon: 'shuffle', color: 'var(--amber)', bg: 'var(--amber-soft)' },
  wireguard: { label: 'WireGuard', icon: 'globe', color: 'var(--blue)', bg: 'var(--blue-soft)' },
}
const isOnline = (s) => (s.status === 'ONLINE' || s.status === 'online' || s.is_online === true || s.online === true)

const cards = computed(() => store.servers.map(s => {
  const on = isOnline(s); const ty = TYPE[s.server_type] || TYPE.wireguard
  const clients = s.total_clients ?? 0, max = s.max_clients || 0; const pct = max ? Math.min(100, (clients / max) * 100) : 0
  const isProxy = s.server_category === 'proxy'
  // agent badge: only for agent-capable (non-mikrotik VPN/proxy over SSH)
  const showAgentBadge = s.agent_mode !== 'mikrotik'
  const breakerOpen = !!(s.agent_breaker && s.agent_breaker.open)
  const isAgent = s.agent_mode === 'agent'
  let agentColor, agentBg, agentIcon, agentLabel
  if (!isAgent) { agentColor = 'var(--text-3)'; agentBg = 'var(--panel-2)'; agentIcon = 'terminal'; agentLabel = tr('servers.sshMode') || 'SSH mode' }
  else if (breakerOpen) { agentColor = 'var(--red)'; agentBg = 'var(--red-soft)'; agentIcon = 'plug'; agentLabel = tr('servers.agentUnreachable') || 'Agent unreachable' }
  else { agentColor = 'var(--green)'; agentBg = 'var(--green-soft)'; agentIcon = 'bot'; agentLabel = tr('servers.agentConnected') || 'Agent connected' }
  const detailRows = [
    { k: tr('servers.interface') || 'Interface', v: isProxy ? '—' : (s.interface || '—') },
    { k: tr('servers.listenPort') || 'Port', v: s.listen_port || '—' },
    { k: tr('servers.addressPool') || 'Pool', v: s.address_pool_ipv4 || s.address_pool || '—', copy: s.address_pool_ipv4 || s.address_pool || '' },
    { k: tr('servers.publicKey') || 'Public key', v: s.public_key || '—', copy: s.public_key || '' },
  ]
  return {
    id: s.id, _raw: s, name: s.display_name || s.name,
    subIcon: s.location ? 'globe' : 'server', subtitle: s.location || s.endpoint || '—',
    statusColor: on ? 'var(--green)' : 'var(--text-3)', statusBg: on ? 'var(--green-soft)' : 'var(--panel-2)', statusLabel: on ? (tr('common.online') || 'Online') : (tr('common.offline') || 'Offline'),
    typeLabel: ty.label, typeIcon: ty.icon, typeColor: ty.color, typeBg: ty.bg,
    isDefault: !!s.is_default, pinned: !!s.force_visible, appOnly: !!s.for_app_only, hidden: !!s.hidden, version: s.agent_version,
    showAgentBadge, agentColor, agentBg, agentIcon, agentLabel,
    endpoint: s.endpoint || '—', clients, maxClients: max || '∞', location: s.location || '—', bandwidth: s.max_bandwidth_mbps || '∞',
    pct: pct + '%', pctLabel: Math.round(pct) + '%', barColor: pct > 90 ? 'var(--red)' : pct > 70 ? 'var(--amber)' : 'var(--accent)',
    detailRows,
  }
}))

// Full ⋮ menu — his SERVERS.md spec (status control, save/backup/restore,
// default, agent, proxy/bandwidth, rename, visibility toggles, pool/keypair/
// obfs/migrate, purge, delete). Dividers as {divider:true}.
function menuItems(s) {
  const proxy = s.server_category === 'proxy'
  const online = isOnline(s)
  const vis = s.customer_visible !== false, visM = s.customer_visible_mobile !== false, visW = s.customer_visible_windows !== false
  const items = []
  if (online) {
    items.push({ icon: 'refresh', label: tr('servers.restart') || 'Restart', onClick: () => restartServer(s) })
    items.push({ icon: 'square', label: tr('servers.stop') || 'Stop', onClick: () => stopServer(s) })
  } else {
    items.push({ icon: 'play', label: tr('servers.start') || 'Start', onClick: () => startServer(s) })
  }
  if (!proxy) items.push({ icon: 'save', label: tr('servers.saveConfig') || 'Save config', onClick: () => saveServerConfig(s) })
  items.push({ icon: 'download', label: tr('servers.backup') || 'Backup', onClick: () => backupServer(s) })
  items.push({ icon: 'upload', label: tr('servers.restore') || 'Restore', onClick: () => restoreServer(s) })
  if (!s.is_default) items.push({ icon: 'star', label: tr('servers.setDefault') || 'Set as default', onClick: () => setDefault(s) })
  if (!proxy && s.agent_mode !== 'mikrotik') items.push({ icon: 'bot', label: s.agent_mode === 'agent' ? (tr('servers.manageAgent') || 'Manage agent') : (tr('servers.installAgent') || 'Install agent'), onClick: () => openAgent(s) })
  if (!proxy) items.push({ icon: 'server', label: tr('servers.installProxy') || 'Install proxy', onClick: () => openInstallProxy(s) })
  items.push({ icon: 'gauge', label: tr('servers.bandwidthLimit') || 'Bandwidth limit', onClick: () => openBw(s) })
  items.push({ divider: true })
  items.push({ icon: 'pencil', label: tr('servers.renameDisplay') || 'Rename', onClick: () => openRename(s) })
  if (!proxy) items.push({ icon: 'layers', label: (tr('servers.splitTunnel') || 'Split tunnel') + (s.split_tunnel_support ? ' · ON' : ' · OFF'), onClick: () => toggleSplit(s) })
  items.push({ icon: vis ? 'eye' : 'eyeoff', label: vis ? (tr('servers.hidePortal') || 'Hide in portal') : (tr('servers.showPortal') || 'Show in portal'), onClick: () => togglePortal(s) })
  items.push({ icon: 'phone', label: s.for_app_only ? (tr('servers.appOnlyOff') || 'App-only: off') : (tr('servers.appOnly') || 'App-only'), onClick: () => toggleAppOnly(s) })
  items.push({ icon: 'phone', label: visM ? (tr('servers.hideMobile') || 'Hide on mobile') : (tr('servers.showMobile') || 'Show on mobile'), onClick: () => toggleMobile(s) })
  items.push({ icon: 'monitor', label: visW ? (tr('servers.hideWindows') || 'Hide on Windows') : (tr('servers.showWindows') || 'Show on Windows'), onClick: () => toggleWindows(s) })
  items.push({ icon: 'pin', label: s.force_visible ? (tr('servers.disableForceVisible') || 'Unpin') : (tr('servers.enableForceVisible') || 'Pin visible'), onClick: () => toggleForceVisible(s) })
  items.push({ divider: true })
  if (!proxy && s.agent_mode !== 'mikrotik') items.push({ icon: 'layers', label: tr('servers.expandPool') || 'Expand pool', onClick: () => openExpandPool(s) })
  if (!proxy && s.server_type !== 'amneziawg') items.push({ icon: 'key', label: tr('servers.exportKeypair') || 'Export keypair', onClick: () => openKeypair(s) })
  if (s.server_type === 'amneziawg') items.push({ icon: 'shuffle', label: tr('servers.obfsSettings') || 'Obfuscation', onClick: () => openObfs(s) })
  if (!proxy) items.push({ icon: 'migrate', label: tr('servers.migrateClients') || 'Migrate clients', onClick: () => openMigrate(s) })
  items.push({ divider: true })
  items.push({ icon: 'box', label: tr('servers.purge') || 'Purge (DB-only)', onClick: () => purgeServer(s) })
  items.push({ icon: 'trash', label: proxy ? (tr('servers.uninstallProxy') || 'Uninstall proxy') : (tr('common.delete') || 'Delete'), danger: true, onClick: () => removeServer(s) })
  return items
}
function run(fn) { menuFor.value = null; fn() }

// details disclosure — lazily pulls per-server stats/top-consumers
async function toggleDetails(card) {
  if (detailsFor.value === card.id) { detailsFor.value = null; topFor.value = null; topConsumers.value = []; return }
  detailsFor.value = card.id; topFor.value = null; topConsumers.value = []
  try {
    const { data } = await serversApi.getClients(card._raw.id)
    const rows = serverClientsFromResponse(data)
    const list = (Array.isArray(rows) ? rows : []).map(c => ({ name: c.name || c.display_name || ('client ' + c.id), bytes: (c.total_bytes ?? ((c.traffic_used_rx || c.rx_bytes || 0) + (c.traffic_used_tx || c.tx_bytes || 0))) }))
    list.sort((a, b) => b.bytes - a.bytes)
    const top = list.slice(0, 3); const maxB = top[0]?.bytes || 1
    topConsumers.value = top.filter(x => x.bytes > 0).map(x => ({ name: x.name, pct: Math.max(4, Math.round((x.bytes / maxB) * 100)) + '%', label: fmtBytes(x.bytes) }))
    if (topConsumers.value.length) topFor.value = card.id
  } catch (_) { /* stats endpoint may be unavailable for this server — details still show static rows */ }
}
function fmtBytes(b) { if (b > 1e9) return (b / 1e9).toFixed(1) + 'G'; if (b > 1e6) return (b / 1e6).toFixed(0) + 'M'; if (b > 1e3) return (b / 1e3).toFixed(0) + 'K'; return b + 'B' }
function serverClientsFromResponse(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.clients)) return data.clients
  if (Array.isArray(data?.items)) return data.items
  return []
}
async function copyText(value) { try { await navigator.clipboard.writeText(String(value || '')) } catch (_) {} }

// add
const showAdd = ref(false), adding = ref(false), addError = ref(''), installProgress = ref(''), detectingIp = ref(false), advOpen = ref(false), reuseKp = ref(false)
function blank() { return { name: '', endpoint: '', interface: 'wg1', listen_port: 51821, address_pool_ipv4: '10.0.1.0/24', dns: '1.1.1.1,8.8.8.8', max_clients: 250, mtu: null, ssh_host: '', ssh_port: 22, ssh_user: 'root', ssh_password: '', server_type: 'wireguard', server_category: 'vpn', split_tunnel_support: false, ipv4_only: false, agent_mode: 'ssh', mikrotik_url: '', mikrotik_username: 'admin', mikrotik_password: '', proxy_domain: '', proxy_tls_mode: 'self_signed', proxy_obfs_password: '', private_key: '', awg_jc: null, awg_jmin: null, awg_jmax: null, awg_s1: null, awg_s2: null, awg_h1: null, awg_h2: null, awg_h3: null, awg_h4: null } }
const ns = ref(blank())
function openAdd() { addError.value = ''; installProgress.value = ''; advOpen.value = false; reuseKp.value = false; ns.value = blank(); showAdd.value = true }
// His card-selector style (category/protocol) — 2px accent border when active.
function cardStyle(active, proto = false) {
  return { textAlign: 'left', width: '100%', padding: proto ? '11px 14px' : '13px 15px', border: '2px solid ' + (active ? 'var(--accent)' : 'var(--border)'), background: active ? 'var(--accent-soft)' : 'var(--panel)', color: 'var(--text)', borderRadius: '11px', cursor: 'pointer', font: 'inherit' }
}
function setCategory(cat) { ns.value.server_category = cat; ns.value.server_type = cat === 'proxy' ? 'hysteria2' : 'wireguard'; onProto() }
function onProto() { const ty = ns.value.server_type, WG = '10.0.1.0/24', AWG = '10.66.66.0/24'; if (ty === 'amneziawg') { if (!ns.value.interface.startsWith('awg')) ns.value.interface = 'awg' + (ns.value.interface.replace(/\D/g, '') || '0'); if ([51820, 51821].includes(ns.value.listen_port)) ns.value.listen_port = 51820; if ([WG, AWG].includes(ns.value.address_pool_ipv4)) ns.value.address_pool_ipv4 = AWG } else if (ty === 'wireguard') { if (!ns.value.interface.startsWith('wg')) ns.value.interface = 'wg' + (ns.value.interface.replace(/\D/g, '') || '1'); if (ns.value.listen_port === 51820) ns.value.listen_port = 51821; if ([WG, AWG].includes(ns.value.address_pool_ipv4)) ns.value.address_pool_ipv4 = WG } else if (ty === 'hysteria2') ns.value.listen_port = 8443; else if (ty === 'tuic') ns.value.listen_port = 8444; else if (ty === 'vless-reality') { ns.value.listen_port = 443; ns.value.proxy_tls_mode = 'self_signed' } }
async function autodetectIp() {
  detectingIp.value = true
  try {
    // No dedicated backend probe — resolve the panel's own public IP client-side.
    const r = await fetch('https://api.ipify.org?format=json'); const j = await r.json(); if (j.ip) ns.value.endpoint = j.ip
  } catch (_) { /* offline / blocked — operator can type it manually */ } finally { detectingIp.value = false }
}
async function addServer() {
  addError.value = ''; adding.value = true; installProgress.value = ''
  const p = { ...ns.value }; const isMik = p.agent_mode === 'mikrotik'; const isProxy = p.server_category === 'proxy'; const isRemote = isMik || !!p.ssh_host
  if (isMik) { delete p.public_key; delete p.private_key; delete p.listen_port }
  if (isProxy) delete p.interface
  if (isProxy && p.server_type !== 'vless-reality' && p.proxy_tls_mode === 'acme' && !p.proxy_domain?.trim()) { addError.value = tr('servers.acmeDomainRequired') || 'ACME requires a domain'; adding.value = false; return }
  if (!p.name?.trim()) p.name = 'Server ' + (p.ssh_host || p.endpoint?.split(':')[0] || p.interface || new Date().toISOString().slice(0, 10))
  if (!p.proxy_domain) delete p.proxy_domain; if (!p.proxy_obfs_password) delete p.proxy_obfs_password
  if (p.mtu === null || p.mtu === '') delete p.mtu
  if (!reuseKp.value || !p.private_key?.trim()) delete p.private_key
  for (const k of awgKeys) { const v = p[k]; if (v === null || v === '' || (typeof v === 'number' && !Number.isFinite(v))) delete p[k] }
  if (!p.ssh_host) { delete p.ssh_host; delete p.ssh_port; delete p.ssh_user; delete p.ssh_password }
  if (isMik) { delete p.ssh_host; delete p.ssh_port; delete p.ssh_user; delete p.ssh_password } else { delete p.mikrotik_url; delete p.mikrotik_username; delete p.mikrotik_password }
  try { if (isMik) installProgress.value = 'Probing RouterOS…'; else if (isRemote) installProgress.value = 'Connecting via SSH…'; await store.createServer(p); showAdd.value = false } catch (e) { addError.value = e.response?.data?.detail || e.message } finally { adding.value = false; installProgress.value = '' }
}

// rename / default / visibility / delete / reconcile
const showRename = ref(false), renameId = ref(null), renameVal = ref(''), renameInternal = ref(''), savingName = ref(false)
function openRename(s) { renameId.value = s.id; renameInternal.value = s.name; renameVal.value = s.display_name || ''; showRename.value = true }
async function saveRename() { if (!renameId.value) return; savingName.value = true; try { await serversApi.update(renameId.value, { display_name: renameVal.value.trim() || null }); await store.fetchServers(); showRename.value = false } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { savingName.value = false } }
async function setDefault(s) { if (s.is_default) return; try { await serversApi.setDefault(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function toggleForceVisible(s) { try { await serversApi.update(s.id, { force_visible: !s.force_visible }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function toggleAppOnly(s) { try { await serversApi.update(s.id, { for_app_only: !s.for_app_only }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function removeServer(s) { if (!await d2confirm(tr('servers.deleteConfirm', { name: s.name }) || `Delete "${s.name}"?`)) return; try { await store.deleteServer(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function reconcile(s) { try { await serversApi.reconcile(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
// ── Direct server actions (his ⋮ menu) ──
async function startServer(s) { try { await serversApi.start(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function stopServer(s) { try { await serversApi.stop(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function restartServer(s) { try { await serversApi.restart(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function saveServerConfig(s) { try { await serversApi.saveConfig(s.id) } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function backupServer(s) {
  try {
    const { data } = await serversApi.backup(s.id)
    const url = URL.createObjectURL(new Blob([data]))
    const a = document.createElement('a'); a.href = url; a.download = (s.display_name || s.name || 'server') + '-backup.tar.gz'; a.click(); URL.revokeObjectURL(url)
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
}
function restoreServer(s) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.tar.gz,.tgz,application/gzip'
  inp.onchange = async () => { const f = inp.files && inp.files[0]; if (!f) return; try { await serversApi.restore(s.id, f); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
  inp.click()
}
async function purgeServer(s) { if (!await d2confirm(tr('servers.purgeConfirm', { name: s.name }) || `Purge "${s.name}" (DB-only, no remote cleanup)?`)) return; try { await serversApi.purge(s.id); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function toggleSplit(s) { try { await serversApi.update(s.id, { split_tunnel_support: !s.split_tunnel_support }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function togglePortal(s) { try { await serversApi.update(s.id, { customer_visible: s.customer_visible === false }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function toggleMobile(s) { try { await serversApi.update(s.id, { customer_visible_mobile: s.customer_visible_mobile === false }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function toggleWindows(s) { try { await serversApi.update(s.id, { customer_visible_windows: s.customer_visible_windows === false }); await store.fetchServers() } catch (e) { alert(e.response?.data?.detail || 'Error') } }

// agent
const showAgent = ref(false), agentServer = ref(null), agentPort = ref(8001), agentBusy = ref(false), agentMsg = ref('')
const agentErr = ref(false), agentLog = ref([]), agentLogBox = ref(null)
const agentInfo = ref({ loading: false, version: null, healthy: false })
const agentNeedCreds = ref(false), agentSshPw = ref(''), agentUninstalling = ref(false)

function openAgent(s) {
  agentServer.value = s
  const m = String(s.agent_url || '').match(/:(\d+)\/?$/)
  agentPort.value = m ? Number(m[1]) : 8001
  agentMsg.value = ''; agentErr.value = false; agentLog.value = []
  agentNeedCreds.value = false; agentSshPw.value = ''; agentUninstalling.value = false
  showAgent.value = true
  // Current agent version + reachability (best-effort, doesn't block the modal)
  agentInfo.value = { loading: true, version: null, healthy: false }
  serversApi.checkAgentStatus(s.id)
    .then(({ data }) => { agentInfo.value = { loading: false, version: data.agent_version || null, healthy: !!data.agent_healthy } })
    .catch(() => { agentInfo.value = { loading: false, version: null, healthy: false } })
}

// Strip the emoji markers the backend log lines carry (legacy UI keeps them;
// the redesign is deliberately icon-free here).
function _plain(line) { return String(line).replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '').trim() }

async function doInstallAgent() {
  if (!agentServer.value || agentBusy.value) return
  agentBusy.value = true; agentErr.value = false; agentLog.value = []
  agentMsg.value = ''
  const taskId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2))
  const serverId = agentServer.value.id

  // Inline SSH password (revealed when the backend said creds are missing):
  // persist it to the server record first, then proceed with the install.
  if (agentNeedCreds.value && agentSshPw.value.trim()) {
    try {
      await serversApi.update(serverId, { ssh_password: agentSshPw.value.trim() })
      agentNeedCreds.value = false
    } catch (e) {
      agentErr.value = true
      agentMsg.value = (tr('common.error') || 'Error') + ': ' + (e.response?.data?.detail || e.message)
      agentBusy.value = false
      return
    }
  }

  // The task poll is the source of truth, NOT the long HTTP call: proxies drop
  // the request after 30-60s while the SSH bootstrap keeps running server-side.
  // Trusting only the HTTP response produced the "says failed, but 5 minutes
  // later it's installed" confusion. We poll until the task reports a terminal
  // state (complete/error), whatever happens to the HTTP call.
  let sinceIdx = 0
  let terminal = null // { error: string|null }
  const poll = async () => {
    try {
      const { data } = await serversApi.getBootstrapLogs(taskId, sinceIdx)
      if (data.logs && data.logs.length) {
        agentLog.value.push(...data.logs.map(_plain).filter(Boolean))
        sinceIdx = data.next_index
        await nextTick()
        if (agentLogBox.value) agentLogBox.value.scrollTop = agentLogBox.value.scrollHeight
      }
      if (data.complete) terminal = { error: data.error || null }
    } catch (_) { /* transient poll failure — keep going */ }
  }

  let settled = null
  const httpCall = serversApi.installAgent(serverId, agentPort.value, { taskId, force: agentServer.value.agent_mode === 'agent' })
    .catch((e) => ({ _httpError: e })) // never reject — the task poll decides
  httpCall.then((r) => { settled = r })

  const deadline = Date.now() + 5 * 60 * 1000
  while (!terminal && Date.now() < deadline) {
    // Fast-fail: a 4xx from the route's PRE-checks (no creds, bad state)
    // arrives before any task is created — don't sit polling a task that
    // will never exist.
    if (settled && settled._httpError && agentLog.value.length === 0) {
      const resp = settled._httpError.response
      if (resp && resp.status >= 400 && resp.status < 500) {
        if (resp.data?.code === 'ssh_credentials_missing') agentNeedCreds.value = true
        terminal = { error: resp.data?.detail || settled._httpError.message }
        break
      }
    }
    await poll()
    if (!terminal) await new Promise(r => setTimeout(r, 1000))
  }
  const httpRes = await Promise.race([httpCall, Promise.resolve(null)])

  await store.fetchServers().catch(() => {})
  // Re-read the agent's live version — the definitive "did it install" check.
  let ver = null, healthy = false
  try { const { data } = await serversApi.checkAgentStatus(serverId); ver = data.agent_version || null; healthy = !!data.agent_healthy } catch (_) {}
  agentInfo.value = { loading: false, version: ver, healthy }

  if (terminal && !terminal.error) {
    agentMsg.value = (tr('servers.agentInstalled') || 'Installed') + (ver ? `, v${ver}` : '')
  } else if (terminal && terminal.error) {
    agentErr.value = true
    agentMsg.value = (tr('common.error') || 'Error') + ': ' + terminal.error
  } else if (healthy) {
    // No terminal state (task expired / never created) but the agent answers —
    // trust reality over plumbing.
    agentMsg.value = (tr('servers.agentInstalled') || 'Installed') + (ver ? `, v${ver}` : '')
  } else {
    agentErr.value = true
    const httpDetail = httpRes && httpRes._httpError ? (httpRes._httpError.response?.data?.detail || httpRes._httpError.message) : (tr('servers.agentTimeout') || 'No confirmation — check the server list in a minute')
    agentMsg.value = (tr('common.error') || 'Error') + ': ' + httpDetail
  }
  agentBusy.value = false
}

async function doUninstallAgent() {
  if (!agentServer.value || agentUninstalling.value || agentBusy.value) return
  const name = agentServer.value.display_name || agentServer.value.name
  if (!await d2confirm((tr('servers.uninstallAgentConfirm', { name }) || `Remove the agent from "${name}"? The VPN interface and customer tunnels stay up; the panel falls back to SSH mode.`))) return
  agentUninstalling.value = true; agentErr.value = false; agentMsg.value = ''
  try {
    await serversApi.uninstallAgent(agentServer.value.id)
    await store.fetchServers().catch(() => {})
    agentInfo.value = { loading: false, version: null, healthy: false }
    // keep the modal open so the operator can reinstall right away
    agentServer.value = { ...agentServer.value, agent_mode: 'ssh', agent_url: null }
    agentMsg.value = tr('servers.agentUninstalled') || 'Agent removed — server switched to SSH mode'
  } catch (e) {
    agentErr.value = true
    agentMsg.value = (tr('common.error') || 'Error') + ': ' + (e.response?.data?.detail || e.message)
  } finally {
    agentUninstalling.value = false
  }
}

// fleet-wide agent reinstall (toolbar button). One bootstrap-log task streams
// the whole rollout; the backend runs it in the background and processes nodes
// sequentially, so the poll (not the short HTTP call) is the source of truth —
// same rule as the single-install modal above.
const ra = reactive({ show: false, busy: false, done: false, err: false, msg: '', log: [] })
const raLogBox = ref(null)
const agentFleetCount = computed(() => store.servers.filter(s => s.agent_mode === 'agent' && s.ssh_host).length)

async function openReinstallAll() {
  const n = agentFleetCount.value
  if (!n) return
  if (!await d2confirm(tr('servers.reinstallAllConfirm', { n }) || `Reinstall the agent on all ${n} agent-mode servers, one at a time? Customer tunnels stay up; each agent restarts briefly.`)) return
  ra.busy = false; ra.done = false; ra.err = false; ra.msg = ''; ra.log = []
  ra.show = true
  startReinstallAll()
}

async function startReinstallAll() {
  if (ra.busy || ra.done) return
  ra.busy = true; ra.err = false; ra.msg = ''; ra.log = []
  const taskId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2))

  let total = agentFleetCount.value
  try {
    const { data } = await serversApi.reinstallAllAgents(taskId)
    total = data.total || total
  } catch (e) {
    ra.err = true
    ra.msg = (tr('common.error') || 'Error') + ': ' + (e.response?.data?.detail || e.message)
    ra.busy = false
    return
  }

  // Stream the rollout log until the task reports terminal state. Budget:
  // generous per-node allowance — the backend keeps going regardless; if we
  // stop watching, the log line tells the operator it continues server-side.
  let sinceIdx = 0
  let terminal = null
  const deadline = Date.now() + Math.max(10, total * 4) * 60 * 1000
  while (!terminal && Date.now() < deadline && ra.show) {
    try {
      const { data } = await serversApi.getBootstrapLogs(taskId, sinceIdx)
      if (data.logs && data.logs.length) {
        ra.log.push(...data.logs.map(_plain).filter(Boolean))
        sinceIdx = data.next_index
        await nextTick()
        if (raLogBox.value) raLogBox.value.scrollTop = raLogBox.value.scrollHeight
      }
      if (data.complete) terminal = { error: data.error || null }
    } catch (_) { /* transient poll failure — keep going */ }
    if (!terminal) await new Promise(r => setTimeout(r, 1000))
  }

  await store.fetchServers().catch(() => {})
  if (terminal && !terminal.error) {
    ra.msg = tr('servers.reinstallAllDone') || 'All agents reinstalled'
  } else if (terminal) {
    ra.err = true
    ra.msg = terminal.error
  } else {
    ra.err = true
    ra.msg = tr('servers.reinstallAllTimeout') || 'Still running server-side — check the agent badges in a few minutes'
  }
  ra.busy = false; ra.done = true
}

// discover
const disc = reactive({ show: false, busy: false, result: '', error: '', form: { ssh_host: '', ssh_port: 22, ssh_user: 'root', ssh_password: '', interface: 'wg0', server_name: '' } })
function openDiscover() { disc.result = ''; disc.error = ''; disc.form = { ssh_host: '', ssh_port: 22, ssh_user: 'root', ssh_password: '', interface: 'wg0', server_name: '' }; disc.show = true }
async function doDiscover() { disc.busy = true; disc.error = ''; disc.result = ''; try { const { data } = await serversApi.discover(disc.form); disc.result = `${data.message || 'Imported'} · ${data.clients_imported ?? 0}`; await store.fetchServers() } catch (e) { disc.error = e.response?.data?.detail || e.message } finally { disc.busy = false } }

// keypair
const kp = reactive({ show: false, loading: false, name: '', data: {} })
async function openKeypair(s) { kp.data = {}; kp.name = s.display_name || s.name; kp.loading = true; kp.show = true; try { const { data } = await serversApi.getKeypair(s.id); kp.data = data } catch (e) { alert(e.response?.data?.detail || 'Error'); kp.show = false } finally { kp.loading = false } }

// expand pool
const ep = reactive({ show: false, busy: false, server: null, cidr: '', current: '', result: '', error: '' })
function openExpandPool(s) { ep.server = s; ep.cidr = ''; ep.current = s.address_pool_ipv4 || s.address_pool || ''; ep.result = ''; ep.error = ''; ep.show = true }
async function doExpandPool() { ep.busy = true; ep.error = ''; ep.result = ''; try { const { data } = await serversApi.expandPool(ep.server.id, ep.cidr.trim()); ep.result = data.message || 'Expanded'; await store.fetchServers() } catch (e) { ep.error = e.response?.data?.detail || e.message } finally { ep.busy = false } }

// migrate
const mig = reactive({ show: false, busy: false, source: null, targetId: null, pushConfigs: true, removeSource: true, result: null, error: '' })
const migrateTargets = computed(() => store.servers.filter(x => mig.source && x.id !== mig.source.id && x.server_category !== 'proxy').map(x => ({ value: x.id, label: x.display_name || x.name })))
function openMigrate(s) { mig.source = s; mig.targetId = null; mig.pushConfigs = true; mig.removeSource = true; mig.result = null; mig.error = ''; mig.show = true }
async function doMigrate() { mig.busy = true; mig.error = ''; try { const { data } = await serversApi.migrateClients(mig.source.id, { target_server_id: mig.targetId, push_configs: mig.pushConfigs, remove_from_source: mig.removeSource }); mig.result = data; await store.fetchServers() } catch (e) { mig.error = e.response?.data?.detail || e.message } finally { mig.busy = false } }

// bandwidth
const bw = reactive({ show: false, busy: false, server: null, limit: 0 })
function openBw(s) { bw.server = s; bw.limit = s.max_bandwidth_mbps || 0; bw.show = true }
async function saveBw() { bw.busy = true; try { await serversApi.update(bw.server.id, { max_bandwidth_mbps: bw.limit > 0 ? Number(bw.limit) : null }); await store.fetchServers(); bw.show = false } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { bw.busy = false } }

// obfs (AmneziaWG params)
const obfs = reactive({ show: false, busy: false, server: null, name: '', error: '', form: {} })
function openObfs(s) { obfs.server = s; obfs.name = s.display_name || s.name; obfs.error = ''; obfs.form = {}; for (const k of awgKeys) obfs.form[k] = s[k] ?? null; obfs.show = true }
async function saveObfs() { obfs.busy = true; obfs.error = ''; try { const payload = {}; for (const k of awgKeys) { const v = obfs.form[k]; payload[k] = (v === '' || v === undefined) ? null : v }; await serversApi.update(obfs.server.id, payload); await store.fetchServers(); obfs.show = false } catch (e) { obfs.error = e.response?.data?.detail || e.message } finally { obfs.busy = false } }

// install proxy
const ip = reactive({ show: false, busy: false, done: false, server: null, msg: '', error: '', log: [], form: { tls_mode: 'self_signed', obfs_password: '' } })
const ipLogBox = ref(null)
function openInstallProxy(s) { ip.server = s; ip.msg = ''; ip.error = ''; ip.done = false; ip.log = []; ip.form = { protocol: 'vless-reality', name: '', port: null, domain: '', tls_mode: 'self_signed', obfs_password: '' }; ip.show = true }
async function doInstallProxy() {
  ip.busy = true; ip.error = ''; ip.done = false; ip.log = []; ip.msg = tr('servers.installing') || 'Installing…'
  const f = ip.form
  const pl = { protocol: f.protocol }
  if (f.name) pl.name = f.name
  if (f.port) pl.port = Number(f.port)
  if (f.protocol === 'vless-reality') { if (f.domain) pl.domain = f.domain }
  else { pl.tls_mode = f.tls_mode; if (f.protocol === 'hysteria2' && f.obfs_password) pl.obfs_password = f.obfs_password }
  const taskId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2))
  pl.task_id = taskId
  // The task poll is the source of truth, NOT the HTTP call: the proxy install
  // over SSH can outlast the request's timeout, but the bootstrap keeps running
  // server-side. Stream the live log until the task reports a terminal state.
  const httpCall = serversApi.installProxy(ip.server.id, pl).catch((e) => ({ _httpError: e }))
  let sinceIdx = 0, terminal = null
  const deadline = Date.now() + 8 * 60 * 1000
  while (!terminal && Date.now() < deadline && ip.show) {
    try {
      const { data } = await serversApi.getBootstrapLogs(taskId, sinceIdx)
      if (data.logs && data.logs.length) {
        ip.log.push(...data.logs.map(_plain).filter(Boolean))
        sinceIdx = data.next_index
        await nextTick()
        if (ipLogBox.value) ipLogBox.value.scrollTop = ipLogBox.value.scrollHeight
      }
      if (data.complete) terminal = { error: data.error || null }
    } catch (_) { /* transient poll failure — keep going */ }
    if (!terminal) await new Promise(r => setTimeout(r, 1000))
  }
  const httpRes = await httpCall.catch(() => null)
  await store.fetchServers().catch(() => {})
  ip.msg = ''
  if (terminal && !terminal.error) {
    ip.done = true; ip.msg = '✅ ' + (tr('servers.installed') || 'Installed'); setTimeout(() => { if (!ip.busy) ip.show = false }, 1600)
  } else if (terminal) {
    ip.error = terminal.error
  } else if (httpRes && httpRes._httpError) {
    ip.error = httpRes._httpError.response?.data?.detail || httpRes._httpError.message
  } else if (httpRes) {
    ip.done = true; ip.msg = '✅ ' + (tr('servers.installed') || 'Installed'); setTimeout(() => { if (!ip.busy) ip.show = false }, 1600)
  } else {
    ip.error = tr('servers.installStillRunning') || 'Still installing server-side — check the server list in a few minutes.'
  }
  ip.busy = false
}

// server clients modal
const svc = reactive({ show: false, loading: false, title: '', rows: [], error: '' })
async function openSvClients(s) {
  svc.title = (tr('servers.clientsOn') || 'Clients on') + ' ' + (s.display_name || s.name); svc.rows = []; svc.error = ''; svc.loading = true; svc.show = true
  try {
    const { data } = await serversApi.getClients(s.id); const list = serverClientsFromResponse(data)
    svc.rows = list.map(c => ({
      id: c.id, name: c.name || c.display_name || ('client ' + c.id), ip: c.ipv4 || c.ip_address || c.assigned_ip || c.address || '—',
      dot: (c.enabled === false || c.status === 'disabled') ? 'var(--text-3)' : 'var(--green)',
      traffic: fmtBytes(c.total_bytes ?? ((c.traffic_used_rx || c.rx_bytes || 0) + (c.traffic_used_tx || c.tx_bytes || 0))),
    }))
  } catch (e) { svc.rows = []; svc.error = e.response?.data?.detail || e.message || (tr('common.error') || 'Failed to load clients') } finally { svc.loading = false }
}

function onDoc() { menuFor.value = null }
onMounted(() => {
  ui.set({ title: tr('nav.servers') || 'Servers', primary: { label: tr('servers.addServer') || 'Add server', onClick: openAdd }, live: null })
  store.fetchServers(); document.addEventListener('click', onDoc)
})
onUnmounted(() => document.removeEventListener('click', onDoc))
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-svgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; align-items: start; }
.d2-mi:hover { background: var(--panel-2); }
.hov-panel2:hover { background: var(--panel-2) !important; }
.hov-accent2:hover { background: var(--accent-2) !important; }
.hov-text:hover { color: var(--text) !important; }
.d2-field { display: flex; flex-direction: column; gap: 6px; }
.d2-flabel { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: var(--text-2); }
.d2-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.d2-pick { display: inline-flex; align-items: center; gap: 6px; padding: 9px 15px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.d2-pick.sm { padding: 7px 12px; font-size: 13px; }
.d2-pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.d2-progress { font-size: 13px; color: var(--accent); background: var(--accent-soft); padding: 9px 12px; border-radius: 9px; }
.d2f-input { width: 100%; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text); font-family: inherit; font-size: 14px; }
.d2f-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); }
.d2f-input.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
</style>
