"""CPU-only ensemble predictor trained from chronological UFC fight data."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from math import exp

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

METHOD_CATEGORIES = ("KO/TKO", "Submission", "Decision", "Other")
FEATURE_NAMES = (
    "experience_diff", "win_rate_diff", "recent_win_rate_diff",
    "finish_rate_diff", "ko_rate_diff", "submission_rate_diff",
    "activity_diff", "days_since_fight_diff", "division_same",
)


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
    last_date: date | None = None
    recent_results: list[int] = field(default_factory=list)
    methods_won: Counter = field(default_factory=Counter)
    total_fights: int = 0

    @property
    def experience(self) -> int:
        return self.wins + self.losses

    def features(self, today: date) -> tuple[float, ...]:
        total = max(1, self.experience)
        recent = self.recent_results[-5:]
        finishes = self.methods_won["KO/TKO"] + self.methods_won["Submission"]
        days = (today - self.last_date).days if self.last_date else 3650
        return (
            float(self.experience),
            self.wins / total,
            sum(recent) / len(recent) if recent else 0.5,
            finishes / total,
            self.methods_won["KO/TKO"] / total,
            self.methods_won["Submission"] / total,
            min(self.experience, 10),
            float(days),
        )


class EnsemblePredictor:
    """Blend logistic regression, random forest, and histogram boosting."""

    def __init__(self):
        self.profiles: dict[str, FighterProfile] = defaultdict(FighterProfile)
        self.global_methods = Counter()
        self.model = VotingClassifier(
            estimators=[
                ("logistic", make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=1000))),
                ("forest", RandomForestClassifier(
                    n_estimators=250, min_samples_leaf=4, max_features=0.8,
                    random_state=42, n_jobs=1,
                )),
                ("boosting", HistGradientBoostingClassifier(
                    max_iter=150, max_leaf_nodes=15, l2_regularization=1.0,
                    random_state=42,
                )),
            ],
            voting="soft",
            weights=[2, 1, 2],
        )
        self.trained = False

    @staticmethod
    def _features(first: FighterProfile, second: FighterProfile, event_date: date | None,
                  same_division: bool = False) -> list[float]:
        today = event_date or date.today()
        left, right = first.features(today), second.features(today)
        return [a - b for a, b in zip(left, right)] + [float(same_division)]

    def _update(self, first: FighterProfile, second: FighterProfile, result: str,
                method: str, event_date: date | None) -> None:
        if result == "win":
            first.wins += 1
            second.losses += 1
            first.recent_results.append(1)
            second.recent_results.append(0)
            first.methods_won[categorize_method(method)] += 1
        elif result == "loss":
            first.losses += 1
            second.wins += 1
            first.recent_results.append(0)
            second.recent_results.append(1)
            second.methods_won[categorize_method(method)] += 1
        else:
            return
        first.recent_results = first.recent_results[-10:]
        second.recent_results = second.recent_results[-10:]
        first.total_fights += 1
        second.total_fights += 1
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
            self.global_methods[categorize_method(fight["method"])] += 1
        if len(set(labels)) < 2:
            raise ValueError("Ensemble requires both win and loss outcomes")
        self.model.fit(np.asarray(rows), np.asarray(labels))
        self.trained = True

    def win_probability(self, first_name: str, second_name: str) -> float:
        if not self.trained:
            raise RuntimeError("Ensemble predictor has not been trained")
        first = self.profiles[first_name]
        second = self.profiles[second_name]
        return float(self.model.predict_proba(
            np.asarray([self._features(first, second, date.today())])
        )[0, 1])

    def method_prediction(self, winner: str, opponent: str) -> tuple[str, float]:
        profile = self.profiles[winner]
        total = sum(self.global_methods.values())
        prior = {category: (self.global_methods[category] + 2) / (total + 2 * len(METHOD_CATEGORIES))
                 for category in METHOD_CATEGORIES}
        observed = profile.methods_won
        count = profile.experience
        probabilities = {
            category: (observed[category] + 3 * prior[category]) / (count + 3)
            for category in METHOD_CATEGORIES
        }
        category = max(probabilities, key=probabilities.get)
        return category, probabilities[category]


def compute_metrics(predictor: EnsemblePredictor, fights: list[tuple[str, str, int, int]]) -> list[dict]:
    results = []
    for first, second, odds1, odds2 in fights:
        probability = predictor.win_probability(first, second)
        p1, p2 = probability, 1.0 - probability
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
