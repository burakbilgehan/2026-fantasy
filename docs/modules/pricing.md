# Room price and opportunity (T-025, dollar part)

Status: product discussion, 2026-10-05. Nothing built yet. Feeds the live draft board (T-018).

## Problem (user, 2026-10-05)
Model dollars (Minus-1, plain or SAVOR) spread the budget flatter than our room pays. In our 2025-26 auction the top 24 took 49% of the budget; the model gives them 37% (SAVOR 41%). Real prices: ranks 1-2 about 86 USD, 3-6 about 68, 7-12 about 48, 13-24 about 37; ranks 97-144 go for 1 to 2.5 (verified, `draft_picks`, draft 2).
Read as fair prices, model dollars say "buy almost nobody after the top 3". In a real room that leaves you with money and nobody good to spend it on.

## Decisions (user, 2026-10-05)
- Two numbers per player, not one: our **value** (model rank) and the **room price** (what this room will pay). Plus an **opportunity** column: value at the room's price minus the expected price.
- Room price = a Yahoo-weighted mix of market prices, but judged by our own evaluation: the room makes mistakes, and the tool must tell a good price from a bad one.
- The room price must update live during the draft through the extension: by the course of the draft, the teams, my team's position and the money spent (T-018). The inflation formula in `draft.md` (Dynamic price range) is the starting point.
- Last season's prices do not carry over per player (a no-name of last year can be valuable now and the reverse). Last season can only teach how this room behaves by tier (how much it pays for the top 24, how hard it bids on known bargains).
- Where the market has no basis for a new price level, use the experts: Josh Lloyd's comments and the drafts he joins. A snake draft position still tells the price level (ADP to price through the room's price-by-rank curve).
- Part of T-025.

## First evidence (2026-10-05, quick test, not in code)
Best 12 for 200 USD at market prices (mean of Yahoo and ESPN average cost, min 1 USD), value = Minus-1 total above the 144th player:
Jokic 77, Reaves 24, Duren 21, Knueppel 15, Kessler 14, D. White 14, Clingan 9, Alexander-Walker 8, Dyson Daniels 7, Gobert 6, Ware 4, Queta 1 (value 76.5).
Value above replacement per market dollar: 60+ USD 0.16, 40-59 USD 0.14 (worst), 25-39 0.17, 10-24 0.27, 3-9 0.49 (best), 1-2 0.34.
Too optimistic: it assumes every player goes at his average price and that nobody else chases the same bargains.

## Proposed build (needs approval)
1. Expected room price per player: Yahoo-weighted mix (Yahoo, ESPN, Fantrax ADP via the room's price-by-rank curve), tier factors from how our room paid against Yahoo in 2025-26, expert price signals where the market is thin.
2. Opportunity = room price of the player's model rank minus his expected room price.
3. Draft plan before the draft: the 12-player optimization above, run many times with noisy prices and with bargains bid up (how much: measured from 2025-26, how far known bargains went above their Yahoo average), so it gives core targets, backups and a "do not pay above" limit per player.
4. Live (T-018): the same numbers recomputed after every sale from the money and slots left.

## Open
- The weights of the price mix.
- How strong the "others chase the same bargain" effect is.
- Expert price signals: extract Lloyd's draft positions and price calls from the notes (claims.md has ADP quotes); his own mock drafts if the notes have them.
- Value: sum of z is not the same as winning H2H weeks (H-score, T-017 open item).
