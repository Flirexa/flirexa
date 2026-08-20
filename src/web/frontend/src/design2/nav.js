// Nav model — 1:1 from the designer's NAV_GROUPS + NAV_ICON. His screen keys are
// mapped to our real router paths. Icons are his sprite ids (#ic-<icon>).
const ICON = {
  dashboard: 'grid', online: 'activity', clients: 'users', slots: 'layers', servers: 'server',
  monitoring: 'pulse', health: 'heart', subscriptions: 'card', payments: 'receipt', portal: 'user',
  promo: 'tag', support: 'chat', notifications: 'bell', bots: 'bot', traffic: 'gauge', apps: 'lock',
  plugins: 'box', backup: 'database', updates: 'download', settings: 'gear', dns: 'lock',
  logs: 'list', applogs: 'terminal',
}
// his key → { path, label (en fallback) }
const MAP = {
  dashboard: { path: '/', label: 'Dashboard', permissions: ['stats'] },
  online: { path: '/online-users', label: 'Online', permissions: ['clients', 'servers'] },
  clients: { path: '/clients', label: 'Clients', permissions: ['clients'] },
  slots: { path: '/slots', label: 'Slots', permissions: ['clients'] },
  servers: { path: '/servers', label: 'Servers', permissions: ['servers'] },
  monitoring: { path: '/server-monitoring', label: 'Monitoring', permissions: ['servers'] },
  health: { path: '/system-health', label: 'Health', permissions: ['stats'] },
  subscriptions: { path: '/subscriptions', label: 'Tariffs', permissions: ['payments'] },
  payments: { path: '/payments', label: 'Payments', permissions: ['payments'] },
  portal: { path: '/portal-users', label: 'Portal Users', permissions: ['clients'] },
  promo: { path: '/promo-codes', label: 'Promo Codes', permissions: ['payments'] },
  support: { path: '/support-messages', label: 'Support', permissions: ['support'] },
  notifications: { path: '/notifications', label: 'Notifications', permissions: ['settings'] },
  bots: { path: '/bots', label: 'Bots', permissions: ['bots'] },
  traffic: { path: '/traffic', label: 'Traffic Rules', permissions: ['settings'] },
  apps: { path: '/applications', label: 'Applications', ownerOnly: true },
  plugins: { path: '/plugins', label: 'Plugins', ownerOnly: true },
  backup: { path: '/backup', label: 'Backup', permissions: ['backup'] },
  updates: { path: '/updates', label: 'Updates', permissions: ['updates'] },
  settings: { path: '/settings', label: 'Settings', permissions: ['settings'] },
  dns: { path: '/dns-protection', label: 'DNS Protection', permissions: ['settings'] },
  logs: { path: '/logs', label: 'Audit Log', permissions: ['logs'] },
  applogs: { path: '/app-logs', label: 'App Logs', permissions: ['logs'] },
}
// his i18n label per group (en fallback + key for i18n `navgrp.<key>`)
const GROUPS = [
  { key: 'overview', label: 'Overview', items: ['dashboard', 'online'] },
  { key: 'clients', label: 'Clients', items: ['clients', 'slots'] },
  { key: 'infrastructure', label: 'Infrastructure', items: ['servers', 'monitoring', 'health'] },
  { key: 'billing', label: 'Billing', items: ['subscriptions', 'payments', 'portal', 'promo'] },
  { key: 'engagement', label: 'Engagement', items: ['support', 'notifications', 'bots', 'traffic'] },
  { key: 'system', label: 'System', items: ['apps', 'dns', 'plugins', 'backup', 'updates', 'settings'] },
  { key: 'logs', label: 'Logs', items: ['logs', 'applogs'] },
]

export const NAV_SECTIONS = GROUPS.map(g => ({
  key: g.key,
  label: g.label,
  items: g.items.filter(k => MAP[k]).map(k => ({ key: k, ...MAP[k], icon: ICON[k] || 'box' })),
}))
