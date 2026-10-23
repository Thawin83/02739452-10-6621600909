"""Data quality checks on the canonical frames produced by include.transform.

severity="error"   -> blocks the load (the DAG's quality_checks task fails)
severity="warning" -> recorded in football.dq_results and shown on the dashboard only
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from include.transform import MATCH_STATUSES, is_known_team

ERROR = "error"
WARNING = "warning"


@dataclass
class CheckResult:
    check_name: str
    entity: str
    severity: str
    passed: bool
    failed_rows: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity == ERROR and not self.passed


def _sample(df: pd.DataFrame, n: int = 5) -> list[dict[str, Any]]:
    return json.loads(df.head(n).to_json(orient="records", date_format="iso", default_handler=str))


def _result(name: str, entity: str, severity: str, failed: pd.DataFrame, **details: Any) -> CheckResult:
    if not failed.empty:
        details["sample"] = _sample(failed)
    return CheckResult(name, entity, severity, failed.empty, len(failed), details)


def _mask(series: pd.Series) -> pd.Series:
    """Nullable boolean -> plain bool (NA counts as 'not failing')."""
    return series.fillna(False).astype(bool)


# ---------------------------------------------------------------------------
# Generic checks
# ---------------------------------------------------------------------------


def check_row_count(df: pd.DataFrame, entity: str, min_rows: int = 1, severity: str = ERROR) -> CheckResult:
    ok = len(df) >= min_rows
    return CheckResult("row_count", entity, severity, ok, 0 if ok else 1, {"rows": len(df), "min_rows": min_rows})


def check_not_null(df: pd.DataFrame, entity: str, cols: list[str], severity: str = ERROR) -> CheckResult:
    absent = [c for c in cols if c not in df.columns]
    if absent:
        return CheckResult("not_null", entity, severity, False, len(df), {"missing_columns": absent})
    nulls = df[cols].isna()
    failed = df[nulls.any(axis=1)]
    return _result("not_null", entity, severity, failed,
                   null_counts={c: int(n) for c, n in nulls.sum().items() if n})


def check_unique(df: pd.DataFrame, entity: str, key_cols: list[str], severity: str = ERROR) -> CheckResult:
    failed = df[df.duplicated(key_cols, keep=False)]
    return _result("unique_key", entity, severity, failed, key=key_cols)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


def check_match_status(matches: pd.DataFrame) -> CheckResult:
    failed = matches[~matches["status"].isin(MATCH_STATUSES)]
    return _result("valid_status", "matches", ERROR, failed, allowed=sorted(MATCH_STATUSES))


def check_match_scores(matches: pd.DataFrame) -> CheckResult:
    """FINISHED matches need both scores; no score may be negative."""
    finished = matches["status"] == "FINISHED"
    missing = finished & (matches["home_score"].isna() | matches["away_score"].isna())
    negative = _mask(matches["home_score"] < 0) | _mask(matches["away_score"] < 0)
    return _result("valid_scores", "matches", ERROR, matches[missing | negative])


def check_scheduled_without_score(matches: pd.DataFrame) -> CheckResult:
    not_played = matches["status"].isin(["SCHEDULED", "POSTPONED", "CANCELLED"])
    has_score = matches["home_score"].notna() | matches["away_score"].notna()
    return _result("unplayed_has_score", "matches", WARNING, matches[not_played & has_score])


def check_no_self_match(matches: pd.DataFrame) -> CheckResult:
    return _result("home_ne_away", "matches", ERROR, matches[matches["home_team_id"] == matches["away_team_id"]])


def check_referential(matches: pd.DataFrame, teams: pd.DataFrame) -> CheckResult:
    known = set(teams["team_id"])
    failed = matches[~matches["home_team_id"].isin(known) | ~matches["away_team_id"].isin(known)]
    return _result("team_fk", "matches", ERROR, failed)


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


def check_standings_arithmetic(standings: pd.DataFrame) -> CheckResult:
    """played = W + D + L and GD = GF - GA must always hold."""
    bad_played = _mask(standings["played"] != standings["won"] + standings["draw"] + standings["lost"])
    bad_gd = _mask(standings["goal_difference"] != standings["goals_for"] - standings["goals_against"])
    return _result("standings_arithmetic", "standings", ERROR, standings[bad_played | bad_gd])


def check_standings_points(standings: pd.DataFrame) -> CheckResult:
    """points = 3W + D. Warning only: point deductions legitimately break this."""
    bad = _mask(standings["points"] != 3 * standings["won"] + standings["draw"])
    return _result("standings_points_formula", "standings", WARNING, standings[bad])


def check_standings_positions(standings: pd.DataFrame) -> CheckResult:
    """Positions within each competition/season should be exactly 1..n."""
    failed = []
    for _, grp in standings.groupby(["competition", "season"]):
        expected = set(range(1, len(grp) + 1))
        if set(grp["position"].dropna().astype(int)) != expected:
            failed.append(grp)
    failed_df = pd.concat(failed) if failed else standings.iloc[0:0]
    return _result("standings_positions", "standings", WARNING, failed_df)


def check_cross_source_standings(standings_all: pd.DataFrame) -> CheckResult:
    """Compare sources for the same team. Only rows with equal `played` are comparable:
    a different games-played count just means one source has not updated yet."""
    if standings_all.empty or standings_all["source"].nunique() < 2:
        return CheckResult("cross_source_points", "standings", WARNING, True,
                           details={"note": "fewer than two sources"})
    keys = ["competition", "season", "team_id"]
    base = standings_all.sort_values("source").drop_duplicates(keys + ["source"])
    pairs = base.merge(base, on=keys, suffixes=("_a", "_b"))
    pairs = pairs[pairs["source_a"] < pairs["source_b"]]
    comparable = _mask(pairs["played_a"] == pairs["played_b"])
    mismatch = comparable & _mask(pairs["points_a"] != pairs["points_b"])
    failed = pairs.loc[mismatch, keys + ["source_a", "points_a", "source_b", "points_b", "played_a"]]
    return _result("cross_source_points", "standings", WARNING, failed,
                   compared_pairs=int(comparable.sum()), lagging_pairs=int((~comparable).sum()))


# ---------------------------------------------------------------------------
# Team mapping
# ---------------------------------------------------------------------------


def check_unmapped_teams(aliases: pd.DataFrame) -> CheckResult:
    """Raw labels that fell back to a slug: add them to transform.CANONICAL_TEAMS."""
    failed = aliases[~aliases["team_id"].map(is_known_team).astype(bool)]
    return _result("unmapped_team_names", "teams", WARNING, failed)


# ---------------------------------------------------------------------------


def run_all_checks(frames: dict[str, pd.DataFrame]) -> list[CheckResult]:
    teams, matches = frames["teams"], frames["matches"]
    standings, standings_all = frames["standings"], frames["standings_all"]
    aliases = frames["aliases"]

    return [
        check_row_count(teams, "teams"),
        check_not_null(teams, "teams", ["team_id", "name"]),
        check_unique(teams, "teams", ["team_id"]),
        check_unmapped_teams(aliases),

        check_row_count(matches, "matches"),
        check_not_null(matches, "matches", ["match_id", "competition", "season", "status",
                                            "home_team_id", "away_team_id", "source"]),
        check_unique(matches, "matches", ["match_id"]),
        check_match_status(matches),
        check_match_scores(matches),
        check_scheduled_without_score(matches),
        check_no_self_match(matches),
        check_referential(matches, teams),

        check_row_count(standings, "standings", severity=WARNING),
        check_not_null(standings, "standings", ["competition", "season", "team_id", "source"]),
        check_unique(standings, "standings", ["competition", "season", "team_id"]),
        check_standings_arithmetic(standings),
        check_standings_points(standings),
        check_standings_positions(standings),
        check_cross_source_standings(standings_all),
    ]


def has_blocking_failures(results: list[CheckResult]) -> bool:
    return any(r.blocking for r in results)
