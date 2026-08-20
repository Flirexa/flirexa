<!-- Donate modal — 1:1 from the designer's DONATE MODAL (handoff 2314-2385):
     gradient header + heart, a list of the operator's configured crypto wallets
     and a bank-card option, a crypto detail view (QR + address + copy + memo),
     and a card view (amount picker → Paylio checkout link). Wired to
     GET /system/donation-wallets. New-design only (Legacy keeps components/DonateModal). -->
<template>
  <Teleport to="body">
    <Transition name="d2dn">
      <div v-if="modelValue" class="d2dn-scrim d2-root" @click.self="close">
        <div class="d2dn-card">
          <div class="d2dn-head">
            <button v-if="view !== 'list'" class="d2dn-x" style="left:16px;right:auto" @click="back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"></path></svg></button>
            <button class="d2dn-x" @click="close"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>
            <div class="d2dn-heart"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A3.5 3.5 0 0 0 12 5.5 3.5 3.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7z"></path></svg></div>
            <div style="font-weight:680;font-size:19px;letter-spacing:-.02em">{{ heading }}</div>
            <div style="font-size:13.5px;color:var(--text-2);line-height:1.6;margin-top:8px;max-width:330px;margin-left:auto;margin-right:auto">{{ subheading }}</div>
          </div>

          <div style="padding:6px 26px 26px">
            <!-- LIST -->
            <div v-if="view === 'list'" style="display:flex;flex-direction:column;gap:9px">
              <button v-for="m in methods" :key="m.key" class="d2dn-row" @click="select(m)">
                <div class="d2dn-badge" :style="{ background: m.iconBg, color: m.iconColor }">{{ m.short }}</div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:12.5px;font-weight:600">{{ m.label }}</div>
                  <div style="font-size:11.5px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ m.hint }}</div>
                </div>
                <span style="color:var(--text-3);display:flex"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"></path></svg></span>
              </button>
            </div>

            <!-- CRYPTO -->
            <div v-else-if="view === 'crypto'" style="display:flex;flex-direction:column;align-items:center;gap:14px">
              <template v-if="sel.addr">
                <div v-if="qrSrc" style="padding:12px;background:#fff;border:1px solid var(--border);border-radius:14px;line-height:0"><img :src="qrSrc" width="150" height="150" alt="QR" /></div>
                <div style="width:100%">
                  <label style="display:block;font-size:11.5px;font-weight:600;color:var(--text-3);margin-bottom:6px">{{ sel.label }}</label>
                  <div style="display:flex;gap:8px">
                    <div style="flex:1;min-width:0;display:flex;align-items:center;padding:0 12px;height:42px;border:1px solid var(--border-strong);border-radius:10px;background:var(--panel-2);font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ sel.addr }}</div>
                    <button class="d2dn-copy" @click="copyAddr"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg></button>
                  </div>
                </div>
                <div style="width:100%">
                  <label style="display:block;font-size:11.5px;font-weight:600;color:var(--text-3);margin-bottom:6px">{{ tr('donate.comment') || 'Comment (memo / tag)' }}</label>
                  <input v-model="comment" :placeholder="tr('donate.commentPh') || 'e.g. your email or nickname'" class="d2dn-in" />
                  <div style="font-size:11px;color:var(--text-3);margin-top:6px">{{ tr('donate.commentHint') || 'Some networks (TON, XRP) require a memo.' }}</div>
                </div>
                <button class="d2dn-cta" @click="copyAddr"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V5a2 2 0 012-2h10"></path></svg>{{ copied ? (tr('donate.copied') || 'Address copied') : (tr('donate.copyAddr') || 'Copy address') }}</button>
              </template>
              <div v-else style="text-align:center;padding:22px 8px;color:var(--text-3)">
                <div style="width:44px;height:44px;border-radius:12px;background:var(--panel-3);display:flex;align-items:center;justify-content:center;margin:0 auto 12px"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v4M12 16h.01"></path></svg></div>
                <div style="font-size:13px;line-height:1.6">{{ tr('donate.notConfigured') || 'This method isn’t set up yet. Add its address in Settings → Donation wallets.' }}</div>
              </div>
            </div>

            <!-- CARD -->
            <div v-else-if="view === 'card'" style="display:flex;flex-direction:column;gap:14px">
              <div>
                <label style="display:block;font-size:11.5px;font-weight:600;color:var(--text-3);margin-bottom:8px">{{ tr('donate.pickAmount') || 'Choose an amount' }}</label>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
                  <button v-for="a in [20, 50, 100]" :key="a" @click="amount = String(a)" :style="{ height:'46px', border:'1px solid '+(amount===String(a)?'var(--accent)':'var(--border-strong)'), background:(amount===String(a)?'var(--accent-soft)':'var(--panel)'), color:(amount===String(a)?'var(--accent)':'var(--text)'), borderRadius:'11px', font:'inherit', fontSize:'15px', fontWeight:680, cursor:'pointer', fontFamily:'JetBrains Mono, monospace' }">${{ a }}</button>
                </div>
              </div>
              <div>
                <label style="display:block;font-size:11.5px;font-weight:600;color:var(--text-3);margin-bottom:6px">{{ tr('donate.custom') || 'Or a custom amount' }}</label>
                <div style="position:relative">
                  <span style="position:absolute;left:13px;top:50%;transform:translateY(-50%);color:var(--text-3);font-weight:600;font-family:'JetBrains Mono',monospace">$</span>
                  <input v-model="amount" inputmode="numeric" placeholder="20" class="d2dn-in" style="padding-left:26px;font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:600" />
                </div>
                <div style="font-size:11px;margin-top:6px" :style="{ color: amountErr ? 'var(--red)' : 'var(--text-3)' }">{{ amountErr ? (tr('donate.minErr') || 'Minimum amount is $20.') : (tr('donate.minNote') || 'Minimum $20.') }}</div>
              </div>
              <div v-if="!cardUrlSet" style="font-size:11.5px;color:var(--text-3);text-align:center">{{ tr('donate.cardNotConfigured') || 'Card payments aren’t set up yet — add a checkout link in Settings → Donation wallets.' }}</div>
              <button class="d2dn-cta" :disabled="!cardReady" :style="{ opacity: cardReady ? 1 : .55, cursor: cardReady ? 'pointer' : 'not-allowed' }" @click="goCard"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="5" width="20" height="14" rx="2.5"></rect><path d="M2 10h20"></path></svg>{{ tr('donate.cardCta') || 'Continue' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import { systemApi } from '../../api'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n({ useScope: 'global' })
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }

const wallets = ref({})
const view = ref('list')
const sel = ref({})
const comment = ref('')
const amount = ref('')
const copied = ref(false)
const qrSrc = ref('')

// Per-coin badge colours to match his design (BTC amber, ETH grey, TON blue,
// USDT red, USDC blue, card grey).
// His exact per-coin brand colours (iconBg = hex + '22' ≈ 13% alpha).
const COINS = [
  { key: 'btc', label: 'Bitcoin', short: 'BTC', hint: 'BTC', iconBg: '#f7931a22', iconColor: '#f7931a' },
  { key: 'eth', label: 'Ethereum / USDT (ERC-20)', short: 'ETH', hint: 'ERC-20', iconBg: '#62759622', iconColor: '#627596' },
  { key: 'ton', label: 'TON', short: 'TON', hint: 'The Open Network', iconBg: '#0098ea22', iconColor: '#0098ea' },
  { key: 'usdt', label: 'USDT (TRC-20)', short: 'USDT', hint: 'TRC-20', iconBg: '#eb003722', iconColor: '#eb0037' },
  { key: 'usdc', label: 'USDC (ERC-20)', short: 'USDC', hint: 'ERC-20', iconBg: '#2775ca22', iconColor: '#2775ca' },
]
// Always render the full standard method list (all 5 cryptos + card), exactly
// like the designer — the list is NEVER filtered by "configured". A method with
// no address configured still shows in the list; its detail view then explains
// it isn't set up yet (operator configures addresses in Settings → Donation
// wallets). This avoids the collapsed "no methods" state on a fresh panel.
const methods = computed(() => {
  const out = COINS.map(c => ({ ...c, addr: (wallets.value[c.key] || '').trim(), kind: 'crypto' }))
  out.push({ key: 'card', label: tr('donate.card') || 'Bank card', short: '$', hint: tr('donate.cardMin') || 'From $20', kind: 'card', iconBg: 'var(--accent-soft)', iconColor: 'var(--accent)' })
  return out
})
const heading = computed(() => view.value === 'list' ? (tr('donate.title') || 'Support the project') : (view.value === 'card' ? (tr('donate.card') || 'Bank card') : sel.value.label))
const subheading = computed(() => view.value === 'list'
  ? (tr('donate.sub') || 'The panel grows thanks to your support. Any donation helps ship updates faster.')
  : (view.value === 'card' ? '' : (tr('donate.cryptoSub') || 'Scan the QR or copy the wallet address.')))
const amountErr = computed(() => amount.value !== '' && Number(amount.value) < 20)
const cardUrlSet = computed(() => !!(wallets.value.card_url || '').trim())
const cardReady = computed(() => Number(amount.value) >= 20 && cardUrlSet.value)

async function load() { try { wallets.value = (await systemApi.getDonationWallets()).data || {} } catch (_) { wallets.value = {} } }
watch(() => props.modelValue, (open) => { if (open) { view.value = 'list'; sel.value = {}; comment.value = ''; amount.value = ''; copied.value = false; qrSrc.value = ''; load() } })

async function select(m) {
  if (m.kind === 'card') { view.value = 'card'; return }
  sel.value = m; view.value = 'crypto'; copied.value = false; qrSrc.value = ''
  if (m.addr) { try { qrSrc.value = await QRCode.toDataURL(m.addr, { margin: 1, width: 300 }) } catch (_) {} }
}
function back() { view.value = 'list' }
function close() { emit('update:modelValue', false) }
function copyAddr() { try { navigator.clipboard.writeText(sel.value.addr); copied.value = true; setTimeout(() => (copied.value = false), 1800) } catch (_) {} }
function goCard() {
  const url = (wallets.value.card_url || '').trim()
  if (!url || !cardReady.value) return
  const sep = url.includes('?') ? '&' : '?'
  window.open(url + sep + 'amount=' + encodeURIComponent(amount.value), '_blank', 'noopener')
  close()
}
</script>

<style scoped>
.d2dn-scrim { position: fixed; inset: 0; z-index: 1300; background: rgba(10, 11, 14, .5); display: flex; align-items: center; justify-content: center; padding: 24px; }
.d2dn-card { width: 440px; max-width: 100%; max-height: 90vh; overflow-y: auto; background: var(--panel); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow-lg); }
.d2dn-head { position: relative; padding: 30px 26px 22px; text-align: center; background: linear-gradient(160deg, var(--accent-soft), transparent); }
.d2dn-x { position: absolute; top: 16px; right: 16px; width: 30px; height: 30px; border: none; background: transparent; color: var(--text-3); cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 8px; }
.d2dn-x:hover { background: var(--panel-3); color: var(--text); }
.d2dn-heart { width: 58px; height: 58px; border-radius: 16px; background: var(--accent); color: #fff; display: flex; align-items: center; justify-content: center; margin: 0 auto 14px; box-shadow: 0 8px 22px var(--accent-ring); }
.d2dn-row { display: flex; align-items: center; gap: 13px; padding: 13px 15px; border: 1px solid var(--border); border-radius: 12px; background: var(--panel-2); cursor: pointer; font: inherit; text-align: left; width: 100%; }
.d2dn-row:hover { border-color: var(--accent); background: var(--accent-soft); }
.d2dn-badge { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex: none; font-weight: 700; font-size: 12px; }
.d2dn-copy { width: 42px; height: 42px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; flex: none; }
.d2dn-copy:hover { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
.d2dn-in { width: 100%; height: 42px; border: 1px solid var(--border-strong); background: var(--panel-2); color: var(--text); border-radius: 10px; padding: 0 13px; font: inherit; font-size: 13px; outline: none; }
.d2dn-in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); background: var(--panel); }
.d2dn-cta { width: 100%; height: 44px; border: none; background: var(--accent); color: #fff; border-radius: 11px; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
.d2dn-cta:hover:not(:disabled) { background: var(--accent-2); }
.d2dn-enter-active, .d2dn-leave-active { transition: opacity .15s ease; }         /* overlayIn */
.d2dn-enter-from, .d2dn-leave-to { opacity: 0; }
.d2dn-enter-active .d2dn-card { transition: transform .2s cubic-bezier(.4,0,.2,1), opacity .2s; }  /* modalIn */
.d2dn-enter-from .d2dn-card, .d2dn-leave-to .d2dn-card { opacity: 0; transform: translateY(8px) scale(.98); }
</style>
