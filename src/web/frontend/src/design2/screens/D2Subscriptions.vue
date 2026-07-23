<!-- Subscriptions/Tariffs — his exact table (# / name+tier+badges / prices /
     devices / traffic / bw / active toggle / edit·delete). Wired to tariffsApi.
     Create/edit modal keeps the 4 "?" tooltips + pricing tiers + Popular flag. -->
<template>
  <div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
      <div style="font-size:12.5px;color:var(--text-3)">{{ tariffs.length }} {{ tr('subscriptions.plans') || 'plans' }} · {{ activeCount }} {{ tr('subscriptions.activePlans') || 'active plans' }}</div>
      <button @click="openSimulate" style="margin-left:auto;display:flex;align-items:center;gap:7px;height:34px;padding:0 13px;border:1px solid var(--border-strong);background:var(--panel);color:var(--text-2);border-radius:9px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer" class="d2-simbtn"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"></path></svg>{{ tr('subscriptions.simulatePayment') || 'Simulate payment' }}</button>
    </div>

    <div v-if="loading && !tariffs.length" style="color:var(--text-3);padding:24px;text-align:center">{{ tr('common.loading') || 'Loading…' }}</div>
    <div v-else-if="!tariffs.length" style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:56px 24px;text-align:center">
      <div style="width:54px;height:54px;border-radius:14px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;margin:0 auto 14px"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7h18M3 12h18M3 17h10"></path></svg></div>
      <div style="font-size:15px;font-weight:600">{{ tr('subscriptions.noTariffs') || 'No tariffs yet' }}</div>
      <div style="font-size:13px;color:var(--text-3);margin-top:4px">{{ tr('subscriptions.noTariffsHint') || 'Create your first plan to start selling subscriptions.' }}</div>
    </div>

    <div v-else style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden"><div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left">
          <th class="d2-th" style="padding-left:20px">#</th><th class="d2-th">{{ tr('subscriptions.name') || 'Name' }}</th><th class="d2-th">{{ tr('subscriptions.monthly') || 'Monthly' }}</th><th class="d2-th">{{ tr('subscriptions.quarterly') || 'Quarterly' }}</th><th class="d2-th">{{ tr('subscriptions.yearly') || 'Yearly' }}</th><th class="d2-th">{{ tr('subscriptions.devices') || 'Devices' }}</th><th class="d2-th">{{ tr('subscriptions.trafficLimitGb') || 'Traffic' }}</th><th class="d2-th">{{ tr('subscriptions.bandwidthMbps') || 'Bandwidth' }}</th><th class="d2-th">{{ tr('subscriptions.active') || 'Active' }}</th><th class="d2-th" style="text-align:right;padding-right:20px">{{ tr('common.actions') || 'Actions' }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="(p, i) in tariffs" :key="p.id" style="border-top:1px solid var(--border)">
            <td class="mono" style="padding:12px 16px 12px 20px;color:var(--text-3)">{{ i + 1 }}</td>
            <td style="padding:12px 12px"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="font-weight:600">{{ p.name }}</span><span :style="{ fontSize:'10.5px', fontWeight:600, padding:'2px 7px', borderRadius:'6px', color:tierColor(p.tier), background:tierBg(p.tier) }">{{ p.tier }}</span><span v-if="p.popular" style="font-size:10px;font-weight:600;padding:2px 6px;border-radius:6px;color:var(--accent);background:var(--accent-soft)">★ Popular</span><span v-if="!p.is_visible" style="font-size:10px;font-weight:600;padding:2px 6px;border-radius:6px;color:var(--text-3);background:var(--gray-soft)">Hidden</span><span v-if="p.corp_networks > 0" style="font-size:10px;font-weight:600;padding:2px 6px;border-radius:6px;color:var(--purple);background:var(--purple-soft)">Corp {{ p.corp_networks }}</span></div><div style="font-size:11px;color:var(--text-3);margin-top:2px">{{ p.description }}</div></td>
            <td class="mono" style="padding:12px 12px;font-weight:600">${{ p.price_monthly_usd }}</td>
            <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ p.price_quarterly_usd ? '$' + p.price_quarterly_usd : '—' }}</td>
            <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ p.price_yearly_usd ? '$' + p.price_yearly_usd : '—' }}</td>
            <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ p.max_devices }}</td>
            <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ p.traffic_limit_gb ? p.traffic_limit_gb + ' GB' : '∞' }}</td>
            <td class="mono" style="padding:12px 12px;color:var(--text-2)">{{ p.bandwidth_limit_mbps ? p.bandwidth_limit_mbps + ' Mbps' : '∞' }}</td>
            <td style="padding:12px 12px"><button @click="toggleActive(p)" :style="{ position:'relative', width:'38px', height:'22px', borderRadius:'20px', border:'none', cursor:'pointer', background: p.is_active ? 'var(--accent)' : 'var(--border-strong)' }"><span :style="{ position:'absolute', top:'2px', left: p.is_active ? '18px' : '2px', width:'18px', height:'18px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 2px rgba(0,0,0,.2)' }"></span></button></td>
            <td style="padding:12px 20px"><div style="display:flex;gap:4px;justify-content:flex-end"><button @click="openEdit(p)" class="d2-rowbtn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"></path></svg></button><button @click="removeTariff(p)" class="d2-rowbtn del"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13"></path></svg></button></div></td>
          </tr>
        </tbody>
      </table>
    </div></div>

    <D2Modal :open="showModal" :title="editing ? (tr('subscriptions.editTariff') || 'Edit tariff') : (tr('subscriptions.createTariff') || 'Create tariff')" size="lg" @close="showModal = false">
      <div style="display:flex;flex-direction:column;gap:14px">
        <D2Field v-model="form.name" :label="tr('subscriptions.name') || 'Name'" placeholder="Pro" />
        <div style="display:flex;gap:12px">
          <div style="flex:1"><D2Field v-model="form.tier" :label="tr('subscriptions.tier') || 'Tier slug'" :disabled="!!editing" placeholder="pro" /></div>
          <div style="width:100px"><D2Field v-model="form.display_order" type="number" :label="tr('subscriptions.order') || 'Order'" /></div>
        </div>
        <D2Field v-model="form.description" :label="tr('subscriptions.description') || 'Description'" />

        <div class="d2-grp">{{ tr('subscriptions.groupPricing') || 'Pricing' }}</div>
        <div class="d2-3col"><D2Field v-model="form.price_monthly_usd" type="number" :label="tr('subscriptions.monthly') || 'Monthly'" placeholder="$8" /><D2Field v-model="form.price_quarterly_usd" type="number" :label="tr('subscriptions.quarterly') || 'Quarterly'" placeholder="$21" /><D2Field v-model="form.price_yearly_usd" type="number" :label="tr('subscriptions.yearly') || 'Yearly'" placeholder="$79" /></div>
        <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.pricingTiers') || 'Duration ladder' }}</label><div v-for="(row, i) in form.pricing_tiers" :key="i" style="display:flex;gap:8px;margin-bottom:8px"><input type="number" v-model.number="row.days" :placeholder="tr('subscriptions.ladderDays') || 'days'" class="d2-in" style="width:90px" /><input type="number" v-model.number="row.price_usd" :placeholder="tr('subscriptions.ladderPrice') || '$'" class="d2-in" style="width:90px" /><input type="text" v-model="row.label" :placeholder="tr('subscriptions.ladderLabel') || 'label'" class="d2-in" style="flex:1" /><button @click="form.pricing_tiers.splice(i, 1)" class="d2-rowbtn del"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"></path></svg></button></div><D2Button size="sm" variant="secondary" icon="plus" :disabled="form.pricing_tiers.length >= 12" @click="form.pricing_tiers.push({ days: 60, price_usd: 0, label: '' })">{{ tr('subscriptions.addTier') || 'Add tier' }}</D2Button></div>

        <div class="d2-grp">{{ tr('subscriptions.groupLimits') || 'Limits' }}</div>
        <div class="d2-2col">
          <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.maxDevices') || 'Max devices' }}<D2HelpTip :text="tr('help.maxDevices') || 'Max WireGuard devices per client.'" /></label><input type="number" min="1" class="d2-in" v-model.number="form.max_devices" /></div>
          <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.trafficLimitGb') || 'Traffic (GB)' }}<D2HelpTip :text="tr('help.trafficLimit') || 'Monthly quota, 0 = unlimited.'" /></label><input type="number" min="0" class="d2-in" v-model.number="form.traffic_limit_gb" placeholder="∞" /></div>
        </div>
        <div class="d2-2col">
          <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.bandwidthMbps') || 'Bandwidth (Mbps)' }}<D2HelpTip :text="tr('help.bandwidthLimit') || 'Speed Mbps, 0 = unlimited.'" /></label><input type="number" min="0" class="d2-in" v-model.number="form.bandwidth_limit_mbps" placeholder="∞" /></div>
          <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.corpNetworks') || 'Corporate networks' }}<D2HelpTip :text="tr('help.corpNetworks') || 'Corporate VPN networks (site-to-site).'" /></label><input type="number" min="0" class="d2-in" v-model.number="form.corp_networks" placeholder="0" /></div>
        </div>
        <div class="d2-2col">
          <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.corpSites') || 'Corporate sites' }}</label><input type="number" min="0" class="d2-in" v-model.number="form.corp_sites" placeholder="0" /></div>
        </div>

        <div class="d2-grp">{{ tr('subscriptions.groupVisibility') || 'Visibility' }}</div>
        <div style="display:flex;gap:20px;flex-wrap:wrap"><D2Toggle v-model="form.is_active">{{ tr('subscriptions.active') || 'Active' }}</D2Toggle><D2Toggle v-model="form.is_visible">{{ tr('subscriptions.visible') || 'Visible' }}</D2Toggle><D2Toggle v-model="form.popular">★ {{ tr('subscriptions.markPopular') || 'Popular' }}</D2Toggle></div>
        <div v-if="formError" style="color:var(--red);font-size:13px">{{ formError }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="showModal = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><D2Button :loading="saving" @click="save">{{ tr('common.save') || 'Save' }}</D2Button></template>
    </D2Modal>

    <D2Modal :open="showSimulate" :title="tr('subscriptions.simulatePaymentTitle') || 'Simulate payment'" size="sm" @close="showSimulate = false">
      <div style="display:flex;flex-direction:column;gap:12px">
        <div style="font-size:12.5px;color:var(--text-2);line-height:1.5">{{ tr('subscriptions.simulatePaymentMsg') || 'Manually mark an invoice as paid. For testing only — this activates the subscription as if the payment succeeded.' }}</div>
        <div class="d2-field"><label class="d2-flabel">{{ tr('subscriptions.invoiceId') || 'Invoice ID' }}</label><input v-model="simulateValue" class="d2-in" style="font-family:'JetBrains Mono',monospace" placeholder="inv_…" /></div>
        <div v-if="simulateError" style="color:var(--red);font-size:13px">{{ simulateError }}</div>
      </div>
      <template #footer><D2Button variant="secondary" @click="showSimulate = false">{{ tr('common.cancel') || 'Cancel' }}</D2Button><button class="d2-simcta" :disabled="simulateBusy || !simulateValue" @click="submitSimulate"><span v-if="simulateBusy" class="d2-simcta-spin"></span>{{ tr('subscriptions.simulateCta') || 'Mark as paid' }}</button></template>
    </D2Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { d2confirm } from '../ui/confirm'
import { useI18n } from 'vue-i18n'
import { tariffsApi } from '../../api'
import { useD2Ui } from '../../stores/d2ui'
import D2Modal from '../ui/D2Modal.vue'
import D2Field from '../ui/D2Field.vue'
import D2Toggle from '../ui/D2Toggle.vue'
import D2Button from '../ui/D2Button.vue'
import D2HelpTip from '../ui/D2HelpTip.vue'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const ui = useD2Ui()
const tariffs = ref([]); const loading = ref(false)
const activeCount = computed(() => tariffs.value.filter(p => p.is_active).length)
const TC = { free: ['var(--text-3)', 'var(--gray-soft)'], starter: ['var(--blue)', 'var(--blue-soft)'], pro: ['var(--accent)', 'var(--accent-soft)'], business: ['var(--purple)', 'var(--purple-soft)'], ultimate: ['var(--amber)', 'var(--amber-soft)'], premium: ['var(--accent)', 'var(--accent-soft)'] }
function tierColor(t) { return (TC[String(t || '').toLowerCase()] || TC.free)[0] }
function tierBg(t) { return (TC[String(t || '').toLowerCase()] || TC.free)[1] }

async function load() { loading.value = true; try { const { data } = await tariffsApi.list(); tariffs.value = data } catch (e) { console.error(e) } finally { loading.value = false } }
const showModal = ref(false); const editing = ref(null); const saving = ref(false); const formError = ref('')
function blank() { return { tier: '', name: '', description: '', max_devices: 1, traffic_limit_gb: null, bandwidth_limit_mbps: null, price_monthly_usd: 0, price_quarterly_usd: null, price_yearly_usd: null, pricing_tiers: [], is_active: true, is_visible: true, display_order: 0, corp_networks: 0, corp_sites: 0, popular: false } }
const form = ref(blank())
function openCreate() { editing.value = null; form.value = { ...blank(), display_order: tariffs.value.length }; formError.value = ''; showModal.value = true }
async function openEdit(tf) { editing.value = tf; form.value = { tier: tf.tier, name: tf.name, description: tf.description || '', max_devices: tf.max_devices, traffic_limit_gb: tf.traffic_limit_gb, bandwidth_limit_mbps: tf.bandwidth_limit_mbps, price_monthly_usd: tf.price_monthly_usd, price_quarterly_usd: tf.price_quarterly_usd, price_yearly_usd: tf.price_yearly_usd, pricing_tiers: Array.isArray(tf.pricing_tiers) ? tf.pricing_tiers.map(x => ({ ...x })) : [], is_active: tf.is_active, is_visible: tf.is_visible, display_order: tf.display_order, corp_networks: tf.corp_networks ?? 0, corp_sites: tf.corp_sites ?? 0, popular: !!tf.popular }; formError.value = ''; showModal.value = true }
async function save() { saving.value = true; formError.value = ''; try { const p = { ...form.value }; if (!p.traffic_limit_gb) p.traffic_limit_gb = null; if (!p.bandwidth_limit_mbps) p.bandwidth_limit_mbps = null; if (!p.price_quarterly_usd) p.price_quarterly_usd = null; if (!p.price_yearly_usd) p.price_yearly_usd = null; if (Array.isArray(p.pricing_tiers)) { p.pricing_tiers = p.pricing_tiers.filter(x => x && Number(x.days) > 0).map(x => ({ days: Number(x.days), price_usd: Number(x.price_usd || 0), label: (x.label || '').trim() || null })); if (!p.pricing_tiers.length) p.pricing_tiers = null } if (editing.value) { const { tier, ...upd } = p; await tariffsApi.update(editing.value.id, upd) } else await tariffsApi.create(p); showModal.value = false; await load() } catch (e) { formError.value = e.response?.data?.detail || e.message } finally { saving.value = false } }
async function toggleActive(p) { try { await tariffsApi.update(p.id, { is_active: !p.is_active }); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }
async function removeTariff(p) { if (!await d2confirm(tr('subscriptions.deleteConfirm') || `Delete "${p.name}"?`)) return; try { await tariffsApi.delete(p.id); await load() } catch (e) { alert(e.response?.data?.detail || 'Error') } }

const showSimulate = ref(false); const simulateValue = ref(''); const simulateBusy = ref(false); const simulateError = ref('')
function openSimulate() { simulateValue.value = ''; simulateError.value = ''; showSimulate.value = true }
async function submitSimulate() { if (!simulateValue.value) return; simulateBusy.value = true; simulateError.value = ''; try { await tariffsApi.simulatePayment(simulateValue.value.trim()); showSimulate.value = false } catch (e) { simulateError.value = e.response?.data?.detail || e.message } finally { simulateBusy.value = false } }
onMounted(() => { ui.set({ title: tr('nav.subscriptions') || 'Tariffs', primary: { label: tr('subscriptions.createTariff') || 'Create tariff', onClick: openCreate } }); load() })
</script>

<style scoped>
.mono { font-family: 'JetBrains Mono', monospace; }
.d2-th { padding: 11px 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); text-align: left; }
.d2-rowbtn { width: 30px; height: 30px; border-radius: 7px; border: none; background: transparent; color: var(--text-2); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.d2-rowbtn:hover { background: var(--panel-3); color: var(--text); }
.d2-rowbtn.del:hover { background: var(--red-soft); color: var(--red); }
.d2-field { display: flex; flex-direction: column; gap: 6px; }
.d2-flabel { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: var(--text-2); }
.d2-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.d2-3col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.d2-in { width: 100%; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--border-strong); background: var(--panel); color: var(--text); font: inherit; font-size: 14px; }
.d2-in:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); }
.d2-grp { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--text-3); border-top: 1px solid var(--border); padding-top: 13px; }
.d2-simbtn:hover { background: var(--panel-2) !important; }
.d2-simcta { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 18px; border: none; background: var(--green); color: #fff; border-radius: 10px; font: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer; }
.d2-simcta:disabled { opacity: .55; cursor: not-allowed; }
.d2-simcta-spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; animation: d2spin .6s linear infinite; display: inline-block; }
@keyframes d2spin { to { transform: rotate(360deg); } }
</style>
