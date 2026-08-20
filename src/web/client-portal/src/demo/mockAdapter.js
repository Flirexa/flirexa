import { demoQrBlob } from '../../../demo/demoQr.js'

const now = Date.now()
const isoAgo = minutes => new Date(now - minutes * 60_000).toISOString()
const json = data => typeof data === 'string' ? JSON.parse(data || '{}') : (data || {})
const response = (config, data, status = 200) => Promise.resolve({ data, status, statusText: status === 200 ? 'OK' : 'Demo', headers: {}, config, request: { demo: true } })

const features = {
  corp_networks: true, config_download: true, qr: true, promo_codes: true,
  account_balance: true, dns_protection: true, dns_policy_advanced: true,
  auto_renewal: false,
}
const subscription = {
  id: 701, tier: 'premium', status: 'active', raw_status: 'active', is_expired: false,
  is_active: true, max_devices: 5, devices_used: 2, over_device_limit: false,
  excess_devices: 0, traffic_limit_gb: 250, traffic_used_gb: 153.4,
  traffic_remaining_gb: 96.6, traffic_percentage: 61.36, bandwidth_limit_mbps: 300,
  price_monthly_usd: 12, expiry_date: new Date(now + 25 * 86400000).toISOString(),
  days_remaining: 25, auto_renew: false, created_at: new Date(now - 160 * 86400000).toISOString(),
  needs_plan: false,
}
const servers = [
  { id: 1, name: 'Amsterdam 01', location: 'Amsterdam, Netherlands', country_code: 'NL', status: 'online', server_category: 'vpn', server_type: 'wireguard', endpoint_host: '192.0.2.14', customer_visible: true },
  { id: 2, name: 'Frankfurt 01', location: 'Frankfurt, Germany', country_code: 'DE', status: 'online', server_category: 'vpn', server_type: 'amneziawg', endpoint_host: '198.51.100.40', customer_visible: true },
  { id: 3, name: 'New York 01', location: 'New York, United States', country_code: 'US', status: 'online', server_category: 'vpn', server_type: 'wireguard', endpoint_host: '203.0.113.21', customer_visible: true },
  { id: 4, name: 'Singapore 01', location: 'Singapore', country_code: 'SG', status: 'online', server_category: 'vpn', server_type: 'wireguard', endpoint_host: '192.0.2.22', customer_visible: true },
]
let slots = [
  { id: 41, label: 'MacBook Pro', subscription_url_path: '/sub/demo/slot/41', active_server_id: 1, active_server_name: 'Amsterdam 01', last_switched_at: isoAgo(90), is_bound: false, created_at: isoAgo(9000), servers: servers.map((s, i) => ({ server_id: s.id, server_name: s.name, server_display_name: s.name, server_location: s.location, country_code: s.country_code, server_type: s.server_type, ipv4: `10.${40 + s.id}.0.12/32`, enabled: i === 0, is_active: i === 0, last_handshake: i === 0 ? isoAgo(1) : null })) },
  { id: 42, label: 'Samsung Galaxy S25', subscription_url_path: '/sub/demo/slot/42', active_server_id: 3, active_server_name: 'New York 01', last_switched_at: isoAgo(240), is_bound: false, created_at: isoAgo(4000), servers: servers.map((s, i) => ({ server_id: s.id, server_name: s.name, server_display_name: s.name, server_location: s.location, country_code: s.country_code, server_type: s.server_type, ipv4: `10.${40 + s.id}.0.24/32`, enabled: i === 2, is_active: i === 2, last_handshake: i === 2 ? isoAgo(2) : null })) },
]
const peers = () => slots.flatMap(slot => slot.servers.map((srv, index) => ({
  id: slot.id * 10 + srv.server_id, slot_id: slot.id, name: slot.label,
  server_id: srv.server_id, server_name: srv.server_name,
  server_type: servers.find(s => s.id === srv.server_id)?.server_type || 'wireguard',
  ipv4: srv.ipv4, enabled: srv.enabled, online: srv.enabled && index < 3,
  last_handshake: srv.last_handshake, traffic_used_rx: 24 * 1024 ** 3,
  traffic_used_tx: 5 * 1024 ** 3,
})))
const dnsProfiles = [
  { id: 'standard', name: 'No filter', description: 'Normal private DNS resolution' },
  { id: 'ads', name: 'Ad & tracker blocking', description: 'Blocks advertising and analytics domains' },
  { id: 'malware', name: 'Malware protection', description: 'Blocks known malicious and phishing domains' },
  { id: 'combined', name: 'Ad, tracker & malware', description: 'Complete DNS protection' },
]
const dnsBySlot = { 41: 'combined', 42: 'ads' }
let invoiceSequence = 704
let balanceAvailableMinor = 10000
let supportMessages = [
  { id: 81, subject: 'Device setup question', message: 'Could you help me connect my laptop?', status: 'answered', direction: 'customer', is_read: true, created_at: isoAgo(2400), replies: [{ id: 811, message: 'Open Devices and choose a location. We are here if you need anything else.', direction: 'admin', is_read: true, created_at: isoAgo(2350) }] },
  { id: 82, subject: 'Payment receipt', message: 'Where can I find my receipt?', status: 'closed', direction: 'customer', is_read: true, created_at: isoAgo(25000), replies: [] },
]
let corporateNetworks = [{
  id: 9, name: 'Operations Network', vpn_subnet: '10.91.0.0/24', status: 'active',
  site_count: 3, active_site_count: 3, expires_at: null,
  health: { health: 'healthy', errors: [], warnings: [] },
  sites: [
    { id: 91, name: 'Amsterdam HQ', status: 'active', is_relay: true, site_subnet: '10.20.0.0/24', local_subnets: ['10.20.0.0/24'], tunnel_ip: '10.91.0.1/32', vpn_ip: '10.91.0.1/32', endpoint: '192.0.2.14:51830', listen_port: 51830, suggested_interface: 'flx-corp-9-91', routing_mode: 'auto', config_downloaded_at: isoAgo(720), last_handshake: isoAgo(1) },
    { id: 92, name: 'London Office', status: 'active', is_relay: false, site_subnet: '10.21.0.0/24', local_subnets: ['10.21.0.0/24'], tunnel_ip: '10.91.0.2/32', vpn_ip: '10.91.0.2/32', endpoint: '198.51.100.12:51831', listen_port: 51831, suggested_interface: 'flx-corp-9-92', routing_mode: 'direct', config_downloaded_at: isoAgo(700), last_handshake: isoAgo(2) },
    { id: 93, name: 'New York Office', status: 'active', is_relay: false, site_subnet: '10.22.0.0/24', local_subnets: ['10.22.0.0/24'], tunnel_ip: '10.91.0.3/32', vpn_ip: '10.91.0.3/32', endpoint: '203.0.113.21:51832', listen_port: 51832, suggested_interface: 'flx-corp-9-93', routing_mode: 'direct', config_downloaded_at: isoAgo(680), last_handshake: isoAgo(3) },
  ],
}]

const currentCorporateNetwork = id => corporateNetworks.find(network => network.id === Number(id))
const syncCorporateCounts = network => {
  if (!network) return network
  network.site_count = network.sites.length
  network.active_site_count = network.sites.filter(site => site.status === 'active').length
  return network
}

export function createPortalDemoAdapter() {
  return async config => {
    const url = (config.url || '').replace(/^https?:\/\/[^/]+/, '')
    const path = url.split('?')[0]
    const method = (config.method || 'get').toLowerCase()
    if (path === '/api/v1/public/branding' || path === '/public/branding') return response(config, {
      branding_customer_app_name: 'Flirexa', branding_customer_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png', branding_favicon_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_primary_color: '#6366f1', branding_footer_text: '© 2026 Flirexa',
      branding_privacy_url: '/demo-authentic/portal/#/legal/privacy', branding_terms_url: '/demo-authentic/portal/#/legal/terms', branding_support_url: 'mailto:support@example.test', branding_support_email: 'support@example.test', branding_powered_by: false,
      branding_privacy_text: 'This interactive preview uses synthetic data only. It does not collect customer credentials or connect to a live VPN service.',
      branding_terms_text: 'This demo is provided for product evaluation. All accounts, payments, devices and network details shown here are fictional.',
      branding_github_card: false,
    })
    if (path === '/client-portal/auth/me') return response(config, { id: 701, username: 'Emma Wilson', email: 'emma.wilson@example.test', is_verified: true })
    if (path.includes('/client-portal/auth/')) return response(config, { ok: true, user: { id: 701, username: 'Emma Wilson', email: 'emma.wilson@example.test', is_verified: true } })
    if (path === '/client-portal/features') return response(config, { features, portal_mode: 'simple' })
    if (path === '/client-portal/subscription') return response(config, subscription)
    if (path === '/client-portal/subscription/plans') return response(config, [
      { tier: 'basic', name: 'Essential', description: 'For one personal device', max_devices: 1, traffic_limit_gb: 100, bandwidth_limit_mbps: 100, price_monthly_usd: 4, price_quarterly_usd: 11, price_yearly_usd: 39, pricing_tiers: [] },
      { tier: 'premium', name: 'Premium', description: 'Every location and advanced protection', max_devices: 5, traffic_limit_gb: 250, bandwidth_limit_mbps: 300, price_monthly_usd: 12, price_quarterly_usd: 32, price_yearly_usd: 99, pricing_tiers: [] },
      { tier: 'business', name: 'Team', description: 'Shared access for small teams', max_devices: 15, traffic_limit_gb: 0, bandwidth_limit_mbps: 0, price_monthly_usd: 29, price_quarterly_usd: 79, price_yearly_usd: 249, pricing_tiers: [] },
    ])
    if (url.startsWith('/client-portal/dashboard/traffic-series')) {
      const series = Array.from({ length: 14 }, (_, i) => ({ date: new Date(now - (13 - i) * 86400000).toISOString().slice(0, 10), rx_gb: 5 + i * .7, tx_gb: 1.3 + i * .2 }))
      return response(config, { range: '14d', series, active_devices_series: series.map((p, i) => ({ date: p.date, count: i % 3 ? 2 : 1 })), summary: { total_rx_gb: 131.8, total_tx_gb: 21.6, total_gb: 153.4, trend_pct: 8.7 } })
    }
    if (path === '/client-portal/wireguard/clients') return response(config, peers())
    if (path === '/client-portal/servers') return response(config, servers)
    if (/\/client-portal\/servers\/\d+\/probe/.test(url)) return response(config, { status: 'online', rtt_ms: 28 + Number(url.match(/\d+/)?.[0] || 1) * 9 })
    if (path === '/client-portal/devices') {
      if (method === 'post') {
        const body = json(config.data); const id = Math.max(...slots.map(s => s.id)) + 1
        const created = { ...slots[0], id, label: body.label || 'New device', is_bound: false, active_server_id: body.initial_server_id || 1, servers: slots[0].servers.map(s => ({ ...s, enabled: s.server_id === (body.initial_server_id || 1), is_active: s.server_id === (body.initial_server_id || 1), last_handshake: null })) }
        slots.push(created)
        return response(config, created)
      }
      return response(config, slots)
    }
    const slotMatch = path.match(/^\/client-portal\/devices\/(\d+)(.*)$/)
    if (slotMatch) {
      const id = Number(slotMatch[1]); const suffix = slotMatch[2]; const slot = slots.find(s => s.id === id)
      if (suffix === '/dns') {
        if (method === 'put') dnsBySlot[id] = json(config.data).profile_id
        return response(config, { enabled: true, forced: false, customer_choice_enabled: true, selected_profile_id: dnsBySlot[id] || 'standard', effective_profile_id: dnsBySlot[id] || 'standard', profiles: dnsProfiles })
      }
      if (suffix === '/release') { slot.is_bound = false; return response(config, slot) }
      if (suffix === '/switch-server') { const serverId = Number(json(config.data).server_id); slot.active_server_id = serverId; slot.active_server_name = servers.find(s => s.id === serverId)?.name; slot.servers.forEach(s => { s.enabled = s.server_id === serverId; s.is_active = s.enabled }); return response(config, slot) }
      if (suffix.startsWith('/config/')) return response(config, { config_text: '[Interface]\nPrivateKey = demo\nAddress = 10.41.0.12/32\nDNS = 10.0.0.53\n\n[Peer]\nPublicKey = demo\nEndpoint = demo.example:51820', protocol: 'wireguard', client_name: slot.label })
      if (suffix.startsWith('/qrcode/')) return response(config, demoQrBlob())
      if (!suffix && method === 'delete') { slots = slots.filter(s => s.id !== id); return response(config, { ok: true }) }
      if (!suffix && method === 'patch') { slot.label = json(config.data).label || slot.label; return response(config, slot) }
    }
    if (/\/client-portal\/wireguard\/config\//.test(url)) return response(config, { config_text: '[Interface]\nPrivateKey = demo\nAddress = 10.41.0.12/32\nDNS = 10.0.0.53', protocol: 'wireguard', client_name: 'Demo device' })
    if (/\/client-portal\/wireguard\/qrcode\//.test(url)) return response(config, demoQrBlob())
    if (path === '/client-portal/referral') return response(config, { referral_code: 'FLIREXA-DEMO', referral_count: 8, paid_referrals: 3 })
    if (path === '/client-portal/payments/history') return response(config, [
      { id: 1, invoice_id: 'INV-000701', amount_usd: 12, status: 'completed', payment_method: 'stripe', purpose: 'subscription', subscription_tier: 'premium', duration_days: 30, created_at: isoAgo(5000) },
      { id: 2, invoice_id: 'INV-000648', amount_usd: 12, status: 'completed', payment_method: 'paypal', purpose: 'subscription', subscription_tier: 'premium', duration_days: 30, created_at: isoAgo(48000) },
      { id: 3, invoice_id: 'INV-000601', amount_usd: 25, status: 'completed', payment_method: 'account_balance', purpose: 'balance_topup', created_at: isoAgo(92000) },
    ])
    if (path === '/client-portal/payments/providers') return response(config, [
      { id: 'stripe', display_name: 'Card', type: 'fiat', configured: true },
      { id: 'paypal', display_name: 'PayPal', type: 'fiat', configured: true },
      { id: 'nowpayments', display_name: 'Crypto', type: 'crypto', configured: true },
    ])
    if (path === '/client-portal/payments/balance' && method === 'get') return response(config, { enabled: true, currency: 'USD', available_minor: balanceAvailableMinor, transactions: [
      { id: 1, type: 'topup', amount_minor: 2500, created_at: isoAgo(2900) },
      { id: 2, type: 'subscription_purchase', amount_minor: -1200, created_at: isoAgo(1600) },
    ] })
    if (path === '/client-portal/payments/create-invoice' && method === 'post') {
      const body = json(config.data)
      const invoiceId = `DEMO-${++invoiceSequence}`
      return response(config, {
        invoice_id: invoiceId,
        amount_usd: Number(body.topup_amount_usd || (body.plan_tier === 'business' ? 29 : body.plan_tier === 'premium' ? 12 : 4)),
        currency: String(body.currency || 'USD').toUpperCase(),
        provider: body.provider || 'stripe',
        status: 'pending',
        expires_at: new Date(now + 30 * 60_000).toISOString(),
        payment_address: body.provider === 'nowpayments' ? 'demo1q7flirexa9preview3payment' : null,
      })
    }
    const paymentCheck = path.match(/^\/client-portal\/payments\/check\/([^/]+)$/)
    if (paymentCheck) {
      return response(config, { invoice_id: paymentCheck[1], status: 'completed', paid: true })
    }
    if (path === '/client-portal/payments/balance/purchase' && method === 'post') {
      balanceAvailableMinor = Math.max(0, balanceAvailableMinor - 1200)
      return response(config, { status: 'completed', balance: { enabled: true, currency: 'USD', available_minor: balanceAvailableMinor } })
    }
    if (path === '/client-portal/promo/validate' && method === 'post') {
      const code = String(json(config.data).code || '').toUpperCase()
      return response(config, code === 'DEMO10'
        ? { valid: true, discount_type: 'percent', discount_value: 10, code }
        : { valid: false, error: 'Try DEMO10 in this preview.' })
    }
    if (path === '/client-portal/support/messages' && method === 'get') return response(config, supportMessages)
    if (path === '/client-portal/support/send' && method === 'post') {
      const body = json(config.data)
      const created = { id: Math.max(...supportMessages.map(item => item.id)) + 1, subject: body.subject, message: body.message, status: 'open', direction: 'customer', is_read: true, created_at: new Date().toISOString(), replies: [] }
      supportMessages = [created, ...supportMessages]
      return response(config, created)
    }
    const supportReply = path.match(/^\/client-portal\/support\/(\d+)\/reply$/)
    if (supportReply && method === 'post') {
      const ticket = supportMessages.find(item => item.id === Number(supportReply[1]))
      if (ticket) {
        ticket.replies.push({ id: Date.now(), message: json(config.data).message, direction: 'customer', is_read: true, created_at: new Date().toISOString() })
        ticket.status = 'open'
      }
      return response(config, ticket || { ok: true })
    }
    if (path === '/client-portal/support/unread-count') return response(config, { unread_count: 0 })
    if (path === '/client-portal/notifications') return response(config, [{ id: 1, title: 'New VPN location', message: 'Singapore is now available in your device settings.', is_read: false, created_at: isoAgo(120) }])

    if (path === '/client-portal/corporate/networks') {
      if (method === 'post') {
        const body = json(config.data)
        const nextId = Math.max(...corporateNetworks.map(item => item.id), 0) + 1
        const created = { id: nextId, name: body.name || `Network ${nextId}`, vpn_subnet: `10.${90 + nextId}.0.0/24`, status: 'active', site_count: 0, active_site_count: 0, expires_at: null, health: { health: 'healthy', errors: [], warnings: [] }, sites: [] }
        corporateNetworks = [created, ...corporateNetworks]
        return response(config, created)
      }
      return response(config, corporateNetworks)
    }
    const corporateBase = path.match(/^\/client-portal\/corporate\/networks\/(\d+)$/)
    if (corporateBase) {
      const network = currentCorporateNetwork(corporateBase[1])
      if (method === 'delete') {
        corporateNetworks = corporateNetworks.filter(item => item.id !== Number(corporateBase[1]))
        return response(config, { ok: true })
      }
      return response(config, network || corporateNetworks[0])
    }
    const corporateSite = path.match(/^\/client-portal\/corporate\/networks\/(\d+)\/sites(?:\/(\d+))?(?:\/(config|regenerate-keys|relay))?$/)
    if (corporateSite) {
      const network = currentCorporateNetwork(corporateSite[1]) || corporateNetworks[0]
      const siteId = Number(corporateSite[2])
      const action = corporateSite[3]
      const site = network?.sites.find(item => item.id === siteId)
      if (!corporateSite[2] && method === 'post') {
        const body = json(config.data)
        const nextId = Math.max(...network.sites.map(item => item.id), network.id * 10) + 1
        const created = { id: nextId, name: body.name || `Site ${network.sites.length + 1}`, status: 'active', is_relay: !!body.is_relay, local_subnets: body.local_subnets || [], site_subnet: body.local_subnets?.[0] || null, vpn_ip: `10.${90 + network.id}.0.${network.sites.length + 1}/32`, tunnel_ip: `10.${90 + network.id}.0.${network.sites.length + 1}/32`, endpoint: body.endpoint || null, listen_port: 51820 + network.sites.length, suggested_interface: `flx-corp-${network.id}-${nextId}`, routing_mode: body.routing_mode || 'auto', config_downloaded_at: null, last_handshake: null }
        network.sites.push(created); syncCorporateCounts(network)
        return response(config, created)
      }
      if (action === 'config') return response(config, `[Interface]\nPrivateKey = demo\nAddress = ${site?.vpn_ip || '10.91.0.10/32'}\n\n[Peer]\nPublicKey = demo\nAllowedIPs = 10.0.0.0/8\n`)
      if (action === 'regenerate-keys') return response(config, { ok: true })
      if (action === 'relay' && site) { site.is_relay = !!json(config.data).is_relay; return response(config, site) }
      if (method === 'patch' && site) { Object.assign(site, json(config.data)); return response(config, site) }
      if (method === 'delete' && site) { network.sites = network.sites.filter(item => item.id !== siteId); syncCorporateCounts(network); return response(config, { ok: true }) }
    }
    const corporateAux = path.match(/^\/client-portal\/corporate\/networks\/(\d+)\/(health|diagnostics|events|relay)$/)
    if (corporateAux) {
      const network = currentCorporateNetwork(corporateAux[1]) || corporateNetworks[0]
      if (corporateAux[2] === 'health') return response(config, { health: 'healthy', errors: [], warnings: [], sites: network.sites })
      if (corporateAux[2] === 'diagnostics') return response(config, {
        health: 'healthy', errors: [], warnings: [], ran_at: new Date().toISOString(),
        has_relay: network.sites.some(site => site.is_relay),
        relay_site_name: network.sites.find(site => site.is_relay)?.name || null,
        sites: network.sites.map(site => ({
          site_id: site.id, site_name: site.name, status: 'healthy',
          is_relay: site.is_relay, routing_mode: site.routing_mode,
          behind_nat: false, vpn_ip: site.vpn_ip, endpoint: site.endpoint,
          endpoint_resolved_ip: site.endpoint?.split(':')[0] || null,
          endpoint_is_private: false, errors: [], warnings: [],
          config_downloaded: !!site.config_downloaded_at,
          has_local_subnets: !!site.local_subnets?.length,
          peers: network.sites.filter(peer => peer.id !== site.id).map(peer => ({
            peer_id: peer.id, peer_name: peer.name, status: 'healthy',
            peer_is_relay: peer.is_relay, uses_relay: false, relay_name: null,
            nat_detected: false, peer_has_endpoint: !!peer.endpoint,
            peer_endpoint_dns_ok: true, bidirectional_endpoints: true, issues: [],
          })),
        })),
      })
      if (corporateAux[2] === 'events') return response(config, [{ id: 1, event_type: 'handshake', severity: 'info', description: 'All sites exchanged fresh handshakes', created_at: isoAgo(4) }])
      return response(config, { relay_site_id: network.sites.find(site => site.is_relay)?.id || null, topology: [] })
    }
    return response(config, { ok: true, demo: true })
  }
}
