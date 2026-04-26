<template>
  <div class="client-dashboard">
    <!-- Toast notifications -->
    <div class="toast-container">
      <transition-group name="toast">
        <div v-for="toast in toasts" :key="toast.id" class="toast-item" :class="'toast-' + toast.type">
          {{ toast.message }}
        </div>
      </transition-group>
    </div>

    <!-- Free tier CTA banner -->
    <div class="upgrade-banner mb-4" v-if="isFreeUser">
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-3">
        <div>
          <h6 class="mb-1 fw-bold text-white">{{ $t('dash.upgradeCta') }}</h6>
          <p class="mb-0 text-white-50 small">{{ $t('dash.upgradeCtaDesc') }}</p>
        </div>
        <button class="btn btn-light fw-bold" @click="showUpgradeModal = true">
          {{ $t('dash.upgradePlan') }}
        </button>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="row g-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card stat-card-blue">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ subscription.tier || 'Free' }}</div>
              <div class="stat-label">{{ $t('dash.subscriptionPlan') }}</div>
            </div>
            <div class="stat-icon-wrap stat-icon-blue">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                <path d="M5.5 9.511c.076.954.83 1.697 2.182 1.785V12h.6v-.709c1.4-.098 2.218-.846 2.218-1.932 0-.987-.626-1.496-1.745-1.76l-.473-.112V5.57c.6.068.982.396 1.074.85h1.052c-.076-.919-.864-1.638-2.126-1.716V4h-.6v.719c-1.195.117-2.01.836-2.01 1.853 0 .9.606 1.472 1.613 1.707l.397.098v2.034c-.615-.093-1.022-.43-1.114-.9H5.5zm2.177-2.166c-.59-.137-.91-.416-.91-.836 0-.47.345-.822.915-.925v1.76h-.005zm.692 1.193c.717.166 1.048.435 1.048.91 0 .542-.412.914-1.135.982V8.518l.087.02z"/>
                <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card stat-card-green stat-card--hero">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value stat-value--hero">{{ daysRemaining }}</div>
              <div class="stat-label">{{ $t('dash.daysRemaining') }}</div>
            </div>
            <div class="stat-icon-wrap stat-icon-green">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                <path d="M11 6.5a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1z"/>
                <path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card stat-card-orange">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ trafficUsedGB }} GB</div>
              <div class="stat-label">{{ $t('dash.trafficUsed') }}</div>
            </div>
            <div class="stat-icon-wrap stat-icon-orange">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                <path d="M0 0h1v15h15v1H0V0Zm14.817 3.113a.5.5 0 0 1 .07.704l-4.5 5.5a.5.5 0 0 1-.74.037L7.06 6.767l-3.656 5.027a.5.5 0 0 1-.808-.588l4-5.5a.5.5 0 0 1 .758-.06l2.609 2.61 4.15-5.073a.5.5 0 0 1 .704-.07Z"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card stat-card-purple">
          <div class="d-flex justify-content-between">
            <div>
              <div class="stat-value">{{ devices.length }}/{{ subscription.max_devices }}</div>
              <div class="stat-label">{{ $t('dash.activeDevices') }}</div>
            </div>
            <div class="stat-icon-wrap stat-icon-purple">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                <path d="M11 1a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1h6zM5 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H5z"/>
                <path d="M8 14a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Traffic Usage Charts -->
    <div class="row g-4 mb-4" v-if="subscription.traffic_limit_gb">
      <div class="col-md-4 col-lg-3">
        <div class="card h-100">
          <div class="card-body d-flex flex-column align-items-center justify-content-center text-center">
            <apexchart
              type="radialBar"
              height="180"
              :options="trafficGaugeOptions"
              :series="[subscription.traffic_percentage || 0]"
            />
            <div class="mt-1">
              <div class="fw-bold" style="font-size:1.05rem">{{ subscription.traffic_used_gb }} <small class="text-muted fw-normal">/ {{ subscription.traffic_limit_gb }} GB</small></div>
              <div class="text-muted small">{{ $t('dash.trafficUsage') }}</div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-md-8 col-lg-9">
        <div class="card h-100">
          <div class="card-body">
            <h6 class="mb-1">{{ $t('dash.trafficUsage') }}</h6>
            <div class="d-flex gap-4 mb-3">
              <div>
                <div class="fw-bold text-primary" style="font-size:1.1rem">{{ subscription.traffic_used_gb }} GB</div>
                <div class="text-muted small">{{ $t('dash.gbUsed', { amount: '' }).trim() || 'Used' }}</div>
              </div>
              <div>
                <div class="fw-bold text-success" style="font-size:1.1rem">{{ subscription.traffic_remaining_gb }} GB</div>
                <div class="text-muted small">{{ $t('dash.gbRemaining', { amount: '' }).trim() || 'Remaining' }}</div>
              </div>
              <div>
                <div class="fw-bold" style="font-size:1.1rem">{{ subscription.traffic_limit_gb }} GB</div>
                <div class="text-muted small">Limit</div>
              </div>
            </div>
            <div class="progress" style="height: 12px; border-radius: 6px;">
              <div class="progress-bar" :class="trafficPercentageClass" role="progressbar"
                :style="{ width: (subscription.traffic_percentage || 0) + '%', borderRadius: '6px', transition: 'width .6s ease' }">
              </div>
            </div>
            <div class="d-flex justify-content-between mt-2">
              <small class="text-muted">0 GB</small>
              <small class="text-muted">{{ subscription.traffic_limit_gb }} GB</small>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Subscription Details -->
    <div class="row g-4 mb-4">
      <div class="col-lg-8 d-flex flex-column">
        <div class="card flex-grow-1">
          <div class="card-header d-flex justify-content-between align-items-center">
            <h6 class="mb-0">{{ $t('dash.subscriptionDetails') }}</h6>
            <button class="btn btn-sm btn-primary" @click="showUpgradeModal = true">
              {{ $t('dash.upgradePlan') }}
            </button>
          </div>
          <div class="card-body">
            <div class="alert alert-warning mb-3" v-if="subscription.days_remaining != null && subscription.days_remaining < 7">
              {{ $t('dash.expiresWarning', { days: subscription.days_remaining }) }}
              <a href="#" @click.prevent="showUpgradeModal = true">{{ $t('dash.renewNow') }}</a>
            </div>
            <div class="sub-group-label">{{ $t('dash.subGroupPlan') }}</div>
            <div class="sub-details-grid mb-4">
              <div class="sub-detail-row">
                <span class="sub-detail-key">{{ $t('dash.plan') }}</span>
                <span class="sub-detail-val fw-semibold">{{ planName }}</span>
              </div>
              <div class="sub-detail-row">
                <span class="sub-detail-key">{{ $t('dash.status') }}</span>
                <span class="sub-detail-val"><span class="badge sub-status-badge" :class="statusBadgeClass">{{ statusLabel }}</span></span>
              </div>
              <div class="sub-detail-row">
                <span class="sub-detail-key">{{ $t('dash.expiryDate') }}</span>
                <span class="sub-detail-val">{{ expiryDate }}</span>
              </div>
              <div class="sub-detail-row" v-if="subscription.price_monthly_usd">
                <span class="sub-detail-key">{{ $t('dash.price') }}</span>
                <span class="sub-detail-val fw-semibold">${{ subscription.price_monthly_usd }}{{ $t('dash.perMonth') }}</span>
              </div>
            </div>
            <div class="sub-group-label">{{ $t('dash.subGroupLimits') }}</div>
            <div class="sub-details-grid">
              <div class="sub-detail-row">
                <span class="sub-detail-key">{{ $t('dash.maxDevices') }}</span>
                <span class="sub-detail-val">{{ $t('dash.devicesCount', { count: subscription.max_devices }) }}</span>
              </div>
              <div class="sub-detail-row">
                <span class="sub-detail-key">{{ $t('dash.bandwidth') }}</span>
                <span class="sub-detail-val">{{ bandwidthLimit }}</span>
              </div>
            </div>
            <div class="mt-4 pt-3 border-top" v-if="subscription.tier && subscription.tier.toLowerCase() !== 'free'">
              <button class="btn btn-sm btn-link btn-cancel-sub px-0"
                @click="cancelSubscription">
                {{ $t('dash.cancelSubscription') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions & Devices -->
      <div class="col-lg-4">
        <div class="card mb-4">
          <div class="card-header"><h6 class="mb-0">{{ $t('dash.quickActions') }}</h6></div>
          <div class="card-body">
            <div class="d-grid gap-2">
              <button class="btn btn-primary" @click="showAddDeviceModal = true"
                :disabled="creatingDevice || devices.length >= (subscription.max_devices || 1)"
                v-if="subscription.status === 'active'">
                <span v-if="creatingDevice" class="spinner-border spinner-border-sm me-1"></span>
                {{ $t('dash.addDevice') }}
              </button>
              <button class="btn btn-outline-secondary" @click="showUpgradeModal = true">
                {{ $t('dash.upgradePlan') }}
              </button>
              <button class="btn btn-link text-secondary px-0 text-start btn-change-password" @click="showChangePassword = true">
                {{ $t('dash.changePassword') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Devices List -->
        <div class="card" v-if="devices.length">
          <div class="card-header">
            <h6 class="mb-0">{{ $t('dash.myDevices') }} ({{ devices.length }}/{{ subscription.max_devices || 1 }})</h6>
          </div>
          <div class="list-group list-group-flush">
            <div class="device-item list-group-item"
              v-for="device in devices" :key="device.id"
              :class="{ 'active-device': selectedDevice?.id === device.id }"
              @click="selectedDevice = device">
              <div class="device-item__info">
                <div class="device-item__name">{{ device.name }}</div>
                <div class="device-item__ip">{{ device.ipv4 }}</div>
              </div>
              <div class="device-item__actions">
                <span class="badge device-status-badge" :class="device.enabled ? 'device-status-on' : 'device-status-off'">
                  {{ device.enabled ? $t('dash.deviceConnected') : $t('dash.deviceDisconnected') }}
                </span>
                <div class="device-btn-group">
                  <button class="btn btn-sm btn-outline-secondary device-action-btn" @click.stop="downloadDeviceConfig(device)" :title="$t('dash.downloadConfig')">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                  </button>
                  <button class="btn btn-sm btn-outline-secondary device-action-btn" @click.stop="showDeviceConfig(device)" title="QR">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M0 .5A.5.5 0 0 1 .5 0h3a.5.5 0 0 1 0 1H1v2.5a.5.5 0 0 1-1 0v-3Zm12 0a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v3a.5.5 0 0 1-1 0V1h-2.5a.5.5 0 0 1-.5-.5ZM.5 12a.5.5 0 0 1 .5.5V15h2.5a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5v-3a.5.5 0 0 1 .5-.5Zm15 0a.5.5 0 0 1 .5.5v3a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1 0-1H15v-2.5a.5.5 0 0 1 .5-.5ZM4 4h1v1H4V4Zm2 0h1v1H6V4Zm-1 1h1v1H5V5Zm1 1h1v1H6V6Zm-2 0h1v1H4V6ZM7 4h1v4H7V4Zm2 0h2v1H9V4Zm0 2h2v1H9V6Zm1-1h1v1h-1V5Zm-1 3h2v1H9V7ZM4 8h1v2H4V8Zm2 0h1v1H6V8Zm0 2h1v1H6v-1Zm1-1h1v2H7V9Zm2 0h1v1H9V9Zm0 2h2v1H9v-1Zm1-1h1v1h-1v-1Z"/></svg>
                  </button>
                  <button class="btn btn-sm btn-outline-danger device-action-btn" @click.stop="deleteDevice(device)" :title="$t('dash.deleteDevice')">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H5.5l1-1h3l1 1h2.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="alert alert-info mt-3" v-if="!devices.length && subscription.status === 'active'">
          {{ $t('dash.noDevicesYet') }}
        </div>
      </div>
    </div>

    <!-- Referral & Auto-renew -->
    <div class="row g-4 mb-4">
      <div class="col-lg-8">
        <div class="card">
          <div class="card-header d-flex align-items-center justify-content-between">
            <div>
              <h6 class="mb-0 d-flex align-items-center gap-2">{{ $t('dash.referralProgram') }}<HelpTooltip :text="$t('help.referral')" /></h6>
              <small class="text-muted">{{ $t('dash.referralInviteHint') }}</small>
            </div>
            <span class="badge bg-success-subtle text-success referral-count-badge" v-if="referral.referral_count">
              {{ referral.referral_count }} {{ $t('dash.referralCount') }}
            </span>
          </div>
          <div class="card-body">
            <div v-if="referral.referral_code">
              <label class="text-secondary small mb-1 d-block">{{ $t('dash.referralLink') }}</label>
              <div class="link-input-group">
                <code class="link-input-group__text">{{ referralLink }}</code>
                <button class="link-input-group__btn" :class="copyFeedback ? 'link-input-group__btn--done' : ''" @click="copyReferralLink">
                  {{ copyFeedback ? ($t('common.copied')) : ($t('common.copy')) }}
                </button>
              </div>
            </div>
            <div v-else class="text-muted small py-2">{{ $t('common.loading') }}</div>
          </div>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="card h-100">
          <div class="card-header"><h6 class="mb-0 d-flex align-items-center">{{ $t('dash.autoRenew') }}<HelpTooltip :text="$t('help.autoRenew')" /></h6></div>
          <div class="card-body d-flex flex-column justify-content-center">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="autoRenewToggle" v-model="autoRenew" @change="toggleAutoRenew">
              <label class="form-check-label auto-renew-label" for="autoRenewToggle">
                {{ autoRenew ? ($t('dash.autoRenewOn')) : ($t('dash.autoRenewOff')) }}
              </label>
            </div>
            <small class="auto-renew-hint mt-2">{{ $t('dash.autoRenewHint') }}</small>
          </div>
        </div>
      </div>
    </div>

    <!-- Subscription Link -->
    <div class="row g-4 mb-4" v-if="subscription.tier && subscription.tier.toLowerCase() !== 'free'">
      <div class="col-12">
        <div class="card">
          <div class="card-header"><h6 class="mb-0 d-flex align-items-center">{{ $t('dash.subscriptionLink') }}<HelpTooltip :text="$t('help.subscriptionLink')" /></h6></div>
          <div class="card-body">
            <p class="text-muted small mb-3">{{ $t('dash.subscriptionLinkDesc') }}</p>
            <div v-if="subLinkToken">
              <div class="link-input-group mb-2">
                <code class="link-input-group__text">{{ subLinkUrl }}</code>
                <button class="link-input-group__btn" :class="subLinkCopied ? 'link-input-group__btn--done' : ''" @click="copySubLink">
                  {{ subLinkCopied ? $t('common.copied') : $t('common.copy') }}
                </button>
              </div>
              <button class="btn btn-sm btn-outline-secondary" @click="regenerateSubLink">{{ $t('dash.regenerate') }}</button>
            </div>
            <div v-else>
              <button class="btn btn-sm btn-primary" @click="loadSubLink">{{ $t('dash.generateLink') }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Payments -->
    <div class="row g-4">
      <div class="col-12">
        <div class="card">
          <div class="card-header d-flex justify-content-between align-items-center">
            <h6 class="mb-0">{{ $t('dash.recentPayments') }}</h6>
            <router-link to="/payments" class="btn btn-sm btn-outline-primary">{{ $t('dash.viewAll') }}</router-link>
          </div>
          <div class="table-responsive">
            <table class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>{{ $t('dash.date') }}</th>
                  <th>{{ $t('dash.amount') }}</th>
                  <th>{{ $t('dash.method') }}</th>
                  <th>{{ $t('common.status') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="payment in recentPayments" :key="payment.invoice_id">
                  <td>{{ formatDate(payment.created_at) }}</td>
                  <td>${{ payment.amount_usd }}</td>
                  <td><span class="badge bg-secondary">{{ payment.payment_method }}</span></td>
                  <td><span class="badge" :class="getPaymentStatusClass(payment.status)">{{ payment.status }}</span></td>
                </tr>
                <tr v-if="recentPayments.length === 0">
                  <td colspan="4" class="text-center text-muted py-4">{{ $t('dash.noPaymentsYet') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- QR Modal -->
    <transition name="modal">
      <div v-if="showConfigModal" class="modal-overlay" @click.self="showConfigModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <h5 class="modal-title">{{ configDeviceName }}</h5>
            <button type="button" class="btn-close" @click="showConfigModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="text-center">
              <div v-if="qrUrl">
                <img :src="qrUrl" alt="QR Code" class="img-fluid" style="max-width: 280px" />
                <p class="text-muted small mt-2">{{ qrHintText }}</p>
              </div>
              <div v-else class="py-4"><div class="spinner-border text-primary"></div></div>
            </div>
            <div v-if="configUri" class="mt-3">
              <label class="form-label small text-muted mb-1">{{ $t('dash.connectionLink') }}</label>
              <div class="input-group">
                <input type="text" class="form-control font-monospace" :value="configUri" readonly>
                <button type="button" class="btn btn-outline-secondary" @click="copyConfigUri">{{ $t('common.copy') }}</button>
              </div>
            </div>
            <div v-if="configText" class="mt-3">
              <label class="form-label small text-muted mb-1">{{ configLabelText }}</label>
              <textarea class="form-control font-monospace" rows="8" :value="configText" readonly></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showConfigModal = false">{{ $t('common.close') }}</button>
            <button v-if="configUri" type="button" class="btn btn-outline-secondary" @click="copyConfigUri">{{ $t('common.copy') }}</button>
            <button v-if="qrUrl" type="button" class="btn btn-outline-primary" @click="downloadQRImage">{{ $t('dash.downloadQR') }}</button>
            <button type="button" class="btn btn-primary" @click="downloadCurrentConfig">{{ downloadConfigButtonText }}</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Change Password Modal -->
    <transition name="modal">
      <div v-if="showChangePassword" class="modal-overlay" @click.self="showChangePassword = false">
        <div class="modal-box">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('dash.changePassword') }}</h5>
            <button type="button" class="btn-close" @click="showChangePassword = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('dash.currentPassword') }}</label>
              <input type="password" class="form-control" v-model="passwordForm.current_password">
            </div>
            <div class="mb-3">
              <label class="form-label">{{ $t('dash.newPassword') }}</label>
              <input type="password" class="form-control" v-model="passwordForm.new_password" minlength="8">
            </div>
            <div class="alert alert-danger" v-if="passwordError">{{ passwordError }}</div>
            <div class="alert alert-success" v-if="passwordSuccess">{{ passwordSuccess }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showChangePassword = false">{{ $t('common.close') }}</button>
            <button class="btn btn-primary" @click="changePassword" :disabled="changingPassword">
              <span v-if="changingPassword" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('dash.changePassword') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Add Device Modal with Server Selection -->
    <transition name="modal">
      <div v-if="showAddDeviceModal" class="modal-overlay" @click.self="showAddDeviceModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('dash.addDevice') }}</h5>
            <button type="button" class="btn-close" @click="showAddDeviceModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">{{ $t('dash.deviceName') }}</label>
              <input
                type="text"
                class="form-control"
                v-model="newDeviceName"
                :placeholder="$t('dash.deviceNamePlaceholder')"
                maxlength="64"
                @keyup.enter="createDevice"
              />
            </div>
            <div class="mb-3" v-if="servers.length > 1">
              <label class="form-label">{{ $t('dash.selectServer') }}</label>
              <select class="form-select" v-model="selectedServerId">
                <option :value="null">{{ $t('dash.autoDefaultServer') }}</option>
                <option v-for="s in servers" :key="s.id" :value="s.id">
                  {{ formatServerOption(s) }}
                </option>
              </select>
            </div>
            <div v-if="selectedServerMeta" class="mt-2">
              <span class="badge bg-light text-dark border">{{ protocolLabel(selectedServerMeta.server_type) }}</span>
            </div>
            <p class="text-muted small" v-if="servers.length <= 1">{{ $t('dash.newDeviceOnDefault') }}</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showAddDeviceModal = false">{{ $t('common.close') }}</button>
            <button class="btn btn-success" @click="createDevice" :disabled="creatingDevice">
              <span v-if="creatingDevice" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('dash.addDevice') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Notification Bell Dropdown -->
    <div class="notification-bell" v-if="notifications.length > 0">
      <button class="btn btn-sm btn-warning position-relative" @click="showNotifDropdown = !showNotifDropdown">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
          <path d="M8 16a2 2 0 0 0 2-2H6a2 2 0 0 0 2 2zM8 1.918l-.797.161A4.002 4.002 0 0 0 4 6c0 .628-.134 2.197-.459 3.742-.16.767-.376 1.566-.663 2.258h10.244c-.287-.692-.502-1.49-.663-2.258C12.134 8.197 12 6.628 12 6a4.002 4.002 0 0 0-3.203-3.92L8 1.917z"/>
        </svg>
        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger" style="font-size: 0.6rem;">
          {{ notifications.length }}
        </span>
      </button>
      <div class="notif-dropdown" v-if="showNotifDropdown" @mouseleave="showNotifDropdown = false">
        <div class="notif-item" v-for="n in notifications" :key="n.id" @click="dismissNotification(n.id)">
          <strong>{{ n.title }}</strong>
          <div class="small text-muted">{{ n.message }}</div>
        </div>
      </div>
    </div>

    <!-- Payment Modal -->
    <PaymentModal v-if="showUpgradeModal" @close="showUpgradeModal = false" @success="onPaymentSuccess" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import PaymentModal from './PaymentModal.vue'
import { formatDate } from '../utils'

const router = useRouter()
const { t } = useI18n()

const subscription = ref({})
const devices = ref([])
const recentPayments = ref([])
const showUpgradeModal = ref(false)
const selectedDevice = ref(null)
const showConfigModal = ref(false)
const configText = ref('')
const configDeviceName = ref('')
const qrUrl = ref(null)
const configUri = ref('')
const configProtocol = ref('wireguard')
const creatingDevice = ref(false)
const newDeviceName = ref('')
const showChangePassword = ref(false)
const referral = ref({ referral_code: '', referral_count: 0, paid_referrals: 0 })
const autoRenew = ref(false)
const passwordForm = ref({ current_password: '', new_password: '' })
const passwordError = ref(null)
const passwordSuccess = ref(null)
const changingPassword = ref(false)
const copyFeedback = ref(false)
const showAddDeviceModal = ref(false)
const servers = ref([])
const selectedServerId = ref(null)
const subLinkToken = ref(null)
const subLinkCopied = ref(false)
const notifications = ref([])
const showNotifDropdown = ref(false)

// Toast system
const toasts = ref([])
let toastId = 0
const showToast = (message, type = 'success') => {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 3000)
}

const isFreeUser = computed(() => {
  const tier = (subscription.value.tier || 'free').toLowerCase()
  return tier === 'free'
})

const daysRemaining = computed(() => subscription.value.days_remaining != null ? subscription.value.days_remaining : '∞')
const trafficUsedGB = computed(() => (subscription.value.traffic_used_gb ?? 0).toFixed(2))
const trafficPercentageClass = computed(() => {
  const pct = subscription.value.traffic_percentage || 0
  if (pct >= 90) return 'bg-danger'
  if (pct >= 70) return 'bg-warning'
  return 'bg-success'
})

const trafficGaugeOptions = computed(() => {
  const pct = subscription.value.traffic_percentage || 0
  const color = pct >= 90 ? '#EA5455' : pct >= 70 ? '#FF9F43' : '#28C76F'
  return {
    chart: { type: 'radialBar', toolbar: { show: false }, fontFamily: 'Inter, sans-serif', animations: { enabled: true, speed: 800 } },
    colors: [color],
    plotOptions: {
      radialBar: {
        startAngle: -135,
        endAngle: 135,
        hollow: { margin: 0, size: '65%', background: 'transparent' },
        track: { background: 'var(--vxy-progress-bg)', strokeWidth: '97%' },
        dataLabels: {
          name: { show: false },
          value: { offsetY: 6, fontSize: '22px', fontWeight: 700, color: color, formatter: v => `${Math.round(v)}%` }
        }
      }
    },
    fill: { type: 'solid' },
    stroke: { lineCap: 'round' },
    labels: ['Traffic'],
  }
})
const planName = computed(() => {
  const tier = subscription.value.tier || 'free'
  return tier.charAt(0).toUpperCase() + tier.slice(1)
})
const expiryDate = computed(() => subscription.value.expiry_date ? new Date(subscription.value.expiry_date).toLocaleDateString() : t('dash.never'))
const statusBadgeClass = computed(() => subscription.value.status === 'active' ? 'bg-success' : 'bg-secondary')
const statusLabel = computed(() => {
  const map = { active: t('dash.statusActive'), inactive: t('dash.statusInactive'), expired: t('dash.statusExpired') }
  return map[subscription.value.status] || subscription.value.status
})
const bandwidthLimit = computed(() => subscription.value.bandwidth_limit_mbps ? `${subscription.value.bandwidth_limit_mbps} Mbps` : t('dash.unlimited'))
const referralLink = computed(() => referral.value.referral_code ? `${window.location.origin}/register?ref=${referral.value.referral_code}` : '')
const selectedServerMeta = computed(() => {
  if (selectedServerId.value == null) return null
  return servers.value.find(s => s.id === selectedServerId.value) || null
})

const protocolLabel = (serverType) => {
  switch ((serverType || 'wireguard').toLowerCase()) {
    case 'wireguard': return 'WireGuard'
    case 'amneziawg': return 'AmneziaWG'
    case 'hysteria2': return 'Hysteria2'
    case 'tuic': return 'TUIC'
    default: return serverType || 'WireGuard'
  }
}

const formatServerOption = (server) => {
  const name = server.name || 'Server'
  const protocol = protocolLabel(server.server_type)
  return `${name} [${protocol}]`
}

const qrHintText = computed(() => (
  (configProtocol.value || '').toLowerCase() === 'wireguard'
    ? t('dash.scanQR')
    : t('dash.scanProxyQR')
))

const configLabelText = computed(() => (
  (configProtocol.value || '').toLowerCase() === 'wireguard'
    ? t('dash.wireguardConfig')
    : t('dash.connectionConfig')
))

const downloadConfigButtonText = computed(() => {
  switch ((configProtocol.value || '').toLowerCase()) {
    case 'hysteria2':
      return t('dash.downloadYaml')
    case 'tuic':
      return t('dash.downloadJson')
    default:
      return t('dash.downloadConf')
  }
})


const loadData = async () => {
  try {
    const [subData, paymentsData] = await Promise.all([
      portalApi.getSubscription(),
      portalApi.getPaymentHistory(5)
    ])
    subscription.value = subData.data
    autoRenew.value = !!subData.data.auto_renew
    recentPayments.value = paymentsData.data
  } catch (error) {
    if (error.response?.status === 401) router.push('/login')
  }
  await loadDevices()
}

const getPaymentStatusClass = (status) => {
  switch (status) {
    case 'completed': return 'bg-success'
    case 'pending': return 'bg-warning'
    case 'failed': return 'bg-danger'
    default: return 'bg-secondary'
  }
}

const loadDevices = async () => {
  try {
    const { data } = await portalApi.getDevices()
    devices.value = data
    if (data.length && !selectedDevice.value) selectedDevice.value = data[0]
  } catch (error) { /* ignore */ }
}

const showDeviceConfig = async (device) => {
  configDeviceName.value = device.name
  configText.value = ''
  configUri.value = ''
  configProtocol.value = (device.server_type || 'wireguard').toLowerCase()
  qrUrl.value = null

  try {
    const { data } = await portalApi.getConfig(device.id)
    configText.value = data.config_text || data.config || data
    configUri.value = data.uri || ''
    configProtocol.value = (data.protocol || device.server_type || 'wireguard').toLowerCase()
    configDeviceName.value = data.client_name || device.name
    showConfigModal.value = true

    try {
      const qrRes = await portalApi.getQRCode(device.id)
      qrUrl.value = URL.createObjectURL(qrRes.data)
    } catch { qrUrl.value = null }
  } catch (err) {
    showToast(t('common.error') + ': ' + (err.response?.data?.detail || err.message), 'error')
  }
}

const configExtension = (protocol) => {
  switch ((protocol || '').toLowerCase()) {
    case 'hysteria2':
      return 'yaml'
    case 'tuic':
      return 'json'
    default:
      return 'conf'
  }
}

const downloadCurrentConfig = () => {
  if (!configText.value) return
  const blob = new Blob([configText.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${configDeviceName.value || 'client'}.${configExtension(configProtocol.value)}`; a.click()
  URL.revokeObjectURL(url)
}

const downloadQRImage = () => {
  if (!qrUrl.value) return
  const a = document.createElement('a')
  a.href = qrUrl.value; a.download = `${configDeviceName.value || 'wireguard'}-qr.png`; a.click()
}

const downloadDeviceConfig = async (device) => {
  try {
    const { data } = await portalApi.getConfig(device.id)
    const config = data.config_text || data.config || data
    const name = data.client_name || device.name
    const protocol = data.protocol || device.server_type || 'wireguard'
    const blob = new Blob([config], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${name}.${configExtension(protocol)}`; a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    showToast(t('common.error') + ': ' + (err.response?.data?.detail || err.message), 'error')
  }
}

const copyConfigUri = async () => {
  if (!configUri.value) return
  try {
    await navigator.clipboard.writeText(configUri.value)
    showToast(t('common.copied'))
  } catch (error) {
    showToast(t('common.error') + ': ' + (error.message || 'copy failed'), 'error')
  }
}

const createDevice = async () => {
  creatingDevice.value = true
  try {
    const { data } = await portalApi.createDevice(selectedServerId.value, newDeviceName.value.trim() || null)
    const protocol = protocolLabel(data.server_type || selectedServerMeta.value?.server_type)
    const message = data.ipv4
      ? t('dash.deviceCreated', { name: data.name, ip: data.ipv4 })
      : `${t('dash.deviceCreated', { name: data.name, ip: '' })} [${protocol}]`
    showToast(message)
    showAddDeviceModal.value = false
    selectedServerId.value = null
    newDeviceName.value = ''
    await loadDevices()
  } catch (error) {
    showToast(t('common.error') + ': ' + (error.response?.data?.detail || error.message), 'error')
  } finally {
    creatingDevice.value = false
  }
}

const deleteDevice = async (device) => {
  if (!confirm(t('dash.deleteDeviceConfirm', { name: device.name }))) return
  try {
    await portalApi.deleteDevice(device.id)
    showToast(t('dash.deviceDeleted'))
    await loadDevices()
  } catch (error) {
    showToast(t('common.error') + ': ' + (error.response?.data?.detail || error.message), 'error')
  }
}

const cancelSubscription = async () => {
  if (!confirm(t('dash.cancelConfirm'))) return
  try {
    await portalApi.cancelSubscription()
    await loadData()
    showToast(t('dash.cancelDone'))
  } catch (error) {
    showToast(t('common.error') + ': ' + (error.response?.data?.detail || error.message), 'error')
  }
}

const changePassword = async () => {
  changingPassword.value = true
  passwordError.value = null
  passwordSuccess.value = null
  try {
    await portalApi.changePassword(passwordForm.value)
    passwordSuccess.value = t('dash.passwordChanged')
    passwordForm.value = { current_password: '', new_password: '' }
    setTimeout(() => { showChangePassword.value = false; passwordSuccess.value = null }, 2000)
  } catch (error) {
    passwordError.value = error.response?.data?.detail || t('common.error')
  } finally {
    changingPassword.value = false
  }
}

const loadReferral = async () => {
  try {
    const { data } = await portalApi.getReferral()
    referral.value = data
  } catch (e) { /* ignore */ }
}

const copyReferralLink = () => {
  navigator.clipboard.writeText(referralLink.value)
  copyFeedback.value = true
  setTimeout(() => { copyFeedback.value = false }, 2000)
}

const toggleAutoRenew = async () => {
  try {
    await portalApi.toggleAutoRenew(autoRenew.value)
  } catch (e) {
    autoRenew.value = !autoRenew.value
    showToast(t('common.error') + ': ' + (e.response?.data?.detail || e.message), 'error')
  }
}

const onPaymentSuccess = () => {
  showUpgradeModal.value = false
  loadData()
  showToast(t('dash.paymentSuccess'))
}

// Server list for device creation
const loadServers = async () => {
  try {
    const { data } = await portalApi.getServers()
    servers.value = data || []
  } catch (e) { /* ignore */ }
}

// Subscription link
const subLinkUrl = computed(() => subLinkToken.value ? `${window.location.origin}/client-portal/sub/${subLinkToken.value}` : '')

const loadSubLink = async () => {
  try {
    const { data } = await portalApi.getSubscriptionLink()
    subLinkToken.value = data.token
  } catch (e) { /* ignore */ }
}

const copySubLink = () => {
  navigator.clipboard.writeText(subLinkUrl.value)
  subLinkCopied.value = true
  setTimeout(() => { subLinkCopied.value = false }, 2000)
}

const regenerateSubLink = async () => {
  try {
    const { data } = await portalApi.regenerateSubscriptionLink()
    subLinkToken.value = data.token
    showToast(t('dash.linkRegenerated'))
  } catch (e) {
    showToast(t('dash.linkRegenerateFailed'), 'error')
  }
}

// Notifications
const loadNotifications = async () => {
  try {
    const { data } = await portalApi.getNotifications()
    notifications.value = data
  } catch (e) { /* ignore */ }
}

const dismissNotification = async (id) => {
  try {
    await portalApi.markNotificationRead(id)
    notifications.value = notifications.value.filter(n => n.id !== id)
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  if (!localStorage.getItem('client_access_token')) { router.push('/login'); return }
  loadData()
  loadReferral()
  loadServers()
  loadSubLink()
  loadNotifications()

  // Poll notifications every 60s
  notifIntervalId = setInterval(loadNotifications, 60000)
})

let notifIntervalId = null
onUnmounted(() => {
  if (notifIntervalId) clearInterval(notifIntervalId)
})
</script>

<style scoped>
/* ── Vuexy Stat Cards ──────────────────────────────────────── */
.stat-card {
  background: var(--vxy-card-bg);
  border-radius: var(--vxy-card-radius);
  box-shadow: var(--vxy-card-shadow);
  padding: 1.25rem;
  transition: box-shadow .2s, transform .2s;
  overflow: hidden;
  position: relative;
  height: 100%;
}
.stat-card:hover { box-shadow: 0 10px 32px rgba(34,41,47,.18); transform: translateY(-3px); }

/* align icon and text block to center vertically */
.stat-card .d-flex { align-items: center; }

.stat-value { font-size: 1.6rem; font-weight: 700; color: var(--vxy-heading); line-height: 1.2; margin-bottom: .2rem; }
.stat-value--hero { font-size: 2rem; }
.stat-label { font-size: .78rem; color: var(--vxy-muted); text-transform: uppercase; letter-spacing: .04em; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Hero card */
.stat-card--hero { box-shadow: 0 4px 20px rgba(40,199,111,.18); }

.stat-icon-wrap { width: 48px; height: 48px; border-radius: .5rem; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-icon-blue   { background: var(--vxy-primary-light); color: var(--vxy-primary); }
.stat-icon-green  { background: var(--vxy-success-light); color: var(--vxy-success); }
.stat-icon-orange { background: var(--vxy-warning-light); color: var(--vxy-warning); }
.stat-icon-purple { background: var(--vxy-info-light);    color: var(--vxy-info); }

/* colored top border */
.stat-card-blue   { border-top: 3px solid var(--vxy-primary); }
.stat-card-green  { border-top: 3px solid var(--vxy-success); }
.stat-card-orange { border-top: 3px solid var(--vxy-warning); }
.stat-card-purple { border-top: 3px solid var(--vxy-info); }

/* ── Upgrade banner ────────────────────────────────────────── */
.upgrade-banner {
  background: linear-gradient(118deg, var(--vxy-primary), #9e95f5);
  border-radius: var(--vxy-card-radius);
  padding: 1.25rem 1.5rem;
  box-shadow: 0 8px 24px rgba(115,103,240,.35);
  position: relative; overflow: hidden;
}
.upgrade-banner::before {
  content: ''; position: absolute; top: -30px; right: -30px;
  width: 160px; height: 160px; border-radius: 50%;
  background: rgba(255,255,255,.08); pointer-events: none;
}

/* ── Active device highlight ───────────────────────────────── */
.active-device { border-left: 3px solid var(--vxy-primary) !important; background: var(--vxy-hover-bg); }

/* ── App download card ─────────────────────────────────────── */
.app-download-card { background: var(--vxy-success-light); border: 1px solid var(--vxy-success); border-radius: var(--vxy-card-radius); }
.app-icon-wrap { width: 48px; height: 48px; border-radius: .5rem; background: var(--vxy-success-light); color: var(--vxy-success); display: flex; align-items: center; justify-content: center; }

/* ── Toast notifications ───────────────────────────────────── */
.toast-container { position: fixed; top: 80px; right: 1.5rem; z-index: 1100; display: flex; flex-direction: column; gap: .5rem; }
.toast-item { padding: .75rem 1.25rem; border-radius: .5rem; color: #fff; font-weight: 500; font-size: .875rem; box-shadow: 0 4px 12px rgba(0,0,0,.15); max-width: 360px; }
.toast-success { background: var(--vxy-success); }
.toast-error   { background: var(--vxy-danger); }
.toast-enter-active { animation: toastIn .3s ease; }
.toast-leave-active { animation: toastOut .3s ease; }
@keyframes toastIn  { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
@keyframes toastOut { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(40px); } }

/* ── Custom modal overlay ──────────────────────────────────── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(34,41,47,.5); z-index: 1050;
  display: flex; align-items: center; justify-content: center; padding: 1rem;
}
.modal-box {
  background: var(--vxy-modal-bg); border-radius: .75rem; width: 100%; max-width: 500px;
  box-shadow: 0 20px 60px rgba(0,0,0,.3); color: var(--vxy-text);
}
.modal-box .modal-header { padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--vxy-border); display: flex; justify-content: space-between; align-items: center; }
.modal-box .modal-body   { padding: 1.25rem; }
.modal-box .modal-footer { padding: 1rem 1.5rem; border-top: 1px solid var(--vxy-border); display: flex; justify-content: flex-end; gap: .5rem; }

.modal-enter-active { animation: modalIn .25s ease; }
.modal-leave-active { animation: modalOut .2s ease; }
@keyframes modalIn  { from { opacity: 0; } to { opacity: 1; } }
@keyframes modalOut { from { opacity: 1; } to { opacity: 0; } }
.modal-enter-active .modal-box { animation: modalBoxIn .25s ease; }
.modal-leave-active .modal-box { animation: modalBoxOut .2s ease; }
@keyframes modalBoxIn  { from { opacity: 0; transform: scale(.95) translateY(-10px); } to { opacity: 1; transform: scale(1) translateY(0); } }
@keyframes modalBoxOut { from { opacity: 1; transform: scale(1) translateY(0); } to { opacity: 0; transform: scale(.95) translateY(-10px); } }

/* ── Notification bell ─────────────────────────────────────── */
.notification-bell { position: fixed; top: 80px; left: 1.5rem; z-index: 1050; }
.notif-dropdown {
  position: absolute; top: 100%; left: 0; margin-top: .25rem;
  background: var(--vxy-card-bg); border: 1px solid var(--vxy-border);
  border-radius: .5rem; box-shadow: 0 8px 24px rgba(0,0,0,.15);
  min-width: 280px; max-height: 300px; overflow-y: auto; z-index: 1100;
}
.notif-item { padding: .75rem 1rem; border-bottom: 1px solid var(--vxy-border); cursor: pointer; transition: background .15s; }
.notif-item:hover { background: var(--vxy-hover-bg); }
.notif-item:last-child { border-bottom: none; }

.device-action-btn { width: 32px; height: 32px; min-width: 32px !important; min-height: 32px !important; padding: 0 !important; display: flex; align-items: center; justify-content: center; }

/* ── Subscription details grid ─────────────────────────────── */
.sub-group-label {
  font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: var(--vxy-muted);
  margin-bottom: .5rem;
}
.sub-details-grid { display: flex; flex-direction: column; gap: 0; }
.sub-detail-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: .5rem 0; border-bottom: 1px solid rgba(125,125,125,.1);
}
.sub-detail-row:last-child { border-bottom: none; }
.sub-detail-key { font-size: .875rem; color: var(--vxy-muted); }
.sub-detail-val { font-size: .875rem; color: var(--vxy-text); text-align: right; font-weight: 500; }
.sub-status-badge { font-size: .7rem; padding: .2em .5em; border-radius: .3rem; }

/* ── Cancel subscription ───────────────────────────────────── */
.btn-cancel-sub {
  font-size: .8rem !important; color: rgba(220,53,69,.6) !important;
  text-decoration: none !important; transition: color .15s, opacity .15s;
}
.btn-cancel-sub:hover { color: #dc3545 !important; text-decoration: underline !important; }

/* ── Change password button ────────────────────────────────── */
.btn-change-password {
  padding-top: .45rem !important; padding-bottom: .45rem !important;
  text-decoration: none !important; border-radius: .25rem;
  transition: background .15s, color .15s !important;
}
.btn-change-password:hover { background: var(--vxy-hover-bg); text-decoration: underline !important; }

/* ── Device list items ─────────────────────────────────────── */
.device-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: .75rem 1rem; cursor: pointer; gap: .75rem;
  transition: background .15s;
}
.device-item:hover { background: var(--vxy-hover-bg); }
.device-item__info { min-width: 0; flex: 1; }
.device-item__name { font-weight: 600; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.device-item__ip { font-size: .78rem; color: var(--vxy-muted); opacity: .65; }
.device-item__actions { display: flex; align-items: center; gap: .375rem; flex-shrink: 0; }
.device-btn-group { display: flex; gap: .3rem; align-items: center; }
.device-status-badge { font-size: .7rem; padding: .18em .45em; border-radius: .3rem; white-space: nowrap; }
.device-status-on  { background: var(--vxy-success-light); color: var(--vxy-success); }
.device-status-off { background: var(--vxy-border); color: var(--vxy-muted); }
/* softer danger for delete */
.device-action-btn.btn-outline-danger { color: rgba(220,53,69,.65) !important; border-color: rgba(220,53,69,.3) !important; }
.device-action-btn.btn-outline-danger:hover { color: #dc3545 !important; border-color: #dc3545 !important; background: rgba(220,53,69,.08) !important; }

/* ── Link input group ──────────────────────────────────────── */
.link-input-group {
  display: flex; align-items: stretch;
  border: 1px solid var(--vxy-border); border-radius: .375rem;
  overflow: hidden; background: var(--vxy-input-bg, var(--vxy-card-bg));
}
.link-input-group__text {
  flex: 1; padding: .45rem .65rem; font-size: .8rem;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
  color: var(--vxy-text); background: transparent; border: none;
  font-family: var(--bs-font-monospace, monospace);
}
.link-input-group__btn {
  flex-shrink: 0; padding: .45rem .75rem; font-size: .8rem; font-weight: 500;
  border: none; border-left: 1px solid rgba(125,125,125,.15);
  background: var(--vxy-hover-bg); color: var(--vxy-primary);
  cursor: pointer; transition: background .15s, color .15s; white-space: nowrap;
}
.link-input-group__btn:hover { background: var(--vxy-primary-light); }
.link-input-group__btn--done { color: var(--vxy-success); }

/* ── Auto-renew ────────────────────────────────────────────── */
.auto-renew-label { font-size: .875rem; color: var(--vxy-text); font-weight: 500; }
.auto-renew-hint { font-size: .8rem; color: var(--vxy-muted); opacity: .7; display: block; }

/* ── Referral count badge ──────────────────────────────────── */
.referral-count-badge { font-size: .75rem; padding: .35em .7em; }

/* ── Mobile ────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .stat-card { padding: 1rem; }
  .stat-value { font-size: 1.35rem; }
  .stat-value--hero { font-size: 1.7rem; }
  .stat-icon-wrap { width: 40px; height: 40px; }
  .stat-icon-wrap svg { width: 20px; height: 20px; }
  .toast-container { right: .75rem; left: .75rem; }
  .toast-item { max-width: 100%; }
  .notification-bell { top: 70px; left: .75rem; }
  .modal-box { max-width: calc(100% - 1rem); }
  .modal-box .modal-header { padding: .875rem 1rem; }
  .modal-box .modal-body { padding: 1rem; }
  .modal-box .modal-footer { padding: .75rem 1rem; flex-wrap: wrap; gap: .5rem; }
  .modal-box .modal-footer .btn { flex: 1; min-width: 0; min-height: 40px; }
  /* Touch-friendly buttons */
  .btn { min-height: 40px; }
  .btn-sm { min-height: 34px; }
  /* Upgrade banner compact */
  .upgrade-banner { padding: 1rem; }
  /* Device items: stack actions below info */
  .device-item { flex-direction: column; align-items: flex-start; }
  .device-item__actions { width: 100%; justify-content: space-between; margin-top: .4rem; }
  .device-action-btn { width: 40px !important; height: 40px !important; min-width: 40px !important; min-height: 40px !important; }
  /* prevent sub-detail values from wrapping oddly */
  .sub-detail-row { flex-wrap: nowrap; gap: .5rem; }
  .sub-detail-val { flex-shrink: 0; }
}
@media (max-width: 576px) {
  .stat-card { padding: .875rem .75rem; }
  .stat-value { font-size: 1.15rem; }
  .stat-value--hero { font-size: 1.45rem; }
  .stat-label { font-size: .72rem; }
  .stat-icon-wrap { width: 36px; height: 36px; }
  .stat-icon-wrap svg { width: 18px; height: 18px; }
  /* Notif dropdown full width */
  .notif-dropdown { min-width: unset; width: calc(100vw - 1.5rem); left: 0; right: 0; }
  /* Bottom sheet modals */
  .modal-overlay { align-items: flex-end; padding: 0; }
  .modal-box {
    max-width: 100%; border-radius: 1rem 1rem 0 0;
    padding-bottom: env(safe-area-inset-bottom, 0px);
    animation: modalSlideUp .3s ease;
  }
  .modal-box::before {
    content: ''; display: block;
    width: 36px; height: 4px; border-radius: 2px;
    background: var(--vxy-border);
    margin: .75rem auto 0;
  }
}
@keyframes modalSlideUp {
  from { transform: translateY(60px); opacity: .8; }
  to   { transform: translateY(0);    opacity: 1; }
}
</style>
