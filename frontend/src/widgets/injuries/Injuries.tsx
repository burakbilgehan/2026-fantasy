// Injuries tab (user, 2026-10-18): every injured player by team, how long he is out and how far to trust it.
// Source: ESPN injuries API (RotoWire notes), read live from the browser (CORS open), refreshed every 10 min.
// Joined by name to the value table (our price, rank, Yahoo status) and to the live draft (sold players grey).
import { useEffect, useMemo, useState } from 'react'
import { api, type ValuationQuery, type ValuedPlayer } from '../../api/client'
import { Headshot } from '../../components/Headshot'
import { useLiveBoard } from '../../lib/liveBoard'
import { useSynced } from '../../lib/synced'
import { badgeOf, fmtDate, missedCamp, normName as norm, trust, useInjuries, weeksOut, type EspnInjury as Espn, type Trust } from '../../lib/injuries'

// Our rank up to which a player counts as fantasy relevant (rank, not price: our price already takes the
// missed games off a long-injured player).
const RELEVANT = 220

export function Injuries() {
  const { rows, error, fetched } = useInjuries()
  const [query] = useSynced<ValuationQuery | null>('pv-query', null)
  const [players, setPlayers] = useState<ValuedPlayer[]>([])
  const [onlyRelevant, setOnlyRelevant] = useState(true)
  const live = useLiveBoard()

  useEffect(() => {
    let alive = true
    const go = (q: ValuationQuery) => api.valuation(q).then((v) => { if (alive) setPlayers(v.players) }).catch(() => { /* table works without our prices */ })
    if (query) go(query)
    else api.valuationOptions().then((o) => { const d = o.defaults; go({ kind: d.kind, source: d.source, season: d.season, basis: d.basis, model: d.model, dollars: d.dollars, pool: d.pool, punt: [] }) })
    return () => { alive = false }
  }, [query])

  const byName = useMemo(() => new Map(players.map((p) => [norm(p.name), p])), [players])
  const sold = useMemo(() => {
    const b = live.board
    if (!b) return new Map<number, string>()
    const name = new Map(b.teams.map((t) => [t.team_id, t.name ?? `Team ${t.team_id}`]))
    return new Map(b.picks.filter((p) => p.player_pk != null).map((p) => [p.player_pk!, `$${p.price} ${name.get(p.team_id)}`]))
  }, [live.board])

  const teams = useMemo(() => {
    const m = new Map<string, { e: Espn; p: ValuedPlayer | undefined; t: Trust; w: number | null }[]>()
    for (const e of rows ?? []) {
      const p = byName.get(norm(e.name))
      // Long absences always show: their low rank is the injury itself.
      if (onlyRelevant && (p?.rank ?? Infinity) > RELEVANT && !(p && badgeOf(e)?.cls === 'long')) continue
      const list = m.get(e.team) ?? []
      list.push({ e, p, t: trust(e), w: weeksOut(e.ret) })
      m.set(e.team, list)
    }
    for (const l of m.values()) l.sort((a, b) => (b.p?.dollars ?? 0) - (a.p?.dollars ?? 0))
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [rows, byName, onlyRelevant])

  const count = teams.reduce((a, [, l]) => a + l.length, 0)
  if (error) return <p className="error">{error}</p>
  if (!rows) return <p className="hint">Loading injuries...</p>

  return (
    <div className="inj">
      <div className="inj-bar">
        <label className="toggle"><input type="checkbox" checked={onlyRelevant} onChange={(e) => setOnlyRelevant(e.target.checked)} />
          Only fantasy relevant (our top {RELEVANT})</label>
        <span className="hint">{count} players on {teams.length} teams · ESPN (RotoWire) · read {fetched?.toLocaleTimeString()} · weeks counted from opening night Oct 20 (assumed)</span>
      </div>
      <div className="inj-legend hint">
        Trust: <span className="inj-trust high">high</span> stated timeline and a return date · <span className="inj-trust medium">medium</span> one of them ·
        <span className="inj-trust low">low</span> no timetable or status only. Return dates are ESPN estimates.
      </div>
      <div className="inj-grid">
        {teams.map(([team, list]) => (
          <section key={team} className="inj-team">
            <h3>{team}</h3>
            <table>
              <tbody>
                {list.map(({ e, p, t, w }) => {
                  const s = p ? sold.get(p.player_id) : undefined
                  return (
                    <tr key={e.name} className={s ? 'sold' : undefined}>
                      <td className="inj-who">
                        <Headshot nbaId={p?.nba_id ?? null} name={e.name} />
                        <span>
                          <strong>{e.name}</strong>
                          <small>{p ? `$${(p.dollars ?? 0).toFixed(0)} ours · #${p.rank ?? '-'}` : 'not in our table'}{p?.injury ? ` · Yahoo ${p.injury}` : ''}{s ? ` · sold ${s}` : ''}</small>
                        </span>
                      </td>
                      <td>
                        <span className={`inj-status ${e.status === 'Out' ? 'out' : 'dtd'}`}>{e.status}</span>
                        <small className="inj-type">{[e.side, e.type].filter(Boolean).join(' ') || '-'}{missedCamp(e) ? ' · missed camp' : ''}</small>
                      </td>
                      <td className="num">
                        <strong>{w == null ? '-' : w >= 20 ? 'season' : w < 0.5 ? 'opening' : `${w.toFixed(1)} wk`}</strong>
                        <small>back {fmtDate(e.ret)}</small>
                      </td>
                      <td><span className={`inj-trust ${t.level}`} title={t.why}>{t.level}</span></td>
                      <td className="inj-note" title={e.long}>{e.short}<small> · {fmtDate(e.date)}</small></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </div>
  )
}
