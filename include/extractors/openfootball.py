"""openfootball/football.json — public-domain fixtures & results on GitHub
(https://github.com/openfootball/football.json). No API key, no rate limit.

One JSON file per league and season, e.g. 2026-27/en.1.json:
    {"name": ..., "matches": [{"round": "Matchday 1", "date": "2026-08-21", "time": "20:00",
                               "team1": "Arsenal FC", "team2": "...", "score": {"ht": [..], "ft": [2, 0]}}]}
Kick-off times are local to the league's country (see transform.LEAGUE_TIMEZONES).
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from . import build_session, strip_personal_data
from .wikipedia_scraper import check_robots

log = logging.getLogger(__name__)

BASE_URL = "https://raw.githubusercontent.com/openfootball/football.json/master"

# competition code -> openfootball file name
LEAGUE_FILES = {"PL": "en.1", "ELC": "en.2", "PD": "es.1", "SA": "it.1", "BL1": "de.1", "FL1": "fr.1"}


def season_folder(season: int) -> str:
    return f"{season}-{str(season + 1)[-2:]}"  # 2026 -> "2026-27"


class OpenFootballExtractor:
    source = "openfootball"

    def __init__(
        self,
        competition: str = "PL",
        season: int = 2026,
        session: requests.Session | None = None,
        timeout: int = 30,
    ):
        if competition not in LEAGUE_FILES:
            raise ValueError(f"no openfootball file for competition {competition!r}")
        self.url = f"{BASE_URL}/{season_folder(season)}/{LEAGUE_FILES[competition]}.json"
        self.session = session or build_session()
        self.timeout = timeout

    def extract(self) -> dict[str, list[dict[str, Any]]]:
        check_robots(self.session, self.url, timeout=self.timeout)
        resp = self.session.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        matches = resp.json().get("matches") or []
        log.info("openfootball: %d matches from %s", len(matches), self.url)
        # goal scorers ("goals1"/"goals2") are personal data -> dropped (PDPA)
        return {"matches": strip_personal_data(matches)}
