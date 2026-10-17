// Player panel above the value table during a live draft (T-018): the nominated player, or the player
// the user clicked in the table. Numbers, our analysis (profile, tags) and fit facts for my team.
// Fit lines are facts (counts, money, H2H before and after), not verdicts (user, 2026-10-05).
import { useEffect, useState, type CSSProperties } from 'react'
import { api, type PlayerCard, type PlayerTag, type ValuationQuery, type ValuedPlayer, type WhatIf } from '../../../api/client'
import { Headshot } from '../../../components/Headshot'
import { TagChip } from '../../../components/TagChip'
import { CAT_LABEL } from '../../../lib/categories'
import { catRanks, h2h, H2H_CATS } from '../../../lib/h2h'
import { eligibility, STARTERS, teamLines, type DraftTeam } from './model'
import { ListMarks } from '../../../lib/playerLists'

// Tags shown as risk lines in the fit section (names from docs/GLOSSARY.md).
const RISK = /bust|injur|load management|shutdown|trade risk|minutes risk/i

function perGame(p: ValuedPlayer, c: string): string {
  const s = p.stats
  // Rate with the volume (attempts per game) in parentheses (user, 2026-10-06).
  const vol = (att: number | null | undefined) => (att != null && s.gp ? ` (${(att / s.gp).toFixed(1)})` : '')
  if (c === 'fg_pct') return s.fga ? ((s.fgm ?? 0) / s.fga).toFixed(3).replace(/^0\./, '.') + vol(s.fga) : '-'
  if (c === 'ft_pct') return s.fta ? ((s.ftm ?? 0) / s.fta).toFixed(3).replace(/^0\./, '.') + vol(s.fta) : '-'
  return s.gp ? ((s[c] ?? 0) / s.gp).toFixed(1) : '-'
}

function useCard(pk: number | null) {
  const [card, setCard] = useState<{ pk: number; card: PlayerCard | null; tags: PlayerTag[] } | null>(null)
  useEffect(() => {
    if (pk == null) return
    let alive = true
    Promise.all([api.playerCard(pk).catch(() => null), api.playerTags(pk).catch(() => [])])
      .then(([c, t]) => { if (alive) setCard({ pk, card: c, tags: t }) })
    return () => { alive = false }
  }, [pk])
  return card && card.pk === pk ? card : null
}

/** Weekly simulation of the candidate on my team against the rosters so far (POST /api/draft/whatif, ms).
 *  Refetches when the focus player, the base or any roster changes, so it follows the draft live. */
function useWhatIf(query: ValuationQuery | null, teams: DraftTeam[], row: ValuedPlayer | null) {
  const [res, setRes] = useState<{ key: string; data: WhatIf } | null>(null)
  const me = teams.find((t) => t.mine)
  const ids = (t: DraftTeam) => t.players.map((p) => p.pk).filter((x): x is number => x != null)
  const my = me ? ids(me) : []
  const opponents = me ? teams.filter((t) => t.team_id !== me.team_id).map(ids) : []
  const key = query && row && me
    ? `${row.player_id}|${query.kind}|${query.source}|${query.season}|${query.basis}|${my.join(',')}|${opponents.map((o) => o.join(',')).join(';')}`
    : null
  useEffect(() => {
    if (!key || !query || !row) return
    let alive = true
    api.whatIf({ kind: query.kind, source: query.source, season: query.season, basis: query.basis, my, opponents, candidate: row.player_id })
      .then((d) => { if (alive) setRes({ key, data: d }) })
      .catch(() => { if (alive) setRes(null) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return res && res.key === key ? res.data : null
}

export function FocusPanel({ row, name, bid, nominated, teams, query, onOpen, onClear }: {
  row: ValuedPlayer | null
  query: ValuationQuery | null
  name: string
  bid: { amount: number; team: string } | null
  nominated: boolean
  teams: DraftTeam[]
  onOpen: () => void
  onClear?: () => void
}) {
  const info = useCard(row?.player_id ?? null)
  const sim = useWhatIf(query, teams, row)
  const me = teams.find((t) => t.mine)
  const summary = info?.card?.summary
  const tags = info?.tags ?? []

  const price = bid?.amount ?? row?.market.market_price ?? null
  const opp = row?.dollars != null && row.market.market_price != null ? row.dollars - row.market.market_price : null

  // Fit facts for my team.
  let fit: { label: string; text: string; tone?: 'good' | 'bad' }[] = []
  if (me && row) {
    const before = teamLines(teams)
    const after = teamLines(teams, { team: me.team_id, row })
    const hb = h2h(before).get(me.team_id)!, ha = h2h(after).get(me.team_id)!
    const rb = catRanks(before).get(me.team_id)!, ra = catRanks(after).get(me.team_id)!
    const eb = eligibility(me.players.map((p) => p.row)), ea = eligibility([...me.players.map((p) => p.row), row])
    const moved = H2H_CATS.filter((c) => rb[c] !== ra[c])
    fit = [
      { label: 'Positions', text: Object.keys(STARTERS).map((pos) => `${pos} ${eb[pos]} → ${ea[pos]} (of ${STARTERS[pos]})`).join(' · ') },
      { label: 'Roster', text: `${me.players.length} → ${me.players.length + 1} players, ${me.open_slots} open slots now` },
    ]
    if (price != null) {
      const left = me.money_left - Math.round(price)
      const open = me.open_slots - 1
      fit.push({ label: 'Money', tone: Math.round(price) > me.max_bid ? 'bad' : undefined,
        text: `at $${Math.round(price)}${bid ? ' (current bid)' : ' (market price)'}: $${me.money_left} → $${left} left`
          + (open > 0 ? `, $${(left / open).toFixed(1)} per open slot` : '')
          + ` · spent $${me.spent} on ${me.players.length} so far · my max bid $${me.max_bid}` })
    }
    fit.push({ label: 'H2H', tone: ha.wins > hb.wins ? 'good' : ha.wins < hb.wins ? 'bad' : undefined,
      text: `${hb.wins} → ${ha.wins} of ${hb.games} category wins` })
    if (moved.length) fit.push({ label: 'My ranks', text: moved.map((c) => `${CAT_LABEL[c]} ${rb[c]} → ${ra[c]}`).join(' · ') })
    if (sim) {
      // Expected weekly lines (per game x games that week x availability) against every roster so far.
      const d = sim.delta
      const sign = (v: number, digits = 1) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`
      const cats = sim.categories.map((c, i) => ({ c, v: d.per_cat[i] })).filter((x) => Math.abs(x.v) >= 3).sort((a, b) => b.v - a.v)
      const adds = cats.filter((x) => x.v > 0).map((x) => `${CAT_LABEL[x.c]} ${sign(x.v, 0)}`).join(' · ')
      const costs = cats.filter((x) => x.v < 0).map((x) => `${CAT_LABEL[x.c]} ${sign(x.v, 0)}`).join(' · ')
      const up = d.per_opp.filter((x) => x > 0).length, down = d.per_opp.filter((x) => x < 0).length
      fit.push({ label: 'Weekly sim', tone: d.cat_share > 0 ? 'good' : d.cat_share < 0 ? 'bad' : undefined,
        text: `${sim.before.cat_share.toFixed(1)}% → ${sim.after.cat_share.toFixed(1)}% of category matchups (${sign(d.cat_share)})`
          + ` · weekly wins ${sign(d.match_share)} points · better vs ${up} teams, worse vs ${down}` })
      if (adds || costs) fit.push({ label: 'Adds · costs', text: [adds && `adds ${adds}`, costs && `costs ${costs}`].filter(Boolean).join(' | ') })
    }
  }
  const risks = tags.filter((t) => RISK.test(t.tag))
  if (risks.length) fit.push({ label: 'Risk', tone: 'bad', text: risks.map((t) => t.tag + (t.detail ? ` (${t.detail})` : '')).join(' · ') })

  return (
    <section className="focus-panel" aria-label="Player in focus">
      <div className="focus-head">
        {row && <Headshot nbaId={row.nba_id} name={row.name} size="lg" />}
        <div className="focus-title">
          <span className="focus-kind">{nominated ? 'Nominated' : 'Selected'}</span>
          <h3>{row?.name ?? name}{row && <> <ListMarks pk={row.player_id} /></>}</h3>
          {row && <span className="hint">{row.team ?? 'FA'} · {row.positions?.join(',') ?? '-'} · {row.stats.gp?.toFixed(0) ?? '-'} GP{row.injury ? ` · ${row.injury}` : ''}</span>}
        </div>
        {bid && <div className="focus-bid"><small>Current bid</small><strong>${bid.amount}</strong><small>{bid.team}</small></div>}
        {row && (
          <dl className="focus-prices">
            <div><dt>Our price</dt><dd>{row.dollars != null ? `$${row.dollars.toFixed(0)}` : '-'}</dd></div>
            <div><dt>Market</dt><dd>{row.market.market_price != null ? `$${row.market.market_price.toFixed(0)}` : '-'}</dd></div>
            <div><dt>Opportunity</dt><dd className={opp == null ? undefined : opp >= 0 ? 'good' : 'bad'}>{opp == null ? '-' : `${opp >= 0 ? '+' : '-'}$${Math.abs(opp).toFixed(0)}`}</dd></div>
            <div><dt>Yahoo / ESPN avg</dt><dd>{row.market.yahoo_average_cost != null ? `$${row.market.yahoo_average_cost.toFixed(0)}` : '-'} / {row.market.espn_average_cost != null ? `$${row.market.espn_average_cost.toFixed(0)}` : '-'}</dd></div>
            <div><dt>Rank · value</dt><dd>{row.rank ?? '-'} · {row.total?.toFixed(2) ?? '-'}</dd></div>
          </dl>
        )}
        <div className="focus-actions">
          {row && <button onClick={onOpen}>Full profile</button>}
          {onClear && <button onClick={onClear}>Back to nominated</button>}
        </div>
      </div>
      {!row && <p className="hint">Not in the value table base.</p>}
      {row && (
        <div className="focus-body">
          <div className="focus-col">
            <table className="team-line">
              <thead><tr>{H2H_CATS.map((c) => <th key={c}>{CAT_LABEL[c]}</th>)}</tr></thead>
              <tbody><tr>{H2H_CATS.map((c) => {
                const z = row.z?.[c]
                const a = z == null ? 0 : Math.min(Math.abs(z) / 2.5, 1)
                return <td key={c} className={z == null ? 'num' : `heat ${z >= 0 ? 'good' : 'bad'} num`}>
                  <span style={{ '--a': a.toFixed(3) } as CSSProperties}>{perGame(row, c)}</span></td>
              })}</tr></tbody>
            </table>
            {fit.length > 0 && (
              <dl className="fit">
                {fit.map((f) => <div key={f.label}><dt>{f.label}</dt><dd className={f.tone}>{f.text}</dd></div>)}
              </dl>
            )}
          </div>
          <div className="focus-col">
            {tags.length > 0 && <div className="tag-row">{tags.map((t) => <TagChip key={`${t.channel}-${t.tag}`} t={t} />)}</div>}
            {summary?.note && <p className="focus-note">{summary.note}</p>}
            {summary && (summary.durable.length > 0 || summary.current.length > 0) && (
              <div className="focus-lists">
                {summary.durable.length > 0 && <div><h4>Lasting</h4><ul>{summary.durable.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
                {summary.current.length > 0 && <div><h4>Now</h4><ul>{summary.current.slice(0, 6).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
              </div>
            )}
            {info && !summary && <p className="hint">No expert profile for this player.</p>}
          </div>
        </div>
      )}
    </section>
  )
}
