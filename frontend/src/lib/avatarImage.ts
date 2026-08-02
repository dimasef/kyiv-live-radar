/** Turning a phone photo into something small enough to live in a database
 * column. The whole avatar feature rests on this: the server accepts a `data:`
 * URL of a few kilobytes (see backend app/auth/avatar.py), so all the resizing
 * happens here, in a canvas, before anything is uploaded.
 */

/** Side of the stored square, in pixels. Enough for a 60px avatar on a 2× or 3×
 * screen without paying for detail nobody sees. */
export const AVATAR_PX = 160

/** The editor works on a square preview of this size; the export scales the
 * same framing up/down to AVATAR_PX, so what you position is what you get. */
export const PREVIEW_PX = 240

export interface Framing {
  /** 1 = the image's shorter side exactly fills the square. */
  zoom: number
  /** Centre offset in PREVIEW_PX units, before zoom. */
  offsetX: number
  offsetY: number
}

export const DEFAULT_FRAMING: Framing = { zoom: 1, offsetX: 0, offsetY: 0 }

/** Decode a picked file. `imageOrientation: 'from-image'` is the important bit:
 * phone photos carry an EXIF rotation that canvas drawing otherwise ignores,
 * which is how avatars end up sideways. */
export async function decodeImage(file: File): Promise<ImageBitmap> {
  return createImageBitmap(file, { imageOrientation: 'from-image' })
}

/** How far the framing may be dragged before the square would show empty space.
 * Returned in the same units as `Framing.offsetX/Y`. */
export function panLimits(bitmap: ImageBitmap, zoom: number) {
  const cover = PREVIEW_PX / Math.min(bitmap.width, bitmap.height)
  const drawnW = bitmap.width * cover * zoom
  const drawnH = bitmap.height * cover * zoom
  return {
    x: Math.max(0, (drawnW - PREVIEW_PX) / 2),
    y: Math.max(0, (drawnH - PREVIEW_PX) / 2),
  }
}

export function clampFraming(bitmap: ImageBitmap, framing: Framing): Framing {
  const zoom = Math.min(4, Math.max(1, framing.zoom))
  const limit = panLimits(bitmap, zoom)
  return {
    zoom,
    offsetX: Math.min(limit.x, Math.max(-limit.x, framing.offsetX)),
    offsetY: Math.min(limit.y, Math.max(-limit.y, framing.offsetY)),
  }
}

/** Paint the framed square onto a canvas of `size`. Shared by the live preview
 * and the export so the two can't drift — the only difference is the scale. */
export function drawFramed(
  ctx: CanvasRenderingContext2D,
  bitmap: ImageBitmap,
  framing: Framing,
  size: number,
) {
  const scale = size / PREVIEW_PX
  const cover = (PREVIEW_PX / Math.min(bitmap.width, bitmap.height)) * framing.zoom * scale
  const drawnW = bitmap.width * cover
  const drawnH = bitmap.height * cover
  ctx.clearRect(0, 0, size, size)
  ctx.drawImage(
    bitmap,
    (size - drawnW) / 2 + framing.offsetX * scale,
    (size - drawnH) / 2 + framing.offsetY * scale,
    drawnW,
    drawnH,
  )
}

/** The framed square as a `data:` URL the server will accept.
 *
 * WebP first — it's roughly half the size of JPEG at this quality, which is the
 * difference between an avatar that rides along in every /friends response
 * comfortably and one that doesn't. Browsers that can't encode it silently
 * return a PNG from toDataURL, which would be several times larger, so that
 * case falls back to JPEG explicitly. */
export function toAvatarDataUrl(bitmap: ImageBitmap, framing: Framing): string {
  const canvas = document.createElement('canvas')
  canvas.width = AVATAR_PX
  canvas.height = AVATAR_PX
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas unavailable')
  drawFramed(ctx, bitmap, framing, AVATAR_PX)
  const webp = canvas.toDataURL('image/webp', 0.85)
  if (webp.startsWith('data:image/webp')) return webp
  return canvas.toDataURL('image/jpeg', 0.85)
}
