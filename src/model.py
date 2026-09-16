from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .models import AnswerState


ALLOWED_INFORMATION_TYPES = {
    "age",
    "breathing_difficulty",
    "swallow_saliva",
    "onset",
    "progression",
    "temperature",
    "runny_nose",
    "fluid_intake",
    "urination_change",
    "medical_conditions",
    "medicines",
    "smoke_dust_exposure",
}

BOOLEAN_INFORMATION_TYPES = {
    "breathing_difficulty",
    "swallow_saliva",
    "runny_nose",
    "smoke_dust_exposure",
}

MODEL_ID = "qwen2.5-3b-instruct-q4_k_m"
_UNSET = object()


@dataclass(frozen=True)
class ProposedFactUpdate:
    information_type: str
    symptom: str | None
    value: Any
    answer_state: str
    source_quote: str


class FactInterpreter(Protocol):
    runtime_name: str

    def interpret_answer(
        self,
        *,
        question_id: str,
        information_type: str,
        symptom: str | None,
        question_wording: str,
        user_message: str,
    ) -> ProposedFactUpdate | None: ...


class LlamaCppError(RuntimeError):
    """A local inference failure that must not be treated as a patient fact."""


class LlamaCppClient:
    """Narrow local client for schema-constrained fact extraction."""

    runtime_name = "llama.cpp/Qwen2.5-3B-Instruct-Q4_K_M"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8081/v1",
        *,
        model: str = MODEL_ID,
        timeout_seconds: float = 30.0,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        key_file = Path(__file__).resolve().parents[1] / "models" / ".llama_api_key"
        self.api_key = api_key or os.environ.get("DISEASE_MVP_LLAMA_API_KEY") or (
            key_file.read_text(encoding="utf-8").strip() if key_file.exists() else "no-key"
        )
        self.last_update: ProposedFactUpdate | None = None
        self.last_rejection_reason: str | None = None

    def is_available(self) -> bool:
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        try:
            request = urllib.request.Request(f"{root}/health", method="GET")
            with urllib.request.urlopen(request, timeout=2.0) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def interpret_answer(
        self,
        *,
        question_id: str,
        information_type: str,
        symptom: str | None,
        question_wording: str,
        user_message: str,
    ) -> ProposedFactUpdate | None:
        self.last_update = None
        self.last_rejection_reason = None
        canonical = {
            "breathing_difficulty": "boolean: true means difficulty is present; false means breathing is normal",
            "swallow_saliva": "boolean: true means able to swallow saliva; false means unable",
            "progression": "one of: better, worse, same",
            "runny_nose": "boolean: true means present; false means absent",
            "fluid_intake": "one of: usual, reduced, increased",
            "urination_change": "one of: no change, less, more",
            "smoke_dust_exposure": "boolean: true means exposed; false means not exposed",
            "temperature": "an object with measured boolean and, when measured, numeric reading and C or F unit",
        }.get(information_type, "preserve the user's stated value without adding detail")
        prompt = (
            "Extract only the answer to the current symptom question. Do not diagnose, give advice, "
            "apply urgency rules, or invent missing details. source_quote must be an exact contiguous "
            "substring of the user message. State rules: answered means the message gives a usable answer, "
            "including an indirect paraphrase; unknown means the person says they do not know; declined "
            "means they refuse or prefer not to answer; unclear is only for a genuinely ambiguous message. "
            "Use null for unknown or declined values. Examples: 'easing up' is answered/better; "
            "'breathing feels normal' is answered/false for breathing difficulty; 'rather not answer' is "
            "declined/null.\n\n"
            f"Question ID: {question_id}\n"
            f"Information type: {information_type}\n"
            f"Target symptom: {symptom or 'none'}\n"
            f"Canonical value: {canonical}\n"
            f"Question: {question_wording}\n"
            f"User message: {user_message}"
        )
        value_schema = self._value_schema(information_type)
        schema = {
            "type": "object",
            "properties": {
                "information_type": {"type": "string", "enum": [information_type]},
                "symptom": {"type": "string", "enum": [symptom]},
                "value": value_schema,
                "answer_state": {
                    "type": "string",
                    "enum": ["answered", "unclear", "unknown", "declined"],
                },
                "source_quote": {"type": "string"},
            },
            "required": [
                "information_type",
                "symptom",
                "value",
                "answer_state",
                "source_quote",
            ],
            "additionalProperties": False,
        }
        if symptom is None:
            schema["properties"]["symptom"] = {"type": "null"}
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a constrained information extractor. Return only schema-valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "patient_fact_update",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            content = response_data["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
            answer_state = parsed["answer_state"]
            value = parsed.get("value")
            if answer_state in {AnswerState.UNKNOWN.value, AnswerState.DECLINED.value} and value == "null":
                value = None
            update = ProposedFactUpdate(
                information_type=parsed["information_type"],
                symptom=parsed.get("symptom"),
                value=value,
                answer_state=answer_state,
                source_quote=parsed["source_quote"],
            )
            self.last_update = update
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            urllib.error.URLError,
            urllib.error.HTTPError,
        ) as exc:
            raise LlamaCppError(f"local model request failed: {type(exc).__name__}") from exc

        valid, reason = validate_model_update(
            update,
            user_message,
            expected_information_type=information_type,
            expected_symptom=symptom,
        )
        self.last_rejection_reason = None if valid else reason
        return update if valid else None

    @staticmethod
    def _value_schema(information_type: str) -> dict[str, Any]:
        if information_type in BOOLEAN_INFORMATION_TYPES:
            return {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
        if information_type == "progression":
            return {"anyOf": [{"type": "string", "enum": ["better", "worse", "same"]}, {"type": "null"}]}
        if information_type == "fluid_intake":
            return {"anyOf": [{"type": "string", "enum": ["usual", "reduced", "increased"]}, {"type": "null"}]}
        if information_type == "urination_change":
            return {"anyOf": [{"type": "string", "enum": ["no change", "less", "more"]}, {"type": "null"}]}
        if information_type == "age":
            return {"anyOf": [{"type": "integer", "minimum": 0, "maximum": 130}, {"type": "null"}]}
        if information_type == "temperature":
            return {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "measured": {"type": "boolean"},
                            "reading": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                            "unit": {"anyOf": [{"type": "string", "enum": ["C", "F"]}, {"type": "null"}]},
                            "measurement_time": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        },
                        "required": ["measured", "reading", "unit", "measurement_time"],
                        "additionalProperties": False,
                    },
                    {"type": "null"},
                ]
            }
        return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def validate_model_update(
    update: ProposedFactUpdate,
    user_message: str,
    *,
    expected_information_type: str | None = None,
    expected_symptom: str | None | object = _UNSET,
) -> tuple[bool, str]:
    """Reject malformed/out-of-scope model proposals before application state can use them."""
    if update.information_type not in ALLOWED_INFORMATION_TYPES:
        return False, "information type is not in the question bank"
    if update.symptom not in {None, "cough", "sore_throat"}:
        return False, "target symptom is invalid"
    if update.answer_state not in {item.value for item in AnswerState}:
        return False, "answer state is invalid"
    if update.answer_state == AnswerState.UNANSWERED.value:
        return False, "a model proposal cannot mark a prompted field unanswered"
    if expected_information_type and update.information_type != expected_information_type:
        return False, "information type does not match the current question"
    if expected_symptom is not _UNSET and update.symptom != expected_symptom:
        return False, "target symptom does not match the current question"
    if not update.source_quote or update.source_quote not in user_message:
        return False, "source quote is not present in the user message"
    if update.answer_state in {AnswerState.UNKNOWN.value, AnswerState.DECLINED.value} and update.value is not None:
        return False, "unknown and declined updates cannot contain an inferred value"
    if update.answer_state == AnswerState.ANSWERED.value:
        if update.information_type in BOOLEAN_INFORMATION_TYPES and not isinstance(update.value, bool):
            return False, "this answered information type requires a boolean value"
        if update.information_type == "progression" and update.value not in {"better", "worse", "same"}:
            return False, "progression must be better, worse, or same"
        if update.information_type == "fluid_intake" and update.value not in {
            "usual",
            "reduced",
            "increased",
        }:
            return False, "fluid intake must be usual, reduced, or increased"
        if update.information_type == "urination_change" and update.value not in {
            "no change",
            "less",
            "more",
        }:
            return False, "urination change must be no change, less, or more"
        if update.information_type == "temperature":
            if not isinstance(update.value, dict) or not isinstance(update.value.get("measured"), bool):
                return False, "temperature requires a structured measured value"
            if update.value["measured"] and (
                not isinstance(update.value.get("reading"), (int, float))
                or update.value.get("unit") not in {"C", "F"}
            ):
                return False, "a measured temperature requires a reading and C or F unit"
    return True, "valid candidate; application rules must still decide whether to accept it"
