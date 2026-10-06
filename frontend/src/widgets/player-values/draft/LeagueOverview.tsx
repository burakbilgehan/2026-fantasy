// League overview under the value table during a live draft (T-018): simulated H2H matrix and the
// teams built so far. With a focus player, my row shows "before → after" for buying him.
import type { CSSProperties } from 'react'
import type { ValuedPlayer } from '../../../api/client'
import { CAT_LABEL } from '../../../lib/categories'
import { catRanks, h2h, H2H_CATS, type Record3 } from '../../../lib/h2h'
import { eligibility, STARTERS, teamLines, type DraftTeam } from './model'

const rec = (r: Record3) => (r.t ? `${r.w}-${r.l}-${r.t}` : `${r.w}-${r.l}`)
const tone = (r: Record3) => (r.w > r.l ? 'good' : r.w < r.l ? 'bad' : undefined)
const fmtCat = (c: string, v: number) => (c.endsWith('pct') ? v.toFixed(3).replace(/^0\./, '.') : v.toFixed(1))

// Rank tint: 1 = full green, last = full red.
function rankStyle(rank: number, n: number): { cls: string; style: CSSProperties } {
  const z = n > 1 ? 1 - (2 * (rank - 1)) / (n - 1) : 0
  return { cls: `heat ${z >= 0 ? 'good' : 'bad'}`, style: { '--a': Math.abs(z).toFixed(3) } as CSSProperties }
}

export function LeagueOverview({ teams, focus }: { teams: DraftTeam[]; focus: ValuedPlayer | null }) {
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
                        {rec(r)}{changed && <span className={`after ${tone(a!) ?? ''}`}> → {rec(a!)}</span>}
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

      <h3>Teams</h3>
      <div className="team-boxes">
        {[...teams].sort((a, b) => Number(b.mine) - Number(a.mine) || a.team_id - b.team_id).map((t) => {
          const elig = eligibility(t.players.map((p) => p.row))
          const line = before.get(t.team_id)
          const rk = ranks.get(t.team_id)!
          return (
            <section key={t.team_id} className={t.mine ? 'team-box mine' : 'team-box'}>
              <header>
                <strong>{t.label}</strong>
                <span>${t.money_left} left · {t.open_slots} open · max ${t.max_bid}{t.autopick ? ' · auto' : ''}</span>
              </header>
              <div className="elig" title="Players eligible per position / starter slots (plus 3 Util, 2 BN)">
                {Object.entries(STARTERS).map(([pos, slots]) => <span key={pos}>{pos} {elig[pos]}/{slots}</span>)}
              </div>
              <ol className="roster">
                {t.players.map((p, i) => (
                  <li key={`${p.pk ?? p.name}-${i}`}>
                    <span className="pname">{p.name}</span>
                    <span className="ppos">{p.row?.positions?.join(',') ?? ''}</span>
                    <span className="num">${p.price}</span>
                  </li>
                ))}
                {!t.players.length && <li className="hint">No players yet</li>}
              </ol>
              <table className="team-line" title="Per game: the players' totals / their games for counting stats, makes / attempts for FG% and FT%. Color: league rank.">
                <thead><tr>{H2H_CATS.map((c) => <th key={c}>{CAT_LABEL[c]}</th>)}</tr></thead>
                <tbody>
                  <tr>
                    {H2H_CATS.map((c) => {
                      if (!line) return <td key={c} className="num">-</td>
                      const rs = rankStyle(rk[c], n)
                      return <td key={c} className={`${rs.cls} num`} title={`Rank ${rk[c]} of ${n}`}><span style={rs.style}>{fmtCat(c, line[c])}</span></td>
                    })}
                  </tr>
                </tbody>
              </table>
            </section>
          )
        })}
      </div>
    </div>
  )
}
