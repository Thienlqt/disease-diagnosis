# Cough and Sore-Throat Learning MVP

A local terminal prototype based on [`MVP.md`](MVP.md). It conducts one structured conversation for a fictional patient age 5 or older, keeps cough and sore-throat facts separate, interrupts the normal question queue for draft urgent disclosures, and exports the exact transcript and current facts as Markdown.

This is **not a medical device or diagnostic tool**. Its question wording, routing rules, and clinical content are drafts without clinical review. Use only fictional data during development.

## Run

Python 3.10 or newer is required. The deterministic mode has no third-party Python dependencies. Local LLM mode uses `llama.cpp` plus the pinned Qwen GGUF described below.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
symptom-chat
```

You can also run without installing:

```bash
python3 -m src
```

The default `--llm auto` mode uses the local server when it is available and otherwise falls back to deterministic interpretation. Use `--llm on` to require the model or `--llm off` to disable it explicitly.

## Local Qwen inference

The checked-in [`model_runtime.json`](model_runtime.json) pins the official Qwen2.5-3B-Instruct Q4_K_M filename, upstream revision, byte size, and SHA-256. Model weights are downloaded to the ignored `models/` directory.

```bash
python3 scripts/download_qwen.py
python3 scripts/start_qwen_server.py
```

Leave the server running, then open a second terminal:

```bash
python3 -m src --llm on
```

The server binds to `127.0.0.1:8081` (port 8080 was already occupied on the development machine), uses a 4,096-token context and one inference slot, enables the model's Jinja chat template, and exposes the alias `qwen2.5-3b-instruct-q4_k_m`. On first launch it creates an ignored, mode-0600 API key at `models/.llama_api_key`; the local client reads the same file. Override the endpoint with `--llama-url` if necessary.

Qwen is used only when the deterministic parser cannot resolve the answer to the current question. It receives that question and the current user message, then proposes one schema-constrained fact. The application verifies the information type, symptom, answer state, value shape, and an exact supporting quote before storing it. Qwen cannot choose questions, apply urgent rules, or mutate session state directly. Timeouts and invalid responses fall back to clarification without becoming negative findings.

At completion, urgent handoff, or early stop, a report is written to `reports/session-<id>.md`. Change the destination with `--report-dir PATH`.

Useful commands during a session:

```text
/summary
/correct onset cough: 4 days ago
/change progression sore_throat: worse this evening
/quit
```

Corrections supersede the current fact but preserve it in history. Changes over time preserve both observations. An urgent handoff deliberately preserves the pending question and never resumes it automatically.

## Test

The test suite uses only the Python standard library:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover the agreed fictional cases plus separate symptoms, answer states, partial temperature answers, age scope, session isolation, exact transcript export, retrieval eligibility, and model-update validation.

## Design

- `ConversationEngine` owns question selection, facts, corrections, scope, and state transitions.
- The versioned 12-question draft lives in `src/data/question_bank.json`.
- Every question and answer is stored as an immutable transcript message. Current facts point back to their source message; corrected facts remain in history.
- The exporter builds the transcript directly from stored messages and never asks a model to reconstruct it.
- The keyword retriever only returns chunks marked `clinically_reviewed_eligible`. This first build intentionally has no eligible medical chunks, so it returns no evidence instead of guessing.
- Model-proposed fact updates have a validation boundary and cannot directly change routing or session state. The deterministic parser runs first; the local Qwen model handles unresolved current-question answers when enabled.

## Source and RAG status

The source register, coverage table, collection manifest, and inactive chunk file are in `src/data/`. Candidate URLs from the product brief are recorded, but all remain excluded pending access/reuse review and clinical review. No web pages were copied into this repository, and no medical advice is generated from unreviewed content.

That means the collection/model milestones are scaffolded but intentionally not claimed as clinically complete. Activating them requires:

1. Reviewing current access and reuse terms for each exact source.
2. Collecting permitted snapshots with hashes and provenance.
3. Verifying every cleaned document and passage against the original.
4. Clinical review for age, geography, routing, and advice applicability.
5. Expanding evaluation of the pinned Qwen2.5-3B-Instruct Q4_K_M artifact on held-out fictional conversations and recording latency, memory, and error categories.

The app remains useful without those steps: it can complete and export a factual symptom record without naming an illness.

## Privacy and retention

Sessions exist only in process memory. A Markdown report is written explicitly at the end of a CLI run. Routine debug logging is not used. Delete exported reports manually when they are no longer needed; do not use real patient data until a retention and deletion policy exists.
