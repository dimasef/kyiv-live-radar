/** Turning a phone screenshot into something a database column can hold.
 *
 * Same trade as `avatarImage.ts`: the server takes a `data:` URL (see backend
 * app/images.py), so every byte of resizing happens here. A screenshot needs to
 * stay READABLE — text in a feed card, a number in a banner — so it keeps far
 * more resolution than an avatar does, and pays for it in JPEG quality instead.
 */

/** Long side of the stored image. A 2560px-wide phone screenshot at this size
 * still shows what its text said; beyond it, only file size grows. */
const MAX_SIDE_PX = 1600

/** Server ceiling is 900 KB of base64 (~675 KB of image); stay clear of it. */
const MAX_CHARS = 800 * 1024

/** Tried in order until one fits — a busy map screenshot compresses far worse
 * than a mostly-dark one, so a single quality can't serve both. */
const QUALITIES = [0.72, 0.55, 0.4]

export class ScreenshotError extends Error {}

/** Decode, downscale and JPEG-encode a picked/pasted image file.
 * `imageOrientation` matters for the same reason it does for avatars: phone
 * captures carry an EXIF rotation that canvas drawing otherwise ignores. */
export async function toScreenshotDataUrl(file: File): Promise<string> {
  if (!file.type.startsWith('image/')) {
    throw new ScreenshotError('Це не зображення')
  }
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE_PX / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new ScreenshotError('Не вдалося обробити зображення')
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()

  for (const quality of QUALITIES) {
    const url = canvas.toDataURL('image/jpeg', quality)
    if (url.length <= MAX_CHARS) return url
  }
  throw new ScreenshotError('Знімок завеликий — спробуйте обрізати його')
}

/** The image in a paste event, if it carried one (Ctrl+V of a screenshot). */
export function imageFromClipboard(data: DataTransfer | null): File | null {
  for (const item of data?.items ?? []) {
    if (!item.type.startsWith('image/')) continue
    const file = item.getAsFile()
    if (file) return file
  }
  return null
}
