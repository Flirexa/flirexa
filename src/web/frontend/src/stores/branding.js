import { defineStore } from 'pinia'
import axios from 'axios'

function isSafeUrl(url) {
  if (!url) return false
  return url.startsWith('/') || url.startsWith('https://') || url.startsWith('http://') || url.startsWith('data:image/')
}

function sanitizeText(text, maxLen = 200) {
  if (!text) return ''
  return String(text).slice(0, maxLen)
}

// ── Runtime accent (white-label) — designer's applyBrandAccent. Overrides the
// accent tokens on :root by injecting a <style id="wl-accent">, so the WHOLE
// panel re-skins at once (no per-element edits). Used on load, on save, and for
// the live preview while the operator picks a colour. ──────────────────────────
function hexToRgb(h) {
  h = (h || '').replace('#', '')
  if (h.length === 3) h = h.split('').map(c => c + c).join('')
  const n = parseInt(h || '6366f1', 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
function shade(h, p) {
  const [r, g, b] = hexToRgb(h)
  const f = v => Math.max(0, Math.min(255, Math.round(v + (p < 0 ? v : 255 - v) * p)))
  return '#' + [f(r), f(g), f(b)].map(v => v.toString(16).padStart(2, '0')).join('')
}
export function applyBrandAccent(hex) {
  if (!hex || !/^#?[0-9a-fA-F]{3,6}$/.test(hex)) { removeBrandAccent(); return }
  if (hex[0] !== '#') hex = '#' + hex
  const [r, g, b] = hexToRgb(hex)
  const a2 = shade(hex, -0.18)
  const ring = `rgba(${r},${g},${b},0.28)`
  // The design2 tokens (--accent etc.) are defined ON `.d2-root` and
  // `[data-theme="dark"] .d2-root` (tokens.css) — NOT on :root. A `:root`
  // override is shadowed by `.d2-root`'s own declaration for everything inside
  // the panel, so it never took effect (colors didn't switch). Override the SAME
  // selectors (equal specificity → later source order wins), with theme-correct
  // soft alphas. Also cover `:root` for any non-d2 surface (e.g. login shell).
  const block = (softA) => `--accent:${hex};--accent-2:${a2};--accent-soft:rgba(${r},${g},${b},${softA});--accent-ring:${ring}`
  const css =
    `:root,.d2-root{${block(0.10)}}` +
    `[data-theme="dark"] .d2-root,[data-theme="dark"]:root{${block(0.16)}}`
  let el = document.getElementById('wl-accent')
  if (!el) { el = document.createElement('style'); el.id = 'wl-accent'; document.head.appendChild(el) }
  el.textContent = css
}
export function removeBrandAccent() {
  const el = document.getElementById('wl-accent')
  if (el) el.remove()
}

export const useBrandingStore = defineStore('branding', {
  state: () => ({
    appName: 'Flirexa',
    companyName: '',
    logoUrl: '',
    faviconUrl: '',
    loginTitle: 'Admin Panel',
    supportEmail: '',
    supportUrl: '',
    footerText: '',
    primaryColor: '',
    loaded: false,
  }),

  actions: {
    async fetchBranding() {
      try {
        const { data } = await axios.get('/api/v1/public/branding')
        this.appName = sanitizeText(data.branding_app_name, 100) || 'Flirexa'
        this.companyName = sanitizeText(data.branding_company_name)
        this.logoUrl = isSafeUrl(data.branding_logo_url) ? data.branding_logo_url : ''
        this.faviconUrl = isSafeUrl(data.branding_favicon_url) ? data.branding_favicon_url : ''
        this.loginTitle = sanitizeText(data.branding_login_title) || 'Admin Panel'
        this.supportEmail = sanitizeText(data.branding_support_email)
        this.supportUrl = isSafeUrl(data.branding_support_url) ? data.branding_support_url : ''
        this.footerText = sanitizeText(data.branding_footer_text, 500)
        this.primaryColor = /^#[0-9a-fA-F]{3,8}$/.test(data.branding_primary_color || '') ? data.branding_primary_color : ''
        this.loaded = true
        this.applyBranding()
      } catch (err) {
        console.warn('Failed to load branding:', err.message)
        this.loaded = true
      }
    },

    applyBranding() {
      document.title = this.appName

      if (this.faviconUrl) {
        let link = document.querySelector("link[rel~='icon']")
        if (!link) {
          link = document.createElement('link')
          link.rel = 'icon'
          document.head.appendChild(link)
        }
        link.href = this.faviconUrl
      }

      // White-label accent — re-skin the whole panel from the operator's colour.
      if (this.primaryColor) applyBrandAccent(this.primaryColor)
      else removeBrandAccent()
    },

    // Live preview while picking a colour in Settings — visual only, does NOT
    // change stored state, so leaving without saving can revert via applyBranding().
    previewAccent(hex) { if (hex && /^#?[0-9a-fA-F]{3,6}$/.test(hex)) applyBrandAccent(hex); else this.applyBranding() },
    // Commit a saved colour to the store + apply.
    commitAccent(hex) { this.primaryColor = /^#[0-9a-fA-F]{3,8}$/.test(hex || '') ? hex : ''; this.applyBranding() },
  },
})
