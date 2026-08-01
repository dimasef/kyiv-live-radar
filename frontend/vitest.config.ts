import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

// Separate from vite.config.ts on purpose: the app config carries the PWA
// plugin, which would try to build a service worker on every test run.
export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    // These suites cover pure logic only — no DOM, no React. Anything needing a
    // rendered component should bring its own environment rather than making
    // every test pay for jsdom.
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
