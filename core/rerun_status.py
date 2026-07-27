"""Helpers for turning interrupted runs into rerun-ready mapping sheets.

The router writes row outcomes as it goes.  When a run is reset or crashes,
these helpers preserve completed rows and label the rest clearly so the next
run can skip finished work and focus on rows that still need attention.
"""

from __future__ import annotations

from collections import Counter
import logging
from typing import Any

import pandas as pd

from .smducar_config import mspb_metadata_buffer, status_updates_buffer
from .smducar_excel import flush_status_updates
from .smducar_filetypes import get_related_counsel_lnis, is_counsel
from .smducar_utils import extract_docket_number
from .itc_extractor import is_itc_row
from .irsplr_extractor import is_irsplr_row
from .ohtax0_extractor import is_ohtax0_row
from .mnsutb_extractor import is_mnsutb_row


STATUS_DONE = "DONE"
STATUS_ALREADY_PROCESSED = "ALREADY PROCESSED"
STATUS_PROCESSING = "PROCESSING"

STATUS_NEEDS_RERUN_SEARCH_FAILED = "NEEDS RERUN - SEARCH FAILED"
STATUS_NEEDS_RERUN_INTERRUPTED = "NEEDS RERUN - INTERRUPTED"
STATUS_NEEDS_RERUN_NOT_ATTEMPTED = "NEEDS RERUN - NOT ATTEMPTED"
STATUS_NEEDS_RERUN_FAILED = "NEEDS RERUN - FAILED"
STATUS_NEEDS_RERUN_COUNSEL_FAILED = "NEEDS RERUN - COUNSEL FAILED"

COMPLETED_STATUSES = {STATUS_DONE, STATUS_ALREADY_PROCESSED}
RERUN_STATUS_PREFIX = "NEEDS RERUN"


def normalize_status(status: Any) -> str:
    """Return a stable uppercase status string without treating NaN as data."""
    if status is None:
        return ""
    try:
        if pd.isna(status):
            return ""
    except Exception:
        pass
    text = str(status).strip()
    if text.lower() == "nan":
        return ""
    return text.upper()


def is_completed_status(status: Any) -> bool:
    return normalize_status(status) in COMPLETED_STATUSES


def mark_row_processing(row_index: int) -> None:
    """Mark a row as actively being handled unless it is already terminal."""
    if is_completed_status(status_updates_buffer.get(row_index)):
        return
    status_updates_buffer[row_index] = STATUS_PROCESSING


def mode_scope_df(df: pd.DataFrame | None, mode: str | None) -> pd.DataFrame:
    """Return rows that belong to the selected router mode."""
    if df is None or df.empty:
        return pd.DataFrame()

    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "itc":
        return df[df.apply(is_itc_row, axis=1)].copy()
    if normalized_mode == "irsplr":
        return df[df.apply(is_irsplr_row, axis=1)].copy()
    if normalized_mode == "ohtax0":
        return df[df.apply(is_ohtax0_row, axis=1)].copy()
    if normalized_mode == "mnsutb":
        return df[df.apply(is_mnsutb_row, axis=1)].copy()
    return df.copy()


def rerun_status_for(status: Any) -> str:
    """Convert a non-terminal status into a clear rerun label."""
    normalized = normalize_status(status)
    if normalized in COMPLETED_STATUSES:
        return normalized
    if normalized.startswith(RERUN_STATUS_PREFIX):
        return normalized
    if normalized in {"", STATUS_PROCESSING, "IN PROGRESS", "RUNNING", "STARTED"}:
        return STATUS_NEEDS_RERUN_INTERRUPTED if normalized else STATUS_NEEDS_RERUN_NOT_ATTEMPTED
    if "ROUTER SESSION LOST" in normalized or "AUTOMATION STOP" in normalized:
        return STATUS_NEEDS_RERUN_INTERRUPTED
    if "SEARCH FAILED" in normalized or "LNI NOT FOUND" in normalized or "LNI RE-SEARCH FAILED" in normalized:
        return STATUS_NEEDS_RERUN_SEARCH_FAILED
    return STATUS_NEEDS_RERUN_FAILED


def summarize_statuses_for_rows(
    df: pd.DataFrame | None,
    status_map: dict[int, str] | None = None,
    *,
    max_examples: int = 25,
) -> dict[str, Any]:
    """Build counts and sample rows for email/report payloads."""
    status_map = status_map or status_updates_buffer
    counts: Counter[str] = Counter()
    rerun_rows = []
    done_rows = []

    if df is None or df.empty:
        for status in status_map.values():
            normalized = normalize_status(status) or str(status or "").strip()
            if normalized:
                counts[normalized] += 1
        return {
            "counts": dict(counts),
            "done_count": counts.get(STATUS_DONE, 0),
            "already_processed_count": counts.get(STATUS_ALREADY_PROCESSED, 0),
            "needs_rerun_count": sum(v for k, v in counts.items() if k.startswith(RERUN_STATUS_PREFIX)),
            "rerun_rows": [],
            "done_rows": [],
        }

    for idx, row in df.iterrows():
        status = status_map.get(idx, row.get("Status", ""))
        normalized = normalize_status(status) or str(status or "").strip()
        if not normalized:
            continue
        counts[normalized] += 1
        row_info = {
            "Excel Row": int(idx) + 2,
            "LNI": str(row.get("LNI", "") or ""),
            "File Name": str(row.get("FileName", "") or row.get("File Name", "") or ""),
            "Status": normalized,
        }
        if normalized.startswith(RERUN_STATUS_PREFIX) and len(rerun_rows) < max_examples:
            rerun_rows.append(row_info)
        elif normalized in COMPLETED_STATUSES and len(done_rows) < max_examples:
            done_rows.append(row_info)

    return {
        "counts": dict(counts),
        "done_count": counts.get(STATUS_DONE, 0),
        "already_processed_count": counts.get(STATUS_ALREADY_PROCESSED, 0),
        "needs_rerun_count": sum(v for k, v in counts.items() if k.startswith(RERUN_STATUS_PREFIX)),
        "rerun_rows": rerun_rows,
        "done_rows": done_rows,
    }


def finalize_rerun_ready_statuses(
    *,
    df: pd.DataFrame | None,
    latest_excel: str | None = None,
    mode: str | None = None,
    scope_df: pd.DataFrame | None = None,
    flush: bool = False,
) -> dict[str, Any]:
    """Preserve completed rows and label unfinished rows for a rerun.

    This should run before critical emails copy the mapping sheet, especially
    after a manual reset or unexpected crash.
    """
    target_df = scope_df.copy() if scope_df is not None else mode_scope_df(df, mode)
    if target_df is None or target_df.empty:
        return summarize_statuses_for_rows(target_df)

    for idx, row in target_df.iterrows():
        current_status = status_updates_buffer.get(idx, row.get("Status", ""))
        normalized = normalize_status(current_status)
        if normalized in COMPLETED_STATUSES:
            status_updates_buffer[idx] = normalized
        else:
            status_updates_buffer[idx] = rerun_status_for(current_status)

    summary = summarize_statuses_for_rows(target_df)

    if flush and latest_excel and df is not None:
        try:
            merged_status_map = {
                idx: status_updates_buffer.get(idx, str(row.get("Status", "")))
                for idx, row in df.iterrows()
            }
            flush_status_updates(
                latest_excel,
                merged_status_map,
                mspb_metadata_buffer if mspb_metadata_buffer else None,
            )
            logging.info(
                "Rerun-ready statuses written to Excel: %d DONE, %d already processed, %d needing rerun.",
                summary.get("done_count", 0),
                summary.get("already_processed_count", 0),
                summary.get("needs_rerun_count", 0),
            )
        except Exception as exc:
            logging.warning("Failed to write rerun-ready statuses to Excel: %s", exc)

    return summary


def defer_main_rows_with_failed_counsel(
    main_df: pd.DataFrame,
    full_df: pd.DataFrame,
    *,
    dar_mode: bool = False,
    wc_mode: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Remove main rows whose required counsel did not finish cleanly.

    SMD/DAR main opinions depend on their paired counsel/ARC rows.  If a
    required counsel row fails, the main opinion should remain rerun-eligible
    instead of being processed with an incomplete pair.
    """
    if main_df is None or main_df.empty or full_df is None or full_df.empty:
        return main_df, []

    failed_counsel_lnis: set[str] = set()
    for idx, row in full_df.iterrows():
        file_name = str(row.get("FileName", "") or row.get("File Name", "") or "")
        if not is_counsel(file_name, dar_mode, wc_mode):
            continue

        status = normalize_status(status_updates_buffer.get(idx, row.get("Status", "")))
        if status in COMPLETED_STATUSES:
            continue

        lni = str(row.get("LNI", "") or "").strip()
        if lni and lni.lower() != "nan":
            failed_counsel_lnis.add(lni)

    if not failed_counsel_lnis:
        return main_df, []

    keep_indices = []
    deferred_rows = []
    for idx, row in main_df.iterrows():
        existing_status = normalize_status(status_updates_buffer.get(idx, row.get("Status", "")))
        if existing_status in COMPLETED_STATUSES:
            keep_indices.append(idx)
            continue

        file_name = str(row.get("FileName", "") or row.get("File Name", "") or "")
        docket = extract_docket_number(file_name, dar_mode, wc_mode)
        if not docket:
            keep_indices.append(idx)
            continue
        related_lnis = get_related_counsel_lnis(
            docket,
            full_df,
            recycled_lni=row.get("RecycledCounselLNI"),
            dar_mode=dar_mode,
            wc_mode=wc_mode,
        )
        blocking_lnis = [lni for lni in related_lnis if lni in failed_counsel_lnis]
        if blocking_lnis:
            status_updates_buffer[idx] = STATUS_NEEDS_RERUN_COUNSEL_FAILED
            deferred_rows.append({
                "Excel Row": int(idx) + 2,
                "LNI": str(row.get("LNI", "") or ""),
                "File Name": file_name,
                "Blocking Counsel LNIs": blocking_lnis,
                "Status": STATUS_NEEDS_RERUN_COUNSEL_FAILED,
            })
        else:
            keep_indices.append(idx)

    if not deferred_rows:
        return main_df, []

    return main_df.loc[keep_indices].copy(), deferred_rows
