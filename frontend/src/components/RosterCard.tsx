// Roster card (user, 2026-10-17: no comma lists of players; Yahoo-like roster screens). One card per team
// or build: a header, a strip of the 9 categories, then one row per roster slot (G G G F F F C, 3 Util,
// 2 BN, docs/RULES.md) with the player, his positions and his price. Open slots stay visible as empty rows.
import type { CSSProperties, ReactNode } from 'react'

export type CardPlayer = { id: number | string; name: string; positions: string[] | null; price: number | null; planned?: boolean }
export type CardCat = { key: string; label: string; text: string; good: boolean; a: number; title?: string }

const SLOTS = ['G', 'G', 'G', 'F', 'F', 'F', 'C', 'Util', 'Util', 'Util', 'BN', 'BN']

/** Players into the league's slots: bought players before planned ones, the least flexible first. */
function assignSlots(players: CardPlayer[]): { slot: string; player: CardPlayer | null }[] {
  const rows: { slot: string; player: CardPlayer | null }[] = SLOTS.map((slot) => ({ slot, player: null }))
  const order = [...players].sort((a, b) => Number(!!a.planned) - Number(!!b.planned)
    || (a.positions?.length ?? 9) - (b.positions?.length ?? 9))
  const extra: CardPlayer[] = []
  for (const p of order) {
    const pos = p.positions ?? []
    const r = rows.find((x) => !x.player && pos.includes(x.slot))
      ?? rows.find((x) => !x.player && x.slot === 'Util')
      ?? rows.find((x) => !x.player && x.slot === 'BN')
    if (r) r.player = p
    else extra.push(p)
  }
  return [...rows, ...extra.map((p) => ({ slot: 'BN', player: p }))]
}

export function RosterCard({ title, badge, sub, mine, cats, players, footer }: {
  title: ReactNode
  badge?: { text: string; good: boolean; a: number; title?: string }
  sub?: ReactNode
  mine?: boolean
  cats?: CardCat[]
  players: CardPlayer[]
  footer?: ReactNode
}) {
  return (
    <article className={mine ? 'rcard mine' : 'rcard'}>
      <header>
        <div>
          <h4>{title}</h4>
          {sub && <div className="hint">{sub}</div>}
        </div>
        {badge && <span className={`rbadge ${badge.good ? 'good' : 'bad'}`} title={badge.title}
          style={{ '--a': badge.a.toFixed(3) } as CSSProperties}>{badge.text}</span>}
      </header>
      {cats && (
        <div className="rcats">
          {cats.map((c) => (
            <div key={c.key} className={`rcat ${c.good ? 'good' : 'bad'}`} title={c.title} style={{ '--a': c.a.toFixed(3) } as CSSProperties}>
              <small>{c.label}</small><span>{c.text}</span>
            </div>
          ))}
        </div>
      )}
      <table className="rslots">
        <tbody>
          {assignSlots(players).map(({ slot, player }, i) => (
            <tr key={i} className={player?.planned ? 'planned' : player ? undefined : 'open'}>
              <td className="slot">{slot}</td>
              <td className="pname">{player ? player.name : <span className="hint">open</span>}</td>
              <td className="ppos">{player?.positions?.join(',') ?? ''}</td>
              <td className="num">{player?.price != null ? `$${player.price}` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {footer && <footer className="hint">{footer}</footer>}
    </article>
  )
}
