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
