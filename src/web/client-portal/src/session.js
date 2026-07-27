import { reactive } from 'vue'
import { portalApi } from './api'

export const portalSession = reactive({
  user: null,
  checked: false,
})

let checkPromise = null

export function setPortalUser(user) {
  portalSession.user = user || null
  portalSession.checked = true
}

export function clearPortalSession() {
  portalSession.user = null
  portalSession.checked = true
}

export async function ensurePortalSession({ force = false } = {}) {
  if (portalSession.checked && !force) return !!portalSession.user
  if (!checkPromise) {
    checkPromise = portalApi.getMe()
      .then(({ data }) => {
        setPortalUser(data)
        return true
      })
      .catch(() => {
        clearPortalSession()
        return false
      })
      .finally(() => {
        checkPromise = null
      })
  }
  return checkPromise
}

if (typeof window !== 'undefined') {
  window.addEventListener('fx:auth-expired', clearPortalSession)
}
