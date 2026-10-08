# Season guide spec (writers read this first)

The user is sick and listens to this guide as a podcast while working. Each episode = one HTML page + one narration text file that is turned into Turkish audio. Depth matters: real analysis, not 2-3 sentence summaries.

## The league (read `docs/RULES.md`)
Yahoo, 12 teams, H2H 9-cat (FG%, FT%, 3PM, PTS, REB, AST, ST, BLK, TO), live auction, 200 USD each, 12 drafted per team, 144 players drafted. Draft: Sunday 2026-10-18. Playoffs weeks 19-21 (ends 2027-03-28). FAB waivers, max 6 adds per week. Trades very frequent, managers experienced.

## The user's core concern (mandatory frame)
Yahoo and ESPN values and average costs mix points-league and category-league value. Some players look like 20 USD because they shine in points leagues; in our 9-cat league they are 10-12 USD players. The reverse also exists: category players the market underprices. Every player discussion must say which way the market number is bent and why. Never treat the Yahoo/ESPN number as the truth.

## Data: `docs/guide/_data/players.json` (verified, built 2026-10-07 from our backend)
One row per player (232 rows). Fields:
- `our_price_minus1`, `cats_rank_minus1`: OUR price. Own projection, Minus-1 model (sum of 9-cat z without the player's own worst category), plain dollars over 144 drafted. This is "bizim fiyat".
- `our_price_zscore`, `cats_rank_zscore`: same projection, full 9-cat z-score (no category dropped). Large gap to minus1 = the player has one very bad category (punt candidate).
- `floor_price_z`, `ceiling_price_z`: z-score dollars on our floor / ceiling projection. Each is priced against its own pool, so floor can exceed ceiling. Use only as a rough spread signal, never as a price.
- `market_price`, `market_rank`: THE OTHERS. Weighted mix: Yahoo avg cost x2, ESPN avg cost, Fantrax ADP on Yahoo's scale. Also raw `yahoo_avg_cost`, `espn_avg_cost`, `fantrax_adp`.
- `points_rank_yahoo`, `points_rank_espn`, `points_rank_avg`: our projection scored with default points formulas (assumed weights: Yahoo PTS 1, REB 1.2, AST 1.5, STL 3, BLK 3, TO -1; ESPN FGM 2, FGA -1, FTM 1, FTA -1, 3PM 1, REB 1, AST 2, STL 4, BLK 4, TO -2, PTS 1).
- `format_gap` = cats_rank_minus1 - points_rank_avg. Positive and large (+20 or more) = points-league inflated: the market likely overpays in our league. Negative and large (-20 or more) = category player the market underrates.
- `format_gap_zscore` = cats_rank_zscore - points_rank_avg. Minus-1 drops each player's worst category, so for high-turnover players (Cade, Trae Young) it hides the points inflation. Check both gaps; when TO is the worst category, the zscore gap is the honest one.
- Per-game projection: gp, mpg, fg_pct, fga, ft_pct, fta, tpm, pts, reb, ast, stl, blk, tov. `z`: per-category z (full pool) for the 9 cats; `tov` z is already signed so negative = bad.
- `profile`: path to the expert profile (`docs/knowledge/profiles/players/<slug>.md`), or null.

### Reading prices correctly (important)
- Our dollar scale is flatter than the room's. Our top-144 prices sum to 2,400 USD; market prices for the top 144 sum to only 1,888 USD. So market prices are inflated about 27% in a real room on average, and stars go higher than our model says (in this league in 2025-26, ranks 1-2 went for about 86 USD). Do NOT say "star X is overpriced" only because our price < market price. Compare ranks and the format gap, then read the expert verdict.
- Own-model outliers are not verdicts. Examples: Dyson Daniels (ours ~30, market 6), Queta (20 vs 1), Cason Wallace (15 vs 1), McDaniels (17 vs 2), Kel'el Ware (24 vs 4). Some are real buys that experts also name, some are projection artifacts. Rule: a buy/avoid chip only when two of the three (our model, market+format gap, expert profile) agree, or you explain the disagreement in one sentence. A single-source outlier gets "model says X, because Y; experts say Z".
- Giannis: minus1 likes him (41 USD) because it drops his FT%; full z-score hates him (20). He is a punt-FT% build anchor. Explain such cases in those terms.
- Never price by rank. Never use the 2025-26 auction as a price law (user rule).

## Sources to read (cite them)
- `docs/knowledge/profiles/players/*.md`: per-player expert notes (Josh Lloyd, Locked On Fantasy Basketball / Basketball Monster) with dated facts and verdicts and USD caps.
- `docs/knowledge/profiles/teams/<TEAM>.md`: depth chart, win total, back-to-backs, playoff-week games (weeks 19-21), expert notes.
- `docs/knowledge/articles/*.md`: synthesized topics (auction-tactics, format-mispriced-players, breakout-candidates, bust-candidates, late-round-flyers, punt-*-targets, injury-risk-list, minutes-battles, players-on-new-teams, rookie-list, playoff-schedule-player-list, etc.).
- `docs/knowledge/methods.md` (rules and methods), `docs/knowledge/claims.md` (claims to check).
- This is a 2026-27 world: rosters changed (example: Luka on LAL, Giannis on MIA). Trust the data files for teams and roles, never your memory. Team = the `team` field (NBA.com rosters).
- Evidence labels: when a claim is from data say so ("projeksiyonumuza göre"), when from experts say so ("uzmanlar", "Josh Lloyd"), when your inference say so ("bence", "çıkarım"). Do not invent stats. Every number in the page must come from the files.

## Verdict chips (use exactly these, Turkish labels)
`<span class="chip al">AL</span>` buy: our value clearly above expected room price and at least one more source agrees.
`<span class="chip adil">ADİL</span>` fair at market.
`<span class="chip pahali">PAHALI</span>` the room will likely pay more than he is worth to us.
`<span class="chip tuzak">FORMAT TUZAĞI</span>` points-league inflated (format_gap >= +20 and market follows points).
`<span class="chip breakout">BREAKOUT</span>`, `<span class="chip flyer">FLYER</span>` (cheap upside, 1-3 USD), `<span class="chip bust">BUST RİSKİ</span>`, `<span class="chip sakat">SAKATLIK</span>`.
Score: "Hedef puanı" 1 to 5 with pips: `<span class="score">●●●○○</span>`. 5 = core target for us, 1 = let others have him.
Max bid: "En fazla $X" = the most we should pay in our room. Use whole dollars. Base it on our price, the room's inflation (stars cost more), expert caps in the profile, and the format gap. Say how you got it in one clause.

## Page format
Full HTML document, saved as `docs/guide/<NN-slug>.html`. Use this skeleton and only the classes in `docs/guide/guide.css` (read it):
```html
<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Bölüm NN · Short Name</title><link rel="stylesheet" href="guide.css"></head>
<body><main>
<header class="ep"><div class="eyebrow">Sezon Rehberi 2026-27 · Bölüm NN</div><h1>...</h1><p class="lede">...</p>
<div class="meta">Veri: kendi projeksiyonumuz (Minus-1, plain) ve piyasa fiyatı, 2026-10-07. Uzman notları: docs/knowledge.</div></header>
<section class="prose">...</section>
...
</main></body></html>
```
Tables: wrap every table in `<div class="tbl">`. Numeric cells `class="num"`. Category z cells: `z2` (z >= 1.0), `z1` (0.4..1.0), nothing (-0.4..0.4), `zn1` (-1.0..-0.4), `zn2` (<= -1.0). Price gap cells: `pos`/`neg`.
Player card:
```html
<article class="player"><div class="head"><h3>Name <span class="meta">TEAM · G,F</span></h3>
<div class="chips"><span class="chip al">AL</span></div><span class="score">●●●●○</span></div>
<div class="prices"><span>Bizim <b>$24</b></span><span>Piyasa <b>$6</b></span><span>9-cat sıra <b>16</b></span><span>Points sıra <b>40</b></span><span>Format farkı <b>-24</b></span><span>En fazla <b>$18</b></span></div>
<p>analysis...</p></article>
```
Turkish text, correct Turkish characters. Player, team and stat names stay in English. Never use the em dash character (—) anywhere; use a period, comma, colon or parentheses. No emojis.

## Narration file
Save as `docs/guide/narration/<NN-slug>.txt`. Plain text, paragraphs separated by one blank line. It is read by a Turkish TTS voice.
- It narrates the page, except purely visual parts. Do not read tables cell by cell; speak their meaning ("tablodaki en büyük fark Brunson'da").
- Spoken Turkish, warm podcast tone, second person ("sen"). Short and medium sentences. No markdown, no symbols, no chips, no brackets, no URLs, no "USD" or "$": write numbers as words where it helps the voice: "yirmi dört dolar", "on altıncı sıra", "yüzde kırk yedi". Percentages: "yüzde seksen iki". Categories spoken naturally: "serbest atış yüzdesi", "üçlük", "ribaund", "asist", "top çalma", "blok", "top kaybı", "saha içi isabet yüzdesi". Use "dokuz kategori" for 9-cat.
- Player names in normal Latin spelling as on the page (the voice handles them). Team names: use the city or nickname in English ("Boston", "Celtics").
- Start with one sentence: which episode, what it covers. End with a 3-5 sentence recap of the most important calls.
- Target length is given per episode. Turkish speech is about 130 words per minute.

## Players (who writes what) - UPDATED 2026-10-07, user correction
The user rejected starters-only coverage. Every team's whole rotation must be covered.
`players.json` now has a `scope` field: `core` (cats_rank_minus1 <= 170 or market_rank <= 150) and `rotation` (projected 10+ minutes or in the team's depth chart in profiles/teams; bad teams run 12-14 deep, every one of them counts). Division episodes (03-08) cover BOTH core and rotation players, about 60-70 per division, 11-15 per team.
- Core players: full card (top 60: 150-220 words; others: 80-140 words).
- Rotation players: a real card too (60-120 words): role and minutes, what categories he gives, when he becomes valuable (injury to whom, handcuff, streaming, punt fit, playoff schedule), whether he is a late $1 pick, a waiver/FAB watch, or ignore, and why. Chip and score still apply; max bid usually $1 or "draft etme, waiver'dan izle".
- Each team block also names the minutes battles and who gains if a starter misses games.
List episodes (09, 10) do not repeat full writeups: one line per player plus the reason, and refer to the division episode.

Divisions: Atlantic BOS BKN NYK PHI TOR; Central CHI CLE DET IND MIL; Southeast ATL CHA MIA ORL WAS; Northwest DEN MIN OKC POR UTA; Pacific GSW LAC LAL PHX SAC; Southwest DAL HOU MEM NOP SAS.

## Episodes
00 giris: season overview and how to read numbers. 01 taktik: 9-cat H2H tactics. 02 auction: auction tactics. 03 atlantic, 04 central, 05 southeast, 06 northwest, 07 pacific, 08 southwest. 09 firsatlar: breakouts, flyers, cheap values. 10 tuzaklar: busts, format traps, injury risks, plus the final cheat sheet (top targets and avoid list with max bids).

## Known model biases (found while writing 00-02)
- Minus-1 drops the worst category. For a center who shoots no threes, 3PM is always the worst (z -1.73), so Minus-1 erases his weakness and his price rises far above market (Queta 20 vs 1, Ware, Kessler, Gobert). This is partly real (punt-3PM builds) and partly a model artifact. For these bigs, quote the zscore price too and lean on the expert profile.
- Players with our price 0 but a market price (Ingram, Barrett, Nurkić, Herb Jones): outside our 144; say so, do not compute a gap.
- When an article cap and the profile cap differ, the profile (newer, dated) wins.
- Episodes 00 (giris), 01 (taktik), 02 (auction) exist; refer to them instead of re-explaining frameworks.

## CORRECTION (2026-10-07): max bid rule
Our prices already sum to the room's 2,400 USD. They are on the room's scale. Do NOT multiply our price by 1.27.
The 1.27 factor belongs to the MARKET price: market price x ~1.27 = what the room will likely pay on average (stars more, $1 players less).
Max bid ("En fazla") = our price, adjusted down by a lower dated expert cap, a large format gap or risk; adjusted up only with a clear reason stated in the card. Chip: compare our price with the expected room price (market x ~1.27).
