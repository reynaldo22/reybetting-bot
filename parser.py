"""
Parse plain-text match input from Telegram into structured dict.

SOCCER FORMAT:
  Arsenal vs Bournemouth
  EPL
  H2H: 1-2, 2-0, 3-1, 1-1, 2-2, 0-1
  Home inj: Saka, White
  Away inj: Cook
  Relegation: none          ← none / home / away / both
  UCL: no                   ← no / knockout / first-leg
  Fwd: home                 ← none / home / away / both
  Def missing: away         ← none / home / away / both  (defensive absence)
  W1:1.48  X:4.2  W2:6.5
  BTTS+:1.65  BTTS-:2.1
  O2.5:2.378  U2.5:1.58
  O1.5:1.09  U1.5:4.25
  O3.5:2.55  U3.5:1.44
  Bank: 84000

NBA FORMAT:
  Lakers vs Warriors
  NBA
  H2H: 112-98, 105-110, 119-115, 108-103, 122-118, 115-99
  Home inj: LeBron, AD
  Away inj: Curry
  Last day: no              ← yes / no
  Spread: -5.5              ← home team spread (negative = home favoured)
  High 3pt: no              ← yes / no
  W1:1.95  W2:1.87
  O224.5:1.91  U224.5:1.91
  HC1-5.5:1.95  HC2+5.5:1.87
  Bank: 101000
"""

import re


# ── helpers ────────────────────────────────────────────────────────────────────

def _after_colon(line: str) -> str:
    """Return text after first colon/equals, stripped."""
    m = re.split(r"[:=]", line, maxsplit=1)
    return m[1].strip() if len(m) > 1 else ""


def _bool(val: str) -> bool:
    return val.lower().strip() in ("yes", "true", "1", "ko", "knockout")


def _parse_scores(raw: str) -> list:
    """'1-2, 3-0, 2-2' → [{"home":1,"away":2}, ...]"""
    results = []
    for chunk in raw.split(","):
        m = re.search(r"(\d+)\s*[-:]\s*(\d+)", chunk.strip())
        if m:
            results.append({"home": int(m.group(1)), "away": int(m.group(2))})
    return results


# ── soccer ─────────────────────────────────────────────────────────────────────

def parse_soccer(text: str) -> dict:
    data = {
        "sport": "soccer",
        "home_team": "Home", "away_team": "Away",
        "competition": "Unknown",
        "h2h": [],
        "home_injuries": [], "away_injuries": [],
        "context": {
            "sport": "soccer",
            "home_relegation": False, "away_relegation": False,
            "ucl_knockout": False,    "ucl_first_leg": False,
            "home_fwd_missing": False,"away_fwd_missing": False,
            "home_def_missing": False,"away_def_missing": False,
        },
        "odds": {},
        "bankroll": 100_000,
    }

    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

    for line in lines:
        low = line.lower()

        # ── Teams ──────────────────────────────────────────────────────────
        if " vs " in low and not re.search(r"[\d.]{3,}", line):
            parts = re.split(r"\s+vs\s+", line, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) == 2:
                data["home_team"] = parts[0].strip().title()
                data["away_team"] = parts[1].strip().title()
            continue

        # ── Competition (only if no colon → not a key:value line) ───────────
        if ":" not in line and re.match(r"^(epl|premier league|serie a|la liga|ucl|champions league|"
                    r"bundesliga|ligue 1|eredivisie|championship|league one|"
                    r"fa cup|copa del rey|coppa italia|mls)", low):
            data["competition"] = line.strip()
            if "ucl" in low or "champions" in low:
                data["context"]["ucl_knockout"] = True
            continue

        # ── H2H scores ─────────────────────────────────────────────────────
        if low.startswith("h2h"):
            data["h2h"] = _parse_scores(_after_colon(line))
            continue

        # ── Injuries ───────────────────────────────────────────────────────
        if re.match(r"home\s*(inj|injur)", low):
            data["home_injuries"] = [n.strip() for n in _after_colon(line).split(",") if n.strip()]
            continue
        if re.match(r"away\s*(inj|injur)", low):
            data["away_injuries"] = [n.strip() for n in _after_colon(line).split(",") if n.strip()]
            continue

        # ── Relegation ─────────────────────────────────────────────────────
        if re.match(r"relg?", low):
            val = _after_colon(line).lower()
            data["context"]["home_relegation"] = "home" in val or "both" in val
            data["context"]["away_relegation"] = "away" in val or "both" in val
            continue

        # ── UCL type ───────────────────────────────────────────────────────
        if low.startswith("ucl"):
            val = _after_colon(line).lower().strip()
            is_no = val in ("no", "false", "0", "none", "-")
            data["context"]["ucl_knockout"] = (not is_no) and (
                "knockout" in val or val == "ko" or "yes" in val.split()
            )
            data["context"]["ucl_first_leg"] = (not is_no) and (
                "first" in val or "leg1" in val or "1st" in val
            )
            continue

        # ── Missing forwards ───────────────────────────────────────────────
        if re.match(r"fwd", low):
            val = _after_colon(line).lower()
            data["context"]["home_fwd_missing"] = "home" in val or "both" in val
            data["context"]["away_fwd_missing"] = "away" in val or "both" in val
            continue

        # ── Missing defensive players ──────────────────────────────────────
        if re.match(r"def\s*miss", low):
            val = _after_colon(line).lower()
            data["context"]["home_def_missing"] = "home" in val or "both" in val
            data["context"]["away_def_missing"] = "away" in val or "both" in val
            continue

        # ── Bankroll ───────────────────────────────────────────────────────
        if re.match(r"bank", low):
            try:
                data["bankroll"] = float(re.sub(r"[,_]", "", _after_colon(line)))
            except ValueError:
                pass
            continue

        # ── Odds — scan any line for known patterns ────────────────────────
        _parse_soccer_odds(line, data["odds"])

    data["context"]["h2h_count"] = len(data["h2h"])
    return data


def _parse_soccer_odds(line: str, odds: dict):
    low = line.lower()
    patterns = [
        (r"w1\s*[:=]\s*([\d.]+)",           "w1"),
        (r"\bx\s*[:=]\s*([\d.]+)",           "draw"),
        (r"w2\s*[:=]\s*([\d.]+)",            "w2"),
        (r"btts[+y]\s*[:=]\s*([\d.]+)",      "btts_yes"),
        (r"btts[-n]\s*[:=]\s*([\d.]+)",      "btts_no"),
        (r"o1\.5\s*[:=]\s*([\d.]+)",         "over_1_5"),
        (r"u1\.5\s*[:=]\s*([\d.]+)",         "under_1_5"),
        (r"o2\.5\s*[:=]\s*([\d.]+)",         "over_2_5"),
        (r"u2\.5\s*[:=]\s*([\d.]+)",         "under_2_5"),
        (r"o3\.5\s*[:=]\s*([\d.]+)",         "over_3_5"),
        (r"u3\.5\s*[:=]\s*([\d.]+)",         "under_3_5"),
        (r"dc1x\s*[:=]\s*([\d.]+)",          "dc_1x"),
        (r"dc12\s*[:=]\s*([\d.]+)",          "dc_12"),
        (r"dcx2\s*[:=]\s*([\d.]+)",          "dc_x2"),
    ]
    for pattern, key in patterns:
        m = re.search(pattern, low)
        if m:
            try:
                odds[key] = float(m.group(1))
            except ValueError:
                pass


# ── NBA ────────────────────────────────────────────────────────────────────────

def parse_nba(text: str) -> dict:
    data = {
        "sport": "nba",
        "home_team": "Home", "away_team": "Away",
        "competition": "NBA",
        "h2h": [],
        "home_injuries": [], "away_injuries": [],
        "context": {
            "sport": "nba",
            "is_last_day_nba": False,
            "high_pace_3pt": False,
            "handicap_line": 0.0,
        },
        "odds": {},
        "bankroll": 100_000,
    }

    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]

    for line in lines:
        low = line.lower()

        # Teams
        if " vs " in low and not re.search(r"[\d.]{3,}", line):
            parts = re.split(r"\s+vs\s+", line, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) == 2:
                data["home_team"] = parts[0].strip().title()
                data["away_team"] = parts[1].strip().title()
            continue

        if low.startswith("h2h"):
            data["h2h"] = _parse_scores(_after_colon(line))
            continue

        if re.match(r"home\s*(inj|injur)", low):
            data["home_injuries"] = [n.strip() for n in _after_colon(line).split(",") if n.strip()]
            continue
        if re.match(r"away\s*(inj|injur)", low):
            data["away_injuries"] = [n.strip() for n in _after_colon(line).split(",") if n.strip()]
            continue

        if re.match(r"last\s*day", low):
            data["context"]["is_last_day_nba"] = _bool(_after_colon(line))
            continue

        if re.match(r"spread", low):
            try:
                data["context"]["handicap_line"] = float(_after_colon(line))
            except ValueError:
                pass
            continue

        if re.match(r"high\s*3pt|pace", low):
            data["context"]["high_pace_3pt"] = _bool(_after_colon(line))
            continue

        if re.match(r"bank", low):
            try:
                data["bankroll"] = float(re.sub(r"[,_]", "", _after_colon(line)))
            except ValueError:
                pass
            continue

        _parse_nba_odds(line, data["odds"])

    data["context"]["h2h_count"] = len(data["h2h"])
    return data


def _parse_nba_odds(line: str, odds: dict):
    low = line.lower()
    patterns = [
        (r"w1\s*[:=]\s*([\d.]+)",                    "w1"),
        (r"w2\s*[:=]\s*([\d.]+)",                    "w2"),
        (r"o([\d.]+)\s*[:=]\s*([\d.]+)",             "over"),   # O224.5:1.91
        (r"u([\d.]+)\s*[:=]\s*([\d.]+)",             "under"),  # U224.5:1.91
        (r"hc1[-+][\d.]+\s*[:=]\s*([\d.]+)",         "hc_fav"),
        (r"hc2[-+][\d.]+\s*[:=]\s*([\d.]+)",         "hc_dog"),
    ]
    for pattern, key in patterns:
        m = re.search(pattern, low)
        if m:
            try:
                # For over/under, store the line too
                if key in ("over", "under"):
                    line_val = float(m.group(1))
                    odds_val = float(m.group(2))
                    odds[key] = odds_val
                    odds[f"{key}_line"] = line_val
                else:
                    odds[key] = float(m.group(1))
            except (ValueError, IndexError):
                pass
