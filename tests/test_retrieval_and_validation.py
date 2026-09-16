from __future__ import annotations

import unittest

from src.model import ProposedFactUpdate, validate_model_update
from src.retrieval import Chunk, KeywordRetriever


def chunk(chunk_id: str, review_state: str, country: str = "general") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc",
        text="Fictional test passage about cough duration.",
        heading_path=("Test",),
        source_url="https://example.invalid/test",
        publisher="fictional test publisher",
        audience="test",
        age_applicability="test-only",
        country=country,
        language="en",
        topic_tags=("cough",),
        source_date=None,
        collection_date="2026-09-16",
        rights_record="test fixture",
        review_state=review_state,
        content_hash=chunk_id,
    )


class RetrievalAndValidationTests(unittest.TestCase):
    def test_retrieval_excludes_unreviewed_and_wrong_population(self) -> None:
        retriever = KeywordRetriever(
            [
                chunk("eligible", "clinically_reviewed_eligible"),
                chunk("unreviewed", "development_only_ineligible"),
                chunk("wrong-country", "clinically_reviewed_eligible", "United Kingdom"),
            ]
        )
        results = retriever.search("cough duration", topics={"cough"}, country="Vietnam")
        self.assertEqual(["eligible"], [item.chunk.chunk_id for item in results])

    def test_empty_or_ineligible_evidence_returns_no_result(self) -> None:
        retriever = KeywordRetriever([chunk("unreviewed", "development_only_ineligible")])
        self.assertEqual([], retriever.search("cough"))

    def test_model_update_requires_verbatim_evidence(self) -> None:
        valid = ProposedFactUpdate(
            information_type="onset",
            symptom="cough",
            value="two days",
            answer_state="answered",
            source_quote="two days",
        )
        self.assertTrue(validate_model_update(valid, "It started two days ago")[0])
        invented = ProposedFactUpdate(
            information_type="onset",
            symptom="cough",
            value="one week",
            answer_state="answered",
            source_quote="one week",
        )
        self.assertFalse(validate_model_update(invented, "It started two days ago")[0])

    def test_model_update_cannot_change_question_target(self) -> None:
        update = ProposedFactUpdate(
            information_type="runny_nose",
            symptom=None,
            value=False,
            answer_state="answered",
            source_quote="No",
        )
        valid, reason = validate_model_update(
            update,
            "No",
            expected_information_type="breathing_difficulty",
            expected_symptom=None,
        )
        self.assertFalse(valid)
        self.assertIn("current question", reason)

    def test_model_boolean_value_must_really_be_boolean(self) -> None:
        update = ProposedFactUpdate(
            information_type="breathing_difficulty",
            symptom=None,
            value="no",
            answer_state="answered",
            source_quote="no",
        )
        self.assertFalse(validate_model_update(update, "no")[0])


if __name__ == "__main__":
    unittest.main()
