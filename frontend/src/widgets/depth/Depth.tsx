// Depth tab (user, 2026-10-17): every team's depth chart with projected minutes from all sources, to see
// starters, rotations and where our own projection's minutes differ from the others.
// Depth chart: ESPN (RotoWire data), refreshed every 6 hours. Starter research: docs/research/.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type LeagueDepth, type LeagueDepthPlayer } from '../../api/client'
import { PlayerDrawer } from '../../components/PlayerDrawer'
import { ListMarks } from '../../lib/playerLists'
import { useSynced } from '../../lib/synced'

// Minutes gap (own projection vs the mean of ESPN and FantasyPros) that marks a row.
const GAP = 5
const one = (v: number | null | undefined) => (v == null ? '-' : v.toFixed(0))

function others(p: LeagueDepthPlayer): number | null {
  // ESPN and FantasyPros only: DARKO's minutes are a July snapshot (T-028 note), too old to judge ours.
  const xs = [p.minutes.espn, p.minutes.fantasypros].filter((x): x is number => x != null && x > 3)
  // Both: one source alone is too noisy to call our number wrong.
  return xs.length >= 2 ? xs.reduce((a, b) => a + b, 0) / xs.length : null
}

/** Why a row needs a look: own minutes far from the other sources, or a starter / bench mismatch. */
function flag(p: LeagueDepthPlayer): string | null {
  const own = p.minutes.own
  if (own == null) return null
  const starter = !!p.starter_slot || p.research?.status === 'confirmed' || p.research?.status === 'very_likely'
  if (starter && own < 22 && !p.injury) return `Starter, but we project ${own.toFixed(0)} min`
  if (!starter && own >= 28 && !p.injury) return `Bench in the depth chart, but we project ${own.toFixed(0)} min`
  const o = others(p)
  if (o != null && Math.abs(own - o) >= GAP) return `Own ${own.toFixed(0)} vs others ${o.toFixed(0)} min`
  return null
}

const BADGE: Record<string, [string, string]> = {
  confirmed: ['S', 'Starter, confirmed (coach or team)'],
  very_likely: ['s', 'Starter, very likely'],
  disputed: ['?', 'Starter spot disputed'],
}

function Row({ p, onOpen }: { p: LeagueDepthPlayer; onOpen: (id: number) => void }) {
  const f = flag(p)
  const r = p.research
  return (
    <tr className={[p.starter_slot ? 'dstart' : undefined, p.injury === 'Out' ? 'dout' : undefined].filter(Boolean).join(' ') || undefined}>
      <td className="dslot" title={`Depth chart: ${p.slots.join(', ')}`}>{p.starter_slot ?? p.slots[0]}</td>
      <td className="dname">
        {p.player_id ? <button className="link" onClick={() => onOpen(p.player_id!)}>{p.name}</button> : p.name}
        {p.player_id && <ListMarks pk={p.player_id} />}
        {r && <a className={`dbadge ${r.status}`} href={r.source_url ?? undefined} target="_blank" rel="noreferrer"
          title={`${BADGE[r.status][1]}${r.role_up ? '. Role up: bench last season' : ''}. ${r.evidence} (${r.source_date})`}>
          {BADGE[r.status][0]}{r.role_up ? '↑' : ''}</a>}
        {p.injury && <span className="injury" title="ESPN injury status">{p.injury === 'Day-To-Day' ? 'DTD' : p.injury}</span>}
      </td>
      <td className={f ? 'num dflag' : 'num'} title={f ?? undefined}><strong>{one(p.minutes.own)}</strong></td>
      <td className="num">{one(p.minutes.espn)}</td>
      <td className="num">{one(p.minutes.darko)}</td>
      <td className="num">{one(p.minutes.fantasypros)}</td>
      <td className="num dlast" title={p.last.gp != null ? `${p.last.season}: ${p.last.gp} games` : 'No games last season'}>
        {one(p.last.mpg)}{p.last.gp != null && <small> ({p.last.gp})</small>}</td>
    </tr>
  )
}

export function Depth() {
  const [data, setData] = useState<LeagueDepth | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [team, setTeam] = useSynced<string>('depth-team', '')
  const [all, setAll] = useState(false)
  const [onlyFlags, setOnlyFlags] = useState(false)
  const [drawer, setDrawer] = useState<number | null>(null)
  const closeDrawer = useCallback(() => setDrawer(null), [])

  useEffect(() => { api.depth().then(setData).catch((e: Error) => setError(e.message)) }, [])

  const teams = useMemo(() => (data?.teams ?? []).filter((t) => !team || t.team === team), [data, team])
  if (!data) return <p className={error ? 'error' : 'hint'}>{error ?? 'Loading depth charts...'}</p>
  const flagged = data.teams.reduce((n, t) => n + t.players.filter((p) => flag(p)).length, 0)

  return (
    <div className="depth-page">
      <div className="controls">
        <label>Team
          <select value={team} onChange={(e) => setTeam(e.target.value)}>
            <option value="">All teams</option>
            {data.teams.map((t) => <option key={t.team} value={t.team}>{t.team}</option>)}
          </select>
        </label>
        <label className="toggle"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />Deep bench too</label>
        <label className="toggle"><input type="checkbox" checked={onlyFlags} onChange={(e) => setOnlyFlags(e.target.checked)} />Only rows to check ({flagged})</label>
      </div>
      <p className="hint">
        Depth chart: {data.source === 'espn_depth' ? 'ESPN (RotoWire)' : 'Hashtag'}, {data.fetched_at?.replace('T', ' ').slice(0, 16)}.
        Minutes per game: <strong>Own</strong> = our projection; ESPN, DARKO, FantasyPros; Last = {data.teams[0]?.players[0]?.last.season} real (games).
        Badges from the starter research of {data.research_date ?? '-'}: S confirmed, s very likely, ? disputed, ↑ bench last season. Click a badge for the source.
        A colored Own cell needs a look (hover for why).
      </p>
      <div className="depth-grid">
        {teams.map((t) => {
          const rows = t.players.filter((p) => (all || p.starter_slot || p.research || (p.minutes.own ?? 0) >= 12)
            && (!onlyFlags || flag(p)))
          if (onlyFlags && !rows.length) return null
          return (
            <section key={t.team} className="depth-team">
              <h3>{t.team}</h3>
              <table className="depth-table">
                <thead><tr><th>Pos</th><th>Player</th><th className="num" title="Our projection">Own</th><th className="num">ESPN</th>
                  <th className="num" title="DARKO, July snapshot">DARKO</th><th className="num" title="FantasyPros">FP</th><th className="num">Last</th></tr></thead>
                <tbody>{rows.map((p) => <Row key={p.player_id ?? p.name} p={p} onOpen={setDrawer} />)}</tbody>
              </table>
              {t.disputed.length > 0 && (
                <details className="depth-notes">
                  <summary>{t.disputed.length} disputed spot{t.disputed.length > 1 ? 's' : ''}</summary>
                  <ul>{t.disputed.map((d) => <li key={d.spot}><strong>{d.spot}</strong>: {d.lean}
                    {d.source_url && <> <a href={d.source_url} target="_blank" rel="noreferrer">({d.source_date})</a></>}</li>)}</ul>
                  {t.rotation && <p className="hint">{t.rotation}</p>}
                </details>
              )}
            </section>
          )
        })}
      </div>
      {drawer != null && <PlayerDrawer playerId={drawer} onClose={closeDrawer} onOpenPlayer={setDrawer} />}
    </div>
  )
}
