import math
from collections import defaultdict


def get_method_factor(method: str, rnd: int = 1) -> float:
    """
    Scale the K-factor based on method and round of victory:
      - Round 1 Finish (KO/TKO/SUB): 1.25x (dominant, early finish)
      - Round 2 Finish: 1.15x
      - Round 3+ Finish: 1.08x
      - Unanimous Decision (U-DEC): 1.00x
      - Majority Decision (M-DEC): 0.95x
      - Split Decision (S-DEC): 0.85x (high variance / razor-close bout)
    """
    m = str(method).upper()
    if "KO" in m or "SUB" in m:
        if rnd == 1:
            return 1.25
        elif rnd == 2:
            return 1.15
        else:
            return 1.08
    elif "S-DEC" in m or "SPLIT" in m:
        return 0.85
    elif "M-DEC" in m or "MAJORITY" in m:
        return 0.95
    elif "U-DEC" in m or "UNANIMOUS" in m:
        return 1.00
    return 1.00


class UFCEloEngine:
    def __init__(
        self,
        initial_elo: float = 1000.0,
        base_k: float = 40.0,
    ):
        self.initial_elo = initial_elo
        self.base_k = base_k

        self.ratings = defaultdict(lambda: self.initial_elo)
        self.bouts = defaultdict(int)

    def _expected(self, ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def _k(self, fighter: str, method: str, rnd: int) -> float:
        k = self.base_k / math.sqrt(max(1, self.bouts[fighter]))
        return k * get_method_factor(method, rnd)

    def process_single_fight(self, row):
        """Process a single fight row (needs .fighter_1, .fighter_2, .result, .method, .round attrs)."""
        f1, f2 = row.fighter_1, row.fighter_2
        res = str(row.result).lower()
        method = getattr(row, "method", "")
        rnd = getattr(row, "round", 1)
        try:
            rnd = int(rnd)
        except Exception:
            rnd = 1

        ra, rb = self.ratings[f1], self.ratings[f2]
        ea = self._expected(ra, rb)
        eb = 1.0 - ea

        if res == "win":
            sa, sb = 1.0, 0.0
        elif res == "draw":
            sa, sb = 0.5, 0.5
        else:
            sa, sb = 0.0, 0.0

        k1 = self._k(f1, method, rnd)
        k2 = self._k(f2, method, rnd)

        self.ratings[f1] = round(ra + k1 * (sa - ea), 2)
        self.ratings[f2] = round(rb + k2 * (sb - eb), 2)

        self.bouts[f1] += 1
        self.bouts[f2] += 1

    def get_rating(self, fighter: str) -> float:
        """Get current rating."""
        return self.ratings[fighter]

    def win_prob(self, f1: str, f2: str) -> float:
        return self._expected(self.get_rating(f1), self.get_rating(f2))


def implied_prob(odds: int) -> float:
    """
    Convert odds to implied probability (0-1).
      +200 → 100 / (200 + 100) = 0.3333
      -150 → 150 / (150 + 100) = 0.6000
    """
    return (100 / (odds + 100)) if odds > 0 else (-odds / (-odds + 100))


def calculate_kelly_unit(win_prob: float, odds: int, fraction: float = 0.25) -> float:
    """
    Calculate suggested bet sizing in units using a conservative Quarter-Kelly Criterion (0.25x).
    Returns suggested unit size rounded to 1 decimal place (e.g., 0.5u - 2.5u).
    Returns 0.0 if EV is negative or zero.
    """
    if win_prob <= 0 or win_prob >= 1:
        return 0.0
    b = (odds / 100.0) if odds > 0 else (100.0 / abs(odds))
    q = 1.0 - win_prob
    kelly_full = (b * win_prob - q) / b
    if kelly_full <= 0:
        return 0.0
    unit = round(min(3.0, max(0.1, kelly_full * fraction * 10.0)), 1)
    return unit


def compute_metrics(
    engine: UFCEloEngine,
    fights: list[tuple[str, str, int, int]],
) -> list[dict]:
    """Compute Elo probabilities, implied probabilities, EV, and Kelly unit sizing for fights."""
    results = []
    for f1, f2, o1, o2 in fights:
        p1 = engine.win_prob(f1, f2)
        p2 = 1.0 - p1
        imp1 = implied_prob(o1)
        imp2 = implied_prob(o2)
        ev1 = p1 - imp1
        ev2 = p2 - imp2
        pred = 1 if p1 >= p2 else 2
        kelly1 = calculate_kelly_unit(p1, o1) if ev1 > 0 else 0.0
        kelly2 = calculate_kelly_unit(p2, o2) if ev2 > 0 else 0.0
        results.append({
            "fighter1": f1,
            "fighter2": f2,
            "odds1": o1,
            "odds2": o2,
            "eloProb1": p1,
            "eloProb2": p2,
            "impProb1": imp1,
            "impProb2": imp2,
            "ev1": ev1,
            "ev2": ev2,
            "predWinner": pred,
            "kelly1": kelly1,
            "kelly2": kelly2,
        })
    return results
