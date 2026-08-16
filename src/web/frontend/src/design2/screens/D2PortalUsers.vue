<!-- New-design Portal Users — his exact handoff markup (toolbar + table + broadcast
     side panel; detail modal with Info/Subscription/Devices/Payments tabs).
     Wired VERBATIM to portalUsersApi (list/get/getTiers/grantSubscription/
     extendSubscription/setSubscriptionExpiry/cancelSubscription/resetTraffic/
     addDeviceSlot/update/deleteUser/confirmPayment/rejectPayment/deletePayment).
     Detail modal carries the "Set Expiry Date" feature + payments. -->
<template>
  <div>
    <!-- ===== PORTAL USERS ===== -->
    <div class="d2-portal-toolbar" style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <!-- Search lives in the top app-header bar (registered via the header config
           below, onSearch → reload). The old inline duplicate here was wired to a
           no-op handler and never filtered — removed per customer report. -->
      <select v-model="filterTier" @change="reload" style="height:34px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;padding:0 9px;font:inherit;font-size:12.5px;outline:none;cursor:pointer">
        <option value="">{{ tr('portalUsers.allTiers') || 'All tiers' }}</option>
        <option v-for="o in puTierOptions" :key="o" :value="o">{{ o }}</option>
      </select>
      <select v-model="filterStatus" @change="reload" style="height:34px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;padding:0 9px;font:inherit;font-size:12.5px;outline:none;cursor:pointer">
        <option value="">{{ tr('portalUsers.allStatuses') || 'All status' }}</option>
        <option value="active">{{ tr('portalUsers.active') || 'Active' }}</option>
        <option value="inactive">{{ tr('portalUsers.inactive') || 'Inactive' }}</option>
        <option value="banned">{{ tr('portalUsers.banned') || 'Banned' }}</option>
      </select>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button @click="openCreate" style="height:34px;padding:0 12px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:6px" class="d2-accentbtn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"></path></svg>{{ tr('portalUsers.createAccount') || 'Create account' }}</button>
        <button @click="reload" class="d2-tbbtn">{{ tr('common.refresh') || 'Refresh' }}</button>
        <button @click="exportUsersCsv" class="d2-tbbtn">{{ tr('portalUsers.exportCsv') || 'Export CSV' }}</button>
        <button @click="exportPaymentsCsv" class="d2-tbbtn">{{ tr('portalUsers.exportPaymentsCsv') || 'Payments CSV' }}</button>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 320px;gap:14px;align-items:start">
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div class="d2-desktop-only" style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left">
            <th class="d2-th" style="padding-left:20px">{{ tr('portalUsers.user') || 'User' }}</th>
            <th class="d2-th">{{ tr('portalUsers.email') || 'Email' }}</th>
            <th class="d2-th">{{ tr('portalUsers.tier') || 'Tier' }}</th>
            <th class="d2-th">{{ tr('portalUsers.devices') || 'Devices' }}</th>
            <th class="d2-th">{{ tr('portalUsers.lastLogin') || 'Last login' }}</th>
            <th class="d2-th">{{ tr('portalUsers.status') || 'Status' }}</th>
            <th class="d2-th" style="text-align:right;padding-right:20px"></th>
          </tr></thead>
          <tbody>
            <tr v-for="u in rows" :key="u.id" @click="openDetail(u.id)" style="border-top:1px solid var(--border);cursor:pointer" class="d2-row">
              <td style="padding:12px 20px"><div style="display:flex;align-items:center;gap:10px"><span style="width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:650;flex:none">{{ u.initials }}</span><div style="min-width:0"><div style="font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ u.name }}</div><div style="font-size:11.5px;color:var(--text-3)">{{ u.username }}</div></div></div></td>
              <td style="padding:12px 12px;color:var(--text-2);font-size:12.5px">{{ u.email }}</td>
              <td style="padding:12px 12px"><span :style="{ fontSize:'10.5px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', color:u.tierColor, background:u.tierBg }">{{ u.tier }}</span></td>
              <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ u.devicesLabel }}</td>
              <td style="padding:12px 12px;font-size:12px;color:var(--text-3)">{{ u.lastLogin }}</td>
              <td style="padding:12px 12px"><span :style="{ display:'inline-flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:550, color:u.statusColor }"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:u.statusColor }"></span>{{ u.statusLabel }}</span></td>
              <td style="padding:12px 20px;text-align:right"><span style="font-size:12px;color:var(--accent);font-weight:550">{{ tr('portalUsers.details') || 'Details' }}</span></td>
            </tr>
            <tr v-if="!rows.length"><td colspan="7" style="padding:30px;text-align:center;color:var(--text-3)">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('portalUsers.noUsers') || 'No users') }}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="d2-mobile-only d2-mobile-list" style="padding:10px">
        <button v-for="u in rows" :key="'mobile-'+u.id" @click="openDetail(u.id)" class="d2-mobile-item d2-portal-mobile-user">
          <span style="width:34px;height:34px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:650;flex:none">{{ u.initials }}</span>
          <span class="d2-mobile-main" style="text-align:left">
            <span class="d2-mobile-title" style="display:block">{{ u.name }}</span>
            <span class="d2-mobile-sub" style="display:block">{{ u.email }}</span>
          </span>
          <span style="text-align:right;flex:none">
            <span :style="{display:'block',fontSize:'10.5px',fontWeight:600,padding:'2px 7px',borderRadius:'6px',color:u.tierColor,background:u.tierBg}">{{ u.tier }}</span>
            <span :style="{display:'block',fontSize:'10.5px',fontWeight:550,color:u.statusColor,marginTop:'4px'}">{{ u.statusLabel }}</span>
          </span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" stroke-width="2"><path d="M9 6l6 6-6 6"></path></svg>
        </button>
        <div v-if="!rows.length" style="padding:22px;text-align:center;color:var(--text-3)">{{ loading ? (tr('common.loading') || 'Loading…') : (tr('portalUsers.noUsers') || 'No users') }}</div>
      </div>
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;padding:12px;font-size:13px;color:var(--text-2);border-top:1px solid var(--border)">
        <button class="d2-tbbtn" :disabled="offset === 0" @click="offset -= limit; loadUsers()">‹</button>
        <span>{{ Math.floor(offset / limit) + 1 }} · {{ total }} {{ tr('portalUsers.total') || 'total' }}</span>
        <button class="d2-tbbtn" :disabled="offset + limit >= total" @click="offset += limit; loadUsers()">›</button>
      </div>
      </div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:18px 20px">
        <div style="font-weight:600;font-size:14px;margin-bottom:4px">{{ tr('portalUsers.broadcast') || 'Broadcast' }}</div>
        <div style="font-size:12px;color:var(--text-3);margin-bottom:14px">POST /portal-users/broadcast</div>
        <select v-model="broadcastTier" style="width:100%;height:38px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text-2);border-radius:9px;padding:0 9px;font:inherit;font-size:12.5px;outline:none;cursor:pointer;margin-bottom:11px">
          <option value="all">{{ tr('portalUsers.allTiers') || 'All tiers' }}</option>
          <option v-for="o in puTierOptions" :key="o" :value="o">{{ o }}</option>
        </select>
        <select v-model="broadcastPlatform" style="width:100%;height:38px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text-2);border-radius:9px;padding:0 9px;font:inherit;font-size:12.5px;outline:none;cursor:pointer;margin-bottom:11px">
          <option value="all">{{ tr('portalUsers.broadcastAllPlatforms') || 'All platforms' }}</option>
          <option value="android">Android</option>
          <option value="ios">iOS</option>
        </select>
        <textarea v-model="broadcastMsg" :placeholder="tr('portalUsers.broadcastPh') || 'Message to send…'" style="width:100%;min-height:90px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;font-size:13px;outline:none"></textarea>
        <div style="display:flex;align-items:center;gap:10px;margin-top:12px">
          <button @click="broadcastActive = !broadcastActive" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background: broadcastActive ? 'var(--accent)' : 'var(--border-strong)', transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left: broadcastActive ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
          <span style="font-size:13px;color:var(--text-2)">{{ tr('portalUsers.broadcastActiveOnly') || 'Active users only' }}</span>
        </div>
        <button @click="sendBroadcast" style="width:100%;height:42px;border:none;background:var(--accent);color:#fff;border-radius:10px;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer;margin-top:14px;display:flex;align-items:center;justify-content:center;gap:8px" class="d2-accentbtn"><span v-if="broadcastBusy" style="width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ tr('portalUsers.broadcastSend') || 'Send broadcast' }}</button>
        <div v-if="broadcastResult" style="margin-top:10px;font-size:12.5px;color:var(--green,#16a34a);text-align:center">{{ broadcastResult }}</div>
      </div>
    </div>

    <!-- ===== PORTAL USER DETAIL MODAL ===== -->
    <D2Modal :open="showDetail" size="lg" @close="showDetail = false">
      <template #header>
        <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
          <span style="width:42px;height:42px;border-radius:50%;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:680;flex:none">{{ detailAdapter.initials }}</span>
          <div style="flex:1;min-width:0"><div style="font-weight:650;font-size:16px">{{ detailAdapter.name }}</div><div style="font-size:12.5px;color:var(--text-3)">{{ detailAdapter.username }}<template v-if="detailAdapter.tg"> · TG {{ detailAdapter.tg }}</template></div></div>
        </div>
      </template>

      <div v-if="detailLoading" style="color:var(--text-3);padding:16px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
      <div v-else-if="detail">
        <div style="display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border);overflow-x:auto;-webkit-overflow-scrolling:touch">
          <button v-for="tabDef in puTabs" :key="tabDef.key" @click="tab = tabDef.key" :style="{ padding:'8px 14px', border:'none', background:'transparent', borderBottom:'2px solid '+(tab===tabDef.key?'var(--accent)':'transparent'), color:(tab===tabDef.key?'var(--text)':'var(--text-3)'), font:'inherit', fontSize:'13px', fontWeight:(tab===tabDef.key?650:500), cursor:'pointer', whiteSpace:'nowrap', flex:'none' }">{{ tabDef.label }}</button>
        </div>

        <!-- Info tab -->
        <div v-if="tab === 'info'">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px">
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.revenue') || 'Revenue' }}</div><div class="mono" style="font-size:18px;font-weight:680;margin-top:2px">${{ detailAdapter.revenue }}</div></div>
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.devices') || 'Devices' }}</div><div class="mono" style="font-size:18px;font-weight:680;margin-top:2px">{{ detailAdapter.devicesLabel }}</div></div>
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.trafficUsed') || 'Traffic' }}</div><div class="mono" style="font-size:18px;font-weight:680;margin-top:2px">{{ detailAdapter.trafficLabel }}</div></div>
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.joined') || 'Joined' }}</div><div style="font-size:14px;font-weight:600;margin-top:4px">{{ detailAdapter.joined }}</div></div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            <button @click="toggleActive" class="d2-mbtn">{{ detail.is_active ? (tr('portalUsers.deactivate') || 'Deactivate') : (tr('portalUsers.activate') || 'Activate') }}</button>
            <button @click="toggleBan" :style="{ height:'36px', padding:'0 13px', border:'1px solid var(--border-strong)', background:'var(--panel)', color: detail.is_banned ? 'var(--green)' : 'var(--red)', borderRadius:'9px', font:'inherit', fontSize:'12.5px', fontWeight:550, cursor:'pointer' }" class="d2-mbtn-plain">{{ detail.is_banned ? (tr('portalUsers.unban') || 'Unban') : (tr('portalUsers.ban') || 'Ban') }}</button>
            <button @click="openPasswordModal" class="d2-mbtn">{{ tr('portalUsers.changePassword') || 'Change password' }}</button>
            <button @click="openAddSlot" class="d2-mbtn">{{ tr('portalUsers.addSlot') || 'Add device' }}</button>
            <button @click="openMessage" class="d2-mbtn">{{ tr('portalUsers.sendMessage') || 'Send message' }}</button>
            <button @click="deleteUser" style="height:36px;padding:0 13px;border:none;background:var(--red-soft);color:var(--red);border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('portalUsers.deleteUser') || 'Delete user' }}</button>
          </div>
        </div>

        <!-- Subscription tab -->
        <div v-if="tab === 'sub'">
          <div v-if="detail.subscription" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin-bottom:16px">
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.expiryDate') || 'Expires' }}</div><div style="font-size:14px;font-weight:650;margin-top:3px">{{ detailAdapter.expiresLabel }}</div><div style="font-size:11px;color:var(--text-3);margin-top:1px">{{ detailAdapter.daysLeftLabel }}</div></div>
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.trafficUsed') || 'Traffic' }}</div><div class="mono" style="font-size:14px;font-weight:650;margin-top:3px">{{ detailAdapter.trafficLabel }}</div></div>
            <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.devices') || 'Devices' }}</div><div class="mono" style="font-size:14px;font-weight:650;margin-top:3px">{{ detailAdapter.devicesLabel }}</div></div>
          </div>
          <div v-else style="padding:18px;text-align:center;border:1px dashed var(--border-strong);border-radius:11px;margin-bottom:16px">
            <div style="font-size:13px;color:var(--text-3);margin-bottom:10px">{{ tr('portalUsers.noSubscription') || 'No active subscription' }}</div>
            <button @click="toggle('grant')" style="height:34px;padding:0 14px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2-accentbtn">{{ tr('portalUsers.grantSub') || 'Grant' }}</button>
          </div>

          <!-- Inline sub-forms -->
          <div v-if="panel === 'grant'" style="padding:14px;border:1px solid var(--border);border-radius:11px;background:var(--panel-2);margin-bottom:14px">
            <div style="font-weight:600;font-size:13px;margin-bottom:10px">{{ tr('portalUsers.grantSub') || 'Grant subscription' }}</div>
            <div class="d2-2col"><D2Select v-model="grantForm.tier" :label="tr('portalUsers.tier') || 'Tier'" :options="tiers.map(t => ({ value: t.tier, label: t.name }))" /><D2Field v-model="grantForm.duration_days" type="number" :min="1" :label="tr('portalUsers.days') || 'Days'" /></div>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px"><D2Button size="sm" :loading="actionLoading" @click="doGrant">{{ tr('common.apply') || 'Grant' }}</D2Button></div>
          </div>
          <div v-if="panel === 'extend'" style="padding:14px;border:1px solid var(--border);border-radius:11px;background:var(--panel-2);margin-bottom:14px">
            <div style="font-weight:600;font-size:13px;margin-bottom:10px">{{ tr('portalUsers.extendSub') || 'Extend' }}</div>
            <D2Field v-model="extendDays" type="number" :min="1" :max="3650" :label="tr('portalUsers.days') || 'Days to add'" />
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px"><D2Button size="sm" :loading="actionLoading" @click="doExtend">{{ tr('common.apply') || 'Extend' }}</D2Button></div>
          </div>
          <div v-if="showSetExpiry" style="padding:14px;border:1px solid var(--border);border-radius:11px;background:var(--panel-2);margin-bottom:14px">
            <div style="font-weight:600;font-size:13px;margin-bottom:10px">{{ tr('portalUsers.setExpiry') || 'Set Expiry Date' }}</div>
            <D2Field v-model="setExpiryDate" type="date" :label="tr('portalUsers.expiryDate') || 'Expiry date'" :hint="tr('portalUsers.setExpiryHint') || 'Sets the exact end date — correct a mistake or deduct days.'" />
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">
              <D2Button size="sm" variant="secondary" @click="showSetExpiry = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
              <D2Button size="sm" :loading="actionLoading" :disabled="!setExpiryDate" @click="doSetExpiry">{{ tr('common.save') || 'Save' }}</D2Button>
            </div>
          </div>

          <div style="display:flex;flex-wrap:wrap;gap:8px">
            <button @click="toggle('grant')" style="height:36px;padding:0 13px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer" class="d2-accentbtn">{{ tr('portalUsers.grantSub') || 'Grant' }}</button>
            <button @click="toggle('extend')" :disabled="!detail.subscription" class="d2-mbtn">{{ tr('portalUsers.extendSub') || 'Extend' }}</button>
            <button @click="openSetExpiry" :disabled="!detail.subscription" class="d2-mbtn">{{ tr('portalUsers.setExpiry') || 'Set Expiry Date' }}</button>
            <button @click="resetTraffic" class="d2-mbtn">{{ tr('portalUsers.resetTraffic') || 'Reset traffic' }}</button>
            <button v-if="detail.subscription" @click="cancelSub" style="height:36px;padding:0 13px;border:none;background:var(--red-soft);color:var(--red);border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('portalUsers.cancelSub') || 'Cancel sub' }}</button>
          </div>
        </div>

        <!-- Devices tab -->
        <div v-if="tab === 'dev'">
          <div v-if="!(detail.devices && detail.devices.length)" style="padding:24px;text-align:center;font-size:13px;color:var(--text-3)">{{ tr('portalUsers.noDevices') || 'No devices' }}</div>
          <div v-else style="display:flex;flex-direction:column;gap:1px">
            <div v-for="d in detailDevices" :key="d.id" style="display:flex;align-items:center;gap:10px;padding:11px 4px;border-bottom:1px solid var(--border)">
              <span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:d.dot, flex:'none' }"></span>
              <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:550">{{ d.name }}</div><div class="mono" style="font-size:11.5px;color:var(--text-3)">{{ d.server }}<template v-if="d.ip"> · {{ d.ip }}</template></div></div>
              <span :style="{ fontSize:'10px', fontWeight:700, letterSpacing:'.04em', padding:'2px 7px', borderRadius:'6px', color:d.enabledColor, background:d.enabledBg, flex:'none' }">{{ d.enabledLabel }}</span>
              <div style="text-align:right"><div class="mono" style="font-size:12px;color:var(--text-2)">{{ d.trafficLabel }}</div><div v-if="d.bwLabel" style="font-size:11px;color:var(--text-3)">{{ d.bwLabel }}</div></div>
            </div>
          </div>
        </div>

        <!-- Payments tab -->
        <div v-if="tab === 'pay'">
          <div v-if="detail.balance" style="padding:14px;border:1px solid var(--border);border-radius:11px;background:var(--panel-2);margin-bottom:14px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
              <div>
                <div style="font-size:11px;color:var(--text-3)">{{ tr('portalUsers.accountBalance') || 'Account balance' }}</div>
                <div class="mono" style="font-size:22px;font-weight:680;margin-top:3px">${{ Number(detail.balance.available || 0).toFixed(2) }}</div>
              </div>
              <button class="d2-mbtn" @click="showBalanceAdjustment = !showBalanceAdjustment">
                {{ tr('portalUsers.adjustBalance') || 'Adjust balance' }}
              </button>
            </div>
            <div v-if="showBalanceAdjustment" class="d2-balance-adjust">
              <D2Field v-model="balanceAdjustment.amount_usd" type="number" step="0.01" :label="tr('portalUsers.adjustmentAmount') || 'Amount, USD'" :hint="tr('portalUsers.adjustmentAmountHint') || 'Use a negative value to deduct credit'" />
              <D2Field v-model="balanceAdjustment.reason" :label="tr('portalUsers.adjustmentReason') || 'Reason'" />
              <D2Button size="sm" :loading="balanceAdjustBusy" :disabled="!balanceAdjustmentValid" @click="submitBalanceAdjustment">{{ tr('common.apply') || 'Apply' }}</D2Button>
            </div>
          </div>
          <div v-if="!(detail.payments && detail.payments.length)" style="padding:24px;text-align:center;font-size:13px;color:var(--text-3)">{{ tr('portalUsers.noPayments') || 'No payments' }}</div>
          <div v-else style="overflow-x:auto"><table data-rtab style="width:100%;border-collapse:collapse;font-size:12.5px">
            <thead><tr style="text-align:left">
              <th class="d2-th2">{{ tr('payments.date') || 'Date' }}</th><th class="d2-th2">{{ tr('payments.amount') || 'Amount' }}</th><th class="d2-th2">{{ tr('portalUsers.tier') || 'Tier' }}</th><th class="d2-th2">{{ tr('payments.method') || 'Method' }}</th><th class="d2-th2">{{ tr('payments.status') || 'Status' }}</th><th class="d2-th2" style="text-align:right"></th>
            </tr></thead>
            <tbody>
              <tr v-for="p in detailPayments" :key="p.id" style="border-top:1px solid var(--border)">
                <td data-mhead class="mono" style="padding:9px 6px;color:var(--text-3)">{{ p.date }}</td>
                <td :data-label="tr('payments.amount') || 'Amount'" class="mono" style="padding:9px 6px;font-weight:600">{{ p.amountLabel }}</td>
                <td :data-label="tr('portalUsers.tier') || 'Tier'" style="padding:9px 6px;font-size:11px;color:var(--text-2)">{{ p.tier }}</td>
                <td :data-label="tr('payments.method') || 'Method'" style="padding:9px 6px;color:var(--text-2)">{{ p.method }}</td>
                <td :data-label="tr('payments.status') || 'Status'" style="padding:9px 6px"><span :style="{ display:'inline-flex', alignItems:'center', gap:'5px', fontSize:'11.5px', fontWeight:550, color:p.statusColor }">{{ p.statusLabel }}</span></td>
                <td data-mfull style="padding:9px 6px"><div style="display:flex;gap:3px;justify-content:flex-end">
                  <template v-if="p.isPending">
                    <button @click="confirmPay(p.id)" style="width:26px;height:26px;border-radius:6px;border:none;background:var(--green-soft);color:var(--green);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l4 4L19 7"></path></svg></button>
                    <button @click="rejectPay(p.id)" style="width:26px;height:26px;border-radius:6px;border:none;background:var(--red-soft);color:var(--red);cursor:pointer;display:flex;align-items:center;justify-content:center"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>
                  </template>
                  <button @click="deletePay(p.id)" class="d2-del2"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button>
                </div></td>
              </tr>
            </tbody>
          </table></div>
        </div>
      </div>
    </D2Modal>

    <!-- ===== CREATE ACCOUNT MODAL ===== -->
    <D2Modal :open="showCreate" size="md" @close="showCreate = false">
      <template #header><div style="font-weight:650;font-size:17px">{{ tr('portalUsers.createAccount') || 'Create account' }}</div></template>
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="d2-2col">
          <D2Field v-model="createForm.email" type="email" :label="tr('portalUsers.email') || 'Email'" placeholder="erza@example.com" />
          <D2Field v-model="createForm.username" :label="'@username'" placeholder="@erza" />
        </div>
        <D2Field v-model="createForm.full_name" :label="tr('portalUsers.fullName') || 'Full name'" placeholder="Erza Scarlet" />
        <D2Field v-model="createForm.password" type="password" :label="tr('portalUsers.password') || 'Password'" placeholder="••••••••" />
        <div class="d2-2col">
          <D2Select v-model="createForm.tier" :label="tr('portalUsers.tier') || 'Tier'" :options="tiers.map(t => ({ value: t.tier, label: t.name || t.tier }))" />
          <D2Field v-model="createForm.duration_days" type="number" :min="1" :label="tr('portalUsers.durationDays') || 'Duration (days)'" />
        </div>
      </div>
      <template #footer>
        <D2Button variant="secondary" @click="showCreate = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button :loading="createBusy" @click="submitCreate">{{ tr('portalUsers.createAccount') || 'Create account' }}</D2Button>
      </template>
    </D2Modal>

    <!-- ===== CHANGE PASSWORD MODAL ===== -->
    <D2Modal :open="showPassword" size="sm" @close="closePasswordModal">
      <template #header><div style="font-weight:650;font-size:17px">{{ tr('portalUsers.changePassword') || 'Change password' }}</div></template>
      <div v-if="passwordSuccess" style="padding:12px 14px;border:1px solid var(--green);border-radius:10px;background:var(--green-soft);color:var(--green);font-size:13px;font-weight:550">
        {{ passwordSuccess }}
      </div>
      <div v-else style="display:flex;flex-direction:column;gap:14px">
        <div style="font-size:12.5px;color:var(--text-3)">
          {{ passwordTarget }}
        </div>
        <D2Field
          v-model="passwordForm.new_password"
          type="password"
          autocomplete="new-password"
          :minlength="8"
          :maxlength="72"
          :label="tr('portalUsers.newPassword') || 'New password'"
          :hint="tr('portalUsers.passwordHint') || 'At least 8 characters and no more than 72 UTF-8 bytes.'"
          :error="newPasswordError"
          placeholder="••••••••"
        />
        <D2Field
          v-model="passwordForm.confirm_password"
          type="password"
          autocomplete="new-password"
          :minlength="8"
          :maxlength="72"
          :label="tr('portalUsers.confirmPassword') || 'Confirm password'"
          :error="confirmPasswordError"
          placeholder="••••••••"
        />
        <div style="font-size:12px;color:var(--text-3)">
          {{ tr('portalUsers.passwordNotice') || 'The customer is not notified automatically, and existing sessions stay signed in. Share the new password through a secure channel.' }}
        </div>
        <div v-if="passwordApiError" style="font-size:12px;color:var(--red)">{{ passwordApiError }}</div>
      </div>
      <template #footer>
        <D2Button variant="secondary" @click="closePasswordModal">{{ passwordSuccess ? (tr('common.close') || 'Close') : (tr('common.cancel') || 'Cancel') }}</D2Button>
        <D2Button v-if="!passwordSuccess" :loading="passwordBusy" :disabled="!passwordFormValid" @click="submitPassword">
          {{ tr('portalUsers.setPassword') || 'Set password' }}
        </D2Button>
      </template>
    </D2Modal>

    <!-- ===== SEND MESSAGE MODAL ===== -->
    <D2Modal :open="showMessage" size="md" @close="showMessage = false">
      <template #header><div style="font-weight:650;font-size:16px">{{ tr('portalUsers.sendMessage') || 'Send message' }}</div></template>
      <div style="font-size:12.5px;color:var(--text-3);margin-bottom:14px">{{ messageTarget }}</div>
      <textarea v-model="messageValue" :placeholder="tr('portalUsers.messagePh') || 'Type your message…'" style="width:100%;min-height:96px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;font-size:13px;outline:none"></textarea>
      <template #footer>
        <D2Button variant="secondary" @click="showMessage = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button :loading="messageBusy" :disabled="!messageValue.trim()" @click="submitMessage">{{ tr('portalUsers.send') || 'Send' }}</D2Button>
      </template>
    </D2Modal>

    <!-- ===== ADD DEVICE SLOT MODAL ===== -->
    <D2Modal :open="showAddSlot" size="md" @close="showAddSlot = false">
      <template #header><div style="font-weight:650;font-size:17px">{{ tr('portalUsers.addSlot') || 'Add device slot' }}</div></template>
      <div style="display:flex;flex-direction:column;gap:14px">
        <D2Field v-model="slotLabel" :label="tr('portalUsers.slotLabel') || 'Device label'" placeholder="iPhone 15 Pro" />
      </div>
      <template #footer>
        <D2Button variant="secondary" @click="showAddSlot = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button>
        <D2Button :loading="actionLoading" :disabled="!slotLabel.trim()" @click="submitAddSlot">{{ tr('portalUsers.add') || 'Add' }}</D2Button>
      </template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { portalUsersApi } from '../../api'
import { formatBytes, formatDate } from '../../utils'
import { useD2Ui } from '../../stores/d2ui'
import D2Modal from '../ui/D2Modal.vue'
import D2Button from '../ui/D2Button.vue'
import D2Field from '../ui/D2Field.vue'
import D2Select from '../ui/D2Select.vue'

const { t } = useI18n()
function tr(k, p) { try { const v = t(k, p || {}); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()

const users = ref([])
const total = ref(0)
const tiers = ref([])
const search = ref('')
const filterTier = ref('')
const filterStatus = ref('')
const offset = ref(0)
const limit = 25
const loading = ref(false)

const puTierOptions = computed(() => tiers.value.map(t => t.tier))

async function loadUsers() {
  loading.value = true
  try {
    const params = { limit, offset: offset.value }
    if (search.value) params.search = search.value
    if (filterTier.value) params.tier = filterTier.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await portalUsersApi.list(params)
    users.value = res.data.items; total.value = res.data.total
  } catch (e) { console.error(e) } finally { loading.value = false }
}
function reload() { offset.value = 0; loadUsers() }

// ── CSV export (built from loaded data; no dedicated endpoint) ──
function csvCell(v) { const s = String(v ?? ''); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s }
function downloadCsv(name, rowsArr) {
  const csv = rowsArr.map(r => r.map(csvCell).join(',')).join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
function exportUsersCsv() {
  const head = ['id', 'username', 'email', 'tier', 'devices', 'last_login', 'status']
  const body = users.value.map(u => [u.id, u.username || '', u.email || '', u.tier || 'free', u.devices_count ?? 0, u.last_login || '', u.is_banned ? 'banned' : (u.is_active ? 'active' : 'inactive')])
  downloadCsv('portal-users.csv', [head, ...body])
}
async function exportPaymentsCsv() {
  if (!portalUsersApi.getPayments) return
  try {
    const res = await portalUsersApi.getPayments({ limit: 1000 })
    const items = res.data?.items || res.data || []
    const head = ['id', 'date', 'amount', 'currency', 'tier', 'method', 'status', 'user']
    const body = items.map(p => [p.id, p.created_at || p.date || '', p.amount_usd ?? p.amount ?? '', (p.currency || 'USD'), p.tier || p.plan || '', p.payment_method || p.method || '', p.status || '', p.username || p.user_id || ''])
    downloadCsv('portal-payments.csv', [head, ...body])
  } catch (e) { alert(e.response?.data?.detail || 'Error') }
}
async function loadTiers() { try { const res = await portalUsersApi.getTiers(); tiers.value = res.data || [] } catch (_) { tiers.value = [] } }

// ── detail ──
const showDetail = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const tab = ref('info')
const panel = ref('')
const actionLoading = ref(false)
const grantForm = ref({ tier: 'basic', duration_days: 30 })
const extendDays = ref(30)
const showSetExpiry = ref(false)
const setExpiryDate = ref('')
const showBalanceAdjustment = ref(false)
const balanceAdjustBusy = ref(false)
const balanceAdjustment = ref({ amount_usd: '', reason: '' })
const balanceAdjustmentValid = computed(() => {
  const amount = Number(balanceAdjustment.value.amount_usd)
  return Number.isFinite(amount) && amount !== 0 && balanceAdjustment.value.reason.trim().length >= 3
})
async function submitBalanceAdjustment() {
  if (!detail.value || !balanceAdjustmentValid.value) return
  balanceAdjustBusy.value = true
  try {
    const requestId = (globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`).replace(/-/g, '_')
    const res = await portalUsersApi.adjustBalance(detail.value.id, {
      amount_usd: Number(balanceAdjustment.value.amount_usd),
      reason: balanceAdjustment.value.reason.trim(),
      request_id: requestId,
    })
    detail.value.balance = res.data
    balanceAdjustment.value = { amount_usd: '', reason: '' }
    showBalanceAdjustment.value = false
  } catch (e) {
    alert(e.response?.data?.detail || 'Could not adjust account balance')
  } finally {
    balanceAdjustBusy.value = false
  }
}

// admin password reset modal
const showPassword = ref(false)
const passwordBusy = ref(false)
const passwordSubmitted = ref(false)
const passwordSuccess = ref('')
const passwordApiError = ref('')
const passwordForm = ref({ new_password: '', confirm_password: '' })
const passwordTarget = computed(() => detailAdapter.value.name + ' · ' + detailAdapter.value.username)
function passwordByteLength(value) { return new TextEncoder().encode(value || '').length }
const newPasswordError = computed(() => {
  const password = passwordForm.value.new_password
  if (!password && passwordSubmitted.value) return tr('portalUsers.passwordRequired') || 'Enter a new password.'
  if (password && password.length < 8) return tr('portalUsers.passwordTooShort') || 'Password must be at least 8 characters.'
  if (password && passwordByteLength(password) > 72) return tr('portalUsers.passwordTooLong') || 'Password must not exceed 72 UTF-8 bytes.'
  return ''
})
const confirmPasswordError = computed(() => {
  const confirmation = passwordForm.value.confirm_password
  if (!confirmation && passwordSubmitted.value) return tr('portalUsers.confirmPasswordRequired') || 'Confirm the new password.'
  if (confirmation && confirmation !== passwordForm.value.new_password) return tr('portalUsers.passwordsDoNotMatch') || 'Passwords do not match.'
  return ''
})
const passwordFormValid = computed(() => {
  const password = passwordForm.value.new_password
  return password.length >= 8
    && passwordByteLength(password) <= 72
    && passwordForm.value.confirm_password === password
})
function openPasswordModal() {
  passwordForm.value = { new_password: '', confirm_password: '' }
  passwordSubmitted.value = false
  passwordSuccess.value = ''
  passwordApiError.value = ''
  showPassword.value = true
}
function closePasswordModal() {
  showPassword.value = false
  passwordForm.value = { new_password: '', confirm_password: '' }
  passwordSubmitted.value = false
  passwordSuccess.value = ''
  passwordApiError.value = ''
}
function passwordErrorMessage(error) {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || String(item)).join(' ')
  return typeof detail === 'string' ? detail : (tr('portalUsers.passwordUpdateFailed') || 'Could not update the password.')
}
async function submitPassword() {
  passwordSubmitted.value = true
  passwordApiError.value = ''
  if (!passwordFormValid.value || !detail.value) return
  passwordBusy.value = true
  try {
    await portalUsersApi.setPassword(detail.value.id, { new_password: passwordForm.value.new_password })
    passwordForm.value = { new_password: '', confirm_password: '' }
    passwordSubmitted.value = false
    passwordSuccess.value = tr('portalUsers.passwordUpdated') || 'Password updated successfully.'
  } catch (error) {
    passwordApiError.value = passwordErrorMessage(error)
  } finally {
    passwordBusy.value = false
  }
}

// create-account modal
const showCreate = ref(false)
const createBusy = ref(false)
const createForm = ref({ email: '', username: '', full_name: '', password: '', tier: 'free', duration_days: 30 })
function openCreate() {
  createForm.value = { email: '', username: '', full_name: '', password: '', tier: (tiers.value[0]?.tier) || 'free', duration_days: 30 }
  showCreate.value = true
}
async function submitCreate() {
  if (!portalUsersApi.createAccount) return
  createBusy.value = true
  try {
    const f = createForm.value
    const payload = { email: f.email, username: f.username, full_name: f.full_name, password: f.password, tier: f.tier, duration_days: Number(f.duration_days) || 0 }
    await portalUsersApi.createAccount(payload)
    showCreate.value = false
    await loadUsers()
  } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { createBusy.value = false }
}

// send-message modal (per-user, from detail)
const showMessage = ref(false)
const messageBusy = ref(false)
const messageValue = ref('')
const messageTarget = computed(() => detailAdapter.value.name + ' · ' + detailAdapter.value.username)
function openMessage() { messageValue.value = ''; showMessage.value = true }
async function submitMessage() {
  const msg = messageValue.value.trim()
  if (!msg || !detail.value || !portalUsersApi.sendMessage) return
  messageBusy.value = true
  try { await portalUsersApi.sendMessage(detail.value.id, { message: msg }); showMessage.value = false }
  catch (e) { alert(e.response?.data?.detail || 'Error') } finally { messageBusy.value = false }
}

// add-device-slot modal (replaces prompt())
const showAddSlot = ref(false)
const slotLabel = ref('')
function openAddSlot() { slotLabel.value = tr('portalUsers.addSlotDefaultLabel') || 'Device'; showAddSlot.value = true }
async function submitAddSlot() {
  const label = slotLabel.value.trim()
  if (!label) return
  await act(() => portalUsersApi.addDeviceSlot(detail.value.id, { label }), () => showAddSlot.value = false)
}

// broadcast side-panel state (his markup)
const broadcastTier = ref('all')
const broadcastPlatform = ref('all')
const broadcastMsg = ref('')
const broadcastActive = ref(false)
const broadcastBusy = ref(false)
const broadcastResult = ref('')
async function sendBroadcast() {
  const msg = broadcastMsg.value.trim()
  if (!msg) return
  broadcastBusy.value = true; broadcastResult.value = ''
  try {
    const { data } = await portalUsersApi.broadcast({
      message: msg,
      tier: broadcastTier.value,          // "all" → every tier (backend normalizes)
      platform: broadcastPlatform.value,  // "all" | "android" | "ios"
      only_active: broadcastActive.value, // matches the "Active users only" toggle
    })
    broadcastMsg.value = ''
    const n = data?.recipients ?? data?.inapp ?? 0
    broadcastResult.value = (tr('portalUsers.broadcastSent') || 'Sent to {n} user(s)').replace('{n}', n)
  } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { broadcastBusy.value = false }
}

async function openDetail(id) {
  showDetail.value = true; detailLoading.value = true; panel.value = ''; showSetExpiry.value = false; tab.value = 'info'
  try { const res = await portalUsersApi.get(id); detail.value = res.data } catch (e) { alert(e.response?.data?.detail || 'Error') } finally { detailLoading.value = false }
}
function toggle(p) { panel.value = panel.value === p ? '' : p; showSetExpiry.value = false }
function openSetExpiry() { panel.value = ''; const cur = detail.value?.subscription?.expiry_date; setExpiryDate.value = cur ? String(cur).slice(0, 10) : ''; showSetExpiry.value = true }

async function doGrant() { await act(() => portalUsersApi.grantSubscription(detail.value.id, grantForm.value), () => panel.value = '') }
async function doExtend() { await act(() => portalUsersApi.extendSubscription(detail.value.id, { days: extendDays.value }), () => panel.value = '') }
async function doSetExpiry() { if (!setExpiryDate.value) return; await act(() => portalUsersApi.setSubscriptionExpiry(detail.value.id, { expiry_date: setExpiryDate.value }), () => showSetExpiry.value = false) }
async function cancelSub() { if (!await d2confirm(tr('portalUsers.cancelSubConfirm') || 'Cancel this subscription?')) return; await act(() => portalUsersApi.cancelSubscription(detail.value.id)) }
async function resetTraffic() { if (!await d2confirm(tr('portalUsers.resetTrafficConfirm') || 'Reset traffic counters?')) return; await act(() => portalUsersApi.resetTraffic(detail.value.id), null, false) }
async function toggleActive() { await act(() => portalUsersApi.update(detail.value.id, { is_active: !detail.value.is_active })) }
async function toggleBan() {
  const willBan = !detail.value.is_banned
  if (willBan && !await d2confirm(tr('portalUsers.banConfirm') || 'Ban this user?')) return
  await act(() => portalUsersApi.update(detail.value.id, { is_banned: willBan }))
}
async function deleteUser() {
  if (!await d2confirm((tr('portalUsers.deleteUserConfirm') || 'Delete user "{name}" permanently?').replace('{name}', detail.value.username))) return
  actionLoading.value = true
  try { await portalUsersApi.deleteUser(detail.value.id); showDetail.value = false; detail.value = null; await loadUsers() }
  catch (e) { alert(e.response?.data?.detail || 'Error') } finally { actionLoading.value = false }
}
async function confirmPay(id) { if (!await d2confirm(tr('portalUsers.confirmPaymentConfirm') || 'Confirm this payment?')) return; await act(() => portalUsersApi.confirmPayment(id)) }
async function rejectPay(id) { if (!await d2confirm(tr('portalUsers.rejectPaymentConfirm') || 'Reject this payment?')) return; await act(() => portalUsersApi.rejectPayment(id)) }
async function deletePay(id) { if (!await d2confirm(tr('portalUsers.deletePaymentConfirm') || 'Delete this payment?')) return; await act(() => portalUsersApi.deletePayment(id)) }

// shared action runner: run fn, refresh detail (+ optional list), run after()
async function act(fn, after, refreshList = true) {
  actionLoading.value = true
  try { await fn(); if (after) after(); await openDetail(detail.value.id); if (refreshList) await loadUsers() }
  catch (e) { alert(e.response?.data?.detail || 'Error') } finally { actionLoading.value = false }
}

// ── helpers ──
function fmtDate(d) { try { return formatDate(d) } catch (_) { return new Date(d).toLocaleDateString() } }
function fmtBytes(b) { return formatBytes(b) }
function trafficPct(s) { if (!s.traffic_limit_gb) return 0; return Math.min(100, ((s.traffic_used_gb ?? 0) / s.traffic_limit_gb) * 100) }
function tierTone(t) { return ({ basic: 'blue', premium: 'accent', ultimate: 'amber', free: 'gray' })[String(t || '').toLowerCase()] || 'gray' }
function payTone(s) { return ({ confirmed: 'green', completed: 'green', pending: 'amber', rejected: 'red', failed: 'red' })[String(s || '').toLowerCase()] || 'gray' }

// ── adapters: map our payload → his field names ──
const TC = { free: ['var(--text-3)', 'var(--gray-soft)'], starter: ['var(--blue)', 'var(--blue-soft)'], basic: ['var(--blue)', 'var(--blue-soft)'], pro: ['var(--accent)', 'var(--accent-soft)'], premium: ['var(--accent)', 'var(--accent-soft)'], business: ['var(--purple)', 'var(--purple-soft)'], ultimate: ['var(--amber)', 'var(--amber-soft)'] }
function tierColorOf(t) { return (TC[String(t || '').toLowerCase()] || TC.free)[0] }
function tierBgOf(t) { return (TC[String(t || '').toLowerCase()] || TC.free)[1] }
function initialsOf(name) { const s = String(name || '').trim(); if (!s) return '?'; const parts = s.split(/[\s_@.]+/).filter(Boolean); return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || s[0].toUpperCase() }
const SC = { completed: 'var(--green)', confirmed: 'var(--green)', pending: 'var(--amber)', rejected: 'var(--red)', failed: 'var(--red)' }
function payStatusLabel(s) { const k = String(s || '').toLowerCase(); return tr('payments.status_' + k) || (k.charAt(0).toUpperCase() + k.slice(1)) }
function money(p) { const c = (p.currency || 'USD').toUpperCase(); const a = p.amount_usd ?? p.amount ?? 0; return c === 'USD' ? '$' + Number(a).toFixed(2) : Number(a).toFixed(2) + ' ' + c }

const rows = computed(() => users.value.map(u => {
  const banned = !!u.is_banned
  const statusColor = banned ? 'var(--red)' : (u.is_active ? 'var(--green)' : 'var(--text-3)')
  const statusLabel = banned ? (tr('portalUsers.banned') || 'Banned') : (u.is_active ? (tr('portalUsers.active') || 'Active') : (tr('portalUsers.inactive') || 'Inactive'))
  return {
    id: u.id,
    initials: initialsOf(u.username || u.email),
    name: u.username || ('user #' + u.id),
    username: u.username ? ('@' + u.username) : ('#' + u.id),
    email: u.email || '—',
    tier: u.tier || 'free',
    tierColor: tierColorOf(u.tier),
    tierBg: tierBgOf(u.tier),
    devicesLabel: String(u.devices_count ?? 0),
    lastLogin: u.last_login ? fmtDate(u.last_login) : (tr('portalUsers.never') || 'Never'),
    statusColor, statusLabel,
    onOpen: () => openDetail(u.id),
  }
}))

const detailAdapter = computed(() => {
  const d = detail.value || {}
  const sub = d.subscription
  return {
    initials: initialsOf(d.username || d.email),
    name: d.username || ('user #' + (d.id ?? '?')),
    username: d.username ? ('@' + d.username) : ('#' + (d.id ?? '?')),
    tg: d.telegram_id || d.tg || '',
    tier: sub?.tier || d.tier || 'free',
    revenue: Number(d.total_revenue_usd ?? d.revenue ?? 0).toFixed(2),
    devicesLabel: String(d.devices_count ?? (d.devices?.length ?? 0)),
    trafficLabel: fmtBytes(((sub?.traffic_used_gb ?? 0) * 1024 * 1024 * 1024) || d.traffic_used_bytes || 0),
    joined: d.created_at ? fmtDate(d.created_at) : '—',
    expiresLabel: sub?.expiry_date ? fmtDate(sub.expiry_date) : (tr('portalUsers.never') || 'Never'),
    daysLeftLabel: daysLeftOf(sub?.expiry_date),
  }
})

function daysLeftOf(exp) {
  if (!exp) return sub_tier_fallback()
  const ms = new Date(exp).getTime() - Date.now()
  if (isNaN(ms)) return ''
  const days = Math.ceil(ms / 86400000)
  if (days < 0) return tr('portalUsers.expired') || 'Expired'
  return (tr('portalUsers.daysLeft') || '{n} days left').replace('{n}', String(days))
}
function sub_tier_fallback() { return detail.value?.subscription?.tier || '' }

const puTabs = computed(() => [
  { key: 'info', label: tr('portalUsers.tabInfo') || 'Info' },
  { key: 'sub', label: tr('portalUsers.subscription') || 'Subscription' },
  { key: 'dev', label: tr('portalUsers.devices') || 'Devices' },
  { key: 'pay', label: tr('portalUsers.payments') || 'Payments' },
])

const detailDevices = computed(() => (detail.value?.devices || []).map(d => {
  const enabled = d.is_enabled !== false
  return {
    id: d.id,
    dot: enabled ? 'var(--green)' : 'var(--text-3)',
    name: d.label || d.name || ('Slot ' + d.id),
    server: d.server_name || d.server || '',
    ip: d.assigned_ip || d.ip || '',
    trafficLabel: fmtBytes((d.traffic_rx || 0) + (d.traffic_tx || 0)),
    bwLabel: d.bandwidth_limit_mbps ? (d.bandwidth_limit_mbps + ' Mbps') : '',
    enabledColor: enabled ? 'var(--green)' : 'var(--text-3)',
    enabledBg: enabled ? 'var(--green-soft)' : 'var(--panel-3)',
    enabledLabel: enabled ? (tr('portalUsers.devEnabled') || 'ON') : (tr('portalUsers.devDisabled') || 'OFF'),
  }
}))

const detailPayments = computed(() => (detail.value?.payments || []).map(p => {
  const st = String(p.status || '').toLowerCase()
  return {
    id: p.id,
    date: fmtDate(p.created_at || p.date),
    amountLabel: money(p),
    tier: p.tier || p.plan || p.tariff_name || '',
    method: p.payment_method || p.method || '—',
    statusColor: SC[st] || 'var(--text-3)',
    statusLabel: payStatusLabel(st),
    isPending: st === 'pending',
  }
}))

onMounted(() => {
  ui.set({
    title: tr('nav.portal') || 'Portal users',
    search: true,
    searchPh: tr('portalUsers.search') || 'Search users…',
    onSearch: v => { search.value = v; reload() },
  })
  loadTiers()
  loadUsers()
})
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-th2 { padding: 8px 6px; font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-row:hover { background: var(--panel-2); }
.d2-tbbtn { height: 34px; padding: 0 12px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 9px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.d2-tbbtn:hover:not(:disabled) { background: var(--panel-2); }
.d2-tbbtn:disabled { opacity: .5; cursor: default; }
.d2-mbtn { height: 36px; padding: 0 13px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); border-radius: 9px; font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; }
.d2-mbtn:hover:not(:disabled) { background: var(--panel-2); }
.d2-mbtn:disabled { opacity: .5; cursor: default; }
.d2-mbtn-plain:hover { background: var(--panel-2); }
.d2-accentbtn:hover { background: var(--accent-2); }
.d2-del2 { width: 26px; height: 26px; border-radius: 6px; border: none; background: transparent; color: var(--text-3); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-del2:hover { background: var(--red-soft); color: var(--red); }
.d2-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.d2-portal-mobile-user { width:100%;display:flex;align-items:center;gap:10px;color:var(--text);font:inherit;cursor:pointer; }
.d2-balance-adjust { display:grid;grid-template-columns:minmax(120px,.45fr) minmax(180px,1fr) auto;gap:10px;align-items:end;margin-top:14px; }
@media (max-width:900px) {
  .d2-portal-toolbar { display:grid !important;grid-template-columns:1fr 1fr; }
  .d2-portal-toolbar > select { width:100%; }
  .d2-portal-toolbar > div { grid-column:1 / -1;margin-left:0 !important;display:grid !important;grid-template-columns:repeat(2,minmax(0,1fr)); }
  .d2-portal-toolbar > div > button { width:100%;justify-content:center; }
  .d2-balance-adjust { grid-template-columns:1fr; }
  .d2-balance-adjust :deep(button) { width:100%;justify-content:center; }
}
@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
