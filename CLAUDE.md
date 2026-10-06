# 2026-fantasy

Personal fantasy basketball "master" site for one Yahoo league. Used all season, not only for the draft.
One local backend, one database, one frontend. Features are widgets on that frontend.

## League rules
- Full rules (9-cat, roster, positions, draft, waivers, playoffs): `docs/RULES.md`. Loaded below. Update it when a rule is verified or changes.

@docs/RULES.md

## Hard boundaries
- Yahoo API is read-only for us. The tool never makes a transaction (no add, drop, claim, trade, bid).
- The tool only analyzes and shows. The user acts on Yahoo by hand.
- LLM work uses the local `claude -p` CLI with the user's subscription. Remove `ANTHROPIC_API_KEY` from the child env. Reference: `scripts/llm-bridge.mjs` in github.com/burakbilgehan/language-tutor.

## Documents (read the relevant one before work)
- `docs/RULES.md`: league rules and general fantasy facts (always in context).
- `docs/GLOSSARY.md`: fantasy terms, expert calls and our tag names, one meaning each. Add a term when you meet it.
- `docs/VISION.md`: full scope. All planned modules. Check here before adding a feature.
- `docs/ROADMAP.md`: phases and dates.
- `docs/TASKS.md`: open tasks. Update status when you finish a task.
- `docs/ARCHITECTURE.md`: stack, folders, data flow, widget model.
- `docs/DATA_SOURCES.md`: every external source, with verification status.
- `docs/modules/draft.md`: draft tool spec.
- `docs/modules/valuation.md`: valuation spec (T-017, T-010): pickers, model list with descriptions, backtest plan.
- `docs/modules/projection.md`: own projection spec (T-025): base layer, LLM context layer, where to change the model, commands.
- `docs/modules/knowledge.md`: expert knowledge synthesis spec (T-022): profiles, tags, articles.
- `prompts/`: every prompt and model setting sent to `claude -p`, one folder per job. Keep it current; code reads it from there.

## Pricing mentality (user rule, 2026-10-05)
- Two reference prices, never mixed: OURS (static price, from our model) and THE OTHERS (market price, the market's own dollars). Opportunity = static price - market price. Nothing moves during a draft: dynamic prices were shelved by the user on 2026-10-06; the user adjusts by hand. Never price by rank, never make a past auction a law. Details: `docs/modules/pricing.md`.

## Data freshness (user rule, 2026-10-05)
- No data source may be older than a week. `make sources` shows every source with its last fetch and age and fetches only the stale ones. Run it at the start of any session that uses source data (projections, values, draft).
- Fantrax projections need the user's logged-in Chrome tab: when `make sources` marks `fantrax_projections` STALE, ask the user, then run the fixed script `backend/app/sources/players/fantrax_capture.js` in a logged-in Fantrax tab (Claude in Chrome), poll `window.__fantraxCapture`, then `make players-sync SOURCE=fantrax`. No improvising: every fetch goes through a script.
- `make projection-context` checks and refreshes stale sources by itself before the LLM runs.
- Team rosters come only from NBA.com (`nba_rosters` job, daily). Other sources never set a team.
- Data flow diagram (user rule, 2026-10-05): `docs/modules/projection-flow.html`, published at https://claude.ai/artifact/Rw4PjAqVkZjrtv3WnNFerU . When a source or a step of the flow changes, edit the template `backend/app/analytics/projection/flow_template.html` (and its ledger table). After any change or refresh: `make flow`, then republish the file to that same URL.
- Own projection stays current in two layers: the base is rebuilt daily from the sources (`projection_base` job, free); the LLM layer reruns per team when that team's expert notes or roster change, when the prompt version changes, or after 7 days (`make projection-update`, also run at the end of `make knowledge-run`).

## Related local projects (reference only, do not edit)
- `~/projects/fantasy-basketball`: older Next.js attempt (Jan 2026). Has a Yahoo client (`lib/yahoo/`) and specs.
- `~/projects/trade-finder`: older JS trade combination finder.

## Work types (user rule, 2026-10-03)
- Engineering work: scaffolding, DB schema, data pipelines, source adapters, stack choices. Take the initiative. Decide and build. The user gives only small directions.
- Product work: what a good draft is, what a good player is, valuation models, price signals, what a widget shows and recommends. Formulas that turn data into "buy / do not buy" signals are product work too, even if they look like engineering.
- Product work is never built from passing remarks. The user's examples are examples, not the scope. When a product topic starts: research (web, data, experts), bring your own ideas and objections, brainstorm with the user. Claude researches, the user decides.
- Product topics stay open in `docs/VISION.md` ("Open product topics") until a refinement session closes them.

## Communication rules (mandatory)
- Write all chat replies in Turkish, in the style of ASD-STE100 (Simplified Technical English) rules:
  - One idea in one sentence.
  - Max 20 words in an instruction. Max 25 words in a description.
  - Use active voice. Use simple, common words. No idioms, no metaphors.
  - Use the same word for the same thing every time.
  - Use numbered steps for procedures. Put one action in one step.
- No em dash. No emojis. No praise.
- Keep replies short. The user cannot read long output.
- When you mention a task id (T-006) or module id, add a one-sentence summary of it. Do not make the user open the docs.

## Control rules (mandatory)
- Do not act on your own initiative outside the agreed task.
- Before large or multi-file work: show a short plan. Product work: wait for approval. Engineering work: state the plan and proceed.
- Do not invent facts. Mark every claim as one of: "verified" (I checked it), "inferred", "assumed".
- Do not guess API behavior or data. Check the source. Give the link.
- If information is missing, ask. Put all questions in one message.
- Report results, not steps.
- Use Claude in Chrome for browser work and for demos to the user.
- Keep sessions short. At the end of a session, update `docs/TASKS.md`.
