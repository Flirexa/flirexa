// Nav model — 1:1 from the designer's NAV_GROUPS + NAV_ICON. His screen keys are
// mapped to our real router paths. Icons are his sprite ids (#ic-<icon>).
const ICON = {
  dashboard: 'grid', online: 'activity', clients: 'users', slots: 'layers', servers: 'server',
  monitoring: 'pulse', health: 'heart', subscriptions: 'card', payments: 'receipt', portal: 'user',
  promo: 'tag', support: 'chat', notifications: 'bell', bots: 'bot', traffic: 'gauge', apps: 'lock',
  plugins: 'box', backup: 'database', updates: 'download', design: 'tag', settings: 'gear',
  logs: 'list', applogs: 'terminal',
}
// his key → { path, label (en fallback) }
const MAP = {
  dashboard: { path: '/', label: 'Dashboard' },
  online: { path: '/online-users', label: 'Online' },
  clients: { path: '/clients', label: 'Clients' },
  slots: { path: '/slots', label: 'Slots' },
  servers: { path: '/servers', label: 'Servers' },
  monitoring: { path: '/server-monitoring', label: 'Monitoring' },
  health: { path: '/health', label: 'Health' },
  subscriptions: { path: '/subscriptions', label: 'Tariffs' },
  payments: { path: '/payments', label: 'Payments' },
  portal: { path: '/portal-users', label: 'Portal Users' },
  promo: { path: '/promo-codes', label: 'Promo Codes' },
  support: { path: '/support-messages', label: 'Support' },
  notifications: { path: '/notifications', label: 'Notifications' },
  bots: { path: '/bots', label: 'Bots' },
  traffic: { path: '/traffic', label: 'Traffic Rules' },
  apps: { path: '/applications', label: 'Applications' },
  plugins: { path: '/plugins', label: 'Plugins' },
  backup: { path: '/backup', label: 'Backup' },
  updates: { path: '/updates', label: 'Updates' },
  design: { path: '/design', label: 'Design' },
  settings: { path: '/settings', label: 'Settings' },
  logs: { path: '/logs', label: 'Audit Log' },
  applogs: { path: '/app-logs', label: 'App Logs' },
}
// his i18n label per group (en fallback + key for i18n `navgrp.<key>`)
const GROUPS = [
  { key: 'overview', label: 'Overview', items: ['dashboard', 'online'] },
  { key: 'clients', label: 'Clients', items: ['clients', 'slots'] },
  { key: 'infrastructure', label: 'Infrastructure', items: ['servers', 'monitoring', 'health'] },
  { key: 'billing', label: 'Billing', items: ['subscriptions', 'payments', 'portal', 'promo'] },
  { key: 'engagement', label: 'Engagement', items: ['support', 'notifications', 'bots', 'traffic'] },
  { key: 'system', label: 'System', items: ['apps', 'plugins', 'backup', 'updates', 'design', 'settings'] },
  { key: 'logs', label: 'Logs', items: ['logs', 'applogs'] },
]

export const NAV_SECTIONS = GROUPS.map(g => ({
  key: g.key,
  label: g.label,
  items: g.items.filter(k => MAP[k]).map(k => ({ key: k, path: MAP[k].path, label: MAP[k].label, icon: ICON[k] || 'box' })),
}))
