import pandas as pd

from conftest import COMP, SEASON
from include.transform import (
    MATCH_COLS,
    TEAM_COLS,
    build_dataset,
    dedup_matches,
    dedup_standings,
    dedup_teams,
    make_match_id,
)

MID = make_match_id(COMP, SEASON, "arsenal", "chelsea")


def _match(source, status, home_score=None, away_score=None, **kw):
    row = dict(match_id=MID, competition=COMP, season=SEASON, matchday=1, utc_date="2026-08-15T14:00:00Z",
               status=status, home_team_id="arsenal", away_team_id="chelsea",
               home_score=home_score, away_score=away_score, source=source, source_match_id=source)
    row.update(kw)
    return row


def test_dedup_matches_prefers_higher_priority_source():
    df = pd.DataFrame([_match("openfootball", "FINISHED", 2, 0), _match("thesportsdb", "FINISHED", 2, 0)],
                      columns=MATCH_COLS)
    out = dedup_matches(df)
    assert len(out) == 1
    assert out["source"].iloc[0] == "thesportsdb"


def test_dedup_matches_prefers_finished_over_priority():
    df = pd.DataFrame([_match("thesportsdb", "SCHEDULED"), _match("openfootball", "FINISHED", 1, 1)],
                      columns=MATCH_COLS)
    out = dedup_matches(df)
    assert out["status"].iloc[0] == "FINISHED"
    assert out["source"].iloc[0] == "openfootball"
    assert (out["home_score"].iloc[0], out["away_score"].iloc[0]) == (1, 1)


def test_dedup_matches_keeps_distinct_fixtures():
    other = make_match_id(COMP, SEASON, "chelsea", "arsenal")  # reverse fixture is a different match
    df = pd.DataFrame([_match("thesportsdb", "SCHEDULED"),
                       _match("thesportsdb", "SCHEDULED", match_id=other,
                              home_team_id="chelsea", away_team_id="arsenal")], columns=MATCH_COLS)
    assert len(dedup_matches(df)) == 2


def test_dedup_matches_empty():
    assert dedup_matches(pd.DataFrame(columns=MATCH_COLS)).empty


def test_dedup_teams_merges_attributes_across_sources():
    df = pd.DataFrame([
        dict(team_id="manchester-united", name="Man United", tla="MUN", crest_url=None,
             founded=1878, source="thesportsdb"),
        dict(team_id="manchester-united", name="Manchester United FC", crest_url="https://badge.png",
             founded=None, venue="Old Trafford", source="openfootball"),
    ], columns=TEAM_COLS)
    out = dedup_teams(df)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["name"] == "Manchester United"          # canonical display name
    assert row["crest_url"] == "https://badge.png"     # filled from lower-priority source
    assert row["founded"] == 1878
    assert row["venue"] == "Old Trafford"
    assert row["sources"] == ["openfootball", "thesportsdb"]


def test_dedup_standings_priority():
    base = dict(competition=COMP, season=SEASON, team_id="arsenal", position=1, played=1,
                won=1, draw=0, lost=0, goals_for=1, goals_against=0, goal_difference=1)
    df = pd.DataFrame([{**base, "points": 99, "source": "wikipedia"},
                       {**base, "points": 3, "source": "thesportsdb"}])
    out = dedup_standings(df)
    assert len(out) == 1
    assert out["source"].iloc[0] == "thesportsdb"
    assert out["points"].iloc[0] == 3


def test_build_dataset_end_to_end(openfootball_raw, thesportsdb_raw, wikipedia_raw):
    frames = build_dataset(
        {"openfootball": openfootball_raw, "thesportsdb": thesportsdb_raw, "wikipedia": wikipedia_raw},
        COMP, SEASON,
    )
    teams, matches, standings = frames["teams"], frames["matches"], frames["standings"]

    # 2 fixtures reported by 2 sources each -> 2 canonical matches
    assert len(matches) == 2 and matches["match_id"].is_unique
    # the not-yet-updated openfootball fixture is replaced by TheSportsDB's finished one
    assert set(matches["status"]) == {"FINISHED"}
    assert sorted(teams["team_id"]) == ["brighton", "manchester-united"]
    # TheSportsDB has one table row, Wikipedia fills in the other team
    assert dict(zip(standings["team_id"], standings["source"])) == {
        "manchester-united": "thesportsdb", "brighton": "wikipedia"}
    assert len(frames["standings_all"]) == 3  # 1 + 2
    # every alias resolved to a canonical team
    assert set(frames["aliases"]["team_id"]) <= set(teams["team_id"])


def test_build_dataset_creates_stub_teams_when_teams_endpoint_missing(wikipedia_raw):
    frames = build_dataset({"wikipedia": wikipedia_raw}, COMP, SEASON)
    teams = frames["teams"].set_index("team_id")
    assert set(teams.index) == {"manchester-united", "brighton"}
    assert teams.loc["brighton", "name"] == "Brighton & Hove Albion"
    assert teams.loc["brighton", "sources"] == ["wikipedia"]


def test_build_dataset_ignores_empty_sources(openfootball_raw):
    frames = build_dataset({"openfootball": openfootball_raw, "thesportsdb": {}}, COMP, SEASON)
    assert len(frames["matches"]) == 2
