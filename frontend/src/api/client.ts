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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  league: () => request<League>('/api/league'),
  syncLeague: () => request<League>('/api/league/sync', { method: 'POST' }),
}
