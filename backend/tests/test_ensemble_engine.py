from datetime import date

from ensemble_engine import EnsemblePredictor, compute_metrics


def _fight(first, second, result, method="U-DEC"):
    return {
        "fighter_1": first,
        "fighter_2": second,
        "result": result,
        "method": method,
        "event_date": date(2020, 1, 1),
    }


def test_ensemble_predicts_and_returns_probabilities():
    fights = []
    for index in range(12):
        fights.append(_fight("Finisher", f"Opponent {index}", "win", "KO/TKO Punches"))
        fights.append(_fight(f"Opponent {index}", f"Journeyman {index}", "win"))

    predictor = EnsemblePredictor()
    predictor.fit(fights)
    result = compute_metrics(predictor, [("Finisher", "New Fighter", -110, -110)])[0]

    assert result["predWinner"] == 1
    assert 0.0 < result["modelProb1"] < 1.0
    assert result["predMethod"] == "KO/TKO"


def test_method_prediction_uses_global_smoothing_for_unknown_fighter():
    predictor = EnsemblePredictor()
    predictor.fit([
        _fight("Known Fighter", "Opponent", "win", "SUB Rear Naked Choke"),
        _fight("Known Fighter", "Opponent 2", "win", "SUB Armbar"),
    ])

    method, probability = predictor.method_prediction("Unknown Fighter", "Opponent")
    assert method == "Submission"
    assert 0.0 < probability <= 1.0
