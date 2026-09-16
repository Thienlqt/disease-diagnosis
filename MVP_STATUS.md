# MVP implementation status

Updated: 2026-09-16

This repository implements the first local terminal release described by `MVP.md`. It is a software learning prototype, not a clinically ready product.

## Implemented

- In-memory, isolated sessions with reporter, age, symptoms, messages, questions, and facts.
- The versioned Q01–Q12 draft question bank, including per-symptom onset and progression.
- Distinct unanswered, answered, unclear, unknown, and declined states.
- Context-aware short answers, conservative volunteered-fact extraction, and partial temperature clarification.
- Correction and change-over-time history with source-message links.
- Draft urgent interruption for explicitly reported breathing difficulty or inability to swallow saliva. The normal queue stops and its pending question remains pending.
- Completion without a disease suggestion, plus Markdown summary and exact stored transcript.
- Source register, coverage/gap table, collection manifest, an eligibility-gated keyword retrieval baseline, and model-update validation.
- Automated fictional tests for core conversations, failure-sensitive state transitions, export, retrieval filtering, and model proposal validation.
- A live four-case Qwen/llama.cpp smoke test, including an end-to-end engine transition, with all cases passing after schema validation.

## Deliberately inactive or pending

- No medical source is active. Current source URLs and reuse/access conditions must be rechecked, and content needs appropriate clinical review before collection or activation.
- No medical snapshot has been downloaded, cleaned, chunked, embedded, or used to give advice.
- No embedding model or vector index has been selected. The deterministic keyword baseline is the only implemented search mechanism.
- Qwen2.5-3B-Instruct Q4_K_M is integrated through a local `llama.cpp` OpenAI-compatible server. The artifact is pinned by revision, size, and SHA-256; model proposals are schema-constrained and validated again by the engine. Broader held-out quality evaluation remains pending.
- Draft urgent rules and all question wording still require clinical review, especially for children, Ho Chi Minh City routing, and uncertainty handling.
- Facility matching, dashboard, and appointment booking are later product features and are not included.

## Milestone mapping

| MVP.md milestone | Status |
|---|---|
| 1. Basic terminal exercise | Complete and tested |
| 2. Question bank and state | Complete and tested |
| 3. Conversation changes | Complete for explicit corrections/changes and draft interruption rules; broader natural-language evaluation remains |
| 4. Markdown export | Complete and tested |
| 5. Source collection | Register/manifest scaffold complete; collection blocked by review and approval requirements |
| 6. RAG data preparation | Eligibility-gated keyword component complete; no approved content to process |
| 7. Model and RAG integration | Qwen/llama.cpp fact-extraction path and validation boundary complete; eligible medical evidence pending |
| 8. End-to-end evaluation | 18 deterministic/model-failure tests and a four-case live-model smoke test pass; broader held-out and retrieval evaluation pending |

The terminal application is ready for fictional development use. The remaining items are evidence/model validation work, not safe defaults to fabricate inside the application.
