import type { StateCreator } from 'zustand'

import {
  authGoogle,
  authLogin,
  authLogout,
  authMe,
  authRefreshToken,
  authRegister,
  authTelegram,
  setAccessToken,
  setRefreshHandler,
  type AuthUser,
  type TelegramAuthPayload,
  type TokenPair,
} from '@/api'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

import type { RadarState } from './types'

/** 'unknown' = before the boot refresh resolves (avoids a login-button flash
 * for an already-signed-in user); then 'anon' or 'authed'. */
export type AuthStatus = 'unknown' | 'anon' | 'authed'

export interface AuthSlice {
  user: AuthUser | null
  authStatus: AuthStatus
  isAdmin: () => boolean
  register: (email: string, password: string, displayName?: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: (credential: string) => Promise<void>
  loginWithTelegram: (payload: TelegramAuthPayload) => Promise<void>
  logout: () => void
  /** Restore a session from the stored refresh token (called once on boot). */
  refreshSession: () => Promise<void>
}

export const createAuthSlice: StateCreator<RadarState, [], [], AuthSlice> = (set, get) => {
  const applyTokens = (res: TokenPair) => {
    setAccessToken(res.access)
    safeSet(STORAGE_KEYS.authRefresh, res.refresh)
    set({ user: res.user, authStatus: 'authed' })
  }

  const clearSession = () => {
    setAccessToken(null)
    safeRemove(STORAGE_KEYS.authRefresh)
    set({ user: null, authStatus: 'anon' })
  }

  // Registered once with api.ts: on a 401, mint a fresh access token from the
  // stored refresh token (or wipe the session if the refresh token is dead).
  setRefreshHandler(async () => {
    const refresh = safeGet(STORAGE_KEYS.authRefresh)
    if (!refresh) return null
    try {
      const { access } = await authRefreshToken(refresh)
      setAccessToken(access)
      return access
    } catch {
      clearSession()
      return null
    }
  })

  return {
    user: null,
    authStatus: 'unknown',

    isAdmin: () => get().user?.role === 'admin',

    register: async (email, password, displayName) => {
      applyTokens(await authRegister(email, password, displayName))
    },

    login: async (email, password) => {
      applyTokens(await authLogin(email, password))
    },

    loginWithGoogle: async (credential) => {
      applyTokens(await authGoogle(credential))
    },

    loginWithTelegram: async (payload) => {
      applyTokens(await authTelegram(payload))
    },

    logout: () => {
      clearSession()
      void authLogout().catch(() => {})
    },

    refreshSession: async () => {
      const refresh = safeGet(STORAGE_KEYS.authRefresh)
      if (!refresh) {
        set({ authStatus: 'anon' })
        return
      }
      try {
        const { access } = await authRefreshToken(refresh)
        setAccessToken(access)
        set({ user: await authMe(), authStatus: 'authed' })
      } catch {
        clearSession()
      }
    },
  }
}
