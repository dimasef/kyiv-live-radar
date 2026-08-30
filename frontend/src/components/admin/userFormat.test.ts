import { describe, expect, it } from 'vitest'

import type { AdminUser } from '@/api'

import {
  blockDisabledReason,
  filterUsers,
  roleChangeBlockedReason,
  roleLabel,
  userLabel,
} from './userFormat'

function user(over: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 1,
    email: 'someone@example.com',
    email_verified: false,
    display_name: 'Оператор',
    avatar_url: null,
    role: 'user',
    role_source: 'default',
    providers: ['password'],
    is_active: true,
    created_at: '2026-08-30T10:00:00Z',
    last_login_at: null,
    last_seen_at: null,
    ...over,
  } as AdminUser
}

describe('userLabel', () => {
  it('prefers the display name, then the email, then the id', () => {
    expect(userLabel(user())).toBe('Оператор')
    expect(userLabel(user({ display_name: null }))).toBe('someone@example.com')
    // A Telegram-only account with neither must still be identifiable — this is
    // why the contacts UI's personLabel (which falls back to '—') isn't reused.
    expect(userLabel(user({ id: 42, display_name: null, email: null }))).toBe('#42')
  })

  it('ignores a whitespace-only display name', () => {
    expect(userLabel(user({ display_name: '   ' }))).toBe('someone@example.com')
  })
})

describe('filterUsers', () => {
  const list = [
    user({ id: 1, display_name: 'Оператор', email: 'boss@x.com' }),
    user({ id: 2, display_name: null, email: null, providers: ['telegram'] }),
    user({ id: 3, display_name: 'Гість', email: 'guest@y.com', providers: ['password', 'google'] }),
  ]

  it('returns the SAME array for an empty query', () => {
    // Identity, not a copy: the filter runs during render, and a fresh array
    // each keystroke would re-render every row for nothing.
    expect(filterUsers(list, '')).toBe(list)
    expect(filterUsers(list, '   ')).toBe(list)
  })

  it('matches name and email case-insensitively, trimmed', () => {
    expect(filterUsers(list, '  ОПЕРАТОР ').map((u) => u.id)).toEqual([1])
    expect(filterUsers(list, 'GUEST@y').map((u) => u.id)).toEqual([3])
  })

  it('matches the provider label and the id', () => {
    expect(filterUsers(list, 'telegram').map((u) => u.id)).toEqual([2])
    expect(filterUsers(list, 'google').map((u) => u.id)).toEqual([3])
    expect(filterUsers(list, '#2').map((u) => u.id)).toEqual([2])
  })

  it('tolerates a null email and null name without throwing', () => {
    expect(() => filterUsers(list, 'x')).not.toThrow()
    expect(filterUsers(list, 'zzz')).toEqual([])
  })
})

describe('roleLabel', () => {
  it('flags an admin whose role nothing backs any more', () => {
    // The one thing this tab exists to surface: role resolution will silently
    // demote them to 'user' at their next login.
    const stale = roleLabel(user({ role: 'admin', role_source: 'default' }))
    expect(stale.stale).toBe(true)
    expect(stale.text).toBe('Адмін')
  })

  it('does not flag an env-backed or manual admin', () => {
    expect(roleLabel(user({ role: 'admin', role_source: 'allowlist' })).stale).toBe(false)
    const manual = roleLabel(user({ role: 'admin_g', role_source: 'manual' }))
    expect(manual.stale).toBe(false)
    expect(manual.text).toBe('Адмін (вручну)')
  })

  it('never flags a plain user, whatever the provenance says', () => {
    expect(roleLabel(user({ role: 'user', role_source: 'default' })).stale).toBe(false)
  })
})

describe('roleChangeBlockedReason', () => {
  it('refuses your own role — demoting yourself locks you out', () => {
    expect(roleChangeBlockedReason(user({ id: 7 }), 7)).toBe('self')
  })

  it('refuses a role the env allowlist grants', () => {
    // Role resolution would hand it straight back at the next login, so a
    // control that appeared to work would be lying.
    const envAdmin = user({ id: 7, role: 'admin', role_source: 'allowlist' })
    expect(roleChangeBlockedReason(envAdmin, 1)).toBe('allowlist')
  })

  it('allows a manual admin and a plain user', () => {
    expect(roleChangeBlockedReason(user({ id: 7, role: 'admin_g', role_source: 'manual' }), 1))
      .toBeNull()
    expect(roleChangeBlockedReason(user({ id: 7, role: 'user' }), 1)).toBeNull()
    // A stale admin IS editable — that is how the operator cleans one up.
    expect(roleChangeBlockedReason(user({ id: 7, role: 'admin', role_source: 'default' }), 1))
      .toBeNull()
  })
})

describe('blockDisabledReason', () => {
  // Must mirror the backend guard in api/admin/users.py exactly — the button is
  // hidden rather than left to fail, because AdminActionButton discards the
  // server's error detail.
  it('refuses your own account first', () => {
    expect(blockDisabledReason(user({ id: 7, role: 'user' }), 7)).toBe('self')
    expect(blockDisabledReason(user({ id: 7, role: 'admin' }), 7)).toBe('self')
  })

  it('refuses any admin', () => {
    expect(blockDisabledReason(user({ id: 7, role: 'admin' }), 1)).toBe('admin')
    expect(blockDisabledReason(user({ id: 7, role: 'admin_g' }), 1)).toBe('admin')
  })

  it('allows a plain user', () => {
    expect(blockDisabledReason(user({ id: 7, role: 'user' }), 1)).toBeNull()
    // Signed-out / unknown viewer: only the self-check is skipped.
    expect(blockDisabledReason(user({ id: 7, role: 'user' }), null)).toBeNull()
  })
})
