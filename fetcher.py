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
    "champions league": "uefa.champions",
    "uel": "uefa.europa", "europa": "uefa.europa",
    "europa league": "uefa.europa", "europa league": "uefa.europa",
    "uecl": "uefa.conference", "conference": "uefa.conference",
    "conference league": "uefa.conference",
    "eredivisie": "ned.1", "netherlands": "ned.1",
}

UCL_CODES = {"uefa.champions", "uefa.europa", "uefa.conference"}

# For teams in Conference League — ESPN has no UECL competition,
# so we look them up via domestic league for form data
TEAM_DOMESTIC_LEAGUE = {
    "fiorentina": "ita.1",  "acf fiorentina": "ita.1",
    "crystal palace": "eng.1",
    "real betis": "esp.1",  "betis": "esp.1",
    "gent": "ned.1",        "kaa gent": "ned.1",
    "anderlecht": "bel.1",  "rsc anderlecht": "bel.1",
    "djurgarden": "swe.1",  "djurgardens if": "swe.1",
    "lask": "aut.1",        "lask linz": "aut.1",
    "chelsea": "eng.1",     "man united": "eng.1",
    "villarreal": "esp.1",  "villarreal cf": "esp.1",
    "heidenheim": "ger.1",  "1. fc heidenheim": "ger.1",
    "rapid vienna": "aut.1","sk rapid": "aut.1",
    "jagiellonia": "pol.1",
    # German teams
    "fc st. pauli": "ger.1",   "st. pauli": "ger.1",
    "fc cologne": "ger.1",     "1. fc köln": "ger.1",
    "1. fc union berlin": "ger.1",
    "borussia mönchengladbach": "ger.1",
    "1. fsv mainz 05": "ger.1","fc augsburg": "ger.1",
    "tsg hoffenheim": "ger.1", "vfl wolfsburg": "ger.1",
    "eintracht frankfurt": "ger.1",
    # Eastern Europe / Turkey
    "sk slavia prague": "cze.1", "ac sparta prague": "cze.1",
    "galatasaray sk": "tur.1",   "fenerbahce sk": "tur.1",
    "besiktas jk": "tur.1",
    "olympiacos fc": "gre.1",
    "shakhtar donetsk": "ukr.1",
    # Italian teams
    "internazionale": "ita.1",  "inter milan": "ita.1",
    "sassuolo": "ita.1",        "us sassuolo": "ita.1",
    "como": "ita.1",            "como 1907": "ita.1",
    "cagliari": "ita.1",        "cagliari calcio": "ita.1",
    "torino": "ita.1",          "fc torino": "ita.1",
    "udinese": "ita.1",         "genoa": "ita.1",
    "lecce": "ita.1",           "parma": "ita.1",
    "hellas verona": "ita.1",   "verona": "ita.1",
    "cremonese": "ita.1",       "pisa": "ita.1",
}

# Common team name aliases for search
SOCCER_ALIASES = {
    "celta": "celta vigo", "celta vigo": "celta vigo",
    "freiburg": "sc freiburg", "sc freiburg": "sc freiburg",
    "frankfurt": "eintracht frankfurt", "eintracht": "eintracht frankfurt",
    "rangers": "rangers fc", "celtic": "celtic fc",
    "sporting": "sporting cp", "sporting cp": "sporting cp",
    "braga": "sc braga", "porto": "fc porto",
    "fiorentina": "fiorentina", "acf fiorentina": "fiorentina",
    "crystal palace": "crystal palace",
    "betis": "real betis", "real betis": "real betis",
    "villarreal": "villarreal cf",
    "anderlecht": "rsc anderlecht",
    "gent": "kaa gent", "kaa gent": "kaa gent",
    "djurgarden": "djurgardens if",
    "lask": "lask linz",
    # German teams
    "st pauli": "fc st. pauli", "st. pauli": "fc st. pauli",
    "st.pauli": "fc st. pauli", "st.bauli": "fc st. pauli",
    "koln": "fc cologne", "köln": "fc cologne", "cologne": "fc cologne",
    "fc köln": "fc cologne", "1. fc koln": "fc cologne", "1. fc köln": "fc cologne",
    "union berlin": "1. fc union berlin", "union": "1. fc union berlin",
    "frankfurt": "eintracht frankfurt", "eintracht": "eintracht frankfurt",
    "gladbach": "borussia mönchengladbach", "monchengladbach": "borussia mönchengladbach",
    "mainz": "1. fsv mainz 05", "augsburg": "fc augsburg",
    "hoffenheim": "tsg hoffenheim", "wolfsburg": "vfl wolfsburg",
    "heidenheim": "1. fc heidenheim",
    # Other teams often in Europa
    "slavia prague": "sk slavia prague", "slavia": "sk slavia prague",
    "sparta prague": "ac sparta prague", "sparta": "ac sparta prague",
    "ajax": "ajax amsterdam",
    "galatasaray": "galatasaray sk", "fenerbahce": "fenerbahce sk",
    "besiktas": "besiktas jk",
    "olympiacos": "olympiacos fc",
    "ferencvaros": "ferencváros tc",
    "shakhtar": "shakhtar donetsk",
    "dynamo kyiv": "dynamo kyiv", "dynamo": "dynamo kyiv",
    "psg": "paris saint-germain", "paris": "paris saint-germain",
    "atletico": "atletico madrid", "atletico madrid": "atletico madrid",
    "man utd": "manchester united", "man united": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton",
    "inter": "internazionale", "inter milan": "internazionale",
    "internazionale milano": "internazionale",
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
    if q == c:
        return True
    # Substring match only if candidate is substantial (>5 chars) to avoid "nets" in "hornets"
    if len(q) > 5 and q in c:
        return True
    if len(c) > 5 and c in q:
        return True
    # Word-level: ALL query words (>4 chars) must appear in candidate
    q_words = [w for w in q.split() if len(w) > 4]
    return bool(q_words) and all(w in c for w in q_words)


# ── Soccer fetcher ────────────────────────────────────────────────────────────

async def _soccer_teams(league_code: str) -> list:
    url = f"{ESPN_BASE}/soccer/{league_code}/teams"
    data = await _get(url)
    return data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])


async def _find_soccer_team(name: str, league_code: str) -> Optional[dict]:
    resolved  = SOCCER_ALIASES.get(name.lower().strip(), name)
    r_norm    = _normalize(resolved)
    n_norm    = _normalize(name)
    teams     = await _soccer_teams(league_code)

    best_team  = None
    best_score = 0

    for t in teams:
        team     = t.get("team", {})
        display  = _normalize(team.get("displayName", ""))
        short    = _normalize(team.get("shortDisplayName", ""))
        tname    = _normalize(team.get("name", ""))

        score = 0
        # Exact match — highest priority
        if r_norm == display or n_norm == display:
            score = 100
        elif r_norm == short or n_norm == short:
            score = 90
        # One fully contains the other
        elif r_norm in display or display in r_norm:
            score = 60
        elif n_norm in display or display in n_norm:
            score = 55
        else:
            # ALL query words must appear in candidate (strict word match)
            q_words = [w for w in r_norm.split() if len(w) > 3]
            if q_words and all(w in display for w in q_words):
                score = 40
            else:
                n_words = [w for w in n_norm.split() if len(w) > 3]
                if n_words and all(w in display for w in n_words):
                    score = 35

        if score > best_score:
            best_score = score
            best_team  = team

    return best_team if best_score > 0 else None


async def _soccer_team_schedule(team_id: str, league_code: str) -> list:
    """Fetch schedule — try current season first, then explicit 2026 season."""
    url = f"{ESPN_BASE}/soccer/{league_code}/teams/{team_id}/schedule"
    data = await _get(url)
    events = data.get("events", [])
    # If no completed games, try with explicit season year
    completed = [e for e in events if e.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("completed")]
    if not completed:
        try:
            data2 = await _get(url + "?season=2026")
            events2 = data2.get("events", [])
            if events2:
                events = events2
        except Exception:
            pass
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
        # Find teams — if UEFA competition, try all three UEFA codes as fallback
        uefa_fallback = ["uefa.champions", "uefa.europa", "uefa.conference"]

        async def find_with_fallback(name: str) -> tuple:
            """Returns (team, actual_league_code)"""
            team = await _find_soccer_team(name, league_code)
            if team:
                return team, league_code
            # Try other UEFA competitions
            if league_code in uefa_fallback:
                for code in uefa_fallback:
                    if code == league_code:
                        continue
                    team = await _find_soccer_team(name, code)
                    if team:
                        return team, code
            # Fallback: try domestic league (for Conference League teams)
            resolved = SOCCER_ALIASES.get(name.lower().strip(), name).lower()
            domestic = TEAM_DOMESTIC_LEAGUE.get(resolved) or TEAM_DOMESTIC_LEAGUE.get(name.lower().strip())
            if domestic:
                team = await _find_soccer_team(name, domestic)
                if team:
                    return team, domestic
            return None, league_code

        (home_team, home_lc), (away_team, away_lc) = await asyncio.gather(
            find_with_fallback(home_name),
            find_with_fallback(away_name),
        )
        # Use whichever league code actually found both teams
        if home_lc != league_code and home_team:
            league_code = home_lc
        elif away_lc != league_code and away_team:
            league_code = away_lc

        # Update display name based on actual league found
        league_name_map = {
            "uefa.champions": "UCL",
            "uefa.europa": "Europa League",
            "uefa.conference": "Conference League",
        }
        if league_code in league_name_map:
            league_disp = league_name_map[league_code]

        if not home_team:
            return (f"❌ Could not find '{home_name}'.\n"
                    f"Try full name e.g. 'Fiorentina', 'Crystal Palace'\n"
                    f"Or specify competition: UCL / Europa / Conference")
        if not away_team:
            return (f"❌ Could not find '{away_name}'.\n"
                    f"Try full name e.g. 'Fiorentina', 'Crystal Palace'\n"
                    f"Or specify competition: UCL / Europa / Conference")

        # Fix competition display if domestic fallback was used
        if league_code not in ("uefa.champions", "uefa.europa", "uefa.conference"):
            orig_key = league.lower().strip()
            if orig_key in ("ucl", "champions", "champions league"):
                league_disp = "UCL"
            elif orig_key in ("uel", "europa", "europa league"):
                league_disp = "Europa League"
            elif orig_key in ("uecl", "conference", "conference league", "uefa"):
                league_disp = "Conference League"

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

    is_ucl  = league_code == "uefa.champions"
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
    "la lakers": "los angeles lakers", "lal": "los angeles lakers", "lakers": "los angeles lakers",
    "la clippers": "los angeles clippers", "lac": "los angeles clippers", "clippers": "los angeles clippers",
    "gsw": "golden state warriors", "warriors": "golden state warriors",
    "okc": "oklahoma city thunder", "thunder": "oklahoma city thunder",
    "ny knicks": "new york knicks", "knicks": "new york knicks",
    "sa spurs": "san antonio spurs", "spurs": "san antonio spurs",
    "nola": "new orleans pelicans", "pelicans": "new orleans pelicans",
    "phx": "phoenix suns", "suns": "phoenix suns",
    # Commonly mismatched
    "hornets": "charlotte hornets", "charlotte": "charlotte hornets",
    "nets": "brooklyn nets", "brooklyn": "brooklyn nets",
    "magic": "orlando magic", "orlando": "orlando magic",
    "heat": "miami heat", "miami": "miami heat",
    "bulls": "chicago bulls", "chicago": "chicago bulls",
    "celtics": "boston celtics", "boston": "boston celtics",
    "hawks": "atlanta hawks", "atlanta": "atlanta hawks",
    "pistons": "detroit pistons", "detroit": "detroit pistons",
    "pacers": "indiana pacers", "indiana": "indiana pacers",
    "cavaliers": "cleveland cavaliers", "cavs": "cleveland cavaliers", "cleveland": "cleveland cavaliers",
    "wizards": "washington wizards", "washington": "washington wizards",
    "raptors": "toronto raptors", "toronto": "toronto raptors",
    "bucks": "milwaukee bucks", "milwaukee": "milwaukee bucks",
    "76ers": "philadelphia 76ers", "sixers": "philadelphia 76ers", "philly": "philadelphia 76ers",
    "nuggets": "denver nuggets", "denver": "denver nuggets",
    "timberwolves": "minnesota timberwolves", "wolves": "minnesota timberwolves", "minnesota": "minnesota timberwolves",
    "jazz": "utah jazz", "utah": "utah jazz",
    "blazers": "portland trail blazers", "portland": "portland trail blazers",
    "kings": "sacramento kings", "sacramento": "sacramento kings",
    "grizzlies": "memphis grizzlies", "memphis": "memphis grizzlies",
    "mavericks": "dallas mavericks", "mavs": "dallas mavericks", "dallas": "dallas mavericks",
    "rockets": "houston rockets", "houston": "houston rockets",
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


async def _nba_recent_games(days: int = 120) -> list:
    """Fetch completed NBA games from last N days using scoreboard endpoint."""
    from datetime import datetime, timedelta
    games = []
    end = datetime.utcnow()
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        for i in range(days):
            d = end - timedelta(days=i)
            date_str = d.strftime("%Y%m%d")
            try:
                r = await client.get(
                    f"{ESPN_BASE}/basketball/nba/scoreboard",
                    params={"dates": date_str}
                )
                events = r.json().get("events", [])
                for e in events:
                    comp = e.get("competitions", [{}])[0]
                    if not comp.get("status", {}).get("type", {}).get("completed"):
                        continue
                    competitors = comp.get("competitors", [])
                    if len(competitors) == 2:
                        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                        games.append({
                            "home_id":    home.get("team", {}).get("id", ""),
                            "home_name":  home.get("team", {}).get("displayName", ""),
                            "home_score": int(home.get("score", 0) or 0),
                            "away_id":    away.get("team", {}).get("id", ""),
                            "away_name":  away.get("team", {}).get("displayName", ""),
                            "away_score": int(away.get("score", 0) or 0),
                        })
            except Exception:
                continue
    return games


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


def _nba_h2h_from_games(games: list, id_a: str, id_b: str) -> list:
    h2h = []
    for g in games:
        if (str(g["home_id"]) == str(id_a) and str(g["away_id"]) == str(id_b)):
            h2h.append((g["home_score"], g["away_score"]))
        elif (str(g["home_id"]) == str(id_b) and str(g["away_id"]) == str(id_a)):
            # flip to always show id_a as "home"
            h2h.append((g["away_score"], g["home_score"]))
        if len(h2h) >= 6:
            break
    return h2h


def _nba_form_from_games(games: list, team_id: str, n: int = 5) -> list:
    results = []
    for g in games:
        if len(results) >= n:
            break
        if str(g["home_id"]) == str(team_id):
            results.append((g["home_score"], g["away_score"]))
        elif str(g["away_id"]) == str(team_id):
            results.append((g["away_score"], g["home_score"]))
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

        # Use scoreboard date-range approach (works year-round, including playoffs)
        all_games, all_injuries = await asyncio.gather(
            _nba_recent_games(days=120),  # full season lookback
            _nba_injuries(),
        )

        h2h       = _nba_h2h_from_games(all_games, home_id, away_id)
        home_form = _nba_form_from_games(all_games, home_id, 5)
        away_form = _nba_form_from_games(all_games, away_id, 5)

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


# ── NHL fetcher ────────────────────────────────────────────────────────────────

NHL_BASE = "https://api-web.nhle.com/v1"

NHL_TEAMS: dict = {}  # cache: abbrev → {abbrev, name}

# Common name → abbreviation map
NHL_NAME_MAP = {
    "bruins": "BOS", "boston": "BOS",
    "maple leafs": "TOR", "toronto": "TOR", "leafs": "TOR",
    "rangers": "NYR", "new york rangers": "NYR",
    "islanders": "NYI", "new york islanders": "NYI",
    "devils": "NJD", "new jersey": "NJD",
    "flyers": "PHI", "philadelphia": "PHI",
    "penguins": "PIT", "pittsburgh": "PIT",
    "capitals": "WSH", "washington": "WSH",
    "hurricanes": "CAR", "carolina": "CAR",
    "lightning": "TBL", "tampa bay": "TBL", "tampa": "TBL",
    "panthers": "FLA", "florida": "FLA",
    "canadiens": "MTL", "montreal": "MTL",
    "senators": "OTT", "ottawa": "OTT",
    "sabres": "BUF", "buffalo": "BUF",
    "red wings": "DET", "detroit": "DET",
    "blackhawks": "CHI", "chicago": "CHI",
    "predators": "NSH", "nashville": "NSH",
    "blues": "STL", "st louis": "STL", "st. louis": "STL",
    "avalanche": "COL", "colorado": "COL",
    "jets": "WPG", "winnipeg": "WPG",
    "wild": "MIN", "minnesota": "MIN",
    "stars": "DAL", "dallas": "DAL",
    "oilers": "EDM", "edmonton": "EDM",
    "flames": "CGY", "calgary": "CGY",
    "canucks": "VAN", "vancouver": "VAN",
    "golden knights": "VGK", "vegas": "VGK",
    "kraken": "SEA", "seattle": "SEA",
    "sharks": "SJS", "san jose": "SJS",
    "ducks": "ANA", "anaheim": "ANA",
    "kings": "LAK", "los angeles kings": "LAK",
    "coyotes": "UTA", "utah": "UTA", "arizona": "UTA",
    "blue jackets": "CBJ", "columbus": "CBJ",
}


async def _nhl_get(path: str) -> dict:
    url = f"{NHL_BASE}{path}"
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
        follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _find_nhl_abbrev(name: str) -> Optional[str]:
    low = _normalize(name)
    # Direct map
    if low in NHL_NAME_MAP:
        return NHL_NAME_MAP[low]
    # Partial match
    for key, abbrev in NHL_NAME_MAP.items():
        if key in low or low in key:
            return abbrev
    # Try 3-letter abbrev
    if len(name) == 3:
        return name.upper()
    return None


async def _nhl_team_schedule(abbrev: str) -> list:
    """Fetch completed games from current + previous 2 NHL seasons."""
    all_games = []
    # current season + 2 previous seasons for H2H coverage
    for season in ["now", "20242025", "20232024"]:
        try:
            data = await _nhl_get(f"/club-schedule-season/{abbrev}/{season}")
            games = [g for g in data.get("games", []) if g.get("gameState") == "OFF"]
            all_games.extend(games)
        except Exception:
            continue
    return all_games


async def _nhl_roster_goalies(abbrev: str) -> list:
    data = await _nhl_get(f"/roster/{abbrev}/current")
    goalies = data.get("goalies", [])
    return [f"{g['firstName']['default']} {g['lastName']['default']}" for g in goalies]


def _nhl_h2h(games: list, home_abbrev: str, away_abbrev: str) -> list:
    h2h = []
    for g in reversed(games):
        h = g.get("homeTeam", {})
        a = g.get("awayTeam", {})
        if h.get("abbrev") == home_abbrev and a.get("abbrev") == away_abbrev:
            h2h.append((h.get("score", 0), a.get("score", 0)))
        elif h.get("abbrev") == away_abbrev and a.get("abbrev") == home_abbrev:
            # Flip so always home-away from perspective of our home team
            h2h.append((a.get("score", 0), h.get("score", 0)))
        if len(h2h) >= 6:
            break
    return h2h


def _nhl_form(games: list, abbrev: str, n: int = 5) -> list:
    results = []
    for g in reversed(games):
        if len(results) >= n:
            break
        h = g.get("homeTeam", {})
        a = g.get("awayTeam", {})
        if h.get("abbrev") == abbrev:
            results.append((h.get("score", 0), a.get("score", 0)))
        elif a.get("abbrev") == abbrev:
            results.append((a.get("score", 0), h.get("score", 0)))
    return results


async def fetch_nhl(home_name: str, away_name: str) -> str:
    home_abbrev = _find_nhl_abbrev(home_name)
    away_abbrev = _find_nhl_abbrev(away_name)

    if not home_abbrev:
        return f"❌ Could not find NHL team '{home_name}'. Try full name (e.g. 'Boston Bruins')."
    if not away_abbrev:
        return f"❌ Could not find NHL team '{away_name}'. Try full name (e.g. 'Toronto Maple Leafs')."

    try:
        home_sched, away_sched, home_goalies, away_goalies = await asyncio.gather(
            _nhl_team_schedule(home_abbrev),
            _nhl_team_schedule(away_abbrev),
            _nhl_roster_goalies(home_abbrev),
            _nhl_roster_goalies(away_abbrev),
        )

        h2h       = _nhl_h2h(home_sched, home_abbrev, away_abbrev)
        if len(h2h) < 3:
            h2h2 = _nhl_h2h(away_sched, away_abbrev, home_abbrev)
            h2h += [(b, a) for a, b in h2h2 if (b, a) not in h2h]
            h2h = h2h[:6]

        home_form = _nhl_form(home_sched, home_abbrev, 5)
        away_form = _nhl_form(away_sched, away_abbrev, 5)

    except Exception as e:
        return f"❌ NHL fetch error: {e}"

    h2h_str = ", ".join(f"{h}-{a}" for h, a in h2h) if h2h else "N/A"

    def form_str(form):
        return " | ".join(f"{h}-{a}" for h, a in form) if form else "N/A"

    home_g_str = ", ".join(home_goalies) if home_goalies else "unknown"
    away_g_str = ", ".join(away_goalies) if away_goalies else "unknown"

    # Get team display names from standings
    try:
        standings = await _nhl_get("/standings/now")
        name_map = {
            t.get("teamAbbrev", {}).get("default", ""): t.get("teamName", {}).get("default", "")
            for t in standings.get("standings", [])
        }
        home_display = name_map.get(home_abbrev, home_abbrev)
        away_display = name_map.get(away_abbrev, away_abbrev)
    except Exception:
        home_display = home_abbrev
        away_display = away_abbrev

    return (
        f"✅ *Data fetched! Add odds then copy & send /nhl*\n\n"
        f"📋 *Recent form:*\n"
        f"  {home_display}: `{form_str(home_form)}`\n"
        f"  {away_display}: `{form_str(away_form)}`\n\n"
        f"🥅 *Goalies on roster:*\n"
        f"  Home: {home_g_str}\n"
        f"  Away: {away_g_str}\n\n"
        f"```\n"
        f"/nhl\n"
        f"{home_display} vs {away_display}\n"
        f"H2H: {h2h_str}\n"
        f"Home inj: [CHECK & ADD MANUALLY]\n"
        f"Away inj: [CHECK & ADD MANUALLY]\n"
        f"B2B: no\n"
        f"Backup goalie: no\n"
        f"Playoffs: no\n"
        f"\n"
        f"[PASTE ODDS BELOW]\n"
        f"W1:  W2:\n"
        f"PL-1.5:  PL+1.5:\n"
        f"O5.5:  U5.5:\n"
        f"O6.5:  U6.5:\n"
        f"Bank: [your bankroll]\n"
        f"```"
    )


# ── Main dispatcher ───────────────────────────────────────────────────────────

async def fetch_match(query: str) -> str:
    query = query.strip()
    low   = query.lower()

    # Detect sport
    is_nhl = "nhl" in low or any(w in low for w in [
        "bruins","maple leafs","leafs","rangers","islanders","devils","flyers",
        "penguins","capitals","hurricanes","lightning","panthers","canadiens",
        "senators","sabres","red wings","blackhawks","predators","blues",
        "avalanche","jets","wild","stars","oilers","flames","canucks",
        "golden knights","kraken","sharks","ducks","kings","coyotes","blue jackets"
    ])
    is_nba = not is_nhl and ("nba" in low or any(w in low for w in [
        "lakers","warriors","celtics","knicks","bulls","heat","nets","spurs",
        "suns","thunder","clippers","rockets","mavs","mavericks","nuggets","jazz"
    ]))

    vs_match = re.search(
        r"(.+?)\s+vs\.?\s+(.+?)(?:\s+(nhl|nba|epl|la liga|serie a|bundesliga|ligue 1|ucl|uel|uecl|champions|europa|conference|premier|spain|italy|germany|france|england|eredivisie).*)?$",
        query, re.IGNORECASE
    )

    if not vs_match:
        return (
            "❌ Format not recognized. Use:\n"
            "`/fetch Arsenal vs Bournemouth EPL`\n"
            "`/fetch Lakers vs Warriors NBA`\n"
            "`/fetch Bruins vs Maple Leafs NHL`"
        )

    home_name = vs_match.group(1).strip()
    away_name = vs_match.group(2).strip()
    league    = (vs_match.group(3) or "").strip()

    if is_nhl:
        return await fetch_nhl(home_name, away_name)
    elif is_nba:
        return await fetch_nba(home_name, away_name)
    else:
        if not league:
            league = "EPL"
        return await fetch_soccer(home_name, away_name, league)
