import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'src/api-types.ts'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.serviceworker },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // CLAUDE.md's rule is to reach for useEffect only to sync with something
      // outside React. An effect with a lying dependency array is the usual
      // symptom of one that shouldn't have been an effect at all, so this is an
      // error, not a warning — it's the objective list of candidates to remove.
      'react-hooks/exhaustive-deps': 'error',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // `_`-prefixed args/vars are the codebase's existing "deliberately unused"
      // marker; everything else unused is a real leftover.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  // The entry point mounts the app and exports nothing to hot-refresh —
  // react-refresh's advice doesn't apply to it. Must come after the block
  // above: in flat config the last matching entry wins.
  { files: ['src/main.tsx'], rules: { 'react-refresh/only-export-components': 'off' } },
)
