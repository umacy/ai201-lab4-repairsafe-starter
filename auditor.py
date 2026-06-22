import json
import os
from datetime import datetime, timezone

from config import LOG_FILE

# Truncation limits — see specs/auditor-spec.md "Why these truncation limits?"
_QUESTION_MAX = 300
_RESPONSE_PREVIEW_MAX = 200
_CONSOLE_QUESTION_MAX = 60


def _utc_timestamp() -> str:
    """ISO 8601 UTC timestamp, e.g. 2026-06-22T15:04:05.123456Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _console_question(question: str) -> str:
    """Single-line, 60-char preview of the question for the terminal summary."""
    collapsed = " ".join(question.split())
    if len(collapsed) > _CONSOLE_QUESTION_MAX:
        return collapsed[:_CONSOLE_QUESTION_MAX] + "…"
    return collapsed


def log_interaction(question: str, tier: str, response: str) -> None:
    """
    Append a structured JSON record of this interaction to the audit log.

    Writes one JSON object per line to LOG_FILE ("logs/audit.jsonl"). See
    specs/auditor-spec.md for field choices, truncation rationale, and the
    console-summary format.

    Output: None — side effects only (appends to the log file, prints a
    one-line summary to the terminal). Logging must never crash the request
    pipeline, so any failure is caught and reported rather than raised.
    """
    record = {
        "timestamp": _utc_timestamp(),
        "tier": tier,
        "question": question[:_QUESTION_MAX],
        "response_preview": response[:_RESPONSE_PREVIEW_MAX],
        "response_length": len(response),
        "question_length": len(question),
    }

    try:
        # Create logs/ on first run; no-op (and race-safe) thereafter.
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        # Never take down the user-facing response because logging failed.
        print(f"[LOG ERROR] could not write audit log: {exc.__class__.__name__}: {exc}")
        return

    summary = (
        f'[LOGGED] tier={tier} | "{_console_question(question)}" '
        f"→ {record['response_length']} chars"
    )
    try:
        print(summary)
    except UnicodeEncodeError:
        # Some Windows consoles use a legacy code page (cp1252) that can't encode
        # "→". Don't let a console-encoding quirk crash the request — fall back to ASCII.
        print(summary.replace("→", "->"))
