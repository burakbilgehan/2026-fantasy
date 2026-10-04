import { useEffect, useState } from 'react'
import { api, type LiveDraft, type LiveDraftSummary } from '../../api/client'

const POLL_MS = 3000
// The server sends `C|` every 6 s during a draft. Longer silence = feed is down or draft is idle.
const STALE_S = 15

export function DraftFeed() {
  const [drafts, setDrafts] = useState<LiveDraftSummary[]>([])
  const [leagueId, setLeagueId] = useState<string | null>(null)
  const [draft, setDraft] = useState<LiveDraft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [userPicked, setUserPicked] = useState(false)

  // The list is polled too: the league folder appears only when the user opens the draft room.
  useEffect(() => {
    const load = () =>
      api.liveDrafts()
        .then((list) => {
          setDrafts(list)
          if (!userPicked) {
            const first = list.find((d) => d.kind === 'league') ?? list[0]
            setLeagueId(first?.league_id ?? null)
          }
        })
        .catch((e: Error) => setError(e.message))
    load()
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [userPicked])

  useEffect(() => {
    if (!leagueId) return
    let alive = true
    const load = () =>
      api.liveDraft(leagueId)
        .then((d) => { if (alive) { setDraft(d); setError(null) } })
        .catch((e: Error) => { if (alive) setError(e.message) })
    load()
    const timer = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(timer) }
  }, [leagueId])

  if (!drafts.length) return <p>{error ?? 'No draft capture yet. Open the Yahoo draft room with the extension on.'}</p>

  const name = (id: number | null | undefined) =>
    id == null ? '?' : draft?.teams.find((t) => t.team_id === id)?.name ?? `Team ${id}`
  const age = draft?.last_event_at
    ? Math.round((Date.parse(draft.server_time) - Date.parse(draft.last_event_at)) / 1000)
    : null
  const n = draft?.nomination

  return (
    <div>
      <select value={leagueId ?? ''} onChange={(e) => { setUserPicked(true); setLeagueId(e.target.value) }}>
        {drafts.map((d) => (
          <option key={d.league_id} value={d.league_id}>
            {d.league_id} ({d.kind}, {d.picks} picks)
          </option>
        ))}
      </select>
      {error && <p className="error">{error}</p>}
      {draft && (
        <>
          <p className={age != null && age <= STALE_S ? 'live' : 'stale'}>
            Last event: {age == null ? 'none' : `${age} s ago`}
            {draft.warnings.length > 0 && ` · ${draft.warnings.length} warnings`}
          </p>
          <dl>
            <dt>On the clock</dt>
            <dd>{draft.on_the_clock ? `${name(draft.on_the_clock.team_id)} (pick ${draft.on_the_clock.pick_no})` : '-'}</dd>
            <dt>Nominated</dt>
            <dd>
              {n
                ? `${n.player_name ?? n.player_id}: $${n.high_bid} by ${name(n.high_team_id)} (${n.bids.length} bids)`
                : '-'}
            </dd>
          </dl>
          <table>
            <thead>
              <tr><th>Team</th><th>$ left</th><th>Players</th><th></th></tr>
            </thead>
            <tbody>
              {draft.teams.map((t) => (
                <tr key={t.team_id} className={t.team_id === draft.my_team_id ? 'mine' : undefined}>
                  <td>{t.name ?? `Team ${t.team_id}`}</td>
                  <td>{t.money_left}</td>
                  <td>{t.players}</td>
                  <td>{t.autopick ? 'auto' : t.online ? '' : 'away'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Picks ({draft.picks.length})</h3>
          <ol reversed className="picks">
            {[...draft.picks].reverse().map((p) => (
              <li key={p.pick_no} value={p.pick_no}>
                {p.player_name ?? p.player_id}, ${p.price}, {name(p.team_id)}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
