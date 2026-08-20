// Shared utility functions for client portal

export function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString()
}

export function formatDateTime(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function messageFrom(value) {
  if (typeof value === 'string') return value.trim()
  if (Array.isArray(value)) {
    return value.map(messageFrom).filter(Boolean).join('. ')
  }
  if (!value || typeof value !== 'object') return ''
  for (const key of ['message', 'msg', 'detail', 'error']) {
    const message = messageFrom(value[key])
    if (message) return message
  }
  return ''
}

// FastAPI may return a string, a validation-error array, or a structured
// entitlement/error object in `detail`. Never interpolate the raw value into
// the UI: doing so produces the customer-visible "[object Object]" message.
export function apiErrorMessage(error, fallback = 'Error') {
  return messageFrom(error?.response?.data?.detail)
    || messageFrom(error?.response?.data?.message)
    || messageFrom(error?.message)
    || fallback
}

// Clipboard.writeText is unavailable on some HTTP/self-signed deployments.
// Keep every Copy button useful by falling back to a temporary textarea.
export async function copyText(text) {
  const value = String(text ?? '')
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch { /* fall through to the DOM fallback */ }
  }
  if (typeof document === 'undefined') return false
  const input = document.createElement('textarea')
  input.value = value
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.opacity = '0'
  document.body.appendChild(input)
  input.select()
  let copied = false
  try { copied = document.execCommand('copy') } catch { copied = false }
  input.remove()
  return copied
}

export function safePortalPath(value, fallback = '/') {
  if (typeof value !== 'string') return fallback
  const path = value.trim()
  return path.startsWith('/') && !path.startsWith('//') && !path.includes('\\')
    ? path
    : fallback
}

// Server locations are intentionally free-form because operators often use
// labels such as "Paris AWG" or "Amsterdam 3".  Keep flag rendering
// deterministic and local (no geo-IP/CDN dependency) by recognising both
// country names and the common city names used for VPN locations. Unknown
// labels fall back to the neutral globe icon in CountryFlag.vue.
const COUNTRY_LOCATION_HINTS = Object.freeze({
  us: ['united states', 'usa', 'u.s.', 'new york', 'los angeles', 'chicago', 'miami', 'dallas', 'seattle', 'atlanta', 'san francisco', 'washington'],
  ca: ['canada', 'toronto', 'montreal', 'vancouver', 'calgary'],
  gb: ['united kingdom', 'great britain', 'england', 'london', 'manchester'],
  nl: ['netherlands', 'holland', 'amsterdam', 'rotterdam'],
  de: ['germany', 'deutschland', 'frankfurt', 'berlin', 'munich', 'nuremberg', 'dusseldorf'],
  fr: ['france', 'paris', 'marseille'],
  pl: ['poland', 'polska', 'warsaw', 'warszawa', 'krakow'],
  es: ['spain', 'espana', 'madrid', 'barcelona'],
  it: ['italy', 'italia', 'milan', 'milano', 'rome', 'roma'],
  pt: ['portugal', 'lisbon', 'lisboa'],
  ch: ['switzerland', 'zurich', 'geneva'],
  at: ['austria', 'vienna', 'wien'],
  se: ['sweden', 'stockholm'],
  no: ['norway', 'oslo'],
  fi: ['finland', 'helsinki'],
  dk: ['denmark', 'copenhagen'],
  be: ['belgium', 'brussels'],
  ie: ['ireland', 'dublin'],
  cz: ['czechia', 'czech republic', 'prague', 'praha'],
  ro: ['romania', 'bucharest'],
  bg: ['bulgaria', 'sofia'],
  gr: ['greece', 'athens'],
  tr: ['turkey', 'turkiye', 'istanbul', 'ankara'],
  ua: ['ukraine', 'kyiv', 'kiev'],
  ru: ['russia', 'moscow', 'saint petersburg', 'st petersburg'],
  ee: ['estonia', 'tallinn'],
  lv: ['latvia', 'riga'],
  lt: ['lithuania', 'vilnius'],
  is: ['iceland', 'reykjavik'],
  lu: ['luxembourg'],
  md: ['moldova', 'chisinau'],
  rs: ['serbia', 'belgrade'],
  hr: ['croatia', 'zagreb'],
  hu: ['hungary', 'budapest'],
  sk: ['slovakia', 'bratislava'],
  si: ['slovenia', 'ljubljana'],
  jp: ['japan', 'tokyo', 'osaka'],
  sg: ['singapore'],
  hk: ['hong kong'],
  in: ['india', 'mumbai', 'delhi', 'bangalore', 'bengaluru'],
  id: ['indonesia', 'jakarta'],
  my: ['malaysia', 'kuala lumpur'],
  th: ['thailand', 'bangkok'],
  vn: ['vietnam', 'hanoi', 'ho chi minh'],
  ph: ['philippines', 'manila'],
  kr: ['south korea', 'seoul'],
  tw: ['taiwan', 'taipei'],
  au: ['australia', 'sydney', 'melbourne', 'brisbane', 'perth'],
  nz: ['new zealand', 'auckland'],
  ae: ['united arab emirates', 'uae', 'dubai', 'abu dhabi'],
  il: ['israel', 'tel aviv'],
  za: ['south africa', 'johannesburg', 'cape town'],
  br: ['brazil', 'sao paulo', 'rio de janeiro'],
  ar: ['argentina', 'buenos aires'],
  mx: ['mexico', 'mexico city'],
  cl: ['chile', 'santiago'],
})

const normaliseLocation = value => String(value || '')
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[_/|]+/g, ' ')
  .replace(/[^a-z0-9. -]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

export function countryCodeFromLocation(...values) {
  const text = normaliseLocation(values.filter(Boolean).join(' '))
  if (!text) return ''

  // Explicit ISO suffixes are useful for operator labels like "edge-de".
  const suffix = text.match(/(?:^|[ ,(-])([a-z]{2})(?:$|[ )-])/g)
  if (suffix) {
    for (const match of suffix.reverse()) {
      const code = match.match(/[a-z]{2}/)?.[0]
      if (code && Object.hasOwn(COUNTRY_LOCATION_HINTS, code)) return code.toUpperCase()
    }
  }

  for (const [code, hints] of Object.entries(COUNTRY_LOCATION_HINTS)) {
    if (hints.some(hint => new RegExp(`(?:^|[^a-z])${hint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:$|[^a-z])`).test(text))) {
      return code.toUpperCase()
    }
  }
  return ''
}

export function countryFlagEmoji(code) {
  const value = String(code || '').trim().toUpperCase()
  if (!/^[A-Z]{2}$/.test(value)) return ''
  return String.fromCodePoint(...[...value].map(char => 127397 + char.charCodeAt(0)))
}
