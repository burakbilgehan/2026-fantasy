// Price curve (user, 2026-10-18): what the room paid for each sold player against the expected price.
// x = expected price (market price or our static price, one at a time, never mixed). y = paid / expected,
// 100% = paid exactly the expected price; clamped to 0-200%. Trend = paid / expected per price band,
// dollar weighted (sum paid / sum expected), so one $1 player sold for $6 does not swing it.
// Click the small chart to open it large, with player photos.
import { useEffect, useState } from 'react'
import type { ValuedPlayer } from '../../../api/client'
import type { DraftTeam } from './model'

type Ref = 'market' | 'ours'
type Point = { id: number | string; team: number; mine: boolean; name: string; nbaId: string | null; exp: number; paid: number; pct: number }

// Players expected under this price are left out: a ratio on $0-1 says nothing.
const MIN_EXPECTED = 2
const Y_MAX = 200
// Price bands of the trend line (expected price, USD). Assumed.
const BANDS = [2, 5, 10, 20, 35, 55, Infinity]
const photo = (nbaId: string) => `https://cdn.nba.com/headshots/nba/latest/260x190/${nbaId}.png`

const expected = (row: ValuedPlayer, ref: Ref) => (ref === 'market' ? row.market.market_price : row.dollars)

function points(teams: DraftTeam[], ref: Ref): { pts: Point[]; skipped: number } {
  const pts: Point[] = []
  let skipped = 0
  for (const t of teams) for (const p of t.players) {
    const exp = p.row ? expected(p.row, ref) : null
    if (exp == null || exp < MIN_EXPECTED) { skipped++; continue }
    pts.push({ id: p.pk ?? p.name, team: t.team_id, mine: t.mine, name: p.name, nbaId: p.row?.nba_id ?? null, exp, paid: p.price, pct: (p.price / exp) * 100 })
  }
  return { pts, skipped }
}

function trend(pts: Point[]): { x: number; pct: number; n: number; lo: number; hi: number }[] {
  const out = []
  for (let i = 0; i < BANDS.length - 1; i++) {
    const inBand = pts.filter((p) => p.exp >= BANDS[i] && p.exp < BANDS[i + 1])
    if (inBand.length < 2) continue
    const paid = inBand.reduce((a, p) => a + p.paid, 0), exp = inBand.reduce((a, p) => a + p.exp, 0)
    out.push({ x: exp / inBand.length, pct: (paid / exp) * 100, n: inBand.length, lo: BANDS[i], hi: BANDS[i + 1] })
  }
  return out
}

// Inline: a wide, low strip over the full page width (user, 2026-10-18), dots only. Large: the zoom view with photos.
// pts = the points shown (one team or all); all = every sold player, for the axis and the room's trend line.
function Chart({ pts, all, large }: { pts: Point[]; all: Point[]; large: boolean }) {
  // Inline width follows the box in pixels, so the strip keeps its low height at any width.
  const [box, setBox] = useState<HTMLDivElement | null>(null)
  const [boxW, setBoxW] = useState(1200)
  useEffect(() => {
    if (!box || large) return
    const on = () => setBoxW(Math.max(320, Math.round(box.clientWidth)))
    on()
    const ro = new ResizeObserver(on)
    ro.observe(box)
    window.addEventListener('resize', on)
    return () => { ro.disconnect(); window.removeEventListener('resize', on) }
  }, [box, large])
  const W = large ? 1000 : boxW, H = large ? 560 : 230
  const m = { l: large ? 48 : 40, r: 12, t: 12, b: large ? 34 : 28 }
  const xMax = Math.max(10, Math.ceil(Math.max(0, ...all.map((p) => p.exp)) / 10) * 10)
  const sx = (v: number) => m.l + (v / xMax) * (W - m.l - m.r)
  const sy = (v: number) => m.t + (1 - Math.min(Math.max(v, 0), Y_MAX) / Y_MAX) * (H - m.t - m.b)
  const xStep = xMax > 60 ? 20 : 10
  const xTicks = Array.from({ length: Math.floor(xMax / xStep) + 1 }, (_, i) => i * xStep)
  const tr = trend(all)
  const r = large ? 13 : 5
  // Hover tooltip in HTML (user, 2026-10-18): the native SVG title shows late and not everywhere.
  const [hover, setHover] = useState<Point | null>(null)
  return (
    <div className="pc-wrap" ref={setBox}>
    <svg viewBox={`0 0 ${W} ${H}`} className={large ? 'pc-svg large' : 'pc-svg'} role="img"
      aria-label="Paid price as a share of the expected price, by expected price">
      <defs><clipPath id="pc-clip" clipPathUnits="objectBoundingBox"><circle cx="0.5" cy="0.5" r="0.5" /></clipPath></defs>
      {[0, 50, 100, 150, 200].map((v) => (
        <g key={v}>
          <line x1={m.l} x2={W - m.r} y1={sy(v)} y2={sy(v)} className={v === 100 ? 'pc-par' : 'pc-grid'} />
          <text x={m.l - 4} y={sy(v)} className="pc-tick" textAnchor="end" dominantBaseline="middle">{v}%</text>
        </g>
      ))}
      {xTicks.map((v) => <text key={v} x={sx(v)} y={H - m.b + (large ? 16 : 12)} className="pc-tick" textAnchor="middle">${v}</text>)}
      {tr.length > 1 && <polyline className="pc-trend" points={tr.map((b) => `${sx(b.x)},${sy(b.pct)}`).join(' ')} />}
      {pts.map((p) => {
        const cx = sx(p.exp), cy = sy(p.pct)
        const tone = p.pct > 100 ? 'over' : 'under'
        const tip = `${p.name}: expected $${p.exp.toFixed(0)}, paid $${p.paid} (${p.pct.toFixed(0)}%)`
        return (
          <g key={p.id} className={`pc-pt ${tone}${p.mine ? ' mine' : ''}`} aria-label={tip}
            onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover((h) => (h === p ? null : h))}>
            {large && p.nbaId ? (
              <>
                <circle cx={cx} cy={cy} r={r + 2} className="pc-ring" />
                <image href={photo(p.nbaId)} x={cx - r} y={cy - r} width={2 * r} height={2 * r} clipPath="url(#pc-clip)" preserveAspectRatio="xMidYMin slice" />
              </>
            ) : <circle cx={cx} cy={cy} r={r} className="pc-dot" />}
            {large && p.pct > Y_MAX && <text x={cx} y={cy - r - 3} className="pc-tick" textAnchor="middle">▲{p.pct.toFixed(0)}%</text>}
            <circle cx={cx} cy={cy} r={Math.max(r, 8)} className="pc-hit" />
          </g>
        )
      })}
      {tr.map((b) => (
        <g key={b.lo}>
          <title>{`Expected $${b.lo}-${b.hi === Infinity ? '+' : b.hi}: ${b.n} players, paid ${b.pct.toFixed(0)}% of expected`}</title>
          <circle cx={sx(b.x)} cy={sy(b.pct)} r={large ? 5 : 3} className="pc-band" />
          {large && <text x={sx(b.x)} y={sy(b.pct) - 9} className="pc-label" textAnchor="middle">{b.pct.toFixed(0)}%</text>}
        </g>
      ))}
    </svg>
    {hover && (
      <div className={`pc-tip ${sx(hover.exp) > W / 2 ? 'left' : ''}`}
        style={{ left: `${(sx(hover.exp) / W) * 100}%`, top: `${(sy(hover.pct) / H) * 100}%` }}>
        <strong>{hover.name}</strong> <span>paid ${hover.paid} vs expected ${hover.exp.toFixed(0)} ({hover.pct.toFixed(0)}%)</span>
      </div>
    )}
    </div>
  )
}

export function PriceCurve({ teams }: { teams: DraftTeam[] }) {
  const [ref, setRef] = useState<Ref>('market')
  const [open, setOpen] = useState(false)
  // Team filter (user, 2026-10-18): one team's points against the whole room's trend line.
  const [team, setTeam] = useState<number | null>(null)
  const { pts: all, skipped } = points(teams, ref)
  const pts = team == null ? all : all.filter((p) => p.team === team)
  const sum = (xs: Point[]) => [xs.reduce((a, p) => a + p.paid, 0), xs.reduce((a, p) => a + p.exp, 0)]
  const [paid, exp] = sum(all)
  const [tPaid, tExp] = sum(pts)
  const tr = trend(all)
  const teamName = teams.find((t) => t.team_id === team)?.label
  useEffect(() => {
    if (!open) return
    const on = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [open])

  const toggle = (
    <span className="pc-controls">
    <select value={team ?? ''} aria-label="Team" onChange={(e) => setTeam(e.target.value ? Number(e.target.value) : null)}>
      <option value="">All teams</option>
      {teams.map((t) => <option key={t.team_id} value={t.team_id}>{t.label}{t.mine ? ' (me)' : ''}</option>)}
    </select>
    <div className="segmented" role="radiogroup" aria-label="Expected price">
      {(['market', 'ours'] as const).map((k) => (
        <button key={k} role="radio" aria-checked={ref === k} className={ref === k ? 'on' : undefined}
          onClick={() => setRef(k)}>{k === 'market' ? 'Market price' : 'Our price'}</button>
      ))}
    </div>
    </span>
  )
  const summary = (
    <p className="hint">{team != null && <><strong>{teamName}: {pts.length} players, paid ${tPaid} for ${Math.round(tExp)} expected ({tExp > 0 ? Math.round((tPaid / tExp) * 100) : '-'}%).</strong> Room: </>}{all.length} sold players{skipped ? ` (${skipped} left out: expected under $${MIN_EXPECTED} or unknown)` : ''}.
      {exp > 0 && <> All: paid {Math.round((paid / exp) * 100)}% of expected.</>}
      {tr.length > 0 && <> By band: {tr.map((b) => `$${b.lo}${b.hi === Infinity ? '+' : `-${b.hi}`} ${b.pct.toFixed(0)}%`).join(' · ')}.</>}</p>
  )

  return (
    <section className="signal price-curve">
      <h4>Paid vs expected {toggle}</h4>
      {all.length === 0 ? <p className="hint">No sold players yet.</p> : (
        <button className="pc-open" onClick={() => setOpen(true)} title="Open large">
          <Chart pts={pts} all={all} large={false} />
        </button>
      )}
      {summary}
      {open && (
        <div className="pc-backdrop" onClick={() => setOpen(false)}>
          <div className="pc-modal" onClick={(e) => e.stopPropagation()}>
            <header><h4>Paid vs expected {toggle}</h4><button onClick={() => setOpen(false)}>Close</button></header>
            <Chart pts={pts} all={all} large />
            {summary}
            <p className="hint">100% = paid the expected price. Line: the whole room, paid / expected per price band, dollar weighted. Above 200% the point sits on the top edge with its value.</p>
          </div>
        </div>
      )}
    </section>
  )
}
