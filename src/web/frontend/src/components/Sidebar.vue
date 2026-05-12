<template>
  <nav class="sidebar" :class="{ show: system.sidebarOpen, collapsed: system.sidebarCollapsed }">
    <div class="sidebar-brand">
      <img v-if="branding.logoUrl" :src="branding.logoUrl" alt="" />
      <span>{{ branding.appName }}</span>
    </div>
    <ul class="sidebar-nav list-unstyled">
      <li class="sidebar-section-title">{{ $t('nav.main') || 'MAIN' }}</li>
      <li class="nav-item" v-for="item in mainItems" :key="item.path">
        <router-link :to="item.path" class="nav-link" @click="system.closeSidebar()">
          <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi"></i></span>
          <span>{{ $t(`nav.${item.key}`) }}</span>
          <span v-if="tierBadgeFor(item)" class="tier-badge" :class="'tier-badge--' + tierBadgeFor(item).toLowerCase()">{{ tierBadgeFor(item) }}</span>
        </router-link>
      </li>
      <li class="sidebar-section-title">{{ $t('nav.management') || 'MANAGEMENT' }}</li>
      <li class="nav-item" v-for="item in mgmtItems" :key="item.path">
        <router-link :to="item.path" class="nav-link" @click="system.closeSidebar()">
          <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi"></i></span>
          <span>{{ $t(`nav.${item.key}`) }}</span>
          <span v-if="tierBadgeFor(item)" class="tier-badge" :class="'tier-badge--' + tierBadgeFor(item).toLowerCase()">{{ tierBadgeFor(item) }}</span>
        </router-link>
      </li>
      <li class="sidebar-section-title">{{ $t('nav.system') || 'SYSTEM' }}</li>
      <li class="nav-item" v-for="item in sysItems" :key="item.path">
        <router-link :to="item.path" class="nav-link" @click="system.closeSidebar()">
          <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi"></i></span>
          <span>{{ $t(`nav.${item.key}`) }}</span>
          <span v-if="tierBadgeFor(item)" class="tier-badge" :class="'tier-badge--' + tierBadgeFor(item).toLowerCase()">{{ tierBadgeFor(item) }}</span>
        </router-link>
      </li>
    </ul>
    <div class="sidebar-footer">
      <span class="sidebar-version">VPN Management Studio</span>
    </div>
  </nav>
</template>

<script setup>
import { useSystemStore } from '../stores/system'
import { useBrandingStore } from '../stores/branding'
import { useLicenseStore } from '../stores/license'
const system = useSystemStore()
const branding = useBrandingStore()
const license = useLicenseStore()

// Each item that maps to a paid feature carries `feature` and `tier`.
// `tierBadgeFor(item)` returns the tier name ('Pro' / 'Business' /
// 'Enterprise') when the current licence is missing that feature; null
// otherwise. We don't hide the menu item — surfacing it with a small
// upgrade badge is a soft-conversion cue rather than an "you can't see
// this" wall.
function tierBadgeFor(item) {
  if (!item.feature) return null
  if (!license.loaded) return null         // before /system/license resolves, don't render anything
  if (license.has(item.feature)) return null
  return item.tier || 'Pro'
}

const mainItems = [
  { path: '/',                  mdi: 'view-dashboard-outline',      key: 'dashboard' },
  { path: '/online-users',      mdi: 'access-point-network',         key: 'onlineUsers' },
  { path: '/clients',           mdi: 'account-multiple-outline',     key: 'clients' },
  { path: '/servers',           mdi: 'server-network',               key: 'servers' },
]
const mgmtItems = [
  { path: '/portal-users',      mdi: 'account-circle-outline',       key: 'portalUsers' },
  { path: '/subscriptions',     mdi: 'card-account-details-outline', key: 'subscriptions' },
  { path: '/payments',          mdi: 'credit-card-outline',          key: 'payments' },
  { path: '/promo-codes',       mdi: 'ticket-percent-outline',       key: 'promoCodes',      feature: 'promo_codes',  tier: 'Starter' },
  { path: '/support-messages',  mdi: 'message-text-outline',         key: 'supportMessages' },
  { path: '/bots',              mdi: 'robot-outline',                key: 'bots' },
  { path: '/applications',      mdi: 'account-key-outline',          key: 'applications',    feature: 'manager_rbac', tier: 'Enterprise' },
  { path: '/traffic',           mdi: 'chart-line',                   key: 'traffic',         feature: 'traffic_rules', tier: 'Pro' },
]
const sysItems = [
  { path: '/health',            mdi: 'heart-pulse',                  key: 'systemHealth' },
  { path: '/server-monitoring', mdi: 'monitor-dashboard',            key: 'serverMonitoring' },
  { path: '/backup',            mdi: 'cloud-upload-outline',         key: 'backup',          feature: 'auto_backup',   tier: 'Pro' },
  { path: '/updates',           mdi: 'update',                       key: 'updates' },
  { path: '/plugins',           mdi: 'puzzle-outline',               key: 'plugins' },
  { path: '/logs',              mdi: 'text-box-outline',             key: 'logs' },
  { path: '/app-logs',          mdi: 'magnify',                      key: 'appLogs' },
  { path: '/settings',          mdi: 'cog-outline',                  key: 'settings' },
]
</script>

<style scoped>
.sidebar-footer { padding: 1rem 1.5rem; border-top: 1px solid rgba(255,255,255,.07); margin-top: auto; }
.sidebar-version { font-size: .7rem; color: rgba(255,255,255,.3); letter-spacing: .5px; }
.tier-badge {
  margin-left: auto;
  font-size: 0.62rem;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.03em;
  font-weight: 600;
  text-transform: uppercase;
  line-height: 1;
}
.tier-badge--starter   { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.tier-badge--pro       { background: rgba(167, 139, 250, 0.18); color: #c4b5fd; }
.tier-badge--business  { background: rgba(245, 158, 11, 0.18); color: #fbbf24; }
.tier-badge--enterprise{ background: rgba(244, 114, 182, 0.18); color: #f9a8d4; }
.nav-link { display: flex; align-items: center; gap: 0.5rem; }
</style>
