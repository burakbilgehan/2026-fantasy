// Compares the browser punt model (src/lib/valuation.ts) with the backend.
// Needs the backend on :8000. Run: node --experimental-strip-types scripts/check-punt.ts
import { runPunt } from '../src/lib/valuation.ts'

const API = 'http://localhost:8000/api/valuation'
const FIELDS = ['gp', 'fgm', 'fga', 'ftm', 'fta', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
const opts = await (await fetch(`${API}/options`)).json()
const cases = [
  { kind: 'projection', source: 'yahoo', season: '2026-27', basis: 'totals', dollars: 'plain', pool: 200, punt: ['ft_pct'] },
  { kind: 'projection', source: 'espn', season: '2026-27', basis: 'per_game', dollars: 'savor', pool: 144, punt: ['fg_pct', 'tov'] },
  { kind: 'actual', source: 'nba', season: '2025-26', basis: 'totals', dollars: 'savor', pool: 0, punt: ['ast', 'stl', 'tpm'] },
  { kind: 'projection', source: 'yahoo', season: '2026-27', basis: 'per_game', dollars: 'plain', pool: 250, punt: ['blk'] },
]
let fails = 0
for (const c of cases) {
  const qs = new URLSearchParams({ ...c, model: 'punt', pool: String(c.pool), punt: c.punt.join(',') } as Record<string, string>)
  const want = (await (await fetch(`${API}?${qs}`)).json()).players as any[]
  const rows = new Map(want.map((p) => [p.player_id, Object.fromEntries(FIELDS.map((k) => [k, p.stats[k] ?? 0]))]))
  const got = runPunt(rows, { basis: c.basis, pool: c.pool || null, punt: c.punt }, opts.drafted, opts.budget, c.dollars, 10)
  let worst = { total: 0, dollars: 0, z: 0, rank: 0 }
  for (const p of want) {
    const g = got.get(p.player_id)
    if (!g) { if (p.rank != null) worst.rank++; continue }
    worst.total = Math.max(worst.total, Math.abs(g.total - p.total))
    worst.dollars = Math.max(worst.dollars, Math.abs(g.dollars - p.dollars))
    worst.z = Math.max(worst.z, ...Object.keys(p.z).map((k) => Math.abs(g.z[k] - p.z[k])))
    if (g.rank !== p.rank) worst.rank++
  }
  const ok = worst.total < 1e-9 && worst.z < 1e-9 && worst.dollars < 1e-4 && worst.rank === 0
  if (!ok) fails++
  console.log(ok ? 'OK  ' : 'FAIL', JSON.stringify(c), JSON.stringify(worst))
}
process.exit(fails ? 1 : 0)
