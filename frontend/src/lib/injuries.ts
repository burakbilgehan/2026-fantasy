// ESPN injuries (RotoWire notes), shared by the Injuries tab and the badges in the value table (user,
// 2026-10-18). Read live from the browser (CORS open), one fetch for the whole page, refreshed every 10 min.
import { useSyncExternalStore } from 'react'

const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
// Regular season start, assumed (2026-27 schedule: opening night October 20).
export const SEASON_START = new Date('2026-10-20T00:00:00Z')

export type EspnInjury = {
  team: string; name: string; status: string; date: string; short: string; long: string
  type: string | null; side: string | null; ret: string | null
}
export type Trust = { level: 'high' | 'medium' | 'low'; why: string }
type State = { rows: EspnInjury[] | null; error: string | null; fetched: Date | null; byName: Map<string, EspnInjury> }

export const normName = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z]/g, '')

let state: State = { rows: null, error: null, fetched: null, byName: new Map() }
const subs = new Set<() => void>()
let started = false

function load() {
  fetch(ESPN).then((r) => r.json()).then((d) => {
    const rows: EspnInjury[] = []
    for (const g of d.injuries ?? []) for (const i of g.injuries ?? []) {
      rows.push({ team: g.displayName, name: i.athlete?.displayName ?? '?', status: i.status, date: i.date, short: i.shortComment ?? '',
        long: i.longComment ?? '', type: i.details?.type ?? null, side: i.details?.side ?? null, ret: i.details?.returnDate ?? null })
    }
    state = { rows, error: null, fetched: new Date(), byName: new Map(rows.map((r) => [normName(r.name), r])) }
    subs.forEach((f) => f())
  }).catch((e: Error) => { state = { ...state, error: `ESPN injuries could not be read: ${e.message}` }; subs.forEach((f) => f()) })
}

function subscribe(f: () => void) {
  subs.add(f)
  if (!started) { started = true; load(); window.setInterval(load, 10 * 60 * 1000) }
  return () => { subs.delete(f) }
}

export function useInjuries(): State {
  return useSyncExternalStore(subscribe, () => state)
}

// How far to trust the time out: a stated timeline and a return date is high; "no timetable" is low.
export function trust(e: EspnInjury): Trust {
  const t = `${e.short} ${e.long}`.toLowerCase()
  if (/no timetable|without a timetable|indefinitely|unclear|uncertain|undisclosed/.test(t)) return { level: 'low', why: 'No timetable in the report' }
  const timeline = /(\d+|one|two|three|four|five|six|eight)\s*(-|to)?\s*(\d+)?\s*(weeks?|months?)|miss the (entire )?(2026-27 )?season|out for the season|season-ending|expected to (miss|return|be ready)|re-?evaluated in|cleared|full participant|full go/.test(t)
  if (timeline && e.ret) return { level: 'high', why: 'Stated timeline and a return date' }
  if (timeline) return { level: 'medium', why: 'Stated timeline, no return date' }
  if (e.ret) return { level: 'medium', why: 'Return date only (ESPN estimate)' }
  return { level: 'low', why: 'Status only' }
}

/** Weeks of the regular season missed, from ESPN's return date. */
export function weeksOut(ret: string | null): number | null {
  if (!ret) return null
  return Math.max(0, (new Date(ret).getTime() - SEASON_START.getTime()) / 86400000 / 7)
}

/** Missed or was limited in training camp / preseason, from the report text. */
export function missedCamp(e: EspnInjury): boolean {
  const t = `${e.short} ${e.long}`.toLowerCase()
  // Training camp itself, or the whole preseason; one missed exhibition game is not enough.
  return (/training camp/.test(t) && /miss|sidelined|held out|not (been )?(a )?(full )?participat|limited|sat out|has yet to|absent/.test(t))
    || /(entire|all of the|whole) preseason/.test(t)
}

export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric',
  year: new Date(s).getFullYear() !== 2026 ? 'numeric' : undefined }) : '-')

/** Badge for the value table: long and certain absences, and players who missed camp. Null = no badge. */
export function badgeOf(e: EspnInjury | undefined): { text: string; cls: string; title: string } | null {
  if (!e) return null
  const w = weeksOut(e.ret), t = trust(e), camp = missedCamp(e)
  const long = e.status === 'Out' && w != null && w >= 1 && t.level !== 'low'
  if (!long && !camp) return null
  const title = `${e.status}${e.type ? ` (${[e.side, e.type].filter(Boolean).join(' ')})` : ''} · back ${fmtDate(e.ret)}`
    + `${w != null ? ` (${w.toFixed(1)} weeks of the season)` : ''} · trust ${t.level}: ${t.why}\n\n${e.short}\n\n${e.long}\n\nESPN / RotoWire, ${fmtDate(e.date)}`
  if (long) return { text: w! >= 20 ? 'OUT season' : `OUT ${Math.round(w!)}w`, cls: 'long', title }
  return { text: 'CAMP', cls: 'camp', title }
}
