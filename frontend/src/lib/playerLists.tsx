import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useSynced } from './synced'

// Player lists (user, 2026-10-17): as many lists as the user wants, like playlists, each with its own
// symbol (flyers, first round targets, stay away). Kept in the browser (localStorage), so they also work
// in the static copy. The local site and the static copy have separate lists.
export type PlayerList = { id: string; name: string; symbol: string; players: number[] }

type Lists = {
  lists: PlayerList[]
  of: (pk: number) => PlayerList[]
  toggle: (listId: string, pk: number) => void
  add: (listId: string, pk: number) => void
  drop: (listId: string, pk: number) => void
  create: (name: string, symbol: string) => string // the new list's id
  update: (listId: string, patch: Partial<Pick<PlayerList, 'name' | 'symbol'>>) => void
  remove: (listId: string) => void
}

const ListsContext = createContext<Lists | null>(null)

export function ListsProvider({ children }: { children: ReactNode }) {
  const [lists, setLists] = useSynced<PlayerList[]>('player-lists', [])
  const value = useMemo<Lists>(() => {
    const byPlayer = new Map<number, PlayerList[]>()
    for (const l of lists) for (const pk of l.players) byPlayer.set(pk, [...(byPlayer.get(pk) ?? []), l])
    return {
      lists,
      of: (pk) => byPlayer.get(pk) ?? [],
      toggle: (listId, pk) => setLists(lists.map((l) => (l.id !== listId ? l
        : { ...l, players: l.players.includes(pk) ? l.players.filter((x) => x !== pk) : [...l.players, pk] }))),
      add: (listId, pk) => setLists(lists.map((l) => (l.id !== listId || l.players.includes(pk) ? l
        : { ...l, players: [...l.players, pk] }))),
      drop: (listId, pk) => setLists(lists.map((l) => (l.id !== listId ? l : { ...l, players: l.players.filter((x) => x !== pk) }))),
      update: (listId, patch) => setLists(lists.map((l) => (l.id !== listId ? l : { ...l, ...patch }))),
      create: (name, symbol) => {
        const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
        setLists([...lists, { id, name, symbol, players: [] }])
        return id
      },
      remove: (listId) => setLists(lists.filter((l) => l.id !== listId)),
    }
  }, [lists, setLists])
  return <ListsContext.Provider value={value}>{children}</ListsContext.Provider>
}

export function useLists(): Lists | null {
  return useContext(ListsContext)
}

/** Symbols of the lists the player is in, next to the name. */
export function ListMarks({ pk }: { pk: number }) {
  const ctx = useLists()
  const mine = ctx?.of(pk) ?? []
  if (!mine.length) return null
  return <span className="list-marks" title={mine.map((l) => `${l.symbol} ${l.name}`).join('\n')}>{mine.map((l) => l.symbol).join('')}</span>
}

export const SYMBOLS = ['🎯', '⭐', '💎', '🚀', '🔥', '🧪', '👀', '💰', '⚠️', '🚫', '💀', '🩼']
