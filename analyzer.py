"""
Main analysis engine.
analyze(data) → result dict ready for formatting.
"""

from ev_calc import calc_ev, ev_to_tier, get_stake, downgrade, bankroll_mode
from rules   import check_rules


# ── H2H stat calculators ───────────────────────────────────────────────────────

def _soccer_freqs(h2h: list) -> dict:
    n = len(h2h)
    if n == 0:
        return {}

    home_w  = sum(1 for r in h2h if r["home"] > r["away"])
    draws   = sum(1 for r in h2h if r["home"] == r["away"])
    away_w  = sum(1 for r in h2h if r["home"] < r["away"])
    btts    = sum(1 for r in h2h if r["home"] > 0 and r["away"] > 0)
    o15     = sum(1 for r in h2h if r["home"] + r["away"] > 1.5)
    o25     = sum(1 for r in h2h if r["home"] + r["away"] > 2.5)
    o35     = sum(1 for r in h2h if r["home"] + r["away"] > 3.5)
    avg_g   = sum(r["home"] + r["away"] for r in h2h) / n

    return {
        "n": n, "avg_goals": round(avg_g, 2),
        "w1":        round(home_w / n, 3),
        "draw":      round(draws  / n, 3),
        "w2":        round(away_w / n, 3),
        "btts_yes":  round(btts   / n, 3),
        "btts_no":   round((n - btts) / n, 3),
        "over_1_5":  round(o15    / n, 3),
        "under_1_5": round((n - o15) / n, 3),
        "over_2_5":  round(o25    / n, 3),
        "under_2_5": round((n - o25) / n, 3),
        "over_3_5":  round(o35    / n, 3),
        "under_3_5": round((n - o35) / n, 3),
    }


def _nba_freqs(h2h: list) -> dict:
    n = len(h2h)
    if n == 0:
        return {}

    home_w  = sum(1 for r in h2h if r["home"] > r["away"])
    away_w  = n - home_w
    totals  = [r["home"] + r["away"] for r in h2h]
    avg_t   = sum(totals) / n

    return {
        "n": n, "avg_total": round(avg_t, 1),
        "w1": round(home_w / n, 3),
        "w2": round(away_w / n, 3),
        # Over/Under frequencies dynamically computed per line in analyze()
        "_totals": totals,
    }


# ── Soccer analysis ────────────────────────────────────────────────────────────

SOCCER_MARKETS = [
    ("w1",        "Home Win (W1)"),
    ("draw",      "Draw (X)"),
    ("w2",        "Away Win (W2)"),
    ("btts_yes",  "BTTS Yes"),
    ("btts_no",   "BTTS No"),
    ("over_1_5",  "Over 1.5"),
    ("under_1_5", "Under 1.5"),
    ("over_2_5",  "Over 2.5"),
    ("under_2_5", "Under 2.5"),
    ("over_3_5",  "Over 3.5"),
    ("under_3_5", "Under 3.5"),
]


def analyze_soccer(data: dict) -> dict:
    h2h      = data["h2h"]
    freqs    = _soccer_freqs(h2h)
    bankroll = data["bankroll"]
    ctx      = {**data["context"],
                "home_team": data["home_team"],
                "away_team": data["away_team"]}
    issues   = check_rules(ctx)

    # Build skip + downgrade maps from rule issues
    skip_set   = set()
    dg_map     = {}
    for issue in issues:
        skip_set.update(issue.get("skip", []))
        for mkt, n in issue.get("downgrade", {}).items():
            dg_map[mkt] = dg_map.get(mkt, 0) + n

    markets = []
    odds    = data["odds"]

    for key, label in SOCCER_MARKETS:
        if key not in odds:
            continue
        freq     = freqs.get(key, 0)
        odds_val = odds[key]
        ev_val   = calc_ev(freq, odds_val)
        raw_t    = ev_to_tier(ev_val)

        if key in skip_set:
            adj_t  = "SKIP"
            reason = "Skipped by rules engine"
        else:
            adj_t  = raw_t
            n_dg   = dg_map.get(key, 0)
            for _ in range(n_dg):
                adj_t = downgrade(adj_t)
            reason = f"Downgraded {n_dg}× by rules" if n_dg > 0 else None

        stake = get_stake(adj_t, bankroll)
        rec   = ("BET" if adj_t in ("S","A","B")
                 else "CONSIDER" if adj_t == "C"
                 else "SKIP")

        markets.append({
            "key": key, "label": label,
            "freq": freq, "odds": odds_val, "ev": ev_val,
            "raw_tier": raw_t, "adj_tier": adj_t,
            "stake": stake, "rec": rec, "reason": reason,
        })

    markets.sort(key=lambda x: x["ev"], reverse=True)

    # Rule 22 — top 2 non-skip recs
    recs = [m for m in markets if m["rec"] in ("BET", "CONSIDER")][:2]

    return {
        "game":        f"{data['home_team']} vs {data['away_team']}",
        "sport":       "soccer",
        "competition": data["competition"],
        "h2h_n":       freqs.get("n", 0),
        "avg_goals":   freqs.get("avg_goals", 0),
        "freqs":       freqs,
        "warnings":    [i["msg"] for i in issues],
        "markets":     markets,
        "recs":        recs,
        "bankroll":    bankroll,
        "mode":        bankroll_mode(bankroll),
        "total_exp":   sum(m["stake"] for m in recs),
    }


# ── NBA analysis ───────────────────────────────────────────────────────────────

def analyze_nba(data: dict) -> dict:
    h2h      = data["h2h"]
    freqs    = _nba_freqs(h2h)
    bankroll = data["bankroll"]
    ctx      = {**data["context"],
                "home_team": data["home_team"],
                "away_team": data["away_team"]}
    issues   = check_rules(ctx)

    skip_set = set()
    dg_map   = {}
    for issue in issues:
        skip_set.update(issue.get("skip", []))
        for mkt, n in issue.get("downgrade", {}).items():
            dg_map[mkt] = dg_map.get(mkt, 0) + n

    markets = []
    odds    = data["odds"]
    totals  = freqs.get("_totals", [])
    n       = freqs.get("n", 1) or 1
    total_line = odds.get("over_line") or odds.get("under_line", 0)

    # W1 / W2
    for key, label in [("w1","Home Win (ML)"), ("w2","Away Win (ML)")]:
        if key not in odds:
            continue
        freq     = freqs.get(key, 0)
        odds_val = odds[key]
        _add_market(markets, key, label, freq, odds_val, skip_set, dg_map, bankroll)

    # Over / Under — use the actual line
    if "over" in odds and total_line:
        freq = sum(1 for t in totals if t > total_line) / n if totals else 0
        _add_market(markets, "over", f"Over {total_line}", freq, odds["over"], skip_set, dg_map, bankroll)
    if "under" in odds and total_line:
        freq = sum(1 for t in totals if t < total_line) / n if totals else 0
        _add_market(markets, "under", f"Under {total_line}", freq, odds["under"], skip_set, dg_map, bankroll)

    # Handicap
    for key, label in [("hc_fav","Handicap (Fav)"), ("hc_dog","Handicap (Dog)")]:
        if key not in odds:
            continue
        # Without historical margin data, use market implied probability as proxy
        implied = 1 / odds[key]
        _add_market(markets, key, label, implied, odds[key], skip_set, dg_map, bankroll)

    markets.sort(key=lambda x: x["ev"], reverse=True)
    recs = [m for m in markets if m["rec"] in ("BET","CONSIDER")][:2]

    return {
        "game":        f"{data['home_team']} vs {data['away_team']}",
        "sport":       "nba",
        "competition": "NBA",
        "h2h_n":       freqs.get("n", 0),
        "avg_total":   freqs.get("avg_total", 0),
        "freqs":       freqs,
        "warnings":    [i["msg"] for i in issues],
        "markets":     markets,
        "recs":        recs,
        "bankroll":    bankroll,
        "mode":        bankroll_mode(bankroll),
        "total_exp":   sum(m["stake"] for m in recs),
    }


# ── NHL analysis ──────────────────────────────────────────────────────────────

def _nhl_freqs(h2h: list) -> dict:
    n = len(h2h)
    if n == 0:
        return {}

    home_w  = sum(1 for r in h2h if r["home"] > r["away"])
    away_w  = n - home_w
    totals  = [r["home"] + r["away"] for r in h2h]
    avg_t   = sum(totals) / n
    margins = [abs(r["home"] - r["away"]) for r in h2h]
    close   = sum(1 for m in margins if m <= 1)  # games within 1 goal

    o55 = sum(1 for t in totals if t > 5.5)
    o65 = sum(1 for t in totals if t > 6.5)
    bts = sum(1 for r in h2h if r["home"] > 0 and r["away"] > 0)

    return {
        "n": n, "avg_total": round(avg_t, 1),
        "w1": round(home_w / n, 3),
        "w2": round(away_w / n, 3),
        "over_5_5": round(o55 / n, 3),
        "under_5_5": round((n - o55) / n, 3),
        "over_6_5": round(o65 / n, 3),
        "under_6_5": round((n - o65) / n, 3),
        "bts_yes": round(bts / n, 3),
        "h2h_close_pct": round(close / n, 3),
        "_totals": totals,
    }


def analyze_nhl(data: dict) -> dict:
    h2h      = data["h2h"]
    freqs    = _nhl_freqs(h2h)
    bankroll = data["bankroll"]
    ctx      = {
        **data["context"],
        "sport": "nhl",
        "home_team": data["home_team"],
        "away_team": data["away_team"],
        "h2h_count": len(h2h),
        "h2h_close_pct": freqs.get("h2h_close_pct", 0),
    }
    issues   = check_rules(ctx)

    skip_set = set()
    dg_map   = {}
    for issue in issues:
        skip_set.update(issue.get("skip", []))
        for mkt, n in issue.get("downgrade", {}).items():
            dg_map[mkt] = dg_map.get(mkt, 0) + n

    markets = []
    odds    = data["odds"]
    totals  = freqs.get("_totals", [])
    n       = freqs.get("n", 1) or 1

    # W1 / W2
    for key, label in [("w1", "Home Win (ML)"), ("w2", "Away Win (ML)")]:
        if key in odds:
            _add_market(markets, key, label, freqs.get(key, 0), odds[key], skip_set, dg_map, bankroll)

    # Over/Under 5.5
    if "over_5_5" in odds:
        _add_market(markets, "over_5_5", "Over 5.5", freqs.get("over_5_5", 0), odds["over_5_5"], skip_set, dg_map, bankroll)
    if "under_5_5" in odds:
        _add_market(markets, "under_5_5", "Under 5.5", freqs.get("under_5_5", 0), odds["under_5_5"], skip_set, dg_map, bankroll)

    # Over/Under 6.5
    if "over_6_5" in odds:
        _add_market(markets, "over_6_5", "Over 6.5", freqs.get("over_6_5", 0), odds["over_6_5"], skip_set, dg_map, bankroll)
    if "under_6_5" in odds:
        _add_market(markets, "under_6_5", "Under 6.5", freqs.get("under_6_5", 0), odds["under_6_5"], skip_set, dg_map, bankroll)

    # Puck line -1.5 (favourite) / +1.5 (underdog)
    if "puck_line_fav" in odds:
        # H2H: how often did the home team win by 2+?
        pl_freq = sum(1 for r in h2h if r["home"] - r["away"] >= 2) / n if h2h else 0
        _add_market(markets, "puck_line_fav", "Puck Line -1.5 (Home)", pl_freq, odds["puck_line_fav"], skip_set, dg_map, bankroll)
    if "puck_line_dog" in odds:
        pl_dog_freq = sum(1 for r in h2h if r["away"] - r["home"] >= 2 or r["home"] - r["away"] <= 1) / n if h2h else 0
        _add_market(markets, "puck_line_dog", "Puck Line +1.5 (Away)", pl_dog_freq, odds["puck_line_dog"], skip_set, dg_map, bankroll)

    # Both teams score
    if "bts_yes" in odds:
        _add_market(markets, "bts_yes", "Both Teams Score", freqs.get("bts_yes", 0), odds["bts_yes"], skip_set, dg_map, bankroll)

    markets.sort(key=lambda x: x["ev"], reverse=True)
    recs = [m for m in markets if m["rec"] in ("BET", "CONSIDER")][:2]

    return {
        "game":             f"{data['home_team']} vs {data['away_team']}",
        "sport":            "nhl",
        "competition":      "NHL",
        "h2h_n":            freqs.get("n", 0),
        "avg_total":        freqs.get("avg_total", 0),
        "h2h_close_pct":    freqs.get("h2h_close_pct", 0),
        "freqs":            freqs,
        "warnings":         [i["msg"] for i in issues],
        "markets":          markets,
        "recs":             recs,
        "bankroll":         bankroll,
        "mode":             bankroll_mode(bankroll),
        "total_exp":        sum(m["stake"] for m in recs),
    }


def _add_market(markets, key, label, freq, odds_val, skip_set, dg_map, bankroll):
    ev_val = calc_ev(freq, odds_val)
    raw_t  = ev_to_tier(ev_val)

    if key in skip_set:
        adj_t  = "SKIP"
        reason = "Skipped by rules engine"
    else:
        adj_t = raw_t
        n_dg  = dg_map.get(key, 0)
        for _ in range(n_dg):
            adj_t = downgrade(adj_t)
        reason = f"Downgraded {n_dg}×" if n_dg > 0 else None

    stake = get_stake(adj_t, bankroll)
    rec   = ("BET" if adj_t in ("S","A","B")
             else "CONSIDER" if adj_t == "C"
             else "SKIP")

    markets.append({
        "key": key, "label": label,
        "freq": freq, "odds": odds_val, "ev": ev_val,
        "raw_tier": raw_t, "adj_tier": adj_t,
        "stake": stake, "rec": rec, "reason": reason,
    })
