from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from .model import FactInterpreter, LlamaCppError, validate_model_update
from .models import (
    AnswerState,
    PatientFact,
    QuestionAsked,
    Reporter,
    Session,
    SessionState,
    Symptom,
)
from .questions import applicable_question_targets, load_question_bank


UNKNOWN_RE = re.compile(r"\b(?:i\s+don'?t\s+know|not\s+sure|unknown|unsure)\b", re.I)
DECLINED_RE = re.compile(
    r"\b(?:prefer\s+not\s+to\s+(?:answer|say)|don'?t\s+want\s+to\s+(?:answer|say)|decline)\b",
    re.I,
)
YES_RE = re.compile(r"^(?:yes|y|yeah|yep|correct|true)\b", re.I)
NO_RE = re.compile(r"^(?:no|n|nope|false|none)\b", re.I)


class ConversationEngine:
    """Application-owned state machine for one in-memory conversation."""

    def __init__(
        self,
        session: Session | None = None,
        interpreter: FactInterpreter | None = None,
    ) -> None:
        self.session = session or Session()
        self.interpreter = interpreter
        if interpreter:
            self.session.model_runtime = interpreter.runtime_name
        self.questions = load_question_bank()
        self._by_id = {item.id: item for item in self.questions}

    def start(self) -> str:
        if self.session.messages:
            return self.session.messages[-1].content
        return self._assistant(
            "Learning prototype only: this chat does not diagnose disease and its draft "
            "questions and urgent-routing rules have not had clinical review. Do not enter "
            "names, exact addresses, or other identifiers.\n\n"
            "Are you answering for yourself as the patient, or for someone else as a caregiver?"
        )

    def respond(self, text: str) -> str:
        text = text.strip()
        if not text:
            return self._assistant("Please enter a response, or /quit to stop.")

        user_message = self.session.add_message("user", text)

        if text.lower().startswith("/quit"):
            self.session.state = SessionState.STOPPED
            self.session.ending_reason = "user ended the conversation"
            return self._assistant("The conversation has been stopped. Your report can still be exported.")

        if text.lower().startswith("/summary"):
            return self._assistant(self.summary())

        if text.lower().startswith("/correct") or text.lower().startswith("/change"):
            return self._handle_fact_command(text, user_message.id)

        urgent_reason = self._urgent_reason(text)
        if urgent_reason:
            self._record_fact(
                "urgent_concern",
                None,
                urgent_reason,
                AnswerState.ANSWERED,
                user_message.id,
                relationship="observation",
            )
            return self._enter_urgent_handoff(urgent_reason)

        contextual_urgent = self._contextual_urgent_reason(text)
        if contextual_urgent:
            asked = self.session.question_asked()
            if asked:
                definition = self._by_id[asked.definition_id]
                value: Any = True if definition.id == "Q02" else False
                self._record_fact(
                    definition.information_type,
                    asked.target_symptom,
                    value,
                    AnswerState.ANSWERED,
                    user_message.id,
                )
                asked.associated_message_ids.append(user_message.id)
            return self._enter_urgent_handoff(contextual_urgent)

        if self.session.state != SessionState.IN_PROGRESS:
            return self._assistant(
                "This session is no longer asking ordinary questions. Use /summary, export the report, or start a new session."
            )

        self._extract_volunteered_facts(text, user_message.id)

        if self.session.setup_stage != "questions":
            return self._handle_setup(text, user_message.id)

        correction = self._natural_onset_correction(text, user_message.id)
        if correction:
            return correction

        return self._handle_current_answer(text, user_message.id)

    def _handle_setup(self, text: str, message_id: str) -> str:
        self._extract_setup_details(text, message_id)

        if self.session.reporter is None:
            return self._assistant(
                "Please say whether you are the patient or a caregiver answering for someone else."
            )

        if self.session.setup_stage == "reporter":
            self.session.setup_stage = "age"

        age_fact = self.session.current_fact("age")
        if age_fact is None:
            direct_age = re.fullmatch(r"\s*(\d{1,3})\s*(?:years?\s*old)?\s*", text, re.I)
            if direct_age and self.session.setup_stage == "age":
                self._store_age(int(direct_age.group(1)), message_id)
                age_fact = self.session.current_fact("age")
            elif UNKNOWN_RE.search(text):
                self._record_fact("age", None, None, AnswerState.UNKNOWN, message_id)
                return self._stop_outside_scope(
                    "The prototype cannot confirm that the patient is within its age-5-and-older scope."
                )
            elif DECLINED_RE.search(text):
                self._record_fact("age", None, None, AnswerState.DECLINED, message_id)
                return self._stop_outside_scope(
                    "The prototype cannot confirm that the patient is within its age-5-and-older scope."
                )

        age_fact = self.session.current_fact("age")
        if age_fact is None:
            self.session.setup_stage = "age"
            return self._ask_setup("Q01", "How old is the patient, in completed years?")

        if self.session.patient_age is None or self.session.patient_age < 5:
            return self._stop_outside_scope(
                "This learning prototype supports only patients age 5 or older."
            )

        if not self.session.symptoms:
            if self.session.setup_stage == "symptoms" and (
                NO_RE.search(text.strip())
                or re.search(r"\b(?:headache|stomach|rash|injury|earache)\b", text, re.I)
            ):
                return self._stop_outside_scope(
                    "This prototype only supports cough, sore throat, or both."
                )
            self.session.setup_stage = "symptoms"
            return self._assistant(
                "Is the patient reporting a cough, a sore throat, or both?"
            )

        self.session.setup_stage = "questions"
        return self._ask_next_question()

    def _extract_setup_details(self, text: str, message_id: str) -> None:
        lowered = text.lower()
        if self.session.reporter is None:
            if re.search(r"\b(?:caregiver|parent|mother|father|my child|my kid|someone else)\b", lowered):
                self.session.reporter = Reporter.CAREGIVER
                self._record_fact("reporter", None, "caregiver", AnswerState.ANSWERED, message_id)
            elif re.search(r"\b(?:myself|the patient|for me|i am the patient|i'm the patient)\b", lowered) or lowered in {
                "me",
                "patient",
                "myself",
            }:
                self.session.reporter = Reporter.PATIENT
                self._record_fact("reporter", None, "patient", AnswerState.ANSWERED, message_id)

        if self.session.current_fact("age") is None:
            age_match = re.search(
                r"\b(?:i\s*am|i'?m|patient\s+is|child\s+is|age\s+is|aged)\s*(\d{1,3})\b",
                lowered,
            )
            if age_match:
                self._store_age(int(age_match.group(1)), message_id)

        has_cough = bool(re.search(r"\bcough(?:ing)?\b", lowered)) and not bool(
            re.search(r"\bno\s+cough\b", lowered)
        )
        has_sore_throat = bool(re.search(r"\bsore\s+throat\b", lowered)) and not bool(
            re.search(r"\bno\s+sore\s+throat\b", lowered)
        )
        if re.search(r"\bboth\b", lowered):
            has_cough = True
            has_sore_throat = True
        if has_cough:
            self.session.symptoms.add(Symptom.COUGH.value)
        if has_sore_throat:
            self.session.symptoms.add(Symptom.SORE_THROAT.value)

    def _extract_volunteered_facts(self, text: str, message_id: str) -> None:
        """Capture only explicit, low-ambiguity facts offered outside their question."""
        lowered = text.lower()
        asked = self.session.question_asked()
        active_info = self._by_id[asked.definition_id].information_type if asked else None

        if active_info != "breathing_difficulty" and re.search(
            r"\b(?:no|not\s+having|without|don'?t\s+have)\s+(?:any\s+)?(?:difficulty\s+breathing|short(?:ness)?\s+of\s+breath)\b",
            lowered,
        ):
            self._record_fact(
                "breathing_difficulty", None, False, AnswerState.ANSWERED, message_id
            )

        if active_info != "swallow_saliva" and re.search(
            r"\b(?:can|able\s+to)\s+(?:still\s+)?swallow\s+(?:my|their|his|her)?\s*(?:own\s+)?saliva\b",
            lowered,
        ):
            self._record_fact("swallow_saliva", None, True, AnswerState.ANSWERED, message_id)

        if active_info != "runny_nose":
            if re.search(r"\bno\s+runny\s+nose\b", lowered):
                self._record_fact("runny_nose", None, False, AnswerState.ANSWERED, message_id)
            elif re.search(r"\b(?:has|have|with)\s+(?:a\s+)?runny\s+nose\b", lowered):
                self._record_fact("runny_nose", None, True, AnswerState.ANSWERED, message_id)

        if active_info != "temperature":
            reading = re.search(r"\b(?:temperature|temp|fever)\D{0,12}(\d{2,3}(?:\.\d+)?)\s*(?:°\s*)?([cf])\b", lowered)
            if reading:
                self._record_fact(
                    "temperature",
                    None,
                    {
                        "measured": True,
                        "reading": float(reading.group(1)),
                        "unit": reading.group(2).upper(),
                        "measurement_time": self._extract_time_phrase(text),
                        "reported_wording": text,
                    },
                    AnswerState.ANSWERED,
                    message_id,
                )

    def _store_age(self, age: int, message_id: str) -> None:
        self.session.patient_age = age
        self._record_fact("age", None, age, AnswerState.ANSWERED, message_id)

    def _handle_current_answer(self, text: str, message_id: str) -> str:
        asked = self.session.question_asked()
        if asked is None:
            return self._ask_next_question()
        definition = self._by_id[asked.definition_id]
        state, value = self._interpret(definition.id, text, asked.target_symptom)
        interpretation_method = "deterministic"
        if state == AnswerState.UNCLEAR and self.interpreter:
            self.session.model_calls += 1
            try:
                proposal = self.interpreter.interpret_answer(
                    question_id=definition.id,
                    information_type=definition.information_type,
                    symptom=asked.target_symptom,
                    question_wording=asked.exact_wording,
                    user_message=text,
                )
            except LlamaCppError:
                self.session.model_failures += 1
                proposal = None
            if proposal:
                valid, _ = validate_model_update(
                    proposal,
                    text,
                    expected_information_type=definition.information_type,
                    expected_symptom=asked.target_symptom,
                )
                if not valid:
                    self.session.model_failures += 1
                    proposal = None
            if proposal:
                state = AnswerState(proposal.answer_state)
                value = self._normalize_model_value(
                    definition.information_type, proposal.value, proposal.source_quote
                )
                interpretation_method = "llama.cpp/qwen2.5-3b-instruct-q4_k_m"
        self._record_fact(
            definition.information_type,
            asked.target_symptom,
            value,
            state,
            message_id,
            relationship="clarification" if state == AnswerState.UNCLEAR else "observation",
            interpretation_method=interpretation_method,
        )
        asked.associated_message_ids.append(message_id)

        if state == AnswerState.UNCLEAR:
            wording = self._format_wording(definition.clarification, asked.target_symptom)
            return self._ask_existing(asked, wording)

        self.session.current_question_asked_id = None
        return self._ask_next_question()

    def _interpret(
        self, question_id: str, text: str, symptom: str | None
    ) -> tuple[AnswerState, Any]:
        lowered = text.strip().lower()
        if UNKNOWN_RE.search(lowered):
            return AnswerState.UNKNOWN, None
        if DECLINED_RE.search(lowered):
            return AnswerState.DECLINED, None

        if question_id in {"Q02", "Q07", "Q12"}:
            if YES_RE.search(lowered):
                return AnswerState.ANSWERED, True
            if NO_RE.search(lowered) or re.search(
                r"\b(?:don'?t|do\s+not|doesn'?t|does\s+not|isn'?t|is\s+not|wasn'?t|was\s+not)\b",
                lowered,
            ):
                return AnswerState.ANSWERED, False
            return AnswerState.UNCLEAR, text

        if question_id == "Q03":
            if re.search(r"\b(?:can(?:not|'t)|unable\s+to)\s+swallow\b", lowered):
                return AnswerState.ANSWERED, False
            if "pain" in lowered and re.search(r"\b(?:can|able)\s+(?:still\s+)?swallow\b", lowered):
                return AnswerState.ANSWERED, True
            if YES_RE.search(lowered):
                return AnswerState.ANSWERED, True
            if NO_RE.search(lowered):
                return AnswerState.ANSWERED, False
            return AnswerState.UNCLEAR, text

        if question_id == "Q04":
            if len(lowered) < 2:
                return AnswerState.UNCLEAR, text
            return AnswerState.ANSWERED, {"reported_wording": text}

        if question_id == "Q05":
            if re.search(r"\b(?:better|improv(?:e|ing|ed))\b", lowered):
                return AnswerState.ANSWERED, "better"
            if re.search(r"\b(?:worse|worsen(?:ing|ed)|getting bad)\b", lowered):
                return AnswerState.ANSWERED, "worse"
            if re.search(r"\b(?:same|unchanged|stable)\b", lowered):
                return AnswerState.ANSWERED, "same"
            return AnswerState.UNCLEAR, text

        if question_id == "Q06":
            if re.search(r"\b(?:not\s+measured|didn'?t\s+measure|no\s+temperature)\b", lowered):
                return AnswerState.ANSWERED, {"measured": False}
            reading = re.search(r"(?<!\d)(\d{2,3}(?:\.\d+)?)\s*(?:°\s*)?([cf])?\b", lowered)
            if reading:
                value = {
                    "measured": True,
                    "reading": float(reading.group(1)),
                    "unit": reading.group(2).upper() if reading.group(2) else None,
                    "measurement_time": self._extract_time_phrase(text),
                    "reported_wording": text,
                }
                if value["unit"] is None:
                    return AnswerState.UNCLEAR, value
                return AnswerState.ANSWERED, value
            previous = self.session.current_fact("temperature")
            if previous and previous.answer_state == AnswerState.UNCLEAR and isinstance(previous.value, dict):
                unit_match = re.search(r"\b(celsius|fahrenheit|c|f)\b", lowered)
                if unit_match:
                    value = dict(previous.value)
                    value["unit"] = "C" if unit_match.group(1).startswith("c") else "F"
                    return AnswerState.ANSWERED, value
            return AnswerState.UNCLEAR, text

        if question_id == "Q08":
            if re.search(r"\b(?:usual|normal|same)\b", lowered):
                return AnswerState.ANSWERED, "usual"
            if re.search(r"\b(?:less|reduced|hardly|not\s+much)\b", lowered):
                return AnswerState.ANSWERED, "reduced"
            if re.search(r"\b(?:more|increased)\b", lowered):
                return AnswerState.ANSWERED, "increased"
            return AnswerState.UNCLEAR, text

        if question_id == "Q09":
            if re.search(r"\b(?:no\s+change|normal|usual|same)\b", lowered):
                return AnswerState.ANSWERED, "no change"
            if re.search(r"\b(?:less|reduced|decreased|fewer)\b", lowered):
                return AnswerState.ANSWERED, "less"
            if re.search(r"\b(?:more|increased|frequent)\b", lowered):
                return AnswerState.ANSWERED, "more"
            return AnswerState.UNCLEAR, text

        if question_id in {"Q10", "Q11"}:
            if re.search(r"\b(?:none|no\s+(?:conditions|medicines?|medications?))\b", lowered):
                return AnswerState.ANSWERED, "none"
            if len(lowered) >= 2:
                return AnswerState.ANSWERED, text
            return AnswerState.UNCLEAR, text

        return AnswerState.UNCLEAR, text

    def _ask_next_question(self) -> str:
        for definition, target in applicable_question_targets(self.session, self.questions):
            fact = self.session.current_fact(definition.information_type, target)
            if fact and fact.answer_state in {
                AnswerState.ANSWERED,
                AnswerState.UNKNOWN,
                AnswerState.DECLINED,
            }:
                continue
            wording = self._format_wording(definition.wording, target)
            return self._ask_new(definition.id, target, wording)

        self.session.current_question_asked_id = None
        self.session.state = SessionState.COMPLETED
        self.session.ending_reason = "questionnaire completed"
        return self._assistant(self.summary())

    def _ask_setup(self, definition_id: str, wording: str) -> str:
        return self._ask_new(definition_id, None, wording)

    def _ask_new(self, definition_id: str, target: str | None, wording: str) -> str:
        message = self.session.add_message(
            "assistant", wording, question_definition_id=definition_id, target_symptom=target
        )
        asked = QuestionAsked(
            id=str(uuid4()),
            definition_id=definition_id,
            target_symptom=target,
            exact_wording=wording,
            asked_at=message.created_at,
            message_id=message.id,
        )
        self.session.questions_asked.append(asked)
        self.session.current_question_asked_id = asked.id
        return wording

    def _ask_existing(self, asked: QuestionAsked, wording: str) -> str:
        message = self.session.add_message(
            "assistant",
            wording,
            question_definition_id=asked.definition_id,
            target_symptom=asked.target_symptom,
        )
        asked.associated_message_ids.append(message.id)
        return wording

    def _assistant(self, text: str) -> str:
        self.session.add_message("assistant", text)
        return text

    def _record_fact(
        self,
        information_type: str,
        symptom: str | None,
        value: Any,
        answer_state: AnswerState,
        source_message_id: str,
        *,
        relationship: str = "observation",
        interpretation_method: str = "deterministic",
    ) -> PatientFact:
        previous = self.session.current_fact(information_type, symptom)
        supersedes_id = previous.id if previous else None
        if previous and relationship != "change_over_time":
            previous.superseded = True
        fact = PatientFact(
            id=str(uuid4()),
            information_type=information_type,
            symptom=symptom,
            value=value,
            answer_state=answer_state,
            source_message_id=source_message_id,
            reporter=self.session.reporter.value if self.session.reporter else None,
            supersedes_fact_id=supersedes_id,
            relationship=relationship,
            interpretation_method=interpretation_method,
        )
        self.session.facts.append(fact)
        return fact

    def _urgent_reason(self, text: str) -> str | None:
        lowered = text.lower()
        breathing_positive = re.search(
            r"\b(?:can(?:not|'t)\s+breathe|struggl(?:e|ing)\s+to\s+breathe|difficulty\s+breathing|short(?:ness)?\s+of\s+breath)\b",
            lowered,
        )
        breathing_negated = re.search(
            r"\b(?:no|not|without|don'?t\s+have|do\s+not\s+have)\s+(?:any\s+)?(?:current\s+)?(?:difficulty\s+breathing|short(?:ness)?\s+of\s+breath)\b",
            lowered,
        )
        if breathing_positive and not breathing_negated:
            return "reported current breathing difficulty"
        unable_swallow = re.search(
            r"\b(?:can(?:not|'t)|unable\s+to)\s+swallow\s+(?:my|their|his|her)?\s*(?:own\s+)?saliva\b",
            lowered,
        )
        if unable_swallow:
            return "reported inability to swallow saliva"
        return None

    def _contextual_urgent_reason(self, text: str) -> str | None:
        asked = self.session.question_asked()
        if not asked:
            return None
        if asked.definition_id == "Q02" and YES_RE.search(text.strip()):
            return "answered yes to current breathing difficulty"
        if asked.definition_id == "Q03":
            lowered = text.strip().lower()
            if NO_RE.search(lowered) or re.search(r"\b(?:can(?:not|'t)|unable)\b", lowered):
                return "reported inability to swallow saliva"
        return None

    def _enter_urgent_handoff(self, reason: str) -> str:
        self.session.state = SessionState.URGENT_HANDOFF
        self.session.ending_reason = reason
        return self._assistant(
            "URGENT HANDOFF (draft, unreviewed rule): ordinary questions have stopped because the patient "
            f"{reason}. Seek urgent in-person medical help now or contact local emergency services. "
            "Do not wait for this prototype to complete a report or compare facilities. If it is safe to do so, "
            "you can still export the conversation record."
        )

    def _stop_outside_scope(self, reason: str) -> str:
        self.session.state = SessionState.STOPPED
        self.session.ending_reason = reason
        return self._assistant(
            f"{reason} No assessment will be attempted. If there is an emergency concern, seek urgent in-person help now."
        )

    def _handle_fact_command(self, text: str, message_id: str) -> str:
        relationship = "correction" if text.lower().startswith("/correct") else "change_over_time"
        pattern = re.compile(
            r"^/(?:correct|change)\s+([a-z_]+)(?:\s+(cough|sore_throat|sore\s+throat))?\s*:\s*(.+)$",
            re.I,
        )
        match = pattern.match(text)
        allowed = {item.information_type for item in self.questions} | {"reporter"}
        if not match or match.group(1).lower() not in allowed:
            return self._assistant(
                "Use /correct FIELD [cough|sore_throat]: VALUE or /change FIELD [cough|sore_throat]: VALUE. "
                "For example: /correct onset cough: 3 days ago"
            )
        information_type = match.group(1).lower()
        symptom = match.group(2)
        symptom = symptom.lower().replace(" ", "_") if symptom else None
        value = match.group(3).strip()

        if information_type in {"onset", "progression"} and symptom not in self.session.symptoms:
            return self._assistant("That symptom is not part of this session, so the fact was not changed.")

        if information_type == "age":
            age_match = re.fullmatch(r"\d{1,3}", value)
            if not age_match:
                return self._assistant("Age corrections must be a whole number of years.")
            self.session.patient_age = int(value)
            stored_value: Any = self.session.patient_age
        else:
            stored_value = value

        self._record_fact(
            information_type,
            symptom,
            stored_value,
            AnswerState.ANSWERED,
            message_id,
            relationship=relationship,
        )

        if information_type == "breathing_difficulty" and value.lower() in {"yes", "true", "difficulty"}:
            return self._enter_urgent_handoff("corrected current breathing difficulty to yes")
        if information_type == "swallow_saliva" and value.lower() in {"no", "false", "unable"}:
            return self._enter_urgent_handoff("corrected ability to swallow saliva to unable")

        if self.session.state == SessionState.COMPLETED:
            return self._assistant("The fact was updated and its prior value was preserved.\n\n" + self.summary())
        return self._assistant("The fact was updated and its prior value was preserved in the session history.")

    def _natural_onset_correction(self, text: str, message_id: str) -> str | None:
        match = re.search(
            r"\b(?:actually|correction|i\s+meant)\b.*?\b(cough|sore\s+throat)\b.*?\b(?:started|start(?:ed)?)\b\s*(.+)$",
            text,
            re.I,
        )
        if not match:
            return None
        symptom = match.group(1).lower().replace(" ", "_")
        if symptom not in self.session.symptoms:
            return None
        self._record_fact(
            "onset",
            symptom,
            {"reported_wording": match.group(2).strip()},
            AnswerState.ANSWERED,
            message_id,
            relationship="correction",
        )
        return self._assistant(
            f"I updated the {self._label(symptom)} onset and kept the earlier fact in the history. "
            "Please answer the pending question when ready."
        )

    def summary(self) -> str:
        lines = ["Current symptom summary (learning prototype; not a diagnosis):"]
        reporter = self.session.reporter.value if self.session.reporter else "unknown"
        age = str(self.session.patient_age) if self.session.patient_age is not None else "unknown"
        symptoms = ", ".join(self._label(item) for item in sorted(self.session.symptoms)) or "unknown"
        lines.extend(
            [
                f"- Reporter: {reporter}",
                f"- Patient age: {age}",
                f"- Symptoms in scope: {symptoms}",
                f"- Session state: {self.session.state.value.replace('_', ' ')}",
            ]
        )

        for symptom in ("cough", "sore_throat"):
            if symptom not in self.session.symptoms:
                continue
            lines.append(f"- {self._label(symptom).title()}:")
            for information_type in ("onset", "progression"):
                fact = self.session.current_fact(information_type, symptom)
                lines.append(f"  - {information_type.replace('_', ' ')}: {self._fact_display(fact)}")

        excluded = {"age", "reporter", "onset", "progression"}
        seen: set[tuple[str, str | None]] = set()
        for fact in self.session.facts:
            key = (fact.information_type, fact.symptom)
            if fact.superseded or fact.information_type in excluded or key in seen:
                continue
            seen.add(key)
            lines.append(
                f"- {fact.information_type.replace('_', ' ')}: {self._fact_display(fact)}"
            )

        missing = self._missing_items()
        if missing:
            lines.append("- Missing or unresolved: " + ", ".join(missing))
        lines.extend(
            [
                "",
                "Assessment and next step:",
                "- No possible cause is named because no clinically reviewed assessment workflow is active.",
                "- This report can be shared with a qualified clinician; seek appropriate in-person care if concerned.",
            ]
        )
        return "\n".join(lines)

    def _missing_items(self) -> list[str]:
        items: list[str] = []
        if self.session.setup_stage == "questions":
            for definition, target in applicable_question_targets(self.session, self.questions):
                fact = self.session.current_fact(definition.information_type, target)
                if fact is None:
                    label = definition.information_type.replace("_", " ")
                    if target:
                        label += f" ({self._label(target)})"
                    items.append(label)
                elif fact.answer_state in {AnswerState.UNKNOWN, AnswerState.DECLINED, AnswerState.UNCLEAR}:
                    label = f"{definition.information_type.replace('_', ' ')} [{fact.answer_state.value}]"
                    if target:
                        label += f" ({self._label(target)})"
                    items.append(label)
        return items

    @staticmethod
    def _fact_display(fact: PatientFact | None) -> str:
        if fact is None:
            return "unanswered"
        if fact.answer_state != AnswerState.ANSWERED:
            if fact.answer_state == AnswerState.UNCLEAR and fact.value:
                return f"unclear ({fact.value})"
            return fact.answer_state.value
        if isinstance(fact.value, dict):
            if "reported_wording" in fact.value and len(fact.value) == 1:
                return str(fact.value["reported_wording"])
            parts = [f"{key.replace('_', ' ')}={value}" for key, value in fact.value.items() if value is not None]
            return ", ".join(parts)
        if isinstance(fact.value, bool):
            return "yes" if fact.value else "no"
        return str(fact.value)

    @staticmethod
    def _extract_time_phrase(text: str) -> str | None:
        match = re.search(r"\b(?:at|this|last|yesterday)\b.+$", text, re.I)
        return match.group(0) if match else None

    @staticmethod
    def _normalize_model_value(information_type: str, value: Any, source_quote: str) -> Any:
        if information_type == "onset" and not isinstance(value, dict):
            return {"reported_wording": str(value or source_quote)}
        return value

    @staticmethod
    def _format_wording(template: str, symptom: str | None) -> str:
        return template.format(symptom_label=ConversationEngine._label(symptom))

    @staticmethod
    def _label(symptom: str | None) -> str:
        return "sore throat" if symptom == "sore_throat" else (symptom or "symptom")
