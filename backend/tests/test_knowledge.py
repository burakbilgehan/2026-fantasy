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
