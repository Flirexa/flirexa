import { createRouter, createWebHashHistory } from 'vue-router'
import { D2_SCREENS } from '../design2/screens/registry.js'

const routes = [
  ['/', 'Dashboard', D2_SCREENS.Dashboard],
  ['/online-users', 'OnlineUsers', D2_SCREENS.OnlineUsers],
  ['/clients', 'Clients', D2_SCREENS.Clients],
  ['/slots', 'Slots', D2_SCREENS.Slots],
  ['/servers', 'Servers', D2_SCREENS.Servers],
  ['/server-monitoring', 'ServerMonitoring', D2_SCREENS.ServerMonitoring],
  ['/system-health', 'SystemHealth', D2_SCREENS.SystemHealth],
  ['/subscriptions', 'Subscriptions', D2_SCREENS.Subscriptions],
  ['/payments', 'Payments', D2_SCREENS.Payments],
  ['/portal-users', 'PortalUsers', D2_SCREENS.PortalUsers],
  ['/promo-codes', 'PromoCodes', D2_SCREENS.PromoCodes],
  ['/support-messages', 'SupportMessages', D2_SCREENS.SupportMessages],
  ['/notifications', 'Notifications', D2_SCREENS.Notifications],
  ['/bots', 'Bots', D2_SCREENS.Bots],
  ['/traffic', 'TrafficRules', D2_SCREENS.TrafficRules],
  ['/applications', 'Applications', D2_SCREENS.Applications],
  ['/dns-protection', 'DnsProtection', D2_SCREENS.DnsProtection],
  ['/plugins', 'Plugins', D2_SCREENS.Plugins],
  ['/backup', 'Backup', D2_SCREENS.Backup],
  ['/updates', 'Updates', D2_SCREENS.Updates],
  ['/settings', 'Settings', D2_SCREENS.Settings],
  ['/logs', 'Logs', D2_SCREENS.Logs],
  ['/app-logs', 'AppLogs', D2_SCREENS.AppLogs],
].map(([path, name, component]) => ({ path, name, component }))

routes.push({ path: '/:pathMatch(.*)*', redirect: '/' })

export default createRouter({ history: createWebHashHistory(), routes })
