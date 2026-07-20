/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/react" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_WS_URL?: string
  // Google OAuth client id — when set, the Google sign-in button renders.
  readonly VITE_GOOGLE_CLIENT_ID?: string
  // Telegram Login Widget bot username (without @) — when set, the Telegram
  // sign-in button renders.
  readonly VITE_TELEGRAM_LOGIN_BOT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Not in the standard DOM lib — the deferred PWA install prompt (Chromium).
interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[]
  prompt(): Promise<void>
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}
interface WindowEventMap {
  beforeinstallprompt: BeforeInstallPromptEvent
}
// iOS Safari standalone flag (non-standard).
interface Navigator {
  readonly standalone?: boolean
}
