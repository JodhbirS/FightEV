import math
from collections import defaultdict

class UFCEloEngine:
    def __init__(
        self,
        initial_elo: float = 1000.0,
        base_k: float = 40.0,
        method_boost: float = 1.15,
    ):
        self.initial_elo = initial_elo
        self.base_k = base_k
        self.method_boost = method_boost

        self.ratings = defaultdict(lambda: self.initial_elo)
        self.bouts = defaultdict(int)

    def _expected(self, ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def _k(self, fighter: str, method: str) -> float:
        k = self.base_k / math.sqrt(max(1, self.bouts[fighter]))
        m = method.upper()
        if "KO" in m or "SUB" in m:
            k *= self.method_boost
        return k

    def process_fights(self, df):
        for row in df.itertuples(index=False):
            f1, f2 = row.fighter_1, row.fighter_2
            res = row.result.lower()
            method = getattr(row, "method", "")

            _ = self.ratings[f1]; _ = self.ratings[f2]

            ra, rb = self.ratings[f1], self.ratings[f2]
            ea = self._expected(ra, rb)
            eb = 1.0 - ea

            if res == "win":
                sa, sb = 1.0, 0.0
            elif res == "draw":
                sa, sb = 0.5, 0.5
            else:
                sa, sb = 0.0, 0.0

            k1 = self._k(f1, method)
            k2 = self._k(f2, method)

            self.ratings[f1] = round(ra + k1 * (sa - ea), 2)
            self.ratings[f2] = round(rb + k2 * (sb - eb), 2)

            self.bouts[f1] += 1
            self.bouts[f2] += 1

    def process_single_fight(self, row):
        """Process a single fight row (needs .fighter_1, .fighter_2, .result, .method attrs)."""
        f1, f2 = row.fighter_1, row.fighter_2
        res = row.result.lower()
        method = getattr(row, "method", "")

        _ = self.ratings[f1]; _ = self.ratings[f2]

        ra, rb = self.ratings[f1], self.ratings[f2]
        ea = self._expected(ra, rb)
        eb = 1.0 - ea

        if res == "win":
            sa, sb = 1.0, 0.0
        elif res == "draw":
            sa, sb = 0.5, 0.5
        else:
            sa, sb = 0.0, 0.0

        k1 = self._k(f1, method)
        k2 = self._k(f2, method)

        self.ratings[f1] = round(ra + k1 * (sa - ea), 2)
        self.ratings[f2] = round(rb + k2 * (sb - eb), 2)

        self.bouts[f1] += 1
        self.bouts[f2] += 1

    def get_rating(self, fighter: str) -> float:
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
