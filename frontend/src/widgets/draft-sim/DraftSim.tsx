// Sim page: one simulated auction room (12 managers with different valuations) and a Monte Carlo season.
// Shows how every team was built, the auction log and who won (user, 2026-10-13). Backend: app/api/sim.py.
import { useEffect, useState, type CSSProperties } from 'react'
import { api, STATIC, type RoomResult, type RoomTeam } from '../../api/client'
import { CAT_LABEL } from '../../lib/categories'

const PLANS = [
  { key: 'one_star', label: 'One star + the rest at value' },
  { key: 'two_stars', label: 'Two stars + cheap fill' },
  { key: 'balanced', label: 'Balanced (G-score dollars)' },
  { key: 'bargains_plus', label: 'Bargains +30%' },
  { key: 'no_stars', label: 'No stars' },
]

function pct(v: number): string { return `${v.toFixed(0)}%` }

function Heat({ v, mid, full, text }: { v: number; mid: number; full: number; text: string }) {
  const z = (v - mid) / full
  const a = Math.min(Math.abs(z), 1)
  return <td className={`heat ${z >= 0 ? 'good' : 'bad'} num`}><span style={{ '--a': a.toFixed(3) } as CSSProperties}>{text}</span></td>
}

export function DraftSim() {
  const [plan, setPlan] = useState('one_star')
  const [seed, setSeed] = useState(1)
  const [res, setRes] = useState<RoomResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  const run = () => {
    setBusy(true); setError(null)
    api.simRoom({ plan, seed, seasons: 300 })
      .then((r) => setRes(r)).catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  useEffect(() => { if (!STATIC) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (STATIC) return <p className="hint">The simulation needs the backend. Not available in the static copy.</p>
  const cats = res?.categories ?? []
  const me = res?.teams.find((t) => t.mine)
  return (
    <div className="draft-sim">
      <div className="controls">
        <label>My plan
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            {PLANS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </label>
        <label>Seed <input type="number" value={seed} min={1} max={9999} onChange={(e) => setSeed(Number(e.target.value) || 1)} /></label>
        <button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run'}</button>
        {res && <span className="hint">
          {res.settings.teams} teams, {res.settings.games} regular weeks + playoffs, {res.settings.seasons} simulated seasons, base {res.settings.source} {res.settings.season}.
          {res.settings.market_is_model ? ' No market prices for this season: the market managers use G-score dollars.' : ''}
        </span>}
      </div>
      {error && <p className="error">{error}</p>}
      {res && me && (
        <p className="hint">
          Room rule: 4 managers pay the market price, 2 use z-score, 1 Minus-1, 1 DURANT, 1 points-league dollars, 1 chases stars, 1 hunts bargains, and me.
          A sale goes to the highest bid at the second-highest bid plus 1. The season adds week-to-week noise from the game logs.
          My team: {me.wins}-{me.losses}, {pct(me.cat_share)} of category matchups, playoffs {pct(me.playoffs)}, title {pct(me.titles)}.
        </p>
      )}
      {res && (
        <table className="values sim">
          <thead>
            <tr className="cols">
              <th>#</th><th>Team</th><th>Plan</th><th className="num">W-L</th><th className="num" title="Share of category matchups won, all teams, all weeks">Cat %</th>
              <th className="num">Playoffs</th><th className="num">Title</th><th className="num">Spent</th><th className="num">Left</th>
              {cats.map((c) => <th key={c} className="num cat">{CAT_LABEL[c]}</th>)}
              <th>Roster (price)</th>
            </tr>
          </thead>
          <tbody>
            {res.teams.map((t, i) => (
              <tr key={t.team} className={t.mine ? 'mine clickable' : 'clickable'} onClick={() => setOpen(open === t.team ? null : t.team)}>
                <td className="rank num">{i + 1}</td>
                <td className="name">{t.name}{t.mine ? ' (me)' : ''}</td>
                <td>{t.style.replace('_', ' ')}</td>
                <td className="num">{t.wins}-{t.losses}</td>
                <Heat v={t.cat_share} mid={50} full={15} text={pct(t.cat_share)} />
                <Heat v={t.playoffs} mid={100 * 8 / res.settings.teams} full={40} text={pct(t.playoffs)} />
                <Heat v={t.titles} mid={100 / res.settings.teams} full={20} text={pct(t.titles)} />
                <td className="num">${t.spent}</td><td className="num">${t.left}</td>
                {t.per_cat.map((v, j) => <Heat key={cats[j]} v={v} mid={50} full={25} text={v.toFixed(0)} />)}
                <td className="roster">{open === t.team
                  ? <RosterList t={t} />
                  : t.roster.map((p) => `${p.name} $${p.price}`).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {res && (
        <details className="auction-log">
          <summary>Auction log ({res.log.length} sales)</summary>
          <table className="values">
            <thead><tr className="cols"><th>#</th><th>Player</th><th>Winner</th><th className="num">Price</th><th className="num">2nd bid</th><th className="num">Bidders</th><th>Nominated by</th></tr></thead>
            <tbody>
              {res.log.map((r) => (
                <tr key={r.pick}><td className="rank num">{r.pick}</td><td className="name">{r.name}</td><td>{r.winner}</td>
                  <td className="num">${r.price}</td><td className="num">${r.second}</td><td className="num">{r.bidders}</td><td>{r.nominator}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}

function RosterList({ t }: { t: RoomTeam }) {
  return (
    <table className="roster-detail">
      <thead><tr><th>Player</th><th className="num">Paid</th><th className="num">G-score $</th><th className="num">Market</th></tr></thead>
      <tbody>{t.roster.map((p) => (
        <tr key={p.player_id}><td>{p.name}</td><td className="num">${p.price}</td><td className="num">${p.gscore_dollars.toFixed(0)}</td><td className="num">${p.market_price.toFixed(0)}</td></tr>
      ))}</tbody>
    </table>
  )
}
