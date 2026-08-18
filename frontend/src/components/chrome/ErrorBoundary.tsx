import { Component, type ErrorInfo, type ReactNode } from 'react'

import { APP_VERSION } from '@/changelog'

interface State {
  error: Error | null
  componentStack: string | null
}

/** Last-resort crash screen.
 *
 * React unmounts the entire tree on an uncaught render error, which on this dark
 * theme looks exactly like a black screen — and on a TV browser there are no
 * devtools to find out why. This shows the actual message instead, so a crash on
 * a device we can't attach to is still diagnosable (read it off the screen, or
 * file it through the bug form on a device that works).
 *
 * Deliberately self-contained: hardcoded Ukrainian strings and no store, i18n or
 * router imports, since any of those could be what failed.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null, componentStack: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[radar] uncaught render error', error, info.componentStack)
    this.setState({ componentStack: info.componentStack ?? null })
  }

  render() {
    const { error, componentStack } = this.state
    if (!error) return this.props.children

    const details = [
      `${error.name}: ${error.message}`,
      (error.stack ?? '').split('\n').slice(1, 6).join('\n'),
      componentStack ? `\nКомпоненти:${componentStack.split('\n').slice(0, 6).join('\n')}` : '',
      `\nВерсія ${APP_VERSION}`,
      navigator.userAgent,
    ]
      .filter(Boolean)
      .join('\n')

    return (
      <div
        style={{
          height: '100%',
          overflowY: 'auto',
          background: '#05080d',
          color: '#dbe7f1',
          padding: 24,
          fontFamily: 'IBM Plex Sans, system-ui, sans-serif',
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px' }}>Радар зламався</h1>
        <p style={{ fontSize: 13, color: '#7d93a8', margin: '0 0 16px', maxWidth: 640 }}>
          Сторінка не змогла намалюватись. Це не втрата даних — перезавантаження зазвичай
          допомагає. Якщо повторюється, надішліть текст нижче.
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            appearance: 'none',
            border: '1px solid rgba(148,197,233,0.2)',
            background: 'rgba(34,211,238,0.12)',
            color: '#67e8f9',
            borderRadius: 8,
            padding: '8px 14px',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Перезавантажити
        </button>
        <pre
          style={{
            marginTop: 20,
            padding: 12,
            borderRadius: 8,
            background: 'rgba(255,255,255,0.04)',
            color: '#94a3b8',
            fontSize: 11,
            lineHeight: 1.5,
            fontFamily: 'IBM Plex Mono, monospace',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {details}
        </pre>
      </div>
    )
  }
}
