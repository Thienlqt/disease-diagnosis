from __future__ import annotations

import argparse
from pathlib import Path

from .engine import ConversationEngine
from .exporter import export_markdown
from .model import LlamaCppClient, MODEL_ID
from .models import SessionState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Learning-only cough and sore-throat terminal conversation"
    )
    parser.add_argument(
        "--report-dir", default="reports", help="directory for the Markdown conversation record"
    )
    parser.add_argument(
        "--llm",
        choices=("auto", "on", "off"),
        default="auto",
        help="use the local llama.cpp server when available (default: auto)",
    )
    parser.add_argument(
        "--llama-url",
        default="http://127.0.0.1:8081/v1",
        help="OpenAI-compatible llama.cpp base URL",
    )
    parser.add_argument(
        "--llama-model", default=MODEL_ID, help="model alias exposed by llama.cpp"
    )
    return parser


def run(
    report_dir: str | Path = "reports",
    *,
    interpreter: LlamaCppClient | None = None,
) -> Path:
    engine = ConversationEngine(interpreter=interpreter)
    print(engine.start())
    if interpreter:
        print(f"\nLocal inference: active ({interpreter.runtime_name})")
    else:
        print("\nLocal inference: inactive; deterministic interpretation only")
    print("\nCommands: /summary, /correct FIELD [SYMPTOM]: VALUE, /change FIELD [SYMPTOM]: VALUE, /quit")

    while engine.session.state == SessionState.IN_PROGRESS:
        try:
            user_text = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print()
            engine.respond("/quit")
            break
        print("\n" + engine.respond(user_text))

    report_path = export_markdown(engine.session, report_dir)
    print(f"\nConversation record exported to: {report_path}")
    return report_path


def main() -> None:
    args = build_parser().parse_args()
    interpreter = None
    if args.llm != "off":
        candidate = LlamaCppClient(args.llama_url, model=args.llama_model)
        if candidate.is_available():
            interpreter = candidate
        elif args.llm == "on":
            raise SystemExit(
                f"llama.cpp is not reachable at {args.llama_url}. Start scripts/start_qwen_server.py first."
            )
    run(args.report_dir, interpreter=interpreter)


if __name__ == "__main__":
    main()
