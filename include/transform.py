"""Normalise raw payloads from every source into one canonical schema.

Canonical frames (column lists below):
    teams          one row per canonical team_id (merged across sources)
    matches        one row per match_id (deduplicated across sources)
    standings      one row per (competition, season, team_id) (deduplicated)
    standings_all  standings from every source, kept for cross-source quality checks
    aliases        raw team label per source -> team_id (audit trail for the mapping)
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

import pandas as pd

# Lower number wins when the same entity comes from several sources.
SOURCE_PRIORITY = {"thesportsdb": 0, "openfootball": 1, "wikipedia": 2}

TEAM_COLS = ["team_id", "name", "short_name", "tla", "founded", "venue", "crest_url", "website",
             "source", "source_team_id"]
TEAM_FINAL_COLS = ["team_id", "name", "short_name", "tla", "founded", "venue", "crest_url", "website",
                   "sources"]
MATCH_COLS = ["match_id", "competition", "season", "matchday", "utc_date", "status",
              "home_team_id", "away_team_id", "home_score", "away_score", "source", "source_match_id"]
STANDING_COLS = ["competition", "season", "team_id", "position", "played", "won", "draw", "lost",
                 "goals_for", "goals_against", "goal_difference", "points", "source"]
ALIAS_COLS = ["alias", "source", "team_id"]

STANDING_INT_COLS = ["season", "position", "played", "won", "draw", "lost",
                     "goals_for", "goals_against", "goal_difference", "points"]
FRAME_SCHEMAS: dict[str, tuple[list[str], list[str]]] = {
    "teams": (TEAM_FINAL_COLS, ["founded"]),
    "matches": (MATCH_COLS, ["season", "matchday", "home_score", "away_score"]),
    "standings": (STANDING_COLS, STANDING_INT_COLS),
    "standings_all": (STANDING_COLS, STANDING_INT_COLS),
    "aliases": (ALIAS_COLS, []),
}

MATCH_STATUSES = {"SCHEDULED", "IN_PLAY", "FINISHED", "POSTPONED", "SUSPENDED", "CANCELLED"}

# ---------------------------------------------------------------------------
# Team-name mapping
# ---------------------------------------------------------------------------
# canonical team_id -> (display name, extra aliases). Aliases are compared after
# normalize_team_name(), so "Man Utd", "MAN UTD." and "Manchester United FC" all match.
CANONICAL_TEAMS: dict[str, tuple[str, list[str]]] = {
    "arsenal": ("Arsenal", []),
    "aston-villa": ("Aston Villa", ["villa"]),
    "bournemouth": ("AFC Bournemouth", []),
    "brentford": ("Brentford", []),
    "brighton": ("Brighton & Hove Albion", ["brighton", "brighton hove", "brighton and hove"]),
    "burnley": ("Burnley", []),
    "chelsea": ("Chelsea", []),
    "coventry-city": ("Coventry City", ["coventry"]),
    "crystal-palace": ("Crystal Palace", ["palace"]),
    "everton": ("Everton", []),
    "fulham": ("Fulham", []),
    "hull-city": ("Hull City", ["hull"]),
    "ipswich-town": ("Ipswich Town", ["ipswich"]),
    "leeds-united": ("Leeds United", ["leeds", "leeds utd"]),
    "leicester-city": ("Leicester City", ["leicester"]),
    "liverpool": ("Liverpool", []),
    "luton-town": ("Luton Town", ["luton"]),
    "manchester-city": ("Manchester City", ["man city", "manchester c"]),
    "manchester-united": ("Manchester United", ["man united", "man utd", "manchester utd", "man u"]),
    "middlesbrough": ("Middlesbrough", ["boro"]),
    "newcastle-united": ("Newcastle United", ["newcastle", "newcastle utd"]),
    "norwich-city": ("Norwich City", ["norwich"]),
    "nottingham-forest": ("Nottingham Forest", ["nottm forest", "nottingham", "forest"]),
    "sheffield-united": ("Sheffield United", ["sheffield utd", "sheff utd"]),
    "southampton": ("Southampton", []),
    "sunderland": ("Sunderland", []),
    "tottenham-hotspur": ("Tottenham Hotspur", ["tottenham", "spurs"]),
    "watford": ("Watford", []),
    "west-bromwich-albion": ("West Bromwich Albion", ["west brom", "wba"]),
    "west-ham-united": ("West Ham United", ["west ham", "west ham utd"]),
    "wolverhampton-wanderers": ("Wolverhampton Wanderers", ["wolves", "wolverhampton"]),
}

_DROP_TOKENS = {"fc", "afc", "cf", "sc"}
_FOOTNOTE = re.compile(r"\[[^\]]*\]")
# Wikipedia table markers: (C) champion, (R) relegated, (Q) qualified, (X), (E), (T)...
_STATUS_MARKER = re.compile(r"\(\s*[A-Z]{1,2}\s*\)")


def clean_team_label(name: Any) -> str:
    """Strip footnotes / status markers but keep the label human readable."""
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = _STATUS_MARKER.sub("", _FOOTNOTE.sub("", str(name)))
    return re.sub(r"\s+", " ", s).strip()


def normalize_team_name(name: Any) -> str:
    """Comparable key for a team label: ascii, lower case, no punctuation or club suffixes."""
    s = clean_team_label(name)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(t for t in s.split() if t not in _DROP_TOKENS)


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for team_id, (display, aliases) in CANONICAL_TEAMS.items():
        for alias in [display, team_id.replace("-", " "), *aliases]:
            index[normalize_team_name(alias)] = team_id
    return index


_ALIAS_INDEX = _build_alias_index()


def resolve_team_id(name: Any) -> str:
    """Map any source's team label to a canonical team_id (slug fallback for unknown teams)."""
    key = normalize_team_name(name)
    if not key:
        return ""
    return _ALIAS_INDEX.get(key) or key.replace(" ", "-")


def is_known_team(team_id: str) -> bool:
    return team_id in CANONICAL_TEAMS


def canonical_name(team_id: str) -> str | None:
    entry = CANONICAL_TEAMS.get(team_id)
    return entry[0] if entry else None


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------
_INT_RE = re.compile(r"-?\d+")


def to_int(value: Any) -> int | None:
    """Lenient int parser: handles None/NaN, '+5', unicode minus '−3' / '− 3', '1[a]'."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else int(value)
    # Wikipedia renders negatives as "−" + digits in separate nodes, scraped as "− 4".
    s = re.sub(r"\s+", "", str(value)).replace("−", "-").replace("–", "-").replace("+", "")
    m = _INT_RE.search(s)
    return int(m.group()) if m else None


def to_utc_iso(value: Any) -> str | None:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_match_id(competition: str, season: int, home_id: str, away_id: str) -> str:
    # In a league each (home, away) pair meets exactly once per season, so this key is
    # stable across sources and across reschedules (unlike a date-based key).
    return f"{competition}-{season}-{home_id}-vs-{away_id}"


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


def _finalize(df: pd.DataFrame, cols: list[str], int_cols: list[str]) -> pd.DataFrame:
    df = df.reindex(columns=cols)
    for c in int_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def _frame(rows: list[dict], cols: list[str], int_cols: list[str] = ()) -> pd.DataFrame:
    return _finalize(pd.DataFrame(rows, columns=cols), cols, list(int_cols))


def _alias_frame(names: list[Any], source: str) -> pd.DataFrame:
    rows = []
    for raw in names:
        label = clean_team_label(raw)
        if label:
            rows.append({"alias": label, "source": source, "team_id": resolve_team_id(label)})
    return _frame(rows, ALIAS_COLS).drop_duplicates(["alias", "source"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-source transforms: raw payload -> canonical frames
# ---------------------------------------------------------------------------
# Kick-off times in openfootball are local to the league's country.
LEAGUE_TIMEZONES = {"PL": "Europe/London", "ELC": "Europe/London", "PD": "Europe/Madrid",
                    "SA": "Europe/Rome", "BL1": "Europe/Berlin", "FL1": "Europe/Paris"}


def local_to_utc_iso(date: Any, time: Any, tz: str) -> str | None:
    ts = pd.to_datetime(f"{date} {time or '00:00'}", errors="coerce")
    return None if pd.isna(ts) else ts.tz_localize(tz).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def transform_openfootball(raw: dict[str, Any], competition: str, season: int) -> dict[str, pd.DataFrame]:
    src = "openfootball"
    tz = LEAGUE_TIMEZONES.get(competition, "UTC")
    names: list[Any] = []
    matches = []
    for m in raw.get("matches") or []:
        home, away = m.get("team1"), m.get("team2")
        if not home or not away:
            continue
        names += [home, away]
        home_id, away_id = resolve_team_id(home), resolve_team_id(away)
        # "score" is either {"ht": [..], "ft": [h, a]} or the short form [h, a] (full time only)
        score = m.get("score")
        full_time = (score.get("ft") if isinstance(score, dict) else score) or [None, None]
        played = full_time[0] is not None and full_time[1] is not None
        matches.append({
            "match_id": make_match_id(competition, season, home_id, away_id),
            "competition": competition, "season": season, "matchday": to_int(m.get("round")),
            "utc_date": local_to_utc_iso(m.get("date"), m.get("time"), tz),
            "status": "FINISHED" if played else "SCHEDULED",
            "home_team_id": home_id, "away_team_id": away_id,
            "home_score": full_time[0], "away_score": full_time[1],
            "source": src, "source_match_id": f"{m.get('date')}:{home_id}:{away_id}",
        })

    # The file only names clubs, so teams carry just the label as seen in this source.
    teams = [{"team_id": resolve_team_id(n), "name": clean_team_label(n), "source": src, "source_team_id": None}
             for n in dict.fromkeys(names)]
    return {
        "teams": _frame(teams, TEAM_COLS, ["founded"]),
        "matches": _frame(matches, MATCH_COLS, FRAME_SCHEMAS["matches"][1]),
        "aliases": _alias_frame(names, src),
    }


_TSDB_STATUS = {
    "match finished": "FINISHED", "ft": "FINISHED", "aet": "FINISHED", "pen": "FINISHED",
    "not started": "SCHEDULED", "ns": "SCHEDULED", "tbd": "SCHEDULED",
    "postponed": "POSTPONED", "pst": "POSTPONED",
    "cancelled": "CANCELLED", "canc": "CANCELLED", "abandoned": "CANCELLED", "abd": "CANCELLED",
    "suspended": "SUSPENDED", "susp": "SUSPENDED",
    "1h": "IN_PLAY", "2h": "IN_PLAY", "ht": "IN_PLAY", "live": "IN_PLAY", "et": "IN_PLAY",
}


def _tsdb_status(event: dict[str, Any], home_score: int | None, away_score: int | None) -> str:
    raw = str(event.get("strStatus") or "").strip().lower()
    if raw in _TSDB_STATUS:
        return _TSDB_STATUS[raw]
    return "FINISHED" if home_score is not None and away_score is not None else "SCHEDULED"


def transform_thesportsdb(raw: dict[str, Any], competition: str, season: int) -> dict[str, pd.DataFrame]:
    src = "thesportsdb"
    names: list[Any] = []

    teams = []
    for t in raw.get("teams") or []:
        if not t.get("strTeam"):
            continue
        names.append(t["strTeam"])
        teams.append({
            "team_id": resolve_team_id(t["strTeam"]), "name": t["strTeam"],
            "short_name": t.get("strTeamAlternate") or None, "tla": t.get("strTeamShort") or None,
            "founded": to_int(t.get("intFormedYear")), "venue": t.get("strStadium") or None,
            "crest_url": t.get("strBadge") or t.get("strTeamBadge") or None,
            "website": t.get("strWebsite") or None,
            "source": src, "source_team_id": str(t.get("idTeam")),
        })

    matches = []
    for e in raw.get("matches") or []:
        home, away = e.get("strHomeTeam"), e.get("strAwayTeam")
        if not home or not away:
            continue
        names += [home, away]
        home_id, away_id = resolve_team_id(home), resolve_team_id(away)
        hs, as_ = to_int(e.get("intHomeScore")), to_int(e.get("intAwayScore"))
        # strTimestamp is UTC without offset; fall back to date + time.
        when = e.get("strTimestamp") or " ".join(filter(None, [e.get("dateEvent"), e.get("strTime")]))
        matches.append({
            "match_id": make_match_id(competition, season, home_id, away_id),
            "competition": competition, "season": season, "matchday": to_int(e.get("intRound")),
            "utc_date": to_utc_iso(when) if when else None, "status": _tsdb_status(e, hs, as_),
            "home_team_id": home_id, "away_team_id": away_id, "home_score": hs, "away_score": as_,
            "source": src, "source_match_id": str(e.get("idEvent")),
        })

    standings = []
    for row in raw.get("standings") or []:
        name = row.get("strTeam") or row.get("name")
        if not name:
            continue
        names.append(name)
        standings.append({
            "competition": competition, "season": season, "team_id": resolve_team_id(name),
            "position": to_int(row.get("intRank")), "played": to_int(row.get("intPlayed")),
            "won": to_int(row.get("intWin")), "draw": to_int(row.get("intDraw")),
            "lost": to_int(row.get("intLoss")), "goals_for": to_int(row.get("intGoalsFor")),
            "goals_against": to_int(row.get("intGoalsAgainst")),
            "goal_difference": to_int(row.get("intGoalDifference")),
            "points": to_int(row.get("intPoints")), "source": src,
        })

    return {
        "teams": _frame(teams, TEAM_COLS, ["founded"]),
        "matches": _frame(matches, MATCH_COLS, FRAME_SCHEMAS["matches"][1]),
        "standings": _frame(standings, STANDING_COLS, STANDING_INT_COLS),
        "aliases": _alias_frame(names, src),
    }


def transform_wikipedia(raw: dict[str, Any], competition: str, season: int) -> dict[str, pd.DataFrame]:
    src = "wikipedia"
    names: list[Any] = []
    standings = []
    for row in raw.get("standings") or []:
        label = clean_team_label(row.get("Team"))
        if not label:
            continue
        names.append(label)
        standings.append({
            "competition": competition, "season": season, "team_id": resolve_team_id(label),
            "position": to_int(row.get("Pos")), "played": to_int(row.get("Pld")),
            "won": to_int(row.get("W")), "draw": to_int(row.get("D")), "lost": to_int(row.get("L")),
            "goals_for": to_int(row.get("GF")), "goals_against": to_int(row.get("GA")),
            "goal_difference": to_int(row.get("GD")), "points": to_int(row.get("Pts")), "source": src,
        })
    return {
        "standings": _frame(standings, STANDING_COLS, STANDING_INT_COLS),
        "aliases": _alias_frame(names, src),
    }


TRANSFORMERS: dict[str, Callable[[dict[str, Any], str, int], dict[str, pd.DataFrame]]] = {
    "thesportsdb": transform_thesportsdb,
    "openfootball": transform_openfootball,
    "wikipedia": transform_wikipedia,
}

# ---------------------------------------------------------------------------
# Deduplication / cross-source merge
# ---------------------------------------------------------------------------


def _priority(df: pd.DataFrame) -> pd.Series:
    return df["source"].map(SOURCE_PRIORITY).fillna(len(SOURCE_PRIORITY)).astype(int)


def dedup_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per match_id. A FINISHED row beats a non-finished one (a source that already
    has the result is fresher); otherwise the higher-priority source wins."""
    if matches.empty:
        return _finalize(matches, MATCH_COLS, FRAME_SCHEMAS["matches"][1])
    d = matches.assign(_finished=(matches["status"] == "FINISHED").astype(int), _prio=_priority(matches))
    d = d.sort_values(["match_id", "_finished", "_prio"], ascending=[True, False, True], kind="stable")
    d = d.drop_duplicates("match_id", keep="first")
    return _finalize(d, MATCH_COLS, FRAME_SCHEMAS["matches"][1])


def dedup_standings(standings: pd.DataFrame) -> pd.DataFrame:
    if standings.empty:
        return _finalize(standings, STANDING_COLS, STANDING_INT_COLS)
    d = standings.assign(_prio=_priority(standings))
    d = d.sort_values(["competition", "season", "_prio", "position"], kind="stable")
    d = d.drop_duplicates(["competition", "season", "team_id"], keep="first")
    return _finalize(d, STANDING_COLS, STANDING_INT_COLS)


def dedup_teams(teams: pd.DataFrame) -> pd.DataFrame:
    """Merge team attributes across sources: each column takes the first non-null value in
    source-priority order, so e.g. a missing venue from one source is filled by another."""
    if teams.empty:
        return _finalize(_empty(TEAM_FINAL_COLS), TEAM_FINAL_COLS, ["founded"])
    d = teams.assign(_prio=_priority(teams)).sort_values(["team_id", "_prio"], kind="stable")
    attrs = ["name", "short_name", "tla", "founded", "venue", "crest_url", "website"]
    merged = d.groupby("team_id", sort=True)[attrs].first()
    merged["sources"] = d.groupby("team_id")["source"].agg(lambda s: sorted(set(s)))
    merged = merged.reset_index()
    merged["name"] = [canonical_name(tid) or n for tid, n in zip(merged["team_id"], merged["name"])]
    return _finalize(merged, TEAM_FINAL_COLS, ["founded"])


def ensure_team_coverage(teams: pd.DataFrame, aliases: pd.DataFrame,
                         matches: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
    """Add stub rows for team_ids referenced by matches/standings but missing from `teams`
    (e.g. a source's teams endpoint failed), so foreign keys hold on load."""
    referenced = set(matches["home_team_id"]) | set(matches["away_team_id"]) | set(standings["team_id"])
    missing = sorted(referenced - set(teams["team_id"]) - {"", None})
    if not missing:
        return teams
    stubs = []
    for tid in missing:
        seen = aliases[aliases["team_id"] == tid]
        name = canonical_name(tid) or (seen["alias"].iloc[0] if not seen.empty else tid)
        stubs.append({"team_id": tid, "name": name, "sources": sorted(set(seen["source"]))})
    stub_df = _finalize(pd.DataFrame(stubs), TEAM_FINAL_COLS, ["founded"])
    combined = stub_df if teams.empty else pd.concat([teams, stub_df], ignore_index=True)
    return _finalize(combined.sort_values("team_id"), TEAM_FINAL_COLS, ["founded"])


def _concat(parts: list[dict[str, pd.DataFrame]], name: str, cols: list[str]) -> pd.DataFrame:
    frames = [p[name] for p in parts if name in p and not p[name].empty]
    return pd.concat(frames, ignore_index=True) if frames else _empty(cols)


def build_dataset(raw_by_source: dict[str, dict[str, Any]], competition: str, season: int) -> dict[str, pd.DataFrame]:
    """raw_by_source: {source: {entity: [records]}} -> canonical frames (see module docstring)."""
    parts = [TRANSFORMERS[src](payload, competition, season)
             for src, payload in raw_by_source.items() if src in TRANSFORMERS and payload]

    aliases = _concat(parts, "aliases", ALIAS_COLS).drop_duplicates(["alias", "source"])
    matches = dedup_matches(_concat(parts, "matches", MATCH_COLS))
    standings_all = _finalize(_concat(parts, "standings", STANDING_COLS), STANDING_COLS, STANDING_INT_COLS)
    standings = dedup_standings(standings_all)
    teams = dedup_teams(_concat(parts, "teams", TEAM_COLS))
    teams = ensure_team_coverage(teams, aliases, matches, standings)

    return {
        "teams": teams,
        "matches": matches,
        "standings": standings,
        "standings_all": standings_all,
        "aliases": _finalize(aliases, ALIAS_COLS, []),
    }


# ---------------------------------------------------------------------------
# Staging (hand-off between Airflow tasks)
# ---------------------------------------------------------------------------


def save_frames(frames: dict[str, pd.DataFrame], directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        records = df.astype(object).where(df.notna(), None).to_dict("records")
        with open(directory / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, default=str)


def load_frames(directory: str | Path) -> dict[str, pd.DataFrame]:
    directory = Path(directory)
    frames = {}
    for name, (cols, int_cols) in FRAME_SCHEMAS.items():
        path = directory / f"{name}.json"
        records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        frames[name] = _finalize(pd.DataFrame(records, columns=cols), cols, int_cols)
    return frames


def inject_bad_rows(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Demo only (DAG param simulate_bad_data): add a duplicate match and a negative score so the
    blocking quality checks fail and the DAG takes the quarantine branch."""
    frames = dict(frames)
    matches = frames["matches"]
    if matches.empty:
        return frames
    bad = matches.head(1).copy()
    bad["home_score"] = pd.array([-1], dtype="Int64")
    bad["status"] = "FINISHED"
    frames["matches"] = _finalize(pd.concat([matches, bad], ignore_index=True), MATCH_COLS, FRAME_SCHEMAS["matches"][1])
    return frames
