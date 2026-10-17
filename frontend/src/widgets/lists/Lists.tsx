// Lists tab (user, 2026-10-17): the player pool on the left, the user's lists on the right as an accordion.
// Drag a player from the pool onto a list to add him, from one list onto another to copy him, from a list
// back onto the pool to take him out. A click on a name opens the player window.
import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react'
import { api, type ValuationQuery, type ValuedPlayer } from '../../api/client'
import { Headshot } from '../../components/Headshot'
import { PlayerDrawer } from '../../components/PlayerDrawer'
import { useLiveBoard } from '../../lib/liveBoard'
import { ListMarks, SYMBOLS, useLists, type PlayerList } from '../../lib/playerLists'
import { useSynced } from '../../lib/synced'

const DEFAULT_QUERY: ValuationQuery = { kind: 'projection', source: 'yahoo', season: '2026-27', basis: 'totals',
  model: 'gscore', dollars: 'plain', pool: 200, punt: [] }
const MIME = 'application/x-player'
type Drag = { pk: number; from: string | null } // from: list id, null = the pool

const readDrag = (e: DragEvent): Drag | null => {
  try { return JSON.parse(e.dataTransfer.getData(MIME)) as Drag } catch { return null }
}

function PlayerRow({ p, from, onOpen, onRemove, sold }: {
  p: ValuedPlayer; from: string | null; onOpen: (id: number) => void; onRemove?: () => void
  sold?: string // "$76 Team name" when the live draft sold him (row in grey)
}) {
  return (
    <div className={sold ? 'lrow sold' : 'lrow'} title={sold ? `Sold: ${sold}` : undefined} draggable
      onDragStart={(e) => { e.dataTransfer.setData(MIME, JSON.stringify({ pk: p.player_id, from })); e.dataTransfer.effectAllowed = 'copyMove' }}>
      <span className="lrank">{p.rank ?? '-'}</span>
      <Headshot nbaId={p.nba_id} name={p.name} />
      <span className="lname">
        <button className="link" onClick={() => onOpen(p.player_id)}>{p.name}</button>
        <ListMarks pk={p.player_id} />
        {p.injury && <span className="injury">{p.injury}</span>}
      </span>
      <span className="lmeta">{p.team ?? 'FA'} · {p.positions?.join(',') ?? '-'}</span>
      {sold ? <span className="lsold">{sold}</span>
        : <span className="lprice" title="Static price (our model)">{p.dollars != null ? `$${p.dollars.toFixed(0)}` : ''}</span>}
      {onRemove && <button className="ldel" title="Take out of the list" onClick={onRemove}>×</button>}
    </div>
  )
}

function SymbolPicker({ value, onPick }: { value: string; onPick: (s: string) => void }) {
  const [own, setOwn] = useState('')
  return (
    <div className="lsyms">
      {SYMBOLS.map((s) => <button key={s} className={s === value ? 'on' : undefined} onClick={() => onPick(s)}>{s}</button>)}
      <input value={own} onChange={(e) => setOwn(e.target.value)} placeholder="own" aria-label="Own symbol" maxLength={4}
        onKeyDown={(e) => { if (e.key === 'Enter' && own.trim()) { onPick(own.trim()); setOwn('') } }} />
    </div>
  )
}

function ListBox({ list, open, onToggle, byId, sold, onOpen, onDrop, dropping, setDropping }: {
  list: PlayerList; open: boolean; onToggle: () => void; byId: Map<number, ValuedPlayer>; sold: Map<number, string>
  onOpen: (id: number) => void; onDrop: (d: Drag) => void; dropping: boolean; setDropping: (v: boolean) => void
}) {
  const ctx = useLists()!
  const [name, setName] = useState(list.name)
  const [picking, setPicking] = useState(false)
  const [deleting, setDeleting] = useState(false)
  useEffect(() => setName(list.name), [list.name])
  const commit = () => { const n = name.trim(); if (n && n !== list.name) ctx.update(list.id, { name: n }); else setName(list.name) }
  const players = list.players.map((pk) => byId.get(pk)).filter((p): p is ValuedPlayer => !!p)
  const missing = list.players.length - players.length
  return (
    <section className={['lbox', dropping && 'drop'].filter(Boolean).join(' ')}
      onDragOver={(e) => { if (e.dataTransfer.types.includes(MIME)) { e.preventDefault(); setDropping(true) } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropping(false) }}
      onDrop={(e) => { e.preventDefault(); setDropping(false); const d = readDrag(e); if (d) onDrop(d) }}>
      <header className="lhead">
        <button className="lchev" aria-expanded={open} onClick={onToggle} title={open ? 'Close' : 'Open'}>{open ? '▾' : '▸'}</button>
        <button className="lsym" title="Change the symbol" onClick={() => setPicking(!picking)}>{list.symbol}</button>
        <input className="ltitle" value={name} aria-label="List name" onChange={(e) => setName(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setName(list.name) }} />
        <span className="lcount">{list.players.length}</span>
        <button className={deleting ? 'ldel-list confirm' : 'ldel-list'} onBlur={() => setDeleting(false)}
          onClick={() => (deleting ? ctx.remove(list.id) : setDeleting(true))} title="Delete the list">
          {deleting ? 'Delete?' : 'Delete'}
        </button>
      </header>
      {picking && <SymbolPicker value={list.symbol} onPick={(s) => { ctx.update(list.id, { symbol: s }); setPicking(false) }} />}
      {open && (
        <div className="lbody">
          {players.length === 0 && <p className="hint">Drag players here.</p>}
          {players.map((p) => <PlayerRow key={p.player_id} p={p} from={list.id} onOpen={onOpen} sold={sold.get(p.player_id)}
            onRemove={() => ctx.drop(list.id, p.player_id)} />)}
          {missing > 0 && <p className="hint">{missing} player(s) not in the current base.</p>}
        </div>
      )}
    </section>
  )
}

export function Lists() {
  const ctx = useLists()!
  const [query] = useSynced<ValuationQuery | null>('pv-query', null)
  const q = query ?? DEFAULT_QUERY
  const [players, setPlayers] = useState<ValuedPlayer[]>([])
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [pos, setPos] = useState('')
  const [hideListed, setHideListed] = useState(false)
  const [openIds, setOpenIds] = useSynced<string[]>('lists-open', [])
  const [dropOn, setDropOn] = useState<string | null>(null) // list id or 'pool'
  const [newName, setNewName] = useState('')
  const [newSym, setNewSym] = useState(SYMBOLS[0])
  const [drawer, setDrawer] = useState<number | null>(null)
  const closeDrawer = useCallback(() => setDrawer(null), [])
  // Players already sold in the followed live draft: grey rows with price and buyer.
  const board = useLiveBoard().board
  const sold = useMemo(() => {
    if (!board) return new Map<number, string>()
    const team = new Map(board.teams.map((t) => [t.team_id, t.name ?? `Team ${t.team_id}`]))
    return new Map(board.picks.filter((x) => x.player_pk != null).map((x) => [x.player_pk!, `$${x.price} ${team.get(x.team_id)}`]))
  }, [board])

  useEffect(() => {
    let alive = true
    api.valuation(q)
      .then((v) => { if (alive) { setPlayers(v.players); setError(null) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
    // The query object is new on every read; its JSON is the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(q)])

  const byId = useMemo(() => new Map(players.map((p) => [p.player_id, p])), [players])
  const pool = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return players.filter((p) => (!needle || p.name.toLowerCase().includes(needle))
      && (!pos || p.positions?.includes(pos)) && (!hideListed || ctx.of(p.player_id).length === 0))
  }, [players, search, pos, hideListed, ctx])

  const create = () => {
    const n = newName.trim()
    if (!n) return
    // A new list opens at once, ready for drops.
    setOpenIds([...openIds, ctx.create(n, newSym)])
    setNewName('')
  }
  const toggle = (id: string) => setOpenIds(openIds.includes(id) ? openIds.filter((x) => x !== id) : [...openIds, id])

  return (
    <div className="lists-page">
      <section className={['lpool', dropOn === 'pool' && 'drop'].filter(Boolean).join(' ')} aria-label="Player pool"
        onDragOver={(e) => { if (e.dataTransfer.types.includes(MIME)) { e.preventDefault(); setDropOn('pool') } }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropOn(null) }}
        onDrop={(e) => { e.preventDefault(); setDropOn(null); const d = readDrag(e); if (d?.from) ctx.drop(d.from, d.pk) }}>
        <div className="lpool-head">
          <h2>Players</h2>
          <input type="search" placeholder="Find a player" aria-label="Find a player" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={pos} onChange={(e) => setPos(e.target.value)} aria-label="Position">
            <option value="">All</option><option value="G">G</option><option value="F">F</option><option value="C">C</option>
          </select>
          <label className="toggle"><input type="checkbox" checked={hideListed} onChange={(e) => setHideListed(e.target.checked)} />Not in a list</label>
        </div>
        <p className="hint">Drag a player onto a list. Drag a player from a list back here to take him out.</p>
        {error && <p className="error">{error}</p>}
        <div className="lpool-rows">
          {pool.map((p) => <PlayerRow key={p.player_id} p={p} from={null} onOpen={setDrawer} sold={sold.get(p.player_id)} />)}
        </div>
      </section>
      <section className="llists" aria-label="Lists">
        <div className="lnew">
          <h2>Lists</h2>
          <SymbolPicker value={newSym} onPick={setNewSym} />
          <div className="lnew-row">
            <span className="lsym-big">{newSym}</span>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New list name" aria-label="New list name"
              onKeyDown={(e) => { if (e.key === 'Enter') create() }} />
            <button onClick={create} disabled={!newName.trim()}>Add list</button>
          </div>
        </div>
        {ctx.lists.length === 0 && <p className="hint">No lists yet. Make one above.</p>}
        {ctx.lists.map((l) => (
          <ListBox key={l.id} list={l} open={openIds.includes(l.id)} onToggle={() => toggle(l.id)} byId={byId} sold={sold}
            onOpen={setDrawer} dropping={dropOn === l.id} setDropping={(v) => setDropOn(v ? l.id : null)}
            onDrop={(d) => { if (d.from !== l.id) ctx.add(l.id, d.pk) }} />
        ))}
      </section>
      {drawer != null && <PlayerDrawer playerId={drawer} query={q} onClose={closeDrawer} onOpenPlayer={setDrawer} />}
    </div>
  )
}
