import type { StateCreator } from 'zustand'

import {
  acceptFriendRequest,
  declineFriendRequest,
  deleteMyHome,
  fetchFriendRequests,
  fetchFriends,
  fetchMyHome,
  patchHomeShare,
  putMyHome,
  removeFriend,
  sendFriendRequest,
  type Friend,
  type FriendAction,
  type FriendRequests,
} from '@/api'
import type { ContactStyle } from '@/lib/contactMarker'
import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'

import type { RadarState } from './types'

const EMPTY_REQUESTS: FriendRequests = { incoming: [], outgoing: [] }

function loadHiddenHomeIds(): number[] {
  const raw = safeGet(STORAGE_KEYS.hiddenContactHomes)
  if (!raw) return []
  try {
    const ids = JSON.parse(raw)
    return Array.isArray(ids) ? ids.filter((n): n is number => typeof n === 'number') : []
  } catch {
    return []
  }
}

function loadContactStyles(): Record<number, ContactStyle> {
  const raw = safeGet(STORAGE_KEYS.contactStyles)
  if (!raw) return {}
  try {
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? (obj as Record<number, ContactStyle>) : {}
  } catch {
    return {}
  }
}

export interface FriendsSlice {
  friends: Friend[]
  friendRequests: FriendRequests
  /** Whether the current user shares their home with friends (server truth). */
  shareHome: boolean
  /** Contact ids whose shared home the user has hidden on their OWN map — a
   * local view preference (the contact keeps sharing), persisted across reloads. */
  hiddenHomeIds: number[]
  /** Per-contact map-marker appearance (colour + icon) the user picked, keyed by
   * contact id — local labelling only, persisted. Missing = default marker. */
  contactStyles: Record<number, ContactStyle>
  /** Fetch friends + pending requests + own share state — called on auth. */
  loadFriends: () => Promise<void>
  /** Drop all friend state — called on logout. */
  clearFriends: () => void
  /** Add a friend by email; returns the action outcome so the UI can toast. */
  requestFriend: (email: string) => Promise<FriendAction>
  acceptRequest: (id: number) => Promise<void>
  declineRequest: (id: number) => Promise<void>
  unfriend: (userId: number) => Promise<void>
  /** Toggle home sharing. Turning on uploads the current local home coords so
   * friends actually have something to see; turning off just flips the flag. */
  setShareHome: (share: boolean) => Promise<void>
  /** Show/hide one contact's shared home on the user's own map (local only). */
  toggleContactHome: (userId: number) => void
  /** Set one contact's marker colour + icon on the user's own map (local only). */
  setContactStyle: (userId: number, style: ContactStyle) => void
}

export const createFriendsSlice: StateCreator<RadarState, [], [], FriendsSlice> = (set, get) => ({
  friends: [],
  friendRequests: EMPTY_REQUESTS,
  shareHome: false,
  hiddenHomeIds: loadHiddenHomeIds(),
  contactStyles: loadContactStyles(),

  loadFriends: async () => {
    const [friends, requests, myHome] = await Promise.all([
      fetchFriends(),
      fetchFriendRequests(),
      fetchMyHome(),
    ])
    set({ friends, friendRequests: requests, shareHome: myHome.share_home })
  },

  clearFriends: () =>
    set({ friends: [], friendRequests: EMPTY_REQUESTS, shareHome: false }),

  requestFriend: async (email) => {
    const action = await sendFriendRequest(email)
    await get().loadFriends()
    return action
  },

  acceptRequest: async (id) => {
    await acceptFriendRequest(id)
    await get().loadFriends()
  },

  declineRequest: async (id) => {
    await declineFriendRequest(id)
    await get().loadFriends()
  },

  unfriend: async (userId) => {
    await removeFriend(userId)
    await get().loadFriends()
  },

  setShareHome: async (share) => {
    const home = get().home
    if (share && home) {
      await putMyHome(home.lat, home.lon, true)
    } else if (share) {
      // No local home to share yet — just record intent server-side; the next
      // setHome will upload the coords (see homeSlice.resyncHomeShare).
      await patchHomeShare(true)
    } else {
      // Stop sharing but keep coords server-side so toggling back on is instant.
      await patchHomeShare(false)
    }
    set({ shareHome: share })
  },

  toggleContactHome: (userId) => {
    const hidden = get().hiddenHomeIds
    const next = hidden.includes(userId)
      ? hidden.filter((id) => id !== userId)
      : [...hidden, userId]
    safeSet(STORAGE_KEYS.hiddenContactHomes, JSON.stringify(next))
    set({ hiddenHomeIds: next })
  },

  setContactStyle: (userId, style) => {
    const next = { ...get().contactStyles, [userId]: style }
    safeSet(STORAGE_KEYS.contactStyles, JSON.stringify(next))
    set({ contactStyles: next })
  },
})

/** Push the current local home to the server — the home twin of resyncHomePush,
 * called from homeSlice.setHome only when already sharing. Clearing home
 * (h === null) deletes the server copy so friends stop seeing a stale marker. */
export async function resyncHomeShare(h: { lat: number; lon: number } | null): Promise<void> {
  if (h) await putMyHome(h.lat, h.lon, true)
  else await deleteMyHome()
}
