import { useEffect, useMemo, useState } from 'react'
import { api, type Valuation, type ValuationOptions, type ValuationQuery, type ValuedPlayer } from '../../api/client'

const CAT_LABEL: Record<string, string> = {
  fg_pct: 'FG%', ft_pct: 'FT%', tpm: '3PM', pts: 'PTS', reb: 'REB', ast: 'AST', stl: 'STL', blk: 'BLK', tov: 'TO',
}

// Per-game value of a category from season totals. Percentages: makes / attempts.
function perGame(p: ValuedPlayer, cat: string): number | null {
  const s = p.stats
  if (cat === 'fg_pct') return s.fga ? (s.fgm ?? 0) / s.fga : null
  if (cat === 'ft_pct') return s.fta ? (s.ftm ?? 0) / s.fta : null
  return s.gp ? (s[cat] ?? 0) / s.gp : null
}

type Column = { key: string; label: string; value: (p: ValuedPlayer) => number | string | null; fmt?: (v: number) => string }

const money = (v: number) => `$${v.toFixed(0)}`
const one = (v: number) => v.toFixed(1)

function columns(cats: string[], view: 'stats' | 'z'): Column[] {
  const base: Column[] = [
    { key: 'rank', label: '#', value: (p) => p.rank },
    { key: 'name', label: 'Player', value: (p) => p.name },
    { key: 'team', label: 'Team', value: (p) => p.team },
    { key: 'pos', label: 'Pos', value: (p) => p.positions?.join(',') ?? null },
    { key: 'dollars', label: 'Model $', value: (p) => p.dollars, fmt: money },
    { key: 'total', label: 'Value', value: (p) => p.total, fmt: (v) => v.toFixed(2) },
    { key: 'y_av', label: 'Y! value', value: (p) => p.market.yahoo_auction_value, fmt: money },
    { key: 'y_cost', label: 'Y! avg cost', value: (p) => p.market.yahoo_average_cost, fmt: money },
    { key: 'e_cost', label: 'ESPN avg $', value: (p) => p.market.espn_average_cost, fmt: money },
    { key: 'gp', label: 'GP', value: (p) => p.stats.gp, fmt: (v) => v.toFixed(0) },
    { key: 'min', label: 'MIN', value: (p) => (p.stats.min != null && p.stats.gp ? p.stats.min / p.stats.gp : null), fmt: one },
  ]
  const catCols: Column[] = cats.map((c) =>
    view === 'z'
      ? { key: `z_${c}`, label: CAT_LABEL[c], value: (p) => p.z?.[c] ?? null, fmt: (v) => v.toFixed(2) }
      : { key: c, label: CAT_LABEL[c], value: (p) => perGame(p, c), fmt: c.endsWith('pct') ? (v) => v.toFixed(3) : one },
  )
  return [...base, ...catCols]
}

const baseKey = (q: { kind: string; source: string; season: string }) => `${q.kind}|${q.source}|${q.season}`

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

  if (!options || !query) return <p>{error ?? 'Loading...'}</p>

  const set = (patch: Partial<ValuationQuery>) => setQuery({ ...query, ...patch })
  const model = options.models.find((m) => m.key === query.model)
  const dollars = options.dollars.find((d) => d.key === query.dollars)
  const clickSort = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: !['rank', 'name', 'team', 'pos'].includes(key) }))

  return (
    <div>
      <div className="controls">
        <label>Base{' '}
          <select value={baseKey(query)} onChange={(e) => {
            const [kind, source, season] = e.target.value.split('|')
            set({ kind, source, season })
          }}>
            {options.bases.map((b) => (
              <option key={baseKey(b)} value={baseKey(b)}>
                {b.season} {b.source} {b.kind === 'projection' ? 'projection' : 'real stats'} ({b.players})
              </option>
            ))}
          </select>
        </label>
        <label>Basis{' '}
          <select value={query.basis} onChange={(e) => set({ basis: e.target.value })}>
            {options.basis.map((b) => <option key={b} value={b}>{b === 'per_game' ? 'per game' : b}</option>)}
          </select>
        </label>
        <label>Model{' '}
          <select value={query.model} onChange={(e) => set({ model: e.target.value })}>
            {options.models.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </label>
        <label>Dollars{' '}
          <select value={query.dollars} onChange={(e) => set({ dollars: e.target.value })}>
            {options.dollars.map((d) => <option key={d.key} value={d.key}>{d.key === 'savor' ? 'SAVOR' : 'plain'}</option>)}
          </select>
        </label>
        <label>Pool{' '}
          <select value={query.pool} onChange={(e) => set({ pool: Number(e.target.value) })}>
            {options.pools.map((p) => <option key={p ?? 0} value={p ?? 0}>{p ?? 'all'}</option>)}
          </select>
        </label>
        <input placeholder="Search player" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <p className="hint">{model?.label}: {model?.description} {dollars?.description}</p>
      {query.model === 'punt' && (
        <div className="controls">
          Punt:
          {cats.map((c) => (
            <label key={c}>
              <input type="checkbox" checked={query.punt.includes(c)} onChange={(e) =>
                set({ punt: e.target.checked ? [...query.punt, c] : query.punt.filter((x) => x !== c) })} />
              {CAT_LABEL[c]}
            </label>
          ))}
        </div>
      )}
      <div className="controls">
        Show:
        <label><input type="radio" checked={view === 'stats'} onChange={() => setView('stats')} /> per game stats</label>
        <label><input type="radio" checked={view === 'z'} onChange={() => setView('z')} /> category z</label>
        <span className="hint">{rows.length} players. ${data?.settings.budget} over {data?.settings.drafted} drafted players.</span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="table-wrap">
        <table className="values">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} onClick={() => clickSort(c.key)} className={sort.key === c.key ? 'sorted' : undefined}>
                  {c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.player_id}>
                {cols.map((c) => {
                  const v = c.value(p)
                  const text = v == null ? '-' : typeof v === 'number' && c.fmt ? c.fmt(v) : String(v)
                  const zClass = view === 'z' && c.key.startsWith('z_') && typeof v === 'number'
                    ? (v >= 1 ? 'pos' : v <= -1 ? 'neg' : undefined) : undefined
                  return (
                    <td key={c.key} className={zClass}>
                      {text}
                      {c.key === 'name' && p.injury && <span className="injury"> {p.injury}</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
