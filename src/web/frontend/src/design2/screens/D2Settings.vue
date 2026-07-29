<!-- New-design Settings — his exact 1:1 handoff (left tab-rail + per-section cards).
     Sections: License, Payments (per-provider tabs), SMTP, Telegram notifications,
     Apps & FCM, Limits, Web access, System tools, Branding (identity + 3 logo slots
     + live preview), Interface/Design (theme + New/Legacy design toggle).
     Design-mode toggle drives the real useDesignMode store. All save/load handlers
     reuse the same systemApi methods the Legacy Settings.vue uses. -->
<template>
  <div class="d2-root-inner">
    <div :style="{ display:'grid', gridTemplateColumns:'220px 1fr', gap:'18px', alignItems:'start' }">
      <!-- LEFT TAB RAIL -->
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:7px;position:sticky;top:84px">
        <button v-for="st in settingsTabs" :key="st.key" @click="st.on"
          :style="{ display:'flex', alignItems:'center', gap:'10px', width:'100%', padding:'9px 11px', border:'none', borderRadius:'9px', background:st.bg, color:st.color, font:'inherit', fontSize:'13px', fontWeight:st.weight, cursor:'pointer', textAlign:'left' }">
          <span style="display:flex;flex:none" v-html="st.icon"></span>{{ st.label }}
        </button>
      </div>

      <div style="min-width:0;display:flex;flex-direction:column;gap:16px">

        <!-- ================= LICENSE ================= -->
        <template v-if="isSetLicense">
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
            <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('settings.license') || 'License' }}</div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:16px">
              <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.licenseTier') || 'Tier' }}</div><div style="font-size:16px;font-weight:680;margin-top:3px">{{ licTier }}</div></div>
              <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.maxClients') || 'Max clients' }}</div><div style="font-size:16px;font-weight:680;font-family:'JetBrains Mono',monospace;margin-top:3px">{{ licMaxClients }}</div></div>
              <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.maxServers') || 'Max servers' }}</div><div style="font-size:16px;font-weight:680;font-family:'JetBrains Mono',monospace;margin-top:3px">{{ licMaxServers }}</div></div>
              <div style="padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.expires') || 'Days left' }}</div><div style="font-size:16px;font-weight:680;font-family:'JetBrains Mono',monospace;margin-top:3px;color:var(--green)">{{ licDays }}</div></div>
            </div>
            <div v-if="licFeatures.length" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px">
              <span v-for="f in licFeatures" :key="f" style="font-size:11px;font-weight:600;padding:3px 9px;border-radius:7px;color:var(--accent);background:var(--accent-soft)">{{ f }}</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px">
              <div><div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:4px"><span style="color:var(--text-3)">{{ tr('settings.clients') || 'Clients' }}</span><span style="font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ licClientsUsed }} / {{ licMaxClients }}</span></div><div style="height:6px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:licClientsPct }"></div></div></div>
              <div><div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:4px"><span style="color:var(--text-3)">{{ tr('settings.servers') || 'Servers' }}</span><span style="font-family:'JetBrains Mono',monospace;color:var(--text-2)">{{ licServersUsed }} / {{ licMaxServers }}</span></div><div style="height:6px;border-radius:4px;background:var(--panel-3);overflow:hidden"><div :style="{ height:'100%', borderRadius:'4px', background:'var(--accent)', width:licServersPct }"></div></div></div>
            </div>
            <div style="display:flex;gap:8px;align-items:flex-end;margin-bottom:14px">
              <div style="flex:1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.activateNewKey') || 'Activate license key' }}</label>
                <input :value="license.newKey" @input="license.newKey = $event.target.value" :placeholder="tr('settings.keyPlaceholder') || 'Paste license key…'" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
              <button @click="activateLicense2" :disabled="!license.newKey || busy.lic" style="height:40px;padding:0 16px;border:none;background:var(--accent);color:#fff;border-radius:10px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;flex:none">{{ tr('settings.activate') || 'Activate' }}</button>
            </div>
            <div v-if="msg.lic" :style="{ fontSize:'12.5px', marginBottom:'12px', color: msgLicTone==='ok' ? 'var(--green)' : 'var(--red)' }">{{ msg.lic }}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:14px">
              <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.serverId') || 'Server ID' }}</div><div style="display:flex;align-items:center;gap:8px;margin-top:3px"><span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2)">{{ license.server_id || '—' }}</span><button @click="copyServerId" style="border:none;background:transparent;color:var(--text-3);cursor:pointer;display:flex"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button></div></div>
              <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.licenseOwner') || 'Owner' }}</div><div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2);margin-top:3px">{{ license.owner || '—' }}</div></div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:8px">
              <button @click="refetchLicense" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.refetch') || 'Re-fetch' }}</button>
              <button @click="openMigration" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.migrationCode') || 'Migration' }}</button>
              <button @click="refreshLicenseCheck" style="height:36px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.refreshNow') || 'Refresh' }}</button>
            </div>
          </div>

          <!-- License server status -->
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
              <div style="font-weight:650;font-size:15px;flex:1">{{ tr('settings.licenseServer') || 'License server' }}</div>
              <span :style="{ display:'inline-flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:600, color:licSrvColor }"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:licSrvColor }"></span>{{ licSrvLabel }}</span>
              <button @click="refreshLicenseCheck" style="height:32px;padding:0 12px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">{{ tr('settings.refreshNow') || 'Refresh' }}</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:11px">
              <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.primaryServer') || 'Primary' }}</div><div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-2);margin-top:3px;word-break:break-all">{{ licServer.primary_url || '—' }}</div></div>
              <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.backupServer') || 'Backup' }}</div><div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-2);margin-top:3px;word-break:break-all">{{ licServer.backup_url || '—' }}</div></div>
            </div>
            <div style="font-size:12px;color:var(--text-3);margin-top:11px">{{ tr('settings.lastCheck') || 'Last check' }}: {{ licLastCheck }}</div>
          </div>
        </template>

        <!-- ================= PAYMENT PROVIDERS ================= -->
        <div v-if="isSetPayments" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:14px">{{ tr('settings.paymentProviders') || 'Payment providers' }}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px">
            <button v-for="p in payTabs" :key="p.key" @click="p.on"
              :style="{ display:'flex', alignItems:'center', gap:'6px', height:'32px', padding:'0 12px', border:'1px solid '+p.border, background:p.bg, color:p.color, borderRadius:'8px', font:'inherit', fontSize:'12.5px', fontWeight:p.weight, cursor:'pointer' }">
              <span :style="{ width:'6px', height:'6px', borderRadius:'50%', background:p.dot }"></span>{{ p.label }}
            </button>
          </div>
          <div v-if="paySubtitle" style="font-size:12px;color:var(--text-3);margin:-6px 0 14px">{{ paySubtitle }}</div>
          <div style="display:flex;flex-direction:column;gap:13px">
            <div v-for="f in payFields" :key="f.key">
              <label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ f.label }}</label>
              <input :value="f.value" @input="f.onInput($event.target.value)" :type="f.type" :placeholder="f.ph" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur">
            </div>
            <div v-if="paySandboxShow" style="display:flex;align-items:center;gap:11px">
              <button @click="togglePaySandbox" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:paySandboxBg, transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:paySandboxX, width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
              <span style="font-size:13px;color:var(--text-2)">{{ paySandboxLabel }}</span>
            </div>
            <div v-if="payIsStripe" style="display:flex;align-items:center;font-size:12px;font-weight:600;color:var(--text-2);margin-top:2px">
              {{ tr('settings.extraMethods') || 'Extra payment methods' }}<D2HelpTip text="Stripe Checkout shows only credit cards by default. To also offer Alipay, WeChat Pay, SEPA Debit, iDEAL, etc., enable each method in your Stripe Dashboard → Settings → Payment methods, then add it to STRIPE_PAYMENT_METHODS in the .env and restart the client-portal service." />
            </div>
            <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px;background:var(--panel-2)"><div style="font-size:11px;color:var(--text-3);margin-bottom:5px">{{ tr('settings.webhookUrl') || 'Webhook URL' }}</div><div style="display:flex;align-items:center;gap:8px"><span style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-2);flex:1;word-break:break-all">{{ payWebhook }}</span><button @click="copyPayWebhook" style="border:none;background:transparent;color:var(--text-3);cursor:pointer;display:flex;flex:none"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button></div></div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:16px">
            <button @click="savePayProvider" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('settings.connect') || 'Save & Connect' }}</button>
            <button @click="testPayProvider" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.test') || 'Test' }}</button>
            <button v-if="payConnected" @click="disconnectPayProvider" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--red);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.disconnect') || 'Disconnect' }}</button>
          </div>
          <div v-if="msg.pay" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.pay }}</div>
        </div>

        <!-- ================= SMTP ================= -->
        <div v-if="isSetSmtp" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px"><div style="font-weight:650;font-size:15px;flex:1">{{ tr('settings.smtpTitle') || 'Email (SMTP)' }}</div><span :style="{ fontSize:'11px', fontWeight:600, padding:'3px 9px', borderRadius:'7px', color:smtpBadgeColor, background:smtpBadgeBg }">{{ smtpBadge }}</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px">
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.smtpHost') || 'Host' }}</label><input :value="smtp.host" @input="smtp.host = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.smtpPort') || 'Port' }}</label><input :value="smtp.port" @input="smtp.port = $event.target.value" inputmode="numeric" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.smtpUser') || 'Username' }}</label><input :value="smtp.username" @input="smtp.username = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.smtpPass') || 'Password' }}</label><input type="password" :value="smtp.password" @input="smtp.password = $event.target.value" :placeholder="smtp.passwordSet ? '••••••••' : ''" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.smtpFrom') || 'From address' }} <span style="color:var(--accent);font-weight:600">· Enterprise</span></label><input :value="smtp.from" @input="smtp.from = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
          </div>
          <div style="display:flex;gap:22px;margin-top:14px">
            <div style="display:flex;align-items:center;gap:10px"><button @click="smtp.tls = !smtp.tls" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(smtp.tls), transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tgX(smtp.tls), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button><span style="font-size:13px;color:var(--text-2)">{{ tr('settings.smtpTls') || 'Use TLS' }}</span></div>
            <div style="display:flex;align-items:center;gap:10px"><button @click="smtp.enabled = !smtp.enabled" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(smtp.enabled), transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tgX(smtp.enabled), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button><span style="font-size:13px;color:var(--text-2)">{{ tr('settings.smtpEnabled') || 'Enabled' }}</span></div>
          </div>
          <div style="display:flex;gap:8px;margin-top:18px">
            <button @click="saveSmtp" :disabled="busy.smtp" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('settings.connect') || 'Save & Connect' }}</button>
            <button @click="testSmtp" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.test') || 'Test' }}</button>
            <button v-if="smtp.enabled" @click="disconnectSmtp" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--red);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.disconnect') || 'Disconnect' }}</button>
          </div>
          <div v-if="msg.smtp" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.smtp }}</div>
        </div>

        <!-- ================= TELEGRAM NOTIFICATIONS ================= -->
        <div v-if="isSetNotif" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('notifications.title') || 'Telegram notifications' }}</div>
          <div style="margin-bottom:16px"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('notifications.adminChatId') || 'Admin chat ID' }}</label><input :value="notif.admin_telegram_chat_id" @input="notif.admin_telegram_chat_id = $event.target.value" style="width:240px;max-width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
          <div style="display:flex;flex-direction:column;gap:2px;margin-bottom:18px">
            <div v-for="tg in tgToggles" :key="tg.key" style="display:flex;align-items:center;gap:11px;padding:9px 2px;border-bottom:1px solid var(--border)">
              <button @click="tg.on" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tg.bg, transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tg.x, width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
              <span style="font-size:13px;color:var(--text-2)">{{ tg.label }}</span>
            </div>
          </div>
          <button @click="saveNotifSettings" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('common.save') || 'Save' }}</button>
          <div v-if="msg.notif" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.notif }}</div>
        </div>

        <!-- ================= APPS & FCM ================= -->
        <div v-if="isSetApps" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('settings.appsTitle') || 'Customer app & push' }}</div>
          <div style="display:flex;align-items:center;gap:11px;margin-bottom:16px">
            <button @click="apps.enabled = !apps.enabled" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(apps.enabled), transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tgX(apps.enabled), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
            <span style="font-size:13px;color:var(--text-2)">{{ tr('settings.appsEnabled') || 'Customer app integration enabled' }}</span>
          </div>
          <!-- App name + push config only appear once the app integration is enabled. -->
          <template v-if="apps.enabled">
            <div style="display:flex;flex-direction:column;gap:13px;margin-bottom:16px">
              <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.appName') || 'App name (push subtitle)' }}</label><input :value="apps.name" @input="apps.name = $event.target.value" maxlength="64" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            </div>
            <div style="display:flex;align-items:flex-start;gap:11px;margin-bottom:16px;padding:13px 14px;background:var(--panel-2);border:1px solid var(--border);border-radius:11px">
              <button @click="apps.push = !apps.push" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(apps.push), transition:'background .15s', flex:'none', marginTop:'1px' }"><span :style="{ position:'absolute', top:'2px', left:tgX(apps.push), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
              <div style="min-width:0"><div style="font-size:13px;font-weight:550;color:var(--text)">{{ tr('settings.appsPush') || 'Push notifications' }}</div><div style="font-size:11.5px;color:var(--text-3);margin-top:3px;line-height:1.45">{{ tr('settings.appsPushDesc') || 'Send mobile push via Firebase Cloud Messaging.' }}</div></div>
            </div>
            <!-- FCM key only when push is switched on. -->
            <div v-if="apps.push" style="display:flex;flex-direction:column;gap:13px;margin-bottom:18px">
              <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.fcmKey') || 'FCM server key' }}</label><input type="password" :value="fcm.server_key" @input="fcm.server_key = $event.target.value" :placeholder="fcm.server_key_set ? '•••••••••• (configured)' : 'AAAA…'" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"><div style="font-size:11.5px;color:var(--text-3);margin-top:6px">{{ tr('settings.fcmKeyHint') || 'Firebase Cloud Messaging server key — used to deliver mobile push.' }}</div></div>
            </div>
          </template>
          <div style="display:flex;gap:8px">
            <button @click="saveApps" :disabled="busy.apps" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('common.save') || 'Save' }}</button>
            <button v-if="apps.enabled && apps.push && fcm.server_key_set" @click="clearFcm" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.clearFcm') || 'Clear FCM key' }}</button>
          </div>
          <div v-if="msg.apps" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.apps }}</div>
        </div>

        <!-- ================= LIMITS ================= -->
        <div v-if="isSetLimits" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('settings.deviceLimitsTitle') || 'Limits' }}</div>
          <div style="display:flex;align-items:center;gap:11px;padding:13px 0;border-bottom:1px solid var(--border)">
            <button @click="freeTier = !freeTier" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(freeTier), transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tgX(freeTier), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
            <div style="flex:1"><div style="font-size:13px;font-weight:550">{{ tr('settings.enableFreeTier') || 'Free tier auto-grant' }}</div><div style="font-size:11.5px;color:var(--text-3)">{{ tr('settings.freeTierDesc') || 'Automatically grant a free plan to new registrations.' }}</div></div>
            <button @click="saveFreeTier" style="height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer">{{ tr('common.save') || 'Save' }}</button>
          </div>
          <div style="display:flex;align-items:flex-end;gap:11px;padding-top:16px">
            <div style="flex:1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.maxDevicesPerCustomer') || 'Max devices per customer' }}</label><div style="font-size:11.5px;color:var(--text-3);margin-bottom:7px">{{ tr('settings.maxDevicesDesc') || '0 = no cap.' }}</div><input :value="deviceLimit" @input="deviceLimit = $event.target.value" inputmode="numeric" style="width:160px;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <button @click="saveDeviceLimits" :disabled="busy.dl" style="height:40px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;flex:none">{{ tr('common.save') || 'Save' }}</button>
          </div>
          <div v-if="msg.dl || msg.ft" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.dl || msg.ft }}</div>
        </div>

        <!-- ================= WEB ACCESS ================= -->
        <div v-if="isSetWeb" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
            <div style="font-weight:650;font-size:15px;flex:1">{{ tr('common.webAccessTitle') || 'Web access' }}</div>
            <div style="display:flex;gap:10px">
              <span style="display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-3)"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:webNginxColor }"></span>nginx</span>
              <span style="display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-3)"><span :style="{ width:'7px', height:'7px', borderRadius:'50%', background:webSslColor }"></span>SSL</span>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:16px">
            <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.portalUrl') || 'Portal URL' }}</div><div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-2);margin-top:3px;word-break:break-all">{{ webPortalUrl }}</div></div>
            <div style="padding:11px 13px;border:1px solid var(--border);border-radius:10px"><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.adminUrl') || 'Admin URL' }}</div><div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--text-2);margin-top:3px;word-break:break-all">{{ webAdminUrl }}</div></div>
          </div>
          <label style="display:block;font-size:12px;font-weight:550;margin-bottom:8px">{{ tr('common.webAccessMode') || 'Access mode' }}</label>
          <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px">
            <button v-for="m in webModes" :key="m.key" @click="m.on"
              :style="{ display:'flex', alignItems:'center', gap:'10px', padding:'11px 13px', border:'1px solid '+m.border, background:m.bg, borderRadius:'10px', cursor:'pointer', font:'inherit', textAlign:'left' }">
              <span :style="{ width:'16px', height:'16px', borderRadius:'50%', border:'2px solid '+m.dotBorder, background:m.dotBg, flex:'none' }"></span>
              <span style="font-size:13px;color:var(--text);font-weight:500">{{ m.label }}</span>
              <span v-if="m.recommended" style="font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:6px;color:var(--green);background:var(--green-soft)">{{ tr('common.recommended') || 'Recommended' }}</span>
            </button>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px;margin-bottom:16px">
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('common.clientPortalDomain') || 'Portal domain' }}</label><input :value="web.client_portal_domain" @input="web.client_portal_domain = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('common.adminPanelDomain') || 'Admin domain' }}</label><input :value="web.admin_panel_domain" @input="web.admin_panel_domain = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('common.certbotEmail') || 'Certbot email' }}</label><input :value="web.certbot_email" @input="web.certbot_email = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
          </div>
          <div style="display:flex;gap:8px">
            <button @click="saveWebAccess" :disabled="web.applying" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('common.apply') || 'Apply' }}</button>
            <button @click="refreshWebAccess" style="height:38px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer">{{ tr('settings.refreshNow') || 'Refresh' }}</button>
          </div>
          <div v-if="msg.web" style="font-size:12.5px;color:var(--green);margin-top:10px">{{ msg.web }}</div>
        </div>

        <!-- ================= SYSTEM TOOLS ================= -->
        <template v-if="isSetTools">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-weight:650;font-size:15px;margin-bottom:14px">{{ tr('settings.healthCheck') || 'Health check' }}</div>
              <div style="display:flex;gap:18px;margin-bottom:16px">
                <span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-2)"><span :style="{ width:'8px', height:'8px', borderRadius:'50%', background:toolDbColor }"></span>{{ tr('settings.database') || 'Database' }}</span>
                <span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-2)"><span :style="{ width:'8px', height:'8px', borderRadius:'50%', background:toolWgColor }"></span>WireGuard</span>
              </div>
              <div style="display:flex;align-items:center;gap:10px">
                <button @click="runHealthCheck" :disabled="busy.health" style="display:flex;align-items:center;gap:7px;height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer"><span v-if="busy.health" style="width:13px;height:13px;border:2px solid rgba(255,255,255,.5);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ tr('settings.runCheck') || 'Run check' }}</button>
                <span v-if="msg.tools" style="font-size:12px;color:var(--text-2)">{{ msg.tools }}</span>
              </div>
            </div>
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-weight:650;font-size:15px;margin-bottom:14px">{{ tr('settings.limitCheck') || 'Limit enforcement' }}</div>
              <div style="display:flex;gap:16px;margin-bottom:16px">
                <div><div style="font-size:18px;font-weight:680;font-family:'JetBrains Mono',monospace;color:var(--amber)">{{ tools.expired }}</div><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.expired') || 'Expired' }}</div></div>
                <div><div style="font-size:18px;font-weight:680;font-family:'JetBrains Mono',monospace;color:var(--red)">{{ tools.exceeded }}</div><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.exceeded') || 'Exceeded' }}</div></div>
                <div><div style="font-size:18px;font-weight:680;font-family:'JetBrains Mono',monospace;color:var(--text-3)">{{ tools.disabled }}</div><div style="font-size:11px;color:var(--text-3)">{{ tr('settings.disabled') || 'Disabled' }}</div></div>
              </div>
              <div style="display:flex;align-items:center;gap:10px">
                <button @click="runLimitCheck" :disabled="busy.limit" style="display:flex;align-items:center;gap:7px;height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer"><span v-if="busy.limit" style="width:13px;height:13px;border:2px solid rgba(255,255,255,.5);border-top-color:#fff;border-radius:50%;animation:d2spin .6s linear infinite;display:inline-block"></span>{{ tr('settings.triggerCheck') || 'Trigger' }}</button>
                <span v-if="msg.limit" style="font-size:12px;color:var(--text-2)">{{ msg.limit }}</span>
              </div>
            </div>
          </div>
          <!-- Create admin -->
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
            <div style="font-weight:650;font-size:15px;margin-bottom:14px">{{ tr('settings.createAdmin') || 'Create admin' }}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px">
              <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('applications.username') || 'Username' }}</label><input :value="newAdmin.username" @input="newAdmin.username = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
              <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('applications.password') || 'Password' }}</label><input type="password" :value="newAdmin.password" @input="newAdmin.password = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            </div>
            <div style="display:flex;align-items:center;gap:10px;margin-top:14px">
              <button @click="createAdmin" :disabled="busy.adm" style="height:38px;padding:0 15px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer">{{ tr('applications.createAccount') || 'Create admin' }}</button>
              <span v-if="msg.adm" :style="{ fontSize:'12.5px', color: msgAdmTone==='ok' ? 'var(--green)' : 'var(--red)' }">{{ msg.adm }}</span>
            </div>
          </div>
        </template>

        <!-- ================= BRANDING ================= -->
        <div v-if="isSetBranding" style="display:grid;grid-template-columns:1fr 320px;gap:16px;align-items:start">
          <div style="display:flex;flex-direction:column;gap:16px">
            <!-- identity -->
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:14px">{{ tr('settings.brandIdentity') || 'Identity' }}</div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px">
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.appName') || 'App name' }}</label><input :value="brand.app_name" @input="brand.app_name = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.brandNameLabel') || 'Brand (customer-facing)' }}</label><input :value="brand.brand_name" @input="brand.brand_name = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.taglineLabel') || 'Logo tagline' }}</label><input :value="brand.tagline" @input="brand.tagline = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.companyName') || 'Company' }}</label><input :value="brand.company_name" @input="brand.company_name = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.loginTitle') || 'Login title' }}</label><input :value="brand.login_title" @input="brand.login_title = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
              </div>
            </div>

            <!-- assets / logo slots -->
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:6px">{{ tr('settings.brandAssets') || 'Logos & assets' }}</div>
              <div style="font-size:11.5px;color:var(--text-3);margin-bottom:14px">{{ tr('settings.brandRecommend') || 'PNG/SVG/WebP, up to 1 MB.' }}</div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:11px">
                <label v-for="lg in logoSlots" :key="lg.key" style="display:block;padding:13px;border:1px dashed var(--border-strong);border-radius:11px;text-align:center;cursor:pointer">
                  <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" @change="lg.onFile" style="display:none">
                  <div style="font-size:11px;font-weight:600;color:var(--text-3);margin-bottom:9px">{{ lg.label }}</div>
                  <div style="width:52px;height:52px;border-radius:11px;background:var(--panel-2);display:flex;align-items:center;justify-content:center;margin:0 auto 10px;color:var(--text-3);overflow:hidden">
                    <img v-if="lg.url" :src="lg.url" alt="" style="max-width:100%;max-height:100%;object-fit:contain">
                    <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M3 16l5-5 4 4 3-3 6 6"></path><circle cx="9" cy="9" r="1.5"></circle></svg>
                  </div>
                  <div style="display:flex;gap:5px;justify-content:center">
                    <span style="height:28px;padding:0 10px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:7px;font-size:11.5px;font-weight:550;display:inline-flex;align-items:center">{{ tr('settings.upload') || 'Upload' }}</span>
                    <button v-if="lg.url" @click.prevent="lg.onRemove" style="height:28px;padding:0 10px;border:none;background:transparent;color:var(--text-3);border-radius:7px;font:inherit;font-size:11.5px;cursor:pointer">{{ tr('settings.remove') || 'Remove' }}</button>
                  </div>
                </label>
              </div>
            </div>

            <!-- theme color -->
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:14px">{{ tr('settings.brandTheme') || 'Brand color' }}</div>
              <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px">
                <button v-for="p in brandPresets" :key="p.hex" @click="p.on" :title="p.hex"
                  :style="{ width:'32px', height:'32px', borderRadius:'9px', border:'2px solid '+p.border, background:p.hex, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }">
                  <svg v-if="p.on_selected" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6"><path d="M5 12l4 4L19 7"></path></svg>
                </button>
              </div>
              <div style="display:flex;align-items:center;gap:9px">
                <input type="color" :value="brand.primary_color" @input="brand.primary_color = $event.target.value; branding.previewAccent($event.target.value)" style="width:40px;height:40px;border:1px solid var(--border);border-radius:9px;padding:2px;background:var(--panel);cursor:pointer;flex:none">
                <input :value="brand.primary_color" @input="brand.primary_color = $event.target.value; branding.previewAccent($event.target.value)" style="flex:1;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur">
              </div>
              <div style="font-size:11.5px;color:var(--text-3);margin-top:8px">{{ tr('settings.brandApplyHint') || 'Color previews instantly in the admin panel and applies to the client portal after saving.' }}</div>
            </div>

            <!-- support -->
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
              <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:14px">{{ tr('settings.brandSupport') || 'Support & footer' }}</div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:13px">
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.supportEmail') || 'Support email' }}</label><input :value="brand.support_email" @input="brand.support_email = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.supportUrl') || 'Support URL' }}</label><input :value="brand.support_url" @input="brand.support_url = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.privacyUrl') || 'Privacy Policy URL' }}</label><input :value="brand.privacy_url" @input="brand.privacy_url = $event.target.value" placeholder="https://example.com/privacy" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.termsUrl') || 'Terms of Service URL' }}</label><input :value="brand.terms_url" @input="brand.terms_url = $event.target.value" placeholder="https://example.com/terms" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
                <div style="grid-column:1 / -1;font-size:11.5px;color:var(--text-3);line-height:1.5">{{ tr('settings.legalUrlHint') || 'An external URL takes priority. Leave it empty to publish the text below as a branded portal page.' }}</div>
                <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.privacyText') || 'Privacy Policy text' }}</label><textarea v-model="brand.privacy_text" maxlength="50000" rows="8" :placeholder="tr('settings.privacyTextPlaceholder') || 'Write your Privacy Policy here…'" style="width:100%;min-height:150px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:11px 12px;font:inherit;font-size:13px;line-height:1.55;outline:none" @focus="onFocus" @blur="onBlur"></textarea></div>
                <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.termsText') || 'Terms of Service text' }}</label><textarea v-model="brand.terms_text" maxlength="50000" rows="8" :placeholder="tr('settings.termsTextPlaceholder') || 'Write your Terms of Service here…'" style="width:100%;min-height:150px;resize:vertical;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:11px 12px;font:inherit;font-size:13px;line-height:1.55;outline:none" @focus="onFocus" @blur="onBlur"></textarea></div>
                <div style="grid-column:1 / -1"><label style="display:block;font-size:12px;font-weight:550;margin-bottom:6px">{{ tr('settings.footerText') || 'Footer' }}</label><input :value="brand.footer_text" @input="brand.footer_text = $event.target.value" style="width:100%;height:40px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 12px;font:inherit;font-size:13px;outline:none" @focus="onFocus" @blur="onBlur"></div>
              </div>
              <div style="display:flex;align-items:center;gap:11px;margin-top:14px">
                <button @click="brand.powered_by = !brand.powered_by" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background:tgBg(brand.powered_by), transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'2px', left:tgX(brand.powered_by), width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button>
                <span style="font-size:13px;color:var(--text-2)">{{ tr('settings.brandPowered') || 'Show “Powered by”' }}</span>
              </div>
            </div>

            <div style="display:flex;align-items:center;gap:8px">
              <button @click="saveBranding" :disabled="busy.brand" style="height:40px;padding:0 16px;border:none;background:var(--accent);color:#fff;border-radius:9px;font:inherit;font-size:13px;font-weight:600;cursor:pointer">{{ tr('settings.brandSave') || 'Apply branding' }}</button>
              <button @click="resetBranding" style="height:40px;padding:0 14px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:13px;font-weight:550;cursor:pointer">{{ tr('settings.brandReset') || 'Reset' }}</button>
              <span v-if="msg.brand" style="font-size:12.5px;color:var(--green)">{{ msg.brand }}</span>
            </div>
          </div>

          <D2BrandingPreview :brand="brand" />
        </div>

        <!-- ================= UPDATE CHANNEL ================= -->
        <div v-if="isSetUpdates" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('updates.channel') || 'Update channel' }}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <button @click="setChannel('stable')" :style="{ textAlign:'left', padding:'16px', border:'2px solid '+(channel==='stable'?'var(--accent)':'var(--border)'), background:(channel==='stable'?'var(--accent-soft)':'var(--panel)'), borderRadius:'12px', cursor:'pointer', font:'inherit' }">
              <div style="display:flex;align-items:center;gap:8px"><span style="font-weight:650;font-size:14px">{{ tr('updates.stable') || 'Stable' }}</span><span v-if="channel==='stable'" style="width:16px;height:16px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;flex:none"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><path d="M5 12l4 4L19 7"></path></svg></span></div>
              <div style="font-size:12px;color:var(--text-3);margin-top:5px">{{ tr('updates.stableDesc') || 'Tested releases only.' }}</div>
            </button>
            <button @click="setChannel('test')" :style="{ textAlign:'left', padding:'16px', border:'2px solid '+(channel==='test'?'var(--accent)':'var(--border)'), background:(channel==='test'?'var(--accent-soft)':'var(--panel)'), borderRadius:'12px', cursor:'pointer', font:'inherit' }">
              <div style="display:flex;align-items:center;gap:8px"><span style="font-weight:650;font-size:14px">{{ tr('updates.test') || 'Test' }}</span><span v-if="channel==='test'" style="width:16px;height:16px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;flex:none"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><path d="M5 12l4 4L19 7"></path></svg></span></div>
              <div style="font-size:12px;color:var(--text-3);margin-top:5px">{{ tr('updates.testDesc') || 'Newer features, may have bugs.' }}</div>
            </button>
          </div>
          <div v-if="msg.ch" style="font-size:12.5px;color:var(--green);margin-top:12px">{{ msg.ch }}</div>
        </div>

        <!-- ================= DONATE WALLETS ================= -->
        <div v-if="isSetDonate" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
          <div style="font-weight:650;font-size:15px;margin-bottom:4px">{{ tr('settings.donateWallets') || 'Donation wallets' }}</div>
          <div style="font-size:12.5px;color:var(--text-2);margin-bottom:18px">{{ tr('settings.donateWalletsSub') || 'Addresses shown in the “Donate” modal.' }}</div>
          <div style="display:flex;flex-direction:column;gap:14px">
            <div><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">Bitcoin (BTC)</label><input :value="donate.btc" @input="donate.btc = $event.target.value" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">Ethereum / USDT (ERC-20)</label><input :value="donate.eth" @input="donate.eth = $event.target.value" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">TON</label><input :value="donate.ton" @input="donate.ton = $event.target.value" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">USDT (TRC-20)</label><input :value="donate.trc" @input="donate.trc = $event.target.value" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
            <div><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">USDC (ERC-20)</label><input :value="donate.usdc" @input="donate.usdc = $event.target.value" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"></div>
          </div>
          <div style="margin-top:16px"><label style="display:block;font-size:12.5px;font-weight:550;margin-bottom:7px">{{ tr('settings.donateCardUrl') || 'Card donation link (Paylio)' }}</label><input :value="donate.card_url" @input="donate.card_url = $event.target.value" placeholder="https://…/checkout/…" style="width:100%;height:42px;border:1px solid var(--border-strong);background:var(--panel-2);color:var(--text);border-radius:10px;padding:0 13px;font-family:'JetBrains Mono',monospace;font-size:12.5px;outline:none" @focus="onFocus" @blur="onBlur"><div style="font-size:11.5px;color:var(--text-3);margin-top:5px">{{ tr('settings.donateCardUrlSub') || 'Paylio hosted-checkout link, settles to your payout wallet. Shown as “Pay by card” in the Donate modal.' }}</div></div>
          <div style="display:flex;align-items:flex-start;gap:11px;margin-top:16px;padding:13px 14px;background:var(--panel-2);border:1px solid var(--border);border-radius:11px">
            <button @click="licensed && (donate.hidden = !donate.hidden)" :disabled="!licensed" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor: licensed ? 'pointer' : 'not-allowed', background: donate.hidden ? 'var(--accent)' : 'var(--border-strong)', opacity: licensed ? 1 : .5, flex:'none', marginTop:'1px' }"><span :style="{ position:'absolute', top:'2px', left: donate.hidden ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s' }"></span></button>
            <div style="min-width:0"><div style="font-size:13px;font-weight:550;color:var(--text)">{{ tr('settings.hideDonate') || 'Hide the Support button' }}</div><div style="font-size:11.5px;color:var(--text-3);margin-top:3px;line-height:1.45">{{ licensed ? (tr('settings.hideDonateOn') || 'Removes the Donate button across the panel.') : (tr('settings.hideDonateGated') || 'Available once the panel is licensed — buying a license already supports the project.') }}</div></div>
          </div>
          <div style="display:flex;justify-content:flex-end;align-items:center;gap:10px;margin-top:18px">
            <span v-if="msg.dn" style="font-size:12.5px;color:var(--green)">{{ msg.dn }}</span>
            <button @click="saveDonateWallets" style="height:40px;padding:0 18px;border:none;background:var(--accent);color:#fff;border-radius:10px;font:inherit;font-size:13px;font-weight:600;cursor:pointer">{{ tr('common.save') || 'Save' }}</button>
          </div>
        </div>

        <!-- ================= INTERFACE / DESIGN ================= -->
        <template v-if="isSetInterface">
          <!-- theme -->
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
            <div style="font-weight:650;font-size:15px;margin-bottom:16px">{{ tr('settings.theme') || 'Appearance' }}</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px">
              <button v-for="th in themeOptions" :key="th.key" @click="system.setTheme(th.key)"
                :style="{ display:'flex', alignItems:'center', gap:'8px', height:'40px', padding:'0 15px', border:'2px solid '+(currentTheme===th.key?'var(--accent)':'var(--border-strong)'), background:(currentTheme===th.key?'var(--accent-soft)':'var(--panel)'), color:(currentTheme===th.key?'var(--accent)':'var(--text-2)'), borderRadius:'10px', font:'inherit', fontSize:'13px', fontWeight:600, cursor:'pointer' }">
                <span v-html="th.icon" style="display:flex"></span>{{ th.label }}
              </button>
            </div>
          </div>

          <!-- design toggle (New vs Legacy) -->
          <div style="max-width:760px">
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:22px 24px;margin-bottom:16px">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px">
                <div>
                  <div style="font-weight:650;font-size:15px">{{ tr('settings.designMode') || 'Design mode' }}</div>
                  <div style="font-size:12.5px;color:var(--text-2);margin-top:4px;max-width:420px;line-height:1.5">{{ tr('settings.designModeHint') || 'Switch between the new design and the classic (legacy) one.' }}</div>
                </div>
                <div style="display:flex;align-items:center;gap:10px;flex:none">
                  <span :style="{ fontSize:'12.5px', fontWeight:550, color: design.isLegacy ? 'var(--text)' : 'var(--text-3)' }">{{ tr('settings.designLegacy') || 'Legacy' }}</span>
                  <button @click="toggleDesign" :title="tr('settings.designMode') || 'Design mode'" :style="{ position:'relative', width:'46px', height:'26px', borderRadius:'20px', border:'none', cursor:'pointer', background: design.isNew ? 'var(--accent)' : 'var(--border-strong)', transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'3px', left: design.isNew ? '23px' : '3px', width:'20px', height:'20px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 3px rgba(0,0,0,.25)' }"></span></button>
                  <span :style="{ fontSize:'12.5px', fontWeight:550, color: design.isNew ? 'var(--text)' : 'var(--text-3)' }">{{ tr('settings.designNew') || 'New' }}</span>
                </div>
              </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
              <button @click="design.set('new')" :style="{ textAlign:'left', padding:'0', border:'2px solid '+(design.isNew?'var(--accent)':'var(--border)'), background:'var(--panel)', borderRadius:'14px', cursor:'pointer', font:'inherit', overflow:'hidden', boxShadow:'var(--shadow)' }">
                <div style="height:128px;background:linear-gradient(135deg,var(--accent) 0%,#8b5cf6 100%);position:relative;display:flex;align-items:center;justify-content:center">
                  <div style="position:absolute;left:14px;top:14px;width:42px;height:calc(100% - 28px);background:rgba(255,255,255,.16);border-radius:8px"></div>
                  <div style="position:absolute;left:66px;right:14px;top:14px;height:18px;background:rgba(255,255,255,.22);border-radius:5px"></div>
                  <div style="position:absolute;left:66px;right:14px;top:42px;bottom:14px;background:rgba(255,255,255,.10);border-radius:7px"></div>
                </div>
                <div style="padding:14px 16px">
                  <div style="display:flex;align-items:center;gap:8px">
                    <span style="font-weight:650;font-size:14px">{{ tr('settings.designNew') || 'New' }}</span>
                    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:#fff;background:var(--accent)">beta</span>
                    <span v-if="design.isNew" style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--green)"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('settings.designCurrent') || 'Current' }}</span>
                  </div>
                  <div style="font-size:12.5px;color:var(--text-3);margin-top:6px;line-height:1.5">{{ tr('settings.designNewDesc') || 'The redesigned flat interface.' }}</div>
                </div>
              </button>

              <button @click="design.set('legacy')" :style="{ textAlign:'left', padding:'0', border:'2px solid '+(design.isLegacy?'var(--accent)':'var(--border)'), background:'var(--panel)', borderRadius:'14px', cursor:'pointer', font:'inherit', overflow:'hidden', boxShadow:'var(--shadow)' }">
                <div style="height:128px;background:#e9ecef;position:relative">
                  <div style="position:absolute;left:0;top:0;bottom:0;width:54px;background:#343a40"></div>
                  <div style="position:absolute;left:0;right:0;top:0;height:26px;background:#0d6efd"></div>
                  <div style="position:absolute;left:68px;right:14px;top:38px;height:30px;background:#fff;border:1px solid #ced4da;border-radius:4px"></div>
                  <div style="position:absolute;left:68px;right:14px;top:78px;bottom:14px;background:#fff;border:1px solid #ced4da;border-radius:4px"></div>
                </div>
                <div style="padding:14px 16px">
                  <div style="display:flex;align-items:center;gap:8px">
                    <span style="font-weight:650;font-size:14px">{{ tr('settings.designLegacy') || 'Legacy' }}</span>
                    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:var(--text-2);background:var(--panel-3)">legacy</span>
                    <span v-if="design.isLegacy" style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--green)"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('settings.designCurrent') || 'Current' }}</span>
                  </div>
                  <div style="font-size:12.5px;color:var(--text-3);margin-top:6px;line-height:1.5">{{ tr('settings.designLegacyDesc') || 'The original Bootstrap interface.' }}</div>
                </div>
              </button>
            </div>

            <div style="margin-top:16px;display:flex;align-items:center;gap:10px;padding:13px 16px;background:var(--amber-soft);border:1px solid var(--amber-soft);border-radius:11px">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8" style="flex:none"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v4M12 16h.01"></path></svg>
              <span style="font-size:12.5px;color:var(--text-2);line-height:1.5">{{ tr('settings.designNote') || 'The switch takes effect immediately and is remembered on this browser.' }}</span>
            </div>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { systemApi } from '../../api'
import { useDesignMode } from '../../stores/designMode'
import { useSystemStore } from '../../stores/system'
import { useBrandingStore } from '../../stores/branding'
import { useD2Ui } from '../../stores/d2ui'
import D2HelpTip from '../ui/D2HelpTip.vue'
import D2BrandingPreview from '../ui/D2BrandingPreview.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }

const design = useDesignMode()
const system = useSystemStore()
const branding = useBrandingStore()
const ui = useD2Ui()

// focus/blur ring on inputs (his style-focus)
function onFocus(e) { const s = e.target.style; s.borderColor = 'var(--accent)'; s.boxShadow = '0 0 0 3px var(--accent-ring)'; s.background = 'var(--panel)' }
function onBlur(e) { const s = e.target.style; s.borderColor = 'var(--border-strong)'; s.boxShadow = 'none'; s.background = 'var(--panel-2)' }

// ── toggle helpers (his 38x22 switches) ──
function tgBg(v) { return v ? 'var(--accent)' : 'var(--border-strong)' }
function tgX(v) { return v ? '18px' : '2px' }

const busy = reactive({})
const msg = reactive({})
function flash(k, m) { msg[k] = m; setTimeout(() => { msg[k] = '' }, 3000) }
function errorText(e, fallback = 'Error') {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') return detail.message || fallback
  return e?.response?.data?.message || fallback
}

function requestUpgrade(feature, tier = 'enterprise') {
  window.dispatchEvent(new CustomEvent('flirexa:upgrade-required', {
    detail: {
      message: `This setting requires ${tier.charAt(0).toUpperCase() + tier.slice(1)}.`,
      tier,
      feature,
      url: 'https://flirexa.biz/#pricing',
    },
  }))
}

// ── active tab ──
const active = ref('license')
const isSetLicense = computed(() => active.value === 'license')
const isSetPayments = computed(() => active.value === 'payments')
const isSetSmtp = computed(() => active.value === 'smtp')
const isSetNotif = computed(() => active.value === 'notif')
const isSetApps = computed(() => active.value === 'apps')
const isSetLimits = computed(() => active.value === 'limits')
const isSetWeb = computed(() => active.value === 'web')
const isSetTools = computed(() => active.value === 'tools')
const isSetBranding = computed(() => active.value === 'branding')
const isSetDonate = computed(() => active.value === 'donate')
const isSetUpdates = computed(() => active.value === 'updates')
const isSetInterface = computed(() => active.value === 'interface')

const ICON = {
  license: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M15 7a4 4 0 11-8 0 4 4 0 018 0z"></path><path d="M11 11l-6 6v3h3l6-6"></path></svg>',
  payments: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2" y="5" width="20" height="14" rx="2"></rect><path d="M2 10h20"></path></svg>',
  smtp: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="M3 7l9 6 9-6"></path></svg>',
  notif: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.7 21a2 2 0 01-3.4 0"></path></svg>',
  apps: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="2" width="14" height="20" rx="2"></rect><path d="M12 18h.01"></path></svg>',
  limits: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"></path></svg>',
  web: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18"></path></svg>',
  tools: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 005.4-5.4l-2.8 2.8-2.2-.6-.6-2.2z"></path></svg>',
  branding: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 2l2.9 6.3L22 9.3l-5 4.8 1.2 6.9L12 17.8 5.8 21l1.2-6.9-5-4.8 7.1-1z"></path></svg>',
  donate: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A3.5 3.5 0 0 0 12 5.5 3.5 3.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7z"></path></svg>',
  updates: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 12a9 9 0 11-3-6.7L21 8"></path><path d="M21 3v5h-5"></path></svg>',
  interface: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="13.5" cy="6.5" r="2.5"></circle><circle cx="19" cy="13" r="2"></circle><path d="M12 22a10 10 0 110-20c5 0 8 3 8 6 0 2-2 3-4 3h-2a2 2 0 00-2 3c0 1 1 2 1 3a2 2 0 01-2 2z"></path></svg>',
}
const settingsTabs = computed(() => [
  { key: 'license', label: tr('settings.license') || 'License' },
  { key: 'payments', label: tr('settings.paymentProviders') || 'Payments' },
  { key: 'smtp', label: tr('settings.smtpTitle') || 'Email (SMTP)' },
  { key: 'notif', label: tr('notifications.title') || 'Telegram' },
  { key: 'apps', label: tr('settings.appsTitle') || 'Apps & FCM', feature: 'app_integration', tier: 'enterprise' },
  { key: 'limits', label: tr('settings.deviceLimitsTitle') || 'Limits' },
  { key: 'web', label: tr('common.webAccessTitle') || 'Web access' },
  { key: 'tools', label: tr('settings.systemTools') || 'System tools' },
  { key: 'branding', label: tr('settings.branding') || 'Branding', feature: 'white_label', tier: 'enterprise' },
  { key: 'donate', label: tr('settings.donateWallets') || 'Donation wallets' },
  { key: 'updates', label: tr('updates.channel') || 'Updates' },
  { key: 'interface', label: tr('settings.interface') || 'Interface' },
].map(s => ({
  ...s,
  icon: ICON[s.key] || '',
  bg: active.value === s.key ? 'var(--accent-soft)' : 'transparent',
  color: active.value === s.key ? 'var(--accent)' : 'var(--text-2)',
  weight: active.value === s.key ? 600 : 500,
  on: () => {
    if (s.feature && !hasLicenseFeature(s.feature)) {
      requestUpgrade(s.feature, s.tier)
      return
    }
    active.value = s.key
  },
})))

// ═══════════════ LICENSE ═══════════════
const license = reactive({ type: '', tier: '', max_clients: null, max_servers: null, days_remaining: null, features: [], current_clients: 0, current_servers: 0, server_id: '', owner: '', newKey: '' })
function hasLicenseFeature(feature) {
  return Array.isArray(license.features) && license.features.includes(feature)
}
const licServer = reactive({ primary_url: '', backup_url: '', last_check: '', online_status: '', server_reachable: false })
const msgLicTone = ref('ok')
const licTier = computed(() => license.tier || license.type || '—')
const licMaxClients = computed(() => license.max_clients == null ? '—' : (license.max_clients === 999999 ? '∞' : license.max_clients))
const licMaxServers = computed(() => license.max_servers == null ? '—' : (license.max_servers === 999999 ? '∞' : license.max_servers))
const licDays = computed(() => license.days_remaining != null ? license.days_remaining + 'd' : (tr('settings.permanent') || 'Permanent'))
const licFeatures = computed(() => Array.isArray(license.features) ? license.features : [])
const licClientsUsed = computed(() => license.current_clients ?? 0)
const licServersUsed = computed(() => license.current_servers ?? 0)
function pct(used, max) { const m = Number(max); if (!m || m === 999999) return '0%'; return Math.min(100, Math.round((Number(used || 0) / m) * 100)) + '%' }
const licClientsPct = computed(() => pct(licClientsUsed.value, license.max_clients))
const licServersPct = computed(() => pct(licServersUsed.value, license.max_servers))
const licSrvColor = computed(() => licServer.online_status === 'revoked' ? 'var(--red)' : (licServer.server_reachable ? 'var(--green)' : 'var(--amber)'))
const licSrvLabel = computed(() => licServer.online_status === 'revoked' ? (tr('settings.revoked') || 'Revoked') : (licServer.server_reachable ? (tr('settings.reachable') || 'Reachable') : (tr('settings.unreachable') || 'Unreachable')))
const licLastCheck = computed(() => { if (!licServer.last_check) return '—'; try { return new Date(licServer.last_check).toLocaleString() } catch (_) { return licServer.last_check } })
async function loadLicense() { try { const r = await systemApi.getLicense(); Object.assign(license, r.data); license.newKey = '' } catch (_) {} }
async function loadLicenseServer() { try { const r = await systemApi.getLicenseServer(); Object.assign(licServer, r.data) } catch (_) {} }
async function activateLicense2() { if (!license.newKey) return; busy.lic = true; msgLicTone.value = 'ok'; try { await systemApi.activateLicense({ license_key: license.newKey.trim() }); msg.lic = tr('settings.licenseActivated') || 'License activated!'; license.newKey = ''; await loadLicense() } catch (e) { msgLicTone.value = 'err'; msg.lic = e.response?.data?.detail || 'Activation failed' } finally { busy.lic = false } }
async function refetchLicense() { await loadLicense(); flash('lic', tr('common.done') || 'Re-fetched') }
async function refreshLicenseCheck() { await loadLicenseServer(); await loadLicense(); flash('lic', tr('common.done') || 'Refreshed') }
async function openMigration() { const code = window.prompt(tr('settings.migrationCode') || 'Paste migration code (JSON):'); if (!code || !code.trim()) return; try { await systemApi.applyMigrationCode({ code: code.trim() }); await loadLicense(); await loadLicenseServer(); flash('lic', tr('settings.applied') || 'Applied') } catch (e) { msgLicTone.value = 'err'; msg.lic = e.response?.data?.detail || 'Migration failed' } }
function copyServerId() { try { navigator.clipboard.writeText(license.server_id || '') } catch (_) {} }

// ═══════════════ PAYMENTS ═══════════════
// Full provider parity with the legacy panel: the backend /system/payment-settings
// exposes 7 providers (3 core + 4 plugin). Each provider declares its editable
// fields, an optional sandbox/testnet flag, and its masked/configured read-back.
const payProvider = ref('cryptopay')
const PAY_META = {
  cryptopay:   { label: 'CryptoPay',   dot: 'var(--blue)',   sub: 'Telegram @CryptoBot · USDT, BTC, TON, ETH', sandbox: { key: 'cryptopay_testnet', label: 'Testnet' },
    fields: [{ key: 'cryptopay_api_token', label: 'API token', type: 'password', mask: 'cryptopay_token_masked' }] },
  paypal:      { label: 'PayPal',      dot: 'var(--accent)', sub: 'Visa, Mastercard, PayPal · Worldwide', sandbox: { key: 'paypal_sandbox', label: 'Sandbox' },
    fields: [
      { key: 'paypal_client_id', label: 'Client ID', type: 'text', mask: 'paypal_client_id_masked' },
      { key: 'paypal_client_secret', label: 'Client secret', type: 'password' },
      { key: 'paypal_webhook_id', label: 'Webhook ID', type: 'text', mask: 'paypal_webhook_id_masked' },
    ] },
  nowpayments: { label: 'NOWPayments', dot: 'var(--purple)', sub: '100+ crypto · BTC, ETH, USDT, XMR, TON', sandbox: { key: 'nowpayments_sandbox', label: 'Sandbox' },
    fields: [
      { key: 'nowpayments_api_key', label: 'API key', type: 'password', mask: 'nowpayments_api_key_masked' },
      { key: 'nowpayments_ipn_secret', label: 'IPN secret', type: 'password' },
    ] },
  stripe:      { label: 'Stripe',      dot: 'var(--blue)',   sub: 'Cards, Apple Pay, Google Pay · 46 countries', sandbox: null,
    fields: [
      { key: 'stripe_secret_key', label: 'Secret key', type: 'password', mask: 'stripe_key_masked', ph: 'sk_live_…' },
      { key: 'stripe_webhook_secret', label: 'Webhook secret (optional)', type: 'password', ph: 'whsec_…' },
    ] },
  payme:       { label: 'Payme',       dot: 'var(--green)',  sub: 'UzCard, Humo, Visa · Uzbekistan', sandbox: null,
    fields: [
      { key: 'payme_merchant_id', label: 'Merchant ID', type: 'text', mask: 'payme_id_masked' },
      { key: 'payme_secret_key', label: 'Secret key', type: 'password' },
    ] },
  mollie:      { label: 'Mollie',      dot: 'var(--amber)',  sub: 'Cards, iDEAL, SEPA, Klarna · Europe', sandbox: null,
    fields: [{ key: 'mollie_api_key', label: 'API key', type: 'password', mask: 'mollie_key_masked', ph: 'live_…' }] },
  razorpay:    { label: 'Razorpay',    dot: 'var(--accent)', sub: 'Cards, UPI, NetBanking · India', sandbox: null,
    fields: [
      { key: 'razorpay_key_id', label: 'Key ID', type: 'text', mask: 'razorpay_key_masked', ph: 'rzp_live_…' },
      { key: 'razorpay_key_secret', label: 'Key secret', type: 'password' },
      { key: 'razorpay_webhook_secret', label: 'Webhook secret', type: 'password', ph: 'whsec_…' },
    ] },
}
// Editable form values (typed by the operator) + read-back meta (masked/configured/flags).
const pf = reactive({})   // e.g. pf.cryptopay_api_token
const pmeta = reactive({})
Object.values(PAY_META).forEach(m => { m.fields.forEach(f => { pf[f.key] = '' }); if (m.sandbox) pf[m.sandbox.key] = false })
function payProviderConfigured(k) { return !!pmeta[k + '_configured'] }
const payTabs = computed(() => Object.keys(PAY_META).map(k => {
  const on = payProvider.value === k
  const configured = payProviderConfigured(k)
  return { key: k, label: PAY_META[k].label, on: () => { payProvider.value = k }, border: on ? 'var(--accent)' : 'var(--border-strong)', bg: on ? 'var(--accent-soft)' : 'var(--panel)', color: on ? 'var(--accent)' : 'var(--text-2)', weight: on ? 600 : 500, dot: configured ? 'var(--green)' : PAY_META[k].dot }
}))
const paySubtitle = computed(() => PAY_META[payProvider.value]?.sub || '')
const payFields = computed(() => (PAY_META[payProvider.value]?.fields || []).map(f => ({
  key: f.key,
  label: tr('settings.pf_' + f.key) || f.label,
  value: pf[f.key],
  type: f.type,
  ph: (f.mask && pmeta[f.mask]) || f.ph || '',
  onInput: v => { pf[f.key] = v },
})))
const paySandboxShow = computed(() => !!PAY_META[payProvider.value]?.sandbox)
const paySandboxKey = computed(() => PAY_META[payProvider.value]?.sandbox?.key)
const paySandboxVal = computed(() => paySandboxKey.value ? !!pf[paySandboxKey.value] : false)
const paySandboxBg = computed(() => tgBg(paySandboxVal.value))
const paySandboxX = computed(() => tgX(paySandboxVal.value))
const paySandboxLabel = computed(() => tr('settings.' + (PAY_META[payProvider.value]?.sandbox?.label || '').toLowerCase()) || PAY_META[payProvider.value]?.sandbox?.label || '')
function togglePaySandbox() { const k = paySandboxKey.value; if (k) pf[k] = !pf[k] }
const payIsStripe = computed(() => payProvider.value === 'stripe')
const payConnected = computed(() => payProviderConfigured(payProvider.value))
// Webhook endpoint — matches the legacy path: {origin}/client-portal/webhooks/{provider}.
const payWebhook = computed(() => (typeof window !== 'undefined' ? window.location.origin : '') + '/client-portal/webhooks/' + payProvider.value)
function copyPayWebhook() { try { navigator.clipboard.writeText(payWebhook.value) } catch (_) {} }
async function loadPayments() { try { const r = await systemApi.getPaymentSettings(); Object.assign(pmeta, r.data || {}); Object.values(PAY_META).forEach(m => { if (m.sandbox) pf[m.sandbox.key] = !!pmeta[m.sandbox.key] }) } catch (_) {} }
async function savePayProvider() {
  const m = PAY_META[payProvider.value]; if (!m) return
  try {
    const body = {}
    if (m.sandbox) body[m.sandbox.key] = !!pf[m.sandbox.key]
    m.fields.forEach(f => { const v = (pf[f.key] || '').trim(); if (v) body[f.key] = v })
    await systemApi.updatePaymentSettings(body)
    m.fields.forEach(f => { pf[f.key] = '' })
    await loadPayments(); flash('pay', tr('common.saved') || 'Saved')
  } catch (e) { flash('pay', e.response?.data?.detail || 'Error') }
}
async function testPayProvider() { try { const r = await systemApi.runPaymentTest(payProvider.value); flash('pay', r.data?.ok === false ? (r.data?.message || 'Test failed') : (tr('settings.testOk') || 'Test OK')) } catch (e) { flash('pay', e.response?.data?.detail || 'Test failed') } }
async function disconnectPayProvider() {
  const m = PAY_META[payProvider.value]; if (!m) return
  if (!await d2confirm((tr('settings.disconnect') || 'Disconnect') + ' ' + m.label + '?')) return
  try { const body = {}; m.fields.forEach(f => { body[f.key] = '' }); await systemApi.updatePaymentSettings(body); await loadPayments(); flash('pay', tr('common.done') || 'Disconnected') } catch (e) { flash('pay', e.response?.data?.detail || 'Error') }
}

// ═══════════════ SMTP ═══════════════
const smtp = reactive({ enabled: false, host: '', port: 587, username: '', password: '', passwordSet: false, tls: true, from: '' })
const smtpBadge = computed(() => smtp.enabled ? (tr('settings.enabled') || 'Enabled') : (tr('settings.disabled') || 'Disabled'))
const smtpBadgeColor = computed(() => smtp.enabled ? 'var(--green)' : 'var(--text-3)')
const smtpBadgeBg = computed(() => smtp.enabled ? 'var(--green-soft)' : 'var(--panel-3)')
async function loadSmtp() { try { const r = await systemApi.getSmtpSettings(); const d = r.data; smtp.enabled = !!d.smtp_enabled; smtp.host = d.smtp_host || ''; smtp.port = d.smtp_port || 587; smtp.username = d.smtp_username || ''; smtp.passwordSet = !!d.smtp_password_set; smtp.tls = d.smtp_tls !== false; smtp.from = d.smtp_from || '' } catch (_) {} }
async function saveSmtp() { busy.smtp = true; try { const p = { smtp_host: smtp.host, smtp_port: Number(smtp.port), smtp_username: smtp.username, smtp_tls: smtp.tls, smtp_from: smtp.from, smtp_enabled: smtp.enabled }; if (smtp.password) p.smtp_password = smtp.password; await systemApi.updateSmtpSettings(p); smtp.password = ''; await loadSmtp(); flash('smtp', tr('common.saved') || 'Saved') } catch (e) { flash('smtp', errorText(e)) } finally { busy.smtp = false } }
async function testSmtp() { try { const r = await systemApi.testSmtp(); flash('smtp', r.data?.ok === false ? (r.data?.message || 'Test failed') : (tr('settings.testOk') || 'Test email sent')) } catch (e) { flash('smtp', e.response?.data?.detail || 'Test failed') } }
async function disconnectSmtp() { if (!await d2confirm(tr('settings.disconnect') || 'Disable SMTP?')) return; try { await systemApi.updateSmtpSettings({ smtp_enabled: false }); smtp.enabled = false; flash('smtp', tr('common.done') || 'Disabled') } catch (e) { flash('smtp', e.response?.data?.detail || 'Error') } }

// ═══════════════ TELEGRAM NOTIFICATIONS ═══════════════
const notif = reactive({ admin_telegram_chat_id: '', notify_admin_new_user: true, notify_admin_new_payment: true, notify_admin_subscription_expired: true, notify_user_expiry_warning: true, notify_user_traffic_warning: true, notify_user_payment_confirmed: true })
const TG_KEYS = [
  ['notify_admin_new_user', 'notifications.notifyNewUser', 'New user registered'],
  ['notify_admin_new_payment', 'notifications.notifyNewPayment', 'New payment received'],
  ['notify_admin_subscription_expired', 'notifications.notifyExpired', 'Subscription expired'],
  ['notify_user_expiry_warning', 'notifications.notifyExpiryWarning', 'Expiry warning'],
  ['notify_user_traffic_warning', 'notifications.notifyTrafficWarning', 'Traffic warning'],
  ['notify_user_payment_confirmed', 'notifications.notifyPaymentConfirmed', 'Payment confirmed (to user)'],
]
const tgToggles = computed(() => TG_KEYS.map(([k, i18n, fb]) => ({ key: k, label: tr(i18n) || fb, bg: tgBg(notif[k]), x: tgX(notif[k]), on: () => { notif[k] = !notif[k] } })))
async function loadNotif() { try { const r = await systemApi.getNotificationSettings(); const d = r.data; if (d.admin_telegram_chat_id != null) notif.admin_telegram_chat_id = d.admin_telegram_chat_id; TG_KEYS.forEach(([k]) => { if (d[k] != null) notif[k] = d[k] === true || d[k] === 'true' }) } catch (_) {} }
async function saveNotifSettings() { try { await systemApi.updateNotificationSettings({ admin_telegram_chat_id: notif.admin_telegram_chat_id, notify_admin_new_user: notif.notify_admin_new_user, notify_admin_new_payment: notif.notify_admin_new_payment, notify_admin_subscription_expired: notif.notify_admin_subscription_expired, notify_user_expiry_warning: notif.notify_user_expiry_warning, notify_user_traffic_warning: notif.notify_user_traffic_warning, notify_user_payment_confirmed: notif.notify_user_payment_confirmed }); flash('notif', tr('common.saved') || 'Saved') } catch (e) { flash('notif', e.response?.data?.detail || 'Error') } }

// ═══════════════ APPS & FCM ═══════════════
const apps = reactive({ enabled: false, push: false, name: '' })
const fcm = reactive({ server_key: '', server_key_set: false })
async function loadApps() { try { const r = await systemApi.getNotificationSettings(); const d = r.data; apps.enabled = d.app_integration_enabled === 'true' || d.app_integration_enabled === true; apps.push = d.push_enabled === 'true' || d.push_enabled === true; apps.name = d.app_name || ''; fcm.server_key_set = !!d.fcm_server_key_set } catch (_) {} }
async function saveApps() { busy.apps = true; try { const p = { app_integration_enabled: apps.enabled ? 'true' : 'false', push_enabled: apps.push ? 'true' : 'false', app_name: (apps.name || '').trim() }; if (fcm.server_key) p.fcm_server_key = fcm.server_key; await systemApi.updateNotificationSettings(p); fcm.server_key = ''; await loadApps(); flash('apps', tr('common.saved') || 'Saved') } catch (e) { flash('apps', e.response?.data?.detail || 'Error') } finally { busy.apps = false } }
async function clearFcm() { if (!await d2confirm(tr('settings.clearFcm') || 'Clear FCM key?')) return; try { await systemApi.updateNotificationSettings({ fcm_server_key: '' }); fcm.server_key = ''; await loadApps(); flash('apps', tr('common.done') || 'Cleared') } catch (e) { flash('apps', e.response?.data?.detail || 'Error') } }

// ═══════════════ LIMITS ═══════════════
const deviceLimit = ref(0)
const freeTier = ref(true)
async function loadLimits() { try { const r = await systemApi.getDeviceLimits(); deviceLimit.value = r.data.max_devices_per_customer ?? 0 } catch (_) {} try { const r2 = await systemApi.getSubscriptionSettings(); freeTier.value = r2.data.enable_free_tier !== false } catch (_) {} }
async function saveDeviceLimits() { busy.dl = true; try { await systemApi.updateDeviceLimits({ max_devices_per_customer: Number(deviceLimit.value || 0) }); flash('dl', tr('common.saved') || 'Saved') } catch (e) { flash('dl', e.response?.data?.detail || 'Error') } finally { busy.dl = false } }
async function saveFreeTier() { busy.ft = true; try { await systemApi.updateSubscriptionSettings({ enable_free_tier: !!freeTier.value }); flash('ft', tr('common.saved') || 'Saved') } catch (e) { flash('ft', e.response?.data?.detail || 'Error') } finally { busy.ft = false } }

// ═══════════════ WEB ACCESS ═══════════════
const web = reactive({ setup_mode: 'none', client_portal_url: '', admin_panel_url: '', public_ip_hint: '', client_portal_domain: '', admin_panel_domain: '', certbot_email: '', nginx_installed: false, certbot_installed: false, applying: false })
const webPortalUrl = computed(() => web.client_portal_url || (web.public_ip_hint ? ('http://' + web.public_ip_hint + ':10090') : '—'))
const webAdminUrl = computed(() => web.admin_panel_url || (web.public_ip_hint ? ('http://' + web.public_ip_hint + ':10086') : '—'))
const webNginxColor = computed(() => web.nginx_installed ? 'var(--green)' : 'var(--red)')
const webSslColor = computed(() => web.certbot_installed ? 'var(--green)' : 'var(--red)')
const WEB_MODES = [
  ['none', 'common.webAccessModeNoneTitle', 'No web access setup', false],
  ['portal_admin_ip', 'common.webAccessModePortalIpTitle', 'Portal domain + admin over IP', false, true],
  ['portal_admin_domain', 'common.webAccessModeBothTitle', 'Portal + admin over domain (HTTPS)', true, true],
]
const webModes = computed(() => WEB_MODES.map(([k, i18n, fb, rec, enterpriseOnly]) => {
  const on = web.setup_mode === k
  return { key: k, label: (tr(i18n) || fb) + (enterpriseOnly && !hasLicenseFeature('white_label') ? ' · Enterprise' : ''), recommended: rec, on: () => { if (enterpriseOnly && !hasLicenseFeature('white_label')) return requestUpgrade('white_label'); web.setup_mode = k }, border: on ? 'var(--accent)' : 'var(--border-strong)', bg: on ? 'var(--accent-soft)' : 'var(--panel)', dotBorder: on ? 'var(--accent)' : 'var(--border-strong)', dotBg: on ? 'var(--accent)' : 'transparent' }
}))
async function loadWebAccess() { try { const r = await systemApi.getWebAccessSettings(); Object.assign(web, r.data) } catch (_) {} }
async function saveWebAccess() { web.applying = true; try { await systemApi.applyWebAccessSettings({ setup_mode: web.setup_mode, client_portal_domain: web.client_portal_domain, admin_panel_domain: web.admin_panel_domain, certbot_email: web.certbot_email }); await loadWebAccess(); flash('web', tr('common.saved') || 'Applied') } catch (e) { flash('web', errorText(e)) } finally { web.applying = false } }
async function refreshWebAccess() { await loadWebAccess(); flash('web', tr('common.done') || 'Refreshed') }

// ═══════════════ SYSTEM TOOLS ═══════════════
const tools = reactive({ dbOk: false, wgOk: false, expired: 0, exceeded: 0, disabled: 0 })
const toolDbColor = computed(() => tools.dbOk ? 'var(--green)' : 'var(--text-3)')
const toolWgColor = computed(() => tools.wgOk ? 'var(--green)' : 'var(--text-3)')
// Backend /system/health returns { status, checks: { database, wireguard }, timestamp }.
async function runHealthCheck() {
  busy.health = true
  try {
    const r = await systemApi.getHealth(); const d = r.data || {}; const c = d.checks || {}
    tools.dbOk = c.database === true || c.database === 'ok'
    tools.wgOk = c.wireguard === true || c.wireguard === 'ok'
    tools.healthDone = true
    flash('tools', (String(d.status).toLowerCase() === 'healthy') ? (tr('settings.healthOk') || 'All systems healthy') : (tr('settings.healthDegraded') || 'Some checks failed'))
  } catch (e) { flash('tools', e.response?.data?.detail || 'Error') } finally { busy.health = false }
}
// Backend /system/check-limits returns { expired_clients, traffic_exceeded_clients, total_disabled, ... }.
async function runLimitCheck() {
  busy.limit = true
  try {
    const r = await systemApi.triggerLimitCheck(); const d = r.data || {}
    tools.expired = d.expired_clients ?? d.expired ?? 0
    tools.exceeded = d.traffic_exceeded_clients ?? d.exceeded ?? 0
    tools.disabled = d.total_disabled ?? d.disabled ?? 0
    flash('limit', tr('settings.limitDone') || 'Check complete')
  } catch (e) { flash('limit', e.response?.data?.detail || 'Error') } finally { busy.limit = false }
}

const newAdmin = reactive({ username: '', password: '' })
const msgAdmTone = ref('ok')
async function createAdmin() { busy.adm = true; msgAdmTone.value = 'ok'; try { await systemApi.createAdmin({ username: newAdmin.username, password: newAdmin.password }); msg.adm = tr('settings.adminCreated') || 'Admin created'; newAdmin.username = ''; newAdmin.password = '' } catch (e) { msgAdmTone.value = 'err'; msg.adm = e.response?.data?.detail || 'Error' } finally { busy.adm = false } }

// ═══════════════ BRANDING ═══════════════
const brand = reactive({ app_name: '', customer_app_name: '', brand_name: '', tagline: '', company_name: '', login_title: '', support_email: '', support_url: '', privacy_url: '', terms_url: '', privacy_text: '', terms_text: '', footer_text: '', powered_by: false, customer_logo_url: '', logo_url: '', favicon_url: '', primary_color: '#6366f1' })
const BRAND_PRESETS = ['#6366f1', '#2563eb', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6']
const brandPresets = computed(() => BRAND_PRESETS.map(hex => {
  const on = (brand.primary_color || '').toLowerCase() === hex
  return { hex, on_selected: on, border: on ? 'var(--text)' : 'transparent', on: () => { brand.primary_color = hex; branding.previewAccent(hex) } }
}))
async function resetBranding() {
  if (!await d2confirm(tr('settings.brandResetConfirm') || 'Reset branding to defaults?')) return
  Object.assign(brand, { app_name: '', customer_app_name: '', brand_name: '', tagline: '', company_name: '', login_title: '', support_email: '', support_url: '', privacy_url: '', terms_url: '', privacy_text: '', terms_text: '', footer_text: '', powered_by: false, primary_color: '#6366f1' })
  flash('brand', tr('common.done') || 'Reset')
}
const logoSlots = computed(() => [
  { key: 'admin', label: tr('settings.adminLogo') || 'Admin logo', url: brand.logo_url, onFile: e => uploadSlot(e, 'admin'), onRemove: () => removeSlot('admin') },
  { key: 'customer', label: tr('settings.customerLogo') || 'Customer logo', url: brand.customer_logo_url, onFile: e => uploadSlot(e, 'customer'), onRemove: () => removeSlot('customer') },
  { key: 'favicon', label: tr('settings.favicon') || 'Favicon', url: brand.favicon_url, onFile: e => uploadSlot(e, 'favicon'), onRemove: () => removeSlot('favicon') },
])
async function loadBranding() { try { const r = await systemApi.getBranding(); const d = r.data; brand.app_name = d.branding_app_name || ''; brand.customer_app_name = d.branding_customer_app_name || ''; brand.brand_name = brand.customer_app_name; brand.tagline = d.branding_tagline || ''; brand.company_name = d.branding_company_name || ''; brand.login_title = d.branding_login_title || ''; brand.support_email = d.branding_support_email || ''; brand.support_url = d.branding_support_url || ''; brand.privacy_url = d.branding_privacy_url || ''; brand.terms_url = d.branding_terms_url || ''; brand.privacy_text = d.branding_privacy_text || ''; brand.terms_text = d.branding_terms_text || ''; brand.footer_text = d.branding_footer_text || ''; brand.powered_by = d.branding_powered_by === true || String(d.branding_powered_by).toLowerCase() === 'true'; brand.customer_logo_url = d.branding_customer_logo_url || ''; brand.logo_url = d.branding_logo_url || ''; brand.favicon_url = d.branding_favicon_url || ''; brand.primary_color = d.branding_primary_color || '#6366f1' } catch (_) {} }
async function saveBranding() { busy.brand = true; try { await systemApi.updateBranding({ branding_app_name: brand.app_name, branding_customer_app_name: brand.brand_name, branding_tagline: brand.tagline, branding_company_name: brand.company_name, branding_login_title: brand.login_title, branding_support_email: brand.support_email, branding_support_url: brand.support_url, branding_privacy_url: brand.privacy_url, branding_terms_url: brand.terms_url, branding_privacy_text: brand.privacy_text, branding_terms_text: brand.terms_text, branding_footer_text: brand.footer_text, branding_powered_by: brand.powered_by, branding_customer_logo_url: brand.customer_logo_url, branding_primary_color: brand.primary_color }); brand.customer_app_name = brand.brand_name; branding.commitAccent(brand.primary_color); flash('brand', tr('common.saved') || 'Saved') } catch (e) { flash('brand', errorText(e)) } finally { busy.brand = false } }
async function uploadSlot(event, slot) {
  const file = event.target.files && event.target.files[0]; if (!file) return
  if (file.size > 1024 * 1024) { flash('brand', tr('settings.fileTooLarge') || 'File too large (max 1MB)'); return }
  try {
    const form = new FormData(); form.append('file', file); let r
    if (slot === 'admin') { r = await systemApi.uploadLogo(form); brand.logo_url = r.data.url; await systemApi.updateBranding({ branding_logo_url: r.data.url }) }
    else if (slot === 'customer') { r = await systemApi.uploadBrandingAsset(form, 'customer_logo'); brand.customer_logo_url = r.data.url; await systemApi.updateBranding({ branding_customer_logo_url: r.data.url }) }
    else { r = await systemApi.uploadLogo(form); brand.favicon_url = r.data.url; await systemApi.updateBranding({ branding_favicon_url: r.data.url }) }
    flash('brand', tr('settings.uploaded') || 'Uploaded')
  } catch (e) { flash('brand', e.response?.data?.detail || 'Error') } finally { event.target.value = '' }
}
async function removeSlot(slot) {
  try {
    if (slot === 'admin') { await systemApi.updateBranding({ branding_logo_url: '' }); brand.logo_url = '' }
    else if (slot === 'customer') { await systemApi.updateBranding({ branding_customer_logo_url: '' }); brand.customer_logo_url = '' }
    else { await systemApi.updateBranding({ branding_favicon_url: '' }); brand.favicon_url = '' }
    flash('brand', tr('common.done') || 'Removed')
  } catch (e) { flash('brand', e.response?.data?.detail || 'Error') }
}

// ═══════════════ DONATE WALLETS ═══════════════
// Donation config — backed by GET/POST /system/donation-wallets. `trc` is our
// TRC-20 field → backend `usdt`. Plus a Paylio card-checkout URL and a `hidden`
// flag (hide the Support button; only effective when licensed — see below).
const donate = reactive({ btc: '', eth: '', ton: '', trc: '', usdc: '', card_url: '', hidden: false })
// "Licensed" unlocks the hide-donate toggle (buying a license already supports us).
const licensed = computed(() => {
  const tier = String(license.tier || license.type || '').toLowerCase()
  return !!(license.lifetime || license.lifetime_protected ||
    (license.days_remaining != null && license.days_remaining > 0) ||
    (tier && !['', 'none', 'free', 'trial', 'unlicensed'].includes(tier)))
})
async function loadDonate() {
  try {
    const d = (await systemApi.getDonationWallets()).data || {}
    donate.btc = d.btc || ''; donate.eth = d.eth || ''; donate.ton = d.ton || ''
    donate.trc = d.usdt || ''; donate.usdc = d.usdc || ''
    donate.card_url = d.card_url || ''; donate.hidden = !!d.hidden
  } catch (_) {}
}
async function saveDonateWallets() {
  try {
    await systemApi.updateDonationWallets({
      btc: donate.btc, eth: donate.eth, ton: donate.ton, usdt: donate.trc, usdc: donate.usdc,
      card_url: donate.card_url, hidden: donate.hidden,
    })
    flash('dn', tr('common.saved') || 'Saved')
  } catch (e) { flash('dn', e.response?.data?.detail || 'Error') }
}

// ═══════════════ UPDATE CHANNEL ═══════════════
const channel = ref('stable')
async function loadChannel() { try { const r = await systemApi.getUpdateChannel(); channel.value = r.data.channel || 'stable' } catch (_) {} }
async function setChannel(ch) { try { const r = await systemApi.setUpdateChannel(ch); channel.value = (r.data && r.data.channel) || ch; flash('ch', tr('settings.channelSet') || ('Channel: ' + channel.value)) } catch (e) { flash('ch', e.response?.data?.detail || 'Error') } }

// ═══════════════ INTERFACE / DESIGN ═══════════════
const currentTheme = computed(() => system.theme)
const themeOptions = computed(() => [
  { key: 'light', label: tr('settings.themeLight') || 'Light', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"></path></svg>' },
  { key: 'dark', label: tr('settings.themeDark') || 'Dark', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"></path></svg>' },
  { key: 'system', label: tr('settings.themeSystem') || 'System', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="3" width="20" height="14" rx="2"></rect><path d="M8 21h8M12 17v4"></path></svg>' },
])
function toggleDesign() { design.set(design.isNew ? 'legacy' : 'new') }

onMounted(() => {
  ui.set({ title: tr('nav.settings') || 'Settings' })
  loadLicense(); loadLicenseServer(); loadPayments(); loadSmtp(); loadNotif(); loadApps(); loadLimits(); loadWebAccess(); loadBranding(); loadChannel(); loadDonate()
})
// Revert any unsaved live-preview accent back to the saved one when leaving Settings.
onUnmounted(() => branding.applyBranding())
</script>

<style scoped>
@media (max-width: 820px) {
  .d2-root-inner > div { grid-template-columns: 1fr !important; }
}
</style>
