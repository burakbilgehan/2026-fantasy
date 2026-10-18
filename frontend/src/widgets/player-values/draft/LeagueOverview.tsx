// League overview during a live draft (T-018): standings with category averages, category supply, the
// teams built so far, and the simulated H2H matrix at the bottom. With a focus player, my row shows "before → after" for buying him.
import type { CSSProperties } from 'react'
import type { ValuedPlayer } from '../../../api/client'
import { CAT_LABEL } from '../../../lib/categories'
import { catRanks, h2h, H2H_CATS, type Record3 } from '../../../lib/h2h'
import { RosterCard, type CardCat } from '../../../components/RosterCard'
import { CategorySupply } from './CategorySupply'
import { DraftSignals } from './DraftSignals'
import { PriceCurve } from './PriceCurve'
import { eligibility, STARTERS, teamLines, type DraftTeam } from './model'

const rec = (r: Record3) => (r.t ? `${r.w}-${r.l}-${r.t}` : `${r.w}-${r.l}`)
const tone = (r: Record3) => (r.w > r.l ? 'good' : r.w < r.l ? 'bad' : undefined)
const fmtCat = (c: string, v: number) => (c.endsWith('pct') ? v.toFixed(3).replace(/^0\./, '.') : v.toFixed(1))

// Rank tint: 1 = full green, last = full red.
function rankStyle(rank: number, n: number): { cls: string; style: CSSProperties } {
  const z = n > 1 ? 1 - (2 * (rank - 1)) / (n - 1) : 0
  return { cls: `heat ${z >= 0 ? 'good' : 'bad'}`, style: { '--a': Math.abs(z).toFixed(3) } as CSSProperties }
}

export function LeagueOverview({ teams, focus, pool, sold }: {
  teams: DraftTeam[]; focus: ValuedPlayer | null; pool: ValuedPlayer[]; sold: Map<number, string> | undefined
}) {
  const me = teams.find((t) => t.mine)
  const before = teamLines(teams)
  const table = h2h(before)
  const after = focus && me ? h2h(teamLines(teams, { team: me.team_id, row: focus })) : null
  const order = [...teams].sort((a, b) => table.get(b.team_id)!.wins - table.get(a.team_id)!.wins)
  const ranks = catRanks(before)
  const n = teams.length
  const short = (t: DraftTeam) => (t.label.length > 9 ? `${t.label.slice(0, 8)}.` : t.label)

  const matrix = (
    <table className="h2h">
      <thead>
        <tr>
          <th>#</th><th>Team</th>
          {order.map((t) => <th key={t.team_id} title={t.label} className={t.mine ? 'mine' : undefined}>{short(t)}</th>)}
          <th title="Category wins (ties count half) out of all category games">Wins</th>
        </tr>
      </thead>
      <tbody>
        {order.map((t, i) => {
          const row = table.get(t.team_id)!
          const aft = after?.get(t.team_id)
          const rs = rankStyle(i + 1, n)
          return (
            <tr key={t.team_id} className={t.mine ? 'mine' : undefined}>
              <td className="num">{i + 1}</td>
              <td className="team">{t.label}</td>
              {order.map((o) => {
                if (o.team_id === t.team_id) return <td key={o.team_id} className="self" />
                const r = row.vs.get(o.team_id)!
                const a = aft?.vs.get(o.team_id)
                const changed = a && rec(a) !== rec(r) && (t.mine || o.mine)
                return (
                  <td key={o.team_id} className={['num', tone(r)].filter(Boolean).join(' ')}>
                    {rec(r)}{changed && <span className={`after ${tone(a!) ?? ''}`}>→{rec(a!)}</span>}
                  </td>
                )
              })}
              <td className={`${rs.cls} num`}>
                <span style={rs.style}>{row.wins}/{row.games}
                  {aft && aft.wins !== row.wins && <> → {aft.wins} ({aft.wins > row.wins ? '+' : ''}{aft.wins - row.wins})</>}
                </span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )

  // Standings (user, 2026-10-18): the matrix order (best simulated H2H on top), the team's category
  // averages in the cells, colored by rank, so a weak category shows at a glance. The matrix moved down.
  return (
    <div className="league-overview">
      <h3>Standings <span className="hint">· order: simulated H2H · cells: team average, color by rank</span></h3>
      <div className="table-wrap standings-wrap">
        <table className="standings">
          <thead>
            <tr>
              <th className="num">#</th><th>Team</th>
              {H2H_CATS.map((c) => <th key={c} className="num">{CAT_LABEL[c]}</th>)}
              <th className="num" title="Simulated H2H: category wins (ties count half) out of all category games">Wins</th>
            </tr>
          </thead>
          <tbody>
            {order.map((t, i) => {
              const line = before.get(t.team_id)
              const rk = ranks.get(t.team_id)!
              const row = table.get(t.team_id)!
              return (
                <tr key={t.team_id} className={t.mine ? 'mine' : undefined}>
                  <td className="num">{i + 1}</td>
                  <td className="team" title={t.label}>{t.label}</td>
                  {H2H_CATS.map((c) => {
                    const h = rankStyle(rk[c], n)
                    return (
                      <td key={c} className={line ? `${h.cls} num` : 'num'} title={`${CAT_LABEL[c]}: rank ${rk[c]} of ${n}`}>
                        <span style={line ? h.style : undefined}>{line ? fmtCat(c, line[c]) : '-'}</span>
                      </td>
                    )
                  })}
                  <td className="num">{row.wins}/{row.games}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="side">
        <CategorySupply pool={pool} sold={sold} />
        <DraftSignals teams={teams} pool={pool} sold={sold} />
      </div>
      <PriceCurve teams={teams} />
      <h3>Teams <span className="hint">same order as the standings · category cells: team average, color by rank</span></h3>
      <div className="table-wrap teams-wrap">
        <div className="rgrid">
          {order.map((t) => {
            const elig = eligibility(t.players.map((p) => p.row))
            const line = before.get(t.team_id)
            const rk = ranks.get(t.team_id)!
            const cats: CardCat[] = H2H_CATS.map((c) => {
              const z = n > 1 ? 1 - (2 * (rk[c] - 1)) / (n - 1) : 0
              return { key: c, label: CAT_LABEL[c], text: line ? fmtCat(c, line[c]) : '-', good: z >= 0, a: line ? Math.abs(z) : 0,
                title: `${CAT_LABEL[c]}: rank ${rk[c]} of ${n}` }
            })
            return (
              <RosterCard key={t.team_id} mine={t.mine} title={<>{t.label}{t.autopick ? <small className="hint"> auto</small> : null}</>}
                sub={`$${t.money_left} left · ${t.open_slots} open · max bid $${t.max_bid} · G ${elig.G}/${STARTERS.G} F ${elig.F}/${STARTERS.F} C ${elig.C}/${STARTERS.C}`}
                cats={cats}
                players={t.players.map((p, i) => ({ id: p.pk ?? `${p.name}-${i}`, name: p.name, positions: p.row?.positions ?? null, price: p.price }))} />
            )
          })}
        </div>
        <h3>H2H, simulated {focus && me ? <span className="hint">· my row: now → if I buy {focus.name}</span> : null}</h3>
        <div className="h2h-wrap">{matrix}</div>
      </div>
    </div>
  )
}
