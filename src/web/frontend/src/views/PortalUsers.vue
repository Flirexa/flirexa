<template>
  <div class="portal-users-page">
    <!-- Header -->
    <div class="d-flex flex-column flex-md-row justify-content-between align-items-stretch align-items-md-center gap-2 mb-3 mobile-toolbar">
      <h6 class="mb-0">{{ $t('portalUsers.title') || 'Portal Users' }} <span class="text-muted small" v-if="total > 0">({{ total }})</span></h6>
      <div class="d-flex flex-wrap gap-2 mobile-filter-bar">
        <a href="/api/v1/portal-users/export/users" class="btn btn-sm pu-btn-ghost" download>
          {{ $t('portalUsersExtra.exportUsers') || 'Export CSV' }}
        </a>
        <a href="/api/v1/portal-users/export/payments" class="btn btn-sm pu-btn-ghost" download>
          {{ $t('portalUsersExtra.exportPayments') || 'Payments CSV' }}
        </a>
        <button class="btn btn-sm btn-outline-secondary" @click="showBroadcast = !showBroadcast">
          {{ $t('portalUsers.broadcast') || 'Broadcast' }}
        </button>
        <button class="btn btn-sm btn-primary" @click="showCreateAccount = true">
          + {{ $t('portalUsers.createAccount') }}
        </button>
      </div>
    </div>

    <!-- Create Account Modal -->
    <div v-if="showCreateAccount" class="modal d-block" style="background:rgba(0,0,0,.5)" @click.self="showCreateAccount=false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ $t('portalUsers.createAccountTitle') }}</h5>
            <button class="btn-close" @click="showCreateAccount=false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-2">
              <label class="form-label small fw-bold">{{ $t('portalUsers.emailLabel') }}</label>
              <input type="email" class="form-control form-control-sm" v-model="newAccount.email" placeholder="user@example.com" />
            </div>
            <div class="mb-2">
              <label class="form-label small fw-bold">{{ $t('portalUsers.usernameLabel') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="newAccount.username" placeholder="username" />
            </div>
            <div class="mb-2">
              <label class="form-label small fw-bold">{{ $t('portalUsers.passwordLabel') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="newAccount.password" placeholder="Min 6 characters" />
            </div>
            <div class="mb-2">
              <label class="form-label small fw-bold">{{ $t('portalUsers.fullNameLabel') }}</label>
              <input type="text" class="form-control form-control-sm" v-model="newAccount.full_name" />
            </div>
            <div class="row g-2 mb-2">
              <div class="col-6">
                <label class="form-label small fw-bold">{{ $t('portalUsers.subscriptionTier') }}</label>
                <select class="form-select form-select-sm" v-model="newAccount.tier">
                  <option value="free">{{ $t('portalUsers.free') }}</option>
                  <option v-for="t in tiers" :key="t.tier" :value="t.tier">{{ t.name }}</option>
                </select>
              </div>
              <div class="col-6">
                <label class="form-label small fw-bold">{{ $t('portalUsers.durationDays') }}</label>
                <input type="number" class="form-control form-control-sm" v-model.number="newAccount.duration_days" min="1" max="3650" />
              </div>
            </div>
            <div v-if="createAccountError" class="alert alert-danger py-1 px-2 small mt-2 mb-0">{{ createAccountError }}</div>
            <div v-if="createAccountSuccess" class="alert alert-success py-1 px-2 small mt-2 mb-0">{{ createAccountSuccess }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-sm btn-secondary" @click="showCreateAccount=false">{{ $t('common.cancel') }}</button>
            <button class="btn btn-sm btn-success" @click="createAccount" :disabled="creatingAccount || !newAccount.email || !newAccount.username || !newAccount.password">
              <span v-if="creatingAccount" class="spinner-border spinner-border-sm me-1"></span>
              {{ $t('common.create') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Broadcast Panel -->
    <div v-if="showBroadcast" class="stat-card mb-4">
      <div class="row g-2 align-items-end">
        <div class="col-md-6">
          <label class="form-label small fw-bold">{{ $t('portalUsers.broadcastMsg') || 'Message (supports HTML)' }}</label>
          <textarea class="form-control form-control-sm" rows="2" v-model="broadcastText" :placeholder="$t('portalUsers.broadcastPlaceholder') || 'Type message for all users...'"></textarea>
        </div>
        <div class="col-md-3">
          <label class="form-label small fw-bold">{{ $t('portalUsers.broadcastTier') || 'Tier filter' }}</label>
          <select class="form-select form-select-sm" v-model="broadcastTier">
            <option value="">{{ $t('portalUsers.allUsers') || 'All active users' }}</option>
            <option v-for="t in tiers" :key="t.tier" :value="t.tier">{{ t.name }}</option>
          </select>
        </div>
        <div class="col-md-3">
          <button class="btn btn-sm btn-primary w-100" @click="sendBroadcast" :disabled="!broadcastText.trim() || broadcastSending">
            <span v-if="broadcastSending" class="spinner-border spinner-border-sm me-1"></span>
            {{ $t('portalUsers.sendBroadcast') || 'Send to all' }}
          </button>
          <small v-if="broadcastResult" class="d-block mt-1" :class="broadcastResult.startsWith('Error') ? 'text-danger' : 'text-success'">{{ broadcastResult }}</small>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="pu-filters mb-4">
      <div class="pu-filters__search">
        <span class="pu-filters__search-icon"><i class="mdi mdi-magnify"></i></span>
        <input
          type="text"
          class="form-control form-control-sm pu-filters__input"
          :placeholder="$t('portalUsers.searchPlaceholder') || 'Search by name or email...'"
          v-model="search"
          @input="debouncedLoad"
        />
      </div>
      <select class="form-select form-select-sm pu-filters__select" v-model="filterTier" @change="loadUsers">
        <option value="">{{ $t('portalUsers.allTiers') || 'All Tiers' }}</option>
        <option v-for="t in tiers" :key="t.tier" :value="t.tier">{{ t.name }}</option>
      </select>
      <select class="form-select form-select-sm pu-filters__select" v-model="filterStatus" @change="loadUsers">
        <option value="">{{ $t('portalUsers.allStatuses') || 'All Statuses' }}</option>
        <option value="active">{{ $t('portalUsers.active') || 'Active' }}</option>
        <option value="banned">{{ $t('portalUsers.banned') || 'Banned' }}</option>
        <option value="inactive">{{ $t('portalUsers.inactive') || 'Inactive' }}</option>
      </select>
      <button class="btn btn-sm btn-outline-secondary pu-filters__refresh" @click="loadUsers" :disabled="loading">
        <span v-if="loading" class="spinner-border spinner-border-sm"></span>
        <i v-else class="mdi mdi-refresh"></i>
      </button>
    </div>

    <!-- Users Table -->
    <div class="table-card">
      <div v-if="loading && users.length === 0" class="text-center py-4">
        <span class="spinner-border spinner-border-sm"></span> {{ $t('common.loading') }}
      </div>
      <div v-else-if="users.length === 0" class="text-center text-muted py-4">
        {{ $t('portalUsers.noUsers') || 'No portal users found' }}
      </div>
      <div v-else class="table-responsive">
        <table class="table table-hover mb-0 pu-table">
          <thead>
            <tr>
              <th>{{ $t('portalUsers.username') || 'Username' }}</th>
              <th class="d-none d-md-table-cell">{{ $t('portalUsers.email') || 'Email' }}</th>
              <th class="d-none d-sm-table-cell">{{ $t('portalUsers.tier') || 'Tier' }}</th>
              <th class="d-none d-sm-table-cell">{{ $t('common.status') || 'Status' }}</th>
              <th class="d-none d-lg-table-cell text-center">{{ $t('portalUsers.devices') || 'Devices' }}</th>
              <th class="d-none d-lg-table-cell">{{ $t('portalUsers.lastLogin') || 'Last Login' }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(user, idx) in users" :key="user.id" :class="idx % 2 === 1 ? 'pu-row-alt' : ''">
              <td>
                <div class="pu-username">{{ user.username }}</div>
                <div class="pu-email d-md-none">{{ user.email }}</div>
                <!-- xs: inline status + tier -->
                <div class="d-sm-none mt-1 d-flex align-items-center gap-1 flex-wrap">
                  <span class="pu-tier-badge" :class="puTierClass(user.tier)">{{ user.tier || 'free' }}</span>
                  <span v-if="user.is_banned" class="badge badge-offline" style="font-size:.65rem">{{ $t('portalUsers.banned') || 'Banned' }}</span>
                  <span v-else-if="!user.is_active" class="badge badge-soft-secondary" style="font-size:.65rem">{{ $t('portalUsers.inactive') || 'Inactive' }}</span>
                  <span v-else class="badge badge-online" style="font-size:.65rem">{{ $t('portalUsers.active') || 'Active' }}</span>
                </div>
              </td>
              <td class="d-none d-md-table-cell">
                <span class="pu-email">{{ user.email }}</span>
              </td>
              <td class="d-none d-sm-table-cell">
                <span class="pu-tier-badge" :class="puTierClass(user.tier)">{{ user.tier || 'free' }}</span>
              </td>
              <td class="d-none d-sm-table-cell">
                <span v-if="user.is_banned" class="badge badge-offline">{{ $t('portalUsers.banned') || 'Banned' }}</span>
                <span v-else-if="!user.is_active" class="pu-status-badge pu-status-badge--inactive">{{ $t('portalUsers.inactive') || 'Inactive' }}</span>
                <span v-else class="badge badge-online">{{ $t('portalUsers.active') || 'Active' }}</span>
              </td>
              <td class="d-none d-lg-table-cell text-center">{{ user.devices_count }}</td>
              <td class="d-none d-lg-table-cell">
                <span class="pu-date" :class="!user.last_login ? 'pu-date--never' : ''">{{ user.last_login ? formatDate(user.last_login) : $t('portalUsers.never') }}</span>
              </td>
              <td>
                <button class="btn btn-sm pu-detail-btn" @click="openDetail(user.id)">
                  {{ $t('portalUsers.details') || 'Details' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="total > limit" class="d-flex justify-content-between align-items-center p-3 border-top mobile-pagination">
        <small class="text-muted">
          {{ $t('common.showing') }} {{ offset + 1 }}-{{ Math.min(offset + limit, total) }} / {{ total }}
        </small>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-primary" :disabled="offset === 0" @click="offset -= limit; loadUsers()">
            {{ $t('common.prev') }}
          </button>
          <button class="btn btn-outline-primary" :disabled="offset + limit >= total" @click="offset += limit; loadUsers()">
            {{ $t('common.next') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="showDetail" class="modal d-block" tabindex="-1" @mousedown.self="showDetail=false">
      <div class="modal-dialog modal-xl modal-dialog-scrollable">
        <div class="modal-content">
          <!-- Header with status indicator -->
          <div class="modal-header border-secondary py-2">
            <div v-if="detail" class="d-flex align-items-center gap-2">
              <div class="user-avatar" :class="avatarClass">
                {{ detail.username ? detail.username.charAt(0).toUpperCase() : '?' }}
              </div>
              <div>
                <h6 class="mb-0">{{ detail.username }}</h6>
                <small class="text-muted">{{ detail.email }}</small>
              </div>
              <span v-if="detail.is_banned" class="badge badge-offline ms-2">{{ $t('portalUsers.banned') }}</span>
              <span v-else-if="!detail.is_active" class="badge badge-soft-secondary ms-2">{{ $t('portalUsers.inactive') }}</span>
              <span v-else class="badge badge-online ms-2">{{ $t('portalUsers.active') }}</span>
            </div>
            <div v-else>
              <h6 class="mb-0">{{ $t('common.loading') }}</h6>
            </div>
            <button type="button" class="btn-close" @click="showDetail=false"></button>
          </div>

          <div class="modal-body" v-if="detailLoading">
            <div class="text-center py-4"><span class="spinner-border"></span></div>
          </div>
          <div class="modal-body p-0" v-else-if="detail">

            <!-- Tabs -->
            <ul class="nav nav-tabs nav-fill border-secondary px-3 pt-2" style="border-bottom: 1px solid var(--bs-border-color);">
              <li class="nav-item">
                <a class="nav-link" :class="{ active: activeTab === 'info' }" href="#" @click.prevent="activeTab='info'">
                  {{ $t('portalUsers.details') || 'Info' }}
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: activeTab === 'subscription' }" href="#" @click.prevent="activeTab='subscription'">
                  {{ $t('portalUsers.subscription') || 'Subscription' }}
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: activeTab === 'devices' }" href="#" @click.prevent="activeTab='devices'">
                  {{ $t('portalUsers.devices') || 'Devices' }}
                  <span class="badge badge-soft-secondary ms-1">{{ detail.devices.length }}</span>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: activeTab === 'payments' }" href="#" @click.prevent="activeTab='payments'">
                  {{ $t('portalUsers.paymentHistory') || 'Payments' }}
                  <span class="badge badge-soft-secondary ms-1">{{ detail.payments.length }}</span>
                </a>
              </li>
            </ul>

            <div class="p-3">

              <!-- TAB: Info -->
              <div v-if="activeTab === 'info'">
                <div class="row g-3 mb-3">
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsers.fullName') || 'Full Name' }}</small>
                      <span class="fw-medium">{{ detail.full_name || '-' }}</span>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsers.registered') || 'Registered' }}</small>
                      <span>{{ formatDate(detail.created_at) }}</span>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsers.lastLogin') || 'Last Login' }}</small>
                      <span>{{ formatDate(detail.last_login) }}</span>
                    </div>
                  </div>
                </div>

                <!-- Referral info -->
                <div class="row g-3 mb-3" v-if="detail.referral_code">
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsersExtra.referralCode') || 'Referral Code' }}</small>
                      <code class="fw-bold">{{ detail.referral_code }}</code>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsersExtra.referredBy') || 'Referred By' }}</small>
                      <span>{{ detail.referred_by_username || '-' }}</span>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <div class="stat-card p-3 h-100">
                      <small class="text-muted d-block mb-1">{{ $t('portalUsersExtra.referralCount') || 'Referrals' }}</small>
                      <span class="fw-bold">{{ detail.referral_count ?? 0 }}</span>
                    </div>
                  </div>
                </div>

                <!-- Ban reason -->
                <div v-if="detail.is_banned && detail.ban_reason" class="alert alert-danger py-2 mb-3">
                  <small class="fw-medium">{{ $t('portalUsers.banReason') || 'Ban reason' }}:</small> {{ detail.ban_reason }}
                </div>

                <!-- Action buttons -->
                <div class="user-actions">
                  <div class="user-actions-primary d-flex flex-wrap gap-2">
                    <button v-if="detail.is_active" class="btn btn-sm btn-outline-warning" @click="deactivateUser" :disabled="actionLoading">
                      <span v-if="actionLoading" class="spinner-border spinner-border-sm me-1"></span>
                      {{ $t('portalUsers.deactivate') || 'Deactivate' }}
                    </button>
                    <button v-else class="btn btn-sm btn-success" @click="activateUser" :disabled="actionLoading">
                      <span v-if="actionLoading" class="spinner-border spinner-border-sm me-1"></span>
                      {{ $t('portalUsers.activate') || 'Activate' }}
                    </button>
                    <button v-if="!detail.is_banned" class="btn btn-sm btn-outline-danger" @click="banUser" :disabled="actionLoading">
                      {{ $t('portalUsers.ban') || 'Ban User' }}
                    </button>
                    <button v-else class="btn btn-sm btn-outline-success" @click="unbanUser" :disabled="actionLoading">
                      {{ $t('portalUsers.unban') || 'Unban User' }}
                    </button>
                    <button v-if="detail.telegram_id" class="btn btn-sm btn-outline-primary" @click="showMsgInput = !showMsgInput">
                      {{ $t('portalUsers.sendMessage') || 'Send Message' }}
                    </button>
                  </div>
                  <div class="user-actions-danger">
                    <button class="btn btn-sm btn-outline-danger" @click="deleteUser" :disabled="actionLoading">
                      {{ $t('portalUsers.deleteUser') || 'Delete User' }}
                    </button>
                  </div>
                </div>

                <!-- Send Message Input -->
                <div v-if="showMsgInput" class="mt-3">
                  <div class="input-group input-group-sm">
                    <input type="text" class="form-control" v-model="msgText" :placeholder="$t('portalUsers.messagePlaceholder') || 'Type a message...'" @keyup.enter="sendMessage">
                    <button class="btn btn-primary" @click="sendMessage" :disabled="!msgText.trim() || sendingMsg">
                      <span v-if="sendingMsg" class="spinner-border spinner-border-sm"></span>
                      <span v-else>{{ $t('portalUsers.send') || 'Send' }}</span>
                    </button>
                  </div>
                  <small v-if="msgResult" class="text-success">{{ msgResult }}</small>
                  <small v-if="msgError" class="text-danger">{{ msgError }}</small>
                </div>
              </div>

              <!-- TAB: Subscription -->
              <div v-if="activeTab === 'subscription'">
                <div v-if="detail.subscription" class="mb-3">
                  <!-- Subscription overview cards -->
                  <div class="row g-3 mb-3">
                    <div class="col-md-3">
                      <div class="stat-card p-3 h-100 text-center">
                        <small class="text-muted d-block mb-1">{{ $t('portalUsers.tier') }}</small>
                        <span class="badge fs-6" :class="tierBadge(detail.subscription.tier)">{{ detail.subscription.tier }}</span>
                        <div class="mt-1">
                          <span class="badge" :class="subStatusBadge(detail.subscription.status)">{{ detail.subscription.status }}</span>
                        </div>
                      </div>
                    </div>
                    <div class="col-md-3">
                      <div class="stat-card p-3 h-100 text-center">
                        <small class="text-muted d-block mb-1">{{ $t('portalUsers.expiryDate') || 'Expiry' }}</small>
                        <span class="fw-medium">{{ detail.subscription.expiry_date ? formatDate(detail.subscription.expiry_date) : 'Never' }}</span>
                        <div v-if="detail.subscription.days_remaining != null" class="mt-1">
                          <span class="badge" :class="detail.subscription.days_remaining <= 3 ? 'badge-offline' : detail.subscription.days_remaining <= 7 ? 'badge-warning' : 'badge-soft-info'">
                            {{ detail.subscription.days_remaining }}d left
                          </span>
                        </div>
                      </div>
                    </div>
                    <div class="col-md-3">
                      <div class="stat-card p-3 h-100 text-center">
                        <small class="text-muted d-block mb-1">{{ $t('portalUsers.trafficUsed') || 'Traffic' }}</small>
                        <span class="fw-medium">{{ (detail.subscription.traffic_used_gb ?? 0).toFixed(2) }} GB</span>
                        <small class="text-muted" v-if="detail.subscription.traffic_limit_gb"> / {{ detail.subscription.traffic_limit_gb }} GB</small>
                        <small class="text-muted" v-else> / ∞</small>
                        <!-- Traffic progress bar -->
                        <div v-if="detail.subscription.traffic_limit_gb" class="progress mt-2" style="height: 6px;">
                          <div class="progress-bar" :class="subTrafficBarClass" :style="{ width: subTrafficPercent + '%' }"></div>
                        </div>
                      </div>
                    </div>
                    <div class="col-md-3">
                      <div class="stat-card p-3 h-100 text-center">
                        <small class="text-muted d-block mb-1">{{ $t('portalUsers.maxDevices') || 'Max Devices' }}</small>
                        <span class="fw-medium fs-5">{{ detail.devices.length }} / {{ detail.subscription.max_devices }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Subscription actions -->
                  <div class="d-flex flex-wrap gap-2 mb-3">
                    <button class="btn btn-sm btn-primary" @click="showGrant = true" :disabled="actionLoading">
                      {{ $t('portalUsers.grantSub') || 'Grant Subscription' }}
                    </button>
                    <button class="btn btn-sm btn-outline-primary" @click="showExtend = true" :disabled="!detail.subscription || actionLoading">
                      {{ $t('portalUsers.extendSub') || 'Extend' }}
                    </button>
                    <button class="btn btn-sm btn-outline-info" @click="resetTraffic" :disabled="!detail.subscription || actionLoading">
                      {{ $t('portalUsers.resetTraffic') || 'Reset Traffic' }}
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="cancelSub" :disabled="!detail.subscription || detail.subscription.status === 'cancelled' || actionLoading">
                      {{ $t('portalUsers.cancelSub') || 'Cancel Subscription' }}
                    </button>
                  </div>
                </div>
                <div v-else class="text-muted mb-3">
                  {{ $t('portalUsers.noSubscription') || 'No subscription' }}
                  <button class="btn btn-sm btn-primary ms-2" @click="showGrant = true" :disabled="actionLoading">
                    {{ $t('portalUsers.grantSub') || 'Grant Subscription' }}
                  </button>
                </div>

                <!-- Grant form -->
                <div v-if="showGrant" class="stat-card p-3 mb-3">
                  <h6 class="mb-2">{{ $t('portalUsers.grantSub') }}</h6>
                  <div class="row g-2">
                    <div class="col-md-6">
                      <label class="form-label small">{{ $t('portalUsers.tier') }}</label>
                      <select class="form-select form-select-sm" v-model="grantForm.tier">
                        <option v-for="t in tiers" :key="t.tier" :value="t.tier">{{ t.name }}</option>
                      </select>
                    </div>
                    <div class="col-md-6">
                      <label class="form-label small">{{ $t('portalUsers.durationDays') || 'Duration (days)' }}</label>
                      <input type="number" class="form-control form-control-sm" v-model.number="grantForm.duration_days" min="1" max="3650" />
                    </div>
                  </div>
                  <div class="mt-2 d-flex gap-2">
                    <button class="btn btn-sm btn-primary" @click="doGrant" :disabled="actionLoading">
                      <span v-if="actionLoading" class="spinner-border spinner-border-sm me-1"></span>
                      {{ $t('common.confirm') }}
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" @click="showGrant=false">{{ $t('common.cancel') }}</button>
                  </div>
                </div>

                <!-- Extend form -->
                <div v-if="showExtend" class="stat-card p-3 mb-3">
                  <h6 class="mb-2">{{ $t('portalUsers.extendSub') }}</h6>
                  <div class="row g-2">
                    <div class="col-md-6">
                      <label class="form-label small">{{ $t('portalUsers.durationDays') || 'Days to add' }}</label>
                      <input type="number" class="form-control form-control-sm" v-model.number="extendDays" min="1" max="3650" />
                    </div>
                  </div>
                  <div class="mt-2 d-flex gap-2">
                    <button class="btn btn-sm btn-primary" @click="doExtend" :disabled="actionLoading">
                      <span v-if="actionLoading" class="spinner-border spinner-border-sm me-1"></span>
                      {{ $t('common.confirm') }}
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" @click="showExtend=false">{{ $t('common.cancel') }}</button>
                  </div>
                </div>
              </div>

              <!-- TAB: Devices -->
              <div v-if="activeTab === 'devices'">
                <div v-if="detail.devices.length === 0" class="text-center text-muted py-4">
                  {{ $t('portalUsers.noDevices') || 'No devices linked' }}
                </div>
                <div v-else class="table-responsive">
                  <table class="table table-sm table-hover mb-0">
                    <thead>
                      <tr>
                        <th>{{ $t('common.name') }}</th>
                        <th>{{ $t('portalUsers.server') || 'Server' }}</th>
                        <th>IP</th>
                        <th>{{ $t('common.status') }}</th>
                        <th>{{ $t('portalUsers.bandwidth') || 'Bandwidth' }}</th>
                        <th>{{ $t('portalUsers.trafficUsed') || 'Traffic' }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="d in detail.devices" :key="d.id">
                        <td class="fw-medium">{{ d.name }}</td>
                        <td><small class="text-muted">{{ d.server_name }}</small></td>
                        <td><code>{{ d.ipv4 }}</code></td>
                        <td>
                          <span class="badge" :class="d.enabled ? 'badge-online' : 'badge-offline'">
                            {{ d.enabled ? 'ON' : 'OFF' }}
                          </span>
                        </td>
                        <td>{{ d.bandwidth_limit ? d.bandwidth_limit + ' Mbps' : '∞' }}</td>
                        <td>
                          <div class="d-flex align-items-center gap-2">
                            <span>{{ formatBytes((d.traffic_rx || 0) + (d.traffic_tx || 0)) }}</span>
                            <div v-if="detail.subscription && detail.subscription.traffic_limit_gb" class="progress flex-grow-1" style="height:5px; min-width:50px; max-width:80px;">
                              <div class="progress-bar" :class="trafficBarClass(d, detail.subscription)" :style="{ width: trafficBarPercent(d, detail.subscription) + '%' }"></div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- TAB: Payments -->
              <div v-if="activeTab === 'payments'">
                <div v-if="detail.payments.length === 0" class="text-center text-muted py-4">
                  {{ $t('portalUsers.noPayments') || 'No payments' }}
                </div>
                <div v-else class="table-responsive">
                  <table class="table table-sm table-hover mb-0">
                    <thead>
                      <tr>
                        <th>{{ $t('portalUsers.date') || 'Date' }}</th>
                        <th>{{ $t('portalUsers.amount') || 'Amount' }}</th>
                        <th>{{ $t('portalUsers.method') || 'Method' }}</th>
                        <th>{{ $t('common.status') }}</th>
                        <th>{{ $t('portalUsers.tier') }}</th>
                        <th>{{ $t('common.actions') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in detail.payments" :key="p.id">
                        <td><small>{{ formatDate(p.created_at) }}</small></td>
                        <td class="fw-medium">${{ p.amount_usd }}</td>
                        <td>{{ p.payment_method || '-' }}</td>
                        <td>
                          <span class="badge" :class="paymentBadge(p.status)">{{ p.status }}</span>
                        </td>
                        <td>{{ p.subscription_tier || '-' }}</td>
                        <td>
                          <div class="d-flex gap-1">
                            <button v-if="p.status === 'pending'" class="btn btn-sm btn-outline-success py-0 px-1" @click="confirmPaymentInDetail(p.id)" :disabled="actionLoading" :title="$t('portalUsers.confirmPayment')">
                              <i class="mdi mdi-check"></i>
                            </button>
                            <button v-if="p.status !== 'completed'" class="btn btn-sm btn-outline-warning py-0 px-1" @click="rejectPaymentInDetail(p.id)" :disabled="actionLoading" :title="$t('portalUsers.rejectPayment') || 'Reject'">
                              <i class="mdi mdi-close"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger py-0 px-1" @click="deletePaymentInDetail(p.id)" :disabled="actionLoading" :title="$t('common.delete')">
                              <i class="mdi mdi-trash-can-outline"></i>
                            </button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showDetail" class="modal-backdrop fade show"></div>

    <!-- All Payments Section -->
    <div class="mt-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h6 class="mb-0">{{ $t('portalUsers.allPayments') || 'All Payments' }}</h6>
        <div class="btn-group btn-group-sm">
          <button class="btn" :class="payFilter === '' ? 'btn-primary' : 'btn-outline-primary'" @click="payFilter=''; loadPayments()">
            {{ $t('clients.all') || 'All' }}
          </button>
          <button class="btn" :class="payFilter === 'pending' ? 'btn-warning' : 'btn-outline-warning'" @click="payFilter='pending'; loadPayments()">
            {{ $t('portalUsers.pending') || 'Pending' }}
          </button>
          <button class="btn" :class="payFilter === 'completed' ? 'btn-success' : 'btn-outline-success'" @click="payFilter='completed'; loadPayments()">
            {{ $t('portalUsers.completed') || 'Completed' }}
          </button>
        </div>
      </div>

      <div class="table-card">
        <div v-if="paymentsLoading" class="text-center py-3"><span class="spinner-border spinner-border-sm"></span></div>
        <div v-else-if="allPayments.length === 0" class="text-center text-muted py-3">{{ $t('portalUsers.noPayments') }}</div>
        <div v-else class="table-responsive">
          <table class="table table-hover mb-0">
            <thead>
              <tr>
                <th>{{ $t('portalUsers.date') }}</th>
                <th>{{ $t('portalUsers.username') }}</th>
                <th>{{ $t('portalUsers.amount') }}</th>
                <th>{{ $t('portalUsers.method') }}</th>
                <th>{{ $t('portalUsers.tier') }}</th>
                <th>{{ $t('common.status') }}</th>
                <th>{{ $t('common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in allPayments" :key="p.id">
                <td><small>{{ formatDate(p.created_at) }}</small></td>
                <td>{{ p.username || '-' }}</td>
                <td class="fw-medium">${{ p.amount_usd }}</td>
                <td>{{ p.payment_method || '-' }}</td>
                <td>{{ p.subscription_tier || '-' }}</td>
                <td><span class="badge" :class="paymentBadge(p.status)">{{ p.status }}</span></td>
                <td>
                  <div class="d-flex gap-1">
                    <button
                      v-if="p.status === 'pending'"
                      class="btn btn-sm btn-outline-success"
                      @click="confirmPayment(p.id)"
                      :disabled="actionLoading"
                    >
                      {{ $t('portalUsers.confirmPayment') || 'Confirm' }}
                    </button>
                    <button
                      v-if="p.status !== 'completed'"
                      class="btn btn-sm btn-outline-warning"
                      @click="rejectPayment(p.id)"
                      :disabled="actionLoading"
                    >
                      {{ $t('portalUsers.rejectPayment') || 'Reject' }}
                    </button>
                    <button
                      class="btn btn-sm btn-outline-danger"
                      @click="deletePaymentGlobal(p.id)"
                      :disabled="actionLoading"
                    >
                      {{ $t('common.delete') || 'Delete' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { portalUsersApi } from '../api'
import { formatBytes } from '../utils'

const users = ref([])
const total = ref(0)
const loading = ref(false)
const search = ref('')
const filterTier = ref('')
const filterStatus = ref('')
const limit = 50
const offset = ref(0)
const tiers = ref([])

const showDetail = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const activeTab = ref('info')

const showGrant = ref(false)
const showExtend = ref(false)
const grantForm = ref({ tier: 'basic', duration_days: 30 })
const extendDays = ref(30)
const actionLoading = ref(false)

const showMsgInput = ref(false)
const msgText = ref('')
const sendingMsg = ref(false)
const msgResult = ref('')
const msgError = ref('')

const showBroadcast = ref(false)
const broadcastText = ref('')
const broadcastTier = ref('')
const broadcastSending = ref(false)
const broadcastResult = ref('')

const allPayments = ref([])
const paymentsLoading = ref(false)
const payFilter = ref('')

const showCreateAccount = ref(false)
const creatingAccount = ref(false)
const createAccountError = ref('')
const createAccountSuccess = ref('')
const newAccount = ref({ email: '', username: '', password: '', full_name: '', tier: 'free', duration_days: 30 })

// Computed
const avatarClass = computed(() => {
  if (!detail.value) return ''
  if (detail.value.is_banned) return 'avatar-banned'
  if (!detail.value.is_active) return 'avatar-inactive'
  return 'avatar-active'
})

const subTrafficPercent = computed(() => {
  const sub = detail.value?.subscription
  if (!sub || !sub.traffic_limit_gb || sub.traffic_limit_gb <= 0) return 0
  return Math.min(100, Math.round(((sub.traffic_used_gb || 0) / sub.traffic_limit_gb) * 100))
})

const subTrafficBarClass = computed(() => {
  if (subTrafficPercent.value >= 90) return 'bg-danger'
  if (subTrafficPercent.value >= 70) return 'bg-warning'
  return 'bg-success'
})

async function createAccount() {
  creatingAccount.value = true
  createAccountError.value = ''
  createAccountSuccess.value = ''
  try {
    const res = await portalUsersApi.createAccount(newAccount.value)
    createAccountSuccess.value = res.data.message || 'Account created'
    newAccount.value = { email: '', username: '', password: '', full_name: '', tier: 'free', duration_days: 30 }
    loadUsers()
    setTimeout(() => { showCreateAccount.value = false; createAccountSuccess.value = '' }, 1500)
  } catch (e) {
    createAccountError.value = e.response?.data?.detail || 'Failed to create account'
  }
  creatingAccount.value = false
}

let debounceTimer = null
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { offset.value = 0; loadUsers() }, 300)
}

async function loadUsers() {
  loading.value = true
  try {
    const params = { limit, offset: offset.value }
    if (search.value) params.search = search.value
    if (filterTier.value) params.tier = filterTier.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await portalUsersApi.list(params)
    users.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    console.error('Failed to load portal users:', e)
  }
  loading.value = false
}

async function loadTiers() {
  try {
    const res = await portalUsersApi.getTiers()
    tiers.value = res.data
  } catch (e) {}
}

async function loadPayments() {
  paymentsLoading.value = true
  try {
    const params = { limit: 50 }
    if (payFilter.value) params.status = payFilter.value
    const res = await portalUsersApi.getPayments(params)
    allPayments.value = res.data.items
  } catch (e) {
    console.error('Failed to load payments:', e)
  }
  paymentsLoading.value = false
}

async function openDetail(userId) {
  showDetail.value = true
  detailLoading.value = true
  showGrant.value = false
  showExtend.value = false
  activeTab.value = 'info'
  try {
    const res = await portalUsersApi.get(userId)
    detail.value = res.data
  } catch (e) {
    console.error('Failed to load user detail:', e)
  }
  detailLoading.value = false
}

async function banUser() {
  const reason = prompt('Ban reason:')
  if (reason === null) return
  actionLoading.value = true
  try {
    await portalUsersApi.update(detail.value.id, { is_banned: true, ban_reason: reason })
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function unbanUser() {
  actionLoading.value = true
  try {
    await portalUsersApi.update(detail.value.id, { is_banned: false })
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function deactivateUser() {
  actionLoading.value = true
  try {
    await portalUsersApi.update(detail.value.id, { is_active: false })
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function activateUser() {
  actionLoading.value = true
  try {
    await portalUsersApi.update(detail.value.id, { is_active: true })
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function doGrant() {
  actionLoading.value = true
  try {
    await portalUsersApi.grantSubscription(detail.value.id, grantForm.value)
    showGrant.value = false
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function doExtend() {
  actionLoading.value = true
  try {
    await portalUsersApi.extendSubscription(detail.value.id, { days: extendDays.value })
    showExtend.value = false
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function cancelSub() {
  if (!confirm('Cancel this subscription?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.cancelSubscription(detail.value.id)
    await openDetail(detail.value.id)
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function resetTraffic() {
  if (!confirm('Reset traffic counters for this user?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.resetTraffic(detail.value.id)
    await openDetail(detail.value.id)
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function deleteUser() {
  if (!confirm(`Delete user "${detail.value.username}" permanently? This cannot be undone.`)) return
  actionLoading.value = true
  try {
    await portalUsersApi.deleteUser(detail.value.id)
    showDetail.value = false
    detail.value = null
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

// Payments in detail modal
async function confirmPaymentInDetail(paymentId) {
  if (!confirm('Confirm this payment?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.confirmPayment(paymentId)
    await openDetail(detail.value.id)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function rejectPaymentInDetail(paymentId) {
  if (!confirm('Reject this payment?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.rejectPayment(paymentId)
    await openDetail(detail.value.id)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function deletePaymentInDetail(paymentId) {
  if (!confirm('Delete this payment permanently?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.deletePayment(paymentId)
    await openDetail(detail.value.id)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

// Payments in global table
async function confirmPayment(paymentId) {
  if (!confirm('Confirm this payment?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.confirmPayment(paymentId)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function rejectPayment(paymentId) {
  if (!confirm('Reject this payment?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.rejectPayment(paymentId)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

async function deletePaymentGlobal(paymentId) {
  if (!confirm('Delete this payment permanently?')) return
  actionLoading.value = true
  try {
    await portalUsersApi.deletePayment(paymentId)
    await loadPayments()
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
  actionLoading.value = false
}

// Messaging
async function sendMessage() {
  if (!msgText.value.trim()) return
  sendingMsg.value = true
  msgResult.value = ''
  msgError.value = ''
  try {
    await portalUsersApi.sendMessage(detail.value.id, { message: msgText.value })
    msgResult.value = 'Message sent!'
    msgText.value = ''
    setTimeout(() => { msgResult.value = '' }, 3000)
  } catch (e) {
    msgError.value = e.response?.data?.detail || 'Failed to send'
  }
  sendingMsg.value = false
}

async function sendBroadcast() {
  if (!broadcastText.value.trim()) return
  if (!confirm(`Send this message to all ${broadcastTier.value || 'active'} users?`)) return
  broadcastSending.value = true
  broadcastResult.value = ''
  try {
    const res = await portalUsersApi.broadcast({
      message: broadcastText.value,
      tier: broadcastTier.value || null,
      only_active: true,
    })
    broadcastResult.value = `Sent: ${res.data.sent}, Failed: ${res.data.failed}`
    broadcastText.value = ''
  } catch (e) {
    broadcastResult.value = 'Error: ' + (e.response?.data?.detail || e.message)
  }
  broadcastSending.value = false
}

function tierBadge(tier) {
  const map = { free: 'badge-soft-secondary', basic: 'badge-soft-info', standard: 'badge-soft-primary', premium: 'badge-soft-warning', enterprise: 'badge-soft-danger' }
  return map[tier] || 'badge-soft-secondary'
}

function puTierClass(tier) {
  const map = { free: 'pu-tier--free', basic: 'pu-tier--basic', standard: 'pu-tier--standard', premium: 'pu-tier--premium', enterprise: 'pu-tier--enterprise', corporation: 'pu-tier--enterprise' }
  return map[tier] || 'pu-tier--free'
}

function subStatusBadge(status) {
  const map = { active: 'badge-online', expired: 'badge-offline', cancelled: 'badge-warning', suspended: 'badge-soft-secondary', pending: 'badge-soft-info' }
  return map[status] || 'badge-soft-secondary'
}

function paymentBadge(status) {
  const map = { completed: 'badge-online', pending: 'badge-warning', expired: 'badge-soft-secondary', failed: 'badge-offline', rejected: 'badge-offline' }
  return map[status] || 'badge-soft-secondary'
}

function formatDate(dt) {
  if (!dt) return '-'
  const d = new Date(dt)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function trafficBarPercent(device, sub) {
  if (!sub || !sub.traffic_limit_gb || sub.traffic_limit_gb <= 0) return 0
  const usedGB = ((device.traffic_rx || 0) + (device.traffic_tx || 0)) / (1024 * 1024 * 1024)
  return Math.min(100, Math.round((usedGB / sub.traffic_limit_gb) * 100))
}

function trafficBarClass(device, sub) {
  const pct = trafficBarPercent(device, sub)
  if (pct >= 90) return 'bg-danger'
  if (pct >= 70) return 'bg-warning'
  return 'bg-success'
}

onMounted(() => {
  loadUsers()
  loadTiers()
  loadPayments()
})
</script>

<style scoped>
/* ── Ghost button for export ───────────────────────────────── */
.pu-btn-ghost {
  color: var(--vxy-muted); border: none; background: none;
  font-size: .8rem; padding: .3rem .5rem;
  transition: color .15s;
}
.pu-btn-ghost:hover { color: var(--vxy-text); text-decoration: underline; }

/* ── Filters bar ───────────────────────────────────────────── */
.pu-filters {
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;
  background: var(--vxy-card-bg); border-radius: var(--vxy-card-radius, .5rem);
  box-shadow: var(--vxy-card-shadow); padding: .625rem .875rem;
}
.pu-filters__search {
  position: relative; flex: 1; min-width: 180px;
}
.pu-filters__search-icon {
  position: absolute; left: .5rem; top: 50%; transform: translateY(-50%);
  font-size: .75rem; pointer-events: none; opacity: .5;
}
.pu-filters__input { padding-left: 1.75rem; }
.pu-filters__select { width: auto; min-width: 120px; }
.pu-filters__refresh {
  width: 34px; height: 34px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: .375rem;
}

/* ── Table ─────────────────────────────────────────────────── */
.pu-table { font-size: .875rem; }
.pu-table thead th {
  font-size: .75rem; text-transform: uppercase; letter-spacing: .03em;
  color: var(--vxy-muted); font-weight: 600; padding: .6rem .75rem;
  border-bottom: 2px solid var(--vxy-border);
}
.pu-table tbody td {
  padding: .7rem .75rem; vertical-align: middle;
  border-bottom: 1px solid rgba(125,125,125,.08);
}
.pu-row-alt { background: rgba(125,125,125,.025); }
.pu-table tbody tr { transition: background .15s; }
.pu-table tbody tr:hover { background: rgba(115,103,240,.04); }

/* Username & email hierarchy */
.pu-username { font-weight: 600; font-size: .875rem; color: var(--vxy-heading); }
.pu-email { font-size: .78rem; color: var(--vxy-muted); }

/* Tier badges */
.pu-tier-badge {
  display: inline-block; padding: .22em .6em; border-radius: .3rem;
  font-size: .72rem; font-weight: 600; text-transform: capitalize;
  letter-spacing: .01em; white-space: nowrap;
}
.pu-tier--free { background: rgba(108,117,125,.12); color: #6c757d; }
.pu-tier--basic { background: rgba(13,202,240,.12); color: #0aa2c0; }
.pu-tier--standard { background: var(--vxy-primary-light); color: var(--vxy-primary); }
.pu-tier--premium { background: rgba(255,159,67,.15); color: #e8851c; }
.pu-tier--corporation { background: rgba(234,84,85,.1); color: #ea5455; }
.pu-tier--enterprise { background: rgba(115,103,240,.12); color: #7367f0; }

/* Status: inactive more visible */
.pu-status-badge--inactive {
  display: inline-block; padding: .2em .55em; border-radius: .3rem;
  font-size: .72rem; font-weight: 500;
  background: rgba(108,117,125,.18); color: #6c757d;
}

/* Date / never */
.pu-date { font-size: .78rem; color: var(--vxy-text); }
.pu-date--never { color: var(--vxy-muted); font-style: italic; opacity: .6; }

/* Details button */
.pu-detail-btn {
  font-size: .78rem; padding: .3rem .7rem;
  border: 1px solid var(--vxy-border); background: transparent;
  color: var(--vxy-muted); border-radius: .35rem;
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
  white-space: nowrap;
}
.pu-detail-btn:hover {
  background: var(--vxy-primary-light, rgba(115,103,240,.08));
  border-color: var(--vxy-primary);
  color: var(--vxy-primary);
}

/* ── Detail modal existing styles ──────────────────────────── */
.user-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 16px; color: #fff;
  flex-shrink: 0;
}
.avatar-active   { background: var(--vxy-success); }
.avatar-banned   { background: var(--vxy-danger); }
.avatar-inactive { background: var(--vxy-muted); }

.nav-tabs .nav-link {
  color: var(--vxy-muted); border: none;
  border-bottom: 2px solid transparent;
  padding: .5rem 1rem; font-size: .875rem;
}
.nav-tabs .nav-link.active {
  color: var(--vxy-heading); background: transparent;
  border-bottom-color: var(--vxy-primary);
}
.nav-tabs .nav-link:hover:not(.active) {
  color: var(--vxy-text); border-bottom-color: var(--vxy-border);
}

.user-actions { display: flex; align-items: flex-start; gap: .5rem; flex-wrap: wrap; }
.user-actions-primary { display: flex; flex-wrap: wrap; gap: .5rem; flex: 1; }
.user-actions-danger { margin-left: auto; }

/* ── Mobile ────────────────────────────────────────────────── */
@media (max-width: 575.98px) {
  .pu-filters { padding: .5rem; gap: .35rem; }
  .pu-filters__search { min-width: 100%; }
  .pu-filters__select { flex: 1; min-width: 0; }

  .nav-tabs { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .nav-tabs .nav-link { padding: .5rem .625rem; font-size: .8rem; white-space: nowrap; }

  .row.g-3 > .col-md-4,
  .row.g-3 > .col-md-3 { width: 100%; }

  .user-actions { flex-direction: column; gap: 0; }
  .user-actions-primary { flex-direction: column; width: 100%; gap: .5rem; }
  .user-actions-primary .btn { width: 100%; justify-content: center; }
  .user-actions-danger {
    margin-left: 0; width: 100%;
    margin-top: .75rem; padding-top: .75rem;
    border-top: 1px solid var(--bs-border-color);
  }
  .user-actions-danger .btn { width: 100%; }

  .modal-header { flex-wrap: wrap; gap: .5rem; }
  .modal-header .d-flex { flex: 1; min-width: 0; overflow: hidden; }
}
</style>
