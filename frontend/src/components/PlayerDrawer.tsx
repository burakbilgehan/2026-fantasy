import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  api, type Article, type ModelValue, type PlayerCard, type PlayerModels, type PlayerProjection, type PlayerTag, type TeamDepth,
  type ValuationQuery,
} from '../api/client'
import { CAT_LABEL } from '../lib/categories'
import { Headshot } from './Headshot'
import { Markdown } from './Markdown'

type Loaded<T> = { data: T | null; error: string | null }

/** Fetches when `key` changes. `key = null` = nothing to fetch. */
function useLoad<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<Loaded<T> & { key: string | null }>({ data: null, error: null, key: null })
  useEffect(() => {
    if (key == null) return
    let alive = true
    load()
      .then((data) => { if (alive) setState({ data, error: null, key }) })
      .catch((e: Error) => { if (alive) setState({ data: null, error: e.message, key }) })
    return () => { alive = false }
    // `load` is a new function on every render; `key` names what it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return state.key === key ? state : { data: null, error: null }
}

const money = (v: number | null | undefined, digits = 0) => (v == null ? '-' : `$${v.toFixed(digits)}`)
const mins = (v: number | null) => (v == null ? '-' : v.toFixed(1))

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="drawer-section">
      <h3>{title}{note && <small> {note}</small>}</h3>
      {children}
    </section>
  )
}

function Status({ error, what }: { error: string | null; what: string }) {
  return <p className={error ? 'error' : 'hint'}>{error ? `Could not load ${what}: ${error}` : 'Loading...'}</p>
}

function Header({ card, selected }: { card: PlayerCard; selected: ModelValue | null }) {
  const p = card.prices
  const prices: { label: string; value: string; title: string }[] = [
    { label: selected ? `${selected.label} $` : 'Model $', value: money(selected?.dollars),
      title: 'Dollars of the model selected in the value table' },
    { label: 'Yahoo avg', value: money(p.yahoo_average_cost, 1), title: 'Yahoo average auction cost' },
    { label: 'ESPN avg', value: money(p.espn_average_cost, 1), title: 'ESPN average auction price' },
    { label: 'Fantrax ADP', value: p.fantrax_adp == null ? '-' : p.fantrax_adp.toFixed(1),
      title: 'Fantrax average draft position (no auction prices on Fantrax)' },
    { label: `Our league ${p.league_last_season}`, value: p.league_last == null ? 'not drafted' : `$${p.league_last}`,
      title: 'Price in our league auction last season' },
  ]
  return (
    <>
      <div className="drawer-meta">
        <span>{card.team ?? 'No NBA team'}</span>
        <span>{card.positions?.join(', ') ?? '-'}</span>
        {card.injury && (
          <span className="injury" title={card.injury_note ?? undefined}>
            {card.injury}{card.injury_note ? ` (${card.injury_note})` : ''}
          </span>
        )}
        {card.usage.length > 0 && (
          <span title="Usage rate (NBA.com), newest season first">
            USG {card.usage.map((u) => `${u.season.slice(2)} ${u.usg_pct == null ? '-' : (u.usg_pct * 100).toFixed(1) + '%'}`)
              .join(', ')}
          </span>
        )}
      </div>
      <div className="price-strip">
        {prices.map((x) => (
          <div key={x.label} className="price" title={x.title}>
            <span className="price-label">{x.label}</span>
            <span className="price-value">{x.value}</span>
          </div>
        ))}
      </div>
    </>
  )
}

function Tags({ tags }: { tags: PlayerTag[] }) {
  if (!tags.length) return <p className="hint">No tags.</p>
  const groups = [['current', 'Current'], ['durable', 'Durable']] as const
  return (
    <>
      {groups.map(([channel, label]) => {
        const list = tags.filter((t) => t.channel === channel)
        if (!list.length) return null
        return (
          <div key={channel} className="tag-row">
            <span className="tag-group">{label}</span>
            {list.map((t, i) => (
              <span key={`${t.tag}-${i}`} className={`tag ${channel}`} title={t.detail ?? undefined}>
                {t.tag}{t.until ? ` (until ${t.until})` : ''}
              </span>
            ))}
          </div>
        )
      })}
    </>
  )
}

function ModelTable({ models, selected }: { models: ModelValue[]; selected: string }) {
  return (
    <table className="mini">
      <thead>
        <tr><th>Model</th><th className="num">Rank</th><th className="num">$</th><th className="num">Value</th></tr>
      </thead>
      <tbody>
        {models.map((m) => (
          <tr key={m.key} className={m.key === selected ? 'selected' : undefined}>
            <td>{m.label}</td>
            <td className="num">{m.rank ?? '-'}</td>
            <td className="num">{money(m.dollars)}</td>
            <td className="num">{m.total == null ? '-' : m.total.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Radar scale: z from -Z_RADAR (center) to +Z_RADAR (outer edge). Values beyond are clamped.
const Z_RADAR = 3
const RINGS = [-1.5, 0, 1.5, 3]
// Clockwise from the top. Guard stats (STL, 3PM, FT%, AST) at the top, big man stats (FG%, REB, BLK)
// at the bottom. PTS between FT% and FG%; TO between BLK and AST (ball handlers).
const RADAR_ORDER = ['tpm', 'ft_pct', 'pts', 'fg_pct', 'reb', 'blk', 'tov', 'ast', 'stl']

// Per game value of a category from season totals (percentages: makes / attempts), as label text.
function perGameText(stats: Record<string, number | null> | undefined, c: string): string | null {
  if (!stats) return null
  const v = (k: string) => stats[k] ?? 0
  if (c === 'fg_pct' || c === 'ft_pct') {
    const [m, a] = c === 'fg_pct' ? ['fgm', 'fga'] : ['ftm', 'fta']
    return v(a) ? `${(100 * v(m) / v(a)).toFixed(1)}%` : null
  }
  return v('gp') ? (v(c) / v('gp')).toFixed(1) : null
}

function CategoryRadar({ m, stats }: { m: ModelValue; stats?: Record<string, number | null> }) {
  if (!m.z) return <p className="hint">Not valued in this base.</p>
  const z = m.z
  const cats = RADAR_ORDER
  const R = 100, C = 150 // radius and center of the 300 x 300 view box
  const at = (i: number, r: number) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / cats.length
    return [C + r * Math.cos(a), C + r * Math.sin(a)]
  }
  const rOf = (v: number) => (R * (Math.max(-Z_RADAR, Math.min(Z_RADAR, v)) + Z_RADAR)) / (2 * Z_RADAR)
  const ring = (v: number) => cats.map((_, i) => at(i, rOf(v)).join(',')).join(' ')
  const shape = cats.map((c, i) => at(i, rOf(z[c])).join(',')).join(' ')
  return (
    <figure className="radar">
      <svg viewBox="-10 -10 320 320" role="img"
        aria-label={`Category z: ${cats.map((c) => `${CAT_LABEL[c]} ${z[c].toFixed(2)}`).join(', ')}`}>
        {RINGS.map((v) => <polygon key={v} points={ring(v)} className={v === 0 ? 'ring avg' : 'ring'} />)}
        {cats.map((_, i) => {
          const [x, y] = at(i, R)
          return <line key={i} x1={C} y1={C} x2={x} y2={y} className="spoke" />
        })}
        <polygon points={shape} className="shape" />
        {cats.map((c, i) => {
          const [x, y] = at(i, rOf(z[c]))
          const off = m.off.includes(c)
          return <circle key={c} cx={x} cy={y} r={3.5} className={off ? 'dot off' : z[c] >= 0 ? 'dot good' : 'dot bad'} />
        })}
        {cats.map((c, i) => {
          const [x, y] = at(i, R + 30)
          const off = m.off.includes(c)
          const raw = perGameText(stats, c)
          return (
            <text key={c} x={x} y={y} textAnchor="middle" className={off ? 'label off' : 'label'}>
              <tspan x={x} dy={raw ? '-0.75em' : '-0.2em'}>{CAT_LABEL[c]}</tspan>
              {raw && <tspan x={x} dy="1.1em" className="raw">{raw}</tspan>}
              <tspan x={x} dy="1.1em" className={off ? 'val' : z[c] >= 0 ? 'val good' : 'val bad'}>
                {z[c] >= 0 ? '+' : ''}{z[c].toFixed(1)}{off ? ' off' : ''}
              </tspan>
            </text>
          )
        })}
      </svg>
      <figcaption className="hint">
        Under each category: per game value, then z. Outer edge = z +{Z_RADAR}, center = z -{Z_RADAR}.
        Dashed ring = pool average (z 0).
        {m.off.length > 0 && ' Gray = not counted by this model.'}
      </figcaption>
    </figure>
  )
}

const PROJ_COLS = ['tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov'] as const
const PROJ_LABEL: Record<string, string> = { tpm: '3PM', pts: 'PTS', reb: 'REB', ast: 'AST', stl: 'STL', blk: 'BLK', tov: 'TO' }

/** T-025: our projection next to every source, usage, and the LLM's judgment with reasons. */
function OwnProjection({ p }: { p: PlayerProjection }) {
  if (!p.lines.length) return <p className="hint">No projection for this player.</p>
  const pct = (m: number, a: number) => (a ? `${((100 * m) / a).toFixed(1)} (${(a / 1).toFixed(1)})` : '-')
  const usg = p.usage
  return (
    <>
      <div className="table-scroll">
        <table className="proj-table">
          <thead>
            <tr>
              <th>Line</th><th className="num">GP</th><th className="num">MIN</th>
              <th className="num" title="FG% (attempts per game)">FG% (FGA)</th>
              <th className="num" title="FT% (attempts per game)">FT% (FTA)</th>
              {PROJ_COLS.map((c) => <th key={c} className="num">{PROJ_LABEL[c]}</th>)}
            </tr>
          </thead>
          <tbody>
            {p.lines.map((l) => {
              const g = l.gp || 1
              return (
                <tr key={l.key} className={l.key === 'own' ? 'proj-own' : l.key === 'actual' ? 'proj-actual'
                  : l.key.startsWith('own-') ? 'proj-ownish' : undefined}>
                  <td>{l.label}</td>
                  <td className="num">{l.gp.toFixed(0)}</td>
                  <td className="num">{l.min ? (l.min / g).toFixed(1) : '-'}</td>
                  <td className="num">{pct(l.fgm / g, l.fga / g)}</td>
                  <td className="num">{pct(l.ftm / g, l.fta / g)}</td>
                  {PROJ_COLS.map((c) => <td key={c} className="num">{(l[c] / g).toFixed(1)}</td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Per game. Own base = weighted mean of {p.base_sources.length ? p.base_sources.join(', ') : 'the sources'}.
        Own = the base judged by the LLM context layer (and manual changes). Floor and ceiling: per game only, same games.
      </p>
      <p>
        <b>Usage (USG%)</b>: {usg.projected != null ? <><b>{usg.projected.toFixed(1)} projected</b>{usg.history.length ? ', ' : ''}</> : null}
        {usg.history.map((h) => `${h.season} ${(100 * h.usg_pct).toFixed(1)}`).join(', ') || (usg.projected == null ? 'no data' : '')}
      </p>
      {p.judgment.map((j) => {
        const bits = [
          j.mpg != null && `minutes ${j.mpg}`, j.gp != null && `games ${j.gp}`,
          j.games_out ? `games out ${j.games_out}` : null, j.late_games_out ? `late games out ${j.late_games_out}` : null,
          ...Object.entries(j.multipliers).map(([k, v]) => `${k} x${v}`),
        ].filter(Boolean)
        return (
          <div key={j.source} className="proj-judgment">
            <p className="hint">
              {j.source === 'manual' ? 'Your correction' : 'LLM judgment'}, {j.updated_at.replace('T', ' ')}
              {j.model ? `, prompt ${j.model}` : ''}{bits.length ? `: ${bits.join('; ')}` : ': no change'}
            </p>
            {j.summary && <p>{j.summary}</p>}
            {j.reasons.length > 0 && (
              <ul className="proj-reasons">
                {j.reasons.map((r, i) => <li key={i}><b>{r.field}</b>: {r.text}</li>)}
              </ul>
            )}
          </div>
        )
      })}
    </>
  )
}

function ArticleItem({ a, onOpenPlayer }: { a: PlayerCard['articles'][number]; onOpenPlayer: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const art = useLoad<Article>(open ? a.slug : null, () => api.article(a.slug))
  return (
    <details className="article" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>{a.title} <small>({a.mentions} {a.mentions === 1 ? 'mention' : 'mentions'})</small></summary>
      {art.data ? <Markdown text={art.data.markdown} onOpenPlayer={onOpenPlayer} />
        : open && <Status error={art.error} what="the article" />}
    </details>
  )
}

function DepthChart({ depth, playerId, onOpenPlayer }:
  { depth: TeamDepth; playerId: number; onOpenPlayer: (id: number) => void }) {
  if (!depth.slots.length) return <p className="hint">No depth chart for {depth.team}.</p>
  return (
    <table className="mini depth">
      <thead>
        <tr>
          <th>Slot</th><th>Player</th>
          <th className="num" title="ESPN projection: minutes / games">ESPN</th>
          <th className="num" title="FanScout projection: minutes per game">FanScout</th>
          <th className="num" title="Fantrax projection: minutes per game">Fantrax</th>
          <th className="num" title="DARKO projected minutes per game">DARKO</th>
          <th className="num" title="FantasyPros projected minutes per game">FPros</th>
        </tr>
      </thead>
      <tbody>
        {depth.slots.map((s) => s.players.map((p, i) => (
          <tr key={`${s.slot}-${i}`} className={[i === 0 && 'slot-start', p.player_id === playerId && 'selected']
            .filter(Boolean).join(' ') || undefined}>
            <td className="muted">{i === 0 ? s.slot : ''}</td>
            <td>
              {p.player_id != null && p.player_id !== playerId
                ? <button className="link" onClick={() => onOpenPlayer(p.player_id!)}>{p.name}</button>
                : p.name}
              {p.player_id == null && <small className="muted" title="Name not matched to a player"> (unmatched)</small>}
            </td>
            <td className="num">{mins(p.minutes.espn)}</td>
            <td className="num">{mins(p.minutes.fanscout)}</td>
            <td className="num">{mins(p.minutes.fantrax)}</td>
            <td className="num">{mins(p.minutes.darko)}</td>
            <td className="num">{mins(p.minutes.fantasypros)}</td>
          </tr>
        )))}
      </tbody>
    </table>
  )
}

type Props = {
  playerId: number
  /** Valuation settings of the caller (value table). None: the API defaults. */
  query?: ValuationQuery | null
  onClose: () => void
  onOpenPlayer: (id: number) => void
}

/** Player profile drawer (T-028). Reusable: needs only a player id. */
export function PlayerDrawer({ playerId, query, onClose, onOpenPlayer }: Props) {
  const panel = useRef<HTMLDivElement>(null)
  const [fallback, setFallback] = useState<ValuationQuery | null>(null)
  const q = query ?? fallback

  useEffect(() => {
    if (query) return
    api.valuationOptions().then((o) => {
      const d = o.defaults
      setFallback({ kind: d.kind, source: d.source, season: d.season, basis: d.basis, model: d.model,
        dollars: d.dollars, pool: d.pool, punt: [] })
    }).catch(() => { /* the model sections show their own error */ })
  }, [query])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  useEffect(() => { panel.current?.scrollTo({ top: 0 }); panel.current?.focus() }, [playerId])

  const card = useLoad<PlayerCard>(String(playerId), () => api.playerCard(playerId))
  const proj = useLoad<PlayerProjection>(String(playerId), () => api.playerProjection(playerId))
  const tags = useLoad<PlayerTag[]>(String(playerId), () => api.playerTags(playerId))
  const models = useLoad<PlayerModels>(q ? `${playerId}|${JSON.stringify({ ...q, model: '' })}` : null,
    () => api.playerModels(playerId, q!))
  const team = card.data?.team ?? null
  const depth = useLoad<TeamDepth>(team, () => api.teamDepth(team!))

  const selected = models.data?.models.find((m) => m.key === q?.model) ?? null

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div ref={panel} className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabIndex={-1}
        onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div className="drawer-title">
            {card.data && <Headshot nbaId={card.data.nba_id} name={card.data.name} size="lg" />}
            <h2 id="drawer-title">{card.data?.name ?? 'Player'}</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close">Close</button>
        </div>
        {card.data ? <Header card={card.data} selected={selected} /> : <Status error={card.error} what="the player" />}

        <Section title="Tags">
          {tags.data ? <Tags tags={tags.data} /> : <Status error={tags.error} what="tags" />}
        </Section>

        <Section title="Own projection" note={proj.data ? `${proj.data.season}, our numbers next to every source` : undefined}>
          {proj.data ? <OwnProjection p={proj.data} /> : <Status error={proj.error} what="the projection" />}
        </Section>

        <Section title="Values across models" note={q ? `${q.season} ${q.source.toUpperCase()} ${q.kind}` : undefined}>
          {models.data
            ? models.data.in_base ? <ModelTable models={models.data.models} selected={q!.model} />
              : <p className="hint">Not in the selected base.</p>
            : <Status error={models.error} what="model values" />}
        </Section>

        <Section title="Category profile" note={selected ? `z per category, ${selected.label}` : undefined}>
          {selected ? <CategoryRadar m={selected} stats={models.data?.stats} />
            : models.data ? <p className="hint">Not in the selected base.</p>
              : <Status error={models.error} what="category values" />}
        </Section>

        <Section title="Player report" note={card.data && !card.data.has_profile ? 'no expert profile, numbers only' : undefined}>
          {card.data ? <Markdown text={card.data.report} onOpenPlayer={onOpenPlayer} />
            : <Status error={card.error} what="the report" />}
        </Section>

        <Section title="Related articles">
          {card.data
            ? card.data.articles.length
              ? card.data.articles.map((a) => <ArticleItem key={a.slug} a={a} onOpenPlayer={onOpenPlayer} />)
              : <p className="hint">No article mentions this player.</p>
            : <Status error={card.error} what="articles" />}
        </Section>

        <Section title="Team depth chart" note={depth.data ? `${depth.data.team}, Hashtag Basketball, minutes per game` : undefined}>
          {!card.data ? <Status error={card.error} what="the team" />
            : !team ? <p className="hint">No NBA team.</p>
              : depth.data ? <DepthChart depth={depth.data} playerId={playerId} onOpenPlayer={onOpenPlayer} />
                : <Status error={depth.error} what="the depth chart" />}
        </Section>

        {team && (
          <Section title="Team report">
            {depth.data
              ? depth.data.report
                ? (
                  <details className="article">
                    <summary>{team} team profile</summary>
                    <Markdown text={depth.data.report} onOpenPlayer={onOpenPlayer} />
                  </details>
                )
                : <p className="hint">No team profile.</p>
              : <Status error={depth.error} what="the team report" />}
          </Section>
        )}
      </div>
    </div>
  )
}
