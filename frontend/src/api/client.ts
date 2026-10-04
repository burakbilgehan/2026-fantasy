export type Team = { team_id: number; name: string }

export type League = {
  league_id: string
  name: string
  num_teams: number
  scoring_type: string
  draft_type: string
  draft_budget: number | null
  draft_time: string | null
  roster_positions: string[]
  stat_categories: string[]
  source: 'yahoo_api' | 'yahoo_web'
  synced_at: string
  teams: Team[]
}

export type LiveDraftSummary = {
  league_id: string
  kind: 'league' | 'mock'
  my_team_id: number | null
  last_event_at: string | null
  picks: number
}

export type LiveDraftTeam = {
  team_id: number
  name: string | null
  money_left: number
  spent: number
  players: number
  online: boolean
  autopick: boolean
}

export type LiveDraftPick = {
  pick_no: number
  player_id: string
  player_name: string | null
  team_id: number
  price: number
  roster_slot: string | null
  nominating_team_id: number | null
  sold_at: string | null
}

export type LiveDraft = {
  league_id: string
  kind: 'league' | 'mock'
  my_team_id: number | null
  budget: number
  last_event_at: string | null
  server_time: string
  teams: LiveDraftTeam[]
  nomination_order: number[]
  on_the_clock: { pick_no: number; team_id: number } | null
  nomination: {
    pick_no: number | null
    player_id: string
    player_name: string | null
    nominating_team_id: number | null
    high_bid: number
    high_team_id: number
    bids: { at: string; team_id: number; amount: number }[]
  } | null
  picks: LiveDraftPick[]
  warnings: string[]
  unknown: Record<string, number>
}

export type ValuationBase = { kind: 'projection' | 'actual'; source: string; season: string; players: number }

export type ValuationOptions = {
  bases: ValuationBase[]
  basis: string[]
  models: { key: string; label: string; description: string; needs: string[] }[]
  dollars: { key: string; description: string }[]
  categories: string[]
  pools: (number | null)[]
  defaults: { kind: string; source: string; season: string; basis: string; model: string; dollars: string; pool: number }
  drafted: number
  budget: number
}

export type ValuationQuery = {
  kind: string
  source: string
  season: string
  basis: string
  model: string
  dollars: string
  pool: number // 0 = all players
  punt: string[]
}

export type ValuedPlayer = {
  player_id: number
  name: string
  team: string | null
  positions: string[] | null
  injury: string | null
  stats: Record<string, number | null>
  z: Record<string, number> | null
  total: number | null
  rank: number | null
  dollars: number | null
  market: { yahoo_auction_value: number | null; yahoo_average_cost: number | null; espn_average_cost: number | null }
}

export type Valuation = {
  settings: ValuationQuery & { drafted: number; budget: number; g_weights_from: string[] | null }
  players: ValuedPlayer[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  league: () => request<League>('/api/league'),
  syncLeague: () => request<League>('/api/league/sync', { method: 'POST' }),
  liveDrafts: () => request<LiveDraftSummary[]>('/api/draft/live'),
  liveDraft: (leagueId: string) => request<LiveDraft>(`/api/draft/live/${leagueId}`),
  valuationOptions: () => request<ValuationOptions>('/api/valuation/options'),
  valuation: (q: ValuationQuery) => {
    const params = new URLSearchParams({
      kind: q.kind, source: q.source, season: q.season, basis: q.basis, model: q.model,
      dollars: q.dollars, pool: String(q.pool), punt: q.punt.join(','),
    })
    return request<Valuation>(`/api/valuation?${params}`)
  },
}
