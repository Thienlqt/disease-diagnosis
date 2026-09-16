from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .engine import ConversationEngine
from .models import AnswerState, Session


def build_markdown_report(session: Session) -> str:
    engine = ConversationEngine(session)
    lines = [
        "# Symptom Conversation Record",
        "",
        "> **Learning prototype only.** This record is not a diagnosis. The question bank and routing rules are draft and unreviewed.",
        "",
        "## Session",
        "",
        f"- Session identifier: `{session.id}`",
        f"- Report date: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Created: {session.created_at}",
        f"- Reporter: {session.reporter.value if session.reporter else 'unknown'}",
        f"- Patient age: {session.patient_age if session.patient_age is not None else 'unknown'}",
        f"- Symptoms: {', '.join(sorted(session.symptoms)) or 'unknown'}",
        f"- Ending state: {session.state.value}",
        f"- Ending reason: {session.ending_reason or 'not yet ended'}",
        f"- Content version: `{session.content_version}`",
        f"- Workflow version: `{session.workflow_version}`",
        f"- Model runtime: {session.model_runtime or 'not active'}",
        f"- Model interpretation calls: {session.model_calls}",
        f"- Model interpretation failures: {session.model_failures}",
        "",
        "## Current summary",
        "",
        engine.summary(),
        "",
        "## Unknown, declined, or unresolved information",
        "",
    ]
    unresolved = [
        fact
        for fact in session.facts
        if not fact.superseded
        and fact.answer_state in {AnswerState.UNKNOWN, AnswerState.DECLINED, AnswerState.UNCLEAR}
    ]
    if unresolved:
        for fact in unresolved:
            target = f" ({fact.symptom.replace('_', ' ')})" if fact.symptom else ""
            lines.append(f"- {fact.information_type.replace('_', ' ')}{target}: {fact.answer_state.value}")
    else:
        lines.append("- None recorded.")

    corrections = [fact for fact in session.facts if fact.superseded or fact.supersedes_fact_id]
    lines.extend(["", "## Fact history and corrections", ""])
    if corrections:
        for fact in session.facts:
            status = "superseded" if fact.superseded else "current"
            if fact.superseded or fact.supersedes_fact_id:
                lines.append(
                    f"- `{fact.id}` — {fact.information_type}"
                    f"{f'/{fact.symptom}' if fact.symptom else ''}: {fact.value!r} "
                    f"({fact.answer_state.value}, {status}, relationship={fact.relationship})"
                )
    else:
        lines.append("- No corrections or changes over time were recorded.")

    lines.extend(
        [
            "",
            "## Assessment and next step",
            "",
            "No possible cause is provided because this build has no clinically reviewed assessment workflow. "
            "The current summary may be shared with a qualified clinician. An urgent handoff message, when present in the transcript, takes priority over this report.",
            "",
            "## Exact transcript",
            "",
        ]
    )
    for message in session.messages:
        role = "Assistant" if message.role == "assistant" else "User"
        lines.extend([f"### {role} — {message.created_at}", "", message.content, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_markdown(session: Session, output_dir: str | Path = "reports") -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"session-{session.id}.md"
    path.write_text(build_markdown_report(session), encoding="utf-8")
    return path.resolve()
