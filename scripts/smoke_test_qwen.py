from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.engine import ConversationEngine  # noqa: E402
from src.model import LlamaCppClient  # noqa: E402


def main() -> None:
    client = LlamaCppClient()
    if not client.is_available():
        raise SystemExit("llama.cpp health check failed")

    cases = [
        {
            "name": "progression paraphrase",
            "kwargs": {
                "question_id": "Q05",
                "information_type": "progression",
                "symptom": "cough",
                "question_wording": "Is the cough getting better, getting worse, or staying about the same?",
                "user_message": "It seems to be easing up today.",
            },
            "expected": {"answer_state": "answered", "value": "better"},
        },
        {
            "name": "breathing paraphrase",
            "kwargs": {
                "question_id": "Q02",
                "information_type": "breathing_difficulty",
                "symptom": None,
                "question_wording": "Is the patient having any difficulty breathing right now?",
                "user_message": "Not really; breathing feels normal to me.",
            },
            "expected": {"answer_state": "answered", "value": False},
        },
        {
            "name": "declined medicine",
            "kwargs": {
                "question_id": "Q11",
                "information_type": "medicines",
                "symptom": None,
                "question_wording": "Is the patient currently taking any medicines?",
                "user_message": "I'd rather not answer that.",
            },
            "expected": {"answer_state": "declined", "value": None},
        },
    ]

    outcomes = []
    for case in cases:
        started = perf_counter()
        update = client.interpret_answer(**case["kwargs"])
        latency = perf_counter() - started
        raw_update = update or client.last_update
        observed = None if raw_update is None else {
            "answer_state": raw_update.answer_state,
            "value": raw_update.value,
            "source_quote": raw_update.source_quote,
            "rejection_reason": client.last_rejection_reason,
        }
        passed = bool(update) and all(
            getattr(update, key) == value for key, value in case["expected"].items()
        )
        outcomes.append(
            {"case": case["name"], "passed": passed, "latency_seconds": round(latency, 3), "observed": observed}
        )

    engine = ConversationEngine(interpreter=client)
    engine.start()
    for answer in ("patient", "30", "cough", "no", "two days ago"):
        engine.respond(answer)
    engine_response = engine.respond("It seems to be easing up today.")
    fact = engine.session.current_fact("progression", "cough")
    engine_passed = bool(fact) and fact.value == "better" and fact.interpretation_method.startswith("llama.cpp/")
    outcomes.append(
        {
            "case": "engine integration",
            "passed": engine_passed,
            "model_calls": engine.session.model_calls,
            "model_failures": engine.session.model_failures,
            "next_prompt": engine_response,
        }
    )

    print(json.dumps(outcomes, indent=2))
    if not all(item["passed"] for item in outcomes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
