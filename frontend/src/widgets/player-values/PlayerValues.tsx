import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { api, type TagCount, type Valuation, type ValuationOptions, type ValuationQuery, type ValuedPlayer } from '../../api/client'
import { Headshot } from '../../components/Headshot'
import { PlayerDrawer } from '../../components/PlayerDrawer'
import { CAT_LABEL } from '../../lib/categories'
import { useLiveBoard } from '../../lib/liveBoard'
import { useSynced } from '../../lib/synced'
import { FocusPanel } from './draft/FocusPanel'
import { LeagueOverview } from './draft/LeagueOverview'
import { buildTeams } from './draft/model'

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

type Group = 'Player' | 'Value' | 'Room' | 'Market' | 'Playing time' | 'Categories'

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
  render?: (p: ValuedPlayer) => ReactNode // custom cell content (sold players in a live draft)
  sub?: (p: ValuedPlayer) => string | null // small second line (FG% and FT%: attempts per game)
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

// Opportunity (static price minus market price) at which the cell reaches full color.
const OPP_FULL = 15

// Prices (docs/modules/pricing.md): two references, nothing moves during a draft (user, 2026-10-06).
// Static price = our model's dollars. Market price = Yahoo avg x2, ESPN avg, Fantrax ADP on Yahoo's scale.
// Opportunity = static price - market price.
function opportunity(p: ValuedPlayer): number | null {
  const m = p.market.market_price
  return p.dollars == null || m == null ? null : p.dollars - m
}

function columns(cats: string[], view: 'stats' | 'z', usageSeason?: string, usage?: UsageScale | null,
  sold?: Map<number, string>): Column[] {
  const base: Column[] = [
    { key: 'rank', label: '#', group: 'Player', num: true, className: 'rank', value: (p) => p.rank },
    { key: 'name', label: 'Player', group: 'Player', className: 'name sticky', value: (p) => p.name },
    { key: 'team', label: 'Team', group: 'Player', value: (p) => p.team },
    { key: 'pos', label: 'Pos', group: 'Player', value: (p) => p.positions?.join(',') ?? null },
    { key: 'dollars', label: 'Static price', title: 'Our model\'s auction dollars (model and dollar method above). Ours, fixed before the draft.', group: 'Value', num: true,
      className: 'dollars group-start', value: (p) => p.dollars, fmt: money },
    { key: 'total', label: 'Value', title: 'Model value: sum of the category z values the model counts', group: 'Value',
      num: true, value: (p) => p.total, fmt: (v) => v.toFixed(2),
      heat: (p) => (p.total == null ? null : { z: p.total, full: TOTAL_FULL }) },
    { key: 'room_exp', label: 'Market price', group: 'Room', num: true, className: 'group-start',
      title: 'What the market pays: Yahoo avg x2, ESPN avg, Fantrax ADP on Yahoo\'s dollar scale. During a live draft: the price paid and the buyer for sold players.',
      value: (p) => p.market.market_price, fmt: money,
      render: sold ? (p) => {
        const s = sold.get(p.player_id)
        return s ? <span className="sold-to">{s}</span> : (p.market.market_price == null ? '-' : money(p.market.market_price))
      } : undefined },
    { key: 'room_opp', label: 'Opportunity', group: 'Room', num: true,
      title: 'Static price minus market price. Green: the market pays less than our model sees. Red: the market pays more than our model sees (stay away).',
      value: (p) => opportunity(p), fmt: (v) => `${v >= 0 ? '+' : '-'}$${Math.abs(v).toFixed(0)}`,
      heat: (p) => { const o = opportunity(p); return o == null ? null : { z: o, full: OPP_FULL } } },
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
    // Volume next to the rate (user, 2026-10-06): attempts per game.
    sub: c.endsWith('pct') ? (p) => {
      const att = c === 'fg_pct' ? p.stats.fga : p.stats.fta
      return att != null && p.stats.gp ? `(${(att / p.stats.gp).toFixed(1)})` : null
    } : undefined,
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

function Cell({ col, p, rowSpan, extra }: { col: Column; p: ValuedPlayer; rowSpan?: number; extra?: string }) {
  const text = cellText(col, p)
  const h = heatOf(col, p)
  if (h) {
    const sub = col.sub?.(p)
    return <td rowSpan={rowSpan} className={[h.cls, col.className, extra].filter(Boolean).join(' ')}><span style={h.style}>{text}{sub && <small className="vol">{sub}</small>}</span></td>
  }
  const cls = [col.num && 'num', col.className, extra].filter(Boolean).join(' ') || undefined
  return (
    <td className={cls} rowSpan={rowSpan}>
      {col.render ? col.render(p) : col.key === 'name'
        ? <span className="name-cell"><Headshot nbaId={p.nba_id} name={p.name} />
          <button className="link" aria-haspopup="dialog" data-open-drawer="1">{text}</button></span>
        : text}
      {col.key === 'name' && p.injury && <span className="injury" title="Injury status (Yahoo)">{p.injury}</span>}
    </td>
  )
}

// Wide table, two lines per player (user, 2026-10-05: see everything without side scroll).
// Left: pairs of columns stacked (top / bottom). Right: the categories, one tall cell each.
const PAIRS: [string, string | null][] = [
  ['team', 'pos'], ['gp', 'min'], ['usg', null], ['dollars', 'total'], ['room_exp', null],
  ['room_opp', null], ['y_cost', 'y_av'], ['e_cost', 'f_adp'],
]

function SortTh({ c, sort, onSort, rowSpan, extra }: {
  c: Column | undefined; sort: { key: string; desc: boolean }; onSort: (k: string) => void
  rowSpan?: number; extra?: string
}) {
  if (!c) return <th rowSpan={rowSpan} className={extra} />
  return (
    <th scope="col" title={c.title} tabIndex={0} rowSpan={rowSpan}
      aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : undefined}
      className={[c.num && 'num', sort.key === c.key && 'sorted', extra].filter(Boolean).join(' ') || undefined}
      onClick={() => onSort(c.key)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(c.key) } }}>
      {c.label}{sort.key === c.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
    </th>
  )
}

function TwoLineTable({ rows, cols, sort, onSort, onOpen, onName, sold }: {
  rows: ValuedPlayer[]; cols: Column[]; sort: { key: string; desc: boolean }
  onSort: (k: string) => void; onOpen: (id: number) => void; sold?: Map<number, string>
  onName?: (id: number) => void // name click (live draft: the row selects, the name opens the drawer)
}) {
  const byKey = new Map(cols.map((c) => [c.key, c]))
  const pairs = PAIRS.filter(([t, b]) => byKey.has(t) || (b && byKey.has(b)))
  const cats = cols.filter((c) => c.group === 'Categories')
  const rank = byKey.get('rank')!
  const name = byKey.get('name')!
  const empty = (k: string | null) => (k && byKey.get(k) ? null : <td className="pair-empty" />)
  return (
    <table className="values two-line">
      <thead>
        <tr className="top">
          <SortTh c={rank} sort={sort} onSort={onSort} rowSpan={2} />
          <SortTh c={name} sort={sort} onSort={onSort} rowSpan={2} extra="sticky" />
          {pairs.map(([t, b], i) => <SortTh key={t} c={byKey.get(t)} sort={sort} onSort={onSort} rowSpan={b ? undefined : 2}
            extra={[i === 0 || t === 'dollars' || t === 'y_cost' ? 'group-start' : '', b ? '' : 'cat'].join(' ').trim() || undefined} />)}
          {cats.map((c, i) => <SortTh key={c.key} c={c} sort={sort} onSort={onSort} rowSpan={2}
            extra={['cat', i === 0 ? 'group-start' : ''].join(' ')} />)}
        </tr>
        <tr className="bottom">
          {pairs.filter(([, b]) => b).map(([t, b]) => <SortTh key={`${t}-b`} c={byKey.get(b!)} sort={sort} onSort={onSort}
            extra={t === 'team' || t === 'dollars' || t === 'y_cost' ? 'group-start' : undefined} />)}
        </tr>
      </thead>
      {rows.map((p) => (
        <tbody key={p.player_id} className={sold?.has(p.player_id) ? 'player sold' : 'player'}
          onClick={(e) => (onName && (e.target as HTMLElement).closest('[data-open-drawer]') ? onName : onOpen)(p.player_id)}>
          <tr className="top">
            <td className="rank num" rowSpan={2}>{cellText(rank, p)}</td>
            <Cell col={name} p={p} rowSpan={2} />
            {pairs.map(([t, b]) => (byKey.get(t) ? <Cell key={t} col={byKey.get(t)!} p={p} rowSpan={b ? undefined : 2}
              extra={b ? undefined : 'cat'} /> : empty(t)))}
            {cats.map((c) => <Cell key={c.key} col={c} p={p} rowSpan={2} extra="cat" />)}
          </tr>
          <tr className="bottom">
            {pairs.filter(([, b]) => b).map(([t, b]) => (byKey.get(b!) ? <Cell key={`${t}-b`} col={byKey.get(b!)!} p={p} />
              : <td key={`${t}-b`} className="pair-empty" />))}
          </tr>
        </tbody>
      ))}
    </table>
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

// Views (user, 2026-10-06): 'draft' = focus panel and table, 'league' = H2H and teams, 'player' = focus
// panel only. Open them in separate tabs side by side; the selected player and the table settings follow
// across tabs.
export type View = 'draft' | 'league' | 'player'

export function PlayerValues({ mode = 'draft' }: { mode?: View }) {
  const [options, setOptions] = useState<ValuationOptions | null>(null)
  const [query, setQuery] = useSynced<ValuationQuery | null>('pv-query', null)
  const [data, setData] = useState<Valuation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'stats' | 'z'>('stats')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: 'rank', desc: false })
  const [drawerId, setDrawerId] = useState<number | null>(null)
  const [minimized, setMinimized] = useState(false)
  const drawer = minimized ? null : drawerId
  // Opening a player always shows the window again, also after minimize.
  const setDrawer = useCallback((id: number | null) => { setDrawerId(id); setMinimized(false) }, [])
  const [tags, setTags] = useState<TagCount[]>([])
  const [tag, setTag] = useState('')
  const [tagLoaded, setTagLoaded] = useState<{ tag: string; ids: Set<number> } | null>(null)
  // Before the tag's players arrive the list is empty, not unfiltered.
  const tagged = useMemo(() => (!tag ? null : tagLoaded?.tag === tag ? tagLoaded.ids : new Set<number>()),
    [tag, tagLoaded])
  const narrow = useNarrow()
  const live = useLiveBoard()
  const board = live.board
  const [onlyUnsold, setOnlyUnsold] = useState(false)
  // Sold player -> "$76 Team name" (faded rows, price cell).
  const sold = useMemo(() => {
    if (!board) return undefined
    const name = new Map(board.teams.map((t) => [t.team_id, t.name ?? `Team ${t.team_id}`]))
    return new Map(board.picks.filter((p) => p.player_pk != null)
      .map((p) => [p.player_pk!, `$${p.price} ${name.get(p.team_id)}`]))
  }, [board])
  // Player in the top panel: the one the user clicked (until the next nomination), else the nominated one.
  const [tried, setTried] = useSynced<{ pk: number; nom: string | null } | null>('pv-tried', null)
  const nomKey = board?.nomination ? `${board.nomination.yahoo_id}` : null
  const closeDrawer = useCallback(() => setDrawer(null), [setDrawer])

  useEffect(() => {
    api.valuationOptions()
      .then((o) => {
        setOptions(o)
        const d = o.defaults
        // Keep a query another tab already chose, when its base still exists.
        const ok = (q: ValuationQuery | null) => q && o.bases.some((b) => b.kind === q.kind && b.source === q.source && b.season === q.season)
        setQuery(ok(query) ? query : { kind: d.kind, source: d.source, season: d.season, basis: d.basis, model: d.model,
          dollars: d.dollars, pool: d.pool, punt: [] })
      })
      .catch((e: Error) => setError(e.message))
    // Runs once on load: reads the query another tab may have stored.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const byId = useMemo(() => new Map((data?.players ?? []).map((p) => [p.player_id, p])), [data])
  const teams = useMemo(() => (board ? buildTeams(board, byId) : []), [board, byId])
  const cols = useMemo(() => columns(cats, view, data?.settings.usage_season, data && usageScale(data.players), sold),
    [cats, view, data, sold])

  const rows = useMemo(() => {
    if (!data) return []
    const col = cols.find((c) => c.key === sort.key) ?? cols[0]
    const needle = search.trim().toLowerCase()
    const list = data.players.filter((p) => (!needle || p.name.toLowerCase().includes(needle))
      && (!tagged || tagged.has(p.player_id)) && (!onlyUnsold || !sold?.has(p.player_id)))
    return [...list].sort((a, b) => {
      const key = col.sortValue ?? col.value
      const x = key(a), y = key(b)
      if (x == null) return 1
      if (y == null) return -1
      const r = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number)
      return sort.desc ? -r : r
    })
  }, [data, cols, sort, search, tagged, onlyUnsold, sold])

  const focusPk = tried && tried.nom === nomKey ? tried.pk : board?.nomination?.player_pk ?? null
  const focusRow = focusPk != null ? byId.get(focusPk) ?? null : null
  const nominatedFocus = !(tried && tried.nom === nomKey) && !!board?.nomination
  const openRow = board ? (pk: number) => setTried({ pk, nom: nomKey }) : setDrawer

  if (!options || !query) return <p className={error ? 'error' : 'hint'}>{error ?? 'Loading values...'}</p>

  const set = (patch: Partial<ValuationQuery>) => setQuery({ ...query, ...patch })
  const model = options.models.find((m) => m.key === query.model)
  const dollars = options.dollars.find((d) => d.key === query.dollars)
  const clickSort = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: !['rank', 'name', 'team', 'pos'].includes(key) }))

  return (
    <div className={`pv pv-${mode}`}>
      {live.drafts.length > 0 && mode !== 'draft' && (
        <div className="live-strip">
          <label>Live draft
            <select value={live.auto ? 'auto' : live.leagueId}
              onChange={(e) => live.setChoice(e.target.value === 'auto' ? null : e.target.value)}>
              <option value="auto">Automatic (active draft){live.auto && live.leagueId ? `: ${live.leagueId}` : live.auto ? ': none' : ''}</option>
              <option value="">Off</option>
              {live.drafts.map((d) => <option key={d.league_id} value={d.league_id}>{d.league_id} ({d.kind}, {d.picks} picks)</option>)}
            </select>
          </label>
          {!board && <span className="hint">No live draft followed. This view fills when a draft is followed.</span>}
        </div>
      )}
      {mode !== 'league' && <>
      {board && (focusPk != null || board.nomination) && (
        <FocusPanel row={focusRow} name={board.nomination?.name ?? board.nomination?.yahoo_id ?? ''}
          bid={nominatedFocus && board.nomination ? { amount: board.nomination.high_bid,
            team: teams.find((t) => t.team_id === board.nomination!.high_team_id)?.label ?? '' } : null}
          nominated={nominatedFocus} teams={teams}
          onOpen={() => focusPk != null && setDrawer(focusPk)}
          onClear={!nominatedFocus && board.nomination ? () => setTried(null) : undefined} />
      )}
      {/* Keeps the panel's space while no player is in focus, so the table does not jump (user, 2026-10-06). */}
      {mode === 'draft' && board && focusPk == null && !board.nomination && (
        <section className="focus-panel focus-empty"><p className="hint">Waiting for the next nomination. Click a row to try a player.</p></section>
      )}
      </>}
      {mode === 'draft' && <>
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
      {live.drafts.length > 0 && (
        <div className="live-strip">
          <label>Live draft
            <select value={live.auto ? 'auto' : live.leagueId}
              onChange={(e) => live.setChoice(e.target.value === 'auto' ? null : e.target.value)}>
              <option value="auto">Automatic (active draft){live.auto && live.leagueId ? `: ${live.leagueId}` : live.auto ? ': none' : ''}</option>
              <option value="">Off</option>
              {live.drafts.map((d) => <option key={d.league_id} value={d.league_id}>{d.league_id} ({d.kind}, {d.picks} picks)</option>)}
            </select>
          </label>
          {board && (
            <>
              <span>{board.picks.length} sold</span>
              {(() => {
                const me = board.teams.find((t) => t.mine)
                return me ? <span title="Your money left minus 1 USD per other open slot"><strong>My max bid: ${me.max_bid}</strong> (${me.money_left} left, {me.open_slots} open slots)</span> : null
              })()}
              <label className="toggle"><input type="checkbox" checked={onlyUnsold} onChange={(e) => setOnlyUnsold(e.target.checked)} />Only unsold</label>
            </>
          )}
        </div>
      )}
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
        <TwoLineTable rows={rows} cols={cols} sort={sort} onSort={clickSort} onOpen={openRow} onName={board ? setDrawer : undefined} sold={sold} />
      </div>
      )}
      </>}
      {mode === 'league' && board && <LeagueOverview teams={teams} focus={focusRow} pool={data?.players ?? []} sold={sold} />}
      {drawer != null && (
        <PlayerDrawer playerId={drawer} query={query} onClose={closeDrawer} onOpenPlayer={setDrawer}
          onMinimize={() => setMinimized(true)} />
      )}
      {minimized && drawerId != null && (
        <button className="drawer-pill" onClick={() => setMinimized(false)} title="Open the player window again">
          ▣ {byId.get(drawerId)?.name ?? 'Player'}
        </button>
      )}
    </div>
  )
}
