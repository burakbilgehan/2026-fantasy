// Season H2H simulation of the drafted rosters (user, 2026-10-18). Backend: app/api/season.py, model in
// app/analytics/season_sim.py: expected lines day by day (availability x per-game line), best 10 starters
// by position, Yahoo weeks and matchups. Shows the league table and my week-by-week matchups.
import { useEffect, useState } from 'react'
import { api, type SeasonSim as Sim, type ValuationQuery } from '../../../api/client'
import { CAT_LABEL } from '../../../lib/categories'

const rec = (r: number[]) => (r[2] ? `${r[0]}-${r[1]}-${r[2]}` : `${r[0]}-${r[1]}`)
const pct = (r: number[]) => {
  const n = r[0] + r[1] + r[2]
  return n ? ((r[0] + r[2] / 2) / n).toFixed(3).replace(/^0\./, '.') : '-'
}
const day = (iso: string) => { const [, m, d] = iso.split('-'); return `${+m}/${+d}` }

export function SeasonSim({ leagueId, query, picks }: { leagueId: string; query: ValuationQuery | null; picks: number }) {
  const [sim, setSim] = useState<Sim | null>(null)
  const [error, setError] = useState<string | null>(null)
  const kind = query?.kind ?? 'projection', source = query?.source ?? 'yahoo', season = query?.season ?? ''

  // Reload when the base changes or a pick lands.
  useEffect(() => {
    let alive = true
    api.seasonSim(leagueId, season ? { kind, source, season } : { kind, source, season: '2026-27' })
      .then((s) => { if (alive) { setSim(s); setError(null) } })
      .catch((e) => { if (alive) setError(String(e)) })
    return () => { alive = false }
  }, [leagueId, kind, source, season, picks])

  if (error) return <p className="error">Season sim: {error}</p>
  if (!sim) return <p className="hint">Season sim: loading…</p>

  const name = new Map(sim.teams.map((t) => [t.team_id, t.name ?? `Team ${t.team_id}`]))
  const order = [...sim.teams].sort((a, b) => (b.record[0] + b.record[2] / 2) - (a.record[0] + a.record[2] / 2))
  const my = sim.my_team_id
  const avgUsed = sim.teams.reduce((a, t) => a + t.used, 0) / sim.teams.length
  const avgPo = sim.teams.reduce((a, t) => a + t.playoff_used, 0) / sim.teams.length

  return (
    <div className="season-sim">
      <h3>Season sim <span className="hint">· base {source} {sim.base.season} · expected lines day by day: availability (GP / 82) x per-game line,
        best 10 starters by position, Yahoo weeks and matchups · no waivers, trades or IL moves</span></h3>
      <div className="ss-grid">
        <table className="standings ss-table">
          <thead>
            <tr>
              <th className="num">#</th><th>Team</th>
              <th className="num" title="Scheduled H2H, weeks 1-18: category wins-losses-ties">Record</th>
              <th className="num" title="Every team against every other team every week: category win share (no schedule luck)">All-play</th>
              <th className="num" title="Starter games used over the season (10 slots a day)">Games</th>
              <th className="num" title="Games the bench could not use: more than 10 starters or no open slot for the position">Lost</th>
              <th className="num" title="Starter games used in playoff weeks 19-21">PO games</th>
            </tr>
          </thead>
          <tbody>
            {order.map((t, i) => (
              <tr key={t.team_id} className={t.mine ? 'mine' : undefined}>
                <td className="num">{i + 1}</td>
                <td className="team" title={t.name ?? ''}>{t.name}</td>
                <td className="num">{rec(t.record)}</td>
                <td className="num">{pct(t.allplay)}</td>
                <td className={`num ${t.used >= avgUsed ? 'good' : 'bad'}`}>{t.used.toFixed(0)}</td>
                <td className="num">{(t.available - t.used).toFixed(1)}</td>
                <td className={`num ${t.playoff_used >= avgPo ? 'good' : 'bad'}`}>{t.playoff_used.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {my != null && (
          <table className="standings ss-weeks">
            <thead>
              <tr>
                <th className="num">Wk</th><th>Dates</th><th>Opponent</th>
                <th className="num" title="Starter games used: me - opponent">Games</th>
                <th className="num">Score</th>
                {sim.cats.map((c) => <th key={c} className="num">{CAT_LABEL[c]}</th>)}
              </tr>
            </thead>
            <tbody>
              {sim.weeks.map((w) => {
                const m = w.matchups.find((x) => x.a === my || x.b === my)
                const mine = w.teams[String(my)]
                if (!m) {
                  return (
                    <tr key={w.week}>
                      <td className="num">{w.week}</td><td>{day(w.first)}-{day(w.last)}</td><td className="hint">playoffs</td>
                      <td className="num">{mine?.used.toFixed(1)}</td><td />{sim.cats.map((c) => <td key={c} />)}
                    </tr>
                  )
                }
                const flip = m.b === my
                const opp = flip ? m.a : m.b
                const cats = flip ? m.cats.map((x) => -x) : m.cats
                const score = flip ? [m.score[1], m.score[0], m.score[2]] : m.score
                const theirs = w.teams[String(opp)]
                return (
                  <tr key={w.week}>
                    <td className="num">{w.week}</td>
                    <td>{day(w.first)}-{day(w.last)}</td>
                    <td className="team" title={name.get(opp)}>{name.get(opp)}</td>
                    <td className="num">{mine.used.toFixed(1)}-{theirs.used.toFixed(1)}</td>
                    <td className={`num ${score[0] > score[1] ? 'good' : score[0] < score[1] ? 'bad' : ''}`}>{rec(score)}</td>
                    {cats.map((x, i) => <td key={i} className={`num ${x > 0 ? 'good' : x < 0 ? 'bad' : ''}`}>{x > 0 ? 'W' : x < 0 ? 'L' : 'T'}</td>)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      {sim.missing.length > 0 && <p className="hint">{sim.missing.length} drafted players have no projection and are left out.</p>}
    </div>
  )
}
