// Historical price curve (user, 2026-10-18): what the followed mock auction rooms paid for each player, as a
// share of the expected price, over every followed mock. One point per player: all his sales together,
// paid / expected dollar weighted. Updates as new mocks are followed. Players already sold in the live
// draft are greyed out, so the unsold ones are easy to find. The live League view curve stays separate.
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, type LiveBoard, type LiveDraftSummary, type ValuationQuery, type ValuedPlayer } from '../../api/client'
import { useLiveBoard } from '../../lib/liveBoard'
import { useSynced } from '../../lib/synced'

type Ref = 'market' | 'ours'
type Sale = { d: number; pk: number; paid: number; exp: number; mine: boolean }
type Dot = { pk: number; name: string; nbaId: string | null; n: number; paid: number; exp: number; pct: number; lo: number; hi: number; d: number }

// Players expected under this price are left out: a ratio on $0-1 says nothing.
const MIN_EXPECTED = 2
// Price bands of the trend line (expected price, USD). Assumed.
const BANDS = [2, 5, 10, 20, 35, 55, Infinity]
const LIST_MS = 30000
const photo = (nbaId: string) => `https://cdn.nba.com/headshots/nba/latest/260x190/${nbaId}.png`
const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('')
const bandLabel = (i: number) => `$${BANDS[i]}${BANDS[i + 1] === Infinity ? '+' : `-${BANDS[i + 1]}`}`

type Band = { i: number; n: number; paid: number; exp: number; x: number; pct: number; median: number }

function bands(sales: Sale[]): Band[] {
  const out: Band[] = []
  for (let i = 0; i < BANDS.length - 1; i++) {
    const xs = sales.filter((s) => s.exp >= BANDS[i] && s.exp < BANDS[i + 1])
    if (!xs.length) continue
    const paid = xs.reduce((a, s) => a + s.paid, 0), exp = xs.reduce((a, s) => a + s.exp, 0)
    const pcts = xs.map((s) => (s.paid / s.exp) * 100).sort((a, b) => a - b)
    out.push({ i, n: xs.length, paid, exp, x: exp / xs.length, pct: (paid / exp) * 100, median: pcts[Math.floor(pcts.length / 2)] })
  }
  return out
}

/** Every followed mock with picks, reloaded when its pick count changes. */
function useMockBoards(): { drafts: LiveDraftSummary[]; boards: Map<string, LiveBoard> } {
  const [drafts, setDrafts] = useState<LiveDraftSummary[]>([])
  const [boards, setBoards] = useState<Map<string, LiveBoard>>(new Map())
  useEffect(() => {
    let alive = true
    const load = () => api.liveDrafts().then((list) => { if (alive) setDrafts(list.filter((d) => d.kind === 'mock' && d.picks > 0)) })
      .catch(() => { /* keep the last list */ })
    load()
    const timer = setInterval(load, LIST_MS)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  useEffect(() => {
    const stale = drafts.filter((d) => boards.get(d.league_id)?.picks.length !== d.picks)
    if (!stale.length) return
    let alive = true
    Promise.all(stale.map((d) => api.liveBoard(d.league_id).catch(() => null))).then((bs) => {
      if (!alive) return
      setBoards((old) => {
        const next = new Map(old)
        for (const b of bs) if (b) next.set(b.league_id, b)
        return next
      })
    })
    return () => { alive = false }
  }, [drafts, boards])
  return { drafts, boards }
}

function useWindowSize() {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight })
  useEffect(() => {
    const on = () => setSize({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return size
}

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([k, l]) => <button key={k} role="radio" aria-checked={value === k} className={value === k ? 'on' : undefined}
        onClick={() => onChange(k)}>{l}</button>)}
    </div>
  )
}

export function Historical() {
  const [query] = useSynced<ValuationQuery | null>('pv-query', null)
  const [fallback, setFallback] = useState<ValuationQuery | null>(null)
  const [players, setPlayers] = useState<ValuedPlayer[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ref, setRef] = useState<Ref>('market')
  const [who, setWho] = useState<'all' | 'mine'>('all')
  const [xs, setXs] = useState<'log' | 'linear'>('log')
  const [ys, setYs] = useState<'log' | 'linear'>('log')
  const [photos, setPhotos] = useState(true)
  const [hover, setHover] = useState<number | null>(null)
  const [box, setBox] = useState<HTMLDivElement | null>(null)
  const [boxW, setBoxW] = useState(1200)
  const win = useWindowSize()
  const { drafts, boards } = useMockBoards()
  const live = useLiveBoard()

  // The Draft tab's query, so "Our price" follows its model; its defaults before the Draft tab is opened.
  useEffect(() => {
    if (query) return
    api.valuationOptions().then((o) => {
      const d = o.defaults
      setFallback({ kind: d.kind, source: d.source, season: d.season, basis: d.basis, model: d.model, dollars: d.dollars, pool: d.pool, punt: [] })
    }).catch((e: Error) => setError(e.message))
  }, [query])
  const q = query ?? fallback
  useEffect(() => {
    if (!q) return
    let alive = true
    api.valuation(q).then((v) => { if (alive) setPlayers(v.players) }).catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [q])

  useEffect(() => {
    if (!box) return
    const on = () => setBoxW(Math.max(320, box.clientWidth))
    on()
    const ro = new ResizeObserver(on)
    ro.observe(box)
    return () => ro.disconnect()
  }, [box, win.w])

  const byId = useMemo(() => new Map((players ?? []).map((p) => [p.player_id, p])), [players])
  const order = useMemo(() => drafts.filter((d) => boards.has(d.league_id)), [drafts, boards])

  // Sold in the live draft: player -> "$price to team" (greyed points).
  const soldLive = useMemo(() => {
    const b = live.board
    if (!b) return new Map<number, string>()
    const name = new Map(b.teams.map((t) => [t.team_id, t.name ?? `Team ${t.team_id}`]))
    return new Map(b.picks.filter((p) => p.player_pk != null).map((p) => [p.player_pk!, `$${p.price} to ${name.get(p.team_id)}`]))
  }, [live.board])

  const { sales, skipped } = useMemo(() => {
    const out: Sale[] = []
    let skip = 0
    order.forEach((d, di) => {
      const b = boards.get(d.league_id)!
      const mine = new Set(b.teams.filter((t) => t.mine).map((t) => t.team_id))
      for (const pk of b.picks) {
        if (pk.player_pk == null) continue
        const row = byId.get(pk.player_pk)
        if (who === 'mine' && !mine.has(pk.team_id)) continue
        const exp = row ? (ref === 'market' ? row.market.market_price : row.dollars) : null
        if (exp == null || exp < MIN_EXPECTED) { skip++; continue }
        out.push({ d: di, pk: pk.player_pk, paid: pk.price, exp, mine: mine.has(pk.team_id) })
      }
    })
    return { sales: out, skipped: skip }
  }, [order, boards, byId, ref, who])

  // One point per player (user, 2026-10-18): all his sales, paid / expected dollar weighted.
  const dots = useMemo(() => {
    const by = new Map<number, Sale[]>()
    for (const s of sales) { const l = by.get(s.pk); if (l) l.push(s); else by.set(s.pk, [s]) }
    return [...by.entries()].map(([pk, xs]): Dot => {
      const paid = xs.reduce((a, s) => a + s.paid, 0), exp = xs.reduce((a, s) => a + s.exp, 0)
      const prices = xs.map((s) => s.paid).sort((a, b) => a - b)
      const row = byId.get(pk)
      return { pk, name: row?.name ?? `#${pk}`, nbaId: row?.nba_id ?? null, n: xs.length, paid: paid / xs.length, exp: exp / xs.length,
        pct: (paid / exp) * 100, lo: prices[0], hi: prices[prices.length - 1], d: xs[0].d }
    })
  }, [sales, byId])

  const pooled = useMemo(() => bands(sales), [sales])
  const perDraft = useMemo(() => order.map((_, i) => bands(sales.filter((s) => s.d === i)).filter((b) => b.n >= 3)).filter((bs) => bs.length > 1), [order, sales])

  const W = boxW, H = W < 600 ? 380 : Math.min(1400, Math.max(460, win.h - 230))
  const m = { l: 52, r: 16, t: 16, b: 44 }
  const xMax = Math.max(10, Math.ceil(Math.max(0, ...dots.map((p) => p.exp)) / 10) * 10)
  const xLo = MIN_EXPECTED * 0.9
  const sx = (v: number) => (xs === 'log'
    ? m.l + ((Math.log(Math.max(v, xLo)) - Math.log(xLo)) / (Math.log(xMax) - Math.log(xLo))) * (W - m.l - m.r)
    : m.l + (v / xMax) * (W - m.l - m.r))
  const ps = dots.map((p) => p.pct)
  const yLo = ys === 'log' ? Math.min(50, ...ps) * 0.9 : 0
  const yHi = ys === 'log' ? Math.max(200, ...ps) * 1.1 : 500
  const sy = (v: number) => {
    const c = Math.min(Math.max(v, yLo), yHi)
    const t = ys === 'log' ? (Math.log(c) - Math.log(yLo)) / (Math.log(yHi) - Math.log(yLo)) : c / yHi
    return m.t + (1 - t) * (H - m.t - m.b)
  }
  const yTicks = ys === 'log' ? [5, 10, 25, 50, 100, 200, 400, 800].filter((v) => v >= yLo && v <= yHi) : [0, 100, 200, 300, 400, 500]
  const xTicks = xs === 'log' ? [2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100].filter((v) => v <= xMax)
    : Array.from({ length: Math.floor(xMax / (xMax > 60 ? 10 : 5)) + 1 }, (_, i) => i * (xMax > 60 ? 10 : 5))
  const r = photos ? (W < 600 ? 7 : W < 1400 ? 10 : W < 2400 ? 13 : 16) : (W < 600 ? 3.5 : 4.5)

  // Photos: nudge overlapping heads apart (each pulled back toward its true spot), so every face shows.
  const pos = useMemo(() => {
    const p = dots.map((d) => ({ x: sx(d.exp), y: sy(d.pct) }))
    if (!photos) return p
    const home = p.map((q) => ({ ...q })), d = 2 * r + 1
    for (let it = 0; it < 160; it++) {
      let moved = 0
      for (let i = 0; i < p.length; i++) for (let j = i + 1; j < p.length; j++) {
        let dx = p[j].x - p[i].x, dy = p[j].y - p[i].y
        let dist = Math.hypot(dx, dy)
        if (dist >= d) continue
        if (dist < 0.01) { dx = Math.cos(i + j); dy = Math.sin(i + j); dist = 1 }
        const push = (d - dist) / 2 / dist
        p[i].x -= dx * push; p[i].y -= dy * push; p[j].x += dx * push; p[j].y += dy * push; moved++
      }
      for (let i = 0; i < p.length; i++) {
        p[i].x += (home[i].x - p[i].x) * 0.02; p[i].y += (home[i].y - p[i].y) * 0.02
        p[i].x = Math.min(Math.max(p[i].x, m.l + r), W - m.r - r); p[i].y = Math.min(Math.max(p[i].y, m.t + r), H - m.b - r)
      }
      if (!moved) break
    }
    return p
    // sx and sy are rebuilt each render from the values listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dots, photos, r, W, H, xs, ys, xMax, yLo, yHi])

  const line = (bs: Band[]) => bs.map((b) => `${sx(b.x).toFixed(1)},${sy(b.pct).toFixed(1)}`).join(' ')
  const paid = sales.reduce((a, s) => a + s.paid, 0), exp = sales.reduce((a, s) => a + s.exp, 0)
  const greyed = dots.filter((d) => soldLive.has(d.pk)).length
  const hv = hover != null ? dots[hover] : null

  if (error) return <p className="error">{error}</p>
  if (!players) return <p className="hint">Loading values...</p>

  return (
    <div className="hist">
      <div className="hist-stats">
        <div><small>Mock drafts</small><strong>{order.length}</strong></div>
        <div><small>Players</small><strong>{dots.length}</strong></div>
        <div><small>Sales</small><strong>{sales.length}</strong></div>
        <div><small>Paid of expected</small><strong>{exp ? `${Math.round((paid / exp) * 100)}%` : '-'}</strong></div>
        <div><small>Left out</small><strong>{skipped} <span className="hint">(expected under ${MIN_EXPECTED})</span></strong></div>
        {live.board && <div><small>Sold in live draft</small><strong>{greyed} <span className="hint">greyed</span></strong></div>}
      </div>
      <div className="hist-controls">
        <label>Teams <select value={who} onChange={(e) => setWho(e.target.value as 'all' | 'mine')}>
          <option value="all">All teams</option><option value="mine">My team</option></select></label>
        <Seg label="Expected price" value={ref} onChange={setRef} options={[['market', 'Market price'], ['ours', 'Our price']]} />
        <Seg label="Price scale" value={xs} onChange={setXs} options={[['log', 'Price: log'], ['linear', 'Price: linear']]} />
        <Seg label="Share scale" value={ys} onChange={setYs} options={[['log', 'Share: log'], ['linear', 'Share: 0-500%']]} />
        <Seg label="Points" value={photos ? 'photos' : 'dots'} onChange={(v) => setPhotos(v === 'photos')} options={[['photos', 'Photos'], ['dots', 'Dots']]} />
      </div>
      <div className="hist-chart" ref={setBox}>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="Paid as a share of the expected price, by expected price, over the followed mock drafts">
          <defs><clipPath id="hist-clip" clipPathUnits="objectBoundingBox"><circle cx="0.5" cy="0.5" r="0.5" /></clipPath></defs>
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={m.l} x2={W - m.r} y1={sy(v)} y2={sy(v)} className={v === 100 ? 'pc-par' : 'pc-grid'} />
              <text x={m.l - 6} y={sy(v)} className="hist-tick" textAnchor="end" dominantBaseline="middle">{v}%</text>
            </g>
          ))}
          {xTicks.map((v) => <text key={v} x={sx(v)} y={H - m.b + 16} className="hist-tick" textAnchor="middle">${v}</text>)}
          <text x={(m.l + W - m.r) / 2} y={H - 6} className="hist-tick" textAnchor="middle">Expected price ({ref === 'market' ? 'market price' : 'our price'})</text>
          {perDraft.map((bs, i) => <polyline key={i} className="hist-trend-draft" points={line(bs)} />)}
          {dots.map((p, i) => {
            const { x, y } = pos[i]
            const sold = soldLive.has(p.pk)
            return (
              <g key={p.pk} className={['pc-pt', p.pct > 100 ? 'over' : 'under', sold && 'hist-sold'].filter(Boolean).join(' ')}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover((h) => (h === i ? null : h))}>
                {photos ? (
                  <>
                    <circle cx={x} cy={y} r={r + 2} className="pc-ring" />
                    <circle cx={x} cy={y} r={r} className="hist-face-bg" />
                    <text x={x} y={y} className="hist-initials" textAnchor="middle" dominantBaseline="central" style={{ fontSize: r * 0.8 } as CSSProperties}>{initials(p.name)}</text>
                    {p.nbaId && <image href={photo(p.nbaId)} x={x - r} y={y - r} width={2 * r} height={2 * r} clipPath="url(#hist-clip)" preserveAspectRatio="xMidYMin slice" />}
                  </>
                ) : <circle cx={x} cy={y} r={r} className="pc-dot" />}
                <circle cx={x} cy={y} r={Math.max(r, 8)} className="pc-hit" />
              </g>
            )
          })}
          {pooled.length > 1 && <polyline className="pc-trend" points={line(pooled.filter((b) => b.n >= 2))} />}
          {pooled.filter((b) => b.n >= 2).map((b) => (
            <g key={b.i}>
              <circle cx={sx(b.x)} cy={sy(b.pct)} r={5} className="pc-band" />
              <text x={sx(b.x)} y={sy(b.pct) - 10} className="hist-band-label" textAnchor="middle">{b.pct.toFixed(0)}%</text>
            </g>
          ))}
        </svg>
        {hv && (
          <div className={`pc-tip ${pos[hover!].x > W / 2 ? 'left' : ''}`} style={{ left: `${pos[hover!].x}px`, top: `${pos[hover!].y}px` }}>
            <strong>{hv.name}</strong> <span>paid ${hv.paid.toFixed(0)} vs expected ${hv.exp.toFixed(0)} ({hv.pct.toFixed(0)}%)</span>
            <br /><span>{hv.n === 1 ? '1 sale' : `${hv.n} sales, average · paid $${hv.lo}-${hv.hi}`}</span>
            {soldLive.has(hv.pk) && <><br /><span>sold in live draft: {soldLive.get(hv.pk)}</span></>}
          </div>
        )}
      </div>
      <p className="hint">One point per player: the average of all his mock sales. Photos are nudged apart where they overlap. Bold line: all shown sales, paid / expected per price band, dollar weighted. Faint lines: one mock each.{live.board ? ' Grey: already sold in the live draft.' : ''}</p>
      <h3>By price band</h3>
      <table className="hist-bands">
        <thead><tr><th>Expected price</th><th className="num">Sales</th><th className="num">Paid</th><th className="num">Expected</th><th className="num">Paid of expected</th><th className="num">Median sale</th></tr></thead>
        <tbody>
          {pooled.map((b) => {
            const a = Math.min(Math.abs(Math.log(b.pct / 100)) / Math.log(2), 1)
            return (
              <tr key={b.i}>
                <td>{bandLabel(b.i)}</td><td className="num">{b.n}</td><td className="num">${b.paid}</td><td className="num">${Math.round(b.exp)}</td>
                <td className={`num heat ${b.pct > 100 ? 'bad' : 'good'}`}><span style={{ '--a': a.toFixed(3) } as CSSProperties}>{Math.round(b.pct)}%</span></td>
                <td className="num">{Math.round(b.median)}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
