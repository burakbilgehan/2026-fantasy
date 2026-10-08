import { useCallback, useEffect, useState } from 'react'

// State shared by all open tabs of the site (user, 2026-10-06: draft, league and player views side by
// side). Kept in localStorage; other tabs get the `storage` event and follow. Each tab still polls the
// backend itself, so every tab stays live on its own.
function read<T>(key: string, initial: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? initial : (JSON.parse(raw) as T)
  } catch {
    return initial
  }
}

export function useSynced<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => read(key, initial))
  useEffect(() => {
    const on = (e: StorageEvent) => {
      if (e.key !== key) return
      try { setValue(e.newValue == null ? initial : (JSON.parse(e.newValue) as T)) } catch { /* keep the old value */ }
    }
    window.addEventListener('storage', on)
    return () => window.removeEventListener('storage', on)
    // `initial` is a fallback only; a new object each render must not resubscribe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  const set = useCallback((v: T) => {
    setValue(v)
    try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* private mode: this tab only */ }
  }, [key])
  return [value, set]
}
