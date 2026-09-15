import type { AnchorHTMLAttributes, ReactNode } from 'react'

import { isPlainClick } from '@/lib/plainClick'
import { navigate } from '@/router'

/** In-app navigation that is a real `<a href>`.
 *
 * Every destination in this app used to be a `<button onClick={navigate}>`,
 * which works for a person with a mouse and for nobody else: a crawler
 * standing on the map found no path to the journal at all (the sitemap was the
 * only thing connecting the site to itself), and a reader could not middle-
 * click a tab open or copy its address.
 *
 * The href is the real one, so all of that works; the plain click is still
 * handled in-app, so nothing reloads.
 */
export default function RouteLink({
  to,
  children,
  onClick,
  ...rest
}: { to: string; children: ReactNode } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e)
        if (e.defaultPrevented || !isPlainClick(e)) return
        e.preventDefault()
        navigate(to)
      }}
      {...rest}
    >
      {children}
    </a>
  )
}
