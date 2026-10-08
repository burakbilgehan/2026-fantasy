// League overview under the value table during a live draft (T-018): simulated H2H matrix and the
// teams built so far. With a focus player, my row shows "before → after" for buying him.
import type { CSSProperties } from 'react'
import type { ValuedPlayer } from '../../../api/client'
import { CAT_LABEL } from '../../../lib/categories'
import { catRanks, h2h, H2H_CATS, type Record3 } from '../../../lib/h2h'
import { CategorySupply } from './CategorySupply'
import { eligibility, STARTERS, teamLines, type DraftTeam } from './model'

// Last name only in the team table (full name on hover): 12 players must fit in two lines.
const surname = (name: string) => { const w = name.split(' '); return w.length > 1 ? w.slice(1).join(' ') : name }
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

  return (
    <div className="league-overview">
      <h3>H2H, simulated {focus && me ? <span className="hint">· my row: now → if I buy {focus.name}</span> : null}</h3>
      <div className="table-wrap">
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
      </div>

      <CategorySupply pool={pool} sold={sold} />
      <h3>Teams</h3>
      {/* One row per team (user, 2026-10-06): fixed columns that do not overlap as rosters fill;
          the players wrap inside their own cell. Same order as the matrix. */}
      <div className="table-wrap teams-wrap">
        <table className="teams">
          <thead>
            <tr>
              <th>Team</th>
              <th className="num" title="Money left">$ left</th>
              <th className="num" title="Open roster slots">Open</th>
              <th className="num" title="Money left minus 1 USD per other open slot">Max bid</th>
              <th title="Players eligible per position / starter slots (plus 3 Util, 2 BN)">G · F · C</th>
              {H2H_CATS.map((c) => <th key={c} className="num">{CAT_LABEL[c]}</th>)}
              <th>Players, best value first</th>
            </tr>
          </thead>
          <tbody>
            {order.map((t) => {
              const elig = eligibility(t.players.map((p) => p.row))
              const line = before.get(t.team_id)
              const rk = ranks.get(t.team_id)!
              // Players by the value of the model selected in the table, best first.
              const players = [...t.players].sort((a, b) => (b.row?.total ?? -1e9) - (a.row?.total ?? -1e9))
              return (
                <tr key={t.team_id} className={t.mine ? 'mine' : undefined}>
                  <td className="team">{t.label}{t.autopick ? <small className="hint"> auto</small> : null}</td>
                  <td className="num">${t.money_left}</td>
                  <td className="num">{t.open_slots}</td>
                  <td className="num">${t.max_bid}</td>
                  <td className="elig">{Object.entries(STARTERS).map(([pos, slots]) => `${elig[pos]}/${slots}`).join(' · ')}</td>
                  {H2H_CATS.map((c) => {
                    if (!line) return <td key={c} className="num">-</td>
                    const rs = rankStyle(rk[c], n)
                    return <td key={c} className={`${rs.cls} num`} title={`Rank ${rk[c]} of ${n}`}><span style={rs.style}>{fmtCat(c, line[c])}</span></td>
                  })}
                  <td className="players"><div className="pgrid">
                    {players.length ? players.map((p, i) => (
                      <span key={`${p.pk ?? p.name}-${i}`} title={`${p.name}, ${p.row?.positions?.join(',') ?? '-'}, $${p.price}`}>
                        <i>{surname(p.name)}</i><small>{p.row?.positions?.join(',') ?? ''}</small><b>${p.price}</b>
                      </span>
                    )) : <span className="hint">No players yet</span>}
                  </div></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
