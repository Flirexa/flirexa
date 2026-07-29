<template>
  <div class="fx-legal-shell">
    <header class="fx-legal-header">
      <router-link to="/" class="fx-legal-brand">
        <img :src="brandLogo" alt="" />
        <span v-if="brandName">{{ brandName }}</span>
        <span class="fx-badge fx-badge-neutral">VPN</span>
      </router-link>
      <div class="fx-legal-actions">
        <button class="fx-icon-btn" @click="toggleTheme" :title="$t(theme === 'dark' ? 'nav.lightMode' : 'nav.darkMode')">
          <FxIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </button>
        <router-link to="/" class="fx-btn fx-btn-secondary fx-btn-sm">
          <FxIcon name="chevronLeft" :size="14" /> {{ $t('legal.backToPortal') }}
        </router-link>
      </div>
    </header>

    <main class="fx-legal-main">
      <article class="fx-card fx-legal-card">
        <div class="fx-legal-icon"><FxIcon name="book" :size="22" /></div>
        <h1>{{ title }}</h1>
        <div v-if="body" class="fx-legal-body">{{ body }}</div>
        <div v-else class="fx-legal-empty">
          <FxIcon name="info" :size="20" />
          <span>{{ $t('legal.notPublished') }}</span>
        </div>
      </article>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FxIcon from '../components/FxIcon.vue'
import bundledLogo from '../assets/flirexa-logo.png'

const props = defineProps({
  kind: { type: String, required: true, validator: value => ['privacy', 'terms'].includes(value) },
})
const { t } = useI18n()

const brandName = computed(() => String(window.__branding?.branding_customer_app_name || '').trim())
const brandLogo = computed(() => window.__branding?.branding_customer_logo_url
  || window.__branding?.branding_logo_url
  || bundledLogo)
const title = computed(() => props.kind === 'privacy'
  ? t('legal.privacyTitle')
  : t('legal.termsTitle'))
const body = computed(() => String(
  window.__branding?.[`branding_${props.kind}_text`] || '',
).trim())

const theme = ref(localStorage.getItem('sb_theme') === 'dark' ? 'dark' : 'light')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('sb_theme', theme.value)
  window.dispatchEvent(new CustomEvent('fx:theme', { detail: theme.value }))
}
</script>

<style scoped>
.fx-legal-shell {
  min-height: 100vh;
  background:
    radial-gradient(55% 45% at 10% 10%, color-mix(in oklab, var(--accent) 15%, transparent), transparent 68%),
    var(--bg);
}
.fx-legal-header {
  min-height: 60px;
  padding: 10px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--border);
  background: var(--header-bg);
  backdrop-filter: blur(14px);
}
.fx-legal-brand { display:flex;align-items:center;gap:10px;color:var(--text);text-decoration:none;font-size:14px;font-weight:650;min-width:0; }
.fx-legal-brand img { width:32px;height:32px;object-fit:contain; }
.fx-legal-brand > span:not(.fx-badge) { white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px; }
.fx-legal-actions { display:flex;align-items:center;gap:8px;flex-shrink:0; }
.fx-legal-main { width:min(900px,100%);margin:0 auto;padding:48px 24px 80px; }
.fx-legal-card { padding:clamp(24px,5vw,52px); }
.fx-legal-icon { width:46px;height:46px;border-radius:13px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);margin-bottom:20px; }
.fx-legal-card h1 { margin:0 0 28px;color:var(--text);font-size:clamp(26px,4vw,38px);letter-spacing:-.03em; }
.fx-legal-body { color:var(--text-2);font-size:14px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere; }
.fx-legal-empty { display:flex;align-items:center;gap:10px;padding:16px;border:1px solid var(--border);border-radius:var(--r-md);background:var(--bg-subtle);color:var(--text-3);font-size:13px; }
@media (max-width:640px) {
  .fx-legal-header { padding:10px 14px; }
  .fx-legal-brand > span:not(.fx-badge) { display:none; }
  .fx-legal-main { padding:24px 14px 56px; }
  .fx-legal-card { padding:22px 18px; }
  .fx-legal-actions .fx-btn { padding:0 10px; }
}
</style>
