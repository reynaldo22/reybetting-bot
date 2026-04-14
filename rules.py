"""
All betting rules (1-25).
check_rules(ctx) → list of issues
Each issue: {"rule": int, "level": str, "msg": str, "skip": [keys], "downgrade": {key: n}}
"""


def check_rules(ctx: dict) -> list:
    """
    ctx keys:
      sport              : "soccer" | "nba"
      home_team          : str
      away_team          : str
      competition        : str
      home_relegation    : bool   (Rule 25)
      away_relegation    : bool   (Rule 25)
      ucl_knockout       : bool   (Rules 19-21)
      ucl_first_leg      : bool   (Rule 20)
      home_fwd_missing   : bool   (Rule 5)
      away_fwd_missing   : bool   (Rule 5)
      home_def_missing   : bool   (Rule 5 — defensive absence inflates scoring)
      away_def_missing   : bool
      h2h_count          : int    (Rule 15)
      is_last_day_nba    : bool   (Rules 11, 23)
      handicap_line      : float  (Rules 7, 9)  positive = home favoured
    """
    issues = []
    sport  = ctx.get("sport", "soccer")
    home   = ctx.get("home_team", "Home")
    away   = ctx.get("away_team", "Away")

    # ── RULE 25 — Relegation survival mode ──────────────────────────────────
    if ctx.get("home_relegation") or ctx.get("away_relegation"):
        team = home if ctx.get("home_relegation") else away
        issues.append({
            "rule": 25, "level": "CRITICAL",
            "msg": (f"🚨 RULE 25: {team} in RELEGATION SURVIVAL MODE\n"
                    "   Desperation overrides ALL form/H2H data.\n"
                    "   → SKIP every totals & BTTS bet on this game."),
            "skip": ["over_1_5","over_2_5","over_3_5",
                     "under_1_5","under_2_5","under_3_5",
                     "btts_yes","btts_no"],
            "downgrade": {}
        })

    # ── RULE 19 — UCL knockout ───────────────────────────────────────────────
    if ctx.get("ucl_knockout"):
        issues.append({
            "rule": 19, "level": "WARNING",
            "msg": ("⚠️ RULE 19: UCL knockout format\n"
                    "   Domestic H2H Over/BTTS data unreliable.\n"
                    "   → Over 2.5/3.5 & BTTS Yes downgraded 1 tier."),
            "skip": [],
            "downgrade": {"over_2_5": 1, "over_3_5": 1, "btts_yes": 1}
        })

    # ── RULE 20 — UCL first leg away ─────────────────────────────────────────
    if ctx.get("ucl_first_leg"):
        issues.append({
            "rule": 20, "level": "WARNING",
            "msg": ("⚠️ RULE 20: UCL first leg — away teams play for 0-0.\n"
                    "   → BTTS Yes max B-tier."),
            "skip": [],
            "downgrade": {"btts_yes": 1}
        })

    # ── RULE 21 — Simeone UCL premium ───────────────────────────────────────
    import unicodedata
    def _strip(s):
        nfkd = unicodedata.normalize("NFKD", s)
        return nfkd.encode("ascii", "ignore").decode("ascii").lower()

    if ctx.get("ucl_knockout"):
        teams = [_strip(home), _strip(away)]
        if any("atletico" in t for t in teams):
            issues.append({
                "rule": 21, "level": "WARNING",
                "msg": ("⚠️ RULE 21: Atletico Madrid in UCL knockout.\n"
                        "   Simeone defensive premium — avoid Over & BTTS Yes against them.\n"
                        "   NOTE: This rule is UCL ONLY — ignore in La Liga."),
                "skip": [],
                "downgrade": {"over_2_5": 1, "btts_yes": 1}
            })

    # ── RULE 5 — Missing players: offensive vs defensive ────────────────────
    if ctx.get("home_fwd_missing") and ctx.get("away_fwd_missing"):
        issues.append({
            "rule": 5, "level": "WARNING",
            "msg": ("⚠️ RULE 5: Both teams missing key forwards.\n"
                    "   → Downgrade Over 2.5/3.5 & BTTS Yes by 1 tier."),
            "skip": [],
            "downgrade": {"over_2_5": 1, "over_3_5": 1, "btts_yes": 1}
        })
    elif ctx.get("home_fwd_missing"):
        issues.append({
            "rule": 5, "level": "INFO",
            "msg": "ℹ️ RULE 5: Home key forward missing → reduce home scoring expectation.",
            "skip": [], "downgrade": {}
        })
    elif ctx.get("away_fwd_missing"):
        issues.append({
            "rule": 5, "level": "INFO",
            "msg": "ℹ️ RULE 5: Away key forward missing → reduce away scoring expectation.",
            "skip": [], "downgrade": {}
        })

    # Defensive absence = scoring INCREASES (Rule 5 inverse)
    if ctx.get("home_def_missing") or ctx.get("away_def_missing"):
        issues.append({
            "rule": 5, "level": "INFO",
            "msg": ("ℹ️ RULE 5: Key defensive player missing.\n"
                    "   Defensive absence INCREASES scoring (opposite effect).\n"
                    "   → Slightly upgrade Over / downgrade Under."),
            "skip": [], "downgrade": {}
        })

    # ── RULE 15 — H2H sample size ────────────────────────────────────────────
    h2h_n = ctx.get("h2h_count", 10)
    if h2h_n < 3:
        issues.append({
            "rule": 15, "level": "CRITICAL",
            "msg": f"🚨 RULE 15: Only {h2h_n} H2H games — SKIP high-confidence bets. Max C-tier.",
            "skip": [],
            "downgrade": {k: 2 for k in ["over_2_5","under_2_5","btts_yes","btts_no","w1","w2"]}
        })
    elif h2h_n < 5:
        issues.append({
            "rule": 15, "level": "WARNING",
            "msg": f"⚠️ RULE 15: Only {h2h_n} H2H games — low conviction. All markets downgraded 1 tier.",
            "skip": [],
            "downgrade": {k: 1 for k in ["over_2_5","under_2_5","btts_yes","btts_no","w1","w2"]}
        })

    # ── NBA-SPECIFIC RULES ───────────────────────────────────────────────────
    if sport == "nba":

        # Rule 9 — No -15.5+ spreads
        hc = abs(ctx.get("handicap_line", 0))
        if hc >= 15.5:
            issues.append({
                "rule": 9, "level": "CRITICAL",
                "msg": (f"🚨 RULE 9: Spread {hc} ≥ 15.5 — SKIP.\n"
                        "   Dominant teams pull starters → garbage time collapses margin."),
                "skip": ["hc_fav"], "downgrade": {}
            })

        # Rule 7 — OT risk kills large spreads
        elif 7.5 <= hc < 15.5:
            issues.append({
                "rule": 7, "level": "WARNING",
                "msg": (f"⚠️ RULE 7: Spread {hc} ≥ 7.5 — OT risk.\n"
                        "   If close game possible → use ML instead of handicap."),
                "skip": [], "downgrade": {"hc_fav": 1}
            })

        # Rules 11 + 23 — Last day of season
        if ctx.get("is_last_day_nba"):
            issues.append({
                "rule": 23, "level": "CRITICAL",
                "msg": ("🚨 RULES 11+23: Last day of NBA season.\n"
                        "   Load management rampant — NO Under bets, NO large spreads.\n"
                        "   Confirm lineups before EVERY bet."),
                "skip": ["under"], "downgrade": {"hc_fav": 2, "hc_dog": 1}
            })

        # Rule 8 — 3PT explosion
        if ctx.get("high_pace_3pt"):
            issues.append({
                "rule": 8, "level": "WARNING",
                "msg": ("⚠️ RULE 8: High-pace 3PT team — 45+ attempts possible.\n"
                        "   → Under bet may be invalidated. Downgrade Under 1 tier."),
                "skip": [], "downgrade": {"under": 1}
            })

    return issues
