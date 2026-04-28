<template>
  <div class="page-content plugins-page">
    <div class="page-header">
      <div>
        <h2 class="mb-1">{{ $t('plugins.title') || 'Plugins' }}</h2>
        <p class="text-muted mb-0">{{ $t('plugins.subtitle') || 'Manage installed plugins and add new ones from a URL.' }}</p>
      </div>
      <button class="btn btn-secondary btn-sm" @click="reload">
        <i class="mdi mdi-refresh"></i> {{ $t('common.refresh') || 'Refresh' }}
      </button>
    </div>

    <!-- Restart banner -->
    <div v-if="restartHint" class="alert alert-warning d-flex align-items-center gap-2 mb-3" role="alert">
      <i class="mdi mdi-alert-circle-outline"></i>
      <div class="flex-grow-1">{{ $t('plugins.restartHint') || 'Plugins were added or removed. Restart the API to apply: `systemctl restart vpnmanager-api`.' }}</div>
      <button class="btn-close" @click="restartHint = false" aria-label="Dismiss"></button>
    </div>

    <!-- Installed plugins -->
    <section class="card-block mb-4">
      <div class="card-block-head">
        <h5 class="mb-0">{{ $t('plugins.installedTitle') || 'Installed plugins' }}</h5>
        <span class="text-muted small">{{ items.length }}</span>
      </div>

      <div v-if="loading" class="p-4 text-center text-muted">
        <i class="mdi mdi-loading mdi-spin"></i>
      </div>

      <div v-else-if="!items.length" class="p-4 text-center text-muted">
        {{ $t('plugins.empty') || 'No plugins installed yet.' }}
      </div>

      <ul v-else class="plugin-list list-unstyled mb-0">
        <li v-for="p in items" :key="p.name" class="plugin-row">
          <div class="plugin-row-main">
            <div class="plugin-row-name">
              <span class="plugin-display-name">{{ p.display_name || p.name }}</span>
              <span v-if="p.version" class="plugin-version">v{{ p.version }}</span>
              <span v-if="p.is_core" class="badge bg-secondary">{{ $t('plugins.core') || 'core' }}</span>
              <span v-else class="badge bg-info">{{ $t('plugins.user') || 'user' }}</span>
            </div>
            <div v-if="p.description" class="plugin-desc">{{ p.description }}</div>
            <div class="plugin-meta">
              <span class="plugin-meta-pair"><i class="mdi mdi-key-outline"></i> {{ p.requires_license_feature || '—' }}</span>
              <span v-if="p.user_installed_from" class="plugin-meta-pair">
                <i class="mdi mdi-link-variant"></i>
                <a :href="p.user_installed_from" target="_blank" rel="noopener">{{ p.user_installed_from }}</a>
              </span>
              <span v-if="p.user_installed_at" class="plugin-meta-pair">
                <i class="mdi mdi-clock-outline"></i> {{ formatDate(p.user_installed_at) }}
              </span>
            </div>
          </div>
          <div class="plugin-row-actions">
            <button
              v-if="!p.is_core"
              class="btn btn-outline-danger btn-sm"
              @click="confirmUninstall(p)"
              :disabled="busy"
            >
              <i class="mdi mdi-delete-outline"></i> {{ $t('plugins.uninstall') || 'Uninstall' }}
            </button>
            <span v-else class="text-muted small" :title="$t('plugins.coreHint') || 'Core plugins are managed by your subscription'">
              {{ $t('plugins.protected') || 'protected' }}
            </span>
          </div>
        </li>
      </ul>
    </section>

    <!-- Install by URL -->
    <section class="card-block">
      <div class="card-block-head">
        <h5 class="mb-0">{{ $t('plugins.installTitle') || 'Install by URL' }}</h5>
      </div>

      <div class="plugin-warn">
        <i class="mdi mdi-shield-alert-outline"></i>
        <div>
          <strong>{{ $t('plugins.warnTitle') || 'Trust the source.' }}</strong>
          {{ $t('plugins.warnBody') || 'A plugin runs as full Python code with the same permissions as the API. Only install plugins from authors and repositories you trust. The SHA-256 below verifies the file you got is the file the author published — it does not vouch for what the code does.' }}
        </div>
      </div>

      <form class="plugin-form" @submit.prevent="install">
        <div class="form-group">
          <label class="form-label">{{ $t('plugins.urlLabel') || 'Tarball URL (https, .tar.gz)' }}</label>
          <input
            type="url"
            class="form-control"
            v-model.trim="form.url"
            placeholder="https://github.com/author/cool-plugin/releases/download/v1.0/plugin.tar.gz"
            required
            :disabled="busy"
          >
        </div>
        <div class="form-group">
          <label class="form-label">{{ $t('plugins.shaLabel') || 'SHA-256' }}</label>
          <input
            type="text"
            class="form-control"
            v-model.trim="form.sha256"
            placeholder="64-character hex"
            pattern="[a-fA-F0-9]{64}"
            minlength="64"
            maxlength="64"
            required
            :disabled="busy"
          >
          <small class="form-text text-muted">{{ $t('plugins.shaHint') || 'Authors usually publish this alongside the release. Required to verify download integrity.' }}</small>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary" :disabled="busy || !canSubmit">
            <i class="mdi mdi-download"></i>
            <span v-if="busy">{{ $t('plugins.installing') || 'Installing…' }}</span>
            <span v-else>{{ $t('plugins.installAction') || 'Download & install' }}</span>
          </button>
        </div>

        <div v-if="lastError" class="alert alert-danger mt-3 mb-0">
          <i class="mdi mdi-alert-octagon-outline"></i> {{ lastError }}
        </div>
        <div v-if="lastSuccess" class="alert alert-success mt-3 mb-0">
          <i class="mdi mdi-check-circle-outline"></i> {{ lastSuccess }}
        </div>
      </form>
    </section>

    <!-- Authoring help -->
    <section class="plugin-help">
      <i class="mdi mdi-book-open-page-variant-outline"></i>
      <div>
        <strong>{{ $t('plugins.helpTitle') || 'Want to write a plugin?' }}</strong>
        {{ $t('plugins.helpBody') || 'See the authoring guide:' }}
        <a href="https://github.com/Flirexa/flirexa/blob/main/docs/plugins.md" target="_blank" rel="noopener">docs/plugins.md</a>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const items = ref([])
const loading = ref(false)
const busy = ref(false)
const restartHint = ref(false)
const lastError = ref('')
const lastSuccess = ref('')

const form = ref({
  url: '',
  sha256: '',
})

const canSubmit = computed(() => {
  return form.value.url.startsWith('https://')
    && (form.value.url.endsWith('.tar.gz') || form.value.url.endsWith('.tgz'))
    && /^[a-fA-F0-9]{64}$/.test(form.value.sha256)
})

async function reload() {
  loading.value = true
  try {
    const { data } = await api.get('/plugins/installed')
    items.value = data
  } catch (e) {
    lastError.value = (e?.response?.data?.detail) || (e?.message) || 'Failed to load plugins'
  } finally {
    loading.value = false
  }
}

async function install() {
  lastError.value = ''
  lastSuccess.value = ''
  busy.value = true
  try {
    const { data } = await api.post('/plugins/install', {
      url: form.value.url,
      sha256: form.value.sha256.toLowerCase(),
    })
    lastSuccess.value = data.message || `${data.display_name || data.name} installed.`
    restartHint.value = true
    form.value.url = ''
    form.value.sha256 = ''
    await reload()
  } catch (e) {
    lastError.value = (e?.response?.data?.detail) || (e?.message) || 'Install failed'
  } finally {
    busy.value = false
  }
}

async function confirmUninstall(p) {
  const ok = window.confirm(
    t('plugins.uninstallConfirm', { name: p.display_name || p.name })
    || `Uninstall ${p.display_name || p.name}? This deletes the plugin's directory.`
  )
  if (!ok) return
  busy.value = true
  lastError.value = ''
  lastSuccess.value = ''
  try {
    const { data } = await api.delete(`/plugins/${encodeURIComponent(p.name)}`)
    lastSuccess.value = data.message || `${p.name} removed.`
    restartHint.value = true
    await reload()
  } catch (e) {
    lastError.value = (e?.response?.data?.detail) || (e?.message) || 'Uninstall failed'
  } finally {
    busy.value = false
  }
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch (e) {
    return iso
  }
}

onMounted(reload)
</script>

<style scoped>
.plugins-page { max-width: 960px; }

.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; gap: 1rem; flex-wrap: wrap; }

.card-block {
  background: var(--vxy-card-bg, #1a1a25);
  border: 1px solid var(--vxy-border, rgba(255,255,255,.08));
  border-radius: 12px;
  overflow: hidden;
}
.card-block-head {
  padding: .9rem 1.1rem;
  border-bottom: 1px solid var(--vxy-border, rgba(255,255,255,.08));
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plugin-list { margin: 0; padding: 0; }
.plugin-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  padding: 1rem 1.1rem;
  border-bottom: 1px solid var(--vxy-border, rgba(255,255,255,.06));
}
.plugin-row:last-child { border-bottom: 0; }
.plugin-row-main { flex-grow: 1; min-width: 0; }
.plugin-row-actions { flex-shrink: 0; }

.plugin-row-name {
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;
  font-weight: 600;
}
.plugin-display-name { color: var(--vxy-text, #e7e9ee); }
.plugin-version { font-size: .8rem; color: var(--vxy-text-muted, #9aa0ad); font-weight: 400; }
.plugin-row-name .badge { font-weight: 500; font-size: .68rem; padding: .2rem .5rem; }

.plugin-desc {
  margin-top: .25rem;
  color: var(--vxy-text-secondary, #c5c8cf);
  font-size: .9rem;
  line-height: 1.5;
}
.plugin-meta {
  margin-top: .5rem;
  display: flex; flex-wrap: wrap; gap: .85rem;
  font-size: .78rem;
  color: var(--vxy-text-muted, #9aa0ad);
}
.plugin-meta-pair { display: inline-flex; align-items: center; gap: .25rem; }
.plugin-meta-pair a { color: var(--vxy-primary, #5e6ee8); word-break: break-all; }

.plugin-warn {
  display: flex;
  gap: .75rem;
  padding: 1rem 1.1rem;
  background: rgba(255, 193, 7, .07);
  border-bottom: 1px solid rgba(255, 193, 7, .25);
  font-size: .88rem;
  line-height: 1.55;
  color: var(--vxy-text-secondary, #c5c8cf);
}
.plugin-warn i { color: #ffc107; font-size: 1.3rem; flex-shrink: 0; }

.plugin-form { padding: 1.25rem 1.1rem; }
.form-group { margin-bottom: 1rem; }
.form-label { font-weight: 500; margin-bottom: .35rem; display: block; }
.form-actions { margin-top: 1rem; }

.plugin-help {
  margin-top: 1.25rem;
  padding: .9rem 1.1rem;
  background: rgba(99, 102, 241, .05);
  border: 1px solid rgba(99, 102, 241, .15);
  border-radius: 10px;
  display: flex;
  gap: .75rem;
  font-size: .9rem;
  color: var(--vxy-text-secondary, #c5c8cf);
}
.plugin-help i { color: var(--vxy-primary, #5e6ee8); font-size: 1.3rem; flex-shrink: 0; }
.plugin-help a { color: var(--vxy-primary, #5e6ee8); }
</style>
