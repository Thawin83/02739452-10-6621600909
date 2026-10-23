import pandas as pd
import pytest

from conftest import COMP, SEASON
from include.quality import (
    ERROR,
    WARNING,
    check_cross_source_standings,
    check_match_scores,
    check_match_status,
    check_no_self_match,
    check_not_null,
    check_referential,
    check_row_count,
    check_scheduled_without_score,
    check_standings_arithmetic,
    check_standings_points,
    check_standings_positions,
    check_unique,
    check_unmapped_teams,
    has_blocking_failures,
    run_all_checks,
)
from include.transform import ALIAS_COLS, MATCH_COLS, STANDING_COLS, build_dataset


def _matches(rows):
    df = pd.DataFrame(rows, columns=MATCH_COLS)
    for c in ["home_score", "away_score"]:
        df[c] = df[c].astype("Int64")
    return df


def _m(status="FINISHED", hs=1, as_=0, home="arsenal", away="chelsea", mid="m1"):
    return dict(match_id=mid, competition=COMP, season=SEASON, status=status, home_team_id=home,
                away_team_id=away, home_score=hs, away_score=as_, source="thesportsdb")


def _s(team="arsenal", pos=1, w=1, d=0, l=0, gf=2, ga=1, played=None, gd=None, pts=None, source="thesportsdb"):
    return dict(competition=COMP, season=SEASON, team_id=team, position=pos, won=w, draw=d, lost=l,
                played=w + d + l if played is None else played, goals_for=gf, goals_against=ga,
                goal_difference=gf - ga if gd is None else gd, points=3 * w + d if pts is None else pts,
                source=source)


def _standings(rows):
    df = pd.DataFrame(rows, columns=STANDING_COLS)
    for c in STANDING_COLS:
        if c not in ("competition", "team_id", "source"):
            df[c] = df[c].astype("Int64")
    return df


def test_row_count():
    assert check_row_count(pd.DataFrame({"a": [1]}), "x").passed
    r = check_row_count(pd.DataFrame({"a": []}), "x")
    assert not r.passed and r.blocking


def test_not_null_reports_counts_and_sample():
    df = pd.DataFrame({"a": [1, None, 3], "b": ["x", "y", None]})
    r = check_not_null(df, "x", ["a", "b"])
    assert r.failed_rows == 2
    assert r.details["null_counts"] == {"a": 1, "b": 1}
    assert len(r.details["sample"]) == 2


def test_not_null_missing_column_fails():
    r = check_not_null(pd.DataFrame({"a": [1]}), "x", ["a", "zzz"])
    assert not r.passed and r.details["missing_columns"] == ["zzz"]


def test_unique():
    df = pd.DataFrame({"k": [1, 1, 2]})
    r = check_unique(df, "x", ["k"])
    assert r.failed_rows == 2
    assert check_unique(df.drop_duplicates(), "x", ["k"]).passed


def test_match_status():
    assert check_match_status(_matches([_m()])).passed
    assert not check_match_status(_matches([_m(status="TIMED")])).passed


@pytest.mark.parametrize("row, ok", [
    (_m(), True),
    (_m(status="SCHEDULED", hs=None, as_=None), True),
    (_m(hs=None), False),          # finished without score
    (_m(hs=-1), False),            # negative score
])
def test_match_scores(row, ok):
    assert check_match_scores(_matches([row])).passed is ok


def test_scheduled_with_score_is_warning():
    r = check_scheduled_without_score(_matches([_m(status="SCHEDULED", hs=1, as_=0)]))
    assert not r.passed and r.severity == WARNING and not r.blocking


def test_self_match_and_referential():
    assert not check_no_self_match(_matches([_m(away="arsenal")])).passed
    teams = pd.DataFrame({"team_id": ["arsenal"]})
    r = check_referential(_matches([_m()]), teams)
    assert not r.passed and r.failed_rows == 1


def test_standings_arithmetic():
    assert check_standings_arithmetic(_standings([_s()])).passed
    assert not check_standings_arithmetic(_standings([_s(played=5)])).passed
    assert not check_standings_arithmetic(_standings([_s(gd=10)])).passed


def test_standings_points_deduction_is_only_warning():
    r = check_standings_points(_standings([_s(pts=-5)]))
    assert not r.passed and r.severity == WARNING


def test_standings_positions():
    assert check_standings_positions(_standings([_s(), _s(team="chelsea", pos=2)])).passed
    assert not check_standings_positions(_standings([_s(), _s(team="chelsea", pos=1)])).passed


def test_cross_source_flags_only_comparable_mismatches():
    df = _standings([
        _s(team="arsenal", source="thesportsdb"),
        _s(team="arsenal", source="wikipedia", pts=4),                 # same played, diff points -> flag
        _s(team="chelsea", w=2, source="thesportsdb"),
        _s(team="chelsea", w=1, source="wikipedia"),                   # wikipedia lagging -> not flagged
    ])
    r = check_cross_source_standings(df)
    assert r.failed_rows == 1
    assert r.details["sample"][0]["team_id"] == "arsenal"
    assert r.details["lagging_pairs"] == 1


def test_cross_source_single_source_passes():
    assert check_cross_source_standings(_standings([_s()])).passed


def test_unmapped_teams():
    aliases = pd.DataFrame([["Arsenal", "wikipedia", "arsenal"],
                            ["Some New FC", "wikipedia", "some-new"]], columns=ALIAS_COLS)
    r = check_unmapped_teams(aliases)
    assert r.failed_rows == 1 and r.severity == WARNING


def test_run_all_checks_clean_dataset_has_no_blocking(openfootball_raw, thesportsdb_raw, wikipedia_raw):
    frames = build_dataset(
        {"openfootball": openfootball_raw, "thesportsdb": thesportsdb_raw, "wikipedia": wikipedia_raw},
        COMP, SEASON,
    )
    results = run_all_checks(frames)
    assert not has_blocking_failures(results), [r for r in results if r.blocking]
    assert all(r.severity in (ERROR, WARNING) for r in results)


def test_run_all_checks_blocks_on_duplicate_matches(openfootball_raw):
    frames = build_dataset({"openfootball": openfootball_raw}, COMP, SEASON)
    frames["matches"] = pd.concat([frames["matches"], frames["matches"]], ignore_index=True)
    assert has_blocking_failures(run_all_checks(frames))
