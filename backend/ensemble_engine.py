"""Elo-plus-logistic predictor trained from chronological UFC fight data."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

METHOD_CATEGORIES = ("KO/TKO", "Submission", "Decision", "Other")


def categorize_method(method: str) -> str:
    normalized = str(method).upper()
    if "SUB" in normalized:
        return "Submission"
    if "KO" in normalized or "TKO" in normalized:
        return "KO/TKO"
    if "DEC" in normalized:
        return "Decision"
    return "Other"


def implied_prob(odds: int) -> float:
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def calculate_kelly_unit(win_prob: float, odds: int, fraction: float = 0.25) -> float:
    if not 0 < win_prob < 1:
        return 0.0
    b = odds / 100 if odds > 0 else 100 / abs(odds)
    kelly = (b * win_prob - (1 - win_prob)) / b
    return round(min(3.0, max(0.1, kelly * fraction * 10)), 1) if kelly > 0 else 0.0


@dataclass
class FighterProfile:
    wins: int = 0
    losses: int = 0
    elo: float = 1000.0
    last_date: date | None = None
    recent_results: list[int] = field(default_factory=list)
    methods_won: Counter = field(default_factory=Counter)
    methods_lost: Counter = field(default_factory=Counter)

    @property
    def experience(self) -> int:
        return self.wins + self.losses

    def features(self, today: date) -> tuple[float, ...]:
        total = max(1, self.experience)
        recent = self.recent_results[-5:]
        finishes = self.methods_won["KO/TKO"] + self.methods_won["Submission"]
        days = (today - self.last_date).days if self.last_date else 3650
        return (
            self.wins / total,
            sum(recent) / len(recent) if recent else 0.5,
            finishes / total,
            self.methods_won["KO/TKO"] / total,
            self.methods_won["Submission"] / total,
            min(self.experience, 10),
            float(days),
        )


class EloLogisticPredictor:
    """Use Elo as the primary signal and logistic regression for adjustment."""

    initial_elo = 1000.0
    base_k = 40.0

    def __init__(self):
        self.profiles: dict[str, FighterProfile] = defaultdict(FighterProfile)
        self.global_methods = Counter()
        self.global_loss_methods = Counter()
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=1000),
        )
        self.trained = False

    @staticmethod
    def _expected(first_elo: float, second_elo: float) -> float:
        return 1.0 / (1.0 + 10 ** ((second_elo - first_elo) / 400.0))

    def _features(
        self,
        first: FighterProfile,
        second: FighterProfile,
        event_date: date | None,
    ) -> list[float]:
        today = event_date or date.today()
        left, right = first.features(today), second.features(today)
        return (
            [first.elo - second.elo]
            + [a - b for a, b in zip(left, right)]
        )

    def _update(
        self,
        first: FighterProfile,
        second: FighterProfile,
        result: str,
        method: str,
        event_date: date | None,
    ) -> None:
        expected_first = self._expected(first.elo, second.elo)
        k_first = self.base_k / (max(1, first.experience) ** 0.5)
        k_second = self.base_k / (max(1, second.experience) ** 0.5)
        score_first = 1.0 if result == "win" else 0.0
        score_second = 1.0 - score_first
        first.elo += k_first * (score_first - expected_first)
        second.elo += k_second * (score_second - (1.0 - expected_first))

        if result == "win":
            first.wins += 1
            second.losses += 1
            first.recent_results.append(1)
            second.recent_results.append(0)
            category = categorize_method(method)
            first.methods_won[category] += 1
            second.methods_lost[category] += 1
            self.global_methods[category] += 1
            self.global_loss_methods[category] += 1
        elif result == "loss":
            first.losses += 1
            second.wins += 1
            first.recent_results.append(0)
            second.recent_results.append(1)
            category = categorize_method(method)
            second.methods_won[category] += 1
            first.methods_lost[category] += 1
            self.global_methods[category] += 1
            self.global_loss_methods[category] += 1
        else:
            return

        first.recent_results = first.recent_results[-10:]
        second.recent_results = second.recent_results[-10:]
        first.last_date = event_date or first.last_date
        second.last_date = event_date or second.last_date

    def fit(self, fights: list[dict]) -> None:
        rows, labels = [], []
        for fight in fights:
            if fight["result"] not in {"win", "loss"}:
                continue
            first = self.profiles[fight["fighter_1"]]
            second = self.profiles[fight["fighter_2"]]
            rows.append(self._features(first, second, fight["event_date"]))
            labels.append(1 if fight["result"] == "win" else 0)
            rows.append(self._features(second, first, fight["event_date"]))
            labels.append(0 if fight["result"] == "win" else 1)
            self._update(first, second, fight["result"], fight["method"], fight["event_date"])
        if len(set(labels)) < 2:
            raise ValueError("Elo-plus-logistic model requires both win and loss outcomes")
        self.model.fit(np.asarray(rows), np.asarray(labels))
        self.trained = True

    def win_probability(self, first_name: str, second_name: str) -> float:
        if not self.trained:
            raise RuntimeError("Predictor has not been trained")
        first = self.profiles[first_name]
        second = self.profiles[second_name]
        return float(self.model.predict_proba(
            np.asarray([self._features(first, second, date.today())])
        )[0, 1])

    @staticmethod
    def _distribution(
        counts: Counter,
        totals: Counter,
        categories: tuple[str, ...],
    ) -> dict[str, float]:
        total = sum(totals.values())
        prior = {
            category: (totals[category] + 2) / (total + 2 * len(categories))
            for category in categories
        }
        observed = sum(counts.values())
        return {
            category: (counts[category] + 3 * prior[category]) / (observed + 3)
            for category in categories
        }

    def method_prediction(self, winner: str, opponent: str) -> tuple[str, float]:
        offense = self._distribution(
            self.profiles[winner].methods_won,
            self.global_methods,
            METHOD_CATEGORIES,
        )
        defense = self._distribution(
            self.profiles[opponent].methods_lost,
            self.global_loss_methods,
            METHOD_CATEGORIES,
        )
        probabilities = {
            category: (offense[category] + defense[category]) / 2
            for category in METHOD_CATEGORIES
        }
        category = max(probabilities, key=probabilities.get)
        return category, probabilities[category]


def compute_metrics(
    predictor: EloLogisticPredictor,
    fights: list[tuple[str, str, int, int]],
) -> list[dict]:
    results = []
    for first, second, odds1, odds2 in fights:
        p1 = predictor.win_probability(first, second)
        p2 = 1.0 - p1
        imp1, imp2 = implied_prob(odds1), implied_prob(odds2)
        pred = 1 if p1 >= p2 else 2
        winner, opponent = (first, second) if pred == 1 else (second, first)
        method, method_prob = predictor.method_prediction(winner, opponent)
        ev1, ev2 = p1 - imp1, p2 - imp2
        results.append({
            "fighter1": first, "fighter2": second, "odds1": odds1, "odds2": odds2,
            "modelProb1": p1, "modelProb2": p2, "impProb1": imp1, "impProb2": imp2,
            "ev1": ev1, "ev2": ev2, "predWinner": pred, "predMethod": method,
            "predMethodProb": method_prob,
            "kelly1": calculate_kelly_unit(p1, odds1) if ev1 > 0 else 0.0,
            "kelly2": calculate_kelly_unit(p2, odds2) if ev2 > 0 else 0.0,
        })
    return results


def _american_to_decimal(odds: int) -> float:
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))


def _parlay(legs: list[dict], mode: str) -> dict:
    probability = float(np.prod([leg["modelProbability"] for leg in legs]))
    decimal_odds = float(np.prod([_american_to_decimal(leg["odds"]) for leg in legs]))
    return {
        "mode": mode,
        "legs": legs,
        "estimatedProbability": probability,
        "combinedDecimalOdds": decimal_odds,
        "combinedAmericanOdds": round((decimal_odds - 1) * 100) if decimal_odds >= 2 else round(-100 / (decimal_odds - 1)),
    }


def build_parlay_summary(fights: list[dict]) -> dict:
    candidates = []
    for fight in fights:
        winner_index = fight["predWinner"] - 1
        candidates.append({
            "fighter": fight[f"fighter{winner_index + 1}"],
            "odds": fight[f"odds{winner_index + 1}"],
            "modelProbability": fight[f"modelProb{winner_index + 1}"],
            "impliedProbability": fight[f"impProb{winner_index + 1}"],
            "ev": fight[f"ev{winner_index + 1}"],
            "methodAngle": fight["predMethod"],
            "methodProbability": fight["predMethodProb"],
        })

    top_candidates = [candidate for candidate in candidates if candidate["modelProbability"] >= 0.55]
    top_pick = max(
        top_candidates or candidates,
        key=lambda candidate: (candidate["ev"], candidate["modelProbability"]),
        default=None,
    )
    conservative = sorted(candidates, key=lambda candidate: candidate["modelProbability"], reverse=True)[:2]
    balanced_pool = [candidate for candidate in candidates if candidate["ev"] > 0]
    balanced = sorted(
        balanced_pool or candidates,
        key=lambda candidate: candidate["ev"] + candidate["modelProbability"],
        reverse=True,
    )[:3]
    aggressive = sorted(candidates, key=lambda candidate: candidate["ev"], reverse=True)[:4]
    for leg in aggressive:
        leg["methodAngleIncluded"] = leg["methodProbability"] >= 0.65
    return {
        "topPick": top_pick,
        "parlays": [
            _parlay(conservative, "Conservative"),
            _parlay(balanced, "Balanced"),
            _parlay(aggressive, "Aggressive"),
        ],
    }
