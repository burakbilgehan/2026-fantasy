from app.knowledge import profile, render, tags


def _reg():
    return tags.Registry([
        tags.Tag("role up", "More minutes.", "role", "current", []),
        tags.Tag("injury prone", "Misses games.", "risk", "durable", ["fragile"]),
    ], [])


def test_resolve_ignores_case_hyphens_and_aliases():
    reg = _reg()
    assert reg.resolve("Role-Up").name == "role up"
    assert reg.resolve("fragile").name == "injury prone"
    assert reg.resolve("bigger role") is None


def test_apply_decisions_merge_new_drop():
    reg = _reg()
    log = tags.apply_decisions(reg, [
        {"proposal": "bigger role", "action": "merge", "target": "role up"},
        {"proposal": "usage bump", "action": "merge", "target": "usage up"},  # target made in this batch
        {"proposal": "usage riser", "action": "new", "target": "usage up", "meaning": "More shots.",
         "kind": "role", "channel": "current"},
        {"proposal": "two-category player", "action": "drop", "reason": "vague"},
        {"proposal": "x", "action": "merge", "target": "no such tag"},
    ])
    assert reg.resolve("bigger role").name == "role up"
    assert reg.resolve("usage bump").name == "usage up"
    assert reg.resolve("usage riser").name == "usage up"
    assert reg.is_dropped("two-category player")
    assert not reg.known("x")
    assert any(line.startswith("unresolved: x") for line in log)


def test_check_rejects_items_without_valid_source():
    out = {"current": [{"text": "a", "sources": ["v1:p0", "bogus"]}, {"text": "b", "sources": ["nope"]}],
           "durable": [{"text": "c", "sources": ["stats"]}], "tags": [{"name": "t", "sources": []}]}
    out, rejected = profile.check(out, {"v1:p0"})
    assert [i["text"] for i in out["current"]] == ["a"]
    assert out["current"][0]["bad_sources"] == ["bogus"]
    assert [i["text"] for i in out["durable"]] == ["c"]
    assert {r.get("text") or r.get("name") for r in rejected} == {"b", "t"}


def test_resolved_tags_merges_duplicates_and_hides_dropped():
    reg = _reg()
    reg.drop("vague tag")
    doc = {"tags": [
        {"name": "role up", "channel": "current", "detail": "starter now", "until": ""},
        {"name": "Role-up", "channel": "current", "detail": "more usage", "until": ""},
        {"name": "fragile", "channel": "current", "detail": "", "until": ""},  # registry channel wins
        {"name": "vague tag", "channel": "current", "detail": "", "until": ""},
        {"name": "brand new", "channel": "current", "detail": "", "until": ""},
    ]}
    got = render.resolved_tags(doc, reg)
    cur = {e["name"]: e for e in got["current"]}
    assert cur["role up"]["detail"] == "starter now; more usage"
    assert cur["brand new"]["unclassified"]
    assert "vague tag" not in cur
    assert [e["name"] for e in got["durable"]] == ["injury prone"]


def _prof(league=None, pos=None, groups=("G",), tpm=1.0):
    from app.knowledge import categories as C
    lz = {c: 0.0 for c in C.CATS} | (league or {})
    pz = {c: 0.0 for c in C.CATS} | (pos or {})
    return C.Profile({c: 0.0 for c in C.CATS} | {"3PM": tpm}, lz, pz, list(groups), True)


def test_gate_needs_real_outliers():
    from app.knowledge.categories import allowed
    trae = _prof(league={"AST": 3.8, "PTS": 1.6, "FG%": -1.8}, pos={"BLK": -0.9, "FG%": -2.1})
    assert allowed("strong:AST", trae, None, ["stats"])[0]
    assert not allowed("strong:PTS", trae, None, ["stats"])[0]   # good scorer, not an outlier
    assert allowed("weak:FG%", trae, None, ["stats"])[0]
    assert allowed("posweak:FG%", trae, None, ["stats"])[0]
    assert not allowed("posweak:BLK", trae, None, ["stats"])[0]  # few blocks is normal for a guard
    assert not allowed("noweak", trae, None, ["stats"])[0]
    assert not allowed("bigstrong:AST", trae, None, ["stats"])[0]
    assert allowed("no3pm", _prof(tpm=0.1), None, [])[0]
    assert not allowed("strong:AST", None, None, ["stats"])[0]   # no projection


def test_gate_injury_needs_status_or_note():
    from app.knowledge.categories import allowed
    assert not allowed("injury", None, None, ["stats"])[0]
    assert allowed("injury", None, "O (Knee)", ["stats"])[0]
    assert allowed("injury", None, None, ["abc:p1"])[0]


def test_punt_fit_only_for_two_weakest_and_positive_rest():
    weak_everywhere = _prof(league={c: -0.8 for c in ("PTS", "REB", "AST", "STL", "BLK")},
                            pos={c: -1.2 for c in ("PTS", "REB", "AST", "STL", "BLK")})
    assert weak_everywhere.pos_weaknesses() == []          # a low value player, not a punt fit
    giannis = _prof(league={"FG%": 4.7, "PTS": 2.9, "REB": 2.5, "FT%": -6.4, "3PM": -1.2, "TO": -2.5},
                    pos={"FT%": -5.9, "TO": -2.9, "3PM": -1.0}, groups=("F", "C"))
    assert giannis.pos_weaknesses() == ["FT%", "TO"]


def test_drawer_article_index_and_links(tmp_path):
    from app.knowledge.index import article_index, for_drawer

    (tmp_path / "README.md").write_text("# Index\n[A](../profiles/players/aa-bb.md)\n")
    (tmp_path / "x.md").write_text(
        "<!-- gen -->\n# Title X\nOne ([A](../profiles/players/aa-bb.md)), two ([A](../profiles/players/aa-bb.md)),"
        " unknown ([U](../profiles/players/zz.md)), [C](../profiles/players/cc.md)\n")
    (tmp_path / "y.md").write_text("# Title Y\n[A](../profiles/players/aa-bb.md)\n")
    idx = article_index({"aa-bb": 1, "cc": 2}, tmp_path)
    assert idx[1] == [{"slug": "x", "title": "Title X", "mentions": 2}, {"slug": "y", "title": "Title Y", "mentions": 1}]
    assert idx[2] == [{"slug": "x", "title": "Title X", "mentions": 1}]
    assert set(idx) == {1, 2}  # README skipped, unknown slug skipped

    md = for_drawer((tmp_path / "x.md").read_text(), {"aa-bb": 1})
    assert not md.startswith("<!--") and "# Title X" not in md
    assert "[A](#player/1)" in md and "[U](#)" in md


def test_drawer_off_categories():
    from app.api.valuation import off_categories

    z = {"fg_pct": 1, "ft_pct": -2, "tpm": 0, "pts": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": -3}
    assert off_categories("zscore", z, frozenset()) == []
    assert off_categories("punt", z, frozenset({"ft_pct"})) == ["ft_pct"]
    assert off_categories("minus1", z, frozenset()) == ["tov"]
    assert off_categories("durant", z, frozenset()) == ["ft_pct", "tov"]


def test_render_newest_first():
    from app.knowledge.render import newest_first

    items = [{"date": "2026-07-31", "t": "a"}, {"date": "2026-09-29", "t": "b"}, {"date": "2026-09-29", "t": "c"}]
    assert [i["t"] for i in newest_first(items)] == ["b", "c", "a"]


def test_usage_season_and_advanced_parse():
    import pytest

    from app.api.valuation import usage_season
    from app.sources.players import nba_advanced

    assert usage_season("actual", "2024-25") == "2024-25"
    assert usage_season("projection", "2026-27") == "2025-26"
    headers = ["PLAYER_ID", "PLAYER_NAME", "GP", "USG_PCT", "TS_PCT", "MIN"]
    payload = {"parameters": {"Season": "2025-26", "MeasureType": "Advanced"},
               "resultSets": [{"headers": headers, "rowSet": [[i, f"P{i}", 50, 0.2, 0.6, 30.0] for i in range(400)]}]}
    rows = nba_advanced.parse({"2025-26": payload})
    assert rows[0] == {"nba_id": "0", "name": "P0", "season": "2025-26", "gp": 50.0, "usg_pct": 0.2, "ts_pct": 0.6,
                       "extra": {**{k.lower(): None for k in nba_advanced.KEEP}, "min": 30.0, "usg_pct": 0.2,
                                 "ts_pct": 0.6}}
    payload["parameters"]["MeasureType"] = "Base"
    with pytest.raises(ValueError):
        nba_advanced.parse({"2025-26": payload})


def test_profile_summary_for_draft_panel():
    from app.knowledge.index import summary
    md = ("**Current**\n- He starts. (fact, 2026-09-29; [09-29](https://youtu.be/x?t=1))\n\n"
          "**Durable**\n- Weak [Steals](#) for a big. (fact, 2026-10-04; stats)\n\n"
          "**Note.** Worth a [bench](#) bid.\n")
    assert summary(md) == {"note": "Worth a bench bid.", "current": ["He starts."], "durable": ["Weak Steals for a big."]}
