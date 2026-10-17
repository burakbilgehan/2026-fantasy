import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useSynced } from './synced'

// Player lists (user, 2026-10-17): as many lists as the user wants, like playlists, each with its own
// symbol (flyers, first round targets, stay away). Kept in the browser (localStorage), so they also work
// in the static copy. The local site and the static copy have separate lists.
export type PlayerList = { id: string; name: string; symbol: string; players: number[] }

type Lists = {
  lists: PlayerList[]
  of: (pk: number) => PlayerList[]
  toggle: (listId: string, pk: number) => void
  create: (name: string, symbol: string) => void
  remove: (listId: string) => void
}

const ListsContext = createContext<Lists | null>(null)

export function ListsProvider({ children }: { children: ReactNode }) {
  const [lists, setLists] = useSynced<PlayerList[]>('player-lists', [])
  const value = useMemo<Lists>(() => {
    const byPlayer = new Map<number, PlayerList[]>()
    for (const l of lists) for (const pk of l.players) byPlayer.set(pk, [...(byPlayer.get(pk) ?? []), l])
    return {
      lists,
      of: (pk) => byPlayer.get(pk) ?? [],
      toggle: (listId, pk) => setLists(lists.map((l) => (l.id !== listId ? l
        : { ...l, players: l.players.includes(pk) ? l.players.filter((x) => x !== pk) : [...l.players, pk] }))),
      create: (name, symbol) => setLists([...lists, { id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
        name, symbol, players: [] }]),
      remove: (listId) => setLists(lists.filter((l) => l.id !== listId)),
    }
  }, [lists, setLists])
  return <ListsContext.Provider value={value}>{children}</ListsContext.Provider>
}

export function useLists(): Lists | null {
  return useContext(ListsContext)
}

/** Symbols of the lists the player is in, next to the name. */
export function ListMarks({ pk }: { pk: number }) {
  const ctx = useLists()
  const mine = ctx?.of(pk) ?? []
  if (!mine.length) return null
  return <span className="list-marks" title={mine.map((l) => `${l.symbol} ${l.name}`).join('\n')}>{mine.map((l) => l.symbol).join('')}</span>
}

const SYMBOLS = ['🎯', '⭐', '💎', '🚀', '🔥', '🧪', '👀', '💰', '⚠️', '🚫', '💀', '🩼']

/** Button next to the name: a menu to put the player into lists, make a new list or delete one. */
export function ListButton({ pk }: { pk: number }) {
  const ctx = useLists()
  const [open, setOpen] = useState<{ x: number; y: number } | null>(null)
  const [name, setName] = useState('')
  const [symbol, setSymbol] = useState(SYMBOLS[0])
  const [deleting, setDeleting] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const btn = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const out = (e: MouseEvent) => { const t = e.target as Node
      if (!box.current?.contains(t) && !btn.current?.contains(t)) setOpen(null) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
    document.addEventListener('mousedown', out)
    document.addEventListener('keydown', esc, true) // capture: the menu stops key events from reaching the row
    return () => { document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc, true) }
  }, [open])
  if (!ctx) return null
  const add = () => {
    const n = name.trim()
    if (!n || !symbol.trim()) return
    ctx.create(n, symbol.trim())
    setName('')
  }
  return (
    // Clicks inside must not open the row or the drawer.
    <span className="list-btn-wrap" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <button ref={btn} className="list-btn" title="Add to a list" aria-haspopup="menu" aria-expanded={!!open}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          setOpen(open ? null : { x: Math.min(r.left, window.innerWidth - 270), y: r.bottom + 4 })
          setDeleting(null)
        }}>+</button>
      {open && createPortal(
        // In <body>: the sticky name column would clip the menu and put it under the other cells.
        <div ref={box} onClick={(e) => e.stopPropagation()} className="list-menu" role="menu" style={{ left: open.x, top: Math.min(open.y, window.innerHeight - 320) }}>
          {ctx.lists.length === 0 && <p className="hint">No lists yet. Make one below.</p>}
          {ctx.lists.map((l) => (
            <div key={l.id} className="list-item">
              <label>
                <input type="checkbox" checked={l.players.includes(pk)} onChange={() => ctx.toggle(l.id, pk)} />
                <span className="list-sym">{l.symbol}</span> {l.name} <small className="hint">({l.players.length})</small>
              </label>
              <button className={deleting === l.id ? 'list-del confirm' : 'list-del'} title="Delete the list"
                onClick={() => { if (deleting === l.id) { ctx.remove(l.id); setDeleting(null) } else setDeleting(l.id) }}>
                {deleting === l.id ? 'Delete?' : '×'}
              </button>
            </div>
          ))}
          <div className="list-new">
            <div className="list-syms">
              {SYMBOLS.map((s) => <button key={s} className={s === symbol ? 'on' : undefined} onClick={() => setSymbol(s)}>{s}</button>)}
            </div>
            <div className="list-new-row">
              <input className="list-sym-input" value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Symbol" maxLength={4} />
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New list name" aria-label="New list name"
                onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
              <button onClick={add} disabled={!name.trim()}>Add</button>
            </div>
          </div>
        </div>, document.body,
      )}
    </span>
  )
}
