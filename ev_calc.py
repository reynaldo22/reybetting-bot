"""EV Calculator + Tier System"""

TIERS = ["S", "A", "B", "C", "SKIP"]

NORMAL_STAKES  = {"S": 3000, "A": 2000, "B": 1500, "C": 1000, "SKIP": 0}
CAUTION_STAKES = {"S": 2000, "A": 1500, "B": 1000, "C":  500, "SKIP": 0}  # bankroll < 90k


def calc_ev(freq: float, odds: float) -> float:
    return round(freq * odds, 3)


def ev_to_tier(ev: float) -> str:
    if ev >= 1.70: return "S"
    if ev >= 1.50: return "A"
    if ev >= 1.30: return "B"
    if ev >= 1.10: return "C"
    return "SKIP"


def get_stake(tier: str, bankroll: float) -> int:
    pool = CAUTION_STAKES if bankroll < 90_000 else NORMAL_STAKES
    return pool.get(tier, 0)


def downgrade(tier: str, n: int = 1) -> str:
    idx = TIERS.index(tier) if tier in TIERS else len(TIERS) - 1
    return TIERS[min(idx + n, len(TIERS) - 1)]


def bankroll_mode(bankroll: float) -> str:
    if bankroll >= 90_000: return "NORMAL"
    if bankroll >= 80_000: return "CAUTION"
    return "PAUSE"
