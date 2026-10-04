import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, type Valuation, type ValuationOptions, type ValuationQuery, type ValuedPlayer } from '../../api/client'

const CAT_LABEL: Record<string, string> = {
  fg_pct: 'FG%', ft_pct: 'FT%', tpm: '3PM', pts: 'PTS', reb: 'REB', ast: 'AST', stl: 'STL', blk: 'BLK', tov: 'TO',
}
// |z| at which a cell reaches full color. Bold text from this |z| on.
const Z_FULL = 2.5
const Z_STRONG = 1.5
// Model value (sum of z) at which the value cell reaches full color.
const TOTAL_FULL = 10

// Per-game value of a category from season totals. Percentages: makes / attempts.
function perGame(p: ValuedPlayer, cat: string): number | null {
  const s = p.stats
  if (cat === 'fg_pct') return s.fga ? (s.fgm ?? 0) / s.fga : null
  if (cat === 'ft_pct') return s.fta ? (s.ftm ?? 0) / s.fta : null
  return s.gp ? (s[cat] ?? 0) / s.gp : null
}

type Group = 'Player' | 'Value' | 'Market' | 'Playing time' | 'Categories'

type Column = {
  key: string
  label: string
  title?: string
  group: Group
  num?: boolean
  className?: string
  value: (p: ValuedPlayer) => number | string | null
  fmt?: (v: number) => string
  heat?: (p: ValuedPlayer) => { z: number; full: number } | null // tint source; positive = good
}

const money = (v: number) => `$${v.toFixed(0)}`
const one = (v: number) => v.toFixed(1)

function columns(cats: string[], view: 'stats' | 'z'): Column[] {
  const base: Column[] = [
    { key: 'rank', label: '#', group: 'Player', num: true, className: 'rank', value: (p) => p.rank },
    { key: 'name', label: 'Player', group: 'Player', className: 'name sticky', value: (p) => p.name },
    { key: 'team', label: 'Team', group: 'Player', value: (p) => p.team },
    { key: 'pos', label: 'Pos', group: 'Player', value: (p) => p.positions?.join(',') ?? null },
    { key: 'dollars', label: 'Model $', title: 'Auction dollars from the model', group: 'Value', num: true,
      className: 'dollars group-start', value: (p) => p.dollars, fmt: money },
    { key: 'total', label: 'Value', title: 'Model value: sum of the category z values the model counts', group: 'Value',
      num: true, value: (p) => p.total, fmt: (v) => v.toFixed(2),
      heat: (p) => (p.total == null ? null : { z: p.total, full: TOTAL_FULL }) },
    { key: 'y_av', label: 'Yahoo value', group: 'Market', num: true, className: 'group-start',
      value: (p) => p.market.yahoo_auction_value, fmt: money },
    { key: 'y_cost', label: 'Yahoo avg', title: 'Yahoo average auction cost', group: 'Market', num: true,
      value: (p) => p.market.yahoo_average_cost, fmt: money },
    { key: 'e_cost', label: 'ESPN avg', title: 'ESPN average auction price', group: 'Market', num: true,
      value: (p) => p.market.espn_average_cost, fmt: money },
    { key: 'gp', label: 'GP', title: 'Games played', group: 'Playing time', num: true, className: 'group-start',
      value: (p) => p.stats.gp, fmt: (v) => v.toFixed(0) },
    { key: 'min', label: 'MIN', title: 'Minutes per game', group: 'Playing time', num: true,
      value: (p) => (p.stats.min != null && p.stats.gp ? p.stats.min / p.stats.gp : null), fmt: one },
  ]
  const catCols: Column[] = cats.map((c, i) => ({
    key: view === 'z' ? `z_${c}` : c,
    label: CAT_LABEL[c],
    group: 'Categories',
    num: true,
    className: i === 0 ? 'group-start' : undefined,
    value: view === 'z' ? (p) => p.z?.[c] ?? null : (p) => perGame(p, c),
    fmt: view === 'z' ? (v) => v.toFixed(2) : c.endsWith('pct') ? (v) => v.toFixed(3) : one,
    heat: (p) => (p.z ? { z: p.z[c], full: Z_FULL } : null),
  }))
  return [...base, ...catCols]
}

const baseKey = (q: { kind: string; source: string; season: string }) => `${q.kind}|${q.source}|${q.season}`

function Cell({ col, p }: { col: Column; p: ValuedPlayer }) {
  const v = col.value(p)
  const text = v == null ? '-' : typeof v === 'number' && col.fmt ? col.fmt(v) : String(v)
  const h = col.heat?.(p)
  if (h && v != null) {
    const a = Math.min(Math.abs(h.z) / h.full, 1)
    const tone = h.z >= 0 ? 'good' : 'bad'
    const strong = Math.abs(h.z) / h.full >= Z_STRONG / Z_FULL
    const cls = ['heat', tone, strong && 'strong', col.className].filter(Boolean).join(' ')
    return <td className={cls}><span style={{ '--a': a.toFixed(3) } as CSSProperties}>{text}</span></td>
  }
  const cls = [col.num && 'num', col.className].filter(Boolean).join(' ') || undefined
  return (
    <td className={cls}>
      {text}
      {col.key === 'name' && p.injury && <span className="injury" title="Injury status (Yahoo)">{p.injury}</span>}
    </td>
  )
}

export function PlayerValues() {
  const [options, setOptions] = useState<ValuationOptions | null>(null)
  const [query, setQuery] = useState<ValuationQuery | null>(null)
  const [data, setData] = useState<Valuation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'stats' | 'z'>('stats')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: 'rank', desc: false })

  useEffect(() => {
    api.valuationOptions()
      .then((o) => {
        setOptions(o)
        const d = o.defaults
        setQuery({ kind: d.kind, source: d.source, season: d.season, basis: d.basis, model: d.model,
          dollars: d.dollars, pool: d.pool, punt: [] })
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!query) return
    let alive = true
    api.valuation(query)
      .then((v) => { if (alive) { setData(v); setError(null) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [query])

  const cats = useMemo(() => options?.categories ?? [], [options])
  const cols = useMemo(() => columns(cats, view), [cats, view])
  const groups = useMemo(() => {
    const out: { name: Group; span: number }[] = []
    for (const c of cols) {
      const last = out[out.length - 1]
      if (last?.name === c.group) last.span++
      else out.push({ name: c.group, span: 1 })
    }
    return out
  }, [cols])

  const rows = useMemo(() => {
    if (!data) return []
    const col = cols.find((c) => c.key === sort.key) ?? cols[0]
    const needle = search.trim().toLowerCase()
    const list = data.players.filter((p) => !needle || p.name.toLowerCase().includes(needle))
    return [...list].sort((a, b) => {
      const x = col.value(a), y = col.value(b)
      if (x == null) return 1
      if (y == null) return -1
      const r = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number)
      return sort.desc ? -r : r
    })
  }, [data, cols, sort, search])

  if (!options || !query) return <p className={error ? 'error' : 'hint'}>{error ?? 'Loading values...'}</p>

  const set = (patch: Partial<ValuationQuery>) => setQuery({ ...query, ...patch })
  const model = options.models.find((m) => m.key === query.model)
  const dollars = options.dollars.find((d) => d.key === query.dollars)
  const clickSort = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: !['rank', 'name', 'team', 'pos'].includes(key) }))

  return (
    <div>
      <div className="controls">
        <label>Base
          <select value={baseKey(query)} onChange={(e) => {
            const [kind, source, season] = e.target.value.split('|')
            set({ kind, source, season })
          }}>
            {options.bases.map((b) => (
              <option key={baseKey(b)} value={baseKey(b)}>
                {b.season} {b.source.toUpperCase()} {b.kind === 'projection' ? 'projection' : 'real stats'} ({b.players})
              </option>
            ))}
          </select>
        </label>
        <label>Basis
          <select value={query.basis} onChange={(e) => set({ basis: e.target.value })}>
            {options.basis.map((b) => <option key={b} value={b}>{b === 'per_game' ? 'Per game' : 'Season totals'}</option>)}
          </select>
        </label>
        <label>Model
          <select value={query.model} onChange={(e) => set({ model: e.target.value })}>
            {options.models.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </label>
        <label>Dollars
          <select value={query.dollars} onChange={(e) => set({ dollars: e.target.value })}>
            {options.dollars.map((d) => <option key={d.key} value={d.key}>{d.key === 'savor' ? 'SAVOR' : 'Plain'}</option>)}
          </select>
        </label>
        <label>Pool
          <select value={query.pool} onChange={(e) => set({ pool: Number(e.target.value) })}>
            {options.pools.map((p) => <option key={p ?? 0} value={p ?? 0}>{p ? `Top ${p}` : 'All players'}</option>)}
          </select>
        </label>
        <input className="search" type="search" placeholder="Find a player" aria-label="Find a player"
          value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <p className="hint"><strong>{model?.label}.</strong> {model?.description} {dollars?.description}</p>
      {query.model === 'punt' && (
        <div className="punts">
          Turn off:
          {cats.map((c) => (
            <label key={c} className="chip">
              <input type="checkbox" checked={query.punt.includes(c)} onChange={(e) =>
                set({ punt: e.target.checked ? [...query.punt, c] : query.punt.filter((x) => x !== c) })} />
              {CAT_LABEL[c]}
            </label>
          ))}
        </div>
      )}
      <div className="table-foot">
        <div className="segmented" role="radiogroup" aria-label="Category cells">
          <button role="radio" aria-checked={view === 'stats'} className={view === 'stats' ? 'on' : undefined}
            onClick={() => setView('stats')}>Per game stats</button>
          <button role="radio" aria-checked={view === 'z'} className={view === 'z' ? 'on' : undefined}
            onClick={() => setView('z')}>Category z</button>
        </div>
        <span className="legend">
          Below pool average <span className="scale" aria-hidden="true" /> Above
        </span>
        <span className="legend">
          {rows.length} players, ${data?.settings.budget} over {data?.settings.drafted} drafted
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="table-wrap">
        <table className="values">
          <thead>
            <tr className="groups">
              {groups.map((g) => <th key={g.name} colSpan={g.span} scope="colgroup">{g.name === 'Player' ? '' : g.name}</th>)}
            </tr>
            <tr className="cols">
              {cols.map((c) => (
                <th key={c.key} scope="col" title={c.title} tabIndex={0}
                  aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : undefined}
                  className={[c.num && 'num', sort.key === c.key && 'sorted', c.className?.includes('sticky') && 'sticky',
                    c.className?.includes('group-start') && 'group-start'].filter(Boolean).join(' ') || undefined}
                  onClick={() => clickSort(c.key)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); clickSort(c.key) } }}>
                  {c.label}{sort.key === c.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.player_id}>
                {cols.map((c) => <Cell key={c.key} col={c} p={p} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
