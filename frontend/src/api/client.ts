import { runPunt } from '../lib/valuation'

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
  nba_id: string | null
  name: string
  team: string | null
  positions: string[] | null
  injury: string | null
  stats: Record<string, number | null>
  usg_pct: number | null // usage rate, fraction; season in settings.usage_season
  z: Record<string, number> | null
  total: number | null
  rank: number | null
  dollars: number | null
  market: { yahoo_auction_value: number | null; yahoo_average_cost: number | null; espn_average_cost: number | null }
}

export type Valuation = {
  settings: ValuationQuery & { drafted: number; budget: number; g_weights_from: string[] | null; usage_season: string; spread: number }
  players: ValuedPlayer[]
}

export type PlayerCard = {
  player_id: number
  nba_id: string | null
  name: string
  team: string | null
  positions: string[] | null
  injury: string | null
  injury_note: string | null
  prices: {
    yahoo_average_cost: number | null
    espn_average_cost: number | null
    league_last: number | null
    league_last_season: string
  }
  usage: { season: string; usg_pct: number | null; ts_pct: number | null; gp: number }[] // newest first
  has_profile: boolean
  report: string
  articles: { slug: string; title: string; mentions: number }[]
}

export type PlayerTag = {
  tag: string
  kind: string | null
  channel: 'durable' | 'current'
  detail: string | null
  until: string | null
  classified: boolean
}

export type ModelValue = {
  key: string
  label: string
  z: Record<string, number> | null
  total: number | null
  rank: number | null
  dollars: number | null
  off: string[]
}

export type PlayerModels = { in_base: boolean; models: ModelValue[] }

export type DepthPlayer = {
  player_id: number | null
  name: string
  depth: number
  minutes: { espn: number | null; darko: number | null; fantasypros: number | null }
}

export type TeamDepth = {
  team: string
  source: string
  fetched_at: string | null
  slots: { slot: string; players: DepthPlayer[] }[]
  report: string | null
}

export type TagCount = { tag: string; kind: string | null; channel: string; count: number }
export type TagPlayer = { player_pk: number; name: string; team: string | null; tag: string; detail: string | null }

export type Article = { slug: string; title: string; markdown: string }

// Static build (GitHub Pages): the API is a set of JSON files made by `app/jobs/export_static.py`.
export const STATIC = import.meta.env.VITE_STATIC === '1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (STATIC) {
    if (init?.method && init.method !== 'GET') throw new Error('Not available in the static copy.')
    const res = await fetch(`${import.meta.env.BASE_URL}${path.slice(1).split('?')[0]}.json`)
    if (!res.ok) throw new Error(res.status === 404 ? 'Not in the static copy.' : `${res.status}`)
    return res.json() as Promise<T>
  }
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

type StaticValues = { settings: Valuation['settings']; categories: string[]; rows: (number | null)[][] }
type StaticFacts = Omit<ValuedPlayer, 'z' | 'total' | 'rank' | 'dollars'>[]

function staticPaths(q: ValuationQuery, model: string) {
  const base = `/api/valuation/${q.kind}_${q.source}_${q.season}`
  return { facts: `${base}/players`, values: `${base}/${q.basis}_${model}_${q.dollars}_${q.pool}` }
}

const STAT_FIELDS = ['gp', 'fgm', 'fga', 'ftm', 'fta', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']

/** The punt model with punted categories is computed here (lib/valuation.ts); the files hold it without punt. */
async function staticPunt(q: ValuationQuery, facts: StaticFacts): Promise<StaticValues> {
  const [opts, plain] = await Promise.all([
    request<ValuationOptions>('/api/valuation/options'), request<StaticValues>(staticPaths(q, 'punt').values)])
  const rows = new Map(facts.map((f) => [f.player_id,
    Object.fromEntries(STAT_FIELDS.map((k) => [k, f.stats[k] ?? 0])) as Record<string, number>]))
  const res = runPunt(rows, { basis: q.basis, pool: q.pool || null, punt: q.punt }, opts.drafted, opts.budget,
    q.dollars, plain.settings.spread ?? 10)
  const cats = plain.categories
  return {
    settings: { ...plain.settings, punt: [...q.punt].sort() },
    categories: cats,
    rows: [...res].map(([id, r]) => [id, r.total, r.rank, r.dollars, ...cats.map((c) => r.z[c])]),
  }
}

async function staticValues(q: ValuationQuery, model: string, facts?: StaticFacts): Promise<StaticValues> {
  const paths = staticPaths(q, model)
  if (model === 'punt' && q.punt.length) return staticPunt(q, facts ?? await request<StaticFacts>(paths.facts))
  return request<StaticValues>(paths.values)
}

async function staticValuation(q: ValuationQuery): Promise<Valuation> {
  const facts = await request<StaticFacts>(staticPaths(q, q.model).facts)
  const v = await staticValues(q, q.model, facts)
  const byId = new Map(v.rows.map((r) => [r[0] as number, r]))
  const players = facts.map((f) => {
    const r = byId.get(f.player_id)
    const z = r && r[4] != null ? Object.fromEntries(v.categories.map((c, i) => [c, r[4 + i] as number])) : null
    return { ...f, total: r?.[1] ?? null, rank: r?.[2] ?? null, dollars: r?.[3] ?? null, z }
  })
  players.sort((a, b) => (a.rank ?? 1e6) - (b.rank ?? 1e6))
  return { settings: v.settings, players }
}

// Same rule as app/api/valuation.py off_categories.
function offCategories(model: string, z: Record<string, number>, cats: string[], punt: string[]): string[] {
  if (model === 'punt') return cats.filter((c) => punt.includes(c))
  if (model !== 'minus1' && model !== 'durant') return []
  const pool = cats.filter((c) => model === 'minus1' || c !== 'tov')
  const worst = pool.reduce((a, b) => (z[b] < z[a] ? b : a))
  return model === 'minus1' ? [worst] : cats.filter((c) => c === 'tov' || c === worst)
}

async function staticPlayerModels(id: number, q: ValuationQuery): Promise<PlayerModels> {
  const opts = await request<ValuationOptions>('/api/valuation/options')
  const all = await Promise.all(opts.models.map((m) => staticValues(q, m.key)))
  const models: ModelValue[] = []
  let inBase = false
  opts.models.forEach((m, i) => {
    const v = all[i]
    const r = v.rows.find((row) => row[0] === id)
    if (r) inBase = true
    const z = r && r[4] != null ? Object.fromEntries(v.categories.map((c, j) => [c, r[4 + j] as number])) : null
    models.push({ key: m.key, label: m.label, z, total: r?.[1] ?? null, rank: r?.[2] ?? null,
      dollars: r?.[3] ?? null, off: z ? offCategories(m.key, z, v.categories, q.punt) : [] })
  })
  return { in_base: inBase, models: inBase ? models : [] }
}

export const api = {
  league: () => request<League>('/api/league'),
  syncLeague: () => request<League>('/api/league/sync', { method: 'POST' }),
  liveDrafts: () => request<LiveDraftSummary[]>('/api/draft/live'),
  liveDraft: (leagueId: string) => request<LiveDraft>(`/api/draft/live/${leagueId}`),
  valuationOptions: () => request<ValuationOptions>('/api/valuation/options'),
  valuation: (q: ValuationQuery) => {
    if (STATIC) return staticValuation(q)
    const params = new URLSearchParams({
      kind: q.kind, source: q.source, season: q.season, basis: q.basis, model: q.model,
      dollars: q.dollars, pool: String(q.pool), punt: q.punt.join(','),
    })
    return request<Valuation>(`/api/valuation?${params}`)
  },
  playerModels: (id: number, q: ValuationQuery) => {
    if (STATIC) return staticPlayerModels(id, q)
    const params = new URLSearchParams({
      kind: q.kind, source: q.source, season: q.season, basis: q.basis,
      dollars: q.dollars, pool: String(q.pool), punt: q.punt.join(','),
    })
    return request<PlayerModels>(`/api/valuation/player/${id}?${params}`)
  },
  playerCard: (id: number) => request<PlayerCard>(`/api/players/${id}/card`),
  playerTags: (id: number) => request<PlayerTag[]>(`/api/knowledge/players/${id}/tags`),
  teamDepth: (team: string) => request<TeamDepth>(`/api/teams/${team}/depth`),
  tags: () => request<TagCount[]>('/api/knowledge/tags'),
  tagPlayers: (tag: string) => request<TagPlayer[]>(`/api/knowledge/tags/${encodeURIComponent(tag)}`),
  article: (slug: string) => request<Article>(`/api/knowledge/articles/${slug}`),
}
