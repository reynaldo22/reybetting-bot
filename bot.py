#!/usr/bin/env python3
"""
BETTING ANALYZER TELEGRAM BOT
Send match data from your phone → get EV analysis + tier recommendations back.

SETUP:
1. Copy .env.example → .env and fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
2. pip install -r requirements.txt
3. python3 bot.py
"""

import os, sys, logging, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
    from telegram.constants import ParseMode
except ImportError:
    print("Run: pip install python-telegram-bot==22.5")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv()

from parser    import parse_soccer, parse_nba
from analyzer  import analyze_soccer, analyze_nba
from formatter import format_result, format_help
from db        import get_bankroll, set_bankroll, log_bet, recent_bets, format_log
from ev_calc   import bankroll_mode

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TOKEN:
    print("ERROR: Set TELEGRAM_BOT_TOKEN environment variable")
    sys.exit(1)


# ── Auth ──────────────────────────────────────────────────────────────────────

async def auth(update: Update) -> bool:
    if CHAT_ID and str(update.effective_chat.id) != str(CHAT_ID):
        await update.message.reply_text("⛔ Unauthorized.")
        return False
    return True


# ── /start + /help ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    bankroll = get_bankroll()
    mode     = bankroll_mode(bankroll)
    mode_icon = {"NORMAL":"✅","CAUTION":"⚠️","PAUSE":"🚨"}.get(mode,"⚠️")
    await update.message.reply_text(
        f"🎯 *BETTING ANALYZER ONLINE*\n\n"
        f"{mode_icon} Status: *{mode}*  |  Bankroll: *{bankroll:,.0f} JPY*\n\n"
        f"Use /help to see input formats.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    await update.message.reply_text(format_help(), parse_mode=ParseMode.MARKDOWN)


# ── /soccer ───────────────────────────────────────────────────────────────────

async def cmd_soccer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return

    # Body can be inline (/soccer Arsenal vs ...) or on next lines
    full_text = update.message.text or ""
    # Strip the command itself
    body = full_text[full_text.find("\n"):].strip() if "\n" in full_text else ""
    # Fallback: treat everything after /soccer as body
    if not body:
        parts = full_text.split(None, 1)
        body  = parts[1].strip() if len(parts) > 1 else ""

    if not body or len(body) < 5:
        await update.message.reply_text(
            "Send match data after /soccer\n\n" + format_help(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    msg = await update.message.reply_text("⏳ Analyzing...")

    try:
        # Use stored bankroll as default if not provided in input
        if "bank" not in body.lower():
            body += f"\nBank: {get_bankroll()}"

        data   = parse_soccer(body)
        result = analyze_soccer(data)
        text   = format_result(result)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}\n\nCheck your input format. Use /help for the template.")


# ── /nba ──────────────────────────────────────────────────────────────────────

async def cmd_nba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return

    full_text = update.message.text or ""
    body = full_text[full_text.find("\n"):].strip() if "\n" in full_text else ""
    if not body:
        parts = full_text.split(None, 1)
        body  = parts[1].strip() if len(parts) > 1 else ""

    if not body or len(body) < 5:
        await update.message.reply_text(
            "Send match data after /nba\n\n" + format_help(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    msg = await update.message.reply_text("⏳ Analyzing NBA game...")

    try:
        if "bank" not in body.lower():
            body += f"\nBank: {get_bankroll()}"

        data   = parse_nba(body)
        result = analyze_nba(data)
        text   = format_result(result)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}\n\nCheck your input format. Use /help for the template.")


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    bankroll = get_bankroll()
    mode     = bankroll_mode(bankroll)
    mode_icon = {"NORMAL":"✅","CAUTION":"⚠️","PAUSE":"🚨"}.get(mode,"⚠️")

    lines = [
        f"📊 *BANKROLL STATUS*",
        f"{mode_icon} Mode: *{mode}*",
        f"💰 Balance: *{bankroll:,.0f} JPY*",
        "",
        "*Thresholds:*",
        f"  ✅ Normal  : ≥ 90,000 JPY",
        f"  ⚠️ Caution : < 90,000 JPY  (tiers downgraded)",
        f"  🛑 Pause   : < 80,000 JPY  (stop betting)",
        f"  ❌ Hard Stop: < 70,000 JPY",
        "",
        "*Daily Limits:*",
        f"  ⚽ Soccer : 10,000 JPY (all leagues combined)",
        f"  🏀 NBA    : 15,000 JPY",
        "",
        "*Position Sizing (Normal mode):*",
        f"  S-tier: 3,000 JPY  (90%+ confidence)",
        f"  A-tier: 2,000 JPY  (75-89%)",
        f"  B-tier: 1,500 JPY  (60-74%)",
        f"  C-tier: 1,000 JPY  (value/spec)",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── /setbank ──────────────────────────────────────────────────────────────────

async def cmd_setbank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/setbank 101000`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        amount = float(args[0].replace(",",""))
        set_bankroll(amount)
        mode = bankroll_mode(amount)
        icon = {"NORMAL":"✅","CAUTION":"⚠️","PAUSE":"🚨"}.get(mode,"⚠️")
        await update.message.reply_text(
            f"{icon} Bankroll updated: *{amount:,.0f} JPY* ({mode} mode)",
            parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text("Invalid amount. Example: `/setbank 101000`", parse_mode=ParseMode.MARKDOWN)


# ── /logbet ───────────────────────────────────────────────────────────────────

async def cmd_logbet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /logbet GAME | MARKET | ODDS | STAKE | WIN/LOSS/PUSH | PNL
    Example: /logbet Fiorentina vs Lazio | BTTS Yes | 1.83 | 2000 | LOSS | -2000
    """
    if not await auth(update): return
    full = update.message.text or ""
    body = full.split(None, 1)[1].strip() if " " in full else ""

    if not body:
        await update.message.reply_text(
            "Usage:\n`/logbet Game | Market | Odds | Stake | WIN/LOSS/PUSH | PnL`\n\n"
            "Example:\n`/logbet Fiorentina vs Lazio | BTTS Yes | 1.83 | 2000 | LOSS | -2000`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    parts = [p.strip() for p in body.split("|")]
    if len(parts) < 6:
        await update.message.reply_text("Need 6 fields: Game | Market | Odds | Stake | Result | PnL")
        return

    try:
        game, market, odds, stake, result, pnl = parts[:6]
        bankroll = get_bankroll()
        new_bank = bankroll + float(pnl)
        log_bet(game, market, float(odds), int(stake), result.upper(), float(pnl), new_bank)
        set_bankroll(new_bank)
        icon = "✅" if result.upper() == "WIN" else "❌" if result.upper() == "LOSS" else "↩️"
        await update.message.reply_text(
            f"{icon} *Logged:* {game}\n"
            f"   {market} @ {odds} | {stake}¥ | {float(pnl):+,.0f}¥\n"
            f"💰 New bankroll: *{new_bank:,.0f} JPY*",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"Error logging bet: {e}")


# ── /log ──────────────────────────────────────────────────────────────────────

async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    n    = int(context.args[0]) if context.args else 10
    rows = recent_bets(n)
    await update.message.reply_text(format_log(rows), parse_mode=ParseMode.MARKDOWN)


# ── Natural language handler ──────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    text = (update.message.text or "").lower().strip()

    intent_map = {
        ("soccer", "football", "epl", "serie a", "la liga", "ucl", "champions"): cmd_soccer,
        ("nba", "basketball", "nba game"):                                         cmd_nba,
        ("status", "bankroll", "balance", "how much"):                             cmd_status,
        ("log", "history", "bets", "recent"):                                      cmd_log,
        ("help", "how", "format", "input"):                                        cmd_help,
    }

    for keywords, handler in intent_map.items():
        if any(kw in text for kw in keywords):
            await handler(update, context)
            return

    await update.message.reply_text(
        "🤖 Not sure what you need. Try:\n"
        "• `/soccer` — analyze a soccer match\n"
        "• `/nba` — analyze an NBA game\n"
        "• `/status` — bankroll status\n"
        "• `/help` — full input format",
        parse_mode=ParseMode.MARKDOWN
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"🎯 Betting Analyzer Bot starting...")
    print(f"Token  : {'SET ✅' if TOKEN else 'MISSING ❌'}")
    print(f"Chat ID: {'SET ✅' if CHAT_ID else 'Open (any user)'}")
    print(f"DB     : {os.path.abspath('bets.db')}")

    # Clear old webhook/polling conflicts
    import urllib.request, urllib.parse
    try:
        data = urllib.parse.urlencode({"drop_pending_updates": "true"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
            data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        urllib.request.urlopen(req, timeout=10)
        print("Webhook cleared ✅")
        time.sleep(10)  # wait for Telegram server to close old session
    except Exception as e:
        print(f"Webhook clear skipped: {e}")

    print("Bot running. Send /start to test.\n")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("soccer",  cmd_soccer))
    app.add_handler(CommandHandler("nba",     cmd_nba))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("setbank", cmd_setbank))
    app.add_handler(CommandHandler("logbet",  cmd_logbet))
    app.add_handler(CommandHandler("log",     cmd_log))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
