"""TheSportsDB v1 JSON API (https://www.thesportsdb.com/free_sports_api).

The free key ("123") is rate limited and caps some list endpoints, which is fine
because this source is a secondary/fallback source.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import build_session, strip_personal_data

log = logging.getLogger(__name__)

BASE_URL = "https://www.thesportsdb.com/api/v1/json"

# competition code -> TheSportsDB league id
LEAGUE_IDS = {
    "PL": 4328,   # English Premier League
    "ELC": 4329,  # English League Championship
    "PD": 4335,   # Spanish La Liga
    "SA": 4332,   # Italian Serie A
    "BL1": 4331,  # German Bundesliga
    "FL1": 4334,  # French Ligue 1
}

# Matchdays per season (double round robin) — used to page through eventsround.php
ROUNDS = {"PL": 38, "ELC": 46, "PD": 38, "SA": 38, "BL1": 34, "FL1": 34}


def season_label(season: int) -> str:
    return f"{season}-{season + 1}"


class TheSportsDBExtractor:
    source = "thesportsdb"

    def __init__(
        self,
        api_key: str = "123",
        competition: str = "PL",
        season: int = 2026,
        session: requests.Session | None = None,
        timeout: int = 30,
        request_delay: float = 3.5,
    ):
        if competition not in LEAGUE_IDS:
            raise ValueError(f"no TheSportsDB league id for competition {competition!r}")
        self.api_key = api_key
        self.league_id = LEAGUE_IDS[competition]
        self.rounds = ROUNDS.get(competition, 38)
        self.season = season
        self.session = session or build_session()
        self.timeout = timeout
        # Free key is limited to ~30 requests/minute and answers 429 + Retry-After: 59 when exceeded.
        self.request_delay = request_delay

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        resp = self.session.get(f"{BASE_URL}/{self.api_key}/{endpoint}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        # Unknown ids/seasons return "null" or {"events": null}
        return resp.json() or {}

    def _in_league(self, team: dict[str, Any]) -> bool:
        league_keys = ["idLeague"] + [f"idLeague{i}" for i in range(2, 8)]
        return str(self.league_id) in {str(team.get(k)) for k in league_keys}

    def extract(self) -> dict[str, list[dict[str, Any]]]:
        label = season_label(self.season)
        # The free key ignores `id` on this endpoint and returns a fixed demo league,
        # so keep only teams that actually belong to the requested league.
        all_teams = self._get("lookup_all_teams.php", id=self.league_id).get("teams") or []
        teams = [t for t in all_teams if self._in_league(t)]
        if len(teams) < len(all_teams):
            log.warning("thesportsdb: dropped %d teams from other leagues (free-key limitation)",
                        len(all_teams) - len(teams))
        events = self._fetch_events(label)
        table = self._get("lookuptable.php", l=self.league_id, s=label).get("table") or []

        log.info("thesportsdb: %d teams, %d events, %d table rows", len(teams), len(events), len(table))
        return {"teams": strip_personal_data(teams), "matches": strip_personal_data(events), "standings": table}

    def _fetch_events(self, label: str) -> list[dict[str, Any]]:
        """eventsseason.php is capped on the free key, so also page through every matchday
        with eventsround.php; events are merged by idEvent."""
        events = {e["idEvent"]: e for e in self._get("eventsseason.php", id=self.league_id, s=label).get("events") or []}
        for rnd in range(1, self.rounds + 1):
            time.sleep(self.request_delay)
            for e in self._get("eventsround.php", id=self.league_id, r=rnd, s=label).get("events") or []:
                events[e["idEvent"]] = e
            if rnd % 10 == 0 or rnd == self.rounds:
                log.info("thesportsdb: round %d/%d fetched, %d events so far", rnd, self.rounds, len(events))
        return list(events.values())
