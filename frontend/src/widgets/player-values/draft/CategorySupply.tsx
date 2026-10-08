// Category supply (user, 2026-10-06): how much of each category is still in the undrafted pool.
// Share = positive category z of the undrafted players / the same at the start, over the valued pool
// of the model picked in the table. Marker = mean share of the categories: a bar left of it is going
// faster than the others. Color grows with the distance from the marker (no cut-off).
import type { CSSProperties } from 'react'
import type { ValuedPlayer } from '../../../api/client'
import { CAT_LABEL } from '../../../lib/categories'
import { H2H_CATS } from '../../../lib/h2h'

// A player counts as a strong source of a category from this z on.
const STRONG_Z = 1
// Distance from the marker (share points) at which the color is full.
const FULL_GAP = 0.25
// TO left out: a positive TO z means few minutes, not a skill to collect.
const CATS = H2H_CATS.filter((c) => c !== 'tov')

export function CategorySupply({ pool, sold }: { pool: ValuedPlayer[]; sold: Map<number, string> | undefined }) {
  const valued = pool.filter((p) => p.rank != null && p.z)
  const left = valued.filter((p) => !sold?.has(p.player_id))
  const pos = (xs: ValuedPlayer[], f: (p: ValuedPlayer) => number) => xs.reduce((a, p) => a + Math.max(f(p), 0), 0)
  const rows = CATS.map((c) => {
    const all = pos(valued, (p) => p.z![c])
    return {
      c, share: all ? pos(left, (p) => p.z![c]) / all : 1,
      strong: left.filter((p) => p.z![c] >= STRONG_Z).length,
      strongAll: valued.filter((p) => p.z![c] >= STRONG_Z).length,
    }
  })
  const mean = rows.reduce((a, r) => a + r.share, 0) / rows.length

  return (
    <div className="supply">
      <h3>Category supply <span className="hint">how much of each category is still undrafted</span></h3>
      <table className="supply-table">
        <thead>
          <tr>
            <th />
            <th className="hint">Left in the pool · line = average of the categories ({Math.round(mean * 100)}%)</th>
            <th className="num" title="Share of the category still undrafted">Left</th>
            <th className="num" title={`Players strong in the category (z ${STRONG_Z} or more): undrafted / at the start`}>Strong players</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, share, strong, strongAll }) => {
            const gap = share - mean
            const style = { '--a': Math.min(Math.abs(gap) / FULL_GAP, 1).toFixed(3) } as CSSProperties
            return (
              <tr key={c}>
                <th>{CAT_LABEL[c]}</th>
                <td className="bar-cell">
                  <div className={`bar ${gap < 0 ? 'scarce' : 'plenty'}`} style={style}
                    title={gap < 0 ? `Going faster than the average category by ${Math.round(-gap * 100)} points`
                      : `Going slower than the average category by ${Math.round(gap * 100)} points`}>
                    <span style={{ width: `${(share * 100).toFixed(1)}%` }} />
                    <i style={{ left: `${(mean * 100).toFixed(1)}%` }} />
                  </div>
                </td>
                <td className="num">{Math.round(share * 100)}%</td>
                <td className="num">{strong} of {strongAll} left</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
