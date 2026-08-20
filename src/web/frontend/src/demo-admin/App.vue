<template>
  <D2App />
  <nav class="demo-switcher" :aria-label="copy.navigation">
    <a :href="demoHomeUrl" class="demo-switcher-home" :title="copy.allApps" :aria-label="copy.allApps">←</a>
    <span>{{ copy.admin }}</span>
    <a :href="portalDemoUrl">{{ copy.openPortal }} →</a>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import D2App from '../design2/D2App.vue'
import i18n from '../i18n'

const locale = i18n.global.locale
const labels = {
  en: { navigation: 'Demo navigation', allApps: 'All demos', admin: 'Admin Panel', openPortal: 'Open Client Portal' },
  ru: { navigation: 'Навигация демо', allApps: 'Все демо', admin: 'Админ-панель', openPortal: 'Открыть клиентский портал' },
  de: { navigation: 'Demo-Navigation', allApps: 'Alle Demos', admin: 'Admin-Panel', openPortal: 'Kundenportal öffnen' },
  fr: { navigation: 'Navigation de la démo', allApps: 'Toutes les démos', admin: "Panneau d'administration", openPortal: 'Ouvrir le portail client' },
  es: { navigation: 'Navegación de la demo', allApps: 'Todas las demos', admin: 'Panel de administración', openPortal: 'Abrir el portal del cliente' },
}
const copy = computed(() => labels[locale.value] || labels.en)
const demoHomeUrl = computed(() => `/demo/?lang=${encodeURIComponent(locale.value || 'en')}`)
const portalDemoUrl = computed(() => `/demo-authentic/portal/?lang=${encodeURIComponent(locale.value || 'en')}#/login`)
</script>

<style>
.demo-switcher {
  position: fixed;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  z-index: 9990;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  background: color-mix(in srgb, var(--panel) 96%, transparent);
  box-shadow: 0 12px 34px rgba(15, 23, 42, .18);
  color: var(--text-2);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  backdrop-filter: blur(14px);
}
.demo-switcher > span { padding: 0 9px; color: var(--text-3); }
.demo-switcher a {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  border-radius: 8px;
  color: #fff;
  background: var(--accent);
  text-decoration: none;
}
.demo-switcher a:hover { background: var(--accent-2); color: #fff; }
.demo-switcher .demo-switcher-home { width: 32px; padding: 0; color: var(--text-2); background: var(--panel-2); }
.demo-switcher .demo-switcher-home:hover { color: var(--text); background: var(--panel-3); }
@media (max-width: 600px) {
  .demo-switcher { bottom: 9px; max-width: calc(100vw - 18px); font-size: 11px; }
  .demo-switcher > span { display: none; }
}
</style>
