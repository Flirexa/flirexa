import { watch, onUnmounted } from 'vue'

/**
 * Wires the Escape key to close a modal-state ref.
 *
 * Usage in a component:
 *   const showModal = ref(false)
 *   useEscapeClose(showModal)
 *
 * Or with a custom handler (the handler runs only when the ref is true):
 *   useEscapeClose(showModal, () => cancelDeleteConfirm())
 *
 * The listener is only attached while the ref is truthy — keeps the
 * global keydown traffic minimal and avoids stacking handlers when
 * many modals coexist in one view.
 */
export function useEscapeClose(openRef, handler) {
  const onKey = (e) => {
    if (e.key !== 'Escape') return
    if (handler) handler()
    else openRef.value = false
  }
  let attached = false
  const stop = watch(openRef, (open) => {
    if (open && !attached) {
      window.addEventListener('keydown', onKey)
      attached = true
    } else if (!open && attached) {
      window.removeEventListener('keydown', onKey)
      attached = false
    }
  }, { immediate: true })
  onUnmounted(() => {
    stop()
    if (attached) {
      window.removeEventListener('keydown', onKey)
      attached = false
    }
  })
}
