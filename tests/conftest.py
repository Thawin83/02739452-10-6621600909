import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COMP, SEASON = "PL", 2026


@pytest.fixture
def openfootball_raw():
    return {
        "matches": [
            {"round": "Matchday 1", "date": "2026-08-15", "time": "15:00",
             "team1": "Manchester United FC", "team2": "Brighton & Hove Albion FC",
             "score": {"ht": [1, 0], "ft": [2, 1]}},
            # Not updated yet in this source (TheSportsDB already has the result)
            {"round": "Matchday 2", "date": "2026-08-22", "time": "15:00",
             "team1": "Brighton & Hove Albion FC", "team2": "Manchester United FC"},
        ]
    }


@pytest.fixture
def thesportsdb_raw():
    return {
        "teams": [
            {"idTeam": "133612", "strTeam": "Man United", "strTeamShort": "MUN", "intFormedYear": "1878",
             "strStadium": "Old Trafford", "strBadge": "https://badges/mun.png", "strWebsite": ""},
            {"idTeam": "133619", "strTeam": "Brighton and Hove Albion", "strTeamShort": "BHA",
             "intFormedYear": "1901", "strStadium": "Amex Stadium", "strBadge": "https://badges/bha.png"},
        ],
        "matches": [
            # Same fixture as football-data match 1
            {"idEvent": "9001", "strHomeTeam": "Man United", "strAwayTeam": "Brighton and Hove Albion",
             "intHomeScore": "2", "intAwayScore": "1", "intRound": "1",
             "strTimestamp": "2026-08-15T14:00:00", "strStatus": "Match Finished"},
            # Same fixture as football-data match 2, but this source already has the result
            {"idEvent": "9002", "strHomeTeam": "Brighton and Hove Albion", "strAwayTeam": "Man United",
             "intHomeScore": "0", "intAwayScore": "0", "intRound": "2",
             "strTimestamp": "2026-08-22T14:00:00", "strStatus": "FT"},
        ],
        "standings": [
            {"strTeam": "Man United", "intRank": "1", "intPlayed": "1", "intWin": "1", "intDraw": "0",
             "intLoss": "0", "intGoalsFor": "2", "intGoalsAgainst": "1", "intGoalDifference": "1", "intPoints": "3"},
        ],
    }


@pytest.fixture
def wikipedia_raw():
    return {
        "standings": [
            {"Pos": "1", "Team": "Manchester United (C)", "Pld": "1", "W": "1", "D": "0", "L": "0",
             "GF": "2", "GA": "1", "GD": "+1", "Pts": "3"},
            {"Pos": "2", "Team": "Brighton & Hove Albion[a]", "Pld": "1", "W": "0", "D": "0", "L": "1",
             "GF": "1", "GA": "2", "GD": "−1", "Pts": "0"},
        ]
    }
