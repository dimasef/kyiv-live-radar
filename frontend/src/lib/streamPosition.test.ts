import { describe, expect, it } from 'vitest'

import type { WSMessage } from '@/types'

import { advance, alreadyApplied } from './streamPosition'

const frame = (type: 'ping' | 'online' | 'health', epoch: number, seq: number): WSMessage =>
  type === 'health'
    ? { type, feed_ok: true, epoch, seq }
    : type === 'online'
      ? { type, online: 1, epoch, seq }
      : { type, epoch, seq }

describe('advance', () => {
  it('moves the position on a data frame', () => {
    expect(advance({ epoch: 7, seq: 10 }, frame('health', 7, 11))).toEqual({ epoch: 7, seq: 11 })
  })

  it('seeds an empty position from a keepalive after the boot hydrate', () => {
    expect(advance(null, frame('online', 7, 10))).toEqual({ epoch: 7, seq: 10 })
    expect(advance(null, frame('ping', 7, 10))).toEqual({ epoch: 7, seq: 10 })
  })

  it('never lets a keepalive carry an existing position forward', () => {
    // The reconnect regression: the 'online' frame that opens every socket
    // is stamped with the server's current seq, past the frames missed while
    // the socket was dead. Adopting it made the replay skip all of them.
    const held = { epoch: 7, seq: 10 }
    expect(advance(held, frame('online', 7, 15))).toBe(held)
    expect(advance(held, frame('ping', 7, 15))).toBe(held)
  })

  it('ignores a frame with no position', () => {
    const held = { epoch: 7, seq: 10 }
    expect(advance(held, { type: 'health', feed_ok: true })).toBe(held)
  })
})

describe('alreadyApplied', () => {
  it('skips a replayed frame a live one has already overtaken', () => {
    expect(alreadyApplied({ epoch: 7, seq: 12 }, frame('health', 7, 12))).toBe(true)
    expect(alreadyApplied({ epoch: 7, seq: 12 }, frame('health', 7, 11))).toBe(true)
  })

  it('applies every frame past the position', () => {
    expect(alreadyApplied({ epoch: 7, seq: 12 }, frame('health', 7, 13))).toBe(false)
  })

  it('treats another epoch as never seen', () => {
    expect(alreadyApplied({ epoch: 7, seq: 12 }, frame('health', 8, 1))).toBe(false)
    expect(alreadyApplied(null, frame('health', 7, 1))).toBe(false)
  })

  it('replays the whole gap after a reconnect that opened with an online frame', () => {
    let position = advance(null, frame('health', 7, 10))
    position = advance(position, frame('online', 7, 15))
    const missed = [11, 12, 13, 14, 15].map((seq) => frame('health', 7, seq))
    expect(missed.filter((f) => !alreadyApplied(position, f))).toHaveLength(5)
  })
})
