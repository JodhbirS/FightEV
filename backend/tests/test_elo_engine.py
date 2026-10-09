from types import SimpleNamespace

from elo_engine import UFCEloEngine, compute_metrics


def test_method_prediction_uses_winner_history():
    engine = UFCEloEngine()
    for method in ("KO/TKO Punches", "KO/TKO Head Kick", "U-DEC"):
        engine.process_single_fight(SimpleNamespace(
            fighter_1="Finisher",
            fighter_2=f"Opponent {method}",
            result="win",
            method=method,
            round=1,
        ))

    result = compute_metrics(engine, [("Finisher", "New Fighter", -110, -110)])[0]

    assert result["predWinner"] == 1
    assert result["predMethod"] == "KO/TKO"
    assert 0.0 < result["predMethodProb"] <= 1.0


def test_method_prediction_falls_back_to_global_mix():
    engine = UFCEloEngine()
    engine.process_single_fight(SimpleNamespace(
        fighter_1="Known Fighter",
        fighter_2="Opponent",
        result="win",
        method="SUBMISSION",
        round=1,
    ))

    probabilities = engine.method_probabilities("Unknown Fighter")

    assert sum(probabilities.values()) == 1.0
    assert probabilities["Submission"] > probabilities["KO/TKO"]
