// Customer-facing branding comes from the public branding payload. Keep URL
// and colour handling in one place so every portal surface applies the same
// validation and palette.
export function brandingUrl(key) {
  const value = String(window.__branding?.[key] || '').trim()
  if (!value) return ''
  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return value
  try {
    const parsed = new URL(value)
    return ['http:', 'https:'].includes(parsed.protocol) ? value : ''
  } catch {
    return ''
  }
}

export function legalDocumentHref(kind) {
  if (!['privacy', 'terms'].includes(kind)) return ''
  const externalOrCustom = brandingUrl(`branding_${kind}_url`)
  if (externalOrCustom) return externalOrCustom
  const body = String(window.__branding?.[`branding_${kind}_text`] || '').trim()
  return body ? `/legal/${kind}` : ''
}

export function isExternalHref(value) {
  return /^https?:\/\//i.test(String(value || ''))
}

const PORTAL_ACCENT_VARIABLES = [
  '--accent-50', '--accent-100', '--accent-200', '--accent-300',
  '--accent-400', '--accent-500', '--accent-600', '--accent-700',
  '--accent-800', '--accent-900', '--accent', '--accent-2',
  '--accent-soft', '--accent-ring', '--accent-fg',
  '--vxy-primary', '--vxy-primary-dark', '--vxy-primary-light',
  '--vxy-input-focus', '--vxy-hover-bg', '--bs-primary',
  '--bs-primary-rgb', '--bs-link-color', '--bs-link-hover-color',
]

function normalizeHex(value) {
  const match = String(value || '').trim().match(/^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/)
  if (!match) return ''
  let hex = match[1].toLowerCase()
  if (hex.length === 3) hex = hex.split('').map(char => char + char).join('')
  return `#${hex}`
}

function hexToRgb(hex) {
  const value = Number.parseInt(hex.slice(1), 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

function shade(hex, amount) {
  const rgb = hexToRgb(hex)
  const channel = value => Math.max(0, Math.min(255, Math.round(
    value + (amount < 0 ? value : 255 - value) * amount,
  )))
  return `#${rgb.map(value => channel(value).toString(16).padStart(2, '0')).join('')}`
}

export function portalBrandPalette(value) {
  const accent = normalizeHex(value)
  if (!accent) return null
  const [r, g, b] = hexToRgb(accent)
  const rgb = `${r}, ${g}, ${b}`
  const dark = shade(accent, -0.18)
  // Keep controls readable even when an operator chooses a very light colour.
  const foreground = ((r * 299 + g * 587 + b * 114) / 1000) >= 165 ? '#111827' : '#ffffff'
  return {
    '--accent-50': shade(accent, 0.94),
    '--accent-100': shade(accent, 0.86),
    '--accent-200': shade(accent, 0.72),
    '--accent-300': shade(accent, 0.52),
    '--accent-400': shade(accent, 0.28),
    '--accent-500': shade(accent, 0.10),
    '--accent-600': accent,
    '--accent-700': dark,
    '--accent-800': shade(accent, -0.32),
    '--accent-900': shade(accent, -0.48),
    '--accent': accent,
    '--accent-2': dark,
    '--accent-soft': `rgba(${rgb}, 0.14)`,
    '--accent-ring': `rgba(${rgb}, 0.28)`,
    '--accent-fg': foreground,
    // Compatibility tokens are still used by payment/corporate screens.
    '--vxy-primary': accent,
    '--vxy-primary-dark': dark,
    '--vxy-primary-light': `rgba(${rgb}, 0.12)`,
    '--vxy-input-focus': `rgba(${rgb}, 0.25)`,
    '--vxy-hover-bg': `rgba(${rgb}, 0.10)`,
    '--bs-primary': accent,
    '--bs-primary-rgb': rgb,
    '--bs-link-color': accent,
    '--bs-link-hover-color': dark,
  }
}

export function applyPortalBranding(branding = null) {
  if (typeof document === 'undefined') return false
  const data = branding || (typeof window !== 'undefined' ? window.__branding : {}) || {}
  const root = document.documentElement
  const palette = portalBrandPalette(data.branding_primary_color)
  if (!palette) {
    PORTAL_ACCENT_VARIABLES.forEach(name => root.style.removeProperty(name))
    return false
  }
  Object.entries(palette).forEach(([name, value]) => root.style.setProperty(name, value))
  return true
}

let portalManifestObjectUrl = ''

function absoluteAssetUrl(value, fallback) {
  const candidate = String(value || fallback || '').trim()
  if (!candidate || typeof window === 'undefined') return ''
  try {
    return new URL(candidate, window.location.origin).href
  } catch {
    return ''
  }
}

// Keep browser/PWA chrome in the same white-label boundary as the rendered
// portal. A static manifest would otherwise expose the platform brand even
// after an Enterprise operator replaced the portal name, logo and favicon.
export function applyPortalDocumentBranding(branding = null) {
  if (typeof document === 'undefined' || typeof window === 'undefined') return
  const data = branding || window.__branding || {}
  const poweredBy = data.branding_powered_by === undefined
    || data.branding_powered_by === true
    || String(data.branding_powered_by).toLowerCase() === 'true'
  const name = String(data.branding_customer_app_name || '').trim()
    || (poweredBy ? String(data.branding_app_name || 'Flirexa').trim() : '')
    || 'VPN Portal'
  const accent = normalizeHex(data.branding_primary_color) || '#5865f2'
  const icon = absoluteAssetUrl(
    data.branding_favicon_url
      || data.branding_customer_logo_url
      || data.branding_logo_url,
    '/flirexa-logo.png',
  )

  document.title = name

  let favicon = document.querySelector("link[rel~='icon']")
  if (!favicon) {
    favicon = document.createElement('link')
    favicon.rel = 'icon'
    document.head.appendChild(favicon)
  }
  favicon.href = icon

  let appleIcon = document.querySelector("link[rel='apple-touch-icon']")
  if (!appleIcon) {
    appleIcon = document.createElement('link')
    appleIcon.rel = 'apple-touch-icon'
    document.head.appendChild(appleIcon)
  }
  appleIcon.href = icon

  const appleTitle = document.querySelector("meta[name='apple-mobile-web-app-title']")
  if (appleTitle) appleTitle.content = name
  const theme = document.querySelector("meta[name='theme-color']")
  if (theme) theme.content = accent

  const manifestLink = document.querySelector("link[rel='manifest']")
  if (!manifestLink || typeof Blob === 'undefined' || !window.URL?.createObjectURL) return
  const manifest = {
    name,
    short_name: name.slice(0, 30),
    description: `${name} VPN portal`,
    start_url: '/',
    display: 'standalone',
    background_color: '#2b2d31',
    theme_color: accent,
    orientation: 'any',
    icons: icon ? [{ src: icon, sizes: 'any', purpose: 'any maskable' }] : [],
  }
  const nextUrl = window.URL.createObjectURL(new Blob(
    [JSON.stringify(manifest)],
    { type: 'application/manifest+json' },
  ))
  manifestLink.href = nextUrl
  if (portalManifestObjectUrl) window.URL.revokeObjectURL(portalManifestObjectUrl)
  portalManifestObjectUrl = nextUrl
}
