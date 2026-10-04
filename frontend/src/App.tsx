import { useEffect, useState } from 'react'
import { STATIC } from './api/client'
import { widgets } from './layout/registry'

type Theme = 'auto' | 'light' | 'dark'

function readTheme(): Theme {
  try {
    const t = localStorage.getItem('theme')
    return t === 'light' || t === 'dark' ? t : 'auto'
  } catch {
    return 'auto'
  }
}

function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') delete root.dataset.theme
    else root.dataset.theme = theme
    try {
      if (theme === 'auto') localStorage.removeItem('theme')
      else localStorage.setItem('theme', theme)
    } catch { /* private mode: theme lasts for this page only */ }
  }, [theme])
  return (
    <div className="segmented" role="radiogroup" aria-label="Theme">
      {(['auto', 'light', 'dark'] as const).map((t) => (
        <button key={t} role="radio" aria-checked={theme === t} className={theme === t ? 'on' : undefined}
          onClick={() => setTheme(t)}>
          {t === 'auto' ? 'System' : t === 'light' ? 'Light' : 'Dark'}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="wordmark">Deh Deh</span>
          <span className="season">2026-27 war room</span>
          {STATIC && <span className="season">Static copy, data of {import.meta.env.VITE_SNAPSHOT}</span>}
        </div>
        <ThemeSwitch />
      </header>
      <main className="grid">
        {widgets.map(({ id, title, component: Widget, wide }) => (
          <section key={id} className={wide ? 'panel wide' : 'panel'} aria-labelledby={`${id}-title`}>
            <h2 id={`${id}-title`}>{title}</h2>
            <Widget />
          </section>
        ))}
      </main>
    </>
  )
}
