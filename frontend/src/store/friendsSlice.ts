import type { StateCreator } from 'zustand'

import {
  acceptFriendRequest,
  declineFriendRequest,
  deleteMyHome,
  fetchContactPrefs,
  fetchFriendRequests,
  fetchFriends,
  fetchMyHome,
  fetchMyPresence,
  patchHomeShare,
  putContactPref,
  putMyHome,
  putMyPresence,
  removeFriend,
  sendFriendRequest,
  type Friend,
  type FriendAction,
  type FriendRequests,
} from '@/api'
import { DEFAULT_CONTACT_COLOR, DEFAULT_CONTACT_ICON, type ContactStyle } from '@/lib/contactMarker'
import { safeGet, safeRemove, safeSet, STORAGE_KEYS } from '@/lib/storage'

import type { RadarState } from './types'

const EMPTY_REQUESTS: FriendRequests = { incoming: [], outgoing: [] }

/** The account's per-contact prefs -> the two shapes the store keeps them in.
 * Server keys are strings (JSON objects have no integer keys), so they're
 * parsed back to the numeric user ids everything else is keyed by. */
function splitContactPrefs(prefs: Record<string, Record<string, unknown>>) {
  const styles: Record<number, ContactStyle> = {}
  const hidden: number[] = []
  for (const [key, entry] of Object.entries(prefs)) {
    const id = Number(key)
    if (!Number.isFinite(id) || !entry) continue
    if (entry.hidden === true) hidden.push(id)
    if (typeof entry.color === 'string' || typeof entry.icon === 'string') {
      styles[id] = {
        color: typeof entry.color === 'string' ? entry.color : DEFAULT_CONTACT_COLOR,
        icon: typeof entry.icon === 'string' ? entry.icon : DEFAULT_CONTACT_ICON,
      }
    }
  }
  return { styles, hidden }
}

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
  /** Whether friends may see WHEN the user was last active. The online dot is
   * NOT gated by this — see backend domain/presence.py. */
  sharePresence: boolean
  /** Contact ids whose shared home the user has hidden on their OWN map (the
   * contact keeps sharing). Account-bound; the local copy is a cache. */
  hiddenHomeIds: number[]
  /** Per-contact map-marker appearance (colour + icon), keyed by contact id.
   * Account-bound like hiddenHomeIds. Missing = default marker. */
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
  /** Toggle whether contacts may see the home. Only a visibility flag — the
   * coordinates live on the account either way (see homeSlice). */
  setShareHome: (share: boolean) => Promise<void>
  setSharePresence: (share: boolean) => Promise<void>
  /** Seed from /auth/me so the switch never renders stale before the friend
   * graph loads. */
  hydrateSharePresence: (share: boolean) => void
  /** Show/hide one contact's shared home on the user's own map. Private to the
   * viewer — the contact keeps sharing and is never told. Stored on the account
   * so it survives a device change. */
  toggleContactHome: (userId: number) => void
  /** Set one contact's marker colour + icon on the user's own map. Same
   * account-bound, contact-invisible labelling as toggleContactHome. */
  setContactStyle: (userId: number, style: ContactStyle) => void
}

export const createFriendsSlice: StateCreator<RadarState, [], [], FriendsSlice> = (set, get) => ({
  friends: [],
  friendRequests: EMPTY_REQUESTS,
  shareHome: false,
  sharePresence: true,
  hiddenHomeIds: loadHiddenHomeIds(),
  contactStyles: loadContactStyles(),

  loadFriends: async () => {
    const [friends, requests, myHome, presence, contactPrefs] = await Promise.all([
      fetchFriends(),
      fetchFriendRequests(),
      fetchMyHome(),
      fetchMyPresence(),
      fetchContactPrefs(),
    ])
    const { styles, hidden } = splitContactPrefs(contactPrefs.prefs ?? {})
    set({
      friends,
      friendRequests: requests,
      shareHome: myHome.share_home,
      sharePresence: presence.share_presence,
      contactStyles: styles,
      hiddenHomeIds: hidden,
    })
    safeSet(STORAGE_KEYS.contactStyles, JSON.stringify(styles))
    safeSet(STORAGE_KEYS.hiddenContactHomes, JSON.stringify(hidden))

    // Home merge: whatever is on THIS device wins and is pushed up, because
    // it's what the user is looking at right now. The account only fills an
    // empty client — which is the case this whole change exists for (opening
    // the app on a second device used to show no home at all).
    const local = get().home
    if (local) {
      void resyncHomeShare(local).catch(() => {})
    } else if (myHome.home) {
      get().hydrateHome({
        lat: myHome.home.lat,
        lon: myHome.home.lon,
        radiusKm: myHome.radius_km ?? 3,
        origin: 'manual',
      })
    }
  },

  clearFriends: () => {
    // Contact labels belong to the account that was signed in, so they go with
    // it — otherwise the next user on this device inherits someone else's
    // colours (and the ids wouldn't even mean the same people).
    safeRemove(STORAGE_KEYS.contactStyles)
    safeRemove(STORAGE_KEYS.hiddenContactHomes)
    set({
      friends: [],
      friendRequests: EMPTY_REQUESTS,
      shareHome: false,
      sharePresence: true,
      contactStyles: {},
      hiddenHomeIds: [],
    })
  },

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
    // Essentially a visibility flip: every setHome already uploads the
    // coordinates. The one gap is the moment right after signing in, before
    // loadFriends has synced this device's home up — flipping sharing on then
    // would leave contacts with a shared-but-empty home, so make sure the
    // coordinates are there first.
    const home = get().home
    if (share && home) await resyncHomeShare(home)
    await patchHomeShare(share)
    set({ shareHome: share })
  },

  hydrateSharePresence: (share) => set({ sharePresence: share }),

  setSharePresence: async (share) => {
    await putMyPresence(share)
    set({ sharePresence: share })
  },

  // Both writers below update local state first and persist in the background:
  // picking a colour should feel instant, and a failed sync is a stale label on
  // your own map — not worth blocking the UI or surfacing an error for.
  toggleContactHome: (userId) => {
    const hidden = get().hiddenHomeIds
    const nowHidden = !hidden.includes(userId)
    const next = nowHidden ? [...hidden, userId] : hidden.filter((id) => id !== userId)
    safeSet(STORAGE_KEYS.hiddenContactHomes, JSON.stringify(next))
    set({ hiddenHomeIds: next })
    if (get().authStatus === 'authed')
      void putContactPref(userId, { hidden: nowHidden }).catch(() => {})
  },

  setContactStyle: (userId, style) => {
    const next = { ...get().contactStyles, [userId]: style }
    safeSet(STORAGE_KEYS.contactStyles, JSON.stringify(next))
    set({ contactStyles: next })
    if (get().authStatus === 'authed') void putContactPref(userId, style).catch(() => {})
  },
})

/** Push the current local home onto the account — the home twin of
 * resyncHomePush, called from homeSlice on every change while signed in. The
 * share flag is untouched here: storing where you live and letting contacts see
 * it are separate decisions. Clearing home (h === null) deletes the server copy
 * too, so it can't come back on the next device. */
export async function resyncHomeShare(
  h: { lat: number; lon: number; radiusKm: number } | null,
): Promise<void> {
  if (h) await putMyHome(h.lat, h.lon, h.radiusKm)
  else await deleteMyHome()
}
