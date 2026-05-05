import { ref, watch, onMounted, onUnmounted, isRef, unref } from 'vue'

/**
 * Auto-refresh a callback at a configurable interval.
 *
 * - Pauses while the tab is hidden so we don't waste agent CPU.
 * - `intervalMs` may be a plain number OR a ref — when it's a ref and the
 *   user picks a new interval at runtime, the timer restarts seamlessly.
 * - Pass `intervalMs = 0` (or set the ref to 0) to disable polling without
 *   tearing the composable down — useful for an "Off" option in a UI picker.
 *
 * Usage:
 *   const interval = ref(15_000)
 *   const { isLive, refreshNow } = useLivePoll(fetchClients, interval)
 *   // later: interval.value = 5000  // picker switched to 5s
 *   // or:    interval.value = 0     // picker switched to Off
 */
export function useLivePoll(callback, intervalMs = 15_000, options = {}) {
  const { runImmediately = false, pauseWhenHidden = true } = options
  const intervalRef = isRef(intervalMs) ? intervalMs : ref(intervalMs)
  const isLive = ref(false)
  let timer = null

  const tick = async () => {
    if (pauseWhenHidden && document.visibilityState !== 'visible') return
    try { await callback() } catch (e) { console.warn('[livePoll] callback failed:', e) }
  }

  const start = () => {
    stop()
    const ms = unref(intervalRef)
    if (!ms || ms <= 0) {
      isLive.value = false
      return
    }
    timer = setInterval(tick, ms)
    // Live indicator should reflect the current document-visibility too —
    // a tab in the background isn't actually polling, so don't lie about it.
    isLive.value = !pauseWhenHidden || document.visibilityState === 'visible'
  }

  const stop = () => {
    if (timer) { clearInterval(timer); timer = null }
    isLive.value = false
  }

  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') start()
    else if (pauseWhenHidden) stop()
  }

  // React to runtime interval changes (picker)
  watch(intervalRef, () => start())

  onMounted(() => {
    if (runImmediately) tick()
    start()
    if (pauseWhenHidden) document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    isLive,
    interval: intervalRef,
    refreshNow: tick,
  }
}

/**
 * Persist a numeric interval (in ms) under a localStorage key. Returns a ref
 * that auto-syncs both directions. Bad/missing keys fall back to `defaultMs`.
 */
export function usePersistedInterval(storageKey, defaultMs = 15_000) {
  let initial = defaultMs
  try {
    const raw = localStorage.getItem(storageKey)
    const parsed = raw === null ? null : Number(raw)
    if (Number.isFinite(parsed) && parsed >= 0) initial = parsed
  } catch (_) { /* sandboxed iframe / private mode — ignore */ }

  const r = ref(initial)
  watch(r, (v) => {
    try { localStorage.setItem(storageKey, String(v)) } catch (_) {}
  })
  return r
}
