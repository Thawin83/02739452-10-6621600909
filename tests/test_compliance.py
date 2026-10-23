"""PDPA (no personal data), robots.txt and the quarantine path."""
import pytest

from conftest import COMP, SEASON
from include.extractors import PERSONAL_FIELDS, strip_personal_data
from include.extractors.openfootball import OpenFootballExtractor
from include.extractors.wikipedia_scraper import RobotsDisallowedError, WikipediaExtractor, check_robots
from include.quality import has_blocking_failures, run_all_checks
from include.transform import build_dataset, inject_bad_rows


class FakeResponse:
    def __init__(self, body=None, text="", status=200):
        self._body, self.text, self.status_code = body, text, status
        self.ok = 200 <= status < 400

    def json(self):
        return self._body

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                return resp
        raise AssertionError(f"unexpected request {url}")


def test_strip_personal_data_drops_person_fields_only():
    out = strip_personal_data([{"name": "Arsenal FC", "squad": [{"name": "A Player"}], "coach": {"name": "X"}}])
    assert out == [{"name": "Arsenal FC"}]


def test_openfootball_extract_drops_goal_scorers():
    session = FakeSession({
        "/robots.txt": FakeResponse(status=404),
        "2026-27/en.1.json": FakeResponse({"matches": [
            {"round": "Matchday 1", "team1": "Arsenal FC", "team2": "Chelsea FC", "score": {"ft": [1, 0]},
             "goals1": [{"name": "A Player", "minute": 10}], "goals2": []}]}),
    })
    out = OpenFootballExtractor(COMP, SEASON, session=session).extract()
    assert out["matches"] == [{"round": "Matchday 1", "team1": "Arsenal FC", "team2": "Chelsea FC",
                               "score": {"ft": [1, 0]}}]
    assert session.calls[0].endswith("/robots.txt")  # robots.txt is checked first


def test_check_robots_allows_and_blocks():
    session = FakeSession({"/robots.txt": FakeResponse(text="User-agent: *\nDisallow: /w/\nAllow: /wiki/\n")})
    check_robots(session, "https://en.wikipedia.org/wiki/2026%E2%80%9327_Premier_League")
    with pytest.raises(RobotsDisallowedError):
        check_robots(session, "https://en.wikipedia.org/w/index.php?title=x")


def test_check_robots_honours_a_group_for_our_user_agent():
    # A group naming our agent replaces the "*" group entirely (standard robots.txt semantics).
    robots = "User-agent: *\nAllow: /\n\nUser-agent: football-pipeline\nDisallow: /wiki/\n"
    session = FakeSession({"/robots.txt": FakeResponse(text=robots)})
    with pytest.raises(RobotsDisallowedError):
        check_robots(session, "https://en.wikipedia.org/wiki/2026%E2%80%9327_Premier_League")


def test_wikipedia_extractor_stops_before_fetching_a_disallowed_page():
    session = FakeSession({"/robots.txt": FakeResponse(text="User-agent: *\nDisallow: /\n")})
    with pytest.raises(RobotsDisallowedError):
        WikipediaExtractor(COMP, SEASON, session=session).extract()
    assert all(url.endswith("/robots.txt") for url in session.calls)


def test_missing_robots_txt_means_allowed():
    session = FakeSession({"/robots.txt": FakeResponse(status=404),
                           "Premier_League": FakeResponse(text="<html></html>")})
    assert WikipediaExtractor(COMP, SEASON, session=session).extract() == {"standings": []}


def test_inject_bad_rows_sends_run_to_quarantine(openfootball_raw):
    frames = build_dataset({"openfootball": openfootball_raw}, COMP, SEASON)
    assert not has_blocking_failures(run_all_checks(frames))

    results = run_all_checks(inject_bad_rows(frames))
    blocking = {f"{r.entity}.{r.check_name}" for r in results if r.blocking}
    assert {"matches.unique_key", "matches.valid_scores"} <= blocking
