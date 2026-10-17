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

export type BoardTeam = {
  team_id: number
  name: string | null
  money_left: number
  spent: number
  open_slots: number
  max_bid: number
  mine: boolean
  online: boolean
  autopick: boolean
}

export type BoardPick = { pick_no: number; player_pk: number | null; yahoo_id: string; name: string | null; team_id: number; price: number; roster_slot: string | null }

export type LiveBoard = {
  league_id: string
  my_team_id: number | null
  budget: number
  slots_per_team: number
  last_event_at: string | null
  teams: BoardTeam[]
  picks: BoardPick[]
  nomination: { player_pk: number | null; yahoo_id: string; name: string | null; high_bid: number; high_team_id: number; nominating_team_id: number | null } | null
}

export type ValuationBase = { kind: 'projection' | 'actual'; source: string; season: string; players: number; label?: string }

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
  age: number | null // age on October 1 of the base season's first year
  playoff_games: number[] | null // games of the player's NBA team in fantasy playoff weeks 19, 20, 21 (current season)
  playoff_b2b: number | null // back-to-backs of his team in those weeks
  z: Record<string, number> | null
  total: number | null
  rank: number | null
  dollars: number | null
  market: { yahoo_auction_value: number | null; yahoo_average_cost: number | null; espn_average_cost: number | null; fantrax_adp: number | null; market_price: number | null }
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
    fantrax_adp: number | null
    league_last: number | null
    league_last_season: string
  }
  usage: { season: string; usg_pct: number | null; ts_pct: number | null; gp: number }[] // newest first
  has_profile: boolean
  report: string
  summary: { note: string | null; current: string[]; durable: string[] } | null // draft panel (T-018)
  articles: { slug: string; title: string; mentions: number }[]
}

export type PlayerTag = {
  tag: string
  kind: string | null
  channel: 'durable' | 'current'
  detail: string | null
  until: string | null
  classified: boolean
  // Why the tag was given: the expert notes behind it (video, timestamp link, quote) or "stats".
  sources?: { id: string; text: string | null; quote: string | null; url: string | null; date: string | null; video: string | null }[]
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

export type PlayerModels = {
  in_base: boolean
  stats?: Record<string, number | null> // season totals of the base row
  models: ModelValue[]
}

export type DepthPlayer = {
  player_id: number | null
  name: string
  depth: number
  minutes: { espn: number | null; fanscout: number | null; fantrax: number | null; darko: number | null; fantasypros: number | null }
}

export type TeamDepth = {
  team: string
  source: string
  fetched_at: string | null
  slots: { slot: string; players: DepthPlayer[] }[]
  report: string | null
}

export type LeagueDepthPlayer = {
  player_id: number | null
  name: string
  slots: string[] // "PG1", "SG3": slot and place in the source's list
  starter_slot: string | null
  injury: string | null // ESPN status, e.g. "Out"
  minutes: { own: number | null; espn: number | null; darko: number | null; fantasypros: number | null }
  own_gp: number | null
  last: { season: string; gp: number | null; mpg: number | null }
  research: { status: 'confirmed' | 'very_likely' | 'disputed'; role_up: boolean; evidence: string; source_url: string | null; source_date: string | null } | null
}

export type LeagueDepth = {
  source: string
  fetched_at: string | null
  season: string
  research_date: string | null
  teams: { team: string; players: LeagueDepthPlayer[]; rotation: string | null
    disputed: { spot: string; candidates: string[]; lean: string; source_url: string | null; source_date: string | null }[] }[]
}

export type TagCount = { tag: string; kind: string | null; channel: string; count: number }
export type TagPlayer = { player_pk: number; name: string; team: string | null; tag: string; detail: string | null }

export type Article = { slug: string; title: string; markdown: string }

// Static build (GitHub Pages): the API is a set of JSON files made by `app/jobs/export_static.py`.
export const STATIC = import.meta.env.VITE_STATIC === '1'
const BUILD = import.meta.env.VITE_BUILD ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (STATIC) {
    if (init?.method && init.method !== 'GET') throw new Error('Not available in the static copy.')
    // ?v=<build> so a phone never mixes a new page with JSON files cached from an older deploy.
    const res = await fetch(`${import.meta.env.BASE_URL}${path.slice(1).split('?')[0]}.json?v=${BUILD}`)
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

// Lloyd's published DURANT H2H weights (app/analytics/valuation/models.py DURANT_H2H_WEIGHTS).
const DURANT_H2H_WEIGHTS: Record<string, number> = { fg_pct: 0.6, ft_pct: 0.6, tpm: 0.6, pts: 1, reb: 0.94, ast: 0.75, stl: 0.6, blk: 0.6 }

// Same rule as app/api/valuation.py off_categories.
function offCategories(model: string, z: Record<string, number>, cats: string[], punt: string[]): string[] {
  if (model === 'punt') return cats.filter((c) => punt.includes(c))
  if (model === 'minus1') return [cats.reduce((a, b) => (z[b] < z[a] ? b : a))]
  if (model === 'durant') {
    // no turnovers; the worst weighted category of the other eight is dropped
    const pool = cats.filter((c) => c !== 'tov')
    const w = (c: string) => (DURANT_H2H_WEIGHTS[c] ?? 1) * z[c]
    const worst = pool.reduce((a, b) => (w(b) < w(a) ? b : a))
    return cats.filter((c) => c === 'tov' || c === worst)
  }
  return []
}

async function staticPlayerModels(id: number, q: ValuationQuery): Promise<PlayerModels> {
  const [opts, facts] = await Promise.all([request<ValuationOptions>('/api/valuation/options'),
    request<StaticFacts>(staticPaths(q, q.model).facts)])
  const stats = facts.find((f) => f.player_id === id)?.stats
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
  return { in_base: inBase, stats, models: inBase ? models : [] }
}

export type SimScore = { cat_share: number; match_share: number; per_cat: number[]; per_opp: number[] }
/** Draft what-if (app/api/draft.py /whatif): my team with and without the candidate, week by week. Shares in percent. */
export type WhatIf = { before: SimScore; after: SimScore; delta: SimScore; weeks: number; categories: string[] }
export type WhatIfBody = { kind: string; source: string; season: string; basis: string; my: number[]; opponents: number[][]; candidate: number }

export type RoomPlayer = { player_id: number; name: string; price: number; gscore_dollars: number; market_price: number }
export type RoomTeam = { team: number; name: string; style: string; mine: boolean; spent: number; left: number; roster: RoomPlayer[]
  cat_share: number; wins: number; losses: number; playoffs: number; titles: number; per_cat: number[] }
export type RoomLog = { pick: number; player_id: number; name: string; nominator: string; winner: string; price: number; second: number; bidders: number }
/** Sim page (app/api/sim.py): one simulated auction room and season. */
export type RoomResult = {
  settings: { kind: string; source: string; season: string; basis: string; plan: string; seed: number; seasons: number; weeks: number; games: number; teams: number; market_is_model: boolean }
  categories: string[]
  teams: RoomTeam[]
  log: RoomLog[]
}

/** Draft plan by build (app/api/assistant.py /builds): best 12 per build at room prices vs dealt average rooms. */
export type BuildPlayer = { player_id: number; name: string; positions: string[] | null; room_price: number; market_price: number; gscore_dollars: number }
export type BuildPlan = { build: string; label: string; punts: string[]; match_share: number; forced_match_share: number
  cat_share: number; per_cat: Record<string, number>; spent: number; roster: BuildPlayer[] }
export type BuildPlans = { categories: string[]; builds: BuildPlan[]
  settings: { kind: string; source: string; season: string; basis: string; blend: number; rooms: number; budget: number; slots: number } }
/** Live draft assistant (app/api/assistant.py /live). Shares in percent. */
export type AssistPerson = { player_id: number; name: string; positions: string[] | null; live_price: number | null }
export type AssistBuild = { build: string; label: string; punts: string[]; match: number; cat: number; per_cat: number[]; fill: AssistPerson[]; fill_cost: number }
export type AssistCandidate = AssistPerson & { price: number; match_delta: number; cat_delta: number; per_cat_delta: number[] }
export type Assist = {
  categories: string[]
  base: { match: number; cat: number; per_cat: number[]; ranks: number[] }
  my_fill: AssistPerson[]
  builds: AssistBuild[]
  candidates: AssistCandidate[]
  breakeven: (AssistPerson & { price: number }) | null
  money_left: number
  open_slots: number
  unknown_players: number[]
  positions: Record<number, string[] | null>
}
export type AssistBody = { kind: string; source: string; season: string; basis: string; nominated: number | null
  teams: { team_id: number; players: number[]; money_left: number; open_slots: number; mine: boolean }[] }

export const api = {
  buildPlans: (q: { kind: string; source: string; season: string; basis: string }) =>
    request<BuildPlans>(`/api/assistant/builds?${new URLSearchParams(q)}`),
  assist: (body: AssistBody) => request<Assist>('/api/assistant/live', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  simRoom: (body: { plan: string; seed: number; seasons: number; kind?: string; source?: string; season?: string; basis?: string }) =>
    request<RoomResult>('/api/sim/room', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  whatIf: (body: WhatIfBody) => request<WhatIf>('/api/draft/whatif', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  league: () => request<League>('/api/league'),
  syncLeague: () => request<League>('/api/league/sync', { method: 'POST' }),
  liveDrafts: () => request<LiveDraftSummary[]>('/api/draft/live'),
  liveDraft: (leagueId: string) => request<LiveDraft>(`/api/draft/live/${leagueId}`),
  liveBoard: (leagueId: string) => request<LiveBoard>(`/api/draft/live/${leagueId}/board`),
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
  playerProjection: (id: number) => request<PlayerProjection>(`/api/players/${id}/projection`),
  playerTags: (id: number) => request<PlayerTag[]>(`/api/knowledge/players/${id}/tags`),
  depth: () => request<LeagueDepth>('/api/depth'),
  teamDepth: (team: string) => request<TeamDepth>(`/api/teams/${team}/depth`),
  tags: () => request<TagCount[]>('/api/knowledge/tags'),
  tagPlayers: (tag: string) => request<TagPlayer[]>(`/api/knowledge/tags/${encodeURIComponent(tag)}`),
  article: (slug: string) => request<Article>(`/api/knowledge/articles/${slug}`),
}

// T-025 own projection for the player drawer: every source line, usage, the LLM's judgment.
export type ProjectionLine = {
  key: string
  label: string
  gp: number
  min: number | null
  fgm: number; fga: number; ftm: number; fta: number
  tpm: number; pts: number; reb: number; ast: number; stl: number; blk: number; tov: number
}

export type PlayerProjection = {
  season: string
  lines: ProjectionLine[]
  usage: { projected: number | null; history: { season: string; usg_pct: number }[] }
  judgment: {
    source: string
    model: string | null
    updated_at: string
    usg: number | null; mpg: number | null; gp: number | null
    games_out: number | null; late_games_out: number | null
    multipliers: Record<string, number>
    summary: string | null
    reasons: { field: string; text: string; sources?: string[] }[]
  }[]
  base_sources: string[]
}
