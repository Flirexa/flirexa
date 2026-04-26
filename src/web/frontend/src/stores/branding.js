import { defineStore } from 'pinia'
import axios from 'axios'

function isSafeUrl(url) {
  if (!url) return false
  return url.startsWith('/') || url.startsWith('https://') || url.startsWith('http://')
}

function sanitizeText(text, maxLen = 200) {
  if (!text) return ''
  return String(text).slice(0, maxLen)
}

export const useBrandingStore = defineStore('branding', {
  state: () => ({
    appName: 'VPN Management Studio',
    companyName: '',
    logoUrl: '',
    faviconUrl: '',
    loginTitle: 'Admin Panel',
    supportEmail: '',
    supportUrl: '',
    footerText: '',
    loaded: false,
  }),

  actions: {
    async fetchBranding() {
      try {
        const { data } = await axios.get('/api/v1/public/branding')
        this.appName = sanitizeText(data.branding_app_name, 100) || 'VPN Management Studio'
        this.companyName = sanitizeText(data.branding_company_name)
        this.logoUrl = isSafeUrl(data.branding_logo_url) ? data.branding_logo_url : ''
        this.faviconUrl = isSafeUrl(data.branding_favicon_url) ? data.branding_favicon_url : ''
        this.loginTitle = sanitizeText(data.branding_login_title) || 'Admin Panel'
        this.supportEmail = sanitizeText(data.branding_support_email)
        this.supportUrl = isSafeUrl(data.branding_support_url) ? data.branding_support_url : ''
        this.footerText = sanitizeText(data.branding_footer_text, 500)
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
    },
  },
})
