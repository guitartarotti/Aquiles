import { reactive, readonly } from 'vue'

const STORAGE_KEY = 'aquiles.auth.session'

function readStoredSession() {
  if (typeof window === 'undefined') return null
  try {
    const session = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || 'null')
    if (!session?.accessToken || !session?.user?.username) return null
    return session
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY)
    return null
  }
}

const storedSession = readStoredSession()
const state = reactive({
  accessToken: storedSession?.accessToken || null,
  user: storedSession?.user || null,
})

export const authState = readonly(state)

export function getAccessToken() {
  return state.accessToken
}

export function hasAuthSession() {
  return Boolean(state.accessToken && state.user)
}

export function setAuthSession(accessToken, user) {
  const session = { accessToken, user }
  state.accessToken = accessToken
  state.user = user
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearAuthSession() {
  state.accessToken = null
  state.user = null
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(STORAGE_KEY)
  }
}
