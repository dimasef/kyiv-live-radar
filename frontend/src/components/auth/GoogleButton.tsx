import { useEffect, useRef } from 'react'

import { useRadar } from '@/store'

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    google?: any
  }
}

// Load the Google Identity Services script exactly once, shared across renders.
let gisPromise: Promise<void> | null = null
function loadGis(): Promise<void> {
  if (gisPromise) return gisPromise
  gisPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.defer = true
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('Failed to load Google Identity Services'))
    document.head.appendChild(s)
  })
  return gisPromise
}

/** Google sign-in. Dormant (renders nothing) unless VITE_GOOGLE_CLIENT_ID is
 * set — so the app builds and runs with no Google setup. */
export default function GoogleButton({ onError }: { onError?: (e: unknown) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const loginWithGoogle = useRadar((s) => s.loginWithGoogle)

  useEffect(() => {
    if (!CLIENT_ID) return
    let cancelled = false
    loadGis()
      .then(() => {
        if (cancelled || !ref.current || !window.google) return
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (resp: { credential: string }) =>
            loginWithGoogle(resp.credential).catch((e: unknown) => onError?.(e)),
        })
        window.google.accounts.id.renderButton(ref.current, {
          theme: 'filled_black',
          size: 'large',
          text: 'continue_with',
          shape: 'pill',
          width: 260,
        })
      })
      .catch((e) => onError?.(e))
    return () => {
      cancelled = true
    }
  }, [loginWithGoogle, onError])

  if (!CLIENT_ID) return null
  return <div ref={ref} className="flex justify-center" />
}
