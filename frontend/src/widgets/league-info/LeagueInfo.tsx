import { useEffect, useState } from 'react'
import { api, type League } from '../../api/client'

export function LeagueInfo() {
  const [league, setLeague] = useState<League | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.league().then(setLeague).catch((e: Error) => setError(e.message))
  }, [])

  const sync = async () => {
    setBusy(true)
    setError(null)
    try {
      setLeague(await api.syncLeague())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <button onClick={sync} disabled={busy}>{busy ? 'Syncing...' : 'Sync from Yahoo'}</button>
      {error && <p className="error">{error}</p>}
      {league && (
        <>
          <h3>{league.name} <small>#{league.league_id}</small></h3>
          <dl>
            <dt>Format</dt><dd>{league.scoring_type}, {league.num_teams} teams</dd>
            <dt>Draft</dt><dd>{league.draft_type}, ${league.draft_budget}, {league.draft_time}</dd>
            <dt>Roster</dt><dd>{league.roster_positions.join(', ')}</dd>
            <dt>Categories</dt><dd>{league.stat_categories.join(', ')}</dd>
            <dt>Source</dt><dd>{league.source}, synced {new Date(league.synced_at).toLocaleString()}</dd>
          </dl>
          <ol>{league.teams.map((t) => <li key={t.team_id}>{t.name}</li>)}</ol>
        </>
      )}
    </div>
  )
}
