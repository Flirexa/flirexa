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
              <template v-if="primaryDevice.server_name">
                <span style="margin:0 6px; color:var(--text-4)">·</span>
                <span>{{ primaryDevice.server_name }}</span>
              </template>
            </template>
            <template v-else>{{ statusSub }}</template>
          </div>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap">
          <button v-if="!devices.length && subscription.status === 'active'"
                  class="fx-btn fx-btn-primary"
                  :disabled="creatingDevice || (subscription.max_devices || 1) < 1"
                  @click="showAddDeviceModal = true">
            <FxIcon name="plus" :size="14" /> {{ $t('dash.addDevice') }}
          </button>
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
          <span>{{ devices.length }}</span>
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
          <!-- Soft-downgrade banner: shown when user has more devices than the
               new plan supports. Existing devices keep working until renewal —
               at that point the oldest excess get auto-pruned, keeping the N
               most recently-used. The banner gives them a heads-up so they
               can choose which device to keep instead of letting us pick. -->
          <div v-if="subscription.over_device_limit"
               class="fx-card" style="padding:12px 14px; background:var(--warning-soft); border-color:color-mix(in oklab, var(--warning) 30%, var(--border)); margin-bottom:14px">
            <div style="display:flex; gap:10px; align-items:flex-start; font-size:13px">
              <FxIcon name="warning" :size="16" style="color:var(--warning); flex-shrink:0; margin-top:2px" />
              <div>
                <strong>
                  {{ $t('dash.overDeviceLimit', { used: subscription.devices_used, max: subscription.max_devices }) ||
                    `You have ${subscription.devices_used} devices but your current plan supports ${subscription.max_devices}.` }}
                </strong>
                <div style="margin-top:4px; color:var(--text-2)">
                  {{ $t('dash.overDeviceLimitHint') ||
                    'All devices will keep working until renewal. To pick which device to keep, remove the extras yourself before the next billing date — otherwise the oldest will be removed automatically.' }}
                </div>
                <a href="#" @click.prevent="showUpgradeModal = true" style="color:var(--accent); margin-top:6px; display:inline-block">
                  {{ $t('dash.upgradePlan') }} →
                </a>
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
            <button class="fx-btn fx-btn-danger-ghost fx-btn-sm" @click="cancelSubscription">
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
            <button class="fx-action primary"
                    :disabled="creatingDevice || devices.length >= (subscription.max_devices || 1) || subscription.status !== 'active'"
                    @click="showAddDeviceModal = true">
              <span class="fx-action-icon"><FxIcon name="plus" :size="16" /></span>
              <span class="fx-action-text">
                <span class="fx-action-title">{{ $t('dash.addDevice') }}</span>
                <span class="fx-action-sub">{{ $t('dash.addDeviceSub') }}</span>
              </span>
            </button>
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
              <span style="color:var(--text-3); font-weight:500; margin-left:6px">{{ devices.length }} / {{ subscription.max_devices || 1 }}</span>
            </h3>
            <button class="fx-btn fx-btn-ghost fx-btn-sm"
                    :disabled="creatingDevice || devices.length >= (subscription.max_devices || 1) || subscription.status !== 'active'"
                    @click="showAddDeviceModal = true">
              <FxIcon name="plus" :size="13" /> {{ $t('common.add') }}
            </button>
          </div>
          <div v-if="!devices.length">
            <div class="fx-empty">
              <div class="fx-empty-icon"><FxIcon name="phone" :size="22" /></div>
              <h3 class="fx-empty-title">{{ $t('dash.noDevicesTitle') }}</h3>
              <p class="fx-empty-sub">{{ $t('dash.noDevicesYet') }}</p>
            </div>
          </div>
          <div v-else>
            <div v-for="device in devices" :key="device.id" class="fx-device-row">
              <span class="fx-device-icon"><FxIcon :name="devicePlatformIcon(device)" :size="16" /></span>
              <div class="fx-device-info">
                <div class="fx-device-name">
                  {{ device.name }}
                  <span class="fx-badge" :class="device.enabled ? 'fx-badge-success' : 'fx-badge-neutral'">
                    {{ device.enabled ? $t('dash.deviceConnected') : $t('dash.deviceDisconnected') }}
                  </span>
                </div>
                <div class="fx-device-meta">
                  <span style="font-family:var(--mono)">{{ device.ipv4 || '—' }}</span>
                  <template v-if="device.server_name">
                    <span style="margin:0 6px; color:var(--text-4)">·</span>
                    <span style="font-family:inherit">{{ device.server_name }}</span>
                  </template>
                  <span style="margin:0 6px; color:var(--text-4)">·</span>
                  <span style="font-family:inherit">{{ protocolLabel(device.server_type) }}</span>
                </div>
              </div>
              <div class="fx-device-actions">
                <button class="fx-icon-btn-sm" :title="$t('dash.downloadConfig')" @click="downloadDeviceConfig(device)">
                  <FxIcon name="download" :size="14" />
                </button>
                <button class="fx-icon-btn-sm" title="QR" @click="showDeviceConfig(device)">
                  <FxIcon name="qr" :size="14" />
                </button>
                <button class="fx-icon-btn-sm danger" :title="$t('dash.deleteDevice')" @click="deleteDevice(device)">
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
            <label class="fx-switch">
              <input type="checkbox" v-model="autoRenew" @change="toggleAutoRenew" />
              <span class="fx-switch-track"></span>
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
            <button v-if="qrUrl" class="fx-btn fx-btn-secondary" @click="downloadQRImage">{{ $t('dash.downloadQR') }}</button>
            <button class="fx-btn fx-btn-primary" @click="downloadCurrentConfig">{{ downloadConfigButtonText }}</button>
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

const router = useRouter()
const { t } = useI18n()

const subscription = ref({})
const devices = ref([])
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
  return tier.charAt(0).toUpperCase() + tier.slice(1)
})
const expiryDate = computed(() => subscription.value.expiry_date
  ? new Date(subscription.value.expiry_date).toLocaleDateString()
  : t('dash.never'))
const statusLabel = computed(() => {
  const m = { active: t('dash.statusActive'), inactive: t('dash.statusInactive'), expired: t('dash.statusExpired') }
  return m[subscription.value.status] || subscription.value.status || '—'
})
const statusBadgeFx = computed(() => {
  const s = subscription.value.status
  if (s === 'active') return 'fx-badge-success'
  if (s === 'expired') return 'fx-badge-danger'
  return 'fx-badge-neutral'
})
// Pick the most likely "active" device — prefer enabled, then first one.
const primaryDevice = computed(() => {
  if (!devices.value.length) return null
  return devices.value.find(d => d.enabled) || devices.value[0] || null
})

const orbClass = computed(() => {
  if (subscription.value.status !== 'active') return 'off'
  if (!primaryDevice.value || !primaryDevice.value.enabled) return 'warn'
  return ''
})

const statusTitle = computed(() => {
  if (subscription.value.status !== 'active') {
    return subscription.value.status === 'expired'
      ? t('dash.statusBannerExpired')
      : t('dash.statusBannerInactive')
  }
  if (primaryDevice.value && primaryDevice.value.enabled) {
    const name = primaryDevice.value.server_name
      || (primaryDevice.value.name)
      || t('dash.statusVpnReady')
    return t('dash.statusConnectedTo', { server: name })
  }
  if (primaryDevice.value && !primaryDevice.value.enabled) {
    return t('dash.statusDeviceDisabled', { name: primaryDevice.value.name })
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
    used: devices.value.length,
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

const devicesUsageHint = computed(() => {
  const used = devices.value.length
  const max = subscription.value.max_devices || 1
  if (used === 0) return t('dash.devicesNoneConnected')
  if (used >= max) return t('dash.devicesAllUsed')
  return t('dash.devicesAvailable', { count: max - used })
})

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
const loadServers = async () => {
  try { const { data } = await portalApi.getServers(); servers.value = data || [] } catch { /* ignore */ }
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
</style>
