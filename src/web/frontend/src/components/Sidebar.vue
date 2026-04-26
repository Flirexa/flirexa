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
        </router-link>
      </li>
      <li class="sidebar-section-title">{{ $t('nav.management') || 'MANAGEMENT' }}</li>
      <li class="nav-item" v-for="item in mgmtItems" :key="item.path">
        <router-link :to="item.path" class="nav-link" @click="system.closeSidebar()">
          <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi"></i></span>
          <span>{{ $t(`nav.${item.key}`) }}</span>
        </router-link>
      </li>
      <li class="sidebar-section-title">{{ $t('nav.system') || 'SYSTEM' }}</li>
      <li class="nav-item" v-for="item in sysItems" :key="item.path">
        <router-link :to="item.path" class="nav-link" @click="system.closeSidebar()">
          <span class="nav-icon"><i :class="'mdi mdi-' + item.mdi"></i></span>
          <span>{{ $t(`nav.${item.key}`) }}</span>
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
const system = useSystemStore()
const branding = useBrandingStore()
const mainItems = [
  { path: '/',                  mdi: 'view-dashboard-outline',      key: 'dashboard' },
  { path: '/clients',           mdi: 'account-multiple-outline',     key: 'clients' },
  { path: '/servers',           mdi: 'server-network',               key: 'servers' },
]
const mgmtItems = [
  { path: '/portal-users',      mdi: 'account-circle-outline',       key: 'portalUsers' },
  { path: '/subscriptions',     mdi: 'card-account-details-outline', key: 'subscriptions' },
  { path: '/payments',          mdi: 'credit-card-outline',          key: 'payments' },
  { path: '/promo-codes',       mdi: 'ticket-percent-outline',       key: 'promoCodes' },
  { path: '/support-messages',  mdi: 'message-text-outline',         key: 'supportMessages' },
  { path: '/bots',              mdi: 'robot-outline',                key: 'bots' },
  { path: '/applications',      mdi: 'account-key-outline',          key: 'applications' },
  { path: '/traffic',           mdi: 'chart-line',                   key: 'traffic' },
]
const sysItems = [
  { path: '/health',            mdi: 'heart-pulse',                  key: 'systemHealth' },
  { path: '/server-monitoring', mdi: 'monitor-dashboard',            key: 'serverMonitoring' },
  { path: '/backup',            mdi: 'cloud-upload-outline',         key: 'backup' },
  { path: '/updates',           mdi: 'update',                       key: 'updates' },
  { path: '/logs',              mdi: 'text-box-outline',             key: 'logs' },
  { path: '/app-logs',          mdi: 'magnify',                      key: 'appLogs' },
  { path: '/settings',          mdi: 'cog-outline',                  key: 'settings' },
]
</script>

<style scoped>
.sidebar-footer { padding: 1rem 1.5rem; border-top: 1px solid rgba(255,255,255,.07); margin-top: auto; }
.sidebar-version { font-size: .7rem; color: rgba(255,255,255,.3); letter-spacing: .5px; }
</style>
