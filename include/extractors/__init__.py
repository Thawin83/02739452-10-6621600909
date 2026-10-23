"""Source extractors.

Every extractor exposes ``extract() -> dict[entity, list[raw_record]]`` and returns
payloads untouched; normalisation happens in ``include.transform``.
"""
from __future__ import annotations

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "football-pipeline/1.0 (educational data pipeline)"
SOURCES = ("thesportsdb", "openfootball", "wikipedia")

# PDPA: fields that identify natural persons (players, coaches, referees, staff) are dropped
# before anything is stored, including the raw landing table. Only club/match data is kept.
PERSONAL_FIELDS = frozenset({
    "squad", "coach", "staff", "referees", "players", "lineups", "goals", "goals1", "goals2", "bookings",
    "substitutions",
    "strReferee", "strManager", "strPlayer", "strHomeLineupGoalkeeper", "strHomeLineupDefense",
    "strHomeLineupMidfield", "strHomeLineupForward", "strHomeLineupSubstitutes", "strHomeGoalDetails",
    "strHomeRedCards", "strHomeYellowCards", "strAwayLineupGoalkeeper", "strAwayLineupDefense",
    "strAwayLineupMidfield", "strAwayLineupForward", "strAwayLineupSubstitutes", "strAwayGoalDetails",
    "strAwayRedCards", "strAwayYellowCards",
})


def strip_personal_data(records: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k not in PERSONAL_FIELDS} for r in records]


def build_session(total_retries: int = 4, backoff: float = 2.0) -> requests.Session:
    """HTTP session that retries on rate limits (429) and transient 5xx errors."""
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_extractor(source: str, competition: str, season: int):
    if source == "thesportsdb":
        from .thesportsdb import TheSportsDBExtractor

        return TheSportsDBExtractor(os.getenv("THESPORTSDB_API_KEY", "123"), competition, season)
    if source == "openfootball":
        from .openfootball import OpenFootballExtractor

        return OpenFootballExtractor(competition, season)
    if source == "wikipedia":
        from .wikipedia_scraper import WikipediaExtractor

        return WikipediaExtractor(competition, season)
    raise ValueError(f"unknown source: {source}")
