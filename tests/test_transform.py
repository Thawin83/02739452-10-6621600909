import pandas as pd
import pytest

from conftest import COMP, SEASON
from include.extractors.wikipedia_scraper import page_title, parse_league_table
from include.transform import (
    build_dataset,
    clean_team_label,
    load_frames,
    make_match_id,
    normalize_team_name,
    resolve_team_id,
    save_frames,
    to_int,
    local_to_utc_iso,
    transform_openfootball,
    transform_thesportsdb,
    transform_wikipedia,
)


@pytest.mark.parametrize("raw, expected", [
    ("Manchester United FC", "manchester united"),
    ("Brighton & Hove Albion", "brighton and hove albion"),
    ("Nott'm Forest", "nottm forest"),
    ("AFC Bournemouth", "bournemouth"),
    ("Atlético Madrid", "atletico madrid"),
    ("Arsenal (C)", "arsenal"),
    ("Chelsea[a]", "chelsea"),
    (None, ""),
])
def test_normalize_team_name(raw, expected):
    assert normalize_team_name(raw) == expected


@pytest.mark.parametrize("labels, team_id", [
    (["Manchester United FC", "Man United", "Man Utd", "Manchester United"], "manchester-united"),
    (["Brighton & Hove Albion FC", "Brighton and Hove Albion", "Brighton Hove"], "brighton"),
    (["Wolverhampton Wanderers FC", "Wolves", "Wolverhampton"], "wolverhampton-wanderers"),
    (["Tottenham Hotspur FC", "Spurs", "Tottenham"], "tottenham-hotspur"),
    (["Nottingham Forest FC", "Nott'm Forest"], "nottingham-forest"),
    (["AFC Bournemouth", "Bournemouth"], "bournemouth"),
])
def test_resolve_team_id_maps_all_source_variants(labels, team_id):
    assert {resolve_team_id(label) for label in labels} == {team_id}


def test_resolve_team_id_unknown_team_falls_back_to_slug():
    assert resolve_team_id("Real Sociedad de Fútbol") == "real-sociedad-de-futbol"


@pytest.mark.parametrize("value, expected", [
    ("+5", 5), ("−3", -3), ("− 4", -4), ("12[a]", 12), ("", None), (None, None),
    (float("nan"), None), (pd.NA, None), (7, 7), (2.0, 2), ("abc", None),
])
def test_to_int(value, expected):
    assert to_int(value) == expected


def test_clean_team_label_keeps_display_form():
    assert clean_team_label("Brighton & Hove Albion (Q)[b]") == "Brighton & Hove Albion"


def test_transform_openfootball(openfootball_raw):
    out = transform_openfootball(openfootball_raw, COMP, SEASON)

    assert list(out["teams"]["team_id"]) == ["manchester-united", "brighton"]
    m = out["matches"]
    assert m["match_id"].iloc[0] == make_match_id(COMP, SEASON, "manchester-united", "brighton")
    assert m["utc_date"].iloc[0] == "2026-08-15T14:00:00Z"  # 15:00 London (BST) -> 14:00 UTC
    assert m["matchday"].tolist() == [1, 2]
    assert m["status"].tolist() == ["FINISHED", "SCHEDULED"]
    assert (m["home_score"].iloc[0], m["away_score"].iloc[0]) == (2, 1)
    assert pd.isna(m["home_score"].iloc[1])
    assert "standings" not in out  # this source has fixtures/results only


def test_transform_openfootball_short_score_form():
    raw = {"matches": [{"round": "Matchday 3", "date": "2026-09-05", "time": "15:00",
                        "team1": "Nottingham Forest FC", "team2": "Tottenham Hotspur FC", "score": [0, 0]}]}
    m = transform_openfootball(raw, COMP, SEASON)["matches"]
    assert m["status"].iloc[0] == "FINISHED"
    assert (m["home_score"].iloc[0], m["away_score"].iloc[0]) == (0, 0)


def test_local_to_utc_iso_handles_daylight_saving():
    assert local_to_utc_iso("2026-12-26", "15:00", "Europe/London") == "2026-12-26T15:00:00Z"  # GMT
    assert local_to_utc_iso("2026-08-22", "20:00", "Europe/Madrid") == "2026-08-22T18:00:00Z"  # CEST
    assert local_to_utc_iso("bad", None, "Europe/London") is None


def test_transform_thesportsdb(thesportsdb_raw):
    out = transform_thesportsdb(thesportsdb_raw, COMP, SEASON)

    assert set(out["teams"]["team_id"]) == {"manchester-united", "brighton"}
    assert out["teams"]["founded"].tolist() == [1878, 1901]
    m = out["matches"]
    assert m["status"].tolist() == ["FINISHED", "FINISHED"]
    assert m["utc_date"].iloc[0] == "2026-08-15T14:00:00Z"
    assert str(m["home_score"].dtype) == "Int64"


def test_thesportsdb_status_fallback_uses_scores():
    raw = {"matches": [
        {"idEvent": "1", "strHomeTeam": "Arsenal", "strAwayTeam": "Chelsea", "intHomeScore": "1",
         "intAwayScore": "1", "strStatus": None, "dateEvent": "2026-09-01", "strTime": "15:00:00"},
        {"idEvent": "2", "strHomeTeam": "Chelsea", "strAwayTeam": "Arsenal", "intHomeScore": None,
         "intAwayScore": None, "strStatus": "", "dateEvent": "2027-01-01"},
    ]}
    m = transform_thesportsdb(raw, COMP, SEASON)["matches"]
    assert m["status"].tolist() == ["FINISHED", "SCHEDULED"]
    assert m["utc_date"].iloc[0] == "2026-09-01T15:00:00Z"


def test_transform_wikipedia(wikipedia_raw):
    out = transform_wikipedia(wikipedia_raw, COMP, SEASON)
    s = out["standings"]
    assert s["team_id"].tolist() == ["manchester-united", "brighton"]
    assert s["goal_difference"].tolist() == [1, -1]
    assert out["aliases"]["alias"].tolist() == ["Manchester United", "Brighton & Hove Albion"]


def test_parse_league_table_from_wikipedia_html():
    html = """
    <table class="wikitable"><tr><th>Season</th><th>Champion</th></tr><tr><td>1</td><td>x</td></tr></table>
    <table class="wikitable">
      <tr><th>Pos</th><th>Team</th><th>Pld</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th>
          <th>GD</th><th>Pts</th><th>Qualification</th></tr>
      <tr><td>1</td><th scope="row"><a>Arsenal</a> (C)</th><td>2</td><td>2</td><td>0</td><td>0</td>
          <td>5</td><td>1</td><td>+4</td><td>6</td><td rowspan="2">Champions League</td></tr>
      <tr><td>2</td><th scope="row"><a>Chelsea</a><sup>[a]</sup></th><td>2</td><td>1</td><td>1</td>
          <td>0</td><td>3</td><td>2</td><td>+1</td><td>4</td></tr>
    </table>"""
    rows = parse_league_table(html)
    assert [r["Team"] for r in rows] == ["Arsenal (C)", "Chelsea"]
    assert rows[1]["Pts"] == "4"


def test_thesportsdb_extractor_drops_teams_from_other_leagues():
    from include.extractors.thesportsdb import TheSportsDBExtractor

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            endpoint = url.rsplit("/", 1)[-1]
            body = {
                "lookup_all_teams.php": {"teams": [
                    {"strTeam": "Wigan Athletic", "idLeague": "4396"},
                    {"strTeam": "Arsenal", "idLeague": "4328"},
                    {"strTeam": "Chelsea", "idLeague": "4480", "idLeague2": "4328"},
                ]},
                "eventsseason.php": {"events": [{"idEvent": "1"}]},
                "eventsround.php": {"events": [{"idEvent": "1"}, {"idEvent": f"r{params.get('r')}"}]},
                "lookuptable.php": None,
            }[endpoint]
            return type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()

    out = TheSportsDBExtractor("123", "PL", 2026, session=FakeSession(), request_delay=0).extract()
    assert [t["strTeam"] for t in out["teams"]] == ["Arsenal", "Chelsea"]
    # season list + 38 matchday pages, merged by idEvent
    assert len(out["matches"]) == 1 + 38
    assert out["standings"] == []


def test_wikipedia_page_title():
    assert page_title("PL", 2026) == "2026–27_Premier_League"


def test_save_and_load_frames_roundtrip(tmp_path, openfootball_raw, thesportsdb_raw):
    frames = build_dataset({"openfootball": openfootball_raw, "thesportsdb": thesportsdb_raw}, COMP, SEASON)
    save_frames(frames, tmp_path)
    loaded = load_frames(tmp_path)

    def plain(df):  # same nulls regardless of dtype (object None vs str NaN)
        return df.astype(object).where(df.notna(), None).reset_index(drop=True)

    for name, df in frames.items():
        pd.testing.assert_frame_equal(plain(loaded[name]), plain(df), check_dtype=False, obj=name)
    assert loaded["teams"]["sources"].iloc[0] == frames["teams"]["sources"].iloc[0]
