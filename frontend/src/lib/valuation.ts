// Punt model in the browser, for the static copy (no backend). A line-by-line port of
// backend/app/analytics/valuation (core.py value/category_z, models.py _punt, dollars.py,
// __init__.py run). Keep the two in step; `scripts/check-punt.ts` compares them.

export const CATEGORIES = ['fg_pct', 'ft_pct', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov'] as const
const PERCENT: Record<string, [string, string]> = { fg_pct: ['fgm', 'fga'], ft_pct: ['ftm', 'fta'] }

export type Row = Record<string, number> // season totals: gp, fgm, fga, ftm, fta, tpm, pts, reb, ast, stl, blk, tov
export type Settings = { basis: string; pool: number | null; punt: string[]; iterations?: number }
export type Result = { z: Record<string, number>; total: number; rank: number; dollars: number }

function basisStats(row: Row, basis: string): Row {
  if (basis === 'totals') return { ...row }
  if (basis === 'per_game') {
    const out: Row = {}
    for (const [k, v] of Object.entries(row)) out[k] = k === 'gp' ? 1 : v / row.gp
    return out
  }
  throw new Error(`unknown basis ${basis}`)
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
const pstdev = (xs: number[]) => { const m = mean(xs); return Math.sqrt(mean(xs.map((x) => (x - m) ** 2))) }

function categoryZ(stats: Map<number, Row>, pool: number[]): Map<number, Record<string, number>> {
  const rates: Record<string, number> = {}
  for (const [c, [m, a]] of Object.entries(PERCENT)) {
    const att = pool.reduce((s, p) => s + stats.get(p)![a], 0)
    rates[c] = pool.reduce((s, p) => s + stats.get(p)![m], 0) / (att || 1)
  }
  const raw = (s: Row, c: string) => (c in PERCENT ? s[PERCENT[c][0]] - rates[c] * s[PERCENT[c][1]] : s[c])
  const moments: Record<string, [number, number]> = {}
  for (const c of CATEGORIES) {
    const xs = pool.map((p) => raw(stats.get(p)!, c))
    moments[c] = [mean(xs), pstdev(xs) || 1]
  }
  const out = new Map<number, Record<string, number>>()
  for (const [p, s] of stats) {
    const z: Record<string, number> = {}
    for (const c of CATEGORIES) z[c] = (raw(s, c) - moments[c][0]) / moments[c][1]
    z.tov = -z.tov
    out.set(p, z)
  }
  return out
}

const puntTotal = (z: Record<string, number>, punt: string[]) =>
  CATEGORIES.reduce((s, c) => (punt.includes(c) ? s : s + z[c]), 0)

// erf, Abramowitz and Stegun 7.1.26 (error below 1.5e-7). Python uses math.erf; dollars differ in the 6th digit.
function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x))
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
    * Math.exp(-x * x)
  return x >= 0 ? y : -y
}

function savor(d: number, spread: number): number {
  if (spread <= 0) return d
  const phi = 0.5 * (1 + erf(d / spread / Math.SQRT2))
  return d * phi - spread / Math.sqrt(2 * Math.PI) * (1 - Math.exp(-d * d / (2 * spread * spread)))
}

function toDollars(totals: Map<number, number>, nDrafted: number, budget: number, method: string,
  spread: number): Map<number, number> {
  const ranked = [...totals.keys()].sort((a, b) => totals.get(b)! - totals.get(a)!)
  const top = ranked.slice(0, nDrafted)
  const replacement = ranked.length > nDrafted ? totals.get(ranked[nDrafted])! : Math.min(...totals.values())
  const vor = new Map(top.map((p) => [p, Math.max(totals.get(p)! - replacement, 0)]))
  const vorSum = [...vor.values()].reduce((a, b) => a + b, 0)
  const scale = (budget - top.length) / (vorSum || 1)
  let extra = new Map([...vor].map(([p, v]) => [p, v * scale]))
  if (method === 'savor') {
    const adjusted = new Map([...extra].map(([p, d]) => [p, savor(d, spread)]))
    const k = [...extra.values()].reduce((a, b) => a + b, 0) / ([...adjusted.values()].reduce((a, b) => a + b, 0) || 1)
    extra = new Map([...adjusted].map(([p, d]) => [p, d * k]))
  } else if (method !== 'plain') {
    throw new Error(`unknown dollar method ${method}`)
  }
  const out = new Map([...totals.keys()].map((p) => [p, 0]))
  for (const [p, d] of extra) out.set(p, 1 + d)
  return out
}

/** Punt model values for every row with gp > 0. Same output as the backend `run(rows, "punt", ...)`. */
export function runPunt(rows: Map<number, Row>, s: Settings, nDrafted: number, budget: number, dollars: string,
  spread: number): Map<number, Result> {
  const stats = new Map<number, Row>()
  for (const [p, r] of rows) if (r.gp > 0) stats.set(p, basisStats(r, s.basis))
  let pool = [...stats.keys()]
  let z = new Map<number, Record<string, number>>()
  let totals = new Map<number, number>()
  for (let i = 0; i < Math.max(1, s.iterations ?? 3); i++) {
    z = categoryZ(stats, pool)
    totals = new Map([...z].map(([p, zp]) => [p, puntTotal(zp, s.punt)]))
    if (s.pool == null || s.pool >= stats.size) break
    pool = [...totals.keys()].sort((a, b) => totals.get(b)! - totals.get(a)!).slice(0, s.pool)
  }
  const usd = toDollars(totals, nDrafted, budget, dollars, spread)
  const ranked = [...totals.keys()].sort((a, b) => totals.get(b)! - totals.get(a)!)
  return new Map(ranked.map((p, i) => [p, { z: z.get(p)!, total: totals.get(p)!, rank: i + 1, dollars: usd.get(p)! }]))
}
