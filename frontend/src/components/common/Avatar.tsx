/** Circular avatar: the person's image, or a phosphor monogram fallback from
 * the first letter of their name. Shared by the account header and the contacts
 * list / contact-profile modal. */
export default function Avatar({
  name,
  avatarUrl,
  size = 32,
}: {
  name: string
  avatarUrl?: string | null
  size?: number
}) {
  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt=""
        className="flex-none rounded-full object-cover"
        style={{ width: size, height: size }}
      />
    )
  }
  const initial = name.trim().charAt(0).toUpperCase() || '?'
  return (
    <div
      aria-hidden
      className="flex flex-none items-center justify-center rounded-full bg-phosphor/10 font-bold text-phosphor-soft ring-1 ring-phosphor/20"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      {initial}
    </div>
  )
}
