import type { StateCreator } from 'zustand'

import {
  ApiError,
  authGoogle,
  authLogin,
  authLogout,
  authMe,
  patchMe,
  authRefreshToken,
  authRegister,
  authTelegram,
  isAdminRole,
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
  /** Edit your own profile. Fields left out are untouched; an explicit null
   * clears one (an avatar of null falls back to the monogram). The avatar
   * travels inline as a data: URL — see lib/avatarImage.ts and backend
   * app/auth/avatar.py. */
  updateProfile: (patch: { display_name?: string | null; avatar_url?: string | null }) =>
    Promise<void>
}

export const createAuthSlice: StateCreator<RadarState, [], [], AuthSlice> = (set, get) => {
  const applyTokens = (res: TokenPair) => {
    setAccessToken(res.access)
    safeSet(STORAGE_KEYS.authRefresh, res.refresh)
    set({ user: res.user, authStatus: 'authed' })
    get().hydrateGamification(res.user.gamification)
    get().hydrateSharePresence(res.user.share_presence)
    void get().loadFriends().catch(() => {})
    void get().loadCollection().catch(() => {})
    // A device with no notification prefs of its own starts from the ones this
    // account last used elsewhere, rather than from the defaults.
    void get().hydrateNotifyPrefs().catch(() => {})
  }

  const clearSession = () => {
    setAccessToken(null)
    safeRemove(STORAGE_KEYS.authRefresh)
    set({ user: null, authStatus: 'anon' })
    get().hydrateGamification(false)
    get().hydrateSharePresence(true)
    get().clearFriends()
    get().clearGame()
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
    } catch (err) {
      // Only a rejection FROM THE SERVER means the refresh token is dead. A
      // network failure says nothing about it, and wiping the session on one
      // would log the user out mid-raid over a dropped request.
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clearSession()
      }
      return null
    }
  })

  return {
    user: null,
    authStatus: 'unknown',

    isAdmin: () => isAdminRole(get().user?.role),

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
        const me = await authMe()
        set({ user: me, authStatus: 'authed' })
        get().hydrateGamification(me.gamification)
        get().hydrateSharePresence(me.share_presence)
        void get().loadFriends().catch(() => {})
        void get().loadCollection().catch(() => {})
        void get().hydrateNotifyPrefs().catch(() => {})
      } catch {
        clearSession()
      }
    },

    updateProfile: async (patch) => {
      // The server echoes the whole user back, so the store takes ITS copy
      // rather than what we sent — a rejected or normalized value can then
      // never leave the UI showing something the account doesn't hold.
      const user = await patchMe(patch)
      set({ user })
    },
  }
}
