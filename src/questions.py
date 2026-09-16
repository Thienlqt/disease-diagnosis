from __future__ import annotations

import json
from importlib.resources import files

from .models import QuestionDefinition, Session


def load_question_bank() -> list[QuestionDefinition]:
    path = files("src.data").joinpath("question_bank.json")
    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        QuestionDefinition(
            id=item["id"],
            information_type=item["information_type"],
            wording=item["wording"],
            clarification=item["clarification"],
            applicable_symptoms=tuple(item["applicable_symptoms"]),
            per_symptom=item["per_symptom"],
            source=item["source"],
            review_status=item["review_status"],
        )
        for item in records
    ]


def applicable_question_targets(
    session: Session, definitions: list[QuestionDefinition]
) -> list[tuple[QuestionDefinition, str | None]]:
    queue: list[tuple[QuestionDefinition, str | None]] = []
    symptom_order = [item for item in ("cough", "sore_throat") if item in session.symptoms]
    for definition in definitions:
        if definition.id == "Q01":
            continue
        if definition.applicable_symptoms and not session.symptoms.intersection(
            definition.applicable_symptoms
        ):
            continue
        targets: list[str | None] = symptom_order if definition.per_symptom else [None]
        for target in targets:
            queue.append((definition, target))
    return queue
