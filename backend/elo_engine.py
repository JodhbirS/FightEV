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


def apply_inactivity_decay(current_elo: float, last_fight_idx: int | None, current_fight_idx: int) -> float:
    """
    Apply mild regression towards the baseline rating (1000.0) if a fighter has
    been inactive for > 450 UFC fights (~12 months).
    """
    if last_fight_idx is None:
        return current_elo
    gap = current_fight_idx - last_fight_idx
    INACTIVITY_THRESHOLD = 450
    if gap > INACTIVITY_THRESHOLD:
        # Number of inactivity periods (each ~100 fights = ~2.5 months)
        periods = min(15.0, (gap - INACTIVITY_THRESHOLD) / 100.0)
        decay = 0.985 ** periods
        return 1000.0 + (current_elo - 1000.0) * decay
    return current_elo


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
        self.last_fight = {}
        self.fight_counter = 0

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

        self.fight_counter += 1
        current_idx = self.fight_counter

        # Apply mild ring rust / inactivity decay before fight
        ra = apply_inactivity_decay(self.ratings[f1], self.last_fight.get(f1), current_idx)
        rb = apply_inactivity_decay(self.ratings[f2], self.last_fight.get(f2), current_idx)

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

        self.last_fight[f1] = current_idx
        self.last_fight[f2] = current_idx
        self.bouts[f1] += 1
        self.bouts[f2] += 1

    def get_rating(self, fighter: str) -> float:
        """Get current rating with up-to-date inactivity decay applied."""
        current_idx = self.fight_counter
        return apply_inactivity_decay(self.ratings[fighter], self.last_fight.get(fighter), current_idx)

    def win_prob(self, f1: str, f2: str) -> float:
        return self._expected(self.get_rating(f1), self.get_rating(f2))


def implied_prob(odds: int) -> float:
    """
    Convert odds to implied probability (0-1).
      +200 → 100 / (200 + 100) = 0.3333
      -150 → 150 / (150 + 100) = 0.6000
    """
    return (100 / (odds + 100)) if odds > 0 else (-odds / (-odds + 100))


def compute_metrics(
    engine: UFCEloEngine,
    fights: list[tuple[str, str, int, int]],
) -> list[dict]:
    """Compute Elo probabilities, implied probabilities, and EV for a list of fights."""
    results = []
    for f1, f2, o1, o2 in fights:
        p1 = engine.win_prob(f1, f2)
        p2 = 1.0 - p1
        imp1 = implied_prob(o1)
        imp2 = implied_prob(o2)
        ev1 = p1 - imp1
        ev2 = p2 - imp2
        pred = 1 if p1 >= p2 else 2
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
        })
    return results
