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
}
