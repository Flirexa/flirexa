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
