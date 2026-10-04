import copy
import gzip
import json
from pathlib import Path

import pytest

from app.experts import extract
from app.experts.match import KnownPlayer, Matcher, learn_nicknames
from app.experts.render import render
from app.experts.transcript import TimedWords, blocks, find_quote, fmt_ts, parse_ts
from app.sources.experts.youtube import Video

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> dict:
    return json.loads(gzip.decompress((FIXTURES / name).read_bytes()))


@pytest.fixture(scope="module")
def video() -> Video:
    return Video.from_dict(_read("youtube_tnzmsYUA4yQ.json.gz"))


@pytest.fixture
def notes() -> dict:
    return _read("expert_notes_tnzmsYUA4yQ.json.gz")


PLAYERS = [
    KnownPlayer("Darius Garland", "LAC", "darius garland"),
    KnownPlayer("Derrick Jones Jr.", "LAC", "derrick jones"),
    KnownPlayer("Victor Wembanyama", "SAS", "victor wembanyama"),
    KnownPlayer("Harrison Barnes", "SAS", "harrison barnes"),
    KnownPlayer("Scottie Barnes", "TOR", "scottie barnes"),
    KnownPlayer("Rui Hachimura", "LAC", "rui hachimura"),
]
ALIASES = {"players": {"Pencil": "Harrison Barnes", "Enpitsu": "Rui Hachimura"}, "teams": {"Clippers": "LAC"}}


def test_timestamps():
    assert fmt_ts(59) == "0:59" and fmt_ts(3725) == "1:02:05"
    assert parse_ts("12:34") == 754 and parse_ts("[1:02:05]") == 3725 and parse_ts(90) == 90
    assert parse_ts("soon") is None and parse_ts("") is None


def test_blocks_cover_whole_transcript(video):
    text = blocks(video.segments)
    lines = text.splitlines()
    assert lines[0].startswith("[0:0")
    assert 60 <= len(lines) <= 80  # 35:22 video in 30 s blocks
    assert sum(len(l.split()) for l in lines) == sum(len(s.text.split()) for s in video.segments) + len(lines)


def test_find_quote(video):
    tw = TimedWords.of(video.segments)
    real = "averaged basically 20 points with seven assists in just 30 minutes on 29 usage"
    ratio, sec = find_quote(tw, real, near=441)
    assert ratio == 1.0 and 455 <= sec <= 470
    # Found far from a wrong timestamp too, with the real position.
    assert 455 <= find_quote(tw, real, near=2000)[1] <= 470
    # Noisy caption still matches (two words changed).
    assert find_quote(tw, "averaged basically 21 points with seven assists in only 30 minutes on 29 usage", 441)
    # Invented and too-short quotes fail.
    assert find_quote(tw, "Garland is the best rebounder in the league and a lock for top five", 441) is None
    assert find_quote(tw, "He's going to be", 1724) is None


def test_verify_flags_invented_items(video, notes):
    notes["player_notes"].append({
        "player": "Darius Garland", "said_as": "Garland", "horizon": "current",
        "text": "Invented.", "ts": "7:21", "quote": "Garland will lead the league in blocks this season for sure",
    })
    notes["rules"].append({"text": "Bad ts.", "ts": "99:99:99", "quote": "nothing like this was ever said in the video"})
    out = extract.verify(notes, video)
    assert out["player_notes"][-1]["verified"] is False
    assert out["rules"][-1]["verified"] is False and out["rules"][-1]["seconds"] is None
    real = [i for i in out["player_notes"][:-1] if len(i["quote"].split()) >= 6]
    assert real and all(i["verified"] for i in real)


def test_no_em_dash():
    assert extract.no_em_dash({"a": ["x — y", "z—w"], "b": 1}) == {"a": ["x, y", "z, w"], "b": 1}


def test_matcher_names_aliases_teams():
    m = Matcher(PLAYERS, {"players": {"Wemby": "Victor Wembanyama"}, "teams": {"Clippers": "LAC"}})
    assert m.player("Derrick Jones Jr.").name == "Derrick Jones Jr."
    assert m.player("Darius Garland").slug == "darius-garland"
    assert m.player("Someone Else", "Wemby").name == "Victor Wembanyama"
    assert m.player("Wemby").team == "SAS"
    assert m.player("Nobody Real") is None
    assert m.team("LAC") == "LAC" and m.team("GS") == "GSW" and m.team("Clippers") == "LAC"
    assert m.team("Seattle") is None


def test_matcher_order_and_fuzzy():
    m = Matcher(PLAYERS, ALIASES)
    # The user's alias wins over a wrong LLM guess.
    assert m.player_how("Scottie Barnes", "Pencil") == (m.player("Harrison Barnes"), "alias")
    assert m.player_how("Enpitsu", "Enpitsu")[1] == "alias"
    assert m.player_how("Rui Hachimura", "Ruy")[1] == "exact"
    # Same first initial and last name; a shared last name needs the team.
    assert m.player_how("Ruy Hachimura")[0].name == "Rui Hachimura"
    assert m.player_how("Ruy Hachimura")[1] == "fuzzy"
    assert m.player_how("Kevin Hachimura")[1] == "none"
    assert m.player_how("Victor Wembanyamma")[1] == "fuzzy"


def test_matcher_uses_team_for_shared_names():
    twins = [KnownPlayer("Jalen Williams", "OKC", "jalen williams"),
             KnownPlayer("Jalen Williams", "FA", "jalen williams"),
             KnownPlayer("Harrison Barnes", "SAS", "harrison barnes"),
             KnownPlayer("Scottie Barnes", "TOR", "scottie barnes"),
             KnownPlayer("Harold Barnett", "TOR", "harold barnett")]
    m = Matcher(twins, {})
    assert m.player("Jalen Williams") is None
    assert m.player("Jalen Williams", team="OKC").team == "OKC"
    assert m.player("Jalen Williams", team="GS") is None
    assert m.player("Scottie Barnes", "Barnes", "TOR").name == "Scottie Barnes"
    assert m.player("Harald Barnes", team="SAS").name == "Harrison Barnes"  # fuzzy + team
    assert m.player_how("Harald Barnes") == (twins[2], "fuzzy")  # only one H. Barnes
    assert m.player("Barnes", "Barnes") is None


def test_learn_nicknames():
    h = KnownPlayer("Rui Hachimura", "LAC", "rui hachimura")
    a = KnownPlayer("Alperen Sengun", "HOU", "alperen sengun")
    j = KnownPlayer("Jalen Duren", "DET", "jalen duren")
    b = KnownPlayer("Jalen Brunson", "NYK", "jalen brunson")
    pairs = [("Enpitsu", h), ("Enpitsu", h), ("Rui", h), ("Hachimura", h), ("Delicate Dancer", a),
             ("JD", j), ("JD", b), ("JD", j), ("", a)]
    # Once is not enough; one nickname for two players is not learned; real name parts are not nicknames.
    assert learn_nicknames(pairs) == {"Enpitsu": "Rui Hachimura"}
    m = Matcher([h, a], {"learned_players": learn_nicknames(pairs, min_count=1)})
    assert m.player_how("Enpitsu", "Enpitsu") == (h, "learned")
    assert m.player_how("Alperen Sengun", "Delicate Dancer") == (a, "exact")


def test_build_prompt_has_no_name_lists(video):
    p = extract.build_prompt(video)
    assert "Victor Wembanyama" not in p and "Pencil" not in p
    assert "[m:ss]" in p and p.rstrip().endswith(video.segments[-1].text.replace("\n", " ").strip())


def test_matcher_skips_ambiguous_keys():
    twins = [KnownPlayer("Jalen Williams", "OKC", "jalen williams"),
             KnownPlayer("Jalen Williams", "FA", "jalen williams")]
    assert Matcher(twins, {}).player("Jalen Williams") is None


def test_render(tmp_path, video, notes):
    notes = extract.verify(copy.deepcopy(notes), video)
    notes["player_notes"].append({
        "player": "Darius Garland", "said_as": "Garland", "horizon": "durable", "text": "Invented note.",
        "ts": "7:21", "quote": "x", "verified": False, "seconds": 441,
    })
    stale = tmp_path / "players" / "old-player.md"
    stale.parent.mkdir()
    stale.write_text("old")
    counts = render([notes], Matcher(PLAYERS, {}), tmp_path)
    assert not stale.exists()
    assert counts["videos"] == 1 and counts["players"] == 3  # Garland, Jones, Hachimura; rest unmatched
    garland = (tmp_path / "players" / "darius-garland.md").read_text()
    assert "## Durable" in garland and "## Current" in garland
    assert "https://youtu.be/tnzmsYUA4yQ?t=" in garland and "Invented note" not in garland
    page = (tmp_path / "videos" / "2026-10-04-tnzmsYUA4yQ.md").read_text()
    assert "## Unverified" in page and "Invented note" in page
    assert "Brandon Ingram" in (tmp_path / "_unmatched.md").read_text()
    for f in tmp_path.rglob("*.md"):
        assert "—" not in f.read_text() and ".." not in f.read_text().replace("../", "")


def test_receiver_payload_to_video():
    from app.jobs.transcript_receiver import to_video
    v = to_video({"video_id": "abc", "title": "T", "channel": "C", "publish_date": "2026-08-01T18:33:06-07:00",
                  "duration": 2275, "segments": [{"ts": "0:01", "text": " Hello  there "}, {"ts": "", "text": "x"},
                                                 {"ts": "1:02:03", "text": "late"}, {"ts": "0:05", "text": ""}]})
    assert v.upload_date == "2026-08-01" and v.duration == 2275
    assert [(s.start, s.text) for s in v.segments] == [(1.0, "Hello there"), (3723.0, "late")]
    with pytest.raises(ValueError):
        to_video({"video_id": "abc", "segments": []})
