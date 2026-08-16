// Registry of active screens, keyed by vue-router route name. The router uses
// these components directly. These are the full screens built from the designer's
// pixel reference `VPN Admin Panel.dc.html` (all charts / gauges / map / widgets),
// audited per-section for fidelity. NOTE: the designer's later `vue-handoff/`
// SFCs (in ./handoff/) are a stripped-down simplification — deliberately NOT
// used; these D2* screens are the complete ones.
import D2Dashboard from './D2Dashboard.vue'
import D2Clients from './D2Clients.vue'
import D2Servers from './D2Servers.vue'
import D2Subscriptions from './D2Subscriptions.vue'
import D2PortalUsers from './D2PortalUsers.vue'
import D2Applications from './D2Applications.vue'
import D2Payments from './D2Payments.vue'
import D2Slots from './D2Slots.vue'
import D2Bots from './D2Bots.vue'
import D2OnlineUsers from './D2OnlineUsers.vue'
import D2Notifications from './D2Notifications.vue'
import D2Backup from './D2Backup.vue'
import D2PromoCodes from './D2PromoCodes.vue'
import D2SystemHealth from './D2SystemHealth.vue'
import D2ServerMonitoring from './D2ServerMonitoring.vue'
import D2Updates from './D2Updates.vue'
import D2Activation from './D2Activation.vue'
import D2Plugins from './D2Plugins.vue'
import D2Logs from './D2Logs.vue'
import D2AppLogs from './D2AppLogs.vue'
import D2Support from './D2Support.vue'
import D2TrafficRules from './D2TrafficRules.vue'
import D2Settings from './D2Settings.vue'
import D2DnsProtection from './D2DnsProtection.vue'

export const D2_SCREENS = {
  Dashboard: D2Dashboard,
  Clients: D2Clients,
  Servers: D2Servers,
  Subscriptions: D2Subscriptions,
  PortalUsers: D2PortalUsers,
  Applications: D2Applications,
  Payments: D2Payments,
  Slots: D2Slots,
  Bots: D2Bots,
  OnlineUsers: D2OnlineUsers,
  Notifications: D2Notifications,
  Backup: D2Backup,
  PromoCodes: D2PromoCodes,
  SystemHealth: D2SystemHealth,
  ServerMonitoring: D2ServerMonitoring,
  Updates: D2Updates,
  Activation: D2Activation,
  Plugins: D2Plugins,
  Logs: D2Logs,
  AppLogs: D2AppLogs,
  SupportMessages: D2Support,
  TrafficRules: D2TrafficRules,
  Settings: D2Settings,
  DnsProtection: D2DnsProtection,
}
