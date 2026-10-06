// Draft panel data (T-018): teams built so far from the live board, joined with the value table rows.
import type { BoardTeam, LiveBoard, ValuedPlayer } from '../../../api/client'
import { teamLine, type TeamLine } from '../../../lib/h2h'

// Our league's draft slots (docs/RULES.md): G G G F F F C, 3 Util, 2 BN.
export const STARTERS: Record<string, number> = { G: 3, F: 3, C: 1 }

export type RosterPlayer = { pk: number | null; name: string; price: number; row: ValuedPlayer | undefined }
export type DraftTeam = BoardTeam & { label: string; players: RosterPlayer[] }

export function buildTeams(board: LiveBoard, byId: Map<number, ValuedPlayer>): DraftTeam[] {
  return board.teams.map((t) => ({
    ...t,
    label: t.name ?? `Team ${t.team_id}`,
    players: board.picks.filter((p) => p.team_id === t.team_id).map((p) => {
      const row = p.player_pk != null ? byId.get(p.player_pk) : undefined
      return { pk: p.player_pk, name: row?.name ?? p.name ?? p.yahoo_id, price: p.price, row }
    }),
  }))
}

/** Category line per team; `add` puts one more player on a team (the "if I buy him" view). */
export function teamLines(teams: DraftTeam[], add?: { team: number; row: ValuedPlayer }): Map<number, TeamLine> {
  return new Map(teams.map((t) => {
    const rows = t.players.map((p) => p.row).filter((r): r is ValuedPlayer => !!r)
    if (add && add.team === t.team_id) rows.push(add.row)
    return [t.team_id, teamLine(rows.map((r) => r.stats))]
  }))
}

/** Players eligible at G, F and C (a G,F player counts in both). */
export function eligibility(rows: (ValuedPlayer | undefined)[]): Record<string, number> {
  const out: Record<string, number> = { G: 0, F: 0, C: 0 }
  for (const r of rows) for (const pos of r?.positions ?? []) if (pos in out) out[pos]++
  return out
}
