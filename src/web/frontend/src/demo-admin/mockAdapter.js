import { demoQrBlob } from '../../../demo/demoQr.js'

const now = Date.now()
const isoAgo = minutes => new Date(now - minutes * 60_000).toISOString()

export const enterpriseFeatures = [
  'white_label', 'custom_branding', 'custom_domain', 'custom_email_sender',
  'applications', 'dns_protection', 'dns_custom_profiles', 'dns_enforcement',
  'account_balance', 'payments', 'promo_codes', 'traffic_rules', 'telegram_bots',
  'backups', 'plugins', 'multi_server', 'unlimited_servers', 'priority_support',
]

const serverSeed = [
  ['Amsterdam 01', 'Amsterdam, Netherlands', 'wireguard', 529, '45.83.21.14'],
  ['Amsterdam 02', 'Amsterdam, Netherlands', 'amneziawg', 478, '45.83.21.18'],
  ['Frankfurt 01', 'Frankfurt, Germany', 'wireguard', 567, '185.91.22.40'],
  ['Frankfurt 02', 'Frankfurt, Germany', 'vless-reality', 411, '185.91.22.41'],
  ['London 01', 'London, United Kingdom', 'wireguard', 544, '91.204.18.12'],
  ['London 02', 'London, United Kingdom', 'hysteria2', 455, '91.204.18.16'],
  ['New York 01', 'New York, United States', 'wireguard', 625, '172.93.44.21'],
  ['New York 02', 'New York, United States', 'amneziawg', 534, '172.93.44.25'],
  ['Los Angeles', 'Los Angeles, United States', 'wireguard', 430, '104.219.18.30'],
  ['Toronto', 'Toronto, Canada', 'tuic', 380, '149.56.23.19'],
  ['Warsaw', 'Warsaw, Poland', 'amneziawg', 492, '194.15.36.11'],
  ['Stockholm', 'Stockholm, Sweden', 'wireguard', 447, '193.182.12.44'],
  ['Singapore 01', 'Singapore', 'wireguard', 508, '103.27.18.22'],
  ['Singapore 02', 'Singapore', 'hysteria2', 448, '103.27.18.28'],
  ['Tokyo', 'Tokyo, Japan', 'vless-reality', 437, '160.16.44.31'],
  ['Sydney', 'Sydney, Australia', 'wireguard', 355, '139.99.17.20'],
  ['São Paulo', 'São Paulo, Brazil', 'amneziawg', 337, '191.96.72.18'],
]

export const demoServers = serverSeed.map((row, index) => ({
  id: index + 1,
  name: row[0],
  display_name: row[0],
  location: row[1],
  server_type: row[2],
  server_category: ['hysteria2', 'tuic', 'vless-reality'].includes(row[2]) ? 'proxy' : 'vpn',
  total_clients: row[3],
  max_clients: 2500,
  endpoint: `${row[4]}:${row[2] === 'vless-reality' ? 443 : 51820}`,
  listen_port: row[2] === 'vless-reality' ? 443 : 51820,
  address_pool_ipv4: `10.${index + 40}.0.0/16`,
  public_key: `FlirexaDemoPublicKey${String(index + 1).padStart(2, '0')}xxxxxxxxxxxx=`,
  interface: row[2] === 'amneziawg' ? 'awg0' : row[2] === 'wireguard' ? 'wg0' : null,
  status: 'online',
  is_online: true,
  online: true,
  is_default: index === 0,
  agent_mode: 'agent',
  agent_version: '2.2.100',
  max_bandwidth_mbps: 1000,
  customer_visible: true,
  customer_visible_mobile: true,
  customer_visible_windows: true,
  split_tunnel_support: true,
}))

const customerNames = [
  'Emma Wilson', 'Noah Williams', 'Olivia Martin', 'Mateo Garcia', 'Sophia Brown',
  'Lucas Bernard', 'Mia Anderson', 'Ethan Miller', 'Ava Thompson', 'Leo Schneider',
  'Isabella Rossi', 'James Walker', 'Amelia Clark', 'Henry Lewis', 'Luna Taylor',
  'Alexander King', 'Chloe Harris', 'Daniel Young', 'Sofia Moore', 'Jack Hall',
  'Emily Allen', 'Benjamin Scott', 'Nora Green', 'Samuel Baker', 'Ella Adams',
  'David Nelson', 'Maya Hill', 'Michael Perez', 'Grace Roberts', 'Thomas Turner',
  'Zoe Campbell', 'William Parker', 'Layla Evans', 'Joseph Collins', 'Aria Stewart',
  'Oliver Morris', 'Elena Reed', 'Theo Cook', 'Mila Morgan', 'Liam Carter',
]

export const demoClients = customerNames.map((name, index) => ({
  id: 1001 + index,
  name,
  email: `${name.toLowerCase().replaceAll(' ', '.')}@example.test`,
  server_id: (index * 3) % 17 + 1,
  ipv4: `10.${40 + ((index * 3) % 17)}.${1 + Math.floor(index / 200)}.${10 + index}`,
  enabled: index % 11 !== 0,
  last_handshake: index % 5 === 0 ? isoAgo(14) : isoAgo((index % 2) + 1),
  traffic_used_rx: (8 + index * 1.7) * 1024 ** 3,
  traffic_used_tx: (2 + index * 0.6) * 1024 ** 3,
  traffic_limit_mb: index % 3 ? 250 * 1024 : 0,
  bandwidth_limit: index % 4 ? 100 : 0,
  expiry_date: new Date(now + (12 + index % 18) * 86_400_000).toISOString(),
  protocol: demoServers[(index * 3) % 17].server_category === 'proxy' ? 'proxy' : 'vpn',
  segment_id: index % 4 === 0 ? 1 : index % 7 === 0 ? 2 : null,
  public_key: `demo-client-public-key-${index + 1}`,
}))

const portalUsers = demoClients.slice(0, 24).map((client, index) => ({
  id: 501 + index,
  email: client.email,
  username: client.name,
  display_name: client.name,
  is_active: true,
  balance: Number((index % 5) * 4.25).toFixed(2),
  balance_usd: Number((index % 5) * 4.25).toFixed(2),
  subscription_tier: index % 5 === 0 ? 'team' : index % 3 === 0 ? 'annual' : 'monthly',
  subscription_status: 'active',
  subscription_expires_at: new Date(now + (20 + index) * 86_400_000).toISOString(),
  devices_count: index % 3 + 1,
  traffic_used_bytes: client.traffic_used_rx + client.traffic_used_tx,
  created_at: new Date(now - (70 - index) * 86_400_000).toISOString(),
}))

const tariffs = [
  { id: 1, name: 'Monthly', tier: 'monthly', price_usd: 4.99, duration_days: 30, max_devices: 2, traffic_limit_gb: 250, bandwidth_limit_mbps: 100, is_active: true, sort_order: 1, subscribers_count: 3792 },
  { id: 2, name: 'Annual', tier: 'annual', price_usd: 39.99, duration_days: 365, max_devices: 5, traffic_limit_gb: null, bandwidth_limit_mbps: null, is_active: true, sort_order: 2, subscribers_count: 3166 },
  { id: 3, name: 'Team', tier: 'team', price_usd: 12.99, duration_days: 30, max_devices: 10, traffic_limit_gb: null, bandwidth_limit_mbps: null, is_active: true, sort_order: 3, subscribers_count: 1019 },
]

const payments = portalUsers.slice(0, 18).map((user, index) => ({
  id: 7001 + index,
  user_id: user.id,
  email: user.email,
  amount: index % 3 === 1 ? 39.99 : index % 3 === 2 ? 12.99 : 4.99,
  amount_usd: index % 3 === 1 ? 39.99 : index % 3 === 2 ? 12.99 : 4.99,
  provider: ['stripe', 'paypal', 'crypto', 'balance'][index % 4],
  status: index === 7 ? 'pending' : 'paid',
  created_at: isoAgo(index * 19 + 4),
  paid_at: isoAgo(index * 19 + 3),
  invoice_id: `INV-DEMO-${7001 + index}`,
}))

const logs = [
  ['create_client', 'Emma Wilson'], ['payment_confirmed', 'INV-DEMO-7001'],
  ['server_health_ok', 'Tokyo'], ['dns_profile_updated', 'Full protection'],
  ['backup_verified', 'full-20260817'], ['portal_login', 'Noah Williams'],
].map((row, index) => ({ id: index + 1, action: row[0], target_name: row[1], actor: 'admin', created_at: isoAgo(index * 7 + 2), details: 'Synthetic interactive demo event' }))

const dates = Array.from({ length: 12 }, (_, index) => new Date(2025 + Math.floor((index + 8) / 12), (index + 8) % 12, 1).toISOString())
const chartData = {
  revenue_trend: dates.map((date, index) => ({ date, amount: 18_708 + index * 1200 })),
  user_trend: dates.map((date, index) => ({ date, count: 820 + index * 74 })),
  traffic_trend: Array.from({ length: 14 }, (_, index) => ({ date: new Date(now - (13 - index) * 86_400_000).toISOString(), gb: 31_000 + index * 1830 })),
  sub_distribution: { monthly: 3792, annual: 3166, team: 1019 },
  payment_methods: { stripe: 19_464, paypal: 7339, crypto: 3510, balance: 1595 },
}

const status = {
  clients: { total: 7977, active: 2002 },
  servers: { total: 17, online: 17 },
  traffic: { total_formatted: '510 TB', bandwidth_mbps: 7583, exceeded_count: 0 },
  expiry: { expiring_week: 61 },
  system: { cpu_percent: 28, memory_percent: 46, disk_percent: 34 },
}

const revenue = { revenue_30d: '31908.00', total_revenue: '281704.00', active_subscriptions: 7977, total_users: 8309 }

const healthServers = demoServers.map((server, index) => ({
  server_id: server.id,
  server_name: server.name,
  status: 'healthy',
  connection_mode: 'agent',
  checked_at: isoAgo(index % 4),
  latency_ms: 18 + index * 2,
  system: { cpu_percent: 18 + index, memory_percent: 31 + index, disk_percent: 24 + index, uptime_seconds: 2_400_000 + index * 40_000 },
  wireguard: { peers_total: server.total_clients, peers_active: Math.round(server.total_clients * 0.25) },
  drift: { detected: false, issues: [] },
}))

const dnsProfiles = [
  ['standard', 'No filter', 'Normal private DNS resolution', ['10.10.0.53']],
  ['ads', 'Ad & tracker blocking', 'Blocks advertising and analytics domains', ['10.10.1.53']],
  ['malware', 'Malware protection', 'Blocks malicious and phishing domains', ['10.10.2.53']],
  ['combined', 'Ad, tracker & malware', 'Combined protection profile', ['10.10.3.53']],
].map((row, index) => ({ id: index + 1, slug: row[0], key: row[0], name: row[1], description: row[2], resolver_addresses: row[3], enabled: true, customer_selectable: true, is_default: index === 0, builtin: true }))

const supportTickets = [
  { id: 81, email: 'emma.wilson@example.test', subject: 'Device setup question', status: 'open', unread_count: 1, created_at: isoAgo(42), updated_at: isoAgo(5), messages: [{ id: 1, sender: 'customer', message: 'Could you help me connect my laptop?', created_at: isoAgo(42) }, { id: 2, sender: 'admin', message: 'Of course. Open Devices and download the configuration for your laptop.', created_at: isoAgo(38) }] },
  { id: 82, email: 'noah.williams@example.test', subject: 'Payment receipt', status: 'closed', unread_count: 0, created_at: isoAgo(340), updated_at: isoAgo(310), messages: [] },
]

function response(config, data, statusCode = 200) {
  return Promise.resolve({ data, status: statusCode, statusText: 'OK', headers: {}, config, request: { demo: true } })
}

function parseBody(config) {
  if (!config.data) return {}
  if (typeof config.data === 'object') return config.data
  try { return JSON.parse(config.data) } catch (_) { return {} }
}

function appLogs() {
  return { entries: logs.map((row, index) => ({ timestamp: row.created_at, level: index === 4 ? 'warning' : 'info', logger: 'flirexa.demo', message: `${row.action}: ${row.target_name}` })) }
}

export function createDemoAdapter() {
  let portalMode = 'simple'
  return async config => {
    const raw = String(config.url || '')
    const url = raw.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api\/v1/, '').split('?')[0]
    const method = String(config.method || 'get').toLowerCase()
    const body = parseBody(config)

    if (url === '/public/branding') return response(config, {
      branding_app_name: 'Flirexa', branding_company_name: 'Enterprise Demo',
      branding_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_favicon_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_powered_by: false, branding_github_card: false, branding_primary_color: '#6366f1',
    })
    if (url === '/system/dashboard') return response(config, { status, clients: { total: 7977, items: demoClients.slice(0, 10) }, servers: { total: 17, items: demoServers }, revenue, charts: chartData })
    if (url === '/system/status') return response(config, status)
    if (url === '/system/logs') return response(config, { total: logs.length, items: logs })
    if (url === '/system/app-logs' || url === '/system/app-logs/errors') return response(config, appLogs())
    if (url === '/system/health') return response(config, { checks: { database: true, redis: true, api: true, portal: true }, status: 'healthy' })
    if (url === '/system/license') return response(config, {
      type: 'enterprise', tier: 'enterprise', status: 'active', active: true,
      lifetime: true, days_remaining: null, expires_at: null,
      features: enterpriseFeatures, max_servers: 999999, max_clients: 999999,
      current_servers: 17, current_clients: 7977,
      server_id: 'demo-enterprise-installation', owner: 'Enterprise Demo',
    })
    if (url === '/system/license-server') return response(config, {
      primary_url: 'Primary licensing endpoint',
      backup_url: 'Signed offline license available',
      server_reachable: true, online_status: 'active',
      last_check: isoAgo(1), grace: false, offline_license: true,
    })
    if (url === '/system/client-portal-settings') {
      if (method === 'post') portalMode = body.mode === 'advanced' ? 'advanced' : 'simple'
      return response(config, { mode: portalMode })
    }
    if (url === '/system/payment-settings') return response(config, { stripe_enabled: true, stripe_configured: true, paypal_enabled: true, paypal_configured: true, crypto_enabled: true, stripe_payment_method_mode: 'automatic', stripe_payment_methods: 'card' })
    if (url === '/system/smtp-settings') return response(config, { smtp_enabled: true, smtp_host: 'smtp.example.test', smtp_port: 587, smtp_username: 'mailer', smtp_password_set: true, smtp_tls: true, smtp_from: 'support@example.test' })
    if (url === '/system/notification-settings') return response(config, { admin_telegram_chat_id: 'configured', notify_admin_new_user: true, notify_admin_new_payment: true, notify_admin_subscription_expired: true, notify_user_expiry_warning: true, notify_user_traffic_warning: true, notify_user_payment_confirmed: true, app_integration_enabled: true, push_enabled: true, app_name: 'NovaShield', fcm_server_key_set: true })
    if (url === '/system/device-limits') return response(config, { max_devices_per_customer: 5 })
    if (url === '/system/subscription-settings') return response(config, { enable_free_tier: true })
    if (url === '/system/web-access') return response(config, { setup_mode: 'https', client_portal_domain: 'account.novashield.example', admin_panel_domain: 'admin.novashield.example', certbot_email: 'admin@example.test', https_ready: true })
    if (url === '/system/branding') return response(config, {
      branding_app_name: 'Flirexa', branding_customer_app_name: 'Flirexa VPN',
      branding_tagline: 'Private access everywhere', branding_company_name: 'Enterprise Demo',
      branding_login_title: 'Admin Panel', branding_support_email: 'support@example.test',
      branding_support_url: 'https://support.example.test', branding_privacy_url: '/privacy',
      branding_terms_url: '/terms', branding_privacy_text: 'Synthetic privacy policy preview.',
      branding_terms_text: 'Synthetic terms preview.', branding_footer_text: '© 2026 Flirexa VPN',
      branding_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_customer_logo_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_favicon_url: '/assets/flirexa-logo-globe-v2-transparent.png',
      branding_powered_by: false, branding_github_card: false, branding_primary_color: '#6366f1',
    })
    if (url === '/system/donation-wallets') return response(config, { wallets: [] })
    if (url === '/system/check-limits') return response(config, { checked: 7977, violations: 0 })
    if (url === '/system/notifications/list') return response(config, { items: logs.slice(0, 4).map((row, index) => ({ id: index + 1, title: row.action, message: row.target_name, status: 'sent', created_at: row.created_at, audience: 'all' })) })

    if (url === '/clients/map-data') return response(config, { servers: demoServers.slice(0, 9).map((server, index) => ({ name: server.name, lat: [52.37, 50.11, 51.5, 40.71, 34.05, 43.65, 52.22, 1.35, 35.68][index], lon: [4.9, 8.68, -0.12, -74, -118.24, -79.38, 21.01, 103.82, 139.69][index] })), clients: [] })
    if (url === '/clients/online') return response(config, { total: 2002, items: demoClients.filter(client => client.enabled).slice(0, 28) })
    if (url === '/clients/slots/admin') return response(config, { items: demoClients.slice(0, 16).map((client, index) => ({ id: 900 + index, label: index % 2 ? 'Mobile device' : 'Desktop device', owner_id: portalUsers[index % portalUsers.length].id, owner_email: portalUsers[index % portalUsers.length].email, device_id: index % 4 ? `device-${index + 1}` : null, device_name: index % 2 ? 'Samsung Galaxy S25' : 'Windows Desktop', active_server_id: client.server_id, peers: [{ server_id: client.server_id, client_id: client.id }], created_at: isoAgo(1000 + index) })) })
    if (url === '/clients') return response(config, { total: 7977, items: demoClients })
    if (/^\/clients\/\d+\/share-link$/.test(url)) return response(config, { url: 'https://account.novashield.example/config/demo-token', expires_at: new Date(now + 600_000).toISOString() })
    if (/^\/clients\/\d+\/config/.test(url)) return response(config, { config: '[Interface]\nPrivateKey = DEMO\nAddress = 10.40.0.10/32\nDNS = 10.10.3.53\n\n[Peer]\nPublicKey = DEMO\nEndpoint = 45.83.21.14:51820', protocol: 'wireguard' })
    if (/^\/clients\/\d+\/qrcode/.test(url)) return response(config, demoQrBlob())
    if (/^\/clients\/\d+$/.test(url) && method === 'get') return response(config, demoClients.find(client => String(client.id) === url.split('/').pop()) || demoClients[0])

    if (url === '/servers') return response(config, { total: 17, items: demoServers, limit: 17, offset: 0 })
    if (/^\/servers\/\d+\/bandwidth$/.test(url)) return response(config, { peer_rates: demoClients.slice(0, 8).map((client, index) => ({ public_key: client.public_key, rx_rate_mbps: 12 + index * 2.4, tx_rate_mbps: 3 + index * 0.8 })) })
    if (/^\/servers\/\d+\/clients$/.test(url)) return response(config, { items: demoClients.slice(0, 12) })
    if (/^\/servers\/\d+\/keypair$/.test(url)) return response(config, { public_key: 'FlirexaDemoPublicKey=', private_key: 'not-present-in-static-demo' })
    if (/^\/servers\/\d+$/.test(url) && method === 'get') return response(config, demoServers.find(server => String(server.id) === url.split('/').pop()) || demoServers[0])

    if (url === '/segments') return response(config, [{ id: 1, name: 'Premium customers', color: '#6366f1', enabled: true, member_count: 1992 }, { id: 2, name: 'Team accounts', color: '#0ea5e9', enabled: true, member_count: 1019 }])
    if (url === '/tariffs') return response(config, tariffs)
    if (url === '/portal-users/stats/revenue') return response(config, revenue)
    if (url === '/portal-users/stats/charts') return response(config, chartData)
    if (url === '/portal-users/tiers') return response(config, tariffs)
    if (url === '/portal-users/payments') return response(config, { total: payments.length, items: payments })
    if (url === '/portal-users/support-messages/unread-count') return response(config, { unread: 1 })
    if (url === '/portal-users/support-messages') return response(config, { items: supportTickets })
    if (/^\/portal-users\/support-messages\/\d+$/.test(url)) return response(config, supportTickets.find(ticket => String(ticket.id) === url.split('/').pop()) || supportTickets[0])
    if (url === '/portal-users') return response(config, { total: 8309, items: portalUsers })
    if (/^\/portal-users\/\d+$/.test(url) && method === 'get') return response(config, portalUsers.find(user => String(user.id) === url.split('/').pop()) || portalUsers[0])

    if (url === '/promo-codes/stats') return response(config, { total: 7, active: 5, redemptions: 1482, discount_total: 4386 })
    if (url === '/promo-codes') return response(config, { items: [{ id: 1, code: 'WELCOME20', discount_percent: 20, max_uses: 500, uses_count: 328, is_active: true, expires_at: new Date(now + 60 * 86_400_000).toISOString() }, { id: 2, code: 'ANNUAL15', discount_percent: 15, max_uses: 1000, uses_count: 611, is_active: true, expires_at: null }] })
    if (url === '/traffic/rules') return response(config, { items: [{ id: 1, name: 'Monthly fair use', period: 'month', threshold_mb: 1_048_576, bandwidth_limit_mbps: 50, enabled: true, affected_clients: 84 }, { id: 2, name: 'Trial allowance', period: 'total', threshold_mb: 30_720, bandwidth_limit_mbps: 10, enabled: true, affected_clients: 19 }] })
    if (url === '/traffic/top') return response(config, { items: demoClients.slice(0, 10).map((client, index) => ({ id: client.id, client_id: client.id, name: client.name, client_name: client.name, server_name: demoServers[client.server_id - 1].name, traffic_bytes: client.traffic_used_rx + client.traffic_used_tx, total_bytes: client.traffic_used_rx + client.traffic_used_tx, rank: index + 1 })) })
    if (url === '/traffic/clients') return response(config, { items: demoClients })

    if (url === '/health/servers') return response(config, { servers: healthServers })
    if (url === '/health/system' || url === '/health/system/refresh') return response(config, { status: 'healthy', summary: { total: 7, healthy: 7, warning: 0, critical: 0 }, components: [{ name: 'API', status: 'healthy', latency_ms: 12 }, { name: 'Database', status: 'healthy', latency_ms: 4 }, { name: 'Client Portal', status: 'healthy', latency_ms: 18 }, { name: 'License validator', status: 'healthy', latency_ms: 31 }] })
    if (url === '/health/issues') return response(config, { active_issues: [], recent_recoveries: [{ id: 1, component: 'Backup storage', message: 'Write verification completed', resolved_at: isoAgo(120) }] })
    if (url === '/health/events') return response(config, { events: logs.map(row => ({ id: row.id, component: row.target_name, status: 'healthy', message: row.action, created_at: row.created_at })) })

    if (url === '/bots/admin/status' || url === '/bots/client/status') return response(config, { running: true, status: 'running', username: url.includes('admin') ? 'flirexa_admin_demo_bot' : 'novashield_customer_demo_bot', uptime_seconds: 864_000, last_update_at: isoAgo(1) })
    if (url === '/bots/config') return response(config, { admin_enabled: true, client_enabled: true, admin_token_set: true, client_token_set: true, admin_chat_id: 'configured', webhook_mode: false })
    if (/^\/bots\/(admin|client)\/logs$/.test(url)) return response(config, { items: logs.slice(0, 5).map(row => ({ ts: row.created_at, level: 'info', msg: row.action, tag: 'demo' })) })

    if (url === '/app-accounts/permissions') return response(config, { permissions: ['clients', 'servers', 'payments', 'support', 'stats', 'bots', 'settings', 'updates', 'backup', 'logs'] })
    if (url === '/app-accounts') return response(config, portalUsers.slice(0, 10).map((user, index) => ({
      id: index + 1,
      username: index === 0 ? 'admin' : user.email,
      email: user.email,
      display_name: user.display_name,
      role: index < 3 ? 'admin' : 'manager',
      is_active: true,
      permissions: index < 3 ? [] : ['clients', 'servers', 'payments', 'support', 'stats'],
      created_at: user.created_at,
      last_login_at: isoAgo(index * 12 + 3),
    })))

    if (url === '/dns-protection') return response(config, { available: true, tier: 'enterprise', settings: { enabled: true, allow_customer_selection: true, enforce_policies: true }, profiles: dnsProfiles, assignments: [{ id: 1, scope_type: 'segment', scope_value: 'Premium customers', profile_id: 4, profile_name: 'Ad, tracker & malware' }], resolution_order: ['device', 'customer', 'segment', 'tariff', 'customer_choice', 'server_default'] })
    if (url === '/plugins/installed') return response(config, { items: [{ name: 'advanced-analytics', version: '1.4.2', enabled: true, description: 'Extended business analytics' }, { name: 'dns-protection', version: '1.0.0', enabled: true, description: 'Per-device resolver policies' }, { name: 'account-balance', version: '1.1.0', enabled: true, description: 'Customer prepaid credit' }] })

    if (url === '/backup/list') return response(config, { backups: Array.from({ length: 7 }, (_, index) => ({
      backup_id: `full-${20260817 - index}`,
      filename: `flirexa-full-${20260817 - index}.tar.zst`,
      timestamp: new Date(now - index * 86_400_000).toISOString(),
      archive_size_bytes: 2_840_000_000 - index * 24_000_000,
      database_dump: true, env_backed_up: true,
      type: 'full', verified: true, status: 'verified',
    })) })
    if (url === '/backup/settings') return response(config, {
      backup_enabled: 'true', backup_interval_hours: '24', backup_hour_utc: '3',
      backup_retention_count: '7', backup_auto_cleanup: 'true',
      backup_storage_type: 'local', backup_path: '/opt/vpnmanager/backups',
      backup_mount_type: 'smb', backup_mount_address: '',
      backup_mount_username: '', backup_mount_password_set: false,
      backup_mount_point: '/mnt/vpnmanager-backup', backup_mount_options: '',
    })
    if (url === '/backup/storage/status') return response(config, {
      storage_type: 'local', ready: true, mounted: true, writable: true,
      target: '/opt/vpnmanager/backups', status: 'ready',
      usage: { total_bytes: 128_000_000_000, used_bytes: 38_600_000_000, percent_used: 30.2 },
    })

    if (url === '/updates/status') return response(config, { current_version: '2.2.100', channel: 'stable', available_update: null, status: 'up_to_date', last_check: isoAgo(2) })
    if (url === '/updates/history') return response(config, { history: [{ id: 11, version: '2.2.100', status: 'success', installed_at: isoAgo(1440), channel: 'stable' }, { id: 10, version: '2.2.99', status: 'success', installed_at: isoAgo(4320), channel: 'stable' }] })
    if (url === '/updates/auto-apply') return response(config, { enabled: false })
    if (url === '/updates/channel') return response(config, { channel: 'stable' })

    if (method !== 'get') return response(config, { ok: true, demo: true, ...body })
    return response(config, {})
  }
}
