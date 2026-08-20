<template>
  <div class="demo-portal-app">
    <nav class="demo-preview-bar" :aria-label="copy.demoNavigation">
      <a :href="demoHomeUrl" class="demo-preview-link demo-preview-back">
        <span aria-hidden="true">←</span>
        <span>{{ copy.allApps }}</span>
      </a>
      <span class="demo-preview-context">
        <span class="demo-preview-dot" aria-hidden="true"></span>
        <span>
          <strong>{{ copy.portal }}</strong>
          <small>{{ copy.safePreview }}</small>
        </span>
      </span>
      <a :href="adminDemoUrl" class="demo-preview-link demo-preview-admin">
        <span>{{ copy.openAdmin }}</span>
        <span aria-hidden="true">→</span>
      </a>
    </nav>

    <router-view v-if="route.meta?.layout === 'auth'" />
    <PortalLayout v-else>
      <router-view />
    </PortalLayout>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import PortalLayout from '../components/Layout.vue'

const { locale } = useI18n()
const route = useRoute()
const labels = {
  en: { demoNavigation: 'Demo navigation', allApps: 'All demos', portal: 'Client Portal', safePreview: 'Interactive preview with synthetic data', openAdmin: 'Admin Panel' },
  ru: { demoNavigation: 'Навигация демо', allApps: 'Все демо', portal: 'Клиентский портал', safePreview: 'Интерактивный просмотр с тестовыми данными', openAdmin: 'Админ-панель' },
  de: { demoNavigation: 'Demo-Navigation', allApps: 'Alle Demos', portal: 'Kundenportal', safePreview: 'Interaktive Vorschau mit Testdaten', openAdmin: 'Admin-Panel' },
  fr: { demoNavigation: 'Navigation de la démo', allApps: 'Toutes les démos', portal: 'Portail client', safePreview: 'Aperçu interactif avec des données fictives', openAdmin: "Panneau d'administration" },
  es: { demoNavigation: 'Navegación de la demo', allApps: 'Todas las demos', portal: 'Portal del cliente', safePreview: 'Vista interactiva con datos de prueba', openAdmin: 'Panel de administración' },
}
const copy = computed(() => labels[locale.value] || labels.en)
const demoHomeUrl = computed(() => `/demo/?lang=${encodeURIComponent(locale.value || 'en')}`)
const adminDemoUrl = computed(() => `/demo-authentic/admin/?lang=${encodeURIComponent(locale.value || 'en')}`)
onMounted(() => {
  const demoLocale = window.__FLIREXA_DEMO_LOCALE__
  if (labels[demoLocale]) locale.value = demoLocale
})
</script>

<style>
.demo-portal-app { min-height: 100vh; }
.demo-preview-bar {
  position: relative;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 48px;
  padding: 7px max(20px, calc((100vw - 1320px) / 2 + 24px));
  border-bottom: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--text-2);
  font-size: 12px;
  font-weight: 500;
}
.demo-preview-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  padding: 0 11px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--bg-elev);
  color: var(--text-2);
  text-decoration: none;
  white-space: nowrap;
  transition: border-color .15s ease, background .15s ease, color .15s ease;
}
.demo-preview-link:hover {
  border-color: var(--border-strong);
  background: var(--bg-hover);
  color: var(--text);
}
.demo-preview-admin {
  border-color: color-mix(in oklab, var(--accent) 34%, var(--border));
  color: var(--accent);
}
.demo-preview-context {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-width: 0;
  text-align: left;
}
.demo-preview-context > span:last-child { display: grid; gap: 1px; }
.demo-preview-context strong { color: var(--text); font-size: 12px; font-weight: 600; }
.demo-preview-context small { color: var(--text-3); font-size: 10px; }
.demo-preview-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
  flex: 0 0 auto;
}
.demo-portal-app .fx-login-theme-toggle { top: 60px; }
@media (max-width: 600px) {
  .demo-preview-bar { min-height: 44px; padding: 6px 12px; gap: 8px; }
  .demo-preview-context { display: none; }
  .demo-preview-link { min-height: 31px; padding: 0 9px; font-size: 11px; }
  .demo-portal-app .fx-login-theme-toggle { top: 56px; }
}
</style>
