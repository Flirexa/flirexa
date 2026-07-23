// In-app confirmation for the redesign — replaces native window.confirm().
//
// Why this exists: native confirm() is silently suppressed once a browser tab
// has "prevent this page from creating additional dialogs" set (Chrome/Firefox
// offer that checkbox after a page shows a few dialogs). When suppressed,
// confirm() returns false with no prompt, so every action guarded by
// `if (!confirm(...)) return` becomes a dead button — exactly what happened to
// the Updates "Install" button on a heavily-used panel while the legacy UI
// (which uses an in-app modal) kept working. This helper is a Promise-based
// drop-in: `if (!(await d2confirm(msg))) return`.
import { reactive } from 'vue'

export const confirmState = reactive({
  open: false,
  message: '',
  confirmLabel: '',
  cancelLabel: '',
  danger: false,
  _resolve: null,
})

export function d2confirm(message, opts = {}) {
  // If a previous prompt is somehow still open, resolve it false first so we
  // never leak a dangling promise.
  if (confirmState._resolve) {
    try { confirmState._resolve(false) } catch (_) { /* ignore */ }
  }
  return new Promise((resolve) => {
    confirmState.message = String(message == null ? '' : message)
    confirmState.confirmLabel = opts.confirmLabel || ''
    confirmState.cancelLabel = opts.cancelLabel || ''
    confirmState.danger = !!opts.danger
    confirmState.open = true
    confirmState._resolve = resolve
  })
}

export function resolveConfirm(value) {
  const r = confirmState._resolve
  confirmState.open = false
  confirmState._resolve = null
  if (r) r(!!value)
}
