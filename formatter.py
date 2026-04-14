"""Format analysis result → Telegram-ready Markdown string."""


def format_result(result: dict) -> str:
    sport = result["sport"]
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    mode_icon = {"NORMAL": "✅", "CAUTION": "⚠️", "PAUSE": "🚨"}.get(result["mode"], "⚠️")
    lines += [
        f"🎯 *{result['game']}*",
        f"_{result['competition']} | {result['h2h_n']} H2H games"
        + (f" | Avg goals: {result['avg_goals']}" if sport == "soccer"
           else f" | Avg total: {result.get('avg_total',0)}")
        + "_",
        "",
    ]

    # ── Warnings ──────────────────────────────────────────────────────────────
    if result["warnings"]:
        lines.append("*⚠️ RULE WARNINGS*")
        for w in result["warnings"]:
            lines.append(w)
        lines.append("")

    # ── H2H summary ───────────────────────────────────────────────────────────
    f = result["freqs"]
    n = result["h2h_n"]
    if sport == "soccer" and n:
        lines += [
            "*📊 H2H FREQUENCIES*",
            "```",
            f"Home Win : {f['w1']*100:>4.0f}%  ({round(f['w1']*n)}/{n})",
            f"Draw     : {f['draw']*100:>4.0f}%  ({round(f['draw']*n)}/{n})",
            f"Away Win : {f['w2']*100:>4.0f}%  ({round(f['w2']*n)}/{n})",
            f"Over 2.5 : {f['over_2_5']*100:>4.0f}%  ({round(f['over_2_5']*n)}/{n})",
            f"Under 2.5: {f['under_2_5']*100:>4.0f}%  ({round(f['under_2_5']*n)}/{n})",
            f"BTTS Yes : {f['btts_yes']*100:>4.0f}%  ({round(f['btts_yes']*n)}/{n})",
            f"BTTS No  : {f['btts_no']*100:>4.0f}%  ({round(f['btts_no']*n)}/{n})",
            "```", "",
        ]
    elif sport == "nba" and n:
        lines += [
            "*📊 H2H FREQUENCIES*",
            "```",
            f"Home Win : {f['w1']*100:>4.0f}%  ({round(f['w1']*n)}/{n})",
            f"Away Win : {f['w2']*100:>4.0f}%  ({round(f['w2']*n)}/{n})",
            f"Avg Total: {f.get('avg_total',0)}",
            "```", "",
        ]
    elif sport == "nhl" and n:
        close_pct = result.get("h2h_close_pct", 0)
        lines += [
            "*📊 H2H FREQUENCIES*",
            "```",
            f"Home Win  : {f['w1']*100:>4.0f}%  ({round(f['w1']*n)}/{n})",
            f"Away Win  : {f['w2']*100:>4.0f}%  ({round(f['w2']*n)}/{n})",
            f"Over 5.5  : {f.get('over_5_5',0)*100:>4.0f}%  ({round(f.get('over_5_5',0)*n)}/{n})",
            f"Over 6.5  : {f.get('over_6_5',0)*100:>4.0f}%  ({round(f.get('over_6_5',0)*n)}/{n})",
            f"BTS Yes   : {f.get('bts_yes',0)*100:>4.0f}%  ({round(f.get('bts_yes',0)*n)}/{n})",
            f"Close (≤1): {close_pct*100:>4.0f}%  (OT/SO risk indicator)",
            f"Avg Goals : {f.get('avg_total',0)}",
            "```", "",
        ]

    # ── Markets table ─────────────────────────────────────────────────────────
    markets = result["markets"]
    if markets:
        lines.append("*📈 ALL MARKETS — sorted by EV*")
        lines.append("```")
        lines.append(f"{'Market':<14} {'Freq':>5} {'Odds':>6} {'EV':>5} {'Tier':>6} {'¥Stake':>6}")
        lines.append("─" * 48)
        for m in markets:
            t = m["adj_tier"]
            t_str = (t + "↓" if m["reason"] and "Downgraded" in (m["reason"] or "")
                     else t + "⛔" if t == "SKIP" and m["raw_tier"] != "SKIP"
                     else t)
            lines.append(
                f"{m['label']:<14} {m['freq']*100:>4.0f}% {m['odds']:>6.3f} "
                f"{m['ev']:>5.2f} {t_str:>6} {m['stake']:>5,}"
            )
        lines.append("```")
        lines.append("")

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = result["recs"]
    if recs:
        lines.append("*✅ RECOMMENDED BETS  (Rule 22: max 2/game)*")
        for i, r in enumerate(recs, 1):
            lines.append(
                f"{i}. *{r['label']}* @ `{r['odds']}`  →  *{r['stake']:,} JPY*\n"
                f"   Tier: {r['adj_tier']} | EV: {r['ev']:.2f} | H2H: {r['freq']*100:.0f}%"
                + (f"\n   _{r['reason']}_" if r["reason"] else "")
            )
        lines += [
            "",
            f"💰 *Total exposure: {result['total_exp']:,} JPY*",
        ]
    else:
        lines.append("❌ *No positive-EV bets found — SKIP this game.*")

    # ── Bankroll status ───────────────────────────────────────────────────────
    mode = result["mode"]
    bank = result["bankroll"]
    lines += [
        "",
        f"{mode_icon} *{mode} MODE*  |  Bankroll: {bank:,.0f} JPY",
    ]
    if mode == "CAUTION":
        lines.append("_All tiers downgraded 1 level (bankroll < 90k)_")
    elif mode == "PAUSE":
        lines.append("_🚨 Bankroll < 80k — STOP BETTING until reassessed_")

    return "\n".join(lines)[:4096]


def format_help() -> str:
    return """
⚽🏀🏒 *BETTING ANALYZER BOT*

*Commands:*
`/soccer` — Analyze a soccer match
`/nba`    — Analyze an NBA game
`/nhl`    — Analyze an NHL game
`/fetch`  — Auto-fetch match data (soccer/NBA/NHL)
`/status` — Show bankroll & daily limits
`/setbank 101000` — Update your bankroll
`/log`    — View recent P&L log
`/help`   — Show this menu

*Soccer input format:*
```
/soccer
Arsenal vs Bournemouth
EPL
H2H: 1-2, 2-0, 3-1, 1-1, 2-2, 0-1
Home inj: Saka, White
Away inj: Cook
Relegation: none
UCL: no
Fwd: home
W1:1.48  X:4.2  W2:6.5
BTTS+:1.65  BTTS-:2.1
O2.5:2.378  U2.5:1.58
Bank: 84000
```

*NBA input format:*
```
/nba
Lakers vs Warriors
H2H: 112-98, 105-110, 119-115, 108-103, 122-118
Home inj: LeBron
Away inj: Curry
Last day: no
Spread: -5.5
W1:1.95  W2:1.87
O224.5:1.91  U224.5:1.91
HC1-5.5:1.95  HC2+5.5:1.87
Bank: 101000
```

*NHL input format:*
```
/nhl
Boston Bruins vs Toronto Maple Leafs
H2H: 3-2, 4-1, 2-3, 1-2, 3-1, 2-4
Home inj: Pastrnak, McAvoy
Away inj: Matthews, Marner
B2B: no
Backup goalie: away
Playoffs: no
W1:1.95  W2:1.90
PL-1.5:3.80  PL+1.5:1.22
O5.5:1.85  U5.5:1.95
O6.5:2.10  U6.5:1.72
Bank: 90000
```

*Fetch command:*
`/fetch Arsenal vs Bournemouth EPL`
`/fetch Lakers vs Warriors NBA`
`/fetch Bruins vs Maple Leafs NHL`

*Soccer context flags:*
• `Relegation: home/away/both/none`
• `UCL: no/knockout/first-leg`
• `Fwd: home/away/both/none`
• `Def missing: home/away/both`
• `Last day: yes/no` (NBA end of season)
• `B2B: home/away/both/no` (NHL back-to-back)
• `Backup goalie: home/away/both/no` (NHL)
""".strip()
