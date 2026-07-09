/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        // Ops-console pairing: Unbounded for display, IBM Plex for body/data.
        display: ['Unbounded', 'IBM Plex Sans', 'sans-serif'],
        sans: ['IBM Plex Sans', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Status palette shared with the map legend (semantics — do not restyle).
        confirmed: '#ef4444',
        unconfirmed: '#eab308',
        destroyed: '#6b7280',
        clear: '#22c55e',
        conflict: '#f97316',
        // Radar-phosphor accent.
        phosphor: {
          DEFAULT: '#22d3ee',
          soft: '#67e8f9',
          dim: '#0e7490',
        },
        ink: {
          950: '#05080d',
          900: '#0a1118',
          850: '#0d151f',
          800: '#111c28',
        },
      },
    },
  },
  plugins: [],
}
