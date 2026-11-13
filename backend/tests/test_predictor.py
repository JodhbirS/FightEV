from datetime import date

import pytest

from ensemble_engine import EloLogisticPredictor, compute_metrics, implied_prob


def _fight(first, second, result, method="U-DEC"):
    return {
        "fighter_1": first,
        "fighter_2": second,
        "result": result,
        "method": method,
        "event_date": date(2020, 1, 1),
    }


def test_elo_logistic_predicts_and_returns_probabilities():
    fights = []
    for index in range(12):
        fights.append(_fight("Finisher", f"Opponent {index}", "win", "KO/TKO Punches"))
        fights.append(_fight(f"Opponent {index}", f"Journeyman {index}", "win"))

    predictor = EloLogisticPredictor()
    predictor.fit(fights)
    result = compute_metrics(predictor, [("Finisher", "New Fighter", -110, -110)])[0]

    assert result["predWinner"] == 1
    assert 0.0 < result["modelProb1"] < 1.0
    assert result["predMethod"] == "KO/TKO"


def test_method_prediction_uses_global_smoothing_for_unknown_fighter():
    predictor = EloLogisticPredictor()
    predictor.fit([
        _fight("Known Fighter", "Opponent", "win", "SUB Rear Naked Choke"),
        _fight("Known Fighter", "Opponent 2", "win", "SUB Armbar"),
    ])

    method, probability = predictor.method_prediction("Unknown Fighter", "Opponent")
    assert method == "Submission"
    assert 0.0 < probability <= 1.0


def test_elo_update_respects_loss_result():
    predictor = EloLogisticPredictor()
    predictor.fit([
        _fight("First Fighter", "Second Fighter", "loss"),
        _fight("First Fighter", "Third Fighter", "win"),
    ])

    assert predictor.profiles["First Fighter"].elo < predictor.profiles["Second Fighter"].elo


def test_ev_uses_expected_return_with_market_anchor():
    predictor = EloLogisticPredictor()
    predictor.fit([
        _fight("First Fighter", "Second Fighter", "win"),
        _fight("First Fighter", "Third Fighter", "loss"),
    ])

    result = compute_metrics(predictor, [("First Fighter", "Second Fighter", -110, -110)])[0]
    market_probability = implied_prob(-110)
    expected_probability = 0.8 * result["modelProb1"] + 0.2 * 0.5
    expected_ev = expected_probability * (1 / market_probability) - 1

    assert result["ev1"] == pytest.approx(expected_ev)
    assert result["ev1"] != pytest.approx(result["modelProb1"] - market_probability)
