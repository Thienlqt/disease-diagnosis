from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AnswerState(str, Enum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    UNCLEAR = "unclear"
    UNKNOWN = "unknown"
    DECLINED = "declined"


class SessionState(str, Enum):
    IN_PROGRESS = "in_progress"
    URGENT_HANDOFF = "urgent_handoff"
    COMPLETED = "completed"
    STOPPED = "stopped"


class Reporter(str, Enum):
    PATIENT = "patient"
    CAREGIVER = "caregiver"


class Symptom(str, Enum):
    COUGH = "cough"
    SORE_THROAT = "sore_throat"


@dataclass(frozen=True)
class QuestionDefinition:
    id: str
    information_type: str
    wording: str
    clarification: str
    applicable_symptoms: tuple[str, ...]
    per_symptom: bool
    source: str
    review_status: str


@dataclass
class Message:
    id: str
    role: str
    content: str
    created_at: str = field(default_factory=utc_now)
    question_definition_id: str | None = None
    target_symptom: str | None = None


@dataclass
class QuestionAsked:
    id: str
    definition_id: str
    target_symptom: str | None
    exact_wording: str
    asked_at: str
    message_id: str
    associated_message_ids: list[str] = field(default_factory=list)


@dataclass
class PatientFact:
    id: str
    information_type: str
    symptom: str | None
    value: Any
    answer_state: AnswerState
    source_message_id: str
    reporter: str | None
    reported_at: str = field(default_factory=utc_now)
    described_time: str | None = None
    superseded: bool = False
    supersedes_fact_id: str | None = None
    relationship: str = "observation"
    interpretation_method: str = "deterministic"


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    patient_age: int | None = None
    reporter: Reporter | None = None
    symptoms: set[str] = field(default_factory=set)
    facts: list[PatientFact] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    questions_asked: list[QuestionAsked] = field(default_factory=list)
    current_question_asked_id: str | None = None
    state: SessionState = SessionState.IN_PROGRESS
    ending_reason: str | None = None
    setup_stage: str = "reporter"
    content_version: str = "draft-question-bank-2026-09-16"
    workflow_version: str = "deterministic-workflow-0.1.0"
    model_runtime: str | None = None
    model_calls: int = 0
    model_failures: int = 0

    def add_message(
        self,
        role: str,
        content: str,
        question_definition_id: str | None = None,
        target_symptom: str | None = None,
    ) -> Message:
        message = Message(
            id=str(uuid4()),
            role=role,
            content=content,
            question_definition_id=question_definition_id,
            target_symptom=target_symptom,
        )
        self.messages.append(message)
        return message

    def current_fact(self, information_type: str, symptom: str | None = None) -> PatientFact | None:
        matches = [
            fact
            for fact in self.facts
            if fact.information_type == information_type
            and fact.symptom == symptom
            and not fact.superseded
        ]
        return matches[-1] if matches else None

    def question_asked(self, asked_id: str | None = None) -> QuestionAsked | None:
        target_id = asked_id or self.current_question_asked_id
        return next((item for item in self.questions_asked if item.id == target_id), None)
