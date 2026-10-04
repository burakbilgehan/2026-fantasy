import { useState } from 'react'

// NBA.com headshot CDN (hotlinked, not copied). An unknown id gives a gray silhouette.
const url = (nbaId: string) => `https://cdn.nba.com/headshots/nba/latest/260x190/${nbaId}.png`

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('')

/** Player photo; initials when there is no NBA id or the image fails. */
export function Headshot({ nbaId, name, size = 'sm' }: { nbaId: string | null; name: string; size?: 'sm' | 'lg' }) {
  const [failed, setFailed] = useState<string | null>(null)
  const show = nbaId && failed !== nbaId
  return (
    <span className={`headshot ${size}`} aria-hidden="true">
      {show ? <img src={url(nbaId)} alt="" loading="lazy" decoding="async" onError={() => setFailed(nbaId)} />
        : <span className="initials">{initials(name)}</span>}
    </span>
  )
}
