// Draft assistant (VISION "Draft assistant", user request 2026-10-17). Two parts:
// - Live: from the rosters so far, my projected team, which build the players I hold point to, the best
//   buys with their category trade-offs, and a break-even price for the nominated player
//   (POST /api/assistant/live, about a second; refetched after every sale and nomination).
// - Plan: before the draft, the best 12 for 200 USD per build at room prices (GET /api/assistant/builds).
// Lines are facts from the simulation, not orders (user, 2026-10-05: the user decides).
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, STATIC, type Assist, type BuildPlans, type ValuationQuery } from '../../api/client'
import { RosterCard, type CardCat, type CardPlayer } from '../../components/RosterCard'
import { CAT_LABEL } from '../../lib/categories'
import { useLiveBoard } from '../../lib/liveBoard'
import { useSynced } from '../../lib/synced'

const DEFAULT_BASE = { kind: 'projection', source: 'yahoo', season: '2026-27', basis: 'totals' }

/** Change cell: full color at +-15 points. */
function Delta({ v, full = 15 }: { v: number; full?: number }) {
  const a = Math.min(Math.abs(v) / full, 1)
  return <td className={`heat ${v >= 0 ? 'good' : 'bad'} num`}><span style={{ '--a': a.toFixed(3) } as CSSProperties}>{v > 0 ? '+' : ''}{v.toFixed(1)}</span></td>
}

/** Category strip of a card from win probabilities (percent). */
function probCats(cats: string[], probs: number[], ranks?: number[]): CardCat[] {
  return cats.map((c, i) => ({ key: c, label: CAT_LABEL[c], text: `${Math.round(probs[i])}`, good: probs[i] >= 50,
    a: Math.min(Math.abs(probs[i] - 50) / 50, 1),
    title: `${CAT_LABEL[c]}: weekly win ${probs[i].toFixed(0)}%${ranks ? `, rank ${ranks[i]} of 12` : ''}` }))
}

const badge = (v: number, label: string) => ({ text: `${Math.round(v)}%`, good: v >= 50, a: Math.min(Math.abs(v - 50) / 50, 1), title: label })

function useBase() {
  const [query] = useSynced<ValuationQuery | null>('pv-query', null)
  return query ? { kind: query.kind, source: query.source, season: query.season, basis: query.basis } : DEFAULT_BASE
}

function insights(a: Assist): string[] {
  const out: string[] = []
  const cats = a.categories
  const free = a.builds.find((b) => b.build === 'none')
  const best = [...a.builds].sort((x, y) => y.match - x.match)[0]
  out.push(`Plain plan (best G-score fill at room prices): ${a.base.match.toFixed(0)}% of matchups won.`)
  if (free && best) {
    const forced = [...a.builds].filter((b) => b.punts.length).sort((x, y) => y.match - x.match)[0]
    out.push(`Best fill of your open slots: ${free.match.toFixed(0)}%. Best forced build: ${forced.label} ${forced.match.toFixed(0)}%.`)
  }
  if (free) {
    const lost = cats.filter((_, i) => free.per_cat[i] < 30).map((c) => CAT_LABEL[c])
    if (lost.length) out.push(`The best fill gives up on: ${lost.join(', ')} (under 30% weekly win).`)
  }
  const weak = cats.map((c, i) => ({ c, i })).filter(({ i }) => a.base.ranks[i] >= 10)
  for (const { c, i } of weak) {
    const fix = [...a.builds].sort((x, y) => y.per_cat[i] - x.per_cat[i])[0]
    out.push(`${CAT_LABEL[c]}: rank ${a.base.ranks[i]} of 12 in the projection. Best fill for it reaches ${fix.per_cat[i].toFixed(0)}% (${fix.label}).`)
  }
  if (a.breakeven) {
    const b = a.breakeven
    out.push(b.price > 0
      ? `${b.name}: worth up to $${b.price} to your team. Live room price $${b.live_price}.`
      : `${b.name}: buying him at any price leaves your projection worse than the best fill without him.`)
  }
  if (a.unknown_players.length) out.push(`${a.unknown_players.length} drafted players are not in this base: they count as empty.`)
  return out
}

function Live({ base }: { base: typeof DEFAULT_BASE }) {
  const live = useLiveBoard()
  const board = live.board
  const [res, setRes] = useState<{ key: string; data: Assist } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const key = board ? `${base.source}|${base.season}|${base.basis}|${board.picks.length}|${board.nomination?.player_pk ?? ''}` : null

  useEffect(() => {
    if (!board || !key) return
    if (!board.teams.some((t) => t.mine)) { setError('My team is not known in this draft.'); return }
    let alive = true
    const teams = board.teams.map((t) => ({
      team_id: t.team_id, money_left: t.money_left, open_slots: t.open_slots, mine: t.mine,
      players: board.picks.filter((p) => p.team_id === t.team_id && p.player_pk != null).map((p) => p.player_pk as number),
    }))
    api.assist({ ...base, teams, nominated: board.nomination?.player_pk ?? null })
      .then((d) => { if (alive) { setRes({ key, data: d }); setError(null) } })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const picker = live.drafts.length > 0 && (
    <div className="live-strip">
      <label>Live draft
        <select value={live.auto ? 'auto' : live.leagueId}
          onChange={(e) => live.setChoice(e.target.value === 'auto' ? null : e.target.value)}>
          <option value="auto">Automatic (active draft){live.auto && live.leagueId ? `: ${live.leagueId}` : live.auto ? ': none' : ''}</option>
          <option value="">Off</option>
          {live.drafts.map((d) => <option key={d.league_id} value={d.league_id}>{d.league_id} ({d.kind}, {d.picks} picks)</option>)}
        </select>
      </label>
    </div>
  )
  if (!board) return <>{picker}<p className="hint">No live draft followed. The live part fills when a draft is followed.</p></>
  const a = res?.data
  const stale = res && res.key !== key
  const cats = a?.categories ?? []
  const me = board.teams.find((t) => t.mine)
  const bought: CardPlayer[] = board.picks.filter((p) => me && p.team_id === me.team_id).map((p) => ({
    id: p.player_pk ?? p.yahoo_id, name: p.name ?? String(p.yahoo_id), price: p.price,
    positions: (p.player_pk != null ? a?.positions[p.player_pk] : null) ?? null }))
  return (
    <div className="assist-live">
      {picker}
      <p className="hint">{board.picks.length} sold{stale ? ' · updating...' : ''}{a ? ` · room: $${a.money_left} for ${a.open_slots} slots` : ''}</p>
      {error && <p className="error">{error}</p>}
      {a && <>
        <ul className="assist-insights">{insights(a).map((t) => <li key={t}>{t}</li>)}</ul>

        <h3>My team by build <span className="hint">bought players + the best fill of my open slots (italic, live price); badge = weekly matchup win %</span></h3>
        <div className="rgrid">
          <RosterCard mine title="Plain plan" sub={`Best G-score fill · ranks in the tooltips`} badge={badge(a.base.match, 'Weekly matchup win %')}
            cats={probCats(cats, a.base.per_cat, a.base.ranks)}
            players={[...bought, ...a.my_fill.map((p) => ({ id: p.player_id, name: p.name, positions: p.positions, price: p.live_price, planned: true }))]} />
          {[...a.builds].sort((x, y) => y.match - x.match).map((b) => (
            <RosterCard key={b.build} title={b.label} sub={`Fill costs $${b.fill_cost}`} badge={badge(b.match, 'Weekly matchup win %')}
              cats={probCats(cats, b.per_cat)}
              players={[...bought, ...b.fill.map((p) => ({ id: p.player_id, name: p.name, positions: p.positions, price: p.live_price, planned: true }))]} />
          ))}
        </div>

        <h3>Best buys <span className="hint">at the live room price, vs my best fill without him (points of weekly win %)</span></h3>
        <table className="values">
          <thead><tr className="cols"><th>Player</th><th className="num">Price</th><th className="num">Match</th>{cats.map((c) => <th key={c} className="num cat">{CAT_LABEL[c]}</th>)}</tr></thead>
          <tbody>
            {a.candidates.slice(0, 20).map((c) => (
              <tr key={c.player_id} className={c.player_id === board.nomination?.player_pk ? 'mine' : undefined}>
                <td className="name">{c.name}</td><td className="num">${c.price}</td><Delta v={c.match_delta} full={5} />
                {c.per_cat_delta.map((v, i) => <Delta key={i} v={v} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </>}
    </div>
  )
}

function Plan({ base }: { base: typeof DEFAULT_BASE }) {
  const [plans, setPlans] = useState<BuildPlans | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = () => {
    setBusy(true)
    api.buildPlans(base).then((p) => { setPlans(p); setError(null) }).catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  const cats = useMemo(() => plans?.categories ?? [], [plans])
  return (
    <details className="assist-plan">
      <summary>Draft plan by build <span className="hint">before the draft: empty roster, $200. It ignores the players you already bought. For live advice use the cards above.</span></summary>
      <p className="hint">
        Room price = half market price, half G-score dollars, scaled to the league budget (assumed). Opponents: 60 rooms of
        average teams dealt by tiers. Weekly noise included. About 2 minutes the first time per base.
      </p>
      <button onClick={run} disabled={busy}>{busy ? 'Running...' : plans ? 'Run again' : 'Run'}</button>
      {error && <p className="error">{error}</p>}
      {plans && (
        <div className="rgrid">
          {plans.builds.map((b) => (
            <RosterCard key={b.build} title={b.label} sub={`Spent $${b.spent} · categories won ${b.cat_share.toFixed(0)}%`}
              badge={badge(b.match_share, 'Weekly matchup win % vs average rooms')}
              cats={probCats(cats, cats.map((c) => b.per_cat[c]))}
              players={b.roster.map((p) => ({ id: p.player_id, name: p.name, positions: p.positions, price: p.room_price }))} />
          ))}
        </div>
      )}
    </details>
  )
}

export function Assistant() {
  const base = useBase()
  if (STATIC) return <p className="hint">The assistant needs the backend. Not available in the static copy.</p>
  return (
    <div className="assistant">
      <p className="hint">Base: {base.source} {base.season} {base.basis} (from the value table).</p>
      <Live base={base} />
      <Plan base={base} />
    </div>
  )
}
