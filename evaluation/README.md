# Evaluation data

This directory is for fictional development and held-out conversations. It must remain separate from medical reference chunks and must never be indexed as clinical evidence.

The current executable cases live in `tests/`. Keep prompt-tuning examples and held-out cases in separate versioned files, and record the exact model artifact hash, upstream revision, runtime, hardware, prompt version, settings, latency, memory, raw response, validation result, and expected-versus-observed facts.

`qwen_live_smoke_2026-09-16.json` records the first live development smoke test of the pinned artifact. It is a small development check, not a held-out evaluation or evidence of clinical reliability.
