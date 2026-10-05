import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, type TagCount, type Valuation, type ValuationOptions, type ValuationQuery, type ValuedPlayer } from '../../api/client'
import { Headshot } from '../../components/Headshot'
import { PlayerDrawer } from '../../components/PlayerDrawer'
import { CAT_LABEL } from '../../lib/categories'

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
  sortValue?: (p: ValuedPlayer) => number | string | null // default: value
  fmt?: (v: number) => string
  heat?: (p: ValuedPlayer) => { z: number; full: number } | null // tint source; positive = good
}

const money = (v: number) => `$${v.toFixed(0)}`
const one = (v: number) => v.toFixed(1)

type UsageScale = { mean: number; sd: number }

/** Mean and spread of usage over the valued pool (players with a rank), for the usage tint. */
function usageScale(players: ValuedPlayer[]): UsageScale | null {
  const xs = players.filter((p) => p.rank != null && p.usg_pct != null).map((p) => p.usg_pct!)
  if (xs.length < 2) return null
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length)
  return sd > 0 ? { mean, sd } : null
}

function columns(cats: string[], view: 'stats' | 'z', usageSeason?: string, usage?: UsageScale | null): Column[] {
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
    { key: 'f_adp', label: 'Fantrax ADP', title: 'Fantrax average draft position (Fantrax has no auction prices; its scale runs longer than ESPN and Yahoo)',
      group: 'Market', num: true, value: (p) => p.market.fantrax_adp, fmt: one },
    { key: 'gp', label: 'GP', title: 'Games played', group: 'Playing time', num: true, className: 'group-start',
      value: (p) => p.stats.gp, fmt: (v) => v.toFixed(0) },
    { key: 'min', label: 'MIN', title: 'Minutes per game', group: 'Playing time', num: true,
      value: (p) => (p.stats.min != null && p.stats.gp ? p.stats.min / p.stats.gp : null), fmt: one },
    { key: 'usg', label: 'USG%', title: `Usage rate, ${usageSeason ?? 'last season'} (NBA.com)`, group: 'Playing time',
      num: true, value: (p) => (p.usg_pct == null ? null : p.usg_pct * 100), fmt: one,
      // Higher usage = green: more shots and counting stats. Tint vs the valued pool.
      heat: (p) => (p.usg_pct == null || !usage ? null : { z: (p.usg_pct - usage.mean) / usage.sd, full: Z_FULL }) },
  ]
  const catCols: Column[] = cats.map((c, i) => ({
    key: view === 'z' ? `z_${c}` : c,
    label: CAT_LABEL[c],
    group: 'Categories',
    num: true,
    className: i === 0 ? 'group-start' : undefined,
    value: view === 'z' ? (p) => p.z?.[c] ?? null : (p) => perGame(p, c),
    // FG% and FT% sort by team impact (z of makes - pool rate x attempts), not the raw rate:
    // 20 shots at 60% help a team more than 0.3 shots at 88%. The tint uses the same z.
    sortValue: c.endsWith('pct') ? (p) => p.z?.[c] ?? null : undefined,
    title: c.endsWith('pct') ? 'Shown: the rate. Color and sort: impact on the team rate (volume counts).' : undefined,
    fmt: view === 'z' ? (v) => v.toFixed(2) : c.endsWith('pct') ? (v) => v.toFixed(3) : one,
    heat: (p) => (p.z ? { z: p.z[c], full: Z_FULL } : null),
  }))
  return [...base, ...catCols]
}

const baseKey = (q: { kind: string; source: string; season: string }) => `${q.kind}|${q.source}|${q.season}`

const cellText = (col: Column, p: ValuedPlayer) => {
  const v = col.value(p)
  return v == null ? '-' : typeof v === 'number' && col.fmt ? col.fmt(v) : String(v)
}

/** Tint of a heat cell: class names and the --a strength, or null for a plain cell. */
function heatOf(col: Column, p: ValuedPlayer): { cls: string; style: CSSProperties } | null {
  const h = col.heat?.(p)
  if (!h || col.value(p) == null) return null
  const a = Math.min(Math.abs(h.z) / h.full, 1)
  const strong = Math.abs(h.z) / h.full >= Z_STRONG / Z_FULL
  return { cls: ['heat', h.z >= 0 ? 'good' : 'bad', strong && 'strong'].filter(Boolean).join(' '),
    style: { '--a': a.toFixed(3) } as CSSProperties }
}

function Cell({ col, p }: { col: Column; p: ValuedPlayer }) {
  const text = cellText(col, p)
  const h = heatOf(col, p)
  if (h) {
    return <td className={[h.cls, col.className].filter(Boolean).join(' ')}><span style={h.style}>{text}</span></td>
  }
  const cls = [col.num && 'num', col.className].filter(Boolean).join(' ') || undefined
  return (
    <td className={cls}>
      {col.key === 'name'
        ? <span className="name-cell"><Headshot nbaId={p.nba_id} name={p.name} />
          <button className="link" aria-haspopup="dialog">{text}</button></span>
        : text}
      {col.key === 'name' && p.injury && <span className="injury" title="Injury status (Yahoo)">{p.injury}</span>}
    </td>
  )
}

// Narrow screens get a two-line list instead of the wide table: no side scroll.
const NARROW = '(max-width: 720px)'

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches)
  useEffect(() => {
    const m = window.matchMedia(NARROW)
    const on = () => setNarrow(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return narrow
}

const TOP_KEYS = ['dollars', 'total', 'y_cost', 'e_cost'] as const
const TOP_LABEL: Record<string, string> = { dollars: '$', total: 'Value', y_cost: 'Y avg', e_cost: 'E avg' }

function MobileList({ rows, cols, cats, sort, onSort, onOpen }: {
  rows: ValuedPlayer[]; cols: Column[]; cats: Column[]; sort: { key: string; desc: boolean }
  onSort: (key: string) => void; onOpen: (id: number) => void
}) {
  const byKey = new Map(cols.map((c) => [c.key, c]))
  const top = TOP_KEYS.map((k) => byKey.get(k)!)
  const arrow = (k: string) => (sort.key === k ? (sort.desc ? ' ↓' : ' ↑') : '')
  const head = (k: string, label: string) => (
    <button className={sort.key === k ? 'sorted' : undefined} onClick={() => onSort(k)}>{label}{arrow(k)}</button>
  )
  const sub = (p: ValuedPlayer) => {
    const min = byKey.get('min')!
    return [p.team ?? 'FA', p.positions?.join(',') ?? '-', p.stats.gp != null ? `${p.stats.gp.toFixed(0)} gp` : null,
      min.value(p) != null ? `${cellText(min, p)} min` : null].filter(Boolean).join(' · ')
  }
  const usgChip = (p: ValuedPlayer) => {
    const usg = byKey.get('usg')!
    if (usg.value(p) == null) return null
    const h = heatOf(usg, p)
    return <span className={['musg', h?.cls].filter(Boolean).join(' ')} title="Usage rate"><span style={h?.style}>
      {cellText(usg, p)}% usg</span></span>
  }
  return (
    <div className="mlist">
      <div className="mrow mhead">
        <div className="mtop">
          {head('rank', '#')}<span />{head('name', 'Player')}
          {top.map((c) => <span key={c.key} className="mnum">{head(c.key, TOP_LABEL[c.key])}</span>)}
        </div>
        <div className="mcats">{cats.map((c) => <span key={c.key}>{head(c.key, c.label)}</span>)}</div>
      </div>
      {rows.map((p) => (
        <div key={p.player_id} className="mrow" role="button" tabIndex={0} onClick={() => onOpen(p.player_id)}
          onKeyDown={(e) => { if (e.key === 'Enter') onOpen(p.player_id) }}>
          <div className="mtop">
            <span className="mrank">{p.rank ?? '-'}</span>
            <Headshot nbaId={p.nba_id} name={p.name} />
            <span className="mname">
              <span className="mplayer">{p.name}{p.injury && <span className="injury">{p.injury}</span>}</span>
              <small>{sub(p)} {usgChip(p)}</small>
            </span>
            {top.map((c) => {
              const h = heatOf(c, p)
              return <span key={c.key} className={['mnum', c.key === 'dollars' && 'mdollars', h?.cls].filter(Boolean).join(' ')}>
                <span style={h?.style}>{cellText(c, p)}</span></span>
            })}
          </div>
          <div className="mcats">
            {cats.map((c) => {
              const h = heatOf(c, p)
              // ".574" instead of "0.574": percentages fit the narrow cell.
              return <span key={c.key} className={h?.cls}><small className="mcat" aria-hidden="true">{c.label}</small><span style={h?.style}>{c.key.endsWith('pct') ? cellText(c, p).replace(/^0\./, '.') : cellText(c, p)}</span></span>
            })}
          </div>
        </div>
      ))}
    </div>
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
  const [drawer, setDrawer] = useState<number | null>(null)
  const [tags, setTags] = useState<TagCount[]>([])
  const [tag, setTag] = useState('')
  const [tagLoaded, setTagLoaded] = useState<{ tag: string; ids: Set<number> } | null>(null)
  // Before the tag's players arrive the list is empty, not unfiltered.
  const tagged = useMemo(() => (!tag ? null : tagLoaded?.tag === tag ? tagLoaded.ids : new Set<number>()),
    [tag, tagLoaded])
  const narrow = useNarrow()
  const closeDrawer = useCallback(() => setDrawer(null), [])

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

  useEffect(() => { api.tags().then(setTags).catch(() => { /* tag filter stays empty */ }) }, [])

  useEffect(() => {
    if (!tag) return
    let alive = true
    api.tagPlayers(tag)
      .then((ps) => { if (alive) setTagLoaded({ tag, ids: new Set(ps.map((x) => x.player_pk)) }) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [tag])

  useEffect(() => {
    if (!query) return
    let alive = true
    api.valuation(query)
      .then((v) => { if (alive) { setData(v); setError(null) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [query])

  const cats = useMemo(() => options?.categories ?? [], [options])
  const cols = useMemo(() => columns(cats, view, data?.settings.usage_season, data && usageScale(data.players)),
    [cats, view, data])
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
    const list = data.players.filter((p) => (!needle || p.name.toLowerCase().includes(needle))
      && (!tagged || tagged.has(p.player_id)))
    return [...list].sort((a, b) => {
      const key = col.sortValue ?? col.value
      const x = key(a), y = key(b)
      if (x == null) return 1
      if (y == null) return -1
      const r = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number)
      return sort.desc ? -r : r
    })
  }, [data, cols, sort, search, tagged])

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
                {b.label ?? `${b.season} ${b.source.toUpperCase()} ${b.kind === 'projection' ? 'projection' : 'real stats'} (${b.players})`}
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
        <label>Tag
          <select value={tag} onChange={(e) => setTag(e.target.value)}>
            <option value="">All players</option>
            {tags.map((t) => <option key={t.tag} value={t.tag}>{t.tag} ({t.count})</option>)}
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
      {narrow ? (
        <MobileList rows={rows} cols={cols} cats={cols.filter((c) => c.group === 'Categories')} sort={sort}
          onSort={clickSort} onOpen={setDrawer} />
      ) : (
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
              <tr key={p.player_id} className="clickable" onClick={() => setDrawer(p.player_id)}>
                {cols.map((c) => <Cell key={c.key} col={c} p={p} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
      {drawer != null && (
        <PlayerDrawer playerId={drawer} query={query} onClose={closeDrawer} onOpenPlayer={setDrawer} />
      )}
    </div>
  )
}
