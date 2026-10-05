"""HTML review of the own projection (T-025), one page per team or all teams in one page.

Same heat colors as the value table on the site (frontend PlayerValues.tsx and index.css):
category z from the valuation engine, green above 0 and red below, stronger with |z|, full
color at |z| = 2.5, bold from |z| = 1.5. Value = the site's default model: Minus-1 on season
totals, reference pool 200, plain dollars, run on the whole "own" projection.
"""

import html
import json
from pathlib import Path

from sqlalchemy import func, select

from app.analytics.projection import context, context_data as cd
from app.analytics.valuation import CATEGORIES, Settings, run as value_run
from app.db import SessionLocal
from app.models import (Player, PlayerAdvancedStats, PlayerGameLog, PlayerProjection, PlayerSeasonStats,
                        ProjectionAdjustment)
from app.seasons import CURRENT_SEASON, previous
from app.sources.players.base import STAT_FIELDS

SEASON = CURRENT_SEASON
Z_FULL, Z_STRONG, TOTAL_FULL = 2.5, 1.5, 10.0
COUNTING = ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")
LABEL = {"tpm": "3PM", "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TO"}
LINES = (("yahoo", "Yahoo"), ("fanscout", "FanScout"), ("fantrax", "Fantrax"), ("espn", "ESPN"),
         ("own-stat", "Own stat model"), ("own-base", "Own base (consensus)"), ("own", "Own"),
         ("own-floor", "Floor"), ("own-ceiling", "Ceiling"))

CSS = """
:root { --bg:#fbfaf7; --panel:#fff; --text:#1d1d1b; --muted:#6b6a65; --line:#e6e3dc; --good:#2f8f57; --bad:#c4473b; --heat-max:44%; --accent:#3d5a80; }
@media (prefers-color-scheme: dark) { :root { --bg:#151514; --panel:#1d1d1b; --text:#ecebe6; --muted:#a3a19a; --line:#34332f; --good:#6fc18d; --bad:#e8806f; --heat-max:46%; --accent:#8fb3dd; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width:1200px; margin:0 auto; padding:20px 16px 60px; }
h1 { font-size:1.5rem; margin:28px 0 4px; } h2 { font-size:1.15rem; margin:26px 0 8px; } h3 { font-size:1rem; margin:22px 0 6px; }
.muted { color:var(--muted); } .small { font-size:.85rem; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; background:var(--panel); }
th, td { padding:5px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
th { font-size:.78rem; color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--panel); }
td.name, th.name { text-align:left; }
tr.total td { font-weight:700; border-top:2px solid var(--line); }
tr.own td { font-weight:600; } tr.ref td { color:var(--muted); }
td.heat { padding:2px 3px; } td.heat span { display:block; padding:3px 6px; border-radius:6px; }
td.heat.good span { background:color-mix(in oklab, var(--good) calc(var(--a) * var(--heat-max)), transparent); }
td.heat.bad span { background:color-mix(in oklab, var(--bad) calc(var(--a) * var(--heat-max)), transparent); }
td.heat.strong.good span { color:color-mix(in oklab, var(--good) 70%, var(--text)); font-weight:700; }
td.heat.strong.bad span { color:color-mix(in oklab, var(--bad) 70%, var(--text)); font-weight:700; }
.note { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:8px 0; }
.chg { font-family:ui-monospace, monospace; font-size:.82rem; color:var(--accent); }
ul.reasons { margin:6px 0 0 18px; padding:0; } ul.reasons li { margin:2px 0; }
a { color:var(--accent); text-underline-offset:2px; } a:visited { color:var(--accent); }
nav a { margin-right:10px; }
td.name a { color:var(--text); font-weight:600; text-decoration-color:var(--muted); }
.player { border-top:1px solid var(--line); padding-top:4px; }
"""


def e(x) -> str:
    return html.escape(str(x))


def heat(text: str, z: float | None, full: float = Z_FULL) -> str:
    if z is None:
        return f"<td>{e(text)}</td>"
    a = min(abs(z) / full, 1.0)
    cls = ["heat", "good" if z >= 0 else "bad"] + (["strong"] if abs(z) / full >= Z_STRONG / Z_FULL else [])
    return f'<td class="{" ".join(cls)}"><span style="--a:{a:.3f}">{e(text)}</span></td>'


def values() -> dict[int, dict]:
    """Minus-1 on the whole own projection, the site's default settings."""
    from app.api.valuation import _league_draft

    with SessionLocal() as db:
        rows = {r.player_pk: {f: getattr(r, f) for f in STAT_FIELDS} for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.source == "own", PlayerProjection.season == SEASON)) if r.gp}
    n, budget = _league_draft()
    return value_run(rows, "minus1", Settings(basis="totals", pool=200), n_drafted=n, budget=budget, dollars="plain")


def cat_cells(r, z: dict | None) -> str:
    g = r.gp or 1.0
    fg = f"{100 * r.fgm / r.fga:.1f} ({r.fga / g:.1f})" if r.fga else "-"
    ft = f"{100 * r.ftm / r.fta:.1f} ({r.fta / g:.1f})" if r.fta else "-"
    z = z or {}
    out = [heat(fg, z.get("fg_pct")), heat(ft, z.get("ft_pct"))]
    out += [heat(f"{getattr(r, c) / g:.1f}", z.get(c)) for c in COUNTING]
    return "".join(out)


CAT_HEAD = "<th>FG% (FGA)</th><th>FT% (FTA)</th>" + "".join(f"<th>{LABEL[c]}</th>" for c in COUNTING)


def team_page(team: str, vals: dict) -> str:
    doc = json.loads((context.OUT_DIR / f"{team}.json").read_text())
    with SessionLocal() as db:
        names = {p.id: f"{p.first_name} {p.last_name}" for p in db.scalars(select(Player).where(Player.team == team))}
        ids = list(names)
        proj = {(r.player_pk, r.source): r for r in db.scalars(select(PlayerProjection).where(
            PlayerProjection.season == SEASON, PlayerProjection.player_pk.in_(ids)))}
        adj = {}
        for a in db.scalars(select(ProjectionAdjustment).where(ProjectionAdjustment.season == SEASON,
                                                               ProjectionAdjustment.player_pk.in_(ids))):
            adj.setdefault(a.player_pk, []).append(a)
        actual = {r.player_pk: r for r in db.scalars(select(PlayerSeasonStats).where(
            PlayerSeasonStats.source == "nba", PlayerSeasonStats.season == previous(SEASON),
            PlayerSeasonStats.player_pk.in_(ids)))}
        mins_last = {pk: m for pk, m in db.execute(select(PlayerGameLog.player_pk, func.sum(PlayerGameLog.min)).where(
            PlayerGameLog.season == previous(SEASON), PlayerGameLog.season_type == "regular",
            PlayerGameLog.player_pk.in_(ids)).group_by(PlayerGameLog.player_pk))}
        usg_last = {}
        for r in db.scalars(select(PlayerAdvancedStats).where(PlayerAdvancedStats.source == "nba",
                                                             PlayerAdvancedStats.player_pk.in_(ids))
                            .order_by(PlayerAdvancedStats.season.desc())):
            if r.usg_pct is not None:
                usg_last.setdefault(r.player_pk, r.usg_pct)
        sources = cd.sources_summary(db)
    order = sorted((pk for pk in names if (pk, "own") in proj and proj[(pk, "own")].gp),
                   key=lambda pk: -(proj[(pk, "own")].min or 0) / proj[(pk, "own")].gp)
    llm = doc.get("llm") or {}
    out = [f'<section id="{team}"><h1>{e(team)}: projection review</h1>',
           f'<p class="muted small">Built {e(doc["built_at"])}, prompt v{e(doc.get("prompt_version"))}, '
           f'{(llm.get("cost_usd_list") or 0):.2f} USD list, {round((llm.get("duration_ms") or 0) / 60000, 1)} min. '
           'Value = Minus-1, season totals, pool 200, plain dollars (the site default), on the whole own projection. '
           'Colors = category z in that model: green helps, red hurts, stronger color = further from average.</p>']

    # Team table.
    out += ['<h2>Team projection</h2><div class="scroll"><table><tr><th class="name">Player</th><th>Rank</th>'
            '<th>$</th><th>Value</th><th>GP</th><th>MIN</th><th>USG% (last)</th>' + CAT_HEAD + '</tr>']
    tot = {k: 0.0 for k in ("min", "fga", "fgm", "fta", "ftm", *COUNTING)}
    usg_min = 0.0
    for pk in order:
        r, v = proj[(pk, "own")], vals.get(pk)
        g = r.gp
        share = g / 82
        u = next((a.usg for a in adj.get(pk, []) if a.usg is not None), None)
        if u is not None:
            usg_min += u * (r.min or 0) / g * share
        for k in tot:
            tot[k] += ((r.min or 0) if k == "min" else getattr(r, k)) / g * share
        ul = usg_last.get(pk)
        usg = (f"{u:.1f}" if u is not None else "-") + (f" ({100 * ul:.1f})" if ul is not None else "")
        out.append(f'<tr><td class="name"><a href="#{team}-{pk}">{e(names[pk])}</a></td>'
                   f'<td>{v["rank"] if v else "-"}</td><td>{"$" + format(v["dollars"], ".0f") if v else "-"}</td>'
                   + heat(f'{v["total"]:.2f}' if v else "-", v["total"] if v else None, TOTAL_FULL)
                   + f"<td>{g:.0f}</td><td>{(r.min or 0) / g:.1f}</td><td>{e(usg)}</td>"
                   + cat_cells(r, v["z"] if v else None) + "</tr>")
    fg = f"{100 * tot['fgm'] / tot['fga']:.1f} ({tot['fga']:.1f})" if tot["fga"] else "-"
    ft = f"{100 * tot['ftm'] / tot['fta']:.1f} ({tot['fta']:.1f})" if tot["fta"] else "-"
    out.append(f'<tr class="total"><td class="name">Total per team game</td><td></td><td></td><td></td><td></td>'
               f"<td>{tot['min']:.0f}</td><td>{usg_min / 48:.0f}</td><td>{fg}</td><td>{ft}</td>"
               + "".join(f"<td>{tot[c]:.1f}</td>" for c in COUNTING) + "</tr>")
    last = cd.team_last_season(team)
    if last:
        out.append(f'<tr class="ref"><td class="name">{e(team)} {previous(SEASON)} actual</td><td></td><td></td><td></td><td></td>'
                   f"<td>{last['min']:.0f}</td><td></td><td>{100 * last['fgm'] / last['fga']:.1f} ({last['fga']:.1f})</td>"
                   f"<td>{100 * last['ftm'] / last['fta']:.1f} ({last['fta']:.1f})</td>"
                   + "".join(f"<td>{last[c]:.1f}</td>" for c in COUNTING) + "</tr>")
    out.append("</table></div>")
    out.append('<p class="muted small">Checks: minutes about 240 per team game; USG% total = sum of usage x minutes / 48, '
               "about 100. Each line counts by the player's share of the 82 games.</p>")
    out.append(f'<div class="note"><b>Team note (LLM).</b> {e(doc.get("team_note", ""))}</div>')

    # Sources.
    out.append("<h3>Sources behind the base</h3>")
    out.append(md_table_to_html(sources))

    # Players.
    out.append("<h2>Players</h2>")
    for pk in order:
        v = vals.get(pk)
        head = f"#{v['rank']}, ${v['dollars']:.0f}, value {v['total']:.2f}" if v else "no value"
        out.append(f'<div class="player" id="{team}-{pk}"><h3>{e(names[pk])} <span class="muted small">{e(head)}</span></h3>')
        out.append('<div class="scroll"><table><tr><th class="name">Line</th><th>GP</th><th>MIN</th>' + CAT_HEAD + "</tr>")
        lines = [(label, proj.get((pk, src)), src) for src, label in LINES]
        lines.append((f"{previous(SEASON)} actual", actual.get(pk), "actual"))
        for label, r, src in lines:
            if r is None or not r.gp:
                continue
            m = mins_last.get(pk) if src == "actual" else r.min
            z = v["z"] if (src == "own" and v) else None
            cls = "own" if src == "own" else ("ref" if src in ("actual",) else "")
            out.append(f'<tr class="{cls}"><td class="name">{e(label)}</td><td>{r.gp:.0f}</td>'
                       f"<td>{(m / r.gp) if m else 0:.1f}</td>" + cat_cells(r, z) + "</tr>")
        out.append("</table></div>")
        for a in adj.get(pk, []):
            bits = [f"usg {a.usg:g}" if a.usg is not None else None, f"mpg {a.mpg:g}" if a.mpg is not None else None,
                    f"gp {a.gp:g}" if a.gp is not None else None,
                    f"games out {a.games_out:g}" if a.games_out else None,
                    f"late games out {a.late_games_out:g}" if a.late_games_out else None,
                    ", ".join(f"{k} x{x}" for k, x in (a.multipliers or {}).items()) or None]
            out.append(f'<p class="chg">[{e(a.source)}] {e("; ".join(b for b in bits if b) or "no change")}</p>')
            if a.note:
                out.append(f"<p>{e(a.note)}</p>")
            if a.reasons:
                out.append('<ul class="reasons">' + "".join(
                    f"<li><b>{e(x.get('field'))}</b>: {e(x.get('text'))}</li>" for x in a.reasons) + "</ul>")
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


def md_table_to_html(md: str) -> str:
    rows = [r.strip().strip("|").split("|") for r in md.strip().splitlines() if r.strip() and not set(r) <= set("|-: ")]
    head, body = rows[0], rows[1:]
    return ('<div class="scroll"><table><tr>' + "".join(f'<th class="name">{e(h.strip())}</th>' for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f'<td class="name">{e(c.strip())}</td>' for c in r) + "</tr>" for r in body)
            + "</table></div>")


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>{e(title)}</title><style>{CSS}</style></head>'
            f"<body><main>{body}</main></body></html>")


def write(teams: list[str]) -> Path:
    vals = values()
    out_dir = context.OUT_DIR / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(teams) == 1:
        path = out_dir / f"{teams[0]}.html"
        path.write_text(page(f"{teams[0]} projection", team_page(teams[0], vals)), encoding="utf-8")
        return path
    nav = "<nav>" + "".join(f'<a href="#{t}">{t}</a>' for t in teams) + "</nav>"
    path = out_dir / "ALL.html"
    path.write_text(page("Own projection review", "<h1>Own projection review</h1>" + nav
                         + "".join(team_page(t, vals) for t in teams)), encoding="utf-8")
    return path
