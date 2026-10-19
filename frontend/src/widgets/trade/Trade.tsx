// Trade page (VISION M5, user 2026-10-19). Backend: app/api/trade.py, model: app/analytics/trade.py.
// 1. Builder: pick my players (give) and one team's players (get); the before/after overview loads at once.
// 2. Find trades: from the players already picked, plus categories to improve; best net gain on top.
// Rosters come from the public Yahoo page; "Update" refetches them (a trade may have just happened).
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { api, STATIC, type TradeBase, type TradeEval, type TradeFound, type TradePlayer, type TradeState, type ValuationQuery } from '../../api/client'
import { CAT_LABEL } from '../../lib/categories'
import { useSynced } from '../../lib/synced'

const CATS = ['fg_pct', 'ft_pct', 'tpm', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov']
const pctFmt = (v: number) => v.toFixed(3).replace(/^0\./, '.')
const fmt = (c: string, v: number, mode: 'avg' | 'total') => (c.endsWith('pct') ? pctFmt(v) : mode === 'total' ? v.toFixed(0) : v.toFixed(1))
const share = (v: number) => (v * 100).toFixed(1)
const signed = (v: number, d = 1) => `${v > 0 ? '+' : ''}${v.toFixed(d)}`
const rec = (r: number[]) => (r[2] ? `${r[0]}-${r[1]}-${r[2]}` : `${r[0]}-${r[1]}`)
const day = (iso: string) => { const [, m, d] = iso.split('-'); return `${+m}/${+d}` }
const ago = (iso: string | null) => {
  if (!iso) return 'never (draft picks)'
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  return min < 1 ? 'just now' : min < 60 ? `${min} min ago` : `${Math.round(min / 60)} h ago`
}
// Rank tint: 1 = full green, 12 = full red (same as the League tab).
const tint = (rank: number, n = 12): { cls: string; style: CSSProperties } => {
  const z = 1 - (2 * (rank - 1)) / (n - 1)
  return { cls: `heat ${z >= 0 ? 'good' : 'bad'}`, style: { '--a': Math.abs(z).toFixed(3) } as CSSProperties }
}
const ACCEPT: Record<string, string> = { likely: 'likely yes', maybe: 'maybe', hard: 'hard sell' }

function baseOf(q: ValuationQuery | null): TradeBase {
  return { kind: q?.kind ?? 'projection', source: q?.source ?? 'yahoo', season: q?.season ?? '2026-27',
    model: q?.model ?? 'gscore', dollars: q?.dollars ?? 'plain', pool: q?.pool ?? 200 }
}

export function Trade() {
  const [query] = useSynced<ValuationQuery | null>('pv-query', null)
  const base = useMemo(() => baseOf(query), [query])
  const [league, setLeague] = useState<string | null>(null)
  const [state, setState] = useState<TradeState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [give, setGive] = useState<number[]>([])
  const [get, setGet] = useState<number[]>([])
  const [partner, setPartner] = useState<number | null>(null)
  const [ev, setEv] = useState<TradeEval | null>(null)
  const [mode, setMode] = useState<'avg' | 'total'>('total')
  const [improve, setImprove] = useState<string[]>([])
  const [maxSize, setMaxSize] = useState(3)
  const [minYahoo, setMinYahoo] = useState(-4)
  const [found, setFound] = useState<TradeFound[] | null>(null)
  const [finding, setFinding] = useState(false)
  const [searchIn, setSearchIn] = useState<number | null>(null) // null = every team

  useEffect(() => {
    api.liveDrafts().then((ds) => setLeague(ds.find((d) => d.kind === 'league')?.league_id ?? null)).catch((e) => setError(String(e)))
  }, [])
  useEffect(() => {
    if (!league) return
    api.tradeState(league, base).then((s) => { setState(s); setError(null) }).catch((e) => setError(String(e)))
  }, [league, base])

  const refresh = () => {
    if (!league) return
    setBusy(true)
    api.tradeRefresh(league, base).then((s) => { setState(s); setError(null); setEv(null); setFound(null) })
      .catch((e) => setError(String(e))).finally(() => setBusy(false))
  }

  const byPk = useMemo(() => new Map(state?.teams.flatMap((t) => t.players.map((p) => [p.pk, p] as const)) ?? []), [state])
  const owner = useMemo(() => new Map(state?.teams.flatMap((t) => t.players.map((p) => [p.pk, t.team_id] as const)) ?? []), [state])
  const teamName = useCallback((id: number) => state?.teams.find((t) => t.team_id === id)?.name ?? `Team ${id}`, [state])
  const mine = state?.teams.find((t) => t.mine)
  const other = state?.teams.find((t) => t.team_id === partner)

  // Players who left a roster after an update drop out of the selection.
  useEffect(() => {
    if (!state) return
    setGive((g) => g.filter((p) => owner.get(p) === state.me))
    setGet((g) => g.filter((p) => partner != null && owner.get(p) === partner))
  }, [state, owner, partner])

  useEffect(() => {
    if (!league || partner == null || (!give.length && !get.length)) { setEv(null); return }
    let alive = true
    api.tradeEvaluate(league, { ...base, give, get, partner }).then((e) => { if (alive) { setEv(e); setError(null) } })
      .catch((e) => { if (alive) setError(String(e)) })
    return () => { alive = false }
  }, [league, base, give, get, partner])

  const toggle = (list: number[], set: (v: number[]) => void, pk: number) =>
    set(list.includes(pk) ? list.filter((x) => x !== pk) : [...list, pk])

  const findTrades = () => {
    if (!league) return
    setFinding(true)
    api.tradeFind(league, { ...base, give, get, partner: get.length ? null : searchIn, improve, max_size: maxSize, min_their_yahoo: minYahoo })
      .then((r) => { setFound(r.results); setError(null) }).catch((e) => setError(String(e))).finally(() => setFinding(false))
  }
  const load = (f: TradeFound) => { setPartner(f.partner); setGive(f.give); setGet(f.get) }
  const names = (pks: number[], extra?: Record<string, string>) => pks.map((p) => byPk.get(p)?.name ?? extra?.[p] ?? `#${p}`).join(', ')

  if (!state) return <div className="trade">{error ? <p className="error">{error}</p> : <p className="hint">Loading rosters…</p>}</div>

  return (
    <div className="trade">
      <div className="trade-bar">
        <h2>Trade</h2>
        <span className="hint">Rosters: {state.source}, updated {ago(state.fetched_at)}</span>
        {STATIC ? <span className="hint">Static snapshot: the builder and Find with picked players need the local site.</span>
          : <button onClick={refresh} disabled={busy}>{busy ? 'Updating…' : 'Update rosters'}</button>}
        <span className="hint">Base: {base.source} {base.season} · our value: {base.model} ({base.dollars}, pool {base.pool}) · change it on the Draft tab</span>
        {state.unmatched.length > 0 && <span className="error">Not in our player table: {state.unmatched.join(', ')}</span>}
      </div>
      {error && <p className="error">{error}</p>}

      <div className="trade-builder">
        <Roster title={`I give · ${mine?.name ?? ''}`} players={mine?.players ?? []} picked={give} onToggle={(pk) => toggle(give, setGive, pk)} />
        <div className="trade-mid">
          <label>Partner{' '}
            <select value={partner ?? ''} onChange={(e) => { setPartner(e.target.value ? +e.target.value : null); setGet([]) }}>
              <option value="">Pick a team…</option>
              {state.teams.filter((t) => !t.mine).map((t) => <option key={t.team_id} value={t.team_id}>{t.name}</option>)}
            </select>
          </label>
          {ev && <Deal ev={ev} names={names} />}
          <div className="trade-find">
            <h3>Find trades</h3>
            <p className="hint">Uses the players picked on either side. One player in: 1-for-1, 1-for-2. Two in: 2-for-1 up to 2-for-3.
              With players on both sides: those, plus one more player on each side. Nothing picked: the whole league, 1-1 up to 2-2
              (about 20 s).</p>
            <div className="chips">
              <span className="hint">Improve:</span>
              {CATS.map((c) => (
                <button key={c} className={improve.includes(c) ? 'chip on' : 'chip'} onClick={() => setImprove(improve.includes(c) ? improve.filter((x) => x !== c) : [...improve, c])}>{CAT_LABEL[c]}</button>
              ))}
            </div>
            <label>Search in <select value={searchIn ?? ''} disabled={get.length > 0} onChange={(e) => setSearchIn(e.target.value ? +e.target.value : null)}>
              <option value="">All teams</option>
              {state.teams.filter((t) => !t.mine).map((t) => <option key={t.team_id} value={t.team_id}>{t.name}</option>)}
            </select></label>{' '}
            <label>Max players back <select value={maxSize} onChange={(e) => setMaxSize(+e.target.value)}>{[1, 2, 3].map((n) => <option key={n}>{n}</option>)}</select></label>{' '}
            <label title="The other manager receives Yahoo value minus what he sends. 0 = he must not lose Yahoo value; -4 = he may lose up to 4; +3 = he must gain at least 3">Min Yahoo gain for them <input type="number" value={minYahoo} onChange={(e) => setMinYahoo(+e.target.value)} style={{ width: 52 }} /></label>{' '}
            <button onClick={findTrades} disabled={finding}>{finding ? 'Searching…' : 'Find'}</button>
          </div>
        </div>
        <Roster title={other ? `I get · ${other.name}` : 'I get · pick a partner'} players={other?.players ?? []} picked={get} onToggle={(pk) => toggle(get, setGet, pk)} />
      </div>

      {ev && <Overview ev={ev} mode={mode} setMode={setMode} myName={mine?.name ?? 'Me'} partnerName={teamName(ev.partner)} teamName={teamName} />}
      {found && <Found found={found} names={names} teamName={teamName} onLoad={load} />}
    </div>
  )
}

function Roster({ title, players, picked, onToggle }: { title: string; players: TradePlayer[]; picked: number[]; onToggle: (pk: number) => void }) {
  return (
    <div className="trade-roster">
      <h3>{title}</h3>
      <table className="standings">
        <thead><tr><th /><th>Player</th><th>Pos</th><th className="num" title="Yahoo auction value">Yahoo</th><th className="num" title="Our value (selected model)">Ours</th></tr></thead>
        <tbody>
          {players.map((p) => (
            <tr key={p.pk} className={picked.includes(p.pk) ? 'picked' : undefined} onClick={() => onToggle(p.pk)}>
              <td><input type="checkbox" readOnly checked={picked.includes(p.pk)} /></td>
              <td className="team" title={p.name}>{p.name}{p.status && <span className="status"> {p.status}</span>}<small className="sub">{p.team} · {p.slot}</small></td>
              <td>{p.positions?.join(',')}</td>
              <td className="num">{p.yahoo.toFixed(0)}</td>
              <td className="num">{p.ours.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Deal({ ev, names }: { ev: TradeEval; names: (pks: number[], extra?: Record<string, string>) => string }) {
  const m = ev.me, t = ev.them
  const v = ev.values
  return (
    <div className="trade-deal">
      <div className="kpis">
        <div><span className="hint">My all-play</span><b>{share(m.sim_before.allplay)} → {share(m.sim_after.allplay)}</b>
          <span className={m.sim_after.allplay >= m.sim_before.allplay ? 'good' : 'bad'}>{signed((m.sim_after.allplay - m.sim_before.allplay) * 100)}</span></div>
        <div><span className="hint">Net (vs free agent move)</span><b className={ev.net_allplay >= 0 ? 'good' : 'bad'}>{signed(ev.net_allplay * 100)}</b></div>
        <div><span className="hint">My record</span><b>{rec(m.sim_before.record)} → {rec(m.sim_after.record)}</b></div>
        <div><span className="hint">Their all-play</span><b>{signed((t.sim_after.allplay - t.sim_before.allplay) * 100)}</b></div>
        <div title="Yahoo value they receive (plus their free-agent add) minus what they send (plus the player they must drop)">
          <span className="hint">Their Yahoo +/-</span><b className={v.their_yahoo_change >= 0 ? 'good' : 'bad'}>{signed(v.their_yahoo_change, 0)}</b>
          <span className="hint">get {v.give_yahoo.toFixed(0)}{v.their_add_yahoo ? ` + FA ${v.their_add_yahoo.toFixed(0)}` : ''} · send {v.get_yahoo.toFixed(0)}{v.their_drop_yahoo ? ` + drop ${v.their_drop_yahoo.toFixed(0)}` : ''}</span></div>
        <div title="Our value I receive (plus my free-agent add) minus what I send (plus the player I must drop)">
          <span className="hint">My value +/-</span><b className={v.ours_change >= 0 ? 'good' : 'bad'}>{signed(v.ours_change, 0)}</b>
          <span className="hint">get {v.get_ours.toFixed(0)}{v.my_add_ours ? ` + FA ${v.my_add_ours.toFixed(0)}` : ''} · send {v.give_ours.toFixed(0)}{v.my_drop_ours ? ` + drop ${v.my_drop_ours.toFixed(0)}` : ''}</span></div>
        <div><span className="hint">Will they accept?</span><b className={`accept ${ev.accept}`}>{ACCEPT[ev.accept]}</b></div>
      </div>
      {(ev.my_drop.length > 0 || ev.my_add.length > 0 || ev.their_drop.length > 0 || ev.their_add.length > 0) && (
        <p className="hint">
          {ev.my_drop.length > 0 && <>I drop {names(ev.my_drop)}. </>}
          {ev.my_add.length > 0 && <>I add free agent {names(ev.my_add, ev.names)} (best by our value). </>}
          {ev.their_drop.length > 0 && <>They drop {names(ev.their_drop)} (their lowest Yahoo value). </>}
          {ev.their_add.length > 0 && <>They add free agent {names(ev.their_add, ev.names)} (best by Yahoo value). </>}
        </p>
      )}
    </div>
  )
}

function Overview({ ev, mode, setMode, myName, partnerName, teamName }: {
  ev: TradeEval; mode: 'avg' | 'total'; setMode: (m: 'avg' | 'total') => void; myName: string; partnerName: string; teamName: (id: number) => string
}) {
  const other = mode === 'avg' ? 'total' : 'avg'
  const rows: { label: string; side: 'me' | 'them'; when: 'before' | 'after' }[] = [
    { label: `${myName} · before`, side: 'me', when: 'before' }, { label: `${myName} · after`, side: 'me', when: 'after' },
    { label: `${partnerName} · before`, side: 'them', when: 'before' }, { label: `${partnerName} · after`, side: 'them', when: 'after' },
  ]
  const fb = new Map(ev.fixture_before.map((w) => [w.week, w]))
  return (
    <div className="trade-overview">
      <h3>Categories <span className="hint">· {mode === 'avg' ? 'per game (season total below)' : 'season total (per game below)'}, color = league rank</span>
        <span className="segmented small">
          <button className={mode === 'avg' ? 'on' : undefined} onClick={() => setMode('avg')}>Per game</button>
          <button className={mode === 'total' ? 'on' : undefined} onClick={() => setMode('total')}>Season total</button>
        </span>
      </h3>
      <table className="standings">
        <thead><tr><th>Team</th>{CATS.map((c) => <th key={c} className="num">{CAT_LABEL[c]}</th>)}<th className="num" title="All-play category win share in the season sim">All-play</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const s = ev[r.side]
            const line = s[mode][r.when], line2 = s[other][r.when]
            const rk = s[mode][r.when === 'before' ? 'rank_before' : 'rank_after']
            const sim = r.when === 'before' ? s.sim_before : s.sim_after
            return (
              <tr key={r.label} className={r.side === 'me' ? 'mine' : undefined}>
                <td className="team" title={r.label}>{r.label}</td>
                {CATS.map((c) => {
                  const h = tint(rk[c])
                  return (
                    <td key={c} className={`${h.cls} num`} title={`rank ${rk[c]} of 12 · all-play ${share(sim.cats[c])}%`}>
                      <span style={h.style}>{fmt(c, line[c], mode)}{!c.endsWith('pct') && <small className="sub">{fmt(c, line2[c], other)}</small>}</span>
                    </td>
                  )
                })}
                <td className="num">{share(sim.allplay)}</td>
              </tr>
            )
          })}
          <tr className="mine">
            <td className="team">My all-play win % change</td>
            {CATS.map((c) => {
              const d = (ev.me.sim_after.cats[c] - ev.me.sim_before.cats[c]) * 100
              return <td key={c} className={`num ${d > 0.05 ? 'good' : d < -0.05 ? 'bad' : ''}`}>{signed(d)}</td>
            })}
            <td className="num">{signed((ev.me.sim_after.allplay - ev.me.sim_before.allplay) * 100)}</td>
          </tr>
        </tbody>
      </table>

      <h3>My schedule <span className="hint">· season sim, Yahoo weeks · score before → after</span></h3>
      <table className="standings">
        <thead><tr><th className="num">Wk</th><th>Dates</th><th>Opponent</th><th className="num">Before</th><th className="num">After</th>
          <th className="num" title="Starter games used: me - opponent (after)">Games</th>{CATS.map((c) => <th key={c} className="num">{CAT_LABEL[c]}</th>)}</tr></thead>
        <tbody>
          {ev.fixture_after.map((w) => {
            const b = fb.get(w.week)
            if (!w.score || !b?.score) {
              return <tr key={w.week}><td className="num">{w.week}</td><td>{day(w.first)}-{day(w.last)}</td><td className="hint">playoffs</td><td /><td /><td className="num">{w.used.toFixed(1)}</td>{CATS.map((c) => <td key={c} />)}</tr>
            }
            const tone = (s: number[]) => (s[0] > s[1] ? 'good' : s[0] < s[1] ? 'bad' : '')
            return (
              <tr key={w.week} className={rec(b.score) !== rec(w.score) ? 'changed' : undefined}>
                <td className="num">{w.week}</td><td>{day(w.first)}-{day(w.last)}</td>
                <td className="team">{teamName(w.opponent!)}</td>
                <td className={`num ${tone(b.score)}`}>{rec(b.score)}</td>
                <td className={`num ${tone(w.score)}`}>{rec(w.score)}</td>
                <td className="num">{w.used.toFixed(1)}-{w.opp_used?.toFixed(1)}</td>
                {(w.cats ?? []).map((x, i) => {
                  const was = b.cats?.[i]
                  return <td key={i} className={`num ${x > 0 ? 'good' : x < 0 ? 'bad' : ''}`}>{x > 0 ? 'W' : x < 0 ? 'L' : 'T'}{was !== x && <small className="flip">*</small>}</td>
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="hint">* = the category result changed with the trade. Model: expected lines day by day (availability GP/82 x per-game line), best 10 starters by position. No waivers, IL moves or game noise.</p>
    </div>
  )
}

function Found({ found, names, teamName, onLoad }: { found: TradeFound[]; names: (pks: number[], extra?: Record<string, string>) => string; teamName: (id: number) => string; onLoad: (f: TradeFound) => void }) {
  if (!found.length) return <p className="hint">No trade found with these rules. Lower "Their Yahoo change" or pick fewer categories.</p>
  return (
    <div className="trade-found">
      <h3>Found trades <span className="hint">· {found.length} trades · best net all-play gain on top (net = minus the free-agent move I could make alone) · click a row to load it</span></h3>
      <div className="found-scroll">
      <table className="standings">
        <thead><tr><th className="num">#</th><th>I give</th><th>I get</th><th>Partner</th><th className="num">Net</th><th className="num">Record</th>
          <th>Accept</th><th className="num" title="Yahoo value they receive minus Yahoo value they send. Plus = they win on Yahoo numbers">Their Yahoo +/-</th><th className="num" title="Their all-play change in our season sim (their real team fit)">Their sim +/-</th>
          <th className="num" title="Our value (selected model) I receive minus what I send">Our value +/-</th><th>Biggest category gains</th></tr></thead>
        <tbody>
          {found.map((f, i) => {
            const top = Object.entries(f.cat_gain).sort((a, b) => b[1] - a[1]).filter(([, v]) => v > 0.005).slice(0, 3)
            const worst = Object.entries(f.cat_gain).sort((a, b) => a[1] - b[1]).filter(([, v]) => v < -0.005).slice(0, 2)
            return (
              <tr key={i} onClick={() => onLoad(f)} className="clickable">
                <td className="num">{i + 1}</td>
                <td>{names(f.give)}</td>
                <td>{names(f.get)}{f.my_drop.length > 0 && <small className="sub">drop {names(f.my_drop)}</small>}{f.my_add.length > 0 && <small className="sub">+ free agent {names(f.my_add, f.names)}</small>}</td>
                <td className="team">{teamName(f.partner)}</td>
                <td className={`num ${f.net_allplay >= 0 ? 'good' : 'bad'}`}>{signed(f.net_allplay * 100)}</td>
                <td className="num">{rec(f.record_after)}</td>
                <td className={`accept ${f.accept}`}>{ACCEPT[f.accept]}</td>
                <td className="num">{signed(f.their_yahoo_gain, 0)}</td>
                <td className="num">{signed(f.their_sim_gain * 100)}</td>
                <td className="num">{signed(f.ours_gain, 0)}</td>
                <td>
                  {top.map(([c, v]) => <span key={c} className="chip good">{CAT_LABEL[c]} {signed(v * 100)}</span>)}
                  {worst.map(([c, v]) => <span key={c} className="chip bad">{CAT_LABEL[c]} {signed(v * 100)}</span>)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
    </div>
  )
}
