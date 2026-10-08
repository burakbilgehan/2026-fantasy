import { useEffect, useState } from 'react'
import { STATIC } from './api/client'
import { widgets } from './layout/registry'
import { PlayerValues, type View } from './widgets/player-values/PlayerValues'

// Views as tabs (user, 2026-10-06). Each has its own address, so two or three can sit side by side in
// separate browser tabs; every tab polls the backend itself and the selected player is shared.
type Page = View | 'info'
const PAGES: { key: Page; label: string }[] = [
  { key: 'draft', label: 'Draft' }, { key: 'league', label: 'League' }, { key: 'player', label: 'Player' }, { key: 'info', label: 'Info' },
]
const pageOf = (): Page => (PAGES.find((p) => `#${p.key}` === window.location.hash)?.key ?? 'draft')

function usePage(): Page {
  const [page, setPage] = useState<Page>(pageOf)
  useEffect(() => {
    const on = () => setPage(pageOf())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return page
}

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
  const page = usePage()
  const title = PAGES.find((p) => p.key === page)!.label
  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="wordmark">Deh Deh</span>
          <span className="season">2026-27 war room</span>
          {STATIC && <span className="season">Static copy, data of {import.meta.env.VITE_SNAPSHOT}</span>}
        </div>
        <nav className="tabs" aria-label="Views">
          {PAGES.map((p) => <a key={p.key} href={`#${p.key}`} className={p.key === page ? 'on' : undefined}
            aria-current={p.key === page ? 'page' : undefined}>{p.label}</a>)}
        </nav>
        <ThemeSwitch />
      </header>
      {page === 'info' ? (
        <main className="grid scroll">
          {widgets.filter((w) => w.id !== 'player-values').map(({ id, title, component: Widget, wide }) => (
            <section key={id} className={wide ? 'panel wide' : 'panel'} aria-labelledby={`${id}-title`}>
              <h2 id={`${id}-title`}>{title}</h2>
              <Widget />
            </section>
          ))}
        </main>
      ) : (
        <main className="fill">
          <section className="panel fill" aria-label={title}>
            <PlayerValues key={page} mode={page} />
          </section>
        </main>
      )}
    </>
  )
}
