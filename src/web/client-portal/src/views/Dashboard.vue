<template>
  <div class="fx-page">
    <!-- Toasts -->
    <div class="fx-toast-wrap">
      <transition-group name="fx-toast-fade">
        <div v-for="t in toasts" :key="t.id" class="fx-toast" :class="t.type">{{ t.message }}</div>
      </transition-group>
    </div>

    <!-- Page head -->
    <div class="fx-page-head">
      <div>
        <h1 class="fx-page-title">{{ welcomeText }}</h1>
        <p class="fx-page-sub">{{ $t('dash.welcomeSub') }}</p>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap">
        <button class="fx-btn fx-btn-secondary" @click="loadData" :disabled="refreshing">
          <FxIcon name="refresh" :size="14" />
          {{ refreshing ? $t('common.loading') : $t('dash.refreshStatus') }}
        </button>
      </div>
    </div>

    <!-- Connection status banner — real data only, no fabricated metrics. -->
    <div class="fx-status-card fx-card">
      <div class="fx-status-row">
        <span class="fx-status-orb" :class="orbClass"></span>
        <div class="fx-status-info">
          <div class="fx-status-title">{{ statusTitle }}</div>
          <div class="fx-status-sub">
            <template v-if="primaryDevice">
              <span style="font-family:var(--mono); font-size:11px">{{ primaryDevice.ipv4 || '—' }}</span>
              <span style="margin:0 6px; color:var(--text-4)">·</span>
              <span>{{ protocolLabel(primaryDevice.server_type) }}</span>
              <template v-if="primaryDevice.server_display_name || primaryDevice.server_name">
                <span style="margin:0 6px; color:var(--text-4)">·</span>
                <span>{{ primaryDevice.server_display_name || primaryDevice.server_name }}</span>
              </template>
            </template>
            <template v-else>{{ statusSub }}</template>
          </div>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap">
          <router-link v-if="subscription.needs_plan"
                       to="/plans" class="fx-btn fx-btn-primary">
            <FxIcon name="tag" :size="14" />
            {{ $t('dash.choosePlan') || 'Choose a plan' }}
          </router-link>
          <router-link v-else-if="!devices.length && subscription.status === 'active'"
                       to="/devices" class="fx-btn fx-btn-primary">
            <FxIcon name="plus" :size="14" /> {{ $t('dash.addDevice') }}
          </router-link>
          <button v-else-if="subscription.tier && subscription.tier.toLowerCase() === 'free'"
                  class="fx-btn fx-btn-primary"
                  @click="showUpgradeModal = true">
            <FxIcon name="trafficUp" :size="14" /> {{ $t('dash.upgradePlan') }}
          </button>
          <button v-else-if="subscription.days_remaining != null && subscription.days_remaining < 7"
                  class="fx-btn fx-btn-primary"
                  @click="showUpgradeModal = true">
            <FxIcon name="refresh" :size="14" /> {{ $t('dash.renewNow') }}
          </button>
          <router-link v-else to="/plans" class="fx-btn fx-btn-secondary">
            {{ $t('dash.changePlan') }}
          </router-link>
        </div>
      </div>
    </div>

    <!-- Stat row -->
    <div class="fx-stat-row">
      <div class="fx-stat">
        <span class="accent-bar"></span>
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('dash.subscriptionPlan') }}</span>
          <span class="fx-stat-icon"><FxIcon name="tag" :size="14" /></span>
        </div>
        <div class="fx-stat-value">{{ planName }}</div>
        <div class="fx-stat-foot">
          <span class="fx-badge" :class="statusBadgeFx">{{ statusLabel }}</span>
        </div>
      </div>

      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('dash.daysRemaining') }}</span>
          <span class="fx-stat-icon"><FxIcon name="calendar" :size="14" /></span>
        </div>
        <div class="fx-stat-value">
          <span>{{ daysRemainingDisplay }}</span>
          <span class="unit">{{ daysRemainingDisplay === '∞' ? '' : $t('dash.daysUnit') }}</span>
        </div>
        <div v-if="daysRemainingSparkData.length" class="fx-stat-spark" style="color:var(--success)">
          <Sparkline :data="daysRemainingSparkData" :height="32" />
        </div>
        <div class="fx-stat-foot">
          <span>{{ expiryDate }}</span>
        </div>
      </div>

      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('dash.trafficUsed') }}</span>
          <span class="fx-stat-icon"><FxIcon name="trafficUp" :size="14" /></span>
        </div>
        <div class="fx-stat-value">
          <span>{{ trafficUsedGB }}</span>
          <span class="unit">{{ subscription.traffic_limit_gb ? `/ ${subscription.traffic_limit_gb} GB` : 'GB' }}</span>
        </div>
        <div v-if="subscription.traffic_limit_gb" class="fx-progress" style="margin-top:12px">
          <div class="fx-progress-fill" :class="trafficFillClass"
               :style="{ width: Math.min(100, subscription.traffic_percentage || 0) + '%' }"></div>
        </div>
        <div class="fx-stat-foot">
          <span v-if="trafficSummary.trend_pct != null" class="fx-stat-trend"
                :class="trafficSummary.trend_pct >= 0 ? 'up' : 'down'">
            <FxIcon :name="trafficSummary.trend_pct >= 0 ? 'arrowUp' : 'arrowDown'" :size="11" />
            {{ Math.abs(trafficSummary.trend_pct).toFixed(1) }}% {{ $t('chart.vsPrev') }}
          </span>
          <span v-else-if="!subscription.traffic_limit_gb" class="fx-stat-trend up">
            <FxIcon name="arrowUp" :size="11" /> {{ $t('dash.unlimited') }}
          </span>
        </div>
      </div>

      <div class="fx-stat">
        <div class="fx-stat-eyebrow">
          <span class="fx-stat-label">{{ $t('dash.activeDevices') }}</span>
          <span class="fx-stat-icon"><FxIcon name="phone" :size="14" /></span>
        </div>
        <div class="fx-stat-value">
          <span>{{ deviceCount }}</span>
          <span class="unit">/ {{ subscription.max_devices || 1 }}</span>
        </div>
        <div class="fx-stat-spark" style="color:var(--accent)">
          <Sparkline :data="activeDevicesSparkData" :height="32" />
        </div>
        <div class="fx-stat-foot">
          <span>{{ devicesUsageHint }}</span>
        </div>
      </div>
    </div>

    <!-- Two-col grid (collapses to single column with mob-order on phone) -->
    <div class="fx-dash-grid">
      <!-- LEFT COLUMN -->
      <div class="fx-dash-col fx-dash-col-main">
        <!-- Big traffic chart -->
        <div class="fx-mob-order-1">
          <TrafficChart
            :series="trafficSeries"
            :summary="trafficSummary"
            :range="trafficRange"
            :loading="trafficLoading"
            @change-range="onChangeRange"
          />
        </div>

        <!-- Subscription details -->
        <div class="fx-card fx-sub-card fx-mob-order-4">
          <div class="fx-sub-header">
            <div>
              <h3 class="fx-sub-plan-name">{{ planName }}</h3>
              <div class="fx-sub-plan-meta">{{ subscriptionStartedHint }}</div>
            </div>
            <button class="fx-btn fx-btn-primary fx-btn-sm" @click="showUpgradeModal = true">
              <FxIcon name="trafficUp" :size="13" /> {{ $t('dash.upgradePlan') }}
            </button>
          </div>
          <div v-if="subscription.days_remaining != null && subscription.days_remaining < 7"
               class="fx-card" style="padding:12px 14px; background:var(--warning-soft); border-color:color-mix(in oklab, var(--warning) 30%, var(--border)); margin-bottom:14px">
            <div style="display:flex; gap:10px; align-items:flex-start; font-size:13px">
              <FxIcon name="warning" :size="16" style="color:var(--warning); flex-shrink:0; margin-top:2px" />
              <div>
                <strong>{{ $t('dash.expiresWarning', { days: subscription.days_remaining }) }}</strong>
                <a href="#" @click.prevent="showUpgradeModal = true" style="color:var(--accent); margin-left:6px">{{ $t('dash.renewNow') }}</a>
              </div>
            </div>
          </div>
          <!-- Soft-downgrade card: shown when user has more devices than the
               new plan supports. Existing devices keep working until renewal —
               at that point the oldest excess get auto-pruned. -->
          <div v-if="subscription.over_device_limit" class="fx-overlimit-card">
            <div class="fx-overlimit-icon">
              <FxIcon name="warning" :size="18" />
            </div>
            <div class="fx-overlimit-body">
              <div class="fx-overlimit-title">{{ overLimitTitle }}</div>
              <p class="fx-overlimit-hint">{{ overLimitHint }}</p>
              <div class="fx-overlimit-actions">
                <button type="button" class="fx-btn fx-btn-primary fx-btn-sm" @click="showUpgradeModal = true">
                  <FxIcon name="trafficUp" :size="13" />
                  {{ $t('dash.overDeviceLimitCta') }}
                </button>
                <router-link to="/devices" class="fx-btn fx-btn-ghost fx-btn-sm">
                  {{ $t('dash.manageDevices') }}
                </router-link>
              </div>
            </div>
          </div>
          <div class="fx-sub-rows">
            <div class="fx-sub-row">
              <span class="k">{{ $t('dash.plan') }}</span>
              <span class="v">{{ planName }}</span>
            </div>
            <div class="fx-sub-row">
              <span class="k">{{ $t('dash.status') }}</span>
              <span class="v"><span class="fx-badge" :class="statusBadgeFx">{{ statusLabel }}</span></span>
            </div>
            <div class="fx-sub-row">
              <span class="k">{{ $t('dash.expiryDate') }}</span>
              <span class="v">{{ expiryDate }}</span>
            </div>
            <div class="fx-sub-row" v-if="subscription.price_monthly_usd">
              <span class="k">{{ $t('dash.price') }}</span>
              <span class="v">${{ subscription.price_monthly_usd }}{{ $t('dash.perMonth') }}</span>
            </div>
            <div class="fx-sub-row">
              <span class="k">{{ $t('dash.maxDevices') }}</span>
              <span class="v">{{ $t('dash.devicesCount', { count: subscription.max_devices || 1 }) }}</span>
            </div>
            <div class="fx-sub-row">
              <span class="k">{{ $t('dash.bandwidth') }}</span>
              <span class="v">{{ bandwidthLimit }}</span>
            </div>
          </div>
          <div v-if="subscription.tier && subscription.tier.toLowerCase() !== 'free'"
               style="margin-top:18px; padding-top:14px; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap">
            <div v-if="autoRenew && subscription.expiry_date" style="font-size:11px; color:var(--text-3)">
              {{ $t('dash.autoRenewsOn', { date: expiryDate }) }}
            </div>
            <span v-else></span>
            <button class="fx-btn fx-btn-danger-ghost fx-btn-sm" @click="showCancelConfirm = true">
              {{ $t('dash.cancelSubscription') }}
            </button>
          </div>
        </div>

        <!-- Referral -->
        <div class="fx-referral fx-card fx-mob-order-5">
          <div class="fx-referral-head">
            <span class="fx-referral-icon"><FxIcon name="gift" :size="20" /></span>
            <div>
              <h3 class="fx-section-title" style="font-size:15px">
                {{ $t('dash.referralProgram') }}
              </h3>
              <div style="font-size:12px; color:var(--text-3); margin-top:2px">
                {{ $t('dash.referralBonusBold') }}
              </div>
            </div>
          </div>
          <div class="fx-referral-stats">
            <div class="fx-referral-stat">
              <div class="fx-referral-stat-num">{{ referral.referral_count || 0 }}</div>
              <div class="fx-referral-stat-lbl">{{ $t('dash.referralInvited') }}</div>
            </div>
            <div class="fx-referral-stat">
              <div class="fx-referral-stat-num">{{ referral.paid_referrals || 0 }}</div>
              <div class="fx-referral-stat-lbl">{{ $t('dash.referralJoined') }}</div>
            </div>
            <div class="fx-referral-stat">
              <div class="fx-referral-stat-num">+{{ (referral.paid_referrals || 0) * 7 }}</div>
              <div class="fx-referral-stat-lbl">{{ $t('dash.referralEarnedDays') }}</div>
            </div>
          </div>
          <div v-if="referral.referral_code">
            <label class="fx-label" style="margin-bottom:6px">{{ $t('dash.referralLink') }}</label>
            <div class="fx-copy-field">
              <span class="fx-copy-text">{{ referralLink }}</span>
              <button class="fx-btn fx-btn-primary fx-btn-sm" @click="copyReferralLink">
                <FxIcon name="copy" :size="12" />
                {{ copyFeedback ? $t('common.copied') : $t('common.copy') }}
              </button>
            </div>
          </div>
          <div v-else class="fx-stat-foot">{{ $t('common.loading') }}</div>
        </div>
      </div>

      <!-- RIGHT COLUMN -->
      <div class="fx-dash-col fx-dash-col-side">
        <!-- Quick actions -->
        <div class="fx-card fx-mob-order-2">
          <div style="padding:var(--pad-card) var(--pad-card) 0">
            <h3 class="fx-section-title">{{ $t('dash.quickActions') }}</h3>
          </div>
          <div class="fx-actions-grid">
            <router-link to="/devices" class="fx-action primary"
                         :class="{ 'fx-action-disabled': subscription.status !== 'active' }">
              <span class="fx-action-icon"><FxIcon name="plus" :size="16" /></span>
              <span class="fx-action-text">
                <span class="fx-action-title">{{ $t('dash.addDevice') }}</span>
                <span class="fx-action-sub">{{ $t('dash.addDeviceSub') }}</span>
              </span>
            </router-link>
            <button class="fx-action" @click="showUpgradeModal = true">
              <span class="fx-action-icon"><FxIcon name="trafficUp" :size="16" /></span>
              <span class="fx-action-text">
                <span class="fx-action-title">{{ $t('dash.upgradePlan') }}</span>
                <span class="fx-action-sub">{{ $t('dash.upgradePlanSub') }}</span>
              </span>
            </button>
            <button class="fx-action" @click="showChangePassword = true">
              <span class="fx-action-icon"><FxIcon name="lock" :size="16" /></span>
              <span class="fx-action-text">
                <span class="fx-action-title">{{ $t('dash.changePassword') }}</span>
                <span class="fx-action-sub">{{ $t('dash.changePasswordSub') }}</span>
              </span>
            </button>
          </div>
        </div>

        <!-- My devices -->
        <div class="fx-card fx-devices fx-mob-order-3">
          <div class="fx-devices-head">
            <h3 class="fx-section-title">
              {{ $t('dash.myDevices') }}
              <span style="color:var(--text-3); font-weight:500; margin-left:6px">{{ deviceCount }} / {{ subscription.max_devices || 1 }}</span>
            </h3>
            <router-link to="/devices" class="fx-btn fx-btn-ghost fx-btn-sm">
              <FxIcon name="plus" :size="13" /> {{ $t('common.add') }}
            </router-link>
          </div>
          <div v-if="!devices.length">
            <div class="fx-empty">
              <div class="fx-empty-icon"><FxIcon name="phone" :size="22" /></div>
              <h3 class="fx-empty-title">{{ $t('dash.noDevicesTitle') }}</h3>
              <p class="fx-empty-sub">{{ $t('dash.noDevicesYet') }}</p>
            </div>
          </div>
          <div v-else>
            <div v-for="device in displayDevices" :key="device.id" class="fx-device-row">
              <span class="fx-device-icon"><FxIcon :name="devicePlatformIcon(device)" :size="16" /></span>
              <div class="fx-device-info">
                <div class="fx-device-name">
                  {{ device.name }}
                  <span class="fx-badge" :class="deviceBadgeClass(device)">
                    {{ deviceBadgeLabel(device) }}
                  </span>
                </div>
                <div class="fx-device-meta">
                  <span style="font-family:var(--mono)">{{ device.ipv4 || '—' }}</span>
                  <template v-if="device.server_display_name || device.server_name">
                    <span style="margin:0 6px; color:var(--text-4)">·</span>
                    <span style="font-family:inherit">{{ device.server_display_name || device.server_name }}</span>
                  </template>
                  <span style="margin:0 6px; color:var(--text-4)">·</span>
                  <span style="font-family:inherit">{{ protocolLabel(device.server_type) }}</span>
                </div>
              </div>
              <div class="fx-device-actions">
                <button v-if="features.config_download" class="fx-icon-btn-sm" :title="$t('dash.downloadConfig')" @click="downloadDeviceConfig(device)">
                  <FxIcon name="download" :size="14" />
                </button>
                <button v-if="features.qr" class="fx-icon-btn-sm" title="QR" @click="showDeviceConfig(device)">
                  <FxIcon name="qr" :size="14" />
                </button>
                <button class="fx-icon-btn-sm danger" :title="$t('dash.deleteDevice')" @click="askDeleteDevice(device)">
                  <FxIcon name="trash" :size="14" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Auto-renew -->
        <div class="fx-card fx-mob-order-6" style="padding:var(--pad-card)" v-if="subscription.tier && subscription.tier.toLowerCase() !== 'free'">
          <div style="display:flex; align-items:center; justify-content:space-between; gap:12px">
            <div style="min-width:0">
              <h3 class="fx-section-title" style="display:inline-flex; align-items:center; gap:6px">
                {{ $t('dash.autoRenew') }}
                <FxIcon name="help" :size="13" style="color:var(--text-4); cursor:help"
                        :title="$t('help.autoRenew')" />
              </h3>
              <div style="font-size:12px; color:var(--text-3); margin-top:4px">
                {{ $t('dash.autoRenewHint') }}
              </div>
            </div>
            <label class="fx-switch" :class="{ 'fx-switch-busy': autoRenewBusy }">
              <input type="checkbox" v-model="autoRenew" @change="toggleAutoRenew"
                     :disabled="autoRenewBusy" />
              <span class="fx-switch-track"></span>
              <FxIcon v-if="autoRenewBusy" name="refresh" :size="12" class="fx-spin fx-switch-spin" />
            </label>
          </div>
        </div>

        <!-- Subscription URL -->
        <div class="fx-card fx-mob-order-7" style="padding:var(--pad-card)" v-if="subscription.tier && subscription.tier.toLowerCase() !== 'free'">
          <h3 class="fx-section-title">{{ $t('dash.subscriptionLink') }}</h3>
          <p style="font-size:12px; color:var(--text-3); margin:6px 0 12px; line-height:1.5">
            {{ $t('dash.subscriptionLinkDesc') }}
          </p>
          <div v-if="subLinkToken">
            <div class="fx-copy-field" style="margin-bottom:8px">
              <span class="fx-copy-text">{{ subLinkUrl }}</span>
              <button class="fx-btn fx-btn-primary fx-btn-sm" @click="copySubLink">
                <FxIcon name="copy" :size="12" />
                {{ subLinkCopied ? $t('common.copied') : $t('common.copy') }}
              </button>
            </div>
            <button class="fx-btn fx-btn-ghost fx-btn-sm" @click="regenerateSubLink">
              <FxIcon name="refresh" :size="12" /> {{ $t('dash.regenerate') }}
            </button>
          </div>
          <button v-else class="fx-btn fx-btn-secondary fx-btn-sm" @click="loadSubLink">
            {{ $t('dash.generateLink') }}
          </button>
        </div>
      </div>
    </div>

    <!-- ─── Modals ─── -->
    <!-- QR / Config modal -->
    <transition name="fx-modal-fade">
      <div v-if="showConfigModal" class="fx-modal-overlay" @click.self="showConfigModal = false">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ configDeviceName }}</h3>
            <button class="fx-icon-btn-sm" @click="showConfigModal = false"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body" style="text-align:center">
            <div v-if="qrUrl">
              <img :src="qrUrl" alt="QR Code" style="max-width:280px; width:100%; border-radius:var(--r-md)" />
              <p style="font-size:12px; color:var(--text-3); margin-top:8px">{{ qrHintText }}</p>
            </div>
            <div v-else style="padding:36px 0">
              <div class="fx-empty-icon"><FxIcon name="qr" :size="22" /></div>
            </div>
            <div v-if="configUri" style="margin-top:14px; text-align:left">
              <label class="fx-label">{{ $t('dash.connectionLink') }}</label>
              <div class="fx-copy-field">
                <span class="fx-copy-text">{{ configUri }}</span>
                <button class="fx-btn fx-btn-secondary fx-btn-sm" @click="copyConfigUri">
                  <FxIcon name="copy" :size="12" /> {{ $t('common.copy') }}
                </button>
              </div>
            </div>
            <div v-if="configText" style="margin-top:14px; text-align:left">
              <label class="fx-label">{{ configLabelText }}</label>
              <textarea class="fx-textarea" rows="6" :value="configText" readonly style="font-family:var(--mono); font-size:12px"></textarea>
            </div>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="showConfigModal = false">{{ $t('common.close') }}</button>
            <button v-if="qrUrl && features.qr" class="fx-btn fx-btn-secondary" @click="downloadQRImage">{{ $t('dash.downloadQR') }}</button>
            <button v-if="features.config_download" class="fx-btn fx-btn-primary" @click="downloadCurrentConfig">{{ downloadConfigButtonText }}</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Change password -->
    <transition name="fx-modal-fade">
      <div v-if="showChangePassword" class="fx-modal-overlay" @click.self="showChangePassword = false">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ $t('dash.changePassword') }}</h3>
            <button class="fx-icon-btn-sm" @click="showChangePassword = false"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <label class="fx-label">{{ $t('dash.currentPassword') }}</label>
            <input class="fx-input" type="password" v-model="passwordForm.current_password" style="margin-bottom:12px" />
            <label class="fx-label">{{ $t('dash.newPassword') }}</label>
            <input class="fx-input" type="password" v-model="passwordForm.new_password" minlength="8" />
            <div v-if="passwordError" style="color:var(--danger); font-size:12px; margin-top:10px">{{ passwordError }}</div>
            <div v-if="passwordSuccess" style="color:var(--success); font-size:12px; margin-top:10px">{{ passwordSuccess }}</div>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="showChangePassword = false">{{ $t('common.close') }}</button>
            <button class="fx-btn fx-btn-primary" @click="changePassword" :disabled="changingPassword">
              {{ $t('dash.changePassword') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Cancel subscription confirm -->
    <transition name="fx-modal-fade">
      <div v-if="showCancelConfirm" class="fx-modal-overlay"
           @click.self="() => { if (!cancellingSub) showCancelConfirm = false }">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ $t('dash.cancelSubscription') }}</h3>
            <button class="fx-icon-btn-sm" @click="showCancelConfirm = false"
                    :disabled="cancellingSub"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <p style="font-size:13px; color:var(--text-2); margin:0">
              {{ $t('dash.cancelConfirm') }}
            </p>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="showCancelConfirm = false"
                    :disabled="cancellingSub">
              {{ $t('common.cancel') }}
            </button>
            <button class="fx-btn fx-btn-danger" @click="cancelSubscription"
                    :disabled="cancellingSub">
              <FxIcon v-if="cancellingSub" name="refresh" :size="13" class="fx-spin" />
              {{ cancellingSub ? $t('common.loading') : $t('dash.cancelSubscription') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Region picker — opened from Download / QR buttons on a slot-backed
         device row. Single-server (legacy) peers bypass this and run the
         action directly. -->
    <transition name="fx-modal-fade">
      <div v-if="showRegionPicker" class="fx-modal-overlay" @click.self="cancelRegionPicker">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>
              {{ pickerMode === 'qr' ? $t('dash.pickRegionQr') : $t('dash.pickRegionDownload') }}
              <span v-if="pickerDevice" style="color:var(--text-3); font-weight:500; margin-left:6px">
                — {{ pickerDevice.name }}
              </span>
            </h3>
            <button class="fx-icon-btn-sm" @click="cancelRegionPicker"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <p style="font-size:13px; color:var(--text-2); margin:0 0 14px">
              {{ pickerMode === 'qr' ? $t('dash.pickRegionQrHint') : $t('dash.pickRegionDownloadHint') }}
            </p>
            <div class="fx-region-grid">
              <button v-for="region in pickerRegions" :key="region.id"
                      class="fx-region-btn"
                      :class="{ 'is-active': region.is_active || (region.enabled && region.online) }"
                      :disabled="pickerBusy"
                      @click="onPickRegion(region)">
                <span class="fx-region-icon">
                  <FxIcon :name="region.server_type === 'amneziawg' ? 'shield' : 'globe'" :size="14" />
                </span>
                <div class="fx-region-info">
                  <div class="fx-region-name">
                    {{ region.server_display_name || region.server_name || `server-${region.server_id}` }}
                  </div>
                  <div class="fx-region-meta">
                    <span style="font-family:var(--mono); font-size:11px; color:var(--text-3)">{{ region.ipv4 || '—' }}</span>
                    <span style="margin:0 6px; color:var(--text-4)">·</span>
                    <span style="font-size:11px; color:var(--text-3)">{{ protocolLabel(region.server_type) }}</span>
                  </div>
                </div>
                <span v-if="region.enabled && region.online" class="fx-badge fx-badge-success">
                  {{ $t('dash.deviceConnected') }}
                </span>
                <span v-else-if="region.enabled" class="fx-badge fx-badge-neutral">
                  {{ $t('devices.active') }}
                </span>
              </button>
            </div>
          </div>
          <div class="fx-modal-footer">
            <button v-if="pickerMode === 'download' && pickerRegions.length > 1"
                    class="fx-btn fx-btn-secondary"
                    :disabled="pickerBusy"
                    @click="downloadAllRegions">
              <FxIcon v-if="pickerBusy" name="refresh" :size="13" class="fx-spin" />
              <FxIcon v-else name="download" :size="13" />
              {{ $t('dash.downloadAllRegions') }}
            </button>
            <button class="fx-btn fx-btn-ghost" @click="cancelRegionPicker" :disabled="pickerBusy">
              {{ $t('common.cancel') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Confirm delete (password-gated to prevent accidental removal) -->
    <transition name="fx-modal-fade">
      <div v-if="showDeleteConfirm" class="fx-modal-overlay" @click.self="cancelDeleteConfirm">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ $t('dash.deletePasswordTitle') }}</h3>
            <button class="fx-icon-btn-sm" @click="cancelDeleteConfirm"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <p style="font-size:13px; color:var(--text-2); margin:0 0 12px">
              {{ $t('dash.deletePasswordHint', { name: deleteTargetName }) }}
            </p>
            <label class="fx-label">{{ $t('dash.deletePasswordPlaceholder') }}</label>
            <input class="fx-input" type="password" v-model="deletePassword"
                   :placeholder="$t('dash.deletePasswordPlaceholder')"
                   @keyup.enter="confirmDeleteWithPassword" />
            <div v-if="deleteError" style="color:var(--danger); font-size:12px; margin-top:10px">{{ deleteError }}</div>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="cancelDeleteConfirm">{{ $t('common.cancel') }}</button>
            <button class="fx-btn fx-btn-danger" @click="confirmDeleteWithPassword"
                    :disabled="deleting || !deletePassword">
              {{ deleting ? $t('common.loading') : $t('dash.deletePasswordSubmit') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Add device -->
    <transition name="fx-modal-fade">
      <div v-if="showAddDeviceModal" class="fx-modal-overlay" @click.self="showAddDeviceModal = false">
        <div class="fx-modal-box">
          <div class="fx-modal-header">
            <h3>{{ $t('dash.addDevice') }}</h3>
            <button class="fx-icon-btn-sm" @click="showAddDeviceModal = false"><FxIcon name="close" :size="14" /></button>
          </div>
          <div class="fx-modal-body">
            <label class="fx-label">{{ $t('dash.deviceName') }}</label>
            <input class="fx-input" v-model="newDeviceName" :placeholder="$t('dash.deviceNamePlaceholder')" maxlength="64"
                   @keyup.enter="createDevice" style="margin-bottom:12px" />
            <div v-if="servers.length > 1">
              <label class="fx-label">{{ $t('dash.selectServer') }}</label>
              <select class="fx-select" v-model="selectedServerId">
                <option :value="null">{{ $t('dash.autoDefaultServer') }}</option>
                <option v-for="s in servers" :key="s.id" :value="s.id">
                  {{ formatServerOption(s) }}
                </option>
              </select>
            </div>
            <p v-else style="font-size:12px; color:var(--text-3); margin-top:6px">
              {{ $t('dash.newDeviceOnDefault') }}
            </p>
          </div>
          <div class="fx-modal-footer">
            <button class="fx-btn fx-btn-ghost" @click="showAddDeviceModal = false">{{ $t('common.close') }}</button>
            <button class="fx-btn fx-btn-primary" @click="createDevice" :disabled="creatingDevice">
              {{ $t('dash.addDevice') }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Upgrade -->
    <PaymentModal v-if="showUpgradeModal" @close="showUpgradeModal = false" @success="onPaymentSuccess" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalApi } from '../api'
import PaymentModal from './PaymentModal.vue'
import FxIcon from '../components/FxIcon.vue'
import Sparkline from '../components/Sparkline.vue'
import TrafficChart from '../components/TrafficChart.vue'
import { useEscapeClose } from '../composables/useEscapeClose.js'

const router = useRouter()
const { t } = useI18n()

const subscription = ref({})
const devices = ref([])
// Per-operator portal gates (from /client-portal/features). Default everything
// ON so a fetch hiccup never hides a capability — backend 403 is the real gate.
const features = ref({ config_download: true, qr: true })
const showUpgradeModal = ref(false)
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
const refreshing = ref(false)

// Password-gated device delete — prevents an accidental tap from wiping
// a working VPN config. The admin retains a no-prompt delete path from
// the panel for legitimate cleanup.
const showDeleteConfirm = ref(false)
const showCancelConfirm = ref(false)

// Region picker — opened from Download / QR on a slot-backed device.
// Legacy single-server peers (slot_id null) bypass and run directly.
const showRegionPicker = ref(false)
const pickerMode = ref('download')       // 'download' | 'qr'
const pickerDevice = ref(null)
const pickerBusy = ref(false)
const pickerRegions = computed(() => {
  if (!pickerDevice.value) return []
  if (pickerDevice.value.slot_id == null) return [pickerDevice.value]
  return (devices.value || [])
    .filter(d => d.slot_id === pickerDevice.value.slot_id)
    .slice()
    .sort((a, b) => {
      // Connected first, then active, then by name.
      const score = (d) => (d.online ? 0 : d.enabled ? 1 : 2)
      const dx = score(a) - score(b)
      return dx !== 0 ? dx : (a.server_name || '').localeCompare(b.server_name || '')
    })
})

// Esc closes all open modals — desktop users expect it, mobile is
// unaffected. cancelDeleteConfirm gates on `deleting` so an in-flight
// delete can't be aborted halfway through.
useEscapeClose(showUpgradeModal)
useEscapeClose(showConfigModal)
useEscapeClose(showChangePassword)
useEscapeClose(showAddDeviceModal)
useEscapeClose(showDeleteConfirm, () => cancelDeleteConfirm())
useEscapeClose(showCancelConfirm, () => { if (!cancellingSub.value) showCancelConfirm.value = false })
useEscapeClose(showRegionPicker, () => { if (!pickerBusy.value) cancelRegionPicker() })
const deleteTarget = ref(null)
const deletePassword = ref('')
const deleteError = ref(null)
const deleting = ref(false)

// Traffic chart state — backed by GET /client-portal/dashboard/traffic-series
const trafficRange = ref('14d')
const trafficSeries = ref([])
const trafficSummary = ref({ total_rx_gb: 0, total_tx_gb: 0, total_gb: 0, trend_pct: null })
const activeDevicesSeries = ref([])
const trafficLoading = ref(false)

const toasts = ref([])
let toastSeq = 0
const showToast = (message, type = 'success') => {
  const id = ++toastSeq
  toasts.value.push({ id, message, type })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 3000)
}

// ─── Welcome / status ───
const welcomeText = computed(() => {
  const n = userFirstName()
  return n ? t('dash.welcomeBack', { name: n }) : t('dash.welcomeAnon')
})
function userFirstName() {
  try {
    const u = JSON.parse(localStorage.getItem('client_user') || '{}')
    return (u.username || (u.email || '').split('@')[0] || '').slice(0, 32)
  } catch { return '' }
}

const isFreeUser = computed(() => (subscription.value.tier || 'free').toLowerCase() === 'free')
const planName = computed(() => {
  const tier = subscription.value.tier || 'free'
  if (subscription.value.needs_plan || tier === 'none') {
    return t('dash.noPlan') || 'No plan'
  }
  return tier.charAt(0).toUpperCase() + tier.slice(1)
})
const expiryDate = computed(() => subscription.value.expiry_date
  ? new Date(subscription.value.expiry_date).toLocaleDateString()
  : t('dash.never'))
const statusLabel = computed(() => {
  if (subscription.value.needs_plan) return t('dash.statusNoPlan') || 'No plan'
  const m = { active: t('dash.statusActive'), inactive: t('dash.statusInactive'), expired: t('dash.statusExpired') }
  return m[subscription.value.status] || subscription.value.status || '—'
})
const statusBadgeFx = computed(() => {
  const s = subscription.value.status
  if (s === 'active') return 'fx-badge-success'
  if (s === 'expired') return 'fx-badge-danger'
  return 'fx-badge-neutral'
})
// Per-device badge — three states:
//   • online (handshake within ~3 min)  → "Connected" / green
//   • enabled but stale (no handshake)  → "Ready" / neutral
//   • disabled by admin                 → "Disconnected" / neutral
const deviceBadgeClass = (d) => {
  if (!d.enabled) return 'fx-badge-neutral'
  if (d.online) return 'fx-badge-success'
  return 'fx-badge-neutral'
}
const deviceBadgeLabel = (d) => {
  if (!d.enabled) return t('dash.deviceDisconnected')
  if (d.online) return t('dash.deviceConnected')
  return t('dash.deviceReady') || t('dash.deviceDisconnected')
}

// Pick the most likely "active" device — prefer one that's actually
// connected (live handshake), then any enabled one, then anything.
const primaryDevice = computed(() => {
  if (!devices.value.length) return null
  return devices.value.find(d => d.online)
      || devices.value.find(d => d.enabled)
      || devices.value[0]
      || null
})

// Indicator is GREEN only when a device has a fresh WG handshake. The
// `enabled` flag stays True after the user disconnects in their VPN app,
// so using it alone made the orb look online forever — switch to `online`
// (handshake within ~3 min, computed server-side in /clients/by-ids).
const orbClass = computed(() => {
  if (subscription.value.status !== 'active') return 'off'
  if (!primaryDevice.value) return 'warn'
  if (!primaryDevice.value.enabled) return 'warn'
  if (!primaryDevice.value.online) return 'warn'
  return ''
})

const statusTitle = computed(() => {
  if (subscription.value.status !== 'active') {
    return subscription.value.status === 'expired'
      ? t('dash.statusBannerExpired')
      : t('dash.statusBannerInactive')
  }
  if (primaryDevice.value && primaryDevice.value.online) {
    const name = primaryDevice.value.server_name
      || (primaryDevice.value.name)
      || t('dash.statusVpnReady')
    return t('dash.statusConnectedTo', { server: name })
  }
  if (primaryDevice.value && !primaryDevice.value.enabled) {
    return t('dash.statusDeviceDisabled', { name: primaryDevice.value.name })
  }
  if (primaryDevice.value) {
    // Enabled in the DB but no fresh handshake — user just isn't connected
    // in their VPN app right now. Show a "ready, not active" line.
    return t('dash.statusReady') || t('dash.statusVpnReady') || 'Ready — not connected'
  }
  return t('dash.statusNoDevice')
})

// Fallback subline when no primary device — concise subscription summary.
const statusSub = computed(() => {
  const parts = []
  if (subscription.value.status === 'active' && subscription.value.days_remaining != null) {
    parts.push(t('dash.statusBannerDaysLeft', { days: subscription.value.days_remaining }))
  }
  parts.push(t('dash.statusBannerDevicesUsed', {
    used: deviceCount.value,
    max: subscription.value.max_devices || 1,
  }))
  return parts.join(' · ')
})

const daysRemainingDisplay = computed(() =>
  subscription.value.days_remaining != null ? subscription.value.days_remaining : '∞')

const trafficUsedGB = computed(() => Number(subscription.value.traffic_used_gb || 0).toFixed(2))
const trafficFillClass = computed(() => {
  const pct = subscription.value.traffic_percentage || 0
  if (pct >= 90) return 'danger'
  if (pct >= 70) return 'warning'
  return ''
})
const bandwidthLimit = computed(() => subscription.value.bandwidth_limit_mbps
  ? `${subscription.value.bandwidth_limit_mbps} Mbps`
  : t('dash.unlimited'))

// Device count for headers/stat cards — uses the subscription's
// slot-aware count when available so a multi-region slot is one device,
// not N peers. Falls back to the peer-array length while the
// subscription payload is still loading.
const deviceCount = computed(() => {
  if (subscription.value.devices_used != null) return subscription.value.devices_used
  return devices.value.length
})

// Group the peer list returned by /wireguard/clients down to one row per
// device — for slot-backed devices we collapse the regional peers into
// the active one (preferring an online peer, then any enabled one).
const displayDevices = computed(() => {
  const bySlot = new Map()
  const standalone = []
  for (const d of devices.value || []) {
    const slotId = d.slot_id ?? null
    if (slotId == null) { standalone.push(d); continue }
    const cur = bySlot.get(slotId)
    if (!cur) { bySlot.set(slotId, d); continue }
    // Prefer the peer the user is actively connected through; otherwise
    // any enabled peer; otherwise keep what we already have.
    const better = (d.online && !cur.online)
      || (d.enabled && !cur.enabled)
    if (better) bySlot.set(slotId, d)
  }
  return [...bySlot.values(), ...standalone]
})

const devicesUsageHint = computed(() => {
  const used = deviceCount.value
  const max = subscription.value.max_devices || 1
  if (used === 0) return t('dash.devicesNoneConnected')
  if (used >= max) return t('dash.devicesAllUsed')
  return t('dash.devicesAvailable', { count: max - used })
})

const overLimitTitle = computed(() => t('dash.overDeviceLimit', {
  used: subscription.value.devices_used ?? 0,
  max:  subscription.value.max_devices ?? 1,
}))
const overLimitHint = computed(() => t('dash.overDeviceLimitHint', {
  used: subscription.value.devices_used ?? 0,
  max:  subscription.value.max_devices ?? 1,
}))

const deleteTargetName = computed(() => deleteTarget.value?.name || '')

const subscriptionStartedHint = computed(() => {
  if (subscription.value.created_at) {
    return t('dash.subscriptionStarted', { date: new Date(subscription.value.created_at).toLocaleDateString() })
  }
  return t('dash.subscriptionStartedUnknown')
})

const referralLink = computed(() => referral.value.referral_code
  ? `${window.location.origin}/register?ref=${referral.value.referral_code}`
  : '')

const protocolLabel = (serverType) => {
  switch ((serverType || 'wireguard').toLowerCase()) {
    case 'wireguard': return 'WireGuard'
    case 'amneziawg': return 'AmneziaWG'
    case 'hysteria2': return 'Hysteria2'
    case 'tuic': return 'TUIC'
    default: return serverType || 'WireGuard'
  }
}

// Best-effort platform icon from the user's device name.
// We don't have a real platform field on the API, so this is purely cosmetic —
// a generic phone icon falls back when the name doesn't hint at a platform.
const devicePlatformIcon = (device) => {
  const n = (device?.name || '').toLowerCase()
  if (/\b(iphone|ipad|ipod|mac|macbook|imac|osx|ios)\b/.test(n)) return 'phone'
  if (/\b(android|samsung|xiaomi|pixel|huawei|oneplus|redmi)\b/.test(n)) return 'phone'
  if (/\b(linux|ubuntu|debian|arch|fedora|rasp)\b/.test(n)) return 'server'
  if (/\b(win|windows|laptop|desktop|pc)\b/.test(n)) return 'server'
  if (/\b(router|gateway|firewall)\b/.test(n)) return 'building'
  return 'phone'
}
const formatServerOption = (server) => {
  const name = server.name || 'Server'
  return `${name} [${protocolLabel(server.server_type)}]`
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
    case 'hysteria2': return t('dash.downloadYaml')
    case 'tuic': return t('dash.downloadJson')
    default: return t('dash.downloadConf')
  }
})

const subLinkUrl = computed(() => subLinkToken.value
  ? `${window.location.origin}/client-portal/sub/${subLinkToken.value}` : '')

// ─── Actions ───
const loadData = async () => {
  refreshing.value = true
  try {
    const { data } = await portalApi.getSubscription()
    subscription.value = data
    autoRenew.value = !!data.auto_renew
  } catch (error) {
    if (error.response?.status === 401) router.push('/login')
  } finally {
    refreshing.value = false
  }
  await loadDevices()
}

const loadTrafficSeries = async (rangeKey = trafficRange.value) => {
  trafficLoading.value = true
  trafficRange.value = rangeKey
  try {
    const { data } = await portalApi.getTrafficSeries(rangeKey)
    trafficSeries.value = data.series || []
    trafficSummary.value = data.summary || { total_rx_gb: 0, total_tx_gb: 0, total_gb: 0, trend_pct: null }
    activeDevicesSeries.value = data.active_devices_series || []
  } catch {
    trafficSeries.value = []
    activeDevicesSeries.value = []
    trafficSummary.value = { total_rx_gb: 0, total_tx_gb: 0, total_gb: 0, trend_pct: null }
  } finally {
    trafficLoading.value = false
  }
}

const onChangeRange = (rangeKey) => loadTrafficSeries(rangeKey)

const activeDevicesSparkData = computed(() =>
  (activeDevicesSeries.value || []).map(p => Number(p.count) || 0))

// Days-remaining is a deterministic linear count-down — no need for a backend
// series. We synthesise 14 daily points ending at today's value.
const daysRemainingSparkData = computed(() => {
  const d = subscription.value.days_remaining
  if (d == null) return []
  const N = 14
  return Array.from({ length: N }, (_, i) => Math.max(0, d + (N - 1 - i)))
})

const loadDevices = async () => {
  try {
    const { data } = await portalApi.getDevices()
    devices.value = data
  } catch { /* ignore */ }
}

// Region-aware QR opener. Slot-backed device → first show the region
// picker (one QR per region — combining them makes no sense), legacy
// peer → straight to the QR modal.
const showDeviceConfig = async (device) => {
  if (device && device.slot_id != null && hasMultipleRegions(device)) {
    openRegionPicker(device, 'qr')
    return
  }
  await openConfigModalForPeer(device)
}

const hasMultipleRegions = (device) => {
  if (!device || device.slot_id == null) return false
  return (devices.value || []).filter(d => d.slot_id === device.slot_id).length > 1
}

const openConfigModalForPeer = async (device) => {
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
    case 'hysteria2': return 'yaml'
    case 'tuic': return 'json'
    default: return 'conf'
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
// Region-aware download. Slot-backed device → open the picker (user
// chooses a specific region or "all"); legacy peer → straight download.
const downloadDeviceConfig = async (device) => {
  if (device && device.slot_id != null && hasMultipleRegions(device)) {
    openRegionPicker(device, 'download')
    return
  }
  await downloadOnePeer(device)
}

const downloadOnePeer = async (peer) => {
  try {
    const { data } = await portalApi.getConfig(peer.id)
    const config = data.config_text || data.config || data
    const name = data.client_name || peer.name
    const protocol = data.protocol || peer.server_type || 'wireguard'
    // Tunnel-name length is capped at 15 chars on Linux/Android (TUN
    // interface name limit). Long combined names like
    // "Phone-a5e5-TexasUSA-AWG.conf" get rejected by AmneziaWG mobile.
    // We use the server identifier when downloading a slot region, and
    // truncate to 15 chars so the import doesn't bounce.
    const fname = peer.server_name
      ? `${peer.server_name.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 15)}.${configExtension(protocol)}`
      : `${name}.${configExtension(protocol)}`
    const blob = new Blob([config], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = fname; a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    showToast(t('common.error') + ': ' + (err.response?.data?.detail || err.message), 'error')
  }
}

const openRegionPicker = (device, mode) => {
  pickerDevice.value = device
  pickerMode.value = mode
  pickerBusy.value = false
  showRegionPicker.value = true
}
const cancelRegionPicker = () => {
  if (pickerBusy.value) return
  showRegionPicker.value = false
  pickerDevice.value = null
}
const onPickRegion = async (region) => {
  if (pickerBusy.value) return
  if (pickerMode.value === 'download') {
    pickerBusy.value = true
    try { await downloadOnePeer(region) } finally { pickerBusy.value = false }
    cancelRegionPicker()
  } else {
    cancelRegionPicker()
    await openConfigModalForPeer(region)
  }
}
const downloadAllRegions = async () => {
  if (pickerBusy.value || !pickerRegions.value.length) return
  pickerBusy.value = true
  try {
    // Browsers will queue multiple downloads if they fire back-to-back —
    // tiny sleep between them keeps Chromium from collapsing some, and
    // gives Safari a fighting chance.
    for (const region of pickerRegions.value) {
      await downloadOnePeer(region)
      await new Promise(r => setTimeout(r, 120))
    }
    showToast(t('dash.allRegionsDownloaded'))
  } finally {
    pickerBusy.value = false
    cancelRegionPicker()
  }
}
const copyConfigUri = async () => {
  if (!configUri.value) return
  try { await navigator.clipboard.writeText(configUri.value); showToast(t('common.copied')) }
  catch (e) { showToast(t('common.error') + ': ' + (e.message || 'copy failed'), 'error') }
}

const createDevice = async () => {
  creatingDevice.value = true
  try {
    const { data } = await portalApi.createDevice(selectedServerId.value, newDeviceName.value.trim() || null)
    const protocol = protocolLabel(data.server_type)
    const message = data.ipv4
      ? t('dash.deviceCreated', { name: data.name, ip: data.ipv4 })
      : `${t('dash.deviceCreated', { name: data.name, ip: '' })} [${protocol}]`
    showToast(message)
    showAddDeviceModal.value = false
    selectedServerId.value = null
    newDeviceName.value = ''
    await loadDevices()
  } catch (error) {
    // Backend now returns a structured 409 payload for device-limit hits so we
    // can offer the user a one-click "Upgrade plan" path instead of a bare
    // error toast. Other errors fall through to the original toast.
    const detail = error.response?.data?.detail
    if (error.response?.status === 409 && detail && typeof detail === 'object' && detail.code === 'device_limit_reached') {
      const used = detail.used_devices ?? 0
      const max  = detail.max_devices  ?? 1
      const msg = t('dash.deviceLimitReached', { used, max }) ||
        `Device limit reached (${used}/${max}). Upgrade your plan or remove a device.`
      if (confirm(msg + '\n\n' + (t('dash.openUpgrade') || 'Open Upgrade plan?'))) {
        showUpgradeModal.value = true
      }
    } else {
      showToast(t('common.error') + ': ' + (typeof detail === 'string' ? detail : (detail?.message || error.message)), 'error')
    }
  } finally {
    creatingDevice.value = false
  }
}
const askDeleteDevice = (device) => {
  deleteTarget.value = device
  deletePassword.value = ''
  deleteError.value = null
  showDeleteConfirm.value = true
}
const cancelDeleteConfirm = () => {
  if (deleting.value) return
  showDeleteConfirm.value = false
  deleteTarget.value = null
  deletePassword.value = ''
  deleteError.value = null
}
const confirmDeleteWithPassword = async () => {
  if (!deleteTarget.value || !deletePassword.value || deleting.value) return
  deleting.value = true
  deleteError.value = null
  try {
    // Verify password by replaying the login flow. Stateless JWT means a
    // fresh access token from this call is harmless — we just discard it.
    // Reusing /auth/login keeps password-hash comparison in one place
    // instead of adding a one-off verify endpoint.
    let userEmail = ''
    try {
      const u = JSON.parse(localStorage.getItem('client_user') || '{}')
      userEmail = u.email || ''
    } catch { /* ignore */ }
    if (!userEmail) {
      deleteError.value = t('common.error')
      deleting.value = false
      return
    }
    try {
      // skip-401-interceptor: see api/index.js — wrong password on this
      // verify-only login must NOT yank the customer's existing session.
      await portalApi.login(
        { email: userEmail, password: deletePassword.value },
        { _skipAuthInterceptor: true },
      )
    } catch (verifyErr) {
      if (verifyErr.response?.status === 400 || verifyErr.response?.status === 401) {
        deleteError.value = t('dash.deletePasswordWrong')
      } else {
        deleteError.value = (typeof verifyErr.response?.data?.detail === 'string'
          ? verifyErr.response.data.detail
          : verifyErr.message) || t('common.error')
      }
      deleting.value = false
      return
    }
    // If the deleted row belongs to a Device Slot, use the slot-delete
    // endpoint so every regional peer of that slot is removed together —
    // otherwise the user has to delete each peer one at a time, which is
    // confusing because they think of the slot as one "device". Legacy
    // single-server peers (no slot_id) fall back to the per-peer delete.
    const slotId = deleteTarget.value.slot_id
    if (slotId != null) {
      await portalApi.deleteSlot(slotId)
    } else {
      await portalApi.deleteDevice(deleteTarget.value.id)
    }
    showToast(t('dash.deviceDeleted'))
    showDeleteConfirm.value = false
    deleteTarget.value = null
    deletePassword.value = ''
    await loadDevices()
    await loadData()
  } catch (error) {
    deleteError.value = (typeof error.response?.data?.detail === 'string'
      ? error.response.data.detail
      : error.message) || t('common.error')
  } finally {
    deleting.value = false
  }
}
const cancellingSub = ref(false)
const cancelSubscription = async () => {
  cancellingSub.value = true
  try {
    await portalApi.cancelSubscription()
    showCancelConfirm.value = false
    await loadData()
    showToast(t('dash.cancelDone'))
  } catch (error) {
    showToast(t('common.error') + ': ' + (error.response?.data?.detail || error.message), 'error')
  } finally {
    cancellingSub.value = false
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
    setTimeout(() => { showChangePassword.value = false; passwordSuccess.value = null }, 1800)
  } catch (error) {
    passwordError.value = error.response?.data?.detail || t('common.error')
  } finally {
    changingPassword.value = false
  }
}
const loadReferral = async () => {
  try { const { data } = await portalApi.getReferral(); referral.value = data } catch { /* ignore */ }
}
const copyReferralLink = async () => {
  try {
    await navigator.clipboard.writeText(referralLink.value)
    copyFeedback.value = true
    setTimeout(() => { copyFeedback.value = false }, 2000)
  } catch { /* ignore */ }
}
const autoRenewBusy = ref(false)
const toggleAutoRenew = async () => {
  if (autoRenewBusy.value) {
    // Double-click race — should never happen because the input is
    // disabled while busy, but guard anyway.
    return
  }
  autoRenewBusy.value = true
  try {
    await portalApi.toggleAutoRenew(autoRenew.value)
  } catch (e) {
    autoRenew.value = !autoRenew.value
    showToast(t('common.error') + ': ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    autoRenewBusy.value = false
  }
}
const onPaymentSuccess = () => {
  showUpgradeModal.value = false
  loadData()
  showToast(t('dash.paymentSuccess'))
}
const loadServers = async () => {
  try { const { data } = await portalApi.getServers(); servers.value = data || [] } catch { /* ignore */ }
}
const loadFeatures = async () => {
  // Fail open: on any error keep the ON-by-default `features` ref untouched.
  try {
    const { data } = await portalApi.getFeatures()
    if (data && data.features) features.value = { ...features.value, ...data.features }
  } catch { /* ignore */ }
}
const loadSubLink = async () => {
  try { const { data } = await portalApi.getSubscriptionLink(); subLinkToken.value = data.token }
  catch { /* ignore */ }
}
const copySubLink = async () => {
  try {
    await navigator.clipboard.writeText(subLinkUrl.value)
    subLinkCopied.value = true
    setTimeout(() => { subLinkCopied.value = false }, 2000)
  } catch { /* ignore */ }
}
const regenerateSubLink = async () => {
  try {
    const { data } = await portalApi.regenerateSubscriptionLink()
    subLinkToken.value = data.token
    showToast(t('dash.linkRegenerated'))
  } catch {
    showToast(t('dash.linkRegenerateFailed'), 'error')
  }
}

onMounted(() => {
  if (!localStorage.getItem('client_access_token')) { router.push('/login'); return }
  loadData()
  loadReferral()
  loadServers()
  loadFeatures()
  loadSubLink()
  loadTrafficSeries()
})
</script>

<style scoped>
.fx-toast-fade-enter-active, .fx-toast-fade-leave-active { transition: all .25s ease; }
.fx-toast-fade-enter-from { opacity: 0; transform: translateX(20px); }
.fx-toast-fade-leave-to { opacity: 0; transform: translateX(20px); }
.fx-modal-fade-enter-active, .fx-modal-fade-leave-active { transition: opacity .2s ease; }
.fx-modal-fade-enter-from, .fx-modal-fade-leave-to { opacity: 0; }

/* Over-limit card — matches the portal's fx-card aesthetic: rounded
   corners, soft warning tint, accent border-left strip, icon chip on
   the side. Replaces the older bootstrap-warning look that didn't
   sit right with the rest of the dashboard. */
.fx-overlimit-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 14px;
  border: 1px solid color-mix(in oklab, var(--warning) 28%, var(--border));
  border-left: 3px solid var(--warning);
  border-radius: var(--r-md, 10px);
  background: linear-gradient(
    180deg,
    color-mix(in oklab, var(--warning) 10%, var(--bg-card, var(--bg-2))) 0%,
    var(--bg-card, var(--bg-2)) 100%
  );
}
.fx-overlimit-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--warning) 18%, transparent);
  color: var(--warning);
}
.fx-overlimit-body { flex: 1; min-width: 0; }
.fx-overlimit-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.fx-overlimit-hint {
  font-size: 12.5px;
  color: var(--text-2);
  margin: 0 0 10px;
  line-height: 1.5;
}
.fx-overlimit-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* Region picker — slot-backed device action chooser. Matches the
   portal's design language: fx-card shell, accent-soft hover, status
   chip on the right. Active region gets the success-tinted border so
   it's obvious which one the customer is on right now. */
.fx-region-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fx-region-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: var(--r-md, 10px);
  background: var(--bg-card, var(--bg-2));
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: border-color .12s ease, background .12s ease, transform .08s ease;
}
.fx-region-btn:hover:not(:disabled) {
  border-color: var(--accent);
  background: color-mix(in oklab, var(--accent) 6%, var(--bg-card, var(--bg-2)));
}
.fx-region-btn:active:not(:disabled) {
  transform: translateY(1px);
}
.fx-region-btn:disabled {
  opacity: 0.6;
  cursor: progress;
}
.fx-region-btn.is-active {
  border-color: color-mix(in oklab, var(--success) 50%, var(--border));
  background: color-mix(in oklab, var(--success) 6%, var(--bg-card, var(--bg-2)));
}
.fx-region-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--accent) 14%, transparent);
  color: var(--accent);
}
.fx-region-btn.is-active .fx-region-icon {
  background: color-mix(in oklab, var(--success) 16%, transparent);
  color: var(--success);
}
.fx-region-info {
  flex: 1;
  min-width: 0;
}
.fx-region-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 2px;
}
.fx-region-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
</style>
