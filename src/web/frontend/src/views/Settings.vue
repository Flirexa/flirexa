<template>
  <div class="settings-page">
    <!-- License -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.license') }}</h4>

    <!-- Revocation banner (highest priority) -->
    <div v-if="licServer.online_status === 'revoked'" class="alert alert-danger d-flex align-items-start mb-3">
      <span class="me-2" style="font-size:1.2em"><i class="mdi mdi-cancel text-danger"></i></span>
      <div>
        <strong>{{ $t('settings.licenseRevoked') }}</strong> — {{ $t('settings.revokedMessage') }}
        <span v-if="brand.support_email || brand.support_url">
          <a :href="brand.support_email ? 'mailto:' + brand.support_email : brand.support_url" class="alert-link ms-1">{{ $t('settings.contactSupport') }}</a>
        </span>
      </div>
    </div>

    <!-- Trial banner -->
    <div v-else-if="license.type === 'trial'" class="alert alert-warning mb-3 settings-inline-alert">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <div>
          <strong>{{ $t('settings.trialMode') }}</strong> —
          <span v-if="license.days_remaining !== null && license.days_remaining > 0">
            {{ $t('settings.daysRemaining', { n: license.days_remaining }) }}
          </span>
          <span v-else-if="license.days_remaining === 0" class="text-danger fw-bold"> {{ $t('settings.trialExpiredToday') }}</span>
          <span v-else> {{ $t('settings.unlimitedTrial') }}</span>
        </div>
        <a href="https://example.com/#pricing" target="_blank" class="btn btn-warning btn-sm ms-3 text-nowrap fw-bold">
          {{ $t('settings.buyLicense') || 'Buy License' }}
        </a>
      </div>
      <div class="small">
        {{ $t('settings.trialLimited', { clients: license.max_clients, servers: license.max_servers }) }}
        {{ $t('settings.trialProtoLimit') || 'Trial supports WireGuard only. Purchase a license to unlock AmneziaWG, Hysteria2, TUIC and more features.' }}
      </div>
    </div>

    <!-- Expiring soon warning -->
    <div v-else-if="license.days_remaining !== null && license.days_remaining <= 7 && license.days_remaining > 0 && !license.grace_period"
         class="alert alert-warning d-flex justify-content-between align-items-center mb-3 settings-inline-alert">
      <div>
        <strong>{{ $t('settings.licenseExpiring') }}</strong> — {{ $t('settings.daysRemaining', { n: license.days_remaining }) }}
        {{ $t('settings.renewBefore') }}
      </div>
      <a v-if="brand.support_email || brand.support_url"
         :href="brand.support_email ? 'mailto:' + brand.support_email : brand.support_url"
         class="btn btn-warning btn-sm ms-3 text-nowrap">{{ $t('settings.renewBtn') }}</a>
    </div>

    <div class="card mb-4" :class="licServer.online_status === 'revoked' ? 'border-danger' : license.type === 'trial' ? 'border-warning' : 'border-success'">
      <div class="card-body">
        <div class="row g-3 mb-3 license-stats-grid">
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 text-center" style="border-color: var(--vxy-border) !important;">
              <div class="fw-bold text-uppercase" :class="license.type === 'trial' ? 'text-warning' : 'text-success'">{{ license.type || 'unknown' }}</div>
              <div class="text-muted small">{{ $t('settings.licenseTier') }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 text-center" style="border-color: var(--vxy-border) !important;">
              <div class="fw-bold">{{ license.max_clients }}</div>
              <div class="text-muted small">{{ $t('settings.maxClients') }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 text-center" style="border-color: var(--vxy-border) !important;">
              <div class="fw-bold">{{ license.max_servers }}</div>
              <div class="text-muted small">{{ $t('settings.maxServers') }}</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="border rounded p-3 text-center" style="border-color: var(--vxy-border) !important;">
              <div class="fw-bold" :class="license.days_remaining != null && license.days_remaining <= 7 ? 'text-danger' : ''">
                {{ license.days_remaining != null ? license.days_remaining + 'd' : $t('settings.permanent') }}
              </div>
              <div class="text-muted small">{{ $t('settings.expires') }}</div>
            </div>
          </div>
        </div>
        <div v-if="license.grace_period" class="alert alert-danger py-2 small mb-3">
          <strong>{{ $t('settings.gracePeriodActive') }}</strong> — {{ $t('settings.gracePeriodMessage', { date: graceEndDate }) }}
        </div>
        <div v-if="license.features && license.features.length" class="mb-3">
          <small class="text-muted">{{ $t('settings.features') }}:</small>
          <span v-for="f in license.features" :key="f" class="badge badge-soft-secondary me-1">{{ f }}</span>
        </div>

        <!-- Usage bars (only for paid tiers) -->
        <div v-if="license.type !== 'trial' && license.max_clients > 0" class="mb-3">
          <div class="d-flex justify-content-between mb-1">
            <small class="text-muted">{{ $t('settings.clientsInUse') }}</small>
            <small :class="clientUsagePct >= 90 ? 'text-danger fw-bold' : clientUsagePct >= 70 ? 'text-warning' : 'text-muted'">
              {{ license.current_clients }} / {{ license.max_clients === 999999 ? '∞' : license.max_clients }}
            </small>
          </div>
          <div class="progress mb-2" style="height:5px">
            <div class="progress-bar" :class="clientUsagePct >= 90 ? 'bg-danger' : clientUsagePct >= 70 ? 'bg-warning' : 'bg-success'"
                 :style="{width: Math.min(100, clientUsagePct) + '%'}"></div>
          </div>
          <div class="d-flex justify-content-between mb-1">
            <small class="text-muted">Servers</small>
            <small :class="serverUsagePct >= 90 ? 'text-danger fw-bold' : 'text-muted'">
              {{ license.current_servers }} / {{ license.max_servers === 999999 ? '∞' : license.max_servers }}
            </small>
          </div>
          <div class="progress" style="height:5px">
            <div class="progress-bar" :class="serverUsagePct >= 90 ? 'bg-danger' : 'bg-success'"
                 :style="{width: Math.min(100, serverUsagePct) + '%'}"></div>
          </div>
        </div>

        <!-- Buy License CTA for trial users -->
        <div v-if="license.type === 'trial'" class="mb-3 p-3 rounded" style="background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(168,85,247,.08));border:1px solid rgba(99,102,241,.25)">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <strong style="color:var(--vxy-primary)">{{ $t('settings.upgradeTitle') || 'Upgrade to Full Version' }}</strong>
              <p class="small text-muted mb-0 mt-1">{{ $t('settings.upgradeDesc') || 'Unlock all 4 protocols, more clients, multi-server, client portal and more.' }}</p>
            </div>
            <a href="https://example.com/#pricing" target="_blank" class="btn btn-primary btn-sm ms-3 text-nowrap">
              {{ $t('settings.viewPlans') || 'View Plans' }}
            </a>
          </div>
        </div>

        <div class="mb-3">
          <label class="form-label">{{ $t('settings.activateKey') }}</label>
          <div class="input-group settings-stack-input-group">
            <input type="text" class="form-control" v-model="license.newKey" :placeholder="$t('settings.keyPlaceholder')" />
            <button class="btn btn-primary" @click="activateLicense" :disabled="saving || !license.newKey">
              {{ saving ? $t('settings.saving') : $t('settings.activate') }}
            </button>
          </div>
          <div class="form-text">{{ $t('settings.upgradeHint') }}</div>
        </div>

        <div class="mb-3">
          <label class="form-label">{{ $t('settings.refetchLicense') || 'Re-fetch License' }}</label>
          <div class="input-group settings-stack-input-group">
            <input type="text" class="form-control" v-model="license.replayCode"
                   placeholder="XXXX-XXXX-XXXX-XXXX" />
            <button class="btn btn-outline-primary" @click="replayLicense"
                    :disabled="replaying || !license.replayCode">
              {{ replaying ? ($t('settings.fetching') || 'Fetching…') : ($t('settings.refetch') || 'Re-fetch') }}
            </button>
          </div>
          <div class="form-text">
            {{ $t('settings.refetchHint') || 'Already activated but lost your license key? Enter the activation code from the original purchase to re-fetch the same key. Hardware-bound — only works from this machine.' }}
          </div>
        </div>

        <!-- Apply transfer code (lifetime_protected, on the NEW server) -->
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.transferApply.label') }}</label>
          <div class="input-group settings-stack-input-group">
            <input type="text" class="form-control font-monospace"
                   v-model="transferApplyCode"
                   placeholder="MIGRATE-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX-XXXXXXXXXX" />
            <button class="btn btn-outline-warning"
                    @click="applyTransferCode"
                    :disabled="applyingTransfer || !transferApplyCode">
              <span v-if="applyingTransfer" class="spinner-border spinner-border-sm me-2"></span>
              {{ $t('settings.transferApply.button') }}
            </button>
          </div>
          <div class="form-text">{{ $t('settings.transferApply.hint') }}</div>
          <div v-if="transferApplyAlert" class="alert mt-2 py-2 small" :class="transferApplyAlertType">{{ transferApplyAlert }}</div>
        </div>
        <div class="small text-muted mb-1 settings-copy-row">
          {{ $t('settings.serverId') }}: <code>{{ license.server_id }}</code>
          <button class="btn btn-outline-secondary btn-sm ms-2 py-0 px-1" style="font-size:0.7rem"
                  @click="copyToClipboard(license.server_id)" title="Copy"><i class="mdi mdi-content-copy"></i></button>
        </div>
        <div v-if="license.activation_code_masked" class="small text-muted mb-2">
          {{ $t('settings.activationCode') }}: <code>{{ license.activation_code_masked }}</code>
        </div>

        <!-- Owner card (only shown when payload carries owner info — 1.5.64+ keys) -->
        <div v-if="license.owner_name || license.owner_email" class="border rounded p-2 mb-2 small">
          <div class="text-muted text-uppercase fw-semibold mb-1" style="font-size:0.7rem;letter-spacing:0.04em">
            {{ $t('settings.licenseOwner') }}
          </div>
          <div v-if="license.owner_name"><i class="mdi mdi-account me-1"></i>{{ license.owner_name }}</div>
          <div v-if="license.owner_email" class="text-muted"><i class="mdi mdi-email-outline me-1"></i>{{ license.owner_email }}</div>
        </div>

        <!-- Lifetime-protected: self-service server transfer -->
        <div v-if="license.enforcement === 'lifetime_protected'" class="border rounded p-3 mb-2"
             :class="license.migration_pending ? 'border-warning' : 'border-info-subtle'">
          <div class="d-flex align-items-center justify-content-between mb-2 flex-wrap gap-2">
            <div>
              <div class="fw-semibold">
                <i class="mdi mdi-server-network me-1"></i>{{ $t('settings.migration.title') }}
              </div>
              <div class="text-muted small">{{ $t('settings.migration.subtitle') }}</div>
            </div>
            <button v-if="!license.migration_pending"
                    class="btn btn-outline-warning btn-sm"
                    @click="openMigrationModal">
              <i class="mdi mdi-export me-1"></i>{{ $t('settings.migration.button') }}
            </button>
          </div>

          <!-- Active migration countdown -->
          <div v-if="license.migration_pending" class="alert alert-warning mb-0 py-2">
            <div class="d-flex align-items-start justify-content-between flex-wrap gap-2">
              <div>
                <strong>{{ $t('settings.migration.pendingTitle') }}</strong><br/>
                <span v-if="!license.migration_pending.decommissioned">
                  {{ $t('settings.migration.decommissionsIn',
                       { time: humanizeSeconds(license.migration_pending.decommission_seconds) }) }}
                </span>
                <span v-else class="text-danger fw-bold">
                  {{ $t('settings.migration.decommissioned') }}
                </span>
              </div>
              <button class="btn btn-sm btn-outline-secondary" @click="cancelMigration">
                {{ $t('settings.migration.cancel') }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="license.alert" class="alert py-2 small" :class="license.alertType">{{ license.alert }}</div>
      </div>
    </div>

    <!-- Migration code modal -->
    <div v-if="migration.modalOpen" class="modal fade show d-block" style="background:rgba(0,0,0,0.5)" @click.self="closeMigrationModal">
      <div class="modal-dialog modal-dialog-centered modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="mdi mdi-server-network me-2"></i>{{ $t('settings.migration.modalTitle') }}
            </h5>
            <button type="button" class="btn-close" @click="closeMigrationModal"></button>
          </div>
          <div class="modal-body">
            <!-- Step 1: warning -->
            <div v-if="!migration.code">
              <div class="alert alert-warning small">
                <strong>{{ $t('settings.migration.warningTitle') }}</strong>
                <ul class="mb-0 mt-1">
                  <li>{{ $t('settings.migration.warning1') }}</li>
                  <li>{{ $t('settings.migration.warning2') }}</li>
                  <li>{{ $t('settings.migration.warning3') }}</li>
                </ul>
              </div>
              <div class="d-flex gap-2 justify-content-end">
                <button class="btn btn-secondary" @click="closeMigrationModal">{{ $t('common.cancel') }}</button>
                <button class="btn btn-warning" :disabled="migration.generating" @click="generateMigration">
                  <span v-if="migration.generating" class="spinner-border spinner-border-sm me-2"></span>
                  {{ $t('settings.migration.generate') }}
                </button>
              </div>
            </div>
            <!-- Step 2: show code -->
            <div v-else>
              <div class="alert alert-success small mb-3">
                <strong>{{ $t('settings.migration.successTitle') }}</strong><br/>
                {{ $t('settings.migration.successHint',
                     { codeDays: 7, decommissionDays: migration.this_server_decommissions_in_days || 3 }) }}
              </div>

              <label class="form-label fw-semibold">{{ $t('settings.migration.codeLabel') }}</label>
              <div class="input-group mb-3">
                <input type="text" class="form-control font-monospace" :value="migration.code" readonly
                       style="font-size:0.95rem;letter-spacing:0.02em"/>
                <button class="btn btn-primary" @click="copyToClipboard(migration.code)">
                  <i class="mdi mdi-content-copy"></i> {{ $t('common.copy') || 'Copy' }}
                </button>
              </div>

              <div class="card bg-body-tertiary">
                <div class="card-body p-3">
                  <div class="fw-semibold small text-uppercase text-muted mb-2"
                       style="letter-spacing:0.04em;font-size:0.7rem">
                    {{ $t('settings.migration.nextSteps') }}
                  </div>
                  <ol class="small mb-0 ps-3">
                    <li>{{ $t('settings.migration.step1') }}</li>
                    <li>{{ $t('settings.migration.step2') }}</li>
                    <li>{{ $t('settings.migration.step3') }}</li>
                    <li>{{ $t('settings.migration.step4') }}</li>
                  </ol>
                </div>
              </div>

              <div class="d-flex justify-content-end mt-3">
                <button class="btn btn-primary" @click="closeMigrationModal">{{ $t('common.close') }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- License Server Status -->
    <div class="card mb-4">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3 settings-card-header">
          <strong>{{ $t('settings.licenseServer') }}</strong>
          <div class="d-flex gap-2 settings-actions settings-actions--compact">
            <span class="badge" :class="licServer.server_reachable ? 'bg-success' : 'bg-secondary'">
              {{ licServer.server_reachable ? $t('settings.reachable') : $t('settings.unreachable') }}
            </span>
            <button class="btn btn-outline-primary btn-sm" @click="refreshLicenseCheck" :disabled="licServer.refreshing">
              {{ licServer.refreshing ? $t('common.loading') : $t('settings.refreshNow') }}
            </button>
          </div>
        </div>
        <div class="row g-2 mb-3">
          <div class="col-md-6">
            <div class="border rounded p-2">
              <div class="small text-muted">{{ $t('settings.primaryServer') }}</div>
              <code class="small">{{ licServer.primary_url || '—' }}</code>
            </div>
          </div>
          <div class="col-md-6">
            <div class="border rounded p-2">
              <div class="small text-muted">{{ $t('settings.backupServer') }}</div>
              <code class="small">{{ licServer.backup_url || '—' }}</code>
            </div>
          </div>
        </div>
        <div v-if="licServer.last_check" class="small text-muted mb-3">
          {{ $t('settings.lastCheck') }}: {{ new Date(licServer.last_check).toLocaleString() }}
          <span v-if="licServer.online_status" class="ms-2 badge settings-status-badge">{{ licServer.online_status }}</span>
        </div>

        <!-- Migration Code -->
        <div>
          <button class="btn btn-outline-secondary btn-sm" @click="licServer.showMigration = !licServer.showMigration">
            {{ licServer.showMigration ? $t('common.hide') : $t('settings.migrationCode') }}
          </button>
          <div v-if="licServer.showMigration" class="mt-3">
            <p class="small text-muted">
              {{ $t('settings.migrationDesc') }}
            </p>
            <textarea class="form-control font-monospace mb-2" rows="4"
              v-model="licServer.migrationCode" placeholder='{"payload":"...","signature":"..."}'
              :disabled="licServer.migrating" style="font-size:0.78rem;" />
            <button class="btn btn-warning btn-sm" @click="applyMigration" :disabled="licServer.migrating || !licServer.migrationCode.trim()">
              {{ licServer.migrating ? $t('settings.applying') : $t('settings.applyMigration') }}
            </button>
            <div v-if="licServer.migrationAlert" class="alert mt-2 py-2 small" :class="licServer.migrationAlertType">
              {{ licServer.migrationAlert }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.paymentProviders') }}</h4>

    <!-- Payment Modules Button -->
    <div class="card mb-4">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <strong>{{ $t('settings.paymentModules') || 'Payment Modules' }}</strong>
          <p class="text-muted small mb-0 mt-1">{{ $t('settings.paymentModulesDesc') || 'Configure payment providers for your client portal' }}</p>
        </div>
        <button class="btn btn-primary" @click="showPaymentModules = true">
          <i class="mdi mdi-credit-card-outline me-1"></i>
          {{ $t('settings.openModules') || 'Open Modules' }}
        </button>
      </div>
    </div>

    <!-- Active providers summary -->
    <div class="d-flex flex-wrap gap-2 mb-4">
      <span v-if="payConfigured" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>CryptoPay</span>
      <span v-if="paypal.configured" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>PayPal</span>
      <span v-if="nowpay.configured" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>NOWPayments</span>
      <span v-if="pluginProviders.stripe" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>Stripe</span>
      <span v-if="pluginProviders.payme" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>Payme</span>
      <span v-if="pluginProviders.mollie" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>Mollie</span>
      <span v-if="pluginProviders.razorpay" class="badge bg-success py-2 px-3"><i class="mdi mdi-check-circle me-1"></i>Razorpay</span>
      <span v-if="!payConfigured && !paypal.configured && !nowpay.configured && Object.keys(pluginProviders).length === 0" class="badge bg-secondary py-2 px-3">{{ $t('settings.noProviders') || 'No providers configured' }}</span>
    </div>

    <!-- Payment Modules Modal -->
    <div v-if="showPaymentModules" class="payment-modules-overlay" @click.self="showPaymentModules = false">
      <div class="payment-modules-modal">
        <div class="payment-modules-header">
          <h5 class="mb-0">{{ $t('settings.paymentModules') || 'Payment Modules' }}</h5>
          <button type="button" class="btn-close" @click="showPaymentModules = false"></button>
        </div>
        <div class="payment-modules-body">
          <p class="text-muted small mb-3">{{ $t('settings.paymentModulesHint') || 'Enter your API keys to activate a provider. Your end-users will see it as a payment option.' }}</p>

          <!-- CryptoPay -->
          <div class="pm-card" :class="{ 'pm-active': payConfigured }">
            <div class="pm-card-head" @click="pmOpen === 'cryptopay' ? pmOpen = '' : pmOpen = 'cryptopay'">
              <span class="pm-icon"><i class="mdi mdi-bitcoin"></i></span>
              <div class="pm-info"><strong>CryptoPay</strong><small>Telegram @CryptoBot · USDT, BTC, TON, ETH</small></div>
              <span class="badge" :class="payConfigured ? 'bg-success' : 'bg-secondary'">{{ payConfigured ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'cryptopay' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'cryptopay'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">API Token</label><div class="input-group input-group-sm"><input :type="showToken ? 'text' : 'password'" class="form-control" v-model="tokenInput" :placeholder="payMasked || 'CryptoPay API token'" /><button class="btn btn-outline-secondary" type="button" @click="showToken = !showToken"><i :class="showToken ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button></div></div>
              <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="testnet2" v-model="testnetMode" /><label class="form-check-label small" for="testnet2">Testnet</label></div>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Webhook URL <small class="text-muted fw-normal">(register in @CryptoBot → My Apps → Webhooks)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.cryptopay" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('cryptopay')"><i class="mdi" :class="copiedUrl === 'cryptopay' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="saveCryptoPay" :disabled="saving">{{ saving ? '...' : 'Save & Connect' }}</button><button v-if="payConfigured" class="btn btn-outline-info btn-sm" @click="runTest('cryptopay')" :disabled="testing === 'cryptopay'">{{ testing === 'cryptopay' ? 'Testing…' : 'Test' }}</button><button v-if="payConfigured" class="btn btn-outline-danger btn-sm" @click="disconnectCryptoPay" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.cryptopay" :result="testResults.cryptopay" />
              <div v-if="alertMsg" class="alert mt-2 py-1 small" :class="alertType">{{ alertMsg }}</div>
            </div>
          </div>

          <!-- PayPal -->
          <div class="pm-card" :class="{ 'pm-active': paypal.configured }">
            <div class="pm-card-head" @click="pmOpen === 'paypal' ? pmOpen = '' : pmOpen = 'paypal'">
              <span class="pm-icon"><i class="mdi mdi-credit-card"></i></span>
              <div class="pm-info"><strong>PayPal</strong><small>Visa, Mastercard, PayPal · Worldwide</small></div>
              <span class="badge" :class="paypal.configured ? 'bg-success' : 'bg-secondary'">{{ paypal.configured ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'paypal' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'paypal'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">Client ID</label><input type="text" class="form-control form-control-sm" v-model="paypal.clientId" :placeholder="paypal.clientIdMasked || 'PayPal Client ID'" /></div>
              <div class="mb-2"><label class="form-label small fw-bold">Client Secret</label><div class="input-group input-group-sm"><input :type="paypal.showSecret ? 'text' : 'password'" class="form-control" v-model="paypal.clientSecret" placeholder="PayPal Client Secret" /><button class="btn btn-outline-secondary" type="button" @click="paypal.showSecret = !paypal.showSecret"><i :class="paypal.showSecret ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button></div></div>
              <div class="mb-2"><label class="form-label small fw-bold">Webhook ID</label><input type="text" class="form-control form-control-sm" v-model="paypal.webhookId" :placeholder="paypal.webhookIdMasked || '12A3456BC7890123D'" /><small class="text-muted">Required in production. Create a webhook in <a href="https://developer.paypal.com/dashboard/webhooks" target="_blank">PayPal Dashboard</a> for the URL below, then paste its ID here.</small></div>
              <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="ppSandbox2" v-model="paypal.sandbox" /><label class="form-check-label small" for="ppSandbox2">Sandbox</label></div>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Webhook URL <small class="text-muted fw-normal">(register in PayPal Developer Dashboard → Webhooks)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.paypal" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('paypal')"><i class="mdi" :class="copiedUrl === 'paypal' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div><small class="text-muted">Subscribe to events: <code>CHECKOUT.ORDER.APPROVED</code>, <code>PAYMENT.CAPTURE.COMPLETED</code></small></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="savePayPal" :disabled="saving">{{ saving ? '...' : 'Save & Connect' }}</button><button v-if="paypal.configured" class="btn btn-outline-info btn-sm" @click="runTest('paypal')" :disabled="testing === 'paypal'">{{ testing === 'paypal' ? 'Testing…' : 'Test' }}</button><button v-if="paypal.configured" class="btn btn-outline-danger btn-sm" @click="disconnectPayPal" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.paypal" :result="testResults.paypal" />
              <div v-if="paypal.alert" class="alert mt-2 py-1 small" :class="paypal.alertType">{{ paypal.alert }}</div>
            </div>
          </div>

          <!-- NOWPayments -->
          <div class="pm-card" :class="{ 'pm-active': nowpay.configured }">
            <div class="pm-card-head" @click="pmOpen === 'nowpay' ? pmOpen = '' : pmOpen = 'nowpay'">
              <span class="pm-icon"><i class="mdi mdi-currency-btc"></i></span>
              <div class="pm-info"><strong>NOWPayments</strong><small>100+ Crypto · BTC, ETH, USDT, XMR, TON</small></div>
              <span class="badge" :class="nowpay.configured ? 'bg-success' : 'bg-secondary'">{{ nowpay.configured ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'nowpay' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'nowpay'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">API Key</label><div class="input-group input-group-sm"><input :type="nowpay.showKey ? 'text' : 'password'" class="form-control" v-model="nowpay.apiKey" :placeholder="nowpay.apiKeyMasked || 'NOWPayments API Key'" /><button class="btn btn-outline-secondary" type="button" @click="nowpay.showKey = !nowpay.showKey"><i :class="nowpay.showKey ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button></div></div>
              <div class="mb-2"><label class="form-label small fw-bold">IPN Secret</label><div class="input-group input-group-sm"><input :type="nowpay.showSecret ? 'text' : 'password'" class="form-control" v-model="nowpay.ipnSecret" placeholder="IPN Callback Secret" /><button class="btn btn-outline-secondary" type="button" @click="nowpay.showSecret = !nowpay.showSecret"><i :class="nowpay.showSecret ? 'mdi mdi-eye-off-outline' : 'mdi mdi-eye-outline'"></i></button></div></div>
              <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" id="npSandbox2" v-model="nowpay.sandbox" /><label class="form-check-label small" for="npSandbox2">Sandbox</label></div>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">IPN Callback URL <small class="text-muted fw-normal">(register in NOWPayments Dashboard → Store Settings → IPN)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.nowpayments" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('nowpayments')"><i class="mdi" :class="copiedUrl === 'nowpayments' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="saveNowPayments" :disabled="saving">{{ saving ? '...' : 'Save & Connect' }}</button><button v-if="nowpay.configured" class="btn btn-outline-info btn-sm" @click="runTest('nowpayments')" :disabled="testing === 'nowpayments'">{{ testing === 'nowpayments' ? 'Testing…' : 'Test' }}</button><button v-if="nowpay.configured" class="btn btn-outline-danger btn-sm" @click="disconnectNowPayments" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.nowpayments" :result="testResults.nowpayments" />
              <div v-if="nowpay.alert" class="alert mt-2 py-1 small" :class="nowpay.alertType">{{ nowpay.alert }}</div>
            </div>
          </div>

          <!-- Stripe -->
          <div class="pm-card" :class="{ 'pm-active': pluginProviders.stripe }">
            <div class="pm-card-head" @click="pmOpen === 'stripe' ? pmOpen = '' : pmOpen = 'stripe'">
              <span class="pm-icon"><i class="mdi mdi-credit-card-outline"></i></span>
              <div class="pm-info"><strong>Stripe</strong><small>Cards, Apple Pay, Google Pay · 46 countries</small></div>
              <span class="badge" :class="pluginProviders.stripe ? 'bg-success' : 'bg-secondary'">{{ pluginProviders.stripe ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'stripe' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'stripe'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">Secret Key</label><div class="input-group input-group-sm"><input type="password" class="form-control" v-model="pluginKeys.stripe_secret_key" :placeholder="pluginMasked.stripe || 'sk_live_...'" /><button class="btn btn-outline-secondary" type="button" @click="togglePluginShow('stripe')"><i class="mdi mdi-eye-outline"></i></button></div></div>
              <div class="mb-2"><label class="form-label small fw-bold">Webhook Secret <small class="text-muted">(optional)</small></label><input type="password" class="form-control form-control-sm" v-model="pluginKeys.stripe_webhook_secret" placeholder="whsec_..." /></div>
              <small class="text-muted d-block mb-2">Get keys at <a href="https://dashboard.stripe.com/apikeys" target="_blank">dashboard.stripe.com/apikeys</a></small>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Webhook endpoint URL <small class="text-muted fw-normal">(register in Stripe Dashboard → Developers → Webhooks)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.stripe" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('stripe')"><i class="mdi" :class="copiedUrl === 'stripe' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div><small class="text-muted">Listen to event: <code>checkout.session.completed</code></small></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="savePlugin('stripe')" :disabled="saving">Save & Connect</button><button v-if="pluginProviders.stripe" class="btn btn-outline-info btn-sm" @click="runTest('stripe')" :disabled="testing === 'stripe'">{{ testing === 'stripe' ? 'Testing…' : 'Test' }}</button><button v-if="pluginProviders.stripe" class="btn btn-outline-danger btn-sm" @click="disconnectPlugin('stripe')" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.stripe" :result="testResults.stripe" />
              <div v-if="pluginAlert.stripe" class="alert mt-2 py-1 small" :class="pluginAlert.stripe.type">{{ pluginAlert.stripe.msg }}</div>
            </div>
          </div>

          <!-- Payme -->
          <div class="pm-card" :class="{ 'pm-active': pluginProviders.payme }">
            <div class="pm-card-head" @click="pmOpen === 'payme' ? pmOpen = '' : pmOpen = 'payme'">
              <span class="pm-icon"><i class="mdi mdi-bank-outline"></i></span>
              <div class="pm-info"><strong>Payme</strong><small>UzCard, Humo, Visa · Uzbekistan</small></div>
              <span class="badge" :class="pluginProviders.payme ? 'bg-success' : 'bg-secondary'">{{ pluginProviders.payme ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'payme' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'payme'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">Merchant ID</label><input type="text" class="form-control form-control-sm" v-model="pluginKeys.payme_merchant_id" :placeholder="pluginMasked.payme || 'Merchant ID'" /></div>
              <div class="mb-2"><label class="form-label small fw-bold">Secret Key</label><input type="password" class="form-control form-control-sm" v-model="pluginKeys.payme_secret_key" placeholder="Secret Key" /></div>
              <small class="text-muted d-block mb-2">Get credentials at <a href="https://payme.uz" target="_blank">payme.uz</a> merchant dashboard</small>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Notification URL <small class="text-muted fw-normal">(register in Payme cabinet → Settings → Notifications)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.payme" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('payme')"><i class="mdi" :class="copiedUrl === 'payme' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="savePlugin('payme')" :disabled="saving">Save & Connect</button><button v-if="pluginProviders.payme" class="btn btn-outline-info btn-sm" @click="runTest('payme')" :disabled="testing === 'payme'">{{ testing === 'payme' ? 'Testing…' : 'Test' }}</button><button v-if="pluginProviders.payme" class="btn btn-outline-danger btn-sm" @click="disconnectPlugin('payme')" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.payme" :result="testResults.payme" />
              <div v-if="pluginAlert.payme" class="alert mt-2 py-1 small" :class="pluginAlert.payme.type">{{ pluginAlert.payme.msg }}</div>
            </div>
          </div>

          <!-- Mollie -->
          <div class="pm-card" :class="{ 'pm-active': pluginProviders.mollie }">
            <div class="pm-card-head" @click="pmOpen === 'mollie' ? pmOpen = '' : pmOpen = 'mollie'">
              <span class="pm-icon"><i class="mdi mdi-credit-card-multiple-outline"></i></span>
              <div class="pm-info"><strong>Mollie</strong><small>Cards, iDEAL, SEPA, Klarna · Europe</small></div>
              <span class="badge" :class="pluginProviders.mollie ? 'bg-success' : 'bg-secondary'">{{ pluginProviders.mollie ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'mollie' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'mollie'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">API Key</label><div class="input-group input-group-sm"><input type="password" class="form-control" v-model="pluginKeys.mollie_api_key" :placeholder="pluginMasked.mollie || 'live_...'" /><button class="btn btn-outline-secondary" type="button" @click="togglePluginShow('mollie')"><i class="mdi mdi-eye-outline"></i></button></div></div>
              <small class="text-muted d-block mb-2">Get keys at <a href="https://www.mollie.com/dashboard" target="_blank">mollie.com/dashboard</a></small>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Webhook URL <small class="text-muted fw-normal">(set per-payment automatically — no dashboard config needed)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.mollie" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('mollie')"><i class="mdi" :class="copiedUrl === 'mollie' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="savePlugin('mollie')" :disabled="saving">Save & Connect</button><button v-if="pluginProviders.mollie" class="btn btn-outline-info btn-sm" @click="runTest('mollie')" :disabled="testing === 'mollie'">{{ testing === 'mollie' ? 'Testing…' : 'Test' }}</button><button v-if="pluginProviders.mollie" class="btn btn-outline-danger btn-sm" @click="disconnectPlugin('mollie')" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.mollie" :result="testResults.mollie" />
              <div v-if="pluginAlert.mollie" class="alert mt-2 py-1 small" :class="pluginAlert.mollie.type">{{ pluginAlert.mollie.msg }}</div>
            </div>
          </div>

          <!-- Razorpay -->
          <div class="pm-card" :class="{ 'pm-active': pluginProviders.razorpay }">
            <div class="pm-card-head" @click="pmOpen === 'razorpay' ? pmOpen = '' : pmOpen = 'razorpay'">
              <span class="pm-icon"><i class="mdi mdi-credit-card-chip-outline"></i></span>
              <div class="pm-info"><strong>Razorpay</strong><small>Cards, UPI, NetBanking · India</small></div>
              <span class="badge" :class="pluginProviders.razorpay ? 'bg-success' : 'bg-secondary'">{{ pluginProviders.razorpay ? 'Active' : 'Off' }}</span>
              <i class="mdi" :class="pmOpen === 'razorpay' ? 'mdi-chevron-up' : 'mdi-chevron-down'"></i>
            </div>
            <div v-if="pmOpen === 'razorpay'" class="pm-card-body">
              <div class="mb-2"><label class="form-label small fw-bold">Key ID</label><input type="text" class="form-control form-control-sm" v-model="pluginKeys.razorpay_key_id" :placeholder="pluginMasked.razorpay || 'rzp_live_...'" /></div>
              <div class="mb-2"><label class="form-label small fw-bold">Key Secret</label><input type="password" class="form-control form-control-sm" v-model="pluginKeys.razorpay_key_secret" placeholder="Key Secret" /></div>
              <div class="mb-2"><label class="form-label small fw-bold">Webhook Secret</label><input type="password" class="form-control form-control-sm" v-model="pluginKeys.razorpay_webhook_secret" placeholder="whsec_..." /><small class="text-muted">Required to verify webhooks. Set in Razorpay Dashboard → Webhooks → Active Events.</small></div>
              <small class="text-muted d-block mb-2">Get keys at <a href="https://razorpay.com/docs/" target="_blank">razorpay.com</a></small>
              <div class="webhook-url-row"><label class="form-label small fw-bold mb-1">Webhook URL <small class="text-muted fw-normal">(register in Razorpay Dashboard → Settings → Webhooks)</small></label><div class="input-group input-group-sm"><input type="text" class="form-control" :value="webhookUrls.razorpay" readonly /><button class="btn btn-outline-secondary" type="button" @click="copyWebhookUrl('razorpay')"><i class="mdi" :class="copiedUrl === 'razorpay' ? 'mdi-check text-success' : 'mdi-content-copy'"></i></button></div><small class="text-muted">Active events: <code>payment.captured</code>, <code>payment_link.paid</code></small></div>
              <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary btn-sm" @click="savePlugin('razorpay')" :disabled="saving">Save & Connect</button><button v-if="pluginProviders.razorpay" class="btn btn-outline-info btn-sm" @click="runTest('razorpay')" :disabled="testing === 'razorpay'">{{ testing === 'razorpay' ? 'Testing…' : 'Test' }}</button><button v-if="pluginProviders.razorpay" class="btn btn-outline-danger btn-sm" @click="disconnectPlugin('razorpay')" :disabled="saving">Disconnect</button></div>
              <PaymentTestResult v-if="testResults.razorpay" :result="testResults.razorpay" />
              <div v-if="pluginAlert.razorpay" class="alert mt-2 py-1 small" :class="pluginAlert.razorpay.type">{{ pluginAlert.razorpay.msg }}</div>
            </div>
          </div>

        </div>
      </div>
    </div>

    <!-- SMTP Email Card -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.smtpTitle') }}</h4>

    <div class="card mb-4">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3 settings-card-header">
          <strong>{{ $t('settings.smtpServer') }}</strong>
          <span class="badge" :class="smtp.configured ? 'bg-success' : 'bg-secondary'">
            {{ smtp.configured ? $t('settings.connected') : $t('settings.notConfigured') }}
          </span>
        </div>
        <div class="row g-3 mb-3">
          <div class="col-md-8">
            <label class="form-label">{{ $t('settings.smtpHost') }}</label>
            <input type="text" class="form-control" v-model="smtp.host" placeholder="smtp.gmail.com" />
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ $t('settings.smtpPort') }}</label>
            <input type="number" class="form-control" v-model.number="smtp.port" placeholder="587" />
          </div>
        </div>
        <div class="row g-3 mb-3">
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.smtpUser') }}</label>
            <input type="text" class="form-control" v-model="smtp.username" placeholder="user@example.com" />
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.smtpPass') }}</label>
            <div class="input-group">
              <input :type="smtp.showPass ? 'text' : 'password'" class="form-control" v-model="smtp.password" :placeholder="smtp.passwordSet ? $t('settings.unchanged') : 'SMTP password'" />
              <button class="btn btn-outline-secondary" type="button" @click="smtp.showPass = !smtp.showPass">{{ smtp.showPass ? $t('common.hide') : $t('common.show') }}</button>
            </div>
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.smtpFrom') }}</label>
          <input type="email" class="form-control" v-model="smtp.from" placeholder="noreply@example.com" />
        </div>
        <div class="d-flex gap-3 mb-3 settings-inline-switches">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" id="smtpTls" v-model="smtp.tls" />
            <label class="form-check-label" for="smtpTls">{{ $t('settings.smtpTls') }}</label>
          </div>
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" id="smtpEnabled" v-model="smtp.enabled" />
            <label class="form-check-label" for="smtpEnabled">{{ $t('settings.emailVerification') }}</label>
          </div>
        </div>
        <div class="d-flex gap-2 settings-actions">
          <button class="btn btn-primary btn-sm" @click="saveSmtp" :disabled="saving">{{ saving ? $t('settings.saving') : $t('settings.saveConnect') }}</button>
          <button class="btn btn-outline-info btn-sm" @click="testSmtp" :disabled="saving || !smtp.configured">{{ $t('settings.smtpTest') }}</button>
          <button v-if="smtp.configured" class="btn btn-outline-danger btn-sm" @click="disconnectSmtp" :disabled="saving">{{ $t('settings.disconnect') }}</button>
        </div>
        <div v-if="smtp.alert" class="alert mt-3 py-2 small" :class="smtp.alertType">{{ smtp.alert }}</div>
      </div>
    </div>

    <!-- Telegram Notifications -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('notifications.title') || 'Telegram Notifications' }}</h4>
    <div class="card mb-4">
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">{{ $t('notifications.adminChatId') || 'Admin Chat ID' }}</label>
          <input type="text" class="form-control" v-model="notif.admin_telegram_chat_id" :placeholder="$t('notifications.adminChatIdHint')">
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="nNewUser" v-model="notif.notify_admin_new_user" />
          <label class="form-check-label" for="nNewUser">{{ $t('notifications.notifyNewUser') || 'New user registered' }}</label>
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="nNewPayment" v-model="notif.notify_admin_new_payment" />
          <label class="form-check-label" for="nNewPayment">{{ $t('notifications.notifyNewPayment') || 'New payment received' }}</label>
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="nExpired" v-model="notif.notify_admin_subscription_expired" />
          <label class="form-check-label" for="nExpired">{{ $t('notifications.notifyExpired') || 'Subscription expired' }}</label>
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="nExpiryWarn" v-model="notif.notify_user_expiry_warning" />
          <label class="form-check-label" for="nExpiryWarn">{{ $t('notifications.notifyExpiryWarning') || 'Expiry warning' }}</label>
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="nTrafficWarn" v-model="notif.notify_user_traffic_warning" />
          <label class="form-check-label" for="nTrafficWarn">{{ $t('notifications.notifyTrafficWarning') || 'Traffic warning' }}</label>
        </div>
        <div class="form-check form-switch mb-3">
          <input class="form-check-input" type="checkbox" id="nPaymentConfirmed" v-model="notif.notify_user_payment_confirmed" />
          <label class="form-check-label" for="nPaymentConfirmed">{{ $t('notifications.notifyPaymentConfirmed') || 'Payment confirmed (to user)' }}</label>
        </div>
        <button class="btn btn-primary btn-sm" @click="saveNotifications" :disabled="saving">{{ saving ? $t('settings.saving') : $t('common.save') }}</button>
        <div v-if="notif.alert" class="alert alert-success mt-3 py-2 small">{{ notif.alert }}</div>
      </div>
    </div>

    <!-- Backup — moved to dedicated /backup page in 1.5.83 -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.backupsTitle') }}</h4>
    <div class="card mb-4">
      <div class="card-body">
        <p class="mb-2"><i class="mdi mdi-information-outline me-1"></i>{{ $t('settings.backupsMovedHint') }}</p>
        <router-link to="/backup" class="btn btn-primary btn-sm">
          <i class="mdi mdi-database-outline me-1"></i>{{ $t('settings.openBackupSection') }}
        </router-link>
      </div>
    </div>

    <!-- Web Access -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('common.webAccessTitle') }}</h4>
    <div class="card mb-4">
      <div class="card-body">
        <p class="text-muted small mb-3">{{ $t('common.webAccessInfo') }}</p>

        <!-- Current URLs -->
        <div class="row g-3 mb-3">
          <div class="col-md-6">
            <label class="form-label fw-semibold small">{{ $t('common.currentClientPortalUrl') }}</label>
            <div class="input-group input-group-sm">
              <span class="input-group-text"><i class="bi bi-globe2"></i></span>
              <input type="text" class="form-control" :value="web.client_portal_url || ('http://' + web.public_ip_hint + ':10090')" readonly />
            </div>
          </div>
          <div class="col-md-6">
            <label class="form-label fw-semibold small">{{ $t('common.currentAdminPanelUrl') }}</label>
            <div class="input-group input-group-sm">
              <span class="input-group-text"><i class="bi bi-shield-lock"></i></span>
              <input type="text" class="form-control" :value="web.admin_panel_url || ('http://' + web.public_ip_hint + ':10086')" readonly />
            </div>
          </div>
        </div>

        <hr class="my-3" />

        <!-- Setup mode -->
        <div class="mb-3">
          <label class="form-label fw-semibold">{{ $t('common.webAccessMode') }}</label>
          <div class="d-flex flex-column gap-2">
            <div class="form-check border rounded p-3" :class="{'border-primary settings-mode-active': web.setup_mode === 'none'}">
              <input class="form-check-input" type="radio" v-model="web.setup_mode" value="none" id="mode_none" />
              <label class="form-check-label" for="mode_none">
                <strong>{{ $t('common.webAccessModeNoneTitle') }}</strong>
                <div class="text-muted small">{{ $t('common.webAccessModeNoneDesc') }}</div>
              </label>
            </div>
            <div class="form-check border rounded p-3" :class="{'border-primary settings-mode-active': web.setup_mode === 'portal_admin_ip'}">
              <input class="form-check-input" type="radio" v-model="web.setup_mode" value="portal_admin_ip" id="mode_portal_ip" />
              <label class="form-check-label" for="mode_portal_ip">
                <strong>{{ $t('common.webAccessModePortalIpTitle') }}</strong>
                <span class="badge bg-success ms-2">{{ $t('common.recommended') }}</span>
                <div class="text-muted small">{{ $t('common.webAccessModePortalIpDesc') }}</div>
              </label>
            </div>
            <div class="form-check border rounded p-3" :class="{'border-primary settings-mode-active': web.setup_mode === 'portal_admin_domain'}">
              <input class="form-check-input" type="radio" v-model="web.setup_mode" value="portal_admin_domain" id="mode_both" />
              <label class="form-check-label" for="mode_both">
                <strong>{{ $t('common.webAccessModeBothTitle') }}</strong>
                <div class="text-muted small">{{ $t('common.webAccessModeBothDesc') }}</div>
              </label>
            </div>
          </div>
        </div>

        <!-- Domain fields -->
        <div v-if="web.setup_mode !== 'none'">
          <div class="settings-info-box small py-2 px-3 mb-3 rounded">
            <strong>{{ $t('common.beforeYouStart') }}</strong>
            {{ $t('common.dnsInstructions') }}
            <span class="text-muted">{{ $t('common.serverIp') }}: <code>{{ web.public_ip_hint || '...' }}</code></span>
          </div>

          <div class="row g-3 mb-3">
            <div class="col-md-6">
              <label class="form-label">{{ $t('common.clientPortalDomain') }}</label>
              <input type="text" class="form-control" v-model="web.client_portal_domain" :placeholder="$t('common.clientPortalDomainPlaceholder')" />
            </div>
            <div class="col-md-6">
              <label class="form-label">{{ $t('common.certbotEmail') }}</label>
              <input type="email" class="form-control" v-model="web.certbot_email" :placeholder="$t('common.certbotEmailPlaceholder')" />
              <div class="form-text small">{{ $t('common.certbotEmailHint') }}</div>
            </div>
          </div>

          <div class="mb-3" v-if="web.setup_mode === 'portal_admin_domain'">
            <label class="form-label">{{ $t('common.adminPanelDomain') }}</label>
            <input type="text" class="form-control" v-model="web.admin_panel_domain" placeholder="admin.example.com" />
          </div>
        </div>

        <!-- Status bar -->
        <div class="d-flex align-items-center gap-3 small text-muted mb-3 settings-status-inline">
          <span>
            <span :class="web.nginx_installed ? 'text-success' : 'text-danger'">●</span>
            nginx: {{ web.nginx_installed ? $t('common.installed') : $t('common.notInstalled') }}
          </span>
          <span>
            <span :class="web.certbot_installed ? 'text-success' : 'text-danger'">●</span>
            SSL: {{ web.certbot_installed ? $t('common.ready') : $t('common.notInstalled') }}
          </span>
        </div>

        <div class="d-flex gap-2 settings-actions">
          <button class="btn btn-primary btn-sm" @click="applyWebAccess" :disabled="saving || web.applying">
            {{ web.applying ? $t('common.applying') : $t('common.saveApply') }}
          </button>
          <button class="btn btn-outline-secondary btn-sm" @click="loadWebAccessSettings" :disabled="saving || web.applying">{{ $t('common.refresh') }}</button>
        </div>
        <div v-if="web.alert" class="alert mt-3 py-2 small" :class="web.alertType">{{ web.alert }}</div>
      </div>
    </div>

    <!-- System Tools -->
    <h4 class="mb-3 settings-page__section-title">{{ $t('settings.systemTools') }}</h4>

    <div class="row g-3 mb-4">
      <!-- Health Check -->
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-body">
            <div class="d-flex align-items-center mb-3">
              <i class="mdi mdi-heart-pulse me-2" style="font-size:1.25rem;color:var(--vxy-success)"></i>
              <strong>{{ $t('settings.healthCheck') }}</strong>
            </div>
            <div v-if="health" class="mb-3">
              <div class="d-flex gap-3">
                <div class="d-flex align-items-center gap-1">
                  <span class="badge" :class="health.checks?.database ? 'bg-success' : 'bg-danger'">DB</span>
                  <span class="small">{{ health.checks?.database ? 'OK' : 'FAIL' }}</span>
                </div>
                <div class="d-flex align-items-center gap-1">
                  <span class="badge" :class="health.checks?.wireguard ? 'bg-success' : 'bg-danger'">WG</span>
                  <span class="small">{{ health.checks?.wireguard ? 'OK' : 'FAIL' }}</span>
                </div>
                <div class="d-flex align-items-center gap-1">
                  <span class="badge" :class="health.status === 'healthy' ? 'bg-success' : 'bg-danger'">
                    {{ health.status || '?' }}
                  </span>
                </div>
              </div>
              <div v-if="health.timestamp" class="small text-muted mt-1">
                {{ new Date(health.timestamp).toLocaleString() }}
              </div>
            </div>
            <div v-if="healthAlert" class="alert py-1 px-2 small mb-2" :class="healthAlertType">{{ healthAlert }}</div>
            <button class="btn btn-outline-info btn-sm" @click="doHealthCheck" :disabled="healthChecking">
              <i class="mdi mdi-refresh me-1"></i>
              {{ healthChecking ? $t('common.loading') : $t('settings.runCheck') }}
            </button>
          </div>
        </div>
      </div>
      <!-- Limit Check -->
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-body">
            <div class="d-flex align-items-center mb-3">
              <i class="mdi mdi-gauge me-2" style="font-size:1.25rem;color:var(--vxy-warning)"></i>
              <strong>{{ $t('settings.limitCheck') }}</strong>
            </div>
            <div v-if="limitResult" class="row g-2 mb-3">
              <div class="col-4 text-center">
                <div class="fw-bold" :class="limitResult.expired_clients > 0 ? 'text-danger' : ''">{{ limitResult.expired_clients }}</div>
                <div class="small text-muted">{{ $t('settings.limitExpired') }}</div>
              </div>
              <div class="col-4 text-center">
                <div class="fw-bold" :class="limitResult.traffic_exceeded_clients > 0 ? 'text-warning' : ''">{{ limitResult.traffic_exceeded_clients }}</div>
                <div class="small text-muted">{{ $t('settings.limitTraffic') }}</div>
              </div>
              <div class="col-4 text-center">
                <div class="fw-bold">{{ limitResult.total_disabled }}</div>
                <div class="small text-muted">{{ $t('settings.limitDisabled') }}</div>
              </div>
            </div>
            <div v-if="limitAlert" class="alert py-1 px-2 small mb-2" :class="limitAlertType">{{ limitAlert }}</div>
            <button class="btn btn-outline-warning btn-sm" @click="triggerLimits" :disabled="limitChecking">
              <i class="mdi mdi-play me-1"></i>
              {{ limitChecking ? $t('common.loading') : $t('settings.triggerCheck') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Branding (White-Label) -->
    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.branding') }}</h4>
    <div class="card mb-4">
      <div class="card-body">
        <div class="row g-3 mb-3">
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.appName') }}</label>
            <input type="text" class="form-control" v-model="brand.app_name" placeholder="Flirexa VPN Studio" />
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.companyName') }}</label>
            <input type="text" class="form-control" v-model="brand.company_name" placeholder="Your Company" />
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.loginPageTitle') }}</label>
          <input type="text" class="form-control" v-model="brand.login_title" placeholder="Admin Panel" />
        </div>
        <div class="row g-3 mb-3">
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.supportEmail') }}</label>
            <input type="email" class="form-control" v-model="brand.support_email" placeholder="support@example.com" />
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ $t('settings.supportUrl') }}</label>
            <input type="url" class="form-control" v-model="brand.support_url" placeholder="https://..." />
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.footerText') }}</label>
          <input type="text" class="form-control" v-model="brand.footer_text" placeholder="Optional footer text" />
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.logo') }}</label>
          <div class="d-flex align-items-center gap-3 settings-upload-row">
            <img v-if="brand.logo_url" :src="brand.logo_url" alt="Logo" style="height: 40px; border: 1px solid var(--vxy-border); border-radius: 4px; padding: 4px; background: var(--vxy-hover-bg);" />
            <input type="file" class="form-control" accept="image/png,image/jpeg,image/svg+xml,image/webp" @change="uploadLogo" />
            <button v-if="brand.logo_url" class="btn btn-outline-danger btn-sm" @click="removeLogo" :disabled="saving">{{ $t('settings.remove') }}</button>
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">{{ $t('settings.favicon') }}</label>
          <div class="d-flex align-items-center gap-3 settings-upload-row">
            <img v-if="brand.favicon_url" :src="brand.favicon_url" alt="Favicon" style="height: 24px; border: 1px solid var(--vxy-border); border-radius: 4px; padding: 2px; background: var(--vxy-hover-bg);" />
            <input type="file" class="form-control" accept="image/png,image/x-icon,image/svg+xml,image/webp" @change="uploadFavicon" />
            <button v-if="brand.favicon_url" class="btn btn-outline-danger btn-sm" @click="removeFavicon" :disabled="saving">{{ $t('settings.remove') }}</button>
          </div>
        </div>
        <div class="d-flex gap-2 settings-actions">
          <button class="btn btn-primary btn-sm" @click="saveBranding" :disabled="saving">{{ saving ? $t('settings.saving') : $t('settings.saveBranding') }}</button>
        </div>
        <div v-if="brand.alert" class="alert mt-3 py-2 small" :class="brand.alertType">{{ brand.alert }}</div>
      </div>
    </div>

    <h4 class="mb-4 settings-page__section-title">{{ $t('settings.appearance') }}</h4>

    <div class="card">
      <div class="card-body">
        <div class="d-flex flex-wrap gap-2 settings-actions settings-actions--compact">
          <button v-for="th in themes" :key="th.key" class="btn btn-sm" :class="curTheme === th.key ? 'btn-primary' : 'btn-outline-secondary'" @click="setTheme(th.key)">{{ th.key }}</button>
        </div>
      </div>
    </div>

    <!-- Feedback -->
    <div class="card mb-4" style="border-color:rgba(99,102,241,.2);background:linear-gradient(135deg,rgba(99,102,241,.05),rgba(168,85,247,.03))">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <strong>{{ $t('settings.feedbackTitle') || 'Help us improve' }}</strong>
          <p class="text-muted small mb-0 mt-1">{{ $t('settings.feedbackDesc') || 'Have an idea or suggestion? We\'d love to hear from you.' }}</p>
        </div>
        <a href="mailto:info@example.com?subject=Feature%20Request%20—%20VPN%20Management%20Studio" class="btn btn-outline-primary btn-sm text-nowrap">
          <i class="mdi mdi-lightbulb-outline me-1"></i>
          {{ $t('settings.suggestFeature') || 'Suggest a Feature' }}
        </a>
      </div>
    </div>
  </div>
</template>

<script>
import { systemApi, authApi, backupApi } from '../api'
import { useSystemStore } from '../stores/system'
import PaymentTestResult from '../components/PaymentTestResult.vue'

export default {
  components: { PaymentTestResult },
  data() {
    return {
      // License
      license: {
        type: '',
        enforcement: '',          // subscription / lifetime / lifetime_protected
        owner_name: null,
        owner_email: null,
        migration_pending: null,  // { initiated_at, decommission_seconds, decommissioned }
        max_clients: 0,
        max_servers: 0,
        current_clients: 0,
        current_servers: 0,
        features: [],
        days_remaining: null,
        grace_period: false,
        expires_at: null,
        server_id: '',
        activation_code_masked: '',
        message: '',
        newKey: '',
        replayCode: '',
        alert: '',
        alertType: 'alert-info',
      },
      // Customer self-service migration modal state
      migration: {
        modalOpen: false,
        generating: false,
        code: '',                 // populated after /license/transfer/initiate
        code_expires_at: null,
        this_server_decommissions_in_days: null,
      },
      // Apply transfer code on the NEW server
      transferApplyCode: '',
      applyingTransfer: false,
      transferApplyAlert: '',
      transferApplyAlertType: 'alert-info',
      replaying: false,
      licServer: {
        primary_url: null,
        backup_url: null,
        server_reachable: false,
        last_check: null,
        online_status: null,
        showMigration: false,
        migrationCode: '',
        migrating: false,
        migrationAlert: '',
        migrationAlertType: 'alert-info',
        refreshing: false,
      },
      // CryptoPay
      payConfigured: false,
      payMasked: '',
      tokenInput: '',
      testnetMode: false,
      showToken: false,
      saving: false,
      alertMsg: '',
      alertType: 'alert-info',
      // PayPal
      paypal: {
        configured: false,
        clientId: '',
        clientIdMasked: '',
        clientSecret: '',
        sandbox: true,
        webhookId: '',
        webhookIdMasked: '',
        showSecret: false,
        alert: '',
        alertType: 'alert-info',
      },
      // NOWPayments
      nowpay: {
        configured: false,
        apiKey: '',
        apiKeyMasked: '',
        ipnSecret: '',
        sandbox: false,
        showKey: false,
        showSecret: false,
        alert: '',
        alertType: 'alert-info',
      },
      // Payment modules modal
      showPaymentModules: false,
      pmOpen: '',
      pluginProviders: {},
      pluginKeys: { stripe_secret_key: '', stripe_webhook_secret: '', payme_merchant_id: '', payme_secret_key: '', mollie_api_key: '', razorpay_key_id: '', razorpay_key_secret: '', razorpay_webhook_secret: '' },
      pluginMasked: {},
      pluginAlert: {},
      // Per-provider test results: { provider_name → result_dict | null }
      testResults: {},
      testing: '',  // currently running provider name (drives spinner state)
      // Public client-portal URL (set after loadPaymentSettings reads CLIENT_PORTAL_DOMAIN)
      publicHost: '',
      copiedUrl: '',  // shows "Copied!" feedback under provider cards
      // SMTP
      smtp: {
        configured: false,
        enabled: false,
        host: '',
        port: 587,
        username: '',
        password: '',
        passwordSet: false,
        tls: true,
        from: '',
        showPass: false,
        alert: '',
        alertType: 'alert-info',
      },
      // Notifications
      notif: {
        admin_telegram_chat_id: '',
        notify_admin_new_user: true,
        notify_admin_new_payment: true,
        notify_admin_subscription_expired: true,
        notify_user_expiry_warning: true,
        notify_user_traffic_warning: true,
        notify_user_payment_confirmed: true,
        alert: '',
      },
      // Branding
      brand: {
        app_name: '',
        company_name: '',
        logo_url: '',
        favicon_url: '',
        primary_color: '#0d6efd',
        login_title: '',
        support_email: '',
        support_url: '',
        footer_text: '',
        alert: '',
        alertType: 'alert-info',
      },
      // Web access
      web: {
        setup_mode: 'none',
        client_portal_domain: '',
        admin_panel_domain: '',
        certbot_email: '',
        client_portal_url: '',
        admin_panel_url: '',
        public_ip_hint: '',
        nginx_installed: false,
        certbot_installed: false,
        alert: '',
        alertType: 'alert-info',
        applying: false,
      },
      // Create Admin
      newAdmin: {
        username: '',
        password: '',
        showPass: false,
        alert: '',
        alertType: 'alert-info',
      },
      health: null,
      healthChecking: false,
      healthAlert: '',
      healthAlertType: 'alert-info',
      limitResult: null,
      limitChecking: false,
      limitAlert: '',
      limitAlertType: 'alert-info',
      themes: [
        { key: 'light' }, { key: 'dark' }
      ],
    }
  },
  computed: {
    curTheme() { return useSystemStore().theme },
    /**
     * Public-facing webhook host. The admin panel runs on port 10086,
     * client portal on 10443 — providers POST to the latter, so we rewrite
     * the port. If the admin already configured CLIENT_PORTAL_DOMAIN this
     * gets overridden later by `webhookHost` once payment-settings loads.
     */
    webhookHost() {
      try {
        if (this.publicHost) return this.publicHost
        const proto = window.location.protocol
        const host = window.location.host.replace(/:10086$/, ':10443')
        return `${proto}//${host}`
      } catch { return '' }
    },
    webhookUrls() {
      const base = this.webhookHost
      return {
        cryptopay:   base ? `${base}/client-portal/webhooks/cryptopay`   : '/client-portal/webhooks/cryptopay',
        paypal:      base ? `${base}/client-portal/webhooks/paypal`      : '/client-portal/webhooks/paypal',
        nowpayments: base ? `${base}/client-portal/webhooks/nowpayments` : '/client-portal/webhooks/nowpayments',
        stripe:      base ? `${base}/client-portal/webhooks/stripe`      : '/client-portal/webhooks/stripe',
        mollie:      base ? `${base}/client-portal/webhooks/mollie`      : '/client-portal/webhooks/mollie',
        razorpay:    base ? `${base}/client-portal/webhooks/razorpay`    : '/client-portal/webhooks/razorpay',
        payme:       base ? `${base}/client-portal/webhooks/payme`       : '/client-portal/webhooks/payme',
      }
    },
    paypalWebhookUrl() { return this.webhookUrls.paypal },
    graceEndDate() {
      if (!this.license.expires_at) return ''
      const d = new Date(this.license.expires_at)
      d.setDate(d.getDate() + 7)
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    },
    clientUsagePct() {
      if (!this.license.max_clients || this.license.max_clients >= 999999) return 0
      return Math.round((this.license.current_clients / this.license.max_clients) * 100)
    },
    serverUsagePct() {
      if (!this.license.max_servers || this.license.max_servers >= 999999) return 0
      return Math.round((this.license.current_servers / this.license.max_servers) * 100)
    },
  },
  async mounted() {
    await Promise.all([this.loadLicense(), this.loadPaymentSettings(), this.loadSmtpSettings(), this.loadNotifications(), this.loadBranding(), this.loadWebAccessSettings()])
  },
  methods: {
    setTheme(k) { useSystemStore().setTheme(k) },

    copyToClipboard(text) {
      if (!text) return
      navigator.clipboard.writeText(text).catch(() => {})
    },

    // License methods
    async loadLicense() {
      try {
        var r = await systemApi.getLicense()
        // Normalize: backend returns license_type, template expects type
        if (r.data.license_type && !r.data.type) r.data.type = r.data.license_type
        Object.assign(this.license, r.data)
      } catch(e) { console.warn('Failed to load license:', e.message) }
      try {
        var rs = await systemApi.getLicenseServer()
        Object.assign(this.licServer, rs.data)
      } catch(e) { console.warn('Failed to load license server:', e.message) }
    },
    async refreshLicenseCheck() {
      this.licServer.refreshing = true
      try {
        await systemApi.triggerLicenseCheck()
        await new Promise(r => setTimeout(r, 3000))
        var rs = await systemApi.getLicenseServer()
        Object.assign(this.licServer, rs.data)
      } catch(e) { console.warn('Refresh failed:', e.message) }
      finally { this.licServer.refreshing = false }
    },
    async applyMigration() {
      this.licServer.migrating = true
      this.licServer.migrationAlert = ''
      try {
        var r = await systemApi.applyMigrationCode({ code: this.licServer.migrationCode.trim() })
        this.licServer.migrationAlertType = 'alert-success'
        this.licServer.migrationAlert = r.data.message || 'Migration applied successfully'
        this.licServer.migrationCode = ''
        var rs = await systemApi.getLicenseServer()
        Object.assign(this.licServer, rs.data)
      } catch(e) {
        this.licServer.migrationAlertType = 'alert-danger'
        this.licServer.migrationAlert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.licServer.migrating = false }
    },

    // ── Customer self-service server transfer (lifetime_protected) ──────
    openMigrationModal() {
      this.migration.modalOpen = true
      this.migration.code = ''
    },
    closeMigrationModal() {
      this.migration.modalOpen = false
      // Refresh license card so the countdown badge shows up after generation
      this.loadLicense()
    },
    async generateMigration() {
      this.migration.generating = true
      try {
        var r = await systemApi.licenseTransferInitiate()
        this.migration.code = r.data.code
        this.migration.code_expires_at = r.data.code_expires_at
        this.migration.this_server_decommissions_in_days = r.data.this_server_decommissions_in_days
      } catch (e) {
        var detail = e.response?.data?.detail
        var msg = (detail && detail.message) || detail || e.message || String(e)
        this.license.alertType = 'alert-danger'
        this.license.alert = 'Migration failed: ' + msg
        this.closeMigrationModal()
      } finally {
        this.migration.generating = false
      }
    },
    async cancelMigration() {
      try {
        await systemApi.licenseTransferCancel()
        this.license.alertType = 'alert-info'
        this.license.alert = 'Migration cancelled — this server will keep running normally.'
        await this.loadLicense()
      } catch (e) {
        this.license.alertType = 'alert-danger'
        this.license.alert = 'Cancel failed: ' + (e.response?.data?.detail || e.message)
      }
    },
    humanizeSeconds(s) {
      if (s == null) return '—'
      if (s <= 0) return 'now'
      var days = Math.floor(s / 86400)
      var hours = Math.floor((s % 86400) / 3600)
      var mins = Math.floor((s % 3600) / 60)
      if (days > 0) return days + 'd ' + hours + 'h'
      if (hours > 0) return hours + 'h ' + mins + 'm'
      return mins + 'm'
    },
    async applyTransferCode() {
      this.applyingTransfer = true
      this.transferApplyAlert = ''
      try {
        var r = await systemApi.licenseTransferApply({ code: this.transferApplyCode.trim() })
        this.transferApplyAlertType = 'alert-success'
        this.transferApplyAlert = r.data.message || 'Transfer code accepted.'
        this.transferApplyCode = ''
        await this.loadLicense()
      } catch (e) {
        this.transferApplyAlertType = 'alert-danger'
        var detail = e.response?.data?.detail
        var msg = (detail && detail.message) || detail || e.message || String(e)
        this.transferApplyAlert = 'Could not apply: ' + msg
      } finally {
        this.applyingTransfer = false
      }
    },
    async activateLicense() {
      if (!this.license.newKey) return
      this.saving = true; this.license.alert = ''
      try {
        var r = await systemApi.activateLicense({ license_key: this.license.newKey })
        this.license.alertType = 'alert-success'
        this.license.alert = 'License activated successfully!'
        this.license.newKey = ''
        var lic = r.data.license || {}
        if (lic.license_type && !lic.type) lic.type = lic.license_type
        Object.assign(this.license, lic)
      } catch(e) {
        this.license.alertType = 'alert-danger'
        this.license.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },

    async replayLicense() {
      if (!this.license.replayCode) return
      this.replaying = true; this.license.alert = ''
      try {
        var r = await systemApi.replayLicense({ activation_code: this.license.replayCode })
        this.license.alertType = 'alert-success'
        this.license.alert = (this.$t('settings.refetchSuccess')
          || 'License re-fetched successfully — same payload, fresh signature.')
        this.license.replayCode = ''
        var lic = r.data.license || {}
        if (lic.license_type && !lic.type) lic.type = lic.license_type
        Object.assign(this.license, lic)
      } catch(e) {
        this.license.alertType = 'alert-danger'
        this.license.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.replaying = false }
    },

    async loadPaymentSettings() {
      try {
        var r = await systemApi.getPaymentSettings()
        this.payConfigured = r.data.cryptopay_configured
        this.payMasked = r.data.cryptopay_token_masked
        this.testnetMode = r.data.cryptopay_testnet
        this.paypal.configured = r.data.paypal_configured
        this.paypal.clientIdMasked = r.data.paypal_client_id_masked
        this.paypal.sandbox = r.data.paypal_sandbox
        this.paypal.webhookIdMasked = r.data.paypal_webhook_id_masked || ''
        this.nowpay.configured = r.data.nowpayments_configured
        this.nowpay.apiKeyMasked = r.data.nowpayments_api_key_masked
        this.nowpay.sandbox = r.data.nowpayments_sandbox
        // Plugin providers
        this.pluginProviders = {
          stripe: r.data.stripe_configured, payme: r.data.payme_configured,
          mollie: r.data.mollie_configured, razorpay: r.data.razorpay_configured,
        }
        this.pluginMasked = {
          stripe: r.data.stripe_key_masked, payme: r.data.payme_id_masked,
          mollie: r.data.mollie_key_masked, razorpay: r.data.razorpay_key_masked,
        }
      } catch(e) {}
    },

    async savePlugin(name) {
      this.saving = true
      this.pluginAlert[name] = null
      try {
        const payload = {}
        if (name === 'stripe') { payload.stripe_secret_key = this.pluginKeys.stripe_secret_key; payload.stripe_webhook_secret = this.pluginKeys.stripe_webhook_secret }
        else if (name === 'payme') { payload.payme_merchant_id = this.pluginKeys.payme_merchant_id; payload.payme_secret_key = this.pluginKeys.payme_secret_key }
        else if (name === 'mollie') { payload.mollie_api_key = this.pluginKeys.mollie_api_key }
        else if (name === 'razorpay') { payload.razorpay_key_id = this.pluginKeys.razorpay_key_id; payload.razorpay_key_secret = this.pluginKeys.razorpay_key_secret; payload.razorpay_webhook_secret = this.pluginKeys.razorpay_webhook_secret }
        await systemApi.updatePaymentSettings(payload)
        this.pluginAlert[name] = { type: 'alert-success', msg: 'Saved & connected!' }
        await this.loadPaymentSettings()
      } catch(e) {
        this.pluginAlert[name] = { type: 'alert-danger', msg: e.response?.data?.detail || 'Error saving' }
      } finally { this.saving = false }
    },

    async disconnectPlugin(name) {
      this.saving = true
      try {
        const payload = {}
        if (name === 'stripe') { payload.stripe_secret_key = '' }
        else if (name === 'payme') { payload.payme_merchant_id = ''; payload.payme_secret_key = '' }
        else if (name === 'mollie') { payload.mollie_api_key = '' }
        else if (name === 'razorpay') { payload.razorpay_key_id = ''; payload.razorpay_key_secret = ''; payload.razorpay_webhook_secret = '' }
        await systemApi.updatePaymentSettings(payload)
        this.pluginAlert[name] = { type: 'alert-info', msg: 'Disconnected.' }
        await this.loadPaymentSettings()
      } catch(e) {
        this.pluginAlert[name] = { type: 'alert-danger', msg: 'Error' }
      } finally { this.saving = false }
    },

    togglePluginShow(name) {
      const el = event.target.closest('.input-group')?.querySelector('input')
      if (el) el.type = el.type === 'password' ? 'text' : 'password'
    },

    /**
     * Click handler for the "Test" button under each provider card.
     * Calls POST /system/payment-test/{name} which runs offline signature
     * verification + API ping in-process and returns a check-list.
     */
    async runTest(name) {
      this.testing = name
      // Reactivity: replace the per-provider entry so Vue picks up the change.
      this.testResults = { ...this.testResults, [name]: null }
      try {
        const r = await systemApi.runPaymentTest(name)
        this.testResults = { ...this.testResults, [name]: r.data }
      } catch (e) {
        const detail = e?.response?.data?.detail || e?.message || 'Unknown error'
        this.testResults = {
          ...this.testResults,
          [name]: {
            provider: name, configured: false,
            checks: [{ name: 'Test request failed', ok: false, detail }],
            passed: 0, failed: 1,
          },
        }
      } finally {
        this.testing = ''
      }
    },

    async loadSmtpSettings() {
      try {
        var r = await systemApi.getSmtpSettings()
        this.smtp.configured = r.data.smtp_configured
        this.smtp.enabled = r.data.smtp_enabled
        this.smtp.host = r.data.smtp_host
        this.smtp.port = r.data.smtp_port
        this.smtp.username = r.data.smtp_username
        this.smtp.passwordSet = r.data.smtp_password_set
        this.smtp.tls = r.data.smtp_tls
        this.smtp.from = r.data.smtp_from
      } catch(e) {}
    },

    // CryptoPay methods
    async saveCryptoPay() {
      this.saving = true; this.alertMsg = ''
      try {
        var p = { cryptopay_testnet: this.testnetMode }
        if (this.tokenInput.trim()) p.cryptopay_api_token = this.tokenInput.trim()
        var r = await systemApi.updatePaymentSettings(p)
        this.alertType = r.data.connected ? 'alert-success' : 'alert-warning'
        this.alertMsg = r.data.message || 'Settings updated'
        this.tokenInput = ''; this.showToken = false
        await this.loadPaymentSettings()
      } catch(e) { this.alertType = 'alert-danger'; this.alertMsg = String(e.message || e) }
      finally { this.saving = false }
    },
    async disconnectCryptoPay() {
      if (!confirm('Disconnect CryptoPay?')) return
      this.saving = true
      try {
        await systemApi.updatePaymentSettings({ cryptopay_api_token: '', cryptopay_testnet: false })
        this.alertMsg = 'Disconnected'; this.alertType = 'alert-info'
        await this.loadPaymentSettings()
      } catch(e) { this.alertType = 'alert-danger'; this.alertMsg = String(e.message || e) }
      finally { this.saving = false }
    },

    // PayPal methods
    async savePayPal() {
      this.saving = true; this.paypal.alert = ''
      try {
        var p = { paypal_sandbox: this.paypal.sandbox }
        if (this.paypal.clientId.trim()) p.paypal_client_id = this.paypal.clientId.trim()
        if ((this.paypal.webhookId || '').trim()) p.paypal_webhook_id = this.paypal.webhookId.trim()
        if (this.paypal.clientSecret.trim()) p.paypal_client_secret = this.paypal.clientSecret.trim()
        var r = await systemApi.updatePaymentSettings(p)
        var pp = r.data.providers?.paypal || {}
        this.paypal.alertType = pp.connected ? 'alert-success' : 'alert-warning'
        this.paypal.alert = pp.message || 'Settings updated'
        this.paypal.clientId = ''; this.paypal.clientSecret = ''; this.paypal.showSecret = false
        await this.loadPaymentSettings()
      } catch(e) { this.paypal.alertType = 'alert-danger'; this.paypal.alert = String(e.message || e) }
      finally { this.saving = false }
    },
    async disconnectPayPal() {
      if (!confirm('Disconnect PayPal?')) return
      this.saving = true
      try {
        await systemApi.updatePaymentSettings({ paypal_client_id: '', paypal_client_secret: '' })
        this.paypal.alert = 'Disconnected'; this.paypal.alertType = 'alert-info'
        await this.loadPaymentSettings()
      } catch(e) { this.paypal.alertType = 'alert-danger'; this.paypal.alert = String(e.message || e) }
      finally { this.saving = false }
    },

    // NOWPayments methods
    async saveNowPayments() {
      this.saving = true; this.nowpay.alert = ''
      try {
        var p = { nowpayments_sandbox: this.nowpay.sandbox }
        if (this.nowpay.apiKey.trim()) p.nowpayments_api_key = this.nowpay.apiKey.trim()
        if (this.nowpay.ipnSecret.trim()) p.nowpayments_ipn_secret = this.nowpay.ipnSecret.trim()
        var r = await systemApi.updatePaymentSettings(p)
        var np = r.data.providers?.nowpayments || {}
        this.nowpay.alertType = np.connected ? 'alert-success' : 'alert-warning'
        this.nowpay.alert = np.message || 'Settings updated'
        this.nowpay.apiKey = ''; this.nowpay.ipnSecret = ''
        await this.loadPaymentSettings()
      } catch(e) { this.nowpay.alertType = 'alert-danger'; this.nowpay.alert = String(e.message || e) }
      finally { this.saving = false }
    },
    async disconnectNowPayments() {
      if (!confirm('Disconnect NOWPayments?')) return
      this.saving = true
      try {
        await systemApi.updatePaymentSettings({ nowpayments_api_key: '', nowpayments_ipn_secret: '' })
        this.nowpay.alert = 'Disconnected'; this.nowpay.alertType = 'alert-info'
        await this.loadPaymentSettings()
      } catch(e) { this.nowpay.alertType = 'alert-danger'; this.nowpay.alert = String(e.message || e) }
      finally { this.saving = false }
    },

    // SMTP methods
    async saveSmtp() {
      this.saving = true; this.smtp.alert = ''
      try {
        var p = {
          smtp_host: this.smtp.host,
          smtp_port: this.smtp.port,
          smtp_username: this.smtp.username,
          smtp_tls: this.smtp.tls,
          smtp_from: this.smtp.from,
          smtp_enabled: this.smtp.enabled,
        }
        if (this.smtp.password) p.smtp_password = this.smtp.password
        var r = await systemApi.updateSmtpSettings(p)
        this.smtp.alertType = r.data.connected ? 'alert-success' : 'alert-warning'
        this.smtp.alert = r.data.message
        this.smtp.password = ''
        await this.loadSmtpSettings()
      } catch(e) { this.smtp.alertType = 'alert-danger'; this.smtp.alert = String(e.message || e) }
      finally { this.saving = false }
    },
    async testSmtp() {
      this.saving = true; this.smtp.alert = ''
      try {
        var r = await systemApi.testSmtp()
        this.smtp.alertType = 'alert-success'
        this.smtp.alert = r.data.message
      } catch(e) {
        this.smtp.alertType = 'alert-danger'
        this.smtp.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },
    async disconnectSmtp() {
      if (!confirm('Disconnect SMTP?')) return
      this.saving = true
      try {
        await systemApi.updateSmtpSettings({ smtp_enabled: false, smtp_host: '' })
        this.smtp.alert = 'SMTP disconnected'; this.smtp.alertType = 'alert-info'
        await this.loadSmtpSettings()
      } catch(e) { this.smtp.alertType = 'alert-danger'; this.smtp.alert = String(e.message || e) }
      finally { this.saving = false }
    },

    // Notification methods
    async loadNotifications() {
      try {
        var r = await systemApi.getNotificationSettings()
        Object.assign(this.notif, r.data)
      } catch(e) {}
    },
    async saveNotifications() {
      this.saving = true
      try {
        await systemApi.updateNotificationSettings({
          admin_telegram_chat_id: this.notif.admin_telegram_chat_id,
          notify_admin_new_user: this.notif.notify_admin_new_user,
          notify_admin_new_payment: this.notif.notify_admin_new_payment,
          notify_admin_subscription_expired: this.notif.notify_admin_subscription_expired,
          notify_user_expiry_warning: this.notif.notify_user_expiry_warning,
          notify_user_traffic_warning: this.notif.notify_user_traffic_warning,
          notify_user_payment_confirmed: this.notif.notify_user_payment_confirmed,
        })
        this.notif.alert = 'Saved!'
        setTimeout(() => { this.notif.alert = '' }, 3000)
      } catch(e) { alert('Error: ' + e.message) }
      finally { this.saving = false }
    },

    async loadWebAccessSettings() {
      try {
        var r = await systemApi.getWebAccessSettings()
        Object.assign(this.web, r.data)
        // Source-of-truth public host for webhook URLs.
        // If the admin set CLIENT_PORTAL_DOMAIN we use that — providers must
        // POST to a public domain, not localhost / IP / admin-port host.
        const cpd = (r.data?.client_portal_domain || '').trim()
        if (cpd) this.publicHost = `https://${cpd}`
      } catch(e) {
        this.web.alertType = 'alert-danger'
        this.web.alert = e.response?.data?.detail || String(e.message || e)
      }
    },
    async copyWebhookUrl(provider) {
      const url = this.webhookUrls[provider] || ''
      if (!url) return
      try {
        await navigator.clipboard.writeText(url)
        this.copiedUrl = provider
        setTimeout(() => { if (this.copiedUrl === provider) this.copiedUrl = '' }, 1500)
      } catch (_e) { /* clipboard refused — admin can select manually */ }
    },
    async applyWebAccess() {
      this.web.applying = true
      this.web.alert = ''
      try {
        var payload = {
          setup_mode: this.web.setup_mode,
          client_portal_domain: this.web.client_portal_domain || null,
          admin_panel_domain: this.web.admin_panel_domain || null,
          certbot_email: this.web.certbot_email || null,
        }
        var r = await systemApi.applyWebAccessSettings(payload)
        this.web.alertType = 'alert-success'
        this.web.alert = r.data.message + (r.data.output ? '\n' + r.data.output : '')
        await this.loadWebAccessSettings()
      } catch(e) {
        this.web.alertType = 'alert-danger'
        this.web.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.web.applying = false }
    },

    // Branding methods
    async loadBranding() {
      try {
        var r = await systemApi.getBranding()
        this.brand.app_name = r.data.branding_app_name || ''
        this.brand.company_name = r.data.branding_company_name || ''
        this.brand.logo_url = r.data.branding_logo_url || ''
        this.brand.favicon_url = r.data.branding_favicon_url || ''
        this.brand.primary_color = r.data.branding_primary_color || '#0d6efd'
        this.brand.login_title = r.data.branding_login_title || ''
        this.brand.support_email = r.data.branding_support_email || ''
        this.brand.support_url = r.data.branding_support_url || ''
        this.brand.footer_text = r.data.branding_footer_text || ''
      } catch(e) { console.warn('Failed to load branding:', e.message) }
    },
    async saveBranding() {
      this.saving = true; this.brand.alert = ''
      try {
        await systemApi.updateBranding({
          branding_app_name: this.brand.app_name,
          branding_company_name: this.brand.company_name,
          branding_login_title: this.brand.login_title,
          branding_support_email: this.brand.support_email,
          branding_support_url: this.brand.support_url,
          branding_footer_text: this.brand.footer_text,
        })
        this.brand.alertType = 'alert-success'
        this.brand.alert = 'Branding saved!'
        try {
          var { useBrandingStore } = await import('../stores/branding')
          useBrandingStore().fetchBranding()
        } catch(e) {}
      } catch(e) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },
    async uploadLogo(event) {
      var file = event.target.files[0]
      if (!file) return
      if (file.size > 2 * 1024 * 1024) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = 'File too large (max 2MB)'
        return
      }
      this.saving = true; this.brand.alert = ''
      try {
        var form = new FormData()
        form.append('file', file)
        var r = await systemApi.uploadLogo(form)
        this.brand.logo_url = r.data.url
        this.brand.alertType = 'alert-success'
        this.brand.alert = 'Logo uploaded'
        // Refresh branding in sidebar/navbar
        try {
          var { useBrandingStore } = await import('../stores/branding')
          useBrandingStore().fetchBranding()
        } catch(e) {}
      } catch(e) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },
    async uploadFavicon(event) {
      var file = event.target.files[0]
      if (!file) return
      if (file.size > 1 * 1024 * 1024) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = 'File too large (max 1MB)'
        return
      }
      this.saving = true; this.brand.alert = ''
      try {
        var form = new FormData()
        form.append('file', file)
        var r = await systemApi.uploadLogo(form)
        this.brand.favicon_url = r.data.url
        // Save favicon URL to branding config
        await systemApi.updateBranding({ branding_favicon_url: r.data.url })
        this.brand.alertType = 'alert-success'
        this.brand.alert = 'Favicon uploaded'
        try {
          var { useBrandingStore } = await import('../stores/branding')
          useBrandingStore().fetchBranding()
        } catch(e) {}
      } catch(e) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },
    async removeLogo() {
      this.saving = true; this.brand.alert = ''
      try {
        await systemApi.updateBranding({ branding_logo_url: '' })
        this.brand.logo_url = ''
        this.brand.alertType = 'alert-success'
        this.brand.alert = 'Logo removed'
        try {
          var { useBrandingStore } = await import('../stores/branding')
          useBrandingStore().fetchBranding()
        } catch(e) {}
      } catch(e) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },
    async removeFavicon() {
      this.saving = true; this.brand.alert = ''
      try {
        await systemApi.updateBranding({ branding_favicon_url: '' })
        this.brand.favicon_url = ''
        this.brand.alertType = 'alert-success'
        this.brand.alert = 'Favicon removed'
        try {
          var { useBrandingStore } = await import('../stores/branding')
          useBrandingStore().fetchBranding()
        } catch(e) {}
      } catch(e) {
        this.brand.alertType = 'alert-danger'
        this.brand.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },

    // Create Admin
    async createAdmin() {
      if (!this.newAdmin.username || !this.newAdmin.password) return
      this.saving = true; this.newAdmin.alert = ''
      try {
        var r = await authApi.createAdmin({
          username: this.newAdmin.username,
          password: this.newAdmin.password,
        })
        this.newAdmin.alertType = 'alert-success'
        this.newAdmin.alert = r.data.message || 'Admin created'
        this.newAdmin.username = ''; this.newAdmin.password = ''; this.newAdmin.showPass = false
      } catch(e) {
        this.newAdmin.alertType = 'alert-danger'
        this.newAdmin.alert = e.response?.data?.detail || String(e.message || e)
      }
      finally { this.saving = false }
    },

    // Backup methods
    // System methods
    async doHealthCheck() {
      this.healthChecking = true; this.healthAlert = ''
      try {
        var r = await systemApi.getHealth()
        this.health = r.data
      } catch(e) {
        this.healthAlert = e.response?.data?.detail || String(e.message || e)
        this.healthAlertType = 'alert-danger'
      } finally { this.healthChecking = false }
    },
    async triggerLimits() {
      this.limitChecking = true; this.limitAlert = ''
      try {
        var r = await systemApi.triggerLimitCheck()
        this.limitResult = r.data
        this.limitAlert = 'Check completed'
        this.limitAlertType = 'alert-success'
        setTimeout(() => { this.limitAlert = '' }, 3000)
      } catch(e) {
        this.limitAlert = e.response?.data?.detail || String(e.message || e)
        this.limitAlertType = 'alert-danger'
      } finally { this.limitChecking = false }
    },
  }
}
</script>

<style scoped>
.settings-page__section-title {
  font-size: .8rem;
  font-weight: 700;
  letter-spacing: .6px;
  text-transform: uppercase;
  color: var(--vxy-muted);
}
/* Payment Modules Modal */
.payment-modules-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1060; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.payment-modules-modal { background: var(--vxy-card-bg, #1a1d2e); color: var(--vxy-text); border-radius: .75rem; width: 100%; max-width: 600px; max-height: 85vh; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,.4); }
.payment-modules-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--vxy-border); flex-shrink: 0; }
.payment-modules-body { padding: 1rem 1.25rem; overflow-y: auto; flex: 1; }
.pm-card { border: 1px solid var(--vxy-border); border-radius: .5rem; margin-bottom: .5rem; overflow: hidden; transition: border-color .2s; }
.pm-card.pm-active { border-color: var(--vxy-success, #22c55e); }
.pm-card-head { display: flex; align-items: center; gap: .75rem; padding: .75rem 1rem; cursor: pointer; transition: background .15s; }
.pm-card-head:hover { background: var(--vxy-hover-bg, rgba(255,255,255,.03)); }
.pm-icon { font-size: 1.5rem; flex-shrink: 0; width: 2rem; text-align: center; }
.pm-info { flex: 1; min-width: 0; }
.pm-info strong { display: block; font-size: .9rem; }
.pm-info small { display: block; color: var(--vxy-muted); font-size: .75rem; }
.pm-card-body { padding: .75rem 1rem; border-top: 1px solid var(--vxy-border); background: var(--vxy-hover-bg, rgba(255,255,255,.02)); }
.webhook-url-row {
  margin: .5rem 0;
  padding: .55rem .65rem;
  background: rgba(13,110,253,.05);
  border: 1px solid rgba(13,110,253,.18);
  border-radius: .375rem;
}
.webhook-url-row input { font-family: var(--mono, monospace); font-size: .78rem; background: var(--vxy-card-bg) !important; }
.pm-card-body pre { margin-bottom: .5rem; font-size: .78rem; }

/* Theme-aware active radio card highlight */
.settings-mode-active {
  background: var(--vxy-primary-light) !important;
}
/* Theme-aware info/hint box (replaces Bootstrap's alert-light) */
.settings-info-box {
  background: var(--vxy-hover-bg);
  border: 1px solid var(--vxy-border);
  color: var(--vxy-text);
}
/* Theme-aware neutral badge (replaces bg-light text-dark) */
.settings-status-badge {
  background: var(--vxy-hover-bg);
  color: var(--vxy-text);
  border: 1px solid var(--vxy-border);
  font-weight: 500;
}
</style>
