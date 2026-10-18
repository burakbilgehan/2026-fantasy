// Draft signals next to the category supply (user, 2026-10-18): money pressure. The price curve has its own full-width row.
// "Who can outbid me" and "position need" were tried and dropped (user: visible elsewhere already). Nothing here moves a price (prices stay fixed during a draft, user 2026-10-06); they help the user
// adjust by hand.
import type { ValuedPlayer } from '../../../api/client'
import type { DraftTeam } from './model'

// Money pressure ratio bands. Assumed: within 10% of 1 counts as balanced.
const PRESSURE_BAND = 0.1

/** Unsold players with our price, best first: the ones the room is still expected to buy. */
function unsoldByPrice(pool: ValuedPlayer[], sold: Map<number, string> | undefined): ValuedPlayer[] {
  return pool.filter((p) => p.dollars != null && !sold?.has(p.player_id)).sort((a, b) => b.dollars! - a.dollars!)
}

// Money pressure: money left in the room / our static price of the best unsold players for the open slots.
// Above 1: more money than value left, late players will cost more than our price. Below 1: bargains later.
function MoneyPressure({ teams, left }: { teams: DraftTeam[]; left: ValuedPlayer[] }) {
  const money = teams.reduce((a, t) => a + t.money_left, 0)
  const slots = teams.reduce((a, t) => a + t.open_slots, 0)
  const value = left.slice(0, slots).reduce((a, p) => a + p.dollars!, 0)
  const ratio = value > 0 ? money / value : null
  const tone = ratio == null ? '' : ratio > 1 + PRESSURE_BAND ? 'bad' : ratio < 1 - PRESSURE_BAND ? 'good' : ''
  return (
    <section className="signal">
      <h4>Money pressure</h4>
      <div className={`signal-big ${tone}`}>{ratio == null ? '-' : `${ratio.toFixed(2)}x`}</div>
      <p className="hint">${money} left in the room for {slots} open slots. Our price of the best {Math.min(slots, left.length)} unsold: ${Math.round(value)}.</p>
      <p className="hint">{ratio == null ? 'No open slots.'
        : ratio > 1 + PRESSURE_BAND ? 'More money than value left: later players will cost more than our price.'
          : ratio < 1 - PRESSURE_BAND ? 'Less money than value left: wait, bargains come later.'
            : 'Money and value are balanced.'}</p>
    </section>
  )
}

export function DraftSignals({ teams, pool, sold }: { teams: DraftTeam[]; pool: ValuedPlayer[]; sold: Map<number, string> | undefined }) {
  const left = unsoldByPrice(pool, sold)
  return (
    <>
      <MoneyPressure teams={teams} left={left} />
    </>
  )
}
