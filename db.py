"""Simple SQLite P&L logger."""

import sqlite3, os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "bets.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            game      TEXT,
            market    TEXT,
            odds      REAL,
            stake     INTEGER,
            result    TEXT,
            pnl       REAL,
            bankroll  REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            val TEXT
        )
    """)
    c.commit()
    return c


def get_bankroll(default: float = 100_000) -> float:
    with _conn() as c:
        row = c.execute("SELECT val FROM config WHERE key='bankroll'").fetchone()
        return float(row[0]) if row else default


def set_bankroll(amount: float):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO config VALUES ('bankroll', ?)", (str(amount),))
        c.commit()


def log_bet(game: str, market: str, odds: float, stake: int,
            result: str, pnl: float, bankroll: float):
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO bets (ts,game,market,odds,stake,result,pnl,bankroll) VALUES (?,?,?,?,?,?,?,?)",
            (ts, game, market, odds, stake, result, pnl, bankroll)
        )
        c.commit()


def recent_bets(n: int = 10) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT ts,game,market,odds,stake,result,pnl FROM bets ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return rows


def format_log(rows: list) -> str:
    if not rows:
        return "No bets logged yet."
    lines = ["*📋 RECENT BETS*", "```"]
    total_pnl = 0
    for ts, game, market, odds, stake, result, pnl in rows:
        icon  = "✅" if result == "WIN" else "❌" if result == "LOSS" else "↩️"
        date  = ts[:10]
        lines.append(f"{icon} {date} {game[:18]}")
        lines.append(f"   {market} @ {odds} | {stake:,}¥ | {pnl:+,.0f}¥")
        total_pnl += pnl
    lines.append("```")
    lines.append(f"*Net ({len(rows)} bets): {total_pnl:+,.0f} JPY*")
    return "\n".join(lines)
