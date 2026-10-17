// Sim page: one simulated auction room (12 managers with different valuations) and a Monte Carlo season.
// Shows how every team was built, the auction log and who won (user, 2026-10-13). Backend: app/api/sim.py.
// Room "strong" (default): 11 good drafters with budget plans; "legacy": the first room. "Compare plans" runs
// every plan over many seeds, because one seed is noise.
import { useEffect, useState, type CSSProperties } from 'react'
import { STATIC, type RoomResult, type RoomTeam } from '../../api/client'
import { CAT_LABEL } from '../../lib/categories'

type Room = 'strong' | 'legacy'
type SimResult = RoomResult & { settings: RoomResult['settings'] & { room: Room; room_rule: string } }
type PlanScore = { plan: string; label: string; wins: number; wins_se: number; cat_share: number; cat_share_se: number
  playoffs: number; playoffs_se: number; titles: number; titles_se: number; spent: number; spent_se: number }
type CompareResult = {
  settings: { room: Room; seeds: number; seasons: number; games: number; teams: number; market_is_model: boolean; room_rule: string; elapsed_s: number }
  plans: PlanScore[]
  opponents: { name: string; style: string; wins: number; spent: number }[]
}

// The Sim endpoints are not in api/client.ts yet (room field, /compare); same contract as its request().
async function simFetch<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(path, body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : undefined)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

const PLANS = [
  { key: 'one_star', label: 'One star + the rest at value' },
  { key: 'two_stars', label: 'Two stars + cheap fill' },
  { key: 'balanced', label: 'Balanced (G-score dollars)' },
  { key: 'bargains_plus', label: 'Bargains +30%' },
  { key: 'no_stars', label: 'No stars' },
]

function pct(v: number): string { return `${v.toFixed(0)}%` }
function pm(v: number, se: number, digits = 1, unit = ''): string { return `${v.toFixed(digits)}${unit} ± ${se.toFixed(digits)}` }

function Heat({ v, mid, full, text }: { v: number; mid: number; full: number; text: string }) {
  const z = (v - mid) / full
  const a = Math.min(Math.abs(z), 1)
  return <td className={`heat ${z >= 0 ? 'good' : 'bad'} num`}><span style={{ '--a': a.toFixed(3) } as CSSProperties}>{text}</span></td>
}

export function DraftSim() {
  const [plan, setPlan] = useState('one_star')
  const [plans, setPlans] = useState(PLANS)
  const [room, setRoom] = useState<Room>('strong')
  const [seed, setSeed] = useState(1)
  const [res, setRes] = useState<SimResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [cmp, setCmp] = useState<CompareResult | null>(null)
  const [cmpBusy, setCmpBusy] = useState(false)
  const [seeds, setSeeds] = useState(20)

  const run = () => {
    setBusy(true); setError(null)
    simFetch<SimResult>('/api/sim/room', { plan, seed, seasons: 300, room })
      .then((r) => setRes(r)).catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  const compare = () => {
    setCmpBusy(true); setError(null)
    simFetch<CompareResult>('/api/sim/compare', { room, plans: plans.map((p) => p.key), seeds, seasons: 100 })
      .then((r) => setCmp(r)).catch((e: Error) => setError(e.message)).finally(() => setCmpBusy(false))
  }
  useEffect(() => {
    if (STATIC) return
    run()
    // Plans registered on the backend (PLAN_PROVIDERS) join the list with their backend label.
    simFetch<{ plans: { key: string; label: string }[] }>('/api/sim/plans')
      .then((r) => setPlans([...PLANS, ...r.plans.filter((p) => !PLANS.some((q) => q.key === p.key))]))
      .catch(() => undefined)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (STATIC) return <p className="hint">The simulation needs the backend. Not available in the static copy.</p>
  const cats = res?.categories ?? []
  const me = res?.teams.find((t) => t.mine)
  return (
    <div className="draft-sim">
      <div className="controls">
        <label>My plan
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            {plans.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </label>
        <label>Room
          <select value={room} onChange={(e) => setRoom(e.target.value as Room)}>
            <option value="strong">Strong (11 good drafters)</option>
            <option value="legacy">Legacy (first room)</option>
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
      <ComparePlans cmp={cmp} busy={cmpBusy} seeds={seeds} setSeeds={setSeeds} onRun={compare} room={room} />
      {res && me && (
        <p className="hint">
          {res.settings.room_rule} A sale goes to the highest bid at the second-highest bid plus 1. The season adds week-to-week noise from the game logs.
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

function ComparePlans({ cmp, busy, seeds, setSeeds, onRun, room }: {
  cmp: CompareResult | null; busy: boolean; seeds: number; setSeeds: (n: number) => void; onRun: () => void; room: Room
}) {
  const s = cmp?.settings
  const best = cmp ? Math.max(...cmp.plans.map((p) => p.wins)) : 0
  return (
    <details className="compare-plans">
      <summary>Compare plans (every plan, many seeds)</summary>
      <div className="controls">
        <label>Seeds <input type="number" value={seeds} min={2} max={200} onChange={(e) => setSeeds(Number(e.target.value) || 20)} /></label>
        <button onClick={onRun} disabled={busy}>{busy ? 'Running…' : `Compare in the ${room} room`}</button>
        {s && <span className="hint">
          {s.room} room, seeds 1-{s.seeds}, {s.seasons} seasons each, {s.games} regular weeks, {s.elapsed_s} s.
          Mean ± standard error over seeds. A gap smaller than about two standard errors is noise.
        </span>}
      </div>
      {cmp && (
        <table className="values">
          <thead><tr className="cols"><th>Plan</th><th className="num">Wins</th><th className="num">Cat %</th>
            <th className="num">Playoffs</th><th className="num">Title</th><th className="num">Spent</th></tr></thead>
          <tbody>
            {cmp.plans.map((p) => (
              <tr key={p.plan} className={p.wins === best ? 'mine' : undefined}>
                <td className="name" title={p.label}>{p.plan.replace('_', ' ')}</td>
                <td className="num">{pm(p.wins, p.wins_se)}</td>
                <td className="num">{pm(p.cat_share, p.cat_share_se, 1, '%')}</td>
                <td className="num">{pm(p.playoffs, p.playoffs_se, 0, '%')}</td>
                <td className="num">{pm(p.titles, p.titles_se, 1, '%')}</td>
                <td className="num">${p.spent.toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {cmp && (
        <p className="hint">
          Opponents, mean wins: {cmp.opponents.map((o) => `${o.name} (${o.style.replace('_', ' ')}) ${o.wins.toFixed(1)}`).join(', ')}.
        </p>
      )}
    </details>
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
