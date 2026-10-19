import { useEffect, useState } from 'react'
import { useSynced } from './synced'
import { api, STATIC, type LiveBoard, type LiveDraftSummary } from '../api/client'

const POLL_MS = 3000
// A draft with an event in this window is followed by default. Older captures (past mocks) stay off
// until the user picks them: following one hides its sold players from the table.
const ACTIVE_MS = 30 * 60 * 1000

/** The live draft the value table follows: teams, picks and the open nomination (T-018). */
export function useLiveBoard() {
  const [drafts, setDrafts] = useState<LiveDraftSummary[]>([])
  const [choice, setChoice] = useSynced<string | null>('live-draft-choice', null) // null = automatic, '' = off
  const [room, setRoom] = useState<LiveBoard | null>(null)
  const [auto, setAuto] = useState('')

  useEffect(() => {
    const load = () => api.liveDrafts()
      .then((list) => {
        setDrafts(list)
        const now = Date.now()
        const active = list.filter((d) => d.last_event_at && now - Date.parse(d.last_event_at) < ACTIVE_MS)
        // After the draft (user, 2026-10-19): with nothing active, follow our league's finished draft, so the
        // League view keeps the teams. Mocks still need a manual pick.
        const league = list.find((d) => d.kind === 'league' && d.picks > 0)
        setAuto((active.find((d) => d.kind === 'league') ?? active[0] ?? league)?.league_id ?? '')
      })
      .catch(() => { /* no backend feed: no live mode */ })
    load()
    if (STATIC) return // the static copy is a snapshot: load once
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [])

  const leagueId = choice ?? auto

  useEffect(() => {
    if (!leagueId) return
    let alive = true
    const load = () => api.liveBoard(leagueId)
      .then((r) => { if (alive) setRoom(r) })
      .catch(() => { /* keep the last board: a failed poll must not blank the views */ })
    load()
    if (STATIC) return () => { alive = false }
    const timer = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(timer) }
  }, [leagueId])

  return { drafts, leagueId, auto: choice == null, setChoice, board: room && room.league_id === leagueId ? room : null }
}
