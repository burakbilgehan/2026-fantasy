# Live draft board: prices and signals (T-018, T-013)

Status 2026-10-06: live prices and ranges SHELVED by the user ("this part is not working out"): the table keeps the market price and our static price as references; the user adjusts by hand. Live in the value table: sold players faded with price and buyer, "Only unsold", my max bid. Next: the draft panel (T-018). T-018 (live draft board) is the large task; T-013 (live price ranges and market tracking) is a part of it. Neither closes until the work is mature.

## Rules from the user (2026-10-05)
- No inference from one past draft. Last season's auction does not set bands, multipliers or prices. The room's own facts count only live, during this draft: its money, its inflation, the stats left in the pool, the teams' H2H standing.
- The board gives ranges, not verdicts. No "buy", "too expensive", "bargain" messages and no fixed percent rules (example: "10% under fair is good"). The user reads the range and decides.
- No fine-tuned thresholds. A 2 USD player does not move by 10%. Some 20 USD players are fine at 28, others are a rip-off at 23. The range must come from the player's situation, not one rule for all.
- Keep the signal list open. The user's examples are examples, not the scope.

## Draft panel, first version (built 2026-10-06, user layout)
Shown inside the value table widget when a live draft is followed. Desktop first.
- Top: focus panel. The nominated player (current bid and bidder), or the player the user clicked in the table (until the next nomination; "Back to nominated"). In live mode a row click selects the player; a click on the name or "Full profile" opens the drawer.
  - Numbers: our price, market price, opportunity, Yahoo and ESPN avg, rank and value, per-game line with category z color.
  - Our analysis: tags, the profile Note, "Lasting" (durable) and "Now" (current) bullets from `docs/knowledge/profiles/` (card endpoint field `summary`).
  - Fit facts for my team, no verdicts: G/F/C eligibility before and after against the starter slots, money after the buy at the current bid (or market price), per open slot, spent so far, my max bid; my H2H wins before and after; my category ranks that change; risk tags (bust, injury, load management, shutdown, trade risk).
- Middle: the value table. Sold players faded with price and buyer; "Only unsold".
- Bottom: league overview. H2H matrix (row team's view, "W-L" per pair, wins out of 99 at the right, best on top, green to red), my row and column show "now → if I buy" the focus player. Team boxes: players with price and positions, money left, open slots, max bid, G/F/C counts, and the 9-category per-game line colored by league rank.
- Team line (`frontend/src/lib/h2h.ts`, checked by `frontend/scripts/check-h2h.ts`): counting stats = the players' season totals summed / their games summed (user, 2026-10-06: an 80-game player weighs more than a 50-game one); FG% and FT% = total makes / total attempts; TO lower wins; ties count half; an empty team loses every category; all 9 categories always count.
- Decided (user, 2026-10-06): no replacement fill. A team line falls as cheaper players join; that is normal (small teams built from stars rank high early).
- API: `GET /api/draft/live/{league_id}/board`.

## Two ranges per player (two views, never mixed, `pricing.md`)
1. The room's range (THE OTHERS). Start: the market price (Yahoo x2, ESPN, Fantrax; `room.py`) as the center. During the draft it moves only with this room: money left against the market prices of the players left (inflation or deflation), and how the sales so far went against their market price. It can be a range: "the room will likely pay between A and B".
2. Our reasonable range (OURS). Center: dynamic worth (our model, moved by money and slots left). The range widens or shifts with the player's situation:
   - Up: what he gives is running out in the pool (few players left with his stats, example: rebounds and blocks), or he fits my team's needs.
   - Down: he does not fit my build (example: a FT% player when I punt FT%), or there is bust or injury risk (tags and profiles, T-022), or projection floor is far below the median.
   - The user's own limits (T-028b d) are shown as they are.

## Category scarcity: an open list of signals
No formula threshold. Signals the board can show, from two sources:
- Live pool: how much of each category is left in the undrafted pool, and how many players are left who give it in volume.
- Experts (notes and articles in `docs/knowledge/`). Examples already in the notes: points, assists and FT% are the scarcest late (C4vlgpJ62NI 30:22); assists are scarce in the middle rounds (n4KkK-OJjqA 17:11); if centers are scarce in your draft, paying the top of a center's range is fine (EGdhmUgPAWY 14:15). User example: this season the middle rounds lack rebounds and blocks, so take bigs early or expect few late.

## Open questions
- Decided (user, 2026-10-06): the room's range reacts fast to sales, with arrows. Built in v1.
- How our range gets its width: projection floor and ceiling (`own-floor`, `own-ceiling`), fit, scarcity, risk tags. Which inputs, and how much each one moves the range.

## Built v1, then shelved (2026-10-06; code removed, kept for the record)
The value table follows a live draft (extension feed, T-012). Engineering slice approved by the user; the room's reaction speed is the user's call ("fast").
- Sold players stay in the table, faded, with the price paid and the buyer in the room price cell (user, 2026-10-06). "Only unsold" hides them. The "Live draft" picker: automatic follows a draft with an event in the last 30 minutes (league first); old mock captures stay off unless picked.
- "Dyn. market price" shows the room's price, the room's range under it, and an arrow when the price moved 1 USD or more since the last sale (a short color flash too).
- Strip above the table: my max bid (my money minus 1 USD per other open slot), sold count, room money and open slots, market price of the best players left (one per open slot), max price (second highest max bid).
- Formula (`backend/app/draft/room_price.py`): center = market price x temperature; range = lowest and highest source price x temperature; everything capped at the second highest max bid. Temperature = paid / market price over this room's sales, weighted by a similar market price (log distance, width 0.5), plus one "pays the market" sale as a start. Sales of players the market prices under 2 USD do not count, and players under 2 USD do not move.
- Constants (v1, tune after the mock rehearsal, T-020): `MIN_MARKET_FOR_TEMP` 2, `CLOSENESS` 0.5, `PRIOR_SALES` 1.
- SGA test: market 69 (range 67 to 72). After Jokic and Wembanyama at 90 each (market 73 and 72): 80 (range 78 to 83).
- Assumed: mocks have the same roster size as our league (12 per team) for the max bid.
- Not moved yet: dynamic worth (ours). It waits for the decision on our range.
- Money left (user, 2026-10-06: prices must follow the money left). Tested 2026-10-06 on three mocks (2627780, 2600009, 2600536), mean error per sale in USD: market price alone 6.0 / 6.8 / 8.5; temperature 3.9 / 4.2 / 5.0; a money factor alone 5.2 / 5.3 / 5.7; temperature and money factor together 7.9 / 8.9 / 5.7. The two together count the money twice: when the room runs short, its sales already go cheap and pull the temperature down. Kept: temperature plus the max bid ceiling. Open: the user's call.
- API: `GET /api/draft/live/{league_id}/prices`. Tests: `backend/tests/test_room_price.py`.

## Removed (2026-10-05)
A first proposal used multipliers per price band taken from the 2025-26 auction and fixed rules (0.8 x worth, a capped premium, a 0.10 scarcity line). The user rejected it: one past draft is not evidence, and fixed rules do not fit players.
Fact kept: one global inflation factor for all players is wrong. In two mocks (mostly bots) it priced worse than the plain market price (mean error 8.4 and 10.5 USD per sale against 6.7 and 8.5).
