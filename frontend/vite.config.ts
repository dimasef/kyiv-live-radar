import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // injectManifest (not generateSW) so we own src/sw.ts — Stage B (Web Push)
      // will add `push`/`notificationclick` handlers there without a strategy
      // migration. registerType 'prompt' + a reload toast (see UpdateToast) so a
      // safety-adjacent app never strands an open tab on a stale bundle.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'prompt',
      injectRegister: null, // registered manually in main.tsx
      includeAssets: ['favicon.svg'],
      injectManifest: { globPatterns: ['**/*.{js,css,html,svg,woff2,png}'] },
      manifest: {
        name: 'Kyiv Live Radar',
        short_name: 'Live Radar',
        description: 'Допоміжний трекер повітряних загроз над Києвом',
        lang: 'uk',
        dir: 'ltr',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'any',
        theme_color: '#05080d',
        background_color: '#05080d',
        categories: ['news', 'utilities', 'weather'],
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      // A live SW during `vite dev` fights HMR/asset caching — enable only for
      // targeted SW debugging.
      devOptions: { enabled: false, type: 'module' },
    }),
  ],
  server: { port: 5173 },
})
