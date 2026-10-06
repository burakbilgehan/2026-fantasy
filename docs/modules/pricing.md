# Static price, market price, opportunity (T-025, dollar part)

Status 2026-10-06: value table columns Static price, Market price, Opportunity (code `backend/app/analytics/valuation/room.py`). Dynamic prices (dynamic worth, dynamic market price, live ranges) shelved by the user on 2026-10-06: the two references stay fixed and the user adjusts by hand during the draft. The table below keeps the old plan for the record.

## Problem (user, 2026-10-05)
Model dollars (Minus-1, plain or SAVOR) spread the budget flatter than our room pays. In our 2025-26 auction the top 24 took 49% of the budget; the model gives them 37% (SAVOR 41%). Real prices: ranks 1-2 about 86 USD, 3-6 about 68, 7-12 about 48, 13-24 about 37; ranks 97-144 go for 1 to 2.5 (verified, `draft_picks`, draft 2).
Read as fair prices, model dollars say "buy almost nobody after the top 3". In a real room that leaves you with money and nobody good to spend it on.

## Pricing mentality (user, 2026-10-05; apply to all later work: T-013, T-018, T-030)
Two views, never mixed:
- OURS: what our analysis says a player is worth. Built from our model.
- THE OTHERS: what the market and this room pay. Built from the market's own dollars, then from the room's live spending.

Names and rules:
| Name | View | At the start of a draft | During the draft |
|---|---|---|---|
| Static price | ours | our model's dollars (model and dollar method picked in the table) | fixed |
| Dynamic worth | ours | = static price | moves with the room (money and slots left, what was bought) |
| Dynamic market price | others | = market price: weighted mean of Yahoo avg cost x2, ESPN avg cost, Fantrax ADP on Yahoo's dollar scale | moves away from the market price with the room's spending |
| Opportunity | | dynamic worth - dynamic market price | live |

Example of the live rule (user): Jokic went for 90 and Wembanyama for 90, both above their market price; SGA is still at 65, so the board says "give 67".
Rules learned the hard way:
- Never turn a price into a rank and back. Two players at ranks 4 and 5 can be close or far apart in value; the price must follow the value, not the rank.
- Never make one past auction a law. Last season can at most describe how this room behaves; it is not a price table.
- At the start of a draft the market prices add up to 1,894 USD for the top 144 (2026-10-05), the room has 2,400 USD. The live board must handle that gap (inflation), not the static numbers.

## Discussion log (user, 2026-10-05)

- Two numbers per player, not one: ours and the room's. Plus an opportunity column.
- The market price is a Yahoo-weighted mix; our own evaluation tells a good price from a bad one, because the room makes mistakes.
- The room price must update live during the draft through the extension: by the course of the draft, the teams, my team's position and the money spent (T-018). The inflation formula in `draft.md` (Dynamic price range) is the starting point.
- Last season's prices do not carry over per player (a no-name of last year can be valuable now and the reverse). Update (user, 2026-10-05): no inference from one past draft at all, not even by tier. The room's behavior counts only live, during this draft.
- Where the market has no basis for a new price level, use the experts: Josh Lloyd's comments and the drafts he joins. A snake draft position still tells the price level (ADP put on the market's dollar scale, the way Fantrax ADP is).
- Part of T-025.

Superseded first attempt (2026-10-05, removed): a price-by-rank curve from the 2025-26 league auction for both numbers. The user rejected it: rank-only pricing and one past auction as a rule.

## First evidence (2026-10-05, quick test, not in code)
Best 12 for 200 USD at market prices (mean of Yahoo and ESPN average cost, min 1 USD), value = Minus-1 total above the 144th player:
Jokic 77, Reaves 24, Duren 21, Knueppel 15, Kessler 14, D. White 14, Clingan 9, Alexander-Walker 8, Dyson Daniels 7, Gobert 6, Ware 4, Queta 1 (value 76.5).
Value above replacement per market dollar: 60+ USD 0.16, 40-59 USD 0.14 (worst), 25-39 0.17, 10-24 0.27, 3-9 0.49 (best), 1-2 0.34.
Too optimistic: it assumes every player goes at his average price and that nobody else chases the same bargains.

## Build plan (static part done 2026-10-05; the rest is T-030 and T-018)
1. Done (static): market price = Yahoo avg cost x2, ESPN avg cost, Fantrax ADP on Yahoo's dollar scale; dynamic worth = static price; opportunity = the gap. Open: expert price signals where the market is thin.
2. Done (static): Static price, Dynamic worth, Dynamic market price and Opportunity columns in the value table.
3. Draft plan before the draft: the 12-player optimization above, run many times with noisy prices and with bargains bid up (how much: measured from 2025-26, how far known bargains went above their Yahoo average), so it gives core targets, backups and a "do not pay above" limit per player.
4. Live (T-018, T-013): dynamic worth and dynamic market price move after every sale with the money and slots left and with how the room paid against the market so far (example: Jokic and Wembanyama at 90 each, so SGA's market price rises).

## Open
- The weights of the price mix.
- How strong the "others chase the same bargain" effect is.
- Expert price signals: extract Lloyd's draft positions and price calls from the notes (claims.md has ADP quotes); his own mock drafts if the notes have them.
- Value: sum of z is not the same as winning H2H weeks (H-score, T-017 open item).
