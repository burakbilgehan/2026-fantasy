// Team category lines and simulated H2H during a draft (T-018, docs/modules/draft.md "Display rule").
// Team line: counting stats = the players' season totals summed, divided by their games summed (user,
// 2026-10-06: an 80-game player weighs more than a 50-game one); FG% and FT% = total makes / total
// attempts, so high-volume players move them more. TO: lower is better.
// Every category always counts (a punt changes player values, not league results).

export const H2H_CATS = ['fg_pct', 'ft_pct', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov'] as const
export type Cat = (typeof H2H_CATS)[number]

/** Season totals of one player (gp, fgm, fga, ftm, fta, tpm, pts, reb, ast, stl, blk, tov). */
export type Totals = Record<string, number | null | undefined>
export type TeamLine = Record<Cat, number> | null // null = no player with games yet
export type Record3 = { w: number; l: number; t: number }

const COUNTING = ['tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov'] as const

/** Category line of a team. Players with no games are skipped. */
export function teamLine(players: Totals[]): TeamLine {
  const ps = players.filter((p) => (p.gp ?? 0) > 0)
  if (!ps.length) return null
  const sum = (k: string) => ps.reduce((a, p) => a + (p[k] ?? 0), 0)
  const games = sum('gp')
  const line = {} as Record<Cat, number>
  for (const k of COUNTING) line[k] = sum(k) / games
  const fga = sum('fga'), fta = sum('fta')
  line.fg_pct = fga ? sum('fgm') / fga : 0
  line.ft_pct = fta ? sum('ftm') / fta : 0
  return line
}

/** Result of one category from team a's view: 1 win, 0 loss, 0.5 tie. An empty team loses. */
export function catResult(a: TeamLine, b: TeamLine, cat: Cat): number {
  if (!a && !b) return 0.5
  if (!a) return 0
  if (!b) return 1
  const x = a[cat], y = b[cat]
  if (Math.abs(x - y) < 1e-9) return 0.5
  return (cat === 'tov' ? x < y : x > y) ? 1 : 0
}

/** Week result of team a against team b over the 9 categories. */
export function matchup(a: TeamLine, b: TeamLine): Record3 {
  const r = { w: 0, l: 0, t: 0 }
  for (const c of H2H_CATS) {
    const x = catResult(a, b, c)
    if (x === 1) r.w++
    else if (x === 0) r.l++
    else r.t++
  }
  return r
}

export type H2HRow = { team: number; vs: Map<number, Record3>; wins: number; games: number }

/** Every team against every other team. wins = category wins + half the ties, out of games. */
export function h2h(lines: Map<number, TeamLine>): Map<number, H2HRow> {
  const out = new Map<number, H2HRow>()
  for (const [a, la] of lines) {
    const vs = new Map<number, Record3>()
    let wins = 0, games = 0
    for (const [b, lb] of lines) {
      if (a === b) continue
      const r = matchup(la, lb)
      vs.set(b, r)
      wins += r.w + r.t / 2
      games += H2H_CATS.length
    }
    out.set(a, { team: a, vs, wins, games })
  }
  return out
}

/** League rank (1 = best) of each team in each category. Empty teams rank last. */
export function catRanks(lines: Map<number, TeamLine>): Map<number, Record<Cat, number>> {
  const out = new Map<number, Record<Cat, number>>()
  for (const t of lines.keys()) out.set(t, {} as Record<Cat, number>)
  for (const c of H2H_CATS) {
    for (const [a, la] of lines) {
      let better = 0
      for (const [b, lb] of lines) if (a !== b && catResult(lb, la, c) === 1) better++
      out.get(a)![c] = better + 1
    }
  }
  return out
}
