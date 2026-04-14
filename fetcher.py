"""
Auto-fetch match data from ESPN (soccer + NBA) — no API key needed.

Usage:
  /fetch Arsenal vs Bournemouth EPL
  /fetch Lakers vs Warriors NBA
  /fetch Barcelona vs Atletico La Liga
"""

import httpx
import asyncio
import re
import unicodedata
from typing import Optional
from datetime import datetime, timezone

# ── League map ────────────────────────────────────────────────────────────────
SOCCER_LEAGUES = {
    "epl": "eng.1", "premier league": "eng.1", "england": "eng.1",
    "la liga": "esp.1", "laliga": "esp.1", "spain": "esp.1",
    "serie a": "ita.1", "seriea": "ita.1", "italy": "ita.1",
    "bundesliga": "ger.1", "germany": "ger.1",
    "ligue 1": "fra.1", "ligue1": "fra.1", "france": "fra.1",
    "ucl": "uefa.champions", "champions": "uefa.champions",
    "champions league": "uefa.champions", "uefa": "uefa.champions",
    "eredivisie": "ned.1", "netherlands": "ned.1",
}

UCL_CODES = {"uefa.champions"}

# Common team name aliases for search
SOCCER_ALIASES = {
    "psg": "paris saint-germain", "paris": "paris saint-germain",
    "atletico": "atletico madrid", "atletico madrid": "atletico madrid",
    "man utd": "manchester united", "man united": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton",
    "inter": "internazionale", "inter milan": "internazionale",
    "ac milan": "ac milan", "milan": "ac milan",
    "bvb": "borussia dortmund", "dortmund": "borussia dortmund",
    "rb leipzig": "rb leipzig", "leipzig": "rb leipzig",
    "ajax": "ajax amsterdam",
    "benfica": "sl benfica",
    "porto": "fc porto",
    "celtic": "celtic fc",
    "real madrid": "real madrid", "real": "real madrid",
    "barca": "barcelona", "fcb": "barcelona",
    "juve": "juventus",
    "roma": "as roma",
    "napoli": "ssc napoli",
    "leverkusen": "bayer leverkusen",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "application/json",
}

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get(url: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _get_score(competitor: dict) -> int:
    score = competitor.get("score", 0)
    if isinstance(score, dict):
        return int(float(score.get("value", 0) or 0))
    return int(float(score or 0))


def _normalize(name: str) -> str:
    """Lowercase, strip accents, remove punctuation for fuzzy matching."""
    # Strip accents: é→e, ó→o, ü→u etc.
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", ascii_str.lower().strip())


def _team_match(query: str, candidate: str) -> bool:
    q = _normalize(query)
    c = _normalize(candidate)
    # exact or one contains the other
    return q == c or q in c or c in q or any(
        w in c for w in q.split() if len(w) > 3
    )


# ── Soccer fetcher ────────────────────────────────────────────────────────────

async def _soccer_teams(league_code: str) -> list:
    url = f"{ESPN_BASE}/soccer/{league_code}/teams"
    data = await _get(url)
    return data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])


async def _find_soccer_team(name: str, league_code: str) -> Optional[dict]:
    # Apply alias first
    resolved = SOCCER_ALIASES.get(name.lower().strip(), name)
    teams = await _soccer_teams(league_code)
    for t in teams:
        team = t.get("team", {})
        if _team_match(resolved, team.get("displayName", "")) or \
           _team_match(resolved, team.get("shortDisplayName", "")) or \
           _team_match(resolved, team.get("name", "")) or \
           _team_match(name, team.get("displayName", "")) or \
           _team_match(name, team.get("shortDisplayName", "")):
            return team
    return None


async def _soccer_team_schedule(team_id: str, league_code: str) -> list:
    url = f"{ESPN_BASE}/soccer/{league_code}/teams/{team_id}/schedule"
    data = await _get(url)
    events = data.get("events", [])
    return events


async def _extract_soccer_form(events: list, team_id: str, n: int = 6) -> list:
    """Get last n completed results for team."""
    results = []
    for ev in reversed(events):
        if len(results) >= n:
            break
        comp = ev.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("completed", False)
        if not status:
            continue
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        home_score = _get_score(home)
        away_score = _get_score(away)
        home_id    = home.get("team", {}).get("id", "")
        # Store from perspective of fetched team (always show as home_score-away_score)
        if str(home_id) == str(team_id):
            results.append((home_score, away_score, "home"))
        else:
            results.append((away_score, home_score, "away"))
    return results


def _h2h_from_schedules(events_a: list, team_a_id: str, team_b_id: str) -> list:
    """Find H2H games between two teams from team A's schedule."""
    h2h = []
    for ev in reversed(events_a):
        comp = ev.get("competitions", [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed", False):
            continue
        competitors = comp.get("competitors", [])
        ids = {c.get("team", {}).get("id", "") for c in competitors}
        if str(team_a_id) not in ids or str(team_b_id) not in ids:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home and away:
            h2h.append((_get_score(home), _get_score(away)))
        if len(h2h) >= 6:
            break
    return h2h


async def _soccer_injuries(team_id: str, league_code: str) -> list:
    try:
        url = f"{ESPN_BASE}/soccer/{league_code}/teams/{team_id}/injuries"
        data = await _get(url)
        injured = []
        for item in data.get("injuries", [])[:5]:
            athlete = item.get("athlete", {})
            status  = item.get("status", "")
            name    = athlete.get("shortName", athlete.get("displayName", ""))
            if name:
                injured.append(f"{name} ({status})")
        return injured
    except Exception:
        return []


async def fetch_soccer(home_name: str, away_name: str, league: str) -> str:
    league_key  = league.lower().strip()
    league_code = SOCCER_LEAGUES.get(league_key, "eng.1")
    league_disp = league.upper()

    try:
        # Find teams
        home_team, away_team = await asyncio.gather(
            _find_soccer_team(home_name, league_code),
            _find_soccer_team(away_name, league_code),
        )

        if not home_team:
            return f"❌ Could not find '{home_name}' in {league_disp}. Check team name."
        if not away_team:
            return f"❌ Could not find '{away_name}' in {league_disp}. Check team name."

        home_id = home_team["id"]
        away_id = away_team["id"]

        # Fetch schedules + injuries in parallel
        home_sched, away_sched, home_inj, away_inj = await asyncio.gather(
            _soccer_team_schedule(home_id, league_code),
            _soccer_team_schedule(away_id, league_code),
            _soccer_injuries(home_id, league_code),
            _soccer_injuries(away_id, league_code),
        )

        # H2H from home team's schedule
        h2h = _h2h_from_schedules(home_sched, home_id, away_id)
        # If less than 3 found, try from away team's schedule
        if len(h2h) < 3:
            h2h2 = _h2h_from_schedules(away_sched, away_id, home_id)
            h2h2_flipped = [(b, a) for a, b in h2h2]
            # Merge unique
            existing = set(map(tuple, h2h))
            for game in h2h2_flipped:
                if game not in existing:
                    h2h.append(list(game))
                    existing.add(game)

        # Recent form
        home_form = await _extract_soccer_form(home_sched, home_id, 5)
        away_form = await _extract_soccer_form(away_sched, away_id, 5)

    except Exception as e:
        return f"❌ Fetch error: {e}"

    # ── Format output ──────────────────────────────────────────────────────────
    h2h_str  = ", ".join(f"{a}-{b}" for a, b in h2h) if h2h else "N/A"
    home_inj_str = ", ".join(home_inj) if home_inj else "none"
    away_inj_str = ", ".join(away_inj) if away_inj else "none"

    def form_str(form):
        return " | ".join(f"{h}-{a}" for h, a, _ in form) if form else "N/A"

    is_ucl  = league_code in UCL_CODES
    ucl_str = "knockout" if is_ucl else "no"

    return (
        f"✅ *Data fetched! Add odds then copy & send /soccer*\n\n"
        f"📋 *Recent form:*\n"
        f"  {home_team['displayName']}: `{form_str(home_form)}`\n"
        f"  {away_team['displayName']}: `{form_str(away_form)}`\n\n"
        f"```\n"
        f"/soccer\n"
        f"{home_team['displayName']} vs {away_team['displayName']}\n"
        f"{league_disp}\n"
        f"H2H: {h2h_str}\n"
        f"Home inj: [CHECK & ADD MANUALLY]\n"
        f"Away inj: [CHECK & ADD MANUALLY]\n"
        f"Relegation: none\n"
        f"UCL: {ucl_str}\n"
        f"Fwd: none\n"
        f"\n"
        f"[PASTE ODDS BELOW]\n"
        f"W1:  X:  W2:\n"
        f"BTTS+:  BTTS-:\n"
        f"O2.5:  U2.5:\n"
        f"Bank: [your bankroll]\n"
        f"```"
    )


# ── NBA fetcher ───────────────────────────────────────────────────────────────

NBA_TEAM_ALIASES = {
    "la lakers": "los angeles lakers", "lal": "los angeles lakers",
    "la clippers": "los angeles clippers", "lac": "los angeles clippers",
    "gsw": "golden state warriors", "warriors": "golden state warriors",
    "okc": "oklahoma city thunder", "thunder": "oklahoma city thunder",
    "ny knicks": "new york knicks", "knicks": "new york knicks",
    "sa spurs": "san antonio spurs", "spurs": "san antonio spurs",
    "nola": "new orleans pelicans", "pelicans": "new orleans pelicans",
    "phx": "phoenix suns", "suns": "phoenix suns",
}


async def _nba_teams() -> list:
    url = f"{ESPN_BASE}/basketball/nba/teams"
    data = await _get(url)
    return data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])


async def _find_nba_team(name: str) -> Optional[dict]:
    alias = NBA_TEAM_ALIASES.get(name.lower().strip(), name)
    teams = await _nba_teams()
    for t in teams:
        team = t.get("team", {})
        if _team_match(alias, team.get("displayName", "")) or \
           _team_match(alias, team.get("shortDisplayName", "")) or \
           _team_match(name, team.get("name", "")) or \
           _team_match(name, team.get("abbreviation", "")):
            return team
    return None


async def _nba_team_schedule(team_id: str) -> list:
    url = f"{ESPN_BASE}/basketball/nba/teams/{team_id}/schedule"
    data = await _get(url)
    return data.get("events", [])


async def _nba_injuries() -> dict:
    """Returns {team_id: [player_name, ...]}"""
    try:
        url = "https://site.web.api.espn.com/apis/v2/sports/basketball/nba/injuries"
        data = await _get(url)
        result = {}
        for item in data.get("injuries", []):
            team_id = item.get("team", {}).get("id", "")
            athlete = item.get("athlete", {})
            name    = athlete.get("shortName", athlete.get("displayName", ""))
            status  = item.get("status", "")
            if team_id and name:
                result.setdefault(team_id, []).append(f"{name} ({status})")
        return result
    except Exception:
        return {}


def _nba_h2h(events: list, team_a_id: str, team_b_id: str) -> list:
    h2h = []
    for ev in reversed(events):
        comp = ev.get("competitions", [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed", False):
            continue
        competitors = comp.get("competitors", [])
        ids = {c.get("team", {}).get("id", "") for c in competitors}
        if str(team_a_id) not in ids or str(team_b_id) not in ids:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home and away:
            h2h.append((_get_score(home), _get_score(away)))
        if len(h2h) >= 6:
            break
    return h2h


async def _nba_form(events: list, team_id: str, n: int = 5) -> list:
    results = []
    for ev in reversed(events):
        if len(results) >= n:
            break
        comp = ev.get("competitions", [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed", False):
            continue
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        h, a = _get_score(home), _get_score(away)
        home_id = home.get("team", {}).get("id", "")
        if str(home_id) == str(team_id):
            results.append((h, a))
        else:
            results.append((a, h))
    return results


async def fetch_nba(home_name: str, away_name: str) -> str:
    try:
        home_team, away_team = await asyncio.gather(
            _find_nba_team(home_name),
            _find_nba_team(away_name),
        )

        if not home_team:
            return f"❌ Could not find NBA team '{home_name}'. Check spelling."
        if not away_team:
            return f"❌ Could not find NBA team '{away_name}'. Check spelling."

        home_id = home_team["id"]
        away_id = away_team["id"]

        home_sched, away_sched, all_injuries = await asyncio.gather(
            _nba_team_schedule(home_id),
            _nba_team_schedule(away_id),
            _nba_injuries(),
        )

        h2h       = _nba_h2h(home_sched, home_id, away_id)
        home_form = await _nba_form(home_sched, home_id, 5)
        away_form = await _nba_form(away_sched, away_id, 5)

        home_inj = all_injuries.get(str(home_id), [])[:5]
        away_inj = all_injuries.get(str(away_id), [])[:5]

    except Exception as e:
        return f"❌ Fetch error: {e}"

    h2h_str      = ", ".join(f"{a}-{b}" for a, b in h2h) if h2h else "N/A"
    home_inj_str = ", ".join(home_inj) if home_inj else "none"
    away_inj_str = ", ".join(away_inj) if away_inj else "none"

    def form_str(form):
        return " | ".join(f"{h}-{a}" for h, a in form) if form else "N/A"

    return (
        f"✅ *Data fetched! Add odds then copy & send /nba*\n\n"
        f"📋 *Recent form:*\n"
        f"  {home_team['displayName']}: `{form_str(home_form)}`\n"
        f"  {away_team['displayName']}: `{form_str(away_form)}`\n\n"
        f"```\n"
        f"/nba\n"
        f"{home_team['displayName']} vs {away_team['displayName']}\n"
        f"H2H: {h2h_str}\n"
        f"Home inj: {home_inj_str}\n"
        f"Away inj: {away_inj_str}\n"
        f"Last day: no\n"
        f"Spread: \n"
        f"\n"
        f"[PASTE ODDS BELOW]\n"
        f"W1:  W2:\n"
        f"O[line]:  U[line]:\n"
        f"HC1[spread]:  HC2[spread]:\n"
        f"Bank: [your bankroll]\n"
        f"```"
    )


# ── Main dispatcher ───────────────────────────────────────────────────────────

async def fetch_match(query: str) -> str:
    """
    Parse '/fetch Arsenal vs Bournemouth EPL' or '/fetch Lakers vs Warriors NBA'
    """
    query = query.strip()

    # Detect sport
    is_nba = "nba" in query.lower() or any(
        w in query.lower() for w in ["lakers","warriors","celtics","knicks",
                                      "bulls","heat","nets","spurs","suns",
                                      "thunder","clippers","rockets","mavs",
                                      "mavericks","nuggets","jazz","kings"]
    )

    # Extract teams (everything before the league/sport keyword)
    vs_match = re.search(r"(.+?)\s+vs\.?\s+(.+?)(?:\s+(nba|epl|la liga|serie a|bundesliga|ligue 1|ucl|champions|premier|spain|italy|germany|france|england|eredivisie).*)?$", query, re.IGNORECASE)

    if not vs_match:
        return (
            "❌ Format not recognized. Use:\n"
            "`/fetch Arsenal vs Bournemouth EPL`\n"
            "`/fetch Lakers vs Warriors NBA`"
        )

    home_name = vs_match.group(1).strip()
    away_name = vs_match.group(2).strip()
    league    = (vs_match.group(3) or "").strip()

    if is_nba:
        return await fetch_nba(home_name, away_name)
    else:
        if not league:
            league = "EPL"  # default
        return await fetch_soccer(home_name, away_name, league)
