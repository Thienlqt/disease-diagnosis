from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.engine import ConversationEngine
from src.exporter import build_markdown_report, export_markdown
from src.model import LlamaCppError, ProposedFactUpdate
from src.models import AnswerState, SessionState


def begin(engine: ConversationEngine, *, age: int = 30, symptoms: str = "both") -> None:
    engine.start()
    engine.respond("patient")
    engine.respond(str(age))
    engine.respond(symptoms)


def complete_both(engine: ConversationEngine) -> None:
    for answer in (
        "no",
        "yes",
        "2 days ago",
        "yesterday",
        "same",
        "worse",
        "38 C this morning",
        "no",
        "usual",
        "no change",
        "none",
        "none",
        "no",
    ):
        engine.respond(answer)


class ConversationTests(unittest.TestCase):
    def test_clear_answers_keep_symptoms_separate_and_complete(self) -> None:
        engine = ConversationEngine()
        begin(engine)
        complete_both(engine)

        self.assertEqual(SessionState.COMPLETED, engine.session.state)
        self.assertEqual(
            {"reported_wording": "2 days ago"},
            engine.session.current_fact("onset", "cough").value,
        )
        self.assertEqual(
            {"reported_wording": "yesterday"},
            engine.session.current_fact("onset", "sore_throat").value,
        )
        self.assertNotIn("possible cause", engine.summary().split("Assessment and next step:")[0])

    def test_new_session_is_empty(self) -> None:
        first = ConversationEngine()
        begin(first, symptoms="cough")
        first.respond("no")
        second = ConversationEngine()
        self.assertNotEqual(first.session.id, second.session.id)
        self.assertEqual([], second.session.facts)
        self.assertEqual(set(), second.session.symptoms)

    def test_unclear_answer_is_clarified_and_partial_temperature_is_preserved(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        engine.respond("maybe")
        self.assertEqual(AnswerState.UNCLEAR, engine.session.current_fact("breathing_difficulty").answer_state)
        engine.respond("no")
        engine.respond("last week")
        engine.respond("same")
        response = engine.respond("38 this morning")
        partial = engine.session.current_fact("temperature")
        self.assertEqual(AnswerState.UNCLEAR, partial.answer_state)
        self.assertIn("number and whether", response)
        engine.respond("Celsius")
        resolved = engine.session.current_fact("temperature")
        self.assertEqual(AnswerState.ANSWERED, resolved.answer_state)
        self.assertEqual("C", resolved.value["unit"])
        self.assertTrue(partial.superseded)

    def test_unknown_declined_negative_and_unanswered_stay_distinct(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        engine.respond("I don't know")
        engine.respond("yesterday")
        engine.respond("prefer not to answer")

        breathing = engine.session.current_fact("breathing_difficulty")
        progression = engine.session.current_fact("progression", "cough")
        temperature = engine.session.current_fact("temperature")
        self.assertEqual(AnswerState.UNKNOWN, breathing.answer_state)
        self.assertEqual(AnswerState.DECLINED, progression.answer_state)
        self.assertIsNone(temperature)

        engine.respond("not measured")
        engine.respond("no")
        self.assertEqual(False, engine.session.current_fact("runny_nose").value)
        self.assertEqual(AnswerState.ANSWERED, engine.session.current_fact("runny_nose").answer_state)

    def test_correction_preserves_old_fact(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        engine.respond("no")
        engine.respond("2 days ago")
        old = engine.session.current_fact("onset", "cough")
        engine.respond("/correct onset cough: 4 days ago")
        new = engine.session.current_fact("onset", "cough")
        self.assertTrue(old.superseded)
        self.assertEqual(old.id, new.supersedes_fact_id)
        self.assertEqual("correction", new.relationship)
        self.assertEqual("4 days ago", new.value)

    def test_change_over_time_keeps_prior_observation_not_superseded(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        engine.respond("no")
        engine.respond("2 days ago")
        engine.respond("same")
        old = engine.session.current_fact("progression", "cough")
        engine.respond("/change progression cough: worse this evening")
        new = engine.session.current_fact("progression", "cough")
        self.assertFalse(old.superseded)
        self.assertEqual(old.id, new.supersedes_fact_id)
        self.assertEqual("change_over_time", new.relationship)

    def test_urgent_disclosure_interrupts_and_preserves_pending_question(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        pending = engine.session.current_question_asked_id
        response = engine.respond("Actually I can't breathe")
        self.assertEqual(SessionState.URGENT_HANDOFF, engine.session.state)
        self.assertEqual(pending, engine.session.current_question_asked_id)
        self.assertIn("URGENT HANDOFF", response)
        later = engine.respond("no")
        self.assertIn("no longer asking", later)
        self.assertEqual(pending, engine.session.current_question_asked_id)

    def test_urgent_message_has_priority_over_unsupported_age(self) -> None:
        engine = ConversationEngine()
        engine.start()
        response = engine.respond("My 4-year-old cannot breathe")
        self.assertEqual(SessionState.URGENT_HANDOFF, engine.session.state)
        self.assertIn("URGENT HANDOFF", response)

    def test_negated_breathing_phrase_is_not_urgent(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        response = engine.respond("I don't have any difficulty breathing")
        self.assertEqual(SessionState.IN_PROGRESS, engine.session.state)
        self.assertNotIn("URGENT", response)
        self.assertEqual(False, engine.session.current_fact("breathing_difficulty").value)

    def test_caregiver_setup_and_scope_boundary(self) -> None:
        engine = ConversationEngine()
        engine.start()
        engine.respond("I am the caregiver for my child")
        response = engine.respond("4")
        self.assertEqual(SessionState.STOPPED, engine.session.state)
        self.assertIn("age 5 or older", response)

    def test_report_uses_exact_stored_transcript(self) -> None:
        engine = ConversationEngine()
        begin(engine, symptoms="cough")
        phrase = "No, and this exact punctuation: !? stays."
        engine.respond(phrase)
        markdown = build_markdown_report(engine.session)
        self.assertIn(phrase, markdown)
        self.assertIn("No possible cause is provided", markdown)
        with TemporaryDirectory() as directory:
            path = export_markdown(engine.session, directory)
            self.assertTrue(path.exists())
            self.assertEqual(markdown, path.read_text(encoding="utf-8"))

    def test_qwen_proposal_is_validated_then_recorded_by_engine(self) -> None:
        class FakeInterpreter:
            runtime_name = "test-llama.cpp/qwen"

            def interpret_answer(self, **kwargs):
                self.kwargs = kwargs
                return ProposedFactUpdate(
                    information_type="progression",
                    symptom="cough",
                    value="better",
                    answer_state="answered",
                    source_quote="easing up",
                )

        interpreter = FakeInterpreter()
        engine = ConversationEngine(interpreter=interpreter)
        begin(engine, symptoms="cough")
        engine.respond("no")
        engine.respond("two days ago")
        response = engine.respond("It seems to be easing up")
        fact = engine.session.current_fact("progression", "cough")
        self.assertEqual("better", fact.value)
        self.assertEqual("llama.cpp/qwen2.5-3b-instruct-q4_k_m", fact.interpretation_method)
        self.assertEqual(1, engine.session.model_calls)
        self.assertEqual(0, engine.session.model_failures)
        self.assertIn("temperature", response.lower())

    def test_model_timeout_does_not_corrupt_state(self) -> None:
        class FailingInterpreter:
            runtime_name = "test-llama.cpp/qwen"

            def interpret_answer(self, **kwargs):
                raise LlamaCppError("timeout")

        engine = ConversationEngine(interpreter=FailingInterpreter())
        begin(engine, symptoms="cough")
        response = engine.respond("perhaps")
        fact = engine.session.current_fact("breathing_difficulty")
        self.assertEqual(AnswerState.UNCLEAR, fact.answer_state)
        self.assertEqual("deterministic", fact.interpretation_method)
        self.assertEqual(1, engine.session.model_failures)
        self.assertIn("yes, no", response.lower())


if __name__ == "__main__":
    unittest.main()
