<!-- Design section — his dedicated DESIGN page (handoff 1417-1473): a New/Legacy
     toggle card, two big preview cards, and an amber note. Wired to the real
     design-mode store (useDesignMode). Switching to Legacy reloads the app tree. -->
<template>
  <div style="max-width:760px">
    <div style="background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:22px 24px;margin-bottom:16px">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px">
        <div>
          <div style="font-weight:650;font-size:15px">{{ tr('design.toggleTitle') || 'Interface design' }}</div>
          <div style="font-size:12.5px;color:var(--text-2);margin-top:4px;max-width:420px;line-height:1.5">{{ tr('design.toggleSub') || 'Switch between the new flat interface and the original panel. Your choice is remembered on this device.' }}</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex:none">
          <span style="font-size:12.5px;font-weight:550" :style="{ color: isLegacy ? 'var(--text)' : 'var(--text-3)' }">{{ tr('design.legacy') || 'Legacy' }}</span>
          <button @click="toggle" :title="tr('design.toggleTitle') || 'Interface design'" :style="{ position:'relative', width:'46px', height:'26px', borderRadius:'20px', border:'none', cursor:'pointer', background: isNew ? 'var(--accent)' : 'var(--border-strong)', transition:'background .15s', flex:'none' }"><span :style="{ position:'absolute', top:'3px', left: isNew ? '23px' : '3px', width:'20px', height:'20px', borderRadius:'50%', background:'#fff', transition:'left .15s', boxShadow:'0 1px 3px rgba(0,0,0,.25)' }"></span></button>
          <span style="font-size:12.5px;font-weight:550" :style="{ color: isNew ? 'var(--text)' : 'var(--text-3)' }">{{ tr('design.new') || 'New' }}</span>
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <button @click="pick('new')" :style="{ textAlign:'left', padding:0, border:'2px solid '+(isNew ? 'var(--accent)' : 'var(--border)'), background:'var(--panel)', borderRadius:'14px', cursor:'pointer', font:'inherit', overflow:'hidden', boxShadow:'var(--shadow)' }">
        <div style="height:128px;background:linear-gradient(135deg,var(--accent) 0%,#8b5cf6 100%);position:relative">
          <div style="position:absolute;left:14px;top:14px;width:42px;height:calc(100% - 28px);background:rgba(255,255,255,.16);border-radius:8px"></div>
          <div style="position:absolute;left:66px;right:14px;top:14px;height:18px;background:rgba(255,255,255,.22);border-radius:5px"></div>
          <div style="position:absolute;left:66px;right:14px;top:42px;bottom:14px;background:rgba(255,255,255,.10);border-radius:7px"></div>
        </div>
        <div style="padding:14px 16px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-weight:650;font-size:14px">{{ tr('design.new') || 'New' }}</span>
            <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:#fff;background:var(--accent)">beta</span>
            <span v-if="isNew" style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--green)"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('design.current') || 'Current' }}</span>
          </div>
          <div style="font-size:12.5px;color:var(--text-3);margin-top:6px;line-height:1.5">{{ tr('design.newDesc') || 'Flat, spacious light/dark interface with live charts and a world map.' }}</div>
        </div>
      </button>

      <button @click="pick('legacy')" :style="{ textAlign:'left', padding:0, border:'2px solid '+(isLegacy ? 'var(--accent)' : 'var(--border)'), background:'var(--panel)', borderRadius:'14px', cursor:'pointer', font:'inherit', overflow:'hidden', boxShadow:'var(--shadow)' }">
        <div style="height:128px;background:#e9ecef;position:relative">
          <div style="position:absolute;left:0;top:0;bottom:0;width:54px;background:#343a40"></div>
          <div style="position:absolute;left:0;right:0;top:0;height:26px;background:#0d6efd"></div>
          <div style="position:absolute;left:68px;right:14px;top:38px;height:30px;background:#fff;border:1px solid #ced4da;border-radius:4px"></div>
          <div style="position:absolute;left:68px;right:14px;top:78px;bottom:14px;background:#fff;border:1px solid #ced4da;border-radius:4px"></div>
        </div>
        <div style="padding:14px 16px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-weight:650;font-size:14px">{{ tr('design.legacy') || 'Legacy' }}</span>
            <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:var(--text-2);background:var(--panel-3)">legacy</span>
            <span v-if="isLegacy" style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--green)"><span style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>{{ tr('design.current') || 'Current' }}</span>
          </div>
          <div style="font-size:12.5px;color:var(--text-3);margin-top:6px;line-height:1.5">{{ tr('design.legacyDesc') || 'The original panel design. Everything works exactly as before.' }}</div>
        </div>
      </button>
    </div>

    <div style="margin-top:16px;display:flex;align-items:center;gap:10px;padding:13px 16px;background:var(--amber-soft);border:1px solid var(--amber-soft);border-radius:11px">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="1.8" style="flex:none"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v4M12 16h.01"></path></svg>
      <span style="font-size:12.5px;color:var(--text-2);line-height:1.5">{{ tr('design.note') || 'Switching applies right away and reloads the panel. You can switch back any time from Settings or here.' }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDesignMode } from '../../stores/designMode'
import { useD2Ui } from '../../stores/d2ui'

const { t } = useI18n()
function tr(k) { try { const v = t(k); return v === k ? '' : v } catch (_) { return '' } }
const design = useDesignMode()
const ui = useD2Ui()
const isNew = computed(() => design.mode !== 'legacy')
const isLegacy = computed(() => design.mode === 'legacy')
function pick(mode) { if ((mode === 'legacy') === isLegacy.value) return; design.set(mode) }
function toggle() { design.set(isNew.value ? 'legacy' : 'new') }
onMounted(() => ui.set({ title: tr('nav.design') || 'Design' }))
</script>
