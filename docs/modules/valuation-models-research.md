# Valuation models research, 2026-10-13 (T-017 follow-up)

Status: research. Nothing in the product changed (models, defaults, UI untouched). The user decides what moves into the tool (section 7).
Scripts and outputs (local only, not in git): `data/research/valuation-2026-10-13/`. Run with the system `python3` (numpy, scipy); they read `data/fantasy.db` directly and import the project's valuation code for the z values.
Status words: verified (I ran it or read the source), inferred, assumed.

## 1. Question
Which player valuation models deserve a place next to Minus-1, and can we build our own from the data we have: a value, a rank and auction dollars that follow weekly H2H results in a 12-team 9-cat league?

## 2. Method: an empirical H2H value from the game logs
The value of a player is measured directly as what he does to a fantasy team's weekly results. No z, no SD.

- Weekly lines: every player's box score summed per Monday-to-Sunday week, 4 seasons (2022-23 to 2025-26), regular season up to the last Sunday of March (our playoffs end there). 23 weeks per season. Injured weeks count as zero (verified: `player_game_logs`).
- Context: a base team of 11 players plus the candidate. The team's weekly 9-cat line is compared with 11 opponent teams in every week; ties count half. The candidate's score is the share of category matchups won (cat share) and the share of weekly matchups won (match share).
- Synthetic contexts: base and opponents drawn at random from the top 144 players by minutes of that season; 600 contexts per season. Every candidate is scored in every context he is not already part of. The mean over contexts is the player's empirical value, called MWV below (marginal win value). Seed-to-seed stability: Spearman 0.997 on the top 200 (verified).
- Real contexts, 2025-26 only: base = one of the 12 real draft rosters of our league minus one member (12 x 12 contexts), opponents = the other 11 real rosters. No prices are used anywhere.
- Limits (assumed): draft and hold, no waivers, no lineup cap, positions ignored, equal weight for every week, All-Star week not merged. Missed weeks count as zero, so the value punishes missed games harder than a manager who streams a replacement would (inferred). The value is hindsight (real season stats), so it measures the model function, not the projection.
- Dollars: not part of this study. The existing plain and SAVOR conversions apply to any value.

MWV cannot run on a projection base as it is: it needs weekly lines. A projection can be turned into simulated weekly lines (per-game stats x games per week from `nba_schedule`, plus week-to-week noise from the logs). That is the step that would make it a dropdown model (inferred, not built).

## 3. Results

### 3.1 Which static formula tracks the empirical value best
Every model computed on the real season totals (basis totals, pool 200, as in the product; G-score with the paper weights, which are within 0.07 of the weights the product computes from our logs, `valuation-backtest.md`). Spearman with MWV on the top 200 players by MWV. Verified.

| Model | 22-23 | 23-24 | 24-25 | 25-26 | mean | 25-26 real rosters |
|---|---|---|---|---|---|---|
| G-score (paper weights) | 0.985 | 0.980 | 0.981 | 0.977 | 0.981 | 0.956 |
| Z-score 9-cat | 0.974 | 0.971 | 0.974 | 0.968 | 0.972 | 0.948 |
| tanh-squashed z9 (s=2.5) | 0.972 | 0.970 | 0.974 | 0.966 | 0.970 | 0.946 |
| z9 with sqrt BLK, STL | 0.974 | 0.966 | 0.970 | 0.963 | 0.968 | 0.943 |
| G-score minus-1 | 0.975 | 0.969 | 0.962 | 0.961 | 0.967 | 0.944 |
| Minus-1 | 0.968 | 0.959 | 0.960 | 0.955 | 0.961 | 0.937 |
| robust z9 (median, MAD) | 0.948 | 0.956 | 0.967 | 0.960 | 0.958 | 0.939 |
| Punt TO | 0.962 | 0.956 | 0.956 | 0.955 | 0.957 | 0.941 |
| DURANT approx. (8 cat, minus-1) | 0.955 | 0.943 | 0.943 | 0.944 | 0.946 | 0.933 |
| Minus-2 | 0.950 | 0.938 | 0.933 | 0.927 | 0.937 | 0.914 |
| Punt FT% | 0.945 | 0.929 | 0.934 | 0.915 | 0.931 | 0.900 |
| Fantasy points (Yahoo) | 0.891 | 0.891 | 0.892 | 0.901 | 0.894 | 0.899 |
| percentile z9 (normal scores) | 0.890 | 0.900 | 0.895 | 0.873 | 0.890 | 0.865 |

The top three (G-score, z9, tanh z9) and the bottom four keep their order in every season and on the real rosters; the middle of the table swaps between seasons (robust z9 ranges from 0.948 to 0.967). G-score is first in every column.

### 3.2 Hindsight snake tournament
12 teams, each drafts by one model's list (real season totals), random order, 12 rounds, best available by its own list, then all-play weekly H2H. 120 draws per season. The empirical value itself plays as an oracle (its ceiling). Verified.

| Model | cat share, mean of 4 seasons | match share |
|---|---|---|
| MWV oracle (hindsight) | 0.548 | 0.615 |
| G-score | 0.524 | 0.553 |
| Z-score 9-cat | 0.518 | 0.545 |
| tanh z9 | 0.517 | 0.544 |
| robust z9 | 0.506 | 0.492 |
| G-score minus-1 | 0.505 | 0.492 |
| Minus-1 | 0.498 | 0.495 |
| Punt TO | 0.495 | 0.517 |
| DURANT v2 (section 3.6, sqrt BLK and STL) | 0.485 | 0.488 |
| DURANT approx. | 0.479 | 0.475 |
| Minus-2 | 0.473 | 0.364 |
| Fantasy points | 0.458 | 0.409 |

G-score beats z9 in three seasons and ties in 2024-25 (standard error 0.001 to 0.003). The gap between the oracle and G-score (0.024) is the room left for team-conditional and nonlinear value.

### 3.3 Preseason chain test, 2025-26 (projection error and room prices included)
ESPN 2025-26 preseason projection, plain dollars, best 12 for 200 USD at the real 2025-26 prices with bidding noise (30 draws, as in `valuation-backtest.md`), all-play against the 12 real rosters. Cat share: percentile z9 0.689, tanh z9 0.680, z9 0.646, G-score 0.631, Minus-1 0.596, DURANT approx. 0.516, fantasy points 0.465 (SD of one draw about 0.03). Verified.
Reading (inferred): the flat models win here because they compress star values, so the knapsack buys more mid-priced players, and in this one room the stars were overpaid (+14.7 USD residual in the 40+ tier, `valuation-backtest.md`). This is a pricing effect of one auction, not a value finding. By the user's rule it sets no rule.

### 3.4 Fitted category weights equal the G-score weights
OLS of MWV on the 9 category z (top 250 players, per season), scaled to mean 1. Verified.

| | FG% | FT% | 3PM | PTS | REB | AST | STL | BLK | TO |
|---|---|---|---|---|---|---|---|---|---|
| fitted, mean of 4 seasons | 0.76 | 0.81 | 1.15 | 1.14 | 1.13 | 1.19 | 0.73 | 1.08 | 1.01 |
| G-score paper weights, same scale | 0.89 | 0.92 | 1.14 | 1.03 | 1.09 | 1.19 | 0.70 | 1.08 | 0.98 |

Leave-one-season-out: fitted weights 0.978 to 0.987, G-score 0.977 to 0.985, z9 0.968 to 0.974. The fit adds nothing over G-score. The G-score theory (arXiv 2307.02188: weekly noise lowers a category's worth) holds in our data; steals are the clearest case (weight 0.7).

### 3.5 Punt builds: the weights move in several categories at once
Same fit, but the base team holds k of 11 players from the 40 worst FT%-impact players of the pool (a punt-FT core). Verified, 2025-26 (2023-24 agrees).

| k bad-FT players | FT% weeks won | FG% | FT% | 3PM | PTS | REB | AST | STL | BLK | TO | fitted rho | G-score rho | z9 rho |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.71 | 0.75 | 0.70 | 1.23 | 0.99 | 1.19 | 1.27 | 0.73 | 1.07 | 1.08 | 0.974 | 0.973 | 0.965 |
| 5 | 0.37 | 0.80 | 0.73 | 1.21 | 1.23 | 1.04 | 1.23 | 0.77 | 0.97 | 1.02 | 0.976 | 0.975 | 0.967 |
| 8 | 0.19 | 0.87 | 0.61 | 1.05 | 1.26 | 1.00 | 1.32 | 0.85 | 1.00 | 1.03 | 0.970 | 0.963 | 0.958 |
| 11 | 0.08 | 0.95 | 0.43 | 0.76 | 1.24 | 1.00 | 1.50 | 0.93 | 1.06 | 1.12 | 0.961 | 0.923 | 0.924 |

Findings:
- A real punt-FT team still keeps FT% at weight 0.4 to 0.6, because some weeks and some opponents are winnable. The "punt FT" model (FT% weight 0) is the worst static model even in these contexts (rho 0.78 at k=11).
- A punt build changes other categories too: 3PM loses weight (the bigs lose it anyway), PTS and AST gain. Minus-1 and the DURANT family do not capture this either (Minus-1 0.85, DURANT v2 0.87 at k=11).
- Up to a moderate punt (k=5) G-score is as good as a context-fitted model. For a real build the right tool is the team-conditional simulation (section 3.8), which is what the H-score literature does (section 4).

### 3.6 DURANT reconstruction from Lloyd's quoted ranks
41 "Nth in DURANT last season" quotes from `docs/knowledge/claims.md` (2025-26 season; Lloyd's "categories" ranks are his DURANT ranks, verified by the Wiggins quote that gives both). Lloyd's lists are per game with no games-played floor (Kessler, 5 games, ranked 19th). Our straight per-game z9 reproduces the "straight 9-cat" ranks he mocks (Spearman 0.89 on 11 quotes), so the calibration set is valid. Verified.

| Formula (per game, pool all) | Spearman vs 41 DURANT ranks | mean abs log rank error |
|---|---|---|
| DURANT v2: no TO, sqrt BLK and STL, minus-1 | 0.984 | 0.14 |
| current DURANT approx.: no TO, minus-1 | 0.976 | 0.19 |
| Minus-1 | 0.959 | 0.26 |
| z9 | 0.885 | 0.40 |

Key names, Lloyd's rank then DURANT v2: Antetokounmpo 9 and 7, Sengun 20 and 24, Holmgren 47 and 43, Castle 87 and 82, Okongwu 60 and 60, Ware 95 and 102, Huff 191 and 163, Pritchard 101 and 87, Brown 24 and 41, Gobert 85 and 52, Banchero 56 and 69. Remaining misses: Lloyd rates volume scorers higher and some bigs lower than v2 does. Superseded by 3.6b: his published formula does better with no guessing.

### 3.6b The published DURANT H2H formula reproduces his ranks
After 3.6 was written, the research pass found Lloyd's own article (section 4b). Implemented as published (`durant_h2h.py`: Yeo-Johnson per category with fitted lambda, standardise over all players with a game, weights PTS 1.00, REB 0.94, AST 0.75, others 0.60, no turnovers, Minus 1 on the eight, per game). Verified.

| Formula (per game) | Spearman vs 41 DURANT ranks | mean abs log rank error |
|---|---|---|
| DURANT H2H as published, all players | 0.987 | 0.14 |
| DURANT H2H as published, players with 10+ games | 0.991 | 0.13 |
| ablation: weights without the transform | 0.977 | 0.18 |
| ablation: transform without the weights | 0.983 | 0.18 |
| neither (our current DURANT approx.) | 0.976 | 0.19 |
| DURANT v2 from 3.6 (sqrt BLK and STL) | 0.984 | 0.14 |
| broad DURANT (TO 0.50, no Minus 1) | 0.870 | 0.38 |

Key names, Lloyd then ours: Antetokounmpo 9 and 10, Maxey 4 and 4, Siakam 48 and 48, Holmgren 47 and 46, Castle 87 and 89, McDaniels 84 and 86, Gobert 85 and 82, Ware 95 and 100, Huff 191 and 182, Sengun 20 and 25, Banchero 56 and 62, Brown 24 and 36, Durant 14 and 7, Curry 7 and 13. The rest of the gap is his sample and date, not the formula (inferred). This replaces DURANT v2: use the published formula.
On the totals basis the published formula tracks the average-team H2H value at 0.92 to 0.94 (z9 0.97, G-score 0.98): it is a per-game judgement view with Minus 1 built in, as he says himself ("an overall H2H value guide, rather than a ranking for one specific punt build").
Hashtag's -2 floor (each category z capped below at -2) on the totals basis: 0.951 to 0.966 vs MWV; with turnovers x0.25 (their H2H default) 0.951 to 0.969. Below plain z9 in every season. Verified.

### 3.7 Where z9 and the empirical value disagree (2025-26, top 200)
z9 rates higher than MWV: low-usage, low-turnover, steals and FG% role players (Javonte Green, Ausar Thompson, Paul Reed, Jordan Goodwin, Gary Payton II, Keon Ellis, Mitchell Robinson). MWV rates higher: scorers with turnovers and poor FG% (Westbrook, Kyshawn George, Clowney, Jerami Grant, P.J. Washington). This is Lloyd's "nine-cat fluff" seen in the data, for a non-punting team. The fix the data supports is the G-score weighting (STL 0.7, FG% 0.76, TO about 1.0), not dropping turnovers.

### 3.8 Team-conditional value on real rosters (demo)
For a real 2025-26 roster, each candidate replaces the weakest member and the roster plays the other 11 real teams. Example, team 6 (Jokić, Mobley, Okongwu, Queta, M. Williams, I. Jackson): the simulation puts Murray, Gilgeous-Alexander and Leonard (+0.072 cat share) ahead of Wembanyama (+0.052), G-score puts Wembanyama first. For teams 8 and 12 the two orders agree. The best addition is almost always the best player; fit reorders within a tier. Verified. The same code answers "what does this player do to my team" during a draft, given simulated weekly lines for the projection (section 2).

### 3.9 Prototype: the simulated value on a preseason projection
To run the simulation on a projection, each player's expected weekly line = per-game projection x availability (projected GP / 82) x his team's games in that fantasy week. Deterministic lines, no weekly noise. ESPN 2025-26 preseason projection, team and games per week taken from the 2025-26 logs (a small leak: trades and NBA Cup games; preseason the schedule and the rosters are known). Then the same chain test as 3.3. The random price draws differ from 3.3 (another iteration order), so G-score shows 0.613 here and 0.631 there: the run-to-run spread for one model is about 0.02, which is why both tables are read as feasibility, not verdict. Verified (`projsim.py`).

| Value on the projection | cat share, 30 draws | at exact real prices |
|---|---|---|
| simulated value (deterministic lines) | 0.666 | 0.671 |
| Z-score 9-cat | 0.648 | 0.633 |
| G-score | 0.613 | 0.622 |
| Minus-1 | 0.602 | 0.646 |

The simulated value ranks the projection almost like G-score (Spearman 0.980 on the top 200) but buys a better team in this one room. One season and bidding noise (SD 0.03 per draw) make this a feasibility result, not a verdict. Adding weekly noise from the logs and the 2026-27 schedule are the next steps if the user picks decision 3.

## 4. Literature and tools (web research, 2026-10-13)
From a research pass over the papers and open-source tools. Verified = the agent read the source; links given.

- H-score, arXiv 2409.09884 (Rosenof, CC BY 4.0): value of a candidate given the drafter's team and the picks left. Category win probability = normal CDF of the difference, variance = weekly noise plus the variance of the opponents' future picks; a strategy vector (category weights, flex shares) is optimized per candidate. No static variant in the paper; the tool's "empty board" H-score is its generic ranking. Evidence: in 2004-05 to 2023-24 simulations one H-score drafter against a G-score field won the league 21.8% (each category) to 37.7% (most categories) of the time against a 8.3% baseline. Games per week are not an input (stated limitation). Auction appendix: cash equivalent of the H-score against a replacement player plus cash. Verified.
- G-score, arXiv 2307.02188 v5: no new method after v4; SAVOR appears only in v4. Evidence: one G drafter in a z field wins 21.4% (each category) and 32.5% (most categories); one z drafter in a G field 0.5%. Our hindsight tournament (3.2) agrees in direction. Verified.
- Roto H-score, arXiv 2501.00933: roto only, not for us. Verified. No other 2025-2026 papers found.
- zer2 fantasy-basketball-optimizer (GitHub): draft, auction and season modes; auction prices "Gnrc. $" (board-dependent) and "Your $" (team-conditioned) with SAVOR spread 10 "sourced by vibes"; no LICENSE file, so all rights reserved: reuse the published methods (paper, CC BY 4.0), not the code. The site differs from the paper (new future-pick model, shrinkage, percentage volume scaling). Verified.
- Community code with a stated method: `hgunduzoglu/nba-fantasy` (expected category wins = sum of normal CDFs, marginal over replacement; evidence weak), `justin-gonzaga/nba-fantasy-assistant` (normal approximation equals Monte Carlo for single-category odds, Brier difference about 0; PolyForm Noncommercial). Verified by the agent, code not read by me.
- Code note for us (agent finding, inferred): `backend/app/analytics/valuation/gscore.py` sets kappa from the pool size (144) where the paper uses the roster size (12). Effect about 1% on the weights (STL 0.44 to 0.43, checked by hand). The site also scales percentage impact by volume (`N x avg_att / ((N-1) x avg_att + player_att)`), which we do not.

### 4b. Industry ranking systems (research pass, 2026-10-13)
Verified = the page was read (the DURANT article by me, in the user's Chrome; the rest by the agent). No commercial source publishes a backtest.
- Josh Lloyd, DURANT and DURANT H2H (joshlloydfantasy.com/research/durant-fantasy-basketball): the method is public. Both apply a Yeo-Johnson power transform per category (sklearn PowerTransformer, lambda fitted) on the full NBA player sample, then standardise. DURANT (roto and H2H): every category 1.00, turnovers 0.50. DURANT H2H (the rank he quotes): points 1.00, rebounds 0.94, assists 0.75, FG% impact, 3PM, blocks, steals and FT% impact 0.60, turnovers excluded, then Minus 1 on the remaining eight. Per game (his tweet: "DURANT H2H per game rankings"). The weights are his judgement ("how I want those contributions reflected", game-to-game volatility and year-to-year consistency). A "Punt+" version for specific builds is announced. Our rebuild in 3.6 is tested against this formula in 3.6b. Verified.
- Basketball Monster (help page): "Values are z-scores. 0.00 is your league average."; "Minus 1 Value: the value with the player's worst category removed"; punt values leave the category out; "LeagueV" = a player's value to the other teams and "Punt+" = the extra value he gains from your punt (members); DURANT H2H is offered to members; total, per game, per 36; "Total Value with Added Replacement Games" fills missed games with estimated free-agent output up to 82 games. Pool and percentage formula not documented (agent fit: mean of 9 z, pool about top 150 to 157, volume-weighted percentages). Verified for the quotes, inferred for the fits.
- Hashtag Basketball (user guide): H2H mode "puts a floor on how low a negative category can go (the floor is set to -2)"; Minus 1 removes the worst category; punt multipliers x0.25 to x3; the rankings page default is H2H with turnovers x0.25; per game or totals (per game x games). Giannis 2025-26 per game: Standard 56th, H2H 18th, Minus 1 8th (agent, by replaying the site's own views). Verified.
- ESPN Player Rater (2007 method article): each category scaled to its average, 0.00 at average, summed, no standard deviation, turnovers excluded, volume-aware percentages. Yahoo help: the default rank "is based on the total projected categories according to your league's scoring settings"; O-Rank and X-Rank not documented. FantasyPros: compares to the category average, summed. Fantrax score and NBA.com category formula: not documented. Verified, ESPN dated.
- RotoWire auction values (2014, 2025): value above waiver-wire players in SD units; dollars = share of league dollars, recomputed during the auction; the 2014 H2H version used only the six positive counting stats. NBC 2014: per-game z with a pool of players over 30 games and 20 minutes (216 players). Verified, dated.
- Ideas worth copying (agent list, my view in brackets): Yeo-Johnson plus weights (tested in 3.6b); Hashtag's -2 floor instead of deleting a category (tested in 3.6b); replacement-games fill for missed games (a projection-side idea for T-025, not a value model); LeagueV and Punt+ (matches our OURS versus THE OTHERS split); down-weighting turnovers instead of dropping them (Hashtag x0.25, DURANT 0.50, BM 2022 article).

### 4c. Community methods and auction dollar conversions (research pass, 2026-10-13)
Verified = the agent read the page or file. Only methods with a stated computation.
- sconies/fantasy-auction (GitHub): a simplified G-score, z = (x - m) / sqrt(sd^2 + tau) with tau the mean within-player variance of weekly rates, plus a weekly replay harness (one team drafts by the formula, 13 by plain z, real weeks). Result: 61 to 66% of weeks won against plain z in 2023-24 to 2025-26; capping z at 2 or 3 changed nothing (47 to 55%). Independent agreement with our 3.1, 3.2 and with the tanh result. Also: VORP dollars with the replacement at the mean of ranks n+1 to n+6 and a GP factor (z_pg - r_pg) x GP / 80; a knapsack bid limit on a room price curve (the largest price p at which buying the player still beats the best roster without him, exact DP). The bid limit is a candidate for T-030's "do not pay above", built from market prices, so a third labelled number, never OURS.
- rjskene/pickandroll and TylerGrossi/Fantasy-Basketball-Simulation-Model: roster-conditional category-win curves, max of sum Phi((T_c - mu_c) / sigma_c) with mu and sigma from simulated team totals; weekly simulator with hand-set variance per category. Evidence in-sample only (10.3 vs 5.9 of 11 matchups against sum-of-z bots). Same family as H-score and our team-conditional simulation.
- mccomark21/fantasy-basketball-rankings: category weights from waiver depth and weekly noise, w_c = sqrt((1 - W_c) / (1 - W_base) x SNR_c / SNR_base), W = waiver-tier output over pool mean, SNR = between-team spread over weekly noise. STL 0.44, BLK 0.65, 3PM 0.71. No evidence. The waiver-depth idea (a category that is easy to stream is worth less) is the one new ingredient here; it belongs with SAVOR, not with the value.
- George Berry (Substack): pseudo z for skewed counting stats by a fitted exponential distribution, score = Phi^-1(CDF(x)); top blocker from z 7.1 to 3.7. Visual evidence only. Our sqrt transform is the same idea; it helped only the DURANT match, not the H2H value (3.1).
- Dollar conversions in use: VORP proportional (RotoWire, sconies, mccomark21): 1 USD + share of (teams x budget - n) by value above replacement; replacement = rank n+1, or the mean of the next 6 or 14, or a waiver stat line; positional baseline (last player at each position = 1 USD, Hardball Times). Our plain conversion is this family with replacement = rank 145. Inflation formulas (FanGraphs, Draft Buddy) are dynamic prices, shelved by the user on 2026-10-06. Yahoo and ESPN default auction values: method undocumented; RotoWire saw ESPN values follow rank (about 70 USD for the top two, minus 1 per slot).
- SGP (Smart Fantasy Baseball): roto only; no H2H adaptation found. nbapr (simulated-league rank value): roto only. Tenth Cat "ECA": replacement-team weekly simulation, method unpublished.
- Not found: robust or MAD z in use, fantasy WAR, evidence for schedule or streaming formulas. A projection backtest in sconies (`data/eval.json`): rank correlation with the real season 0.54 for "last season repeated", 0.60 for a stats model, 0.68 for ESPN preseason; a useful yardstick for T-025.
- Prior art for our section 2, read in the user's Chrome: Giora Omer, "Fantasy NBA: Valuation Via Simulation" (Medium, 2023-09-26): random drafted 12-team leagues with positions, millions of matchups, H2H win share per player on 2022-23 per-game stats ("AVDIJA rankings"). Same idea, per-game lines without weekly variance or schedule; finds Giannis as the biggest gain over z, and z closer to the simulator than min-max scores (5.2 vs 6.3 rank spots). No test against real seasons. Verified.
- Still unread (403 for the agent): Razzball category values, Reddit threads, Harvard Sports Analysis handbook.


## 5. Career progression: base rates in our data
Year-over-year change of the per-game G-score rank (players with 1000+ minutes and 20+ games in both seasons, 592 pairs, 2022-23 to 2025-26, age on October 1 of the second season from `players.birth_date`). Verified.

| Age | n | mean rank change | improved 20+ ranks | declined 20+ ranks | top-150 only: mean change, improved 20+ |
|---|---|---|---|---|---|
| 22 and under | 75 | +38 | 65% | 16% | +27, 54% |
| 23 to 24 | 103 | +12 | 41% | 27% | -5, 27% |
| 25 to 26 | 110 | +6 | 34% | 30% | -8, 21% |
| 27 to 29 | 137 | -12 | 26% | 39% | -13, 24% |
| 30 to 32 | 100 | -16 | 20% | 41% | -24, 10% |
| 33 and over | 67 | -22 | 10% | 45% | -18, 8% |

- Age is the strongest cheap prior: under 23 most players improve, over 27 most decline. Rank-to-rank Spearman between seasons is 0.79, so the yearly change is large and mostly not explained by age (38% of the top-150 players who gained 20+ ranks were 24 or younger).
- Team change (modal team differs): movers aged 23 to 26 gained more than stayers (+35 vs +9 at 23 to 24, n=13; +19 vs +4 at 25 to 26, n=17; small samples), movers 27 and over lost a little more than stayers (-14 vs -10, -19 vs -13, -26 vs -19). Among movers the usage change does not correlate with the TS% change (-0.06, n=143); it correlates 0.29 with the rank change. Our 4 seasons cannot separate "fit" from "role": that needs minutes and usage projections, which T-025 already takes from the depth charts and the LLM layer.
- Team change in our data, year-to-year Pearson r of per-36 rates (1000+ minutes both seasons; stayers n=449, movers n=143): PTS 0.89 vs 0.79, TO 0.86 vs 0.76, usage 0.90 vs 0.81, FG% 0.85 vs 0.79, TS% 0.66 vs 0.61, AST 0.92 vs 0.87; REB 0.95 vs 0.94, BLK 0.90 vs 0.90, FT% 0.76 vs 0.76. A team change makes scoring volume, turnovers and usage less predictable; rebounds, blocks and free-throw shooting travel with the player. Verified (`movers.py`).

### 5b. Progression and projection systems in the literature (research pass, 2026-10-13)
Verified = the agent read the page; links in the research transcript, main ones here.
- DARKO (darko.app/about): every game weighted by beta^t with a beta per stat, plus a modified Kalman filter; a gradient-boosted tree combines both. Per-stat aging curves inside; a team change raises the learning rate. Half-lives: minutes about 2 games, usage about 17 games, 3P% about 1.5 seasons. Output: per-100-possession box-score projections plus projected minutes and pace (Fantasy Lab CSV), no season games-played. Terms: commercial use prohibited without permission, no license for bulk datasets. We already ingest DARKO minutes (T-026); the per-100 stats would be a cheap blend source for T-025 (inferred: personal use is within the terms; check before adding).
- Basketball-Reference Simple Projection System (Kubatko): minutes and stats weighted 6, 3, 1 over three seasons, add 1000 minutes of league average, per 36; age factor x(1 + (28 - age) x 0.004) under 28 and x(1 + (28 - age) x 0.002) over 28, sign reversed for misses, turnovers and fouls; projects misses, not attempts. Backtest 1983 to 2009, n=6887: r 0.839 on efficiency per 48. A clean baseline our blend must beat; needs 3 seasons of history per player (we have 4). Verified.
- Marcel (Tango): weights 5, 4, 3, 1200 PA of league average, age 0.006 per year under 29 and 0.003 over 29. Verified.
- SCHOENE (Pelton, ESPN): three seasons weighted by age plus regression; aging from the 50 most similar players at the same age; usage and roster-turnover adjustments at team level only. Method not reusable without the similarity database. Verified.
- Aging: Paine 2009 (players over 2000 minutes), change in win shares per 3000 minutes by age: 20 +2.0, 22 +1.2, 23 +1.2, 24 +0.5, 28 -0.4, 34 -1.0. Per-minute peak about 26, point guards 29 (Pelton 2018); survivor bias is large (APBR). Brahme and Franks, arXiv 2609.33752 (Sep 2026, about 2300 players 1997 to 2026): blocks and offensive rebounds peak in the early twenties, shooting in the mid-twenties or later, 3PA rate rises into the early thirties, minutes decay faster than they rise. No numeric table. Verified.
- Year 2 and year 3 jumps: no source quantifies a general year-1-to-2 or 2-to-3 delta. The Ringer (2024): outlier rookies regress (20+ ppg rookies +0.55 pts per 36, 10+ rpg rookies -0.4 reb per 36). The literature models age, not experience; our table in section 5 is the age prior we can use.
- Team change: Paine 2010 (1974 to 2010, ages 24 to 34), year-to-year r for stayers vs movers: TS% 0.71 vs 0.56, ORtg 0.72 vs 0.56, AST rate 0.97 vs 0.96, TO rate 0.80 vs 0.74, OREB% 0.94 vs 0.93; team plus role change drops AST rate to 0.79. Our replication above agrees in direction (scoring and turnovers lose stability, rebounds and blocks do not) with a smaller efficiency effect.
- Usage and efficiency: Oliver 2005 -0.6 ORtg per +1% usage; Witus 2008 -1.25 (lineup data); Paine tiers: usage under 18% 1.65, 18 to 23% 1.24, over 23% 0.82 ORtg per point of usage. Quoted via Paine; Witus original not opened. In our movers the usage change and the TS% change are uncorrelated (-0.06), so the trade-off is not visible at the season level in 4 seasons.
- Not found: Pelton's player-level team-change rule, a usage-redistribution model, Cleaning the Glass fit work, a paper that predicts a traded player's stats, Hashtag and FantasyPros projection methods, a next-season box-score ML paper with error numbers.
- What this suggests for T-025 (inferred): (1) an age multiplier per category in the base layer (SPS sizes as the start, early peak for BLK and OREB, late for 3P% and FT%); (2) for team changers, shrink the scoring, turnover and usage history harder toward the new role, keep REB, BLK and FT% history; (3) when a high-usage teammate arrives or leaves, rescale team usage to 100% and move efficiency by the Paine tiers, unvalidated; (4) DARKO per-100 stats as one more blend source. Own curves need more seasons; `make past-stats-sync SEASONS=...` can fetch them.

## 6. What this changes in our picture of the models
1. For an average, non-punting H2H team the best single number is G-score: it tracks the empirical value at 0.98, wins the hindsight tournament every season, and the empirically fitted weights are its weights. Z-score is a close second. This agrees with the one-season preseason backtest of 2026-10-04 (z9 63.0, G 59.7, Minus-1 59.2 cat share, within noise between z9 and G).
2. Minus-1 and DURANT answer a different question: the value of a player for a team that will punt his worst category. Static use on the whole table overrates one-category players for everyone (3.1, 3.2). The published DURANT H2H formula reproduces Lloyd's ranks (3.6b); as a per-game list it carries no games-played information by design.
3. A single-category punt toggle is a poor stand-in for a build (3.5). The build changes the worth of several categories and keeps some of the punted one. The honest tool is the team-conditional simulation, during the draft, on simulated weekly lines.
4. The simulation engine exists (scratch code): all 4 seasons, 600 contexts, about 3 seconds per season. Its hindsight values are a strict benchmark for any future model, and the projection prototype (3.9) shows it can run before the season.

## 7. Decisions for the user
Taken 2026-10-13 (user): 1 G-score default; 2 the published DURANT H2H and the broad DURANT replace the approximation; 3 Simulated H2H added to the dropdown (deterministic expected lines; the team-conditional draft-day version stays open); 4 FPts and Fluff columns; 5 Minus-2 and percentile z not added; 6 only the kappa fix (volume scaling: no evidence, Spearman change under 0.001); 7 not needed, T-025 already fits an age factor per component from our seasons (`fit_age`); 8 research scripts moved to `backend/scripts/research/valuation_2026_10_13/`. The list below is kept for the record.
1. Default model: keep Minus-1, or switch the table and the draft board to G-score (evidence above; the user's 2026-10-04 choice was Minus-1).
2. Replace the DURANT approximation by the published DURANT H2H (3.6b): Yeo-Johnson transform, weights 1.00 / 0.94 / 0.75 / 0.60, no turnovers, Minus 1, per game, full sample. Description for the dropdown: "Josh Lloyd's head-to-head list, as he published it: skew-corrected categories, points weigh most, no turnovers, worst category dropped." Needs scipy (Yeo-Johnson) or a small own implementation. The broad DURANT (turnovers at 0.50, no Minus 1) can be a second entry.
3. Add "Simulated H2H value" as a model: hindsight on real seasons now; on projections after a weekly-line simulator (per-game x schedule games per week x noise from logs). Also the team-conditional version for the draft assistant (T-018): "if you buy this player, your weekly cat share changes by X against each team". This is the H-score idea on our own engine; the paper is CC BY 4.0, the site code is not reusable.
4. Fantasy points (Yahoo formula) as a column, not a model: the fluff indicator from the spec (9-cat rank vs points rank).
5. Keep or drop: Minus-2 (weak everywhere), percentile z (weak in hindsight, strong only in the one-room preseason test), robust z (middle).
6. Small code fixes if wanted: G-score kappa from roster size; percentage volume scaling as in the zer2 site.
7. Progression: add an age prior to the own projection base layer (T-025) from the table in section 5, and keep team fit in the LLM layer. Needs more seasons of totals for a proper curve (`make past-stats-sync SEASONS=...` can fetch them).
8. Move the research scripts from `data/research/` into `backend/scripts/` (then they are in git) or leave them local.
