"""Critical error reporting and Outlook notification helpers."""

from __future__ import annotations

import datetime
import json
import logging
import os
import random
import shutil
import socket
import threading
from pathlib import Path
from typing import Any

from .smducar_config import error_log_entries, load_config, status_updates_buffer
from .rerun_status import RERUN_STATUS_PREFIX, summarize_statuses_for_rows


DEFAULT_DEVELOPER_EMAIL = "kevinjohn.libuna@reedelsevier.com"
CRITICAL_STATUS_MARKERS = (
    "ERROR",
    "NEEDS RERUN",
    "RELATED LNI ERROR",
    "RELATED LNI TIMEOUT",
    "NO COUNSEL ATTACHED",
    "SKIPPED: MSPB PDF DATA NOT FOUND",
)

_run_lock = threading.Lock()
_active_run: dict[str, Any] = {}
_email_random = random.SystemRandom()


def start_critical_error_run(latest_excel=None, mode=None, config=None):
    """Reset critical notification state for a new automation run."""
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    with _run_lock:
        _active_run.clear()
        _active_run.update({
            "run_id": run_id,
            "latest_excel": str(latest_excel) if latest_excel else "",
            "mode": mode or "",
            "config": dict(config or {}),
            "notified": False,
            "completion_notified": False,
        })
    return run_id


def _current_run():
    with _run_lock:
        return dict(_active_run)


def _mark_notified():
    with _run_lock:
        if _active_run.get("notified"):
            return False
        _active_run["notified"] = True
        return True


def _mark_completion_notified():
    with _run_lock:
        if _active_run.get("notified"):
            return False
        if _active_run.get("completion_notified"):
            return False
        _active_run["completion_notified"] = True
        return True


def _safe_filename(value):
    safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in str(value or ""))
    safe = safe.strip(" ._")
    return safe or "Critical Error"


def _get_current_log_file():
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            return Path(handler.baseFilename)

    logs_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Logs"
    try:
        return max(logs_dir.glob("log_*.txt"), key=lambda path: path.stat().st_mtime)
    except ValueError:
        return None


def _copy_attachment(source, report_dir, label=None):
    if not source:
        return None

    source_path = Path(source)
    if not source_path.exists():
        return None

    destination_name = f"{label}{source_path.suffix}" if label else source_path.name
    destination = report_dir / _safe_filename(destination_name)
    try:
        shutil.copy2(source_path, destination)
        return destination
    except Exception as exc:
        logging.warning("Failed to copy report attachment %s: %s", source_path, exc)
        return None


def _tail_text(path, max_lines=80):
    if not path or not Path(path).exists():
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            lines = file.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def _write_json(path, payload):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, default=str)
        return path
    except Exception as exc:
        logging.warning("Failed to write report JSON: %s", exc)
        return None


def _pick(options):
    return _email_random.choice(tuple(options))


def _count_value(counts, key):
    try:
        return int(counts.get(key, 0) or 0)
    except Exception:
        return 0


def _format_mode_label(mode):
    value = str(mode or "").strip()
    return value.upper() if value else "N/A"


def _document_result_label(mode):
    normalized = str(mode or "").strip().lower()
    labels = {
        "mspb": "MSPB documents",
        "itc": "ITC documents",
        "irsplr": "IRSPLR documents",
        "ohtax0": "OHTAX0 documents",
        "mnsutb": "MNSUTB documents",
        "mosu00": "MOSU main/table documents",
    }
    return labels.get(normalized, "Main opinions")


def _is_document_only_mode(mode):
    return str(mode or "").strip().lower() in {"mspb", "itc", "irsplr", "ohtax0", "mnsutb"}


def _mode_display_name(mode):
    normalized = str(mode or "").strip().lower()
    labels = {
        "mspb": "MSPB Autorouter",
        "itc": "ITC Autorouter",
        "irsplr": "IRSPLR Autorouter",
        "ohtax0": "OHTAX0 Autorouter",
        "mnsutb": "MNSUTB Autorouter",
        "mosu00": "MOSU Autorouter",
        "dar": "DAR Autoruter",
        "smd": "SMD Autorouter",
    }
    return labels.get(normalized, f"{_format_mode_label(mode)} Autorouter" if mode else "SMD Autorouter")


def _legacy_success_email_theme():
    return _pick((
        {
            "subject": "Run complete, receipts attached",
            "hello": "Hi there,",
            "opener": (
                "{app_name} finished the run cleanly. The queue got its paperwork handled, "
                "and the receipts are attached for future-you."
            ),
            "scoreboard": "Here is the tidy little scorecard:",
            "attachments": (
                "I attached the run summary, current log, and completed mapping sheet copy "
                "so nobody has to go folder-hunting later."
            ),
            "closer": "Filed, labeled, and politely out of the way.",
        },
        {
            "subject": "Autorouting wrapped like a responsible adult",
            "hello": "Good news,",
            "opener": (
                "{app_name} is done. No confetti cannon was deployed, but the run summary "
                "is here and the documentation behaved beautifully."
            ),
            "scoreboard": "Quick scoreboard:",
            "attachments": (
                "The summary, log, and mapping sheet copy are attached. Neat receipts, "
                "zero scavenger hunt."
            ),
            "closer": "A small operational victory, now properly documented.",
        },
        {
            "subject": "Run finished, paperwork included",
            "hello": "Hello,",
            "opener": (
                "{app_name} completed the run and brought the paperwork with it. "
                "Very considerate. Very on brand."
            ),
            "scoreboard": "Run snapshot:",
            "attachments": (
                "You will find the run summary, current log, and completed mapping sheet copy attached "
                "for review or future detective work."
            ),
            "closer": "That is this run, buttoned up and ready for the archive shelf.",
        },
        {
            "subject": "Queue handled, documentation served",
            "hello": "Good news from the routing desk,",
            "opener": (
                "{app_name} clocked in, handled the queue, and left the paperwork neat "
                "like it has a performance review tomorrow."
            ),
            "scoreboard": "The official chika, but make it organized:",
            "attachments": (
                "The summary, current log, and completed mapping sheet copy are attached, "
                "because the receipts should never enter their mysterious era."
            ),
            "closer": "Clean run, clean notes, clean exit.",
        },
        {
            "subject": "Run completed, no drama detected",
            "hello": "Hi, bestie of the batch file,",
            "opener": (
                "{app_name} finished this run without needing a group chat intervention. "
                "The documents have been handled and the evidence is tidy."
            ),
            "scoreboard": "Tiny but important scorecard:",
            "attachments": (
                "I attached the summary, log, and mapping sheet copy so review time can be quick, "
                "calm, and emotionally affordable."
            ),
            "closer": "The queue has left the building, respectfully.",
        },
        {
            "subject": "Routing complete, very demure",
            "hello": "Hello hello,",
            "opener": (
                "{app_name} completed the run and behaved with unusual maturity. "
                "The queue is processed, the numbers are below, and the receipts are included."
            ),
            "scoreboard": "Run numbers, freshly plated:",
            "attachments": (
                "Attached are the run summary, current log, and completed mapping sheet copy "
                "for anyone who enjoys evidence with structure."
            ),
            "closer": "Handled, documented, and quietly fabulous.",
        },
        {
            "subject": "Automation complete, paperwork behaving",
            "hello": "Quick update,",
            "opener": (
                "{app_name} made it through the run and brought back clean documentation. "
                "A rare corporate creature: useful and not trying to be difficult."
            ),
            "scoreboard": "Here is the receipt roll:",
            "attachments": (
                "The summary, current log, and completed mapping sheet copy are attached "
                "so the audit trail is not doing interpretive dance."
            ),
            "closer": "Another run packed, stacked, and ready for later.",
        },
        {
            "subject": "Run done, queue survived",
            "hello": "Friendly update,",
            "opener": (
                "{app_name} has finished the run. The queue survived, the files cooperated, "
                "and the documentation showed up dressed for work."
            ),
            "scoreboard": "The useful numbers:",
            "attachments": (
                "I included the summary, current log, and completed mapping sheet copy. "
                "Future troubleshooting can start from facts, not folklore."
            ),
            "closer": "A calm little win, with attachments.",
        },
        {
            "subject": "All wrapped, receipts included",
            "hello": "Good news, mga ka-router,",
            "opener": (
                "{app_name} completed the run and did not choose violence today. "
                "The batch is handled and the supporting files are ready."
            ),
            "scoreboard": "Run breakdown:",
            "attachments": (
                "Attached: summary, current log, and mapping sheet copy. "
                "Documentation said, 'I am present.'"
            ),
            "closer": "We love a productive ending with receipts.",
        },
        {
            "subject": "Batch complete, please clap internally",
            "hello": "Hello from the tiny operations desk,",
            "opener": (
                "{app_name} wrapped the run and kept the paper trail tidy. "
                "No speech, no parade, just competent little behavior."
            ),
            "scoreboard": "For the record:",
            "attachments": (
                "The run summary, current log, and completed mapping sheet copy are attached "
                "so the documentation can do its job without making anyone chase it."
            ),
            "closer": "Quietly iconic. Properly documented.",
        },
        {
            "subject": "Run completed, paperwork has range",
            "hello": "Hi hi,",
            "opener": (
                "{app_name} completed the run and came back with numbers, files, and a calm attitude. "
                "We respect growth in automated systems."
            ),
            "scoreboard": "Here is the run tea, sanitized for corporate:",
            "attachments": (
                "Attached are the summary, current log, and completed mapping sheet copy "
                "for quick checking and future receipts."
            ),
            "closer": "Done, documented, and giving organized energy.",
        },
    ))


def _legacy_critical_email_theme():
    return _pick((
        {
            "subject": "Run needs a look",
            "hello": "Hi there,",
            "opener": (
                "{app_name} hit a real stopping point during the run. I gathered the clues right away "
                "so troubleshooting can start from evidence instead of vibes."
            ),
            "snapshot": "What I captured:",
            "attachments": (
                "I attached the critical summary, payload, current log, and mapping sheet copy. "
                "The useful clues are bundled together."
            ),
            "closer": "Not the outcome we wanted, but the trail is warm and organized.",
        },
        {
            "subject": "Critical report captured",
            "hello": "Quick heads-up,",
            "opener": (
                "{app_name} ran into something serious enough to document. I saved the receipts "
                "before the trail could get fuzzy."
            ),
            "snapshot": "Debugging snapshot:",
            "attachments": (
                "The report files are attached so the issue can be reviewed without digging through the machine first."
            ),
            "closer": "Tiny drama, tidy evidence.",
        },
        {
            "subject": "Routing snag, clues attached",
            "hello": "Hello,",
            "opener": (
                "{app_name} stopped on a critical issue. I packaged the run details so this can be traced "
                "with fewer mysteries and fewer forehead wrinkles."
            ),
            "snapshot": "Useful details:",
            "attachments": (
                "Attached are the summary, payload, log, and mapping sheet copy. Basically: the good debugging stuff."
            ),
            "closer": "The bot is taking responsibility and arriving with documentation.",
        },
        {
            "subject": "Small plot twist, report attached",
            "hello": "Quick heads-up from the routing desk,",
            "opener": (
                "{app_name} hit a critical issue and decided to document instead of pretending everything was fine. "
                "Growth. Accountability. Receipts."
            ),
            "snapshot": "What needs attention:",
            "attachments": (
                "I attached the critical summary, payload, current log, and mapping sheet copy "
                "so the fix can start with context already in hand."
            ),
            "closer": "A little plot twist, but not an unsolved mystery.",
        },
        {
            "subject": "Pa-check please, clues included",
            "hello": "Hi, pa-check please,",
            "opener": (
                "{app_name} ran into something serious enough to raise its hand. "
                "No panic, but definitely worth a look."
            ),
            "snapshot": "Issue notes:",
            "attachments": (
                "The supporting files are attached: critical summary, payload, current log, and mapping sheet copy. "
                "Everything is gathered so nobody has to reconstruct the scene from vibes."
            ),
            "closer": "Not cute, but very documented.",
        },
        {
            "subject": "Run stopped for adult supervision",
            "hello": "Hello hello,",
            "opener": (
                "{app_name} encountered a critical snag and politely requested adult supervision. "
                "I captured the details while they were still fresh."
            ),
            "snapshot": "Troubleshooting tea:",
            "attachments": (
                "Attached are the summary, payload, log, and mapping sheet copy, also known as "
                "the evidence folder with better manners."
            ),
            "closer": "The issue is annoying, but at least it arrived with paperwork.",
        },
        {
            "subject": "Critical snag, receipts secured",
            "hello": "Friendly alert,",
            "opener": (
                "{app_name} stopped on a critical issue. I saved the run details immediately, "
                "because debugging without receipts is just workplace astrology."
            ),
            "snapshot": "The situation:",
            "attachments": (
                "The critical summary, payload, current log, and mapping sheet copy are attached "
                "for a faster, less dramatic investigation."
            ),
            "closer": "The problem is logged, the clues are together, and the next step is much less mysterious.",
        },
        {
            "subject": "Router needs a rescue glance",
            "hello": "Hi team,",
            "opener": (
                "{app_name} found something it could not safely push through. "
                "Instead of freestyling, it stopped and packed the details."
            ),
            "snapshot": "What the router reported:",
            "attachments": (
                "I attached the critical summary, payload, current log, and mapping sheet copy "
                "so the review has the full little paper trail."
            ),
            "closer": "A careful stop is better than a confident mess.",
        },
        {
            "subject": "Issue logged, evidence bundled",
            "hello": "Heads up,",
            "opener": (
                "{app_name} hit a critical routing issue. The good news: it did not vanish into the fog. "
                "The details are captured below."
            ),
            "snapshot": "Captured details:",
            "attachments": (
                "The attached files include the summary, payload, current log, and mapping sheet copy. "
                "Receipts are present and accounted for."
            ),
            "closer": "This one needs a look, but the breadcrumbs are clean.",
        },
        {
            "subject": "Bot tripped, logs reported for duty",
            "hello": "Hi, quick routing chika,",
            "opener": (
                "{app_name} ran into a critical issue and stopped before making things weirder. "
                "Respectfully, that was the correct kind of dramatic."
            ),
            "snapshot": "Here is the useful part:",
            "attachments": (
                "The critical summary, payload, current log, and mapping sheet copy are attached. "
                "The clues are together and ready for inspection."
            ),
            "closer": "Not the dream ending, but the paperwork showed up with purpose.",
        },
        {
            "subject": "Critical issue caught, report ready",
            "hello": "Hello from the alert desk,",
            "opener": (
                "{app_name} caught a critical issue during the run and created a report. "
                "No guessing game required; the context is below."
            ),
            "snapshot": "Run interruption details:",
            "attachments": (
                "Attached are the critical summary, payload, current log, and mapping sheet copy "
                "so the investigation can begin from actual evidence."
            ),
            "closer": "The run did not finish cleanly, but the trail is tidy.",
        },
    ))


SUCCESS_SUBJECTS = (
    "The queue is clear",
    "Run complete and neatly documented",
    "Clean run with the receipts attached",
    "Everything routed cleanly",
    "The paper trail is ready",
    "Run wrapped with notes in place",
    "Queue cleared without a fuss",
    "Routing finished and records are ready",
    "Clean finish from the routing desk",
    "Batch handled with receipts",
    "The run landed cleanly",
    "Documents routed and notes packed",
    "This one closed cleanly",
    "Run complete with a tidy trail",
    "The queue behaved today",
    "Routing done, records in hand",
    "Finished cleanly with the details attached",
    "Another batch safely wrapped",
    "The records are ready for review",
    "Clean run, tidy notes",
    "The batch is closed",
    "Run finished with everything attached",
    "Queue cleared and documented",
    "A clean little routing win",
    "The run is done and traceable",
    "Routing complete with no loose ends",
    "The paperwork made it home",
    "Files routed, trail secured",
    "Run closed with receipts ready",
    "All clear from the routing desk",
)


CRITICAL_SUBJECTS = (
    "Run needs a quick review",
    "A few rows need another pass",
    "The bot paused with clues attached",
    "Routing stopped with a report ready",
    "This run needs attention",
    "Issue caught and documented",
    "The report is ready for review",
    "Run interrupted with notes attached",
    "A routing snag needs a look",
    "The queue hit a checkpoint",
    "Not finished yet, but documented",
    "Some rows need rerun",
    "The run paused before guessing",
    "Critical stop with clues ready",
    "Chrome may need a fresh start",
    "Search Inventory needs another pass",
    "The Modify button went missing",
    "PDF text needs a closer look",
    "Related counsel needs attention",
    "Router session needs review",
    "The batch needs a careful rerun",
    "Issue logged with context",
    "Something stopped the run cleanly",
    "The trail is ready for debugging",
    "A rerun path is ready",
    "Review needed with receipts attached",
    "The bot stopped and brought notes",
    "The queue needs a second look",
    "Run paused with the evidence intact",
    "Critical report ready",
)


SUCCESS_GREETINGS = (
    "Good news,",
    "Quick update,",
    "Hello from the routing desk,",
    "Friendly run update,",
    "Hi there,",
    "Run update,",
    "A tidy little update,",
    "Good news from the queue,",
)


SUCCESS_OPENERS = (
    "{app_name} finished the run and kept the paper trail tidy. We love a clean exit.",
    "{app_name} made it through the batch cleanly, with the useful details packed and ready.",
    "{app_name} closed this run without drama and brought the notes along like a professional.",
    "{app_name} handled the queue and left behind enough context for future-you to breathe.",
    "{app_name} finished routing and did the polite thing: documented everything.",
    "{app_name} wrapped the work cleanly. The queue is handled, and the receipts did not wander off.",
    "{app_name} completed the run with the numbers below and the supporting files attached.",
    "{app_name} got through the batch and kept the documentation close. Sensible behavior. We approve.",
    "{app_name} finished the run and left a tidy trail behind. Very considerate of the next person.",
    "{app_name} handled this one cleanly. Nothing mystical, just useful automation with notes.",
)


SUCCESS_SCOREBOARDS = (
    "Quick run snapshot:",
    "The useful numbers:",
    "Run scorecard:",
    "For the record:",
    "Here is the clean little breakdown:",
    "Routing snapshot:",
)


SUCCESS_ATTACHMENT_LINES = (
    "I attached the run summary, current log, and completed mapping sheet copy so nobody has to go digging later.",
    "The summary, current log, and mapping sheet copy are attached for quick review and future troubleshooting.",
    "The important files are attached: summary, log, and mapping sheet copy. Receipts, but organized.",
    "I included the summary, log, and mapping sheet copy so the run can be checked without a folder scavenger hunt.",
    "The supporting files are attached, because a good run deserves a readable paper trail.",
    "Summary, current log, and mapping sheet copy are attached. Future debugging gets to start from facts.",
)


SUCCESS_CLOSERS = (
    "Clean finish. Receipts included.",
    "A small routing win, neatly documented.",
    "Done, traceable, and ready for the archive shelf.",
    "That is the run, wrapped and behaving.",
    "Clean queue, clean notes, calm ending.",
    "Nicely handled. The paperwork made it home.",
    "A tidy finish from your routing desk.",
    "Closed cleanly, with no loose ends left wandering.",
)


CRITICAL_GREETINGS = (
    "Quick heads-up,",
    "Routing alert,",
    "Hi there,",
    "Careful pause from the routing desk,",
    "Heads up,",
    "Quick review needed,",
    "Friendly alert,",
    "The bot has a note,",
)


CRITICAL_OPENERS = (
    "{app_name} hit a real stopping point and paused before making the situation messier. Sensible, if slightly dramatic.",
    "{app_name} ran into something it could not safely push through, so it stopped and gathered the details.",
    "{app_name} paused on a critical issue. Not ideal, but the clues are organized and ready.",
    "{app_name} found a snag worth documenting. The run did not finish cleanly, but the trail is intact.",
    "{app_name} stopped at the right moment instead of guessing. Annoying, yes. Useful for debugging, also yes.",
    "{app_name} ran into a blocker and packed the evidence before the trail could get fuzzy.",
    "{app_name} could not complete the run cleanly, so it saved the context for a faster review.",
    "{app_name} needs a look. The good news: the report arrived with the clues already grouped.",
)


CRITICAL_SNAPSHOTS = (
    "What happened:",
    "Issue snapshot:",
    "The useful details:",
    "What needs review:",
    "The short version:",
    "Captured context:",
)


CRITICAL_ATTACHMENT_LINES = (
    "I attached the critical summary, payload, current log, and mapping sheet copy so review can start from actual clues.",
    "The summary, payload, log, and mapping sheet copy are attached. No detective work from scratch required.",
    "The supporting files are attached, including the payload and current log, so the fix has a proper starting point.",
    "I included the critical report files and mapping sheet copy so the next pass can be targeted instead of chaotic.",
    "The useful files are bundled: summary, payload, log, and mapping sheet copy.",
    "Everything needed for first-pass troubleshooting is attached. Very polite for a failure report.",
)


CRITICAL_CLOSERS = (
    "Not the ending we wanted, but the trail is tidy.",
    "A little annoying, very documented.",
    "The run needs attention, but at least the clues showed up organized.",
    "This one needs review. The paper trail is ready.",
    "The issue is logged, and the rerun path is clearer now.",
    "Not a clean finish, but not a mystery either.",
    "The bot paused, brought notes, and left the next step visible.",
    "Recoverable energy. With attachments.",
)


def _success_email_theme():
    return {
        "subject": _pick(SUCCESS_SUBJECTS),
        "hello": _pick(SUCCESS_GREETINGS),
        "opener": _pick(SUCCESS_OPENERS),
        "scoreboard": _pick(SUCCESS_SCOREBOARDS),
        "attachments": _pick(SUCCESS_ATTACHMENT_LINES),
        "closer": _pick(SUCCESS_CLOSERS),
    }


def _critical_email_theme():
    return {
        "subject": _pick(CRITICAL_SUBJECTS),
        "hello": _pick(CRITICAL_GREETINGS),
        "opener": _pick(CRITICAL_OPENERS),
        "snapshot": _pick(CRITICAL_SNAPSHOTS),
        "attachments": _pick(CRITICAL_ATTACHMENT_LINES),
        "closer": _pick(CRITICAL_CLOSERS),
    }


def _format_email_timestamp(timestamp):
    try:
        if isinstance(timestamp, datetime.datetime):
            value = timestamp
        else:
            value = datetime.datetime.fromisoformat(str(timestamp or "").replace("Z", "+00:00"))
        return value.strftime("%m/%d/%Y %I:%M:%S %p")
    except Exception:
        return str(timestamp or "").replace("T", " ")


def _format_email_subject(subject_mode, timestamp, theme):
    mode_label = str(subject_mode or "GENERAL").strip().upper()
    if mode_label == "AUTOROUTER":
        mode_label = "GENERAL"
    return f"SADM Autorouter: {mode_label} - {theme['subject']} - {_format_email_timestamp(timestamp)}"


def _success_subject(subject_mode, timestamp, theme=None):
    theme = theme or _success_email_theme()
    return _format_email_subject(subject_mode, timestamp, theme)


def _critical_subject(subject_mode, timestamp, theme=None):
    theme = theme or _critical_email_theme()
    return _format_email_subject(subject_mode, timestamp, theme)


def _format_count_line(label, value):
    return f"- {label}: {value}"


def _format_run_status_counts(summary):
    if not summary:
        return []

    counts = summary.get("counts") or {}
    lines = [
        _format_count_line("Rows marked DONE", summary.get("done_count", 0)),
        _format_count_line("Rows already processed", summary.get("already_processed_count", 0)),
        _format_count_line("Rows needing rerun", summary.get("needs_rerun_count", 0)),
    ]
    for status, count in sorted(counts.items()):
        status_text = str(status or "")
        if status_text.startswith(RERUN_STATUS_PREFIX):
            lines.append(_format_count_line(status_text.title(), count))
    return lines


def _format_run_status_examples(summary, max_rows=12):
    rows = (summary or {}).get("rerun_rows") or []
    if not rows:
        return []

    lines = ["Rows to rerun preview:"]
    for row in rows[:max_rows]:
        excel_row = row.get("Excel Row") or row.get("Row") or "N/A"
        lni = row.get("LNI", "N/A")
        status = row.get("Status", "N/A")
        lines.append(f"- Row {excel_row}: {lni} ({status})")
    extra_count = max(0, len(rows) - max_rows)
    if extra_count:
        lines.append(f"- ...and {extra_count} more row(s).")
    return lines


def _flatten_payload_text(value):
    if isinstance(value, dict):
        return " ".join(_flatten_payload_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_payload_text(item) for item in value)
    return str(value or "")


def _critical_issue_key(payload, run_status_summary):
    text = " ".join((
        _flatten_payload_text(payload.get("title")),
        _flatten_payload_text(payload.get("error")),
        _flatten_payload_text(payload.get("details")),
        _flatten_payload_text(payload.get("status_updates")),
        _flatten_payload_text(payload.get("error_log_entries")),
        _flatten_payload_text(run_status_summary),
    )).lower()

    if "user reset" in text or "reset the bot" in text or "reset automation" in text:
        return "user_reset"
    if any(marker in text for marker in (
        "invalid session id",
        "session lost",
        "chrome not reachable",
        "disconnected",
        "target window already closed",
        "no such window",
        "router session lost",
    )):
        return "router_session_lost"
    if "search inventory" in text:
        return "search_inventory"
    if "modify button" in text or "modify failed" in text or "modify mode" in text:
        return "modify_button"
    if any(marker in text for marker in (
        "pdf data not found",
        "pdf text extraction returned no text",
        "unreadable pdf",
        "ocr",
        "pytesseract",
        "tesseract",
    )):
        return "pdf_unreadable"
    if "related lni" in text or "no counsel attached" in text or "missing counsel" in text:
        return "related_lni"
    if (run_status_summary or {}).get("needs_rerun_count", 0):
        return "needs_rerun"
    return "general"


def _critical_troubleshooting_steps(payload, run_status_summary):
    issue_key = _critical_issue_key(payload, run_status_summary)

    playbooks = {
        "user_reset": (
            "If the reset was intentional, this is mostly a cleanup report, not instant panic.",
            "Open the attached mapping sheet and filter the Status column for NEEDS RERUN.",
            "Rerun the same sheet and leave DONE or ALREADY PROCESSED rows unchanged; the bot will skip them.",
            "If the reset happened because the bot looked frozen, send this report with the log so the pause point can be reviewed.",
        ),
        "router_session_lost": (
            "Close any leftover Chrome windows that were opened by the bot.",
            "Relaunch the bot, then rerun the attached mapping sheet.",
            "Keep DONE and ALREADY PROCESSED rows as-is; focus on NEEDS RERUN rows.",
            "If it happens again, try fewer parallel routers first. Chrome may simply be asking for a smaller circus.",
        ),
        "search_inventory": (
            "Confirm the IRT site opens normally in Chrome.",
            "Rerun the attached mapping sheet and let the bot retry the NEEDS RERUN rows.",
            "If Search Inventory keeps failing, try signing into IRT fresh before launching the bot again.",
            "For repeated failures, reduce parallel routers and send the attached report for review.",
        ),
        "modify_button": (
            "Rerun the attached mapping sheet and focus on rows marked NEEDS RERUN.",
            "If the same LNI fails again, manually open that IRT form and check whether it is locked, already processed, or loading unusually slowly.",
            "Leave DONE and ALREADY PROCESSED rows alone so the rerun stays targeted.",
            "Send this report if the Modify button keeps disappearing. That page may be stale, locked, or being dramatic in a very specific way.",
        ),
        "pdf_unreadable": (
            "Open the downloaded PDF from the report or download folder and confirm it has readable text.",
            "If it is scanned or image-only, confirm Tesseract OCR is installed or bundled with the EXE being used.",
            "Rerun the affected NEEDS RERUN row after OCR support is confirmed.",
            "If OCR is available but the same PDF still fails, send the PDF plus this report for parser review.",
        ),
        "related_lni": (
            "Check whether the required counsel LNI exists in the mapping sheet.",
            "Confirm the counsel row is DONE before rerunning the related main opinion.",
            "If counsel is missing, add or route the counsel first, then rerun the main opinion row.",
            "If the counsel exists but will not attach, send the report so the related-LNI flow can be checked.",
        ),
        "needs_rerun": (
            "Open the attached mapping sheet and filter the Status column for NEEDS RERUN.",
            "Rerun the same sheet; the bot should skip rows marked DONE or ALREADY PROCESSED.",
            "If the same row fails twice, check that LNI manually in IRT before another rerun.",
            "Send this report for review if the rerun does not clear the affected rows.",
        ),
        "general": (
            "Open the attached mapping sheet and check whether any rows are marked NEEDS RERUN.",
            "If rows need rerun, rerun the same sheet and leave DONE or ALREADY PROCESSED rows unchanged.",
            "Review the attached current log for the first ERROR near the bottom of the run.",
            "If the same issue repeats, send the full report folder for review.",
        ),
    }
    return playbooks.get(issue_key, playbooks["general"])


def _format_troubleshooting_steps(steps):
    return [f"{index}. {step}" for index, step in enumerate(steps, start=1)]


def _build_critical_email_body(payload, report_dir, theme=None):
    theme = theme or _critical_email_theme()
    title = str(payload.get("title") or "Critical issue captured")
    error_text = str(payload.get("error") or "").strip()
    details = payload.get("details") or {}
    context = details.get("Context") if isinstance(details, dict) else ""
    run_status_summary = payload.get("run_status_summary") or (
        details.get("Rerun Status Summary") if isinstance(details, dict) else None
    )
    app_name = _mode_display_name(payload.get("mode"))

    lines = [
        theme["hello"],
        "",
        theme["opener"].format(app_name=app_name),
        "",
        theme["snapshot"],
        _format_count_line("Problem", title),
    ]
    if error_text:
        lines.append(_format_count_line("Error", error_text))

    lines.extend([
        _format_count_line("Mode", _format_mode_label(payload.get("mode"))),
        _format_count_line("Router", payload.get("router_label") or "N/A"),
        _format_count_line("LNI", payload.get("lni") or "N/A"),
        _format_count_line("Docket", payload.get("docket") or "N/A"),
    ])

    if context:
        lines.append(_format_count_line("Context", context))

    status_lines = _format_run_status_counts(run_status_summary)
    if status_lines:
        lines.extend(["", "Rerun-ready status:", *status_lines])
        example_lines = _format_run_status_examples(run_status_summary)
        if example_lines:
            lines.extend(["", *example_lines])

    troubleshooting_steps = _critical_troubleshooting_steps(payload, run_status_summary)
    if troubleshooting_steps:
        lines.extend([
            "",
            "Suggested next steps:",
            *_format_troubleshooting_steps(troubleshooting_steps),
        ])

    lines.extend([
        "",
        theme["attachments"],
        "",
        "Report folder:",
        str(report_dir),
        "",
        theme["closer"],
        "- Your SMD Autorouter",
    ])
    return "\n".join(lines)


def _build_success_email_body(mode, counts, report_dir, theme=None):
    theme = theme or _success_email_theme()
    counts = counts or {}
    document_label = _document_result_label(mode)
    app_name = _mode_display_name(mode)
    counsel_success = _count_value(counts, "counsel_success")
    document_success = _count_value(counts, "main_success")
    counsel_already = _count_value(counts, "counsel_already")
    document_already = _count_value(counts, "main_already")
    counsel_timeout = _count_value(counts, "counsel_timeout")
    document_timeout = _count_value(counts, "main_timeout")
    total_routed = counsel_success + document_success
    total_already = counsel_already + document_already
    total_timeouts = counsel_timeout + document_timeout

    document_only_mode = _is_document_only_mode(mode)
    lines = [
        theme["hello"],
        "",
        theme["opener"].format(app_name=app_name),
        "",
        theme["scoreboard"],
        _format_count_line("Mode", _format_mode_label(mode)),
        _format_count_line("Total routed", total_routed),
    ]

    if document_only_mode:
        lines.extend([
            _format_count_line(f"{document_label} routed", document_success),
            _format_count_line("Already processed", document_already),
        ])
    else:
        lines.extend([
            _format_count_line(f"{document_label} routed", document_success),
            _format_count_line("Counsel routed", counsel_success),
            _format_count_line("Already processed", total_already),
            _format_count_line(f"{document_label} already processed", document_already),
            _format_count_line("Counsel already processed", counsel_already),
        ])

    if total_timeouts:
        lines.append(_format_count_line("Related-LNI timeouts", total_timeouts))
        if document_only_mode:
            lines.append(_format_count_line(f"{document_label} timeouts", document_timeout))
        else:
            lines.extend([
                _format_count_line(f"{document_label} timeouts", document_timeout),
                _format_count_line("Counsel timeouts", counsel_timeout),
            ])

    lines.extend([
        "",
        theme["attachments"],
        "",
        "Report folder:",
        str(report_dir),
        "",
        theme["closer"],
        "- Your SMD Autorouter",
    ])
    return "\n".join(lines)


def _write_error_entries_workbook(report_dir):
    if not error_log_entries:
        return None
    try:
        import pandas as pd

        path = report_dir / "Error Entries.xlsx"
        pd.DataFrame(error_log_entries).to_excel(path, index=False)
        return path
    except Exception as exc:
        logging.warning("Failed to write critical error entries workbook: %s", exc)
        return None


def _get_outlook_user_email(outlook):
    try:
        session = outlook.Session
        for index in range(1, session.Accounts.Count + 1):
            account = session.Accounts.Item(index)
            smtp_address = getattr(account, "SmtpAddress", "") or ""
            if smtp_address:
                return smtp_address
    except Exception:
        pass

    try:
        address_entry = outlook.Session.CurrentUser.AddressEntry
        if address_entry.Type == "EX":
            exchange_user = address_entry.GetExchangeUser()
            if exchange_user:
                return exchange_user.PrimarySmtpAddress
        return address_entry.Address
    except Exception:
        return ""


def _valid_email(value):
    value = str(value or "").strip()
    return "@" in value and "." in value.split("@", 1)[-1]


def _send_outlook_email(subject, body, attachments, config):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        user_email = str(config.get("critical_error_user_email", "") or "").strip()
        if not user_email:
            user_email = _get_outlook_user_email(outlook)

        developer_email = str(config.get("critical_error_developer_email", "") or "").strip()
        if not developer_email:
            developer_email = DEFAULT_DEVELOPER_EMAIL

        recipients = []
        if _valid_email(user_email):
            recipients.append(user_email)
        if _valid_email(developer_email) and developer_email.lower() not in {r.lower() for r in recipients}:
            recipients.append(developer_email)

        if not recipients:
            logging.warning("Report saved, but no valid email recipients were configured.")
            return False

        recipients_text = "; ".join(recipients)
        mail = outlook.CreateItem(0)
        try:
            session = outlook.Session
            if session.Accounts.Count >= 1:
                mail.SendUsingAccount = session.Accounts.Item(1)
        except Exception:
            pass
        mail.To = recipients_text
        mail.Subject = subject
        mail.Body = body
        mail.Save()
        for attachment in attachments:
            if attachment and Path(attachment).exists():
                mail.Attachments.Add(str(Path(attachment).resolve()))
        mail.Save()
        mail.Send()
        logging.info("Report email sent to: %s", recipients_text)
        return True
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _build_report_folder(title, folder_name="Critical Error Reports"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%I-%M-%S_%p").lstrip("0")
    base_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / folder_name
    report_dir = base_dir / f"{timestamp} - {_safe_filename(title)}"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _write_summary(report_dir, payload, log_copy=None):
    summary_path = report_dir / "Critical Error Summary.txt"
    details = payload.get("details") or {}
    run_status_summary = payload.get("run_status_summary") or (
        details.get("Rerun Status Summary") if isinstance(details, dict) else None
    )
    lines = [
        "SMD Autorouter Critical Error Report",
        "=" * 39,
        f"Generated: {payload.get('timestamp')}",
        f"Machine: {payload.get('machine')}",
        f"User: {payload.get('windows_user')}",
        f"Run ID: {payload.get('run_id')}",
        f"Mode: {payload.get('mode')}",
        f"Router: {payload.get('router_label') or 'N/A'}",
        f"LNI: {payload.get('lni') or 'N/A'}",
        f"Docket: {payload.get('docket') or 'N/A'}",
        "",
        "Problem",
        "-------",
        str(payload.get("title") or ""),
        str(payload.get("error") or ""),
        "",
        "Details",
        "-------",
        json.dumps(details, indent=2, default=str) if details else "N/A",
    ]

    status_lines = _format_run_status_counts(run_status_summary)
    if status_lines:
        lines.extend(["", "Rerun-Ready Status", "------------------", *status_lines])
        example_lines = _format_run_status_examples(run_status_summary, max_rows=50)
        if example_lines:
            lines.extend(["", *example_lines])

    lines.extend([
        "",
        "Traceback",
        "---------",
        str(payload.get("traceback") or "N/A"),
    ])

    log_tail = _tail_text(log_copy)
    if log_tail:
        lines.extend(["", "Last Log Lines", "--------------", log_tail])

    with open(summary_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return summary_path


def notify_critical_error(
    title,
    error=None,
    *,
    latest_excel=None,
    mode=None,
    router_label=None,
    lni=None,
    docket=None,
    traceback_text=None,
    details=None,
    run_status_summary=None,
    config=None,
):
    """Create a critical report folder and send it by Outlook once per run."""
    run = _current_run()
    config = dict(config or run.get("config") or load_config())
    if not config.get("critical_error_email_enabled", True):
        logging.info("Critical error email notification skipped because it is disabled in config.")
        return None

    if not _mark_notified():
        logging.info("Critical error notification already sent for this run; skipping duplicate.")
        return None

    latest_excel = latest_excel or run.get("latest_excel")
    mode = mode or run.get("mode")
    report_dir = _build_report_folder(title)
    resolved_run_status_summary = run_status_summary or (
        (details or {}).get("Rerun Status Summary") if isinstance(details, dict) else None
    )
    if resolved_run_status_summary is None and status_updates_buffer:
        resolved_run_status_summary = summarize_statuses_for_rows(None)

    log_file = _get_current_log_file()
    log_copy = _copy_attachment(log_file, report_dir, "Current Run Log") if log_file else None
    excel_copy = _copy_attachment(latest_excel, report_dir, "Current Run Mapping Sheet")

    payload = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "machine": socket.gethostname(),
        "windows_user": os.environ.get("USERNAME", ""),
        "run_id": run.get("run_id", ""),
        "mode": mode,
        "router_label": router_label,
        "lni": lni,
        "docket": docket,
        "title": title,
        "error": str(error or ""),
        "traceback": traceback_text or "",
        "details": details or {},
        "run_status_summary": resolved_run_status_summary,
        "latest_excel": str(latest_excel or ""),
        "log_file": str(log_file or ""),
        "status_updates": {str(key): value for key, value in status_updates_buffer.items()},
        "error_log_entries": list(error_log_entries),
    }

    summary_path = _write_summary(report_dir, payload, log_copy)
    payload_path = _write_json(report_dir / "Critical Error Payload.json", payload)
    error_entries_path = _write_error_entries_workbook(report_dir)

    attachments = [summary_path, payload_path, log_copy, excel_copy, error_entries_path]
    attachments = [path for path in attachments if path]

    subject_mode = str(mode or "Autorouter").upper()
    email_theme = _critical_email_theme()
    subject = _critical_subject(subject_mode, payload["timestamp"], email_theme)
    body = _build_critical_email_body(payload, report_dir, email_theme)

    try:
        _send_outlook_email(subject, body, attachments, config)
    except Exception as exc:
        logging.warning("Critical report saved to %s, but Outlook email failed: %s", report_dir, exc)

    return report_dir


def _write_run_summary(report_dir, payload, log_copy=None):
    summary_path = report_dir / "Run Summary.txt"
    counts = payload.get("result_counts") or {}
    document_label = _document_result_label(payload.get("mode"))
    document_sentence_label = document_label[:1].upper() + document_label[1:] if document_label else "Main opinions"
    lines = [
        "SMD Autorouter Run Summary",
        "=" * 28,
        f"Generated: {payload.get('timestamp')}",
        f"Machine: {payload.get('machine')}",
        f"User: {payload.get('windows_user')}",
        f"Run ID: {payload.get('run_id')}",
        f"Mode: {payload.get('mode')}",
        "",
        "Result Counts",
        "-------------",
        f"Counsel successfully routed: {counts.get('counsel_success', 0)}",
        f"{document_sentence_label} successfully routed: {counts.get('main_success', 0)}",
        f"Counsel already processed: {counts.get('counsel_already', 0)}",
        f"{document_sentence_label} already processed: {counts.get('main_already', 0)}",
        f"Counsel related-LNI timeouts: {counts.get('counsel_timeout', 0)}",
        f"{document_sentence_label} related-LNI timeouts: {counts.get('main_timeout', 0)}",
        "",
        "Context",
        "-------",
        str(payload.get("context") or "N/A"),
    ]

    log_tail = _tail_text(log_copy, max_lines=40)
    if log_tail:
        lines.extend(["", "Last Log Lines", "--------------", log_tail])

    with open(summary_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return summary_path


def notify_successful_run(
    *,
    latest_excel=None,
    mode=None,
    result_counts=None,
    context=None,
    config=None,
):
    """Create and email a successful run summary once per run."""
    run = _current_run()
    config = dict(config or run.get("config") or load_config())
    if not config.get("run_summary_email_enabled", True):
        logging.info("Run summary email skipped because it is disabled in config.")
        return None

    if not _mark_completion_notified():
        logging.info("Run summary email skipped because a report was already sent for this run.")
        return None

    latest_excel = latest_excel or run.get("latest_excel")
    mode = mode or run.get("mode")
    report_dir = _build_report_folder("Completed Run Summary", "Run Summary Reports")

    log_file = _get_current_log_file()
    log_copy = _copy_attachment(log_file, report_dir, "Current Run Log") if log_file else None
    excel_copy = _copy_attachment(latest_excel, report_dir, "Completed Run Mapping Sheet")

    payload = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "machine": socket.gethostname(),
        "windows_user": os.environ.get("USERNAME", ""),
        "run_id": run.get("run_id", ""),
        "mode": mode,
        "context": context or "",
        "result_counts": result_counts or {},
        "latest_excel": str(latest_excel or ""),
        "log_file": str(log_file or ""),
        "status_updates": {str(key): value for key, value in status_updates_buffer.items()},
        "error_log_entries": list(error_log_entries),
    }

    summary_path = _write_run_summary(report_dir, payload, log_copy)
    payload_path = _write_json(report_dir / "Run Summary Payload.json", payload)
    attachments = [path for path in [summary_path, payload_path, log_copy, excel_copy] if path]

    counts = payload["result_counts"]
    subject_mode = str(mode or "Autorouter").upper()
    email_theme = _success_email_theme()
    subject = _success_subject(subject_mode, payload["timestamp"], email_theme)
    body = _build_success_email_body(mode, counts, report_dir, email_theme)

    try:
        _send_outlook_email(subject, body, attachments, config)
    except Exception as exc:
        logging.warning("Run summary saved to %s, but Outlook email failed: %s", report_dir, exc)

    return report_dir


def is_critical_status(status):
    normalized = str(status or "").strip().upper()
    return any(marker in normalized for marker in CRITICAL_STATUS_MARKERS)


def notify_for_critical_statuses(df, latest_excel=None, mode=None, config=None, context=None, run_status_summary=None):
    """Send one critical report if completed rows contain failure statuses."""
    if df is None or df.empty:
        return None

    affected_rows = []
    for idx, row in df.iterrows():
        status = status_updates_buffer.get(idx, row.get("Status", ""))
        if not is_critical_status(status):
            continue
        affected_rows.append({
            "Excel Row": idx + 2,
            "LNI": row.get("LNI", ""),
            "File Name": row.get("FileName", ""),
            "Status": status,
        })

    if not affected_rows:
        return None

    run_status_summary = run_status_summary or summarize_statuses_for_rows(df)

    return notify_critical_error(
        "One or more LNIs did not process cleanly",
        f"{len(affected_rows)} row(s) ended with a critical routing status.",
        latest_excel=latest_excel,
        mode=mode,
        details={
            "Context": context or "",
            "Affected Rows": affected_rows,
            "Rerun Status Summary": run_status_summary,
        },
        run_status_summary=run_status_summary,
        config=config,
    )
