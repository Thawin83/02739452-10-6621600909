"""Scrapes the league table from the English Wikipedia season article (requests + BeautifulSoup,
no browser automation).

Used as an independent cross-check for standings (see quality.check_cross_source_standings).
Before every fetch the site's robots.txt is checked for our User-Agent; a disallowed URL is
never requested. Only the club-level league table is parsed (no personal data).
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from . import USER_AGENT, build_session

log = logging.getLogger(__name__)

BASE_URL = "https://en.wikipedia.org/wiki"

WIKI_LEAGUE_NAMES = {
    "PL": "Premier_League",
    "ELC": "EFL_Championship",
    "PD": "La_Liga",
    "SA": "Serie_A",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
}
REQUIRED_HEADERS = {"Pos", "Team", "Pld", "Pts"}
_FOOTNOTE = re.compile(r"\[[^\]]*\]")


def page_title(competition: str, season: int) -> str:
    # e.g. 2026 + PL -> "2026–27_Premier_League" (en dash, as Wikipedia uses)
    return f"{season}–{str(season + 1)[-2:]}_{WIKI_LEAGUE_NAMES[competition]}"


def _cell_text(cell) -> str:
    return _FOOTNOTE.sub("", cell.get_text(" ", strip=True)).strip()


def parse_league_table(html: str) -> list[dict[str, str]]:
    """Return rows of the first wikitable whose header contains Pos/Team/Pld/Pts.

    Cells are mapped by header position. Trailing columns that use rowspan
    (e.g. "Qualification or relegation") may misalign, but they are not used.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table.wikitable"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [_cell_text(c) for c in rows[0].find_all(["th", "td"])]
        if not REQUIRED_HEADERS.issubset(headers):
            continue

        min_cells = headers.index("Pts") + 1
        records = []
        for tr in rows[1:]:
            cells = tr.find_all(["th", "td"])
            if len(cells) < min_cells:
                continue
            record = {h: _cell_text(cells[i]) for i, h in enumerate(headers) if i < len(cells)}
            if record.get("Team"):
                records.append(record)
        if records:
            return records
    return []


class RobotsDisallowedError(PermissionError):
    pass


def check_robots(session: requests.Session, url: str, user_agent: str = USER_AGENT, timeout: int = 30) -> None:
    """Raise RobotsDisallowedError if robots.txt forbids `url` for `user_agent`."""
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    resp = session.get(robots_url, timeout=timeout)
    parser = RobotFileParser(robots_url)
    if resp.status_code in (401, 403):
        parser.disallow_all = True  # same convention as RobotFileParser.read()
    elif resp.ok:
        parser.parse(resp.text.splitlines())
    else:
        parser.allow_all = True  # no robots.txt (e.g. 404) means no restrictions
    if not parser.can_fetch(user_agent, url):
        raise RobotsDisallowedError(f"robots.txt at {robots_url} disallows {url} for {user_agent!r}")
    log.info("robots.txt allows %s", url)


class WikipediaExtractor:
    source = "wikipedia"

    def __init__(
        self,
        competition: str = "PL",
        season: int = 2026,
        session: requests.Session | None = None,
        timeout: int = 30,
    ):
        if competition not in WIKI_LEAGUE_NAMES:
            raise ValueError(f"no Wikipedia article mapping for competition {competition!r}")
        self.url = f"{BASE_URL}/{quote(page_title(competition, season))}"
        self.session = session or build_session()
        self.timeout = timeout

    def extract(self) -> dict[str, list[dict[str, Any]]]:
        check_robots(self.session, self.url, timeout=self.timeout)
        resp = self.session.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        rows = parse_league_table(resp.text)
        if not rows:
            log.warning("no league table found at %s", self.url)
        log.info("wikipedia: %d table rows from %s", len(rows), self.url)
        return {"standings": rows}
