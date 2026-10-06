// Hand-computed checks for src/lib/h2h.ts. Run: node --experimental-strip-types scripts/check-h2h.ts
import { catRanks, h2h, matchup, teamLine } from '../src/lib/h2h.ts'

const p = (o: Record<string, number>) => ({ gp: 10, fgm: 0, fga: 0, ftm: 0, fta: 0, tpm: 0, pts: 0, reb: 0, ast: 0, stl: 0, blk: 0, tov: 0, ...o })
let fails = 0
const eq = (name: string, got: unknown, want: unknown) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (!ok) fails++
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}: ${JSON.stringify(got)}${ok ? '' : ` want ${JSON.stringify(want)}`}`)
}

// Team A: one big (100 FGA at 60%, 20 PTS/g) and one guard (50 FGA at 40%). FG% = (60+20)/(100+50) = 0.5333.
const A = teamLine([p({ fgm: 60, fga: 100, pts: 200, reb: 100, tov: 30 }), p({ fgm: 20, fga: 50, pts: 100, ast: 80, tov: 10 })])!
eq('A fg% volume weighted', A.fg_pct.toFixed(4), '0.5333')
eq('A pts mean per game', A.pts, 15)
eq('A tov per game', A.tov, 2)
// 80-game player at 20 PTS and 50-game player at 10 PTS: totals / games = 2100 / 130, not the mean 15.
eq('games weighted', teamLine([p({ gp: 80, pts: 1600 }), p({ gp: 50, pts: 500 })])!.pts.toFixed(2), '16.15')
// Team B: 18 PTS/g, FG% 0.5, REB 0, AST 2, TO 1. A vs B: FG% W, PTS L, REB W, AST W, TO L (lower wins),
// FT% tie (no attempts both), 3PM, STL, BLK tie at 0 -> 3-2-4.
const B = teamLine([p({ fgm: 50, fga: 100, pts: 180, ast: 20, tov: 10 })])
eq('A vs B', matchup(A, B), { w: 3, l: 2, t: 4 })
eq('empty team loses all', matchup(teamLine([]), B), { w: 0, l: 9, t: 0 })
eq('no games skipped', teamLine([p({ gp: 0, pts: 99 })]), null)
const table = h2h(new Map([[1, A], [2, B], [3, null]]))
eq('A wins (3 + 2 ties + 9 vs empty)', table.get(1)!.wins, 3 + 4 / 2 + 9)
eq('games per team = 2 x 9', table.get(1)!.games, 18)
eq('ranks: A best in REB, B best in PTS, empty last', [catRanks(new Map([[1, A], [2, B], [3, null]])).get(1)!.reb, catRanks(new Map([[1, A], [2, B], [3, null]])).get(2)!.pts, catRanks(new Map([[1, A], [2, B], [3, null]])).get(3)!.pts], [1, 1, 3])
if (fails) { console.log(`${fails} failed`); process.exit(1) }
