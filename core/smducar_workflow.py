"""
Workflow orchestration module for SMDUCAR automation.

This module contains the main automation workflow that coordinates
Chrome setup, router creation, and batch processing.
"""

import os
import logging
import time
import traceback
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.chrome.options import Options

# Config and logging utilities
from .smducar_config import (
    load_config,
    status_updates_buffer,
    mspb_metadata_buffer,
    itc_content_fingerprint_buffer,
    error_log_entries,
)

# Excel utilities
from .smducar_excel import (
    flush_status_updates,
)

# File type detection
from .smducar_filetypes import (
    is_counsel,
    get_related_counsel_lnis,
)

from .smducar_utils import (
    extract_docket_number,
)

from .itc_extractor import (
    is_itc_row,
)

from .irsplr_extractor import (
    is_irsplr_row,
)

from .ohtax0_extractor import (
    is_ohtax0_row,
)

from .mnsutb_extractor import (
    is_mnsutb_row,
)

from .smducar_data import (
    filter_mapping_data,
)

# User utilities
from .smducar_user import (
    clean_display_name,
    get_full_username,
)

# Router class
from .smducar_router import (
    CaseLawRouter,
)

from .critical_error_notifier import (
    notify_critical_error,
    notify_for_critical_statuses,
    notify_successful_run,
    start_critical_error_run,
)

from .rerun_status import (
    defer_main_rows_with_failed_counsel,
    finalize_rerun_ready_statuses,
)

from .chromedriver_resolver import (
    resolve_chromedriver_path as resolve_compatible_chromedriver_path,
)


MAX_PARALLEL_ROUTERS = 6
COMPLETED_ROW_STATUSES = {"DONE", "ALREADY PROCESSED"}
_worker_log_context = threading.local()
_worker_log_factory_installed = False
_worker_log_factory_lock = threading.Lock()


def _install_worker_log_record_factory():
    """Prefix log messages emitted from parallel worker threads."""
    global _worker_log_factory_installed
    if _worker_log_factory_installed:
        return

    with _worker_log_factory_lock:
        if _worker_log_factory_installed:
            return

        original_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = original_factory(*args, **kwargs)
            worker_label = getattr(_worker_log_context, "worker_label", None)
            if worker_label:
                prefix = f"{worker_label} - "
                message = record.getMessage()
                if not message.startswith(prefix):
                    record.msg = prefix + message
                    record.args = ()
            return record

        logging.setLogRecordFactory(factory)
        _worker_log_factory_installed = True


def _set_worker_log_label(worker_label):
    _install_worker_log_record_factory()
    _worker_log_context.worker_label = worker_label


def _clear_worker_log_label():
    if hasattr(_worker_log_context, "worker_label"):
        delattr(_worker_log_context, "worker_label")


def _get_parallel_enabled(config):
    return bool(config.get("parallel_routers_enabled", config.get("mspb_parallel_enabled", False)))


def _get_parallel_lni_limit(config):
    return 0


def _get_parallel_router_count(config):
    try:
        requested_routers = int(config.get("parallel_router_instances", config.get("mspb_parallel_workers", 2)) or 2)
    except (TypeError, ValueError):
        requested_routers = 2
    return max(1, min(requested_routers, MAX_PARALLEL_ROUTERS))


def _get_mode_router_label(dar_mode=False, mspb_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    if mspb_mode:
        return "MSPB"
    if itc_mode:
        return "ITC"
    if irsplr_mode:
        return "IRSPLR"
    if ohtax0_mode:
        return "OHTAX0"
    if mnsutb_mode:
        return "MNSUTB"
    if dar_mode:
        return "DAR"
    return "SADM"


def _resolve_chromedriver_path():
    """Resolve a usable chromedriver.exe path once for a run."""
    return resolve_compatible_chromedriver_path()


def _build_chrome_options(config, download_dir):
    chrome_options = Options()
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    })

    if config.get("headless", False):
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
    else:
        chrome_options.add_argument("--start-maximized")

    return chrome_options


def _create_chrome_driver(driver_path, chrome_options, headless_mode):
    service = ChromeService(driver_path)
    logging.info("ChromeService created successfully.")
    driver = ChromeWebDriver(service=service, options=chrome_options)
    logging.info("Chrome instance created successfully.")
    try:
        driver.set_page_load_timeout(90)
    except Exception:
        logging.info("Could not set Chrome page load timeout.")

    if not headless_mode:
        try:
            logging.info("Maximizing browser window...")
            driver.maximize_window()
            time.sleep(1.0)
            logging.info("Browser window maximized.")
        except Exception as e:
            logging.warning(f"Could not maximize window: {e}")

    return driver


def _navigate_with_retries(driver, env_url, attempts=2):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                logging.info(f"Retrying navigation to: {env_url} (attempt {attempt}/{attempts})")
            driver.get(env_url)
            logging.info(f"Successfully navigated to: {env_url}")
            return
        except Exception as e:
            last_error = e
            logging.warning(f"Navigation attempt {attempt}/{attempts} failed: {e}")
            if attempt < attempts:
                time.sleep(5)
    raise last_error


def _open_search_inventory_with_recovery(router, driver, env_url, context_label, attempts=3):
    for attempt in range(1, attempts + 1):
        if router.click_search_inventory():
            if attempt > 1:
                logging.info("Search Inventory opened after refresh for %s.", context_label)
            return True

        if attempt < attempts:
            logging.info(
                "Search Inventory did not open for %s on attempt %d/%d; refreshing the Inventory page and trying again.",
                context_label,
                attempt,
                attempts,
            )
            try:
                _navigate_with_retries(driver, env_url, attempts=1)
            except Exception as exc:
                logging.warning("Search Inventory recovery navigation failed for %s: %s", context_label, exc)
            time.sleep(2)

    logging.error("Search Inventory did not open for %s after %d attempt(s).", context_label, attempts)
    return False


def _split_dataframe_evenly(df, worker_count):
    if worker_count <= 1:
        return [df]

    chunks = []
    total = len(df)
    base_size = total // worker_count
    remainder = total % worker_count
    start = 0

    for worker_index in range(worker_count):
        size = base_size + (1 if worker_index < remainder else 0)
        if size <= 0:
            continue
        chunks.append(df.iloc[start:start + size])
        start += size

    return chunks


def _select_parallel_rows(df, limit):
    if "LNI" not in df.columns:
        return df.iloc[0:0]

    valid_lni_mask = (
        df["LNI"].notna()
        & df["LNI"].astype(str).str.strip().ne("")
        & df["LNI"].astype(str).str.strip().str.lower().ne("nan")
    )
    if "Status" in df.columns:
        valid_lni_mask = valid_lni_mask & ~_completed_status_mask(df)
    selected = df[valid_lni_mask].copy()
    if limit and limit > 0:
        selected = selected.head(limit)
    return selected


def _completed_status_mask(df):
    if "Status" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Status"].astype(str).str.strip().str.upper().isin(COMPLETED_ROW_STATUSES)


def _select_parallel_document_rows(df_filtered, full_df, limit, dar_mode=False, wc_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    selected = _select_parallel_rows(df_filtered, limit)
    if selected.empty:
        return selected
    if itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode:
        return selected

    selected_indices = set(selected.index)
    counsel_lni_to_indices = {}

    for idx, row in df_filtered.iterrows():
        file_name = str(row.get("FileName", "")).strip()
        if not is_counsel(file_name, dar_mode, wc_mode):
            continue
        lni = str(row.get("LNI", "")).strip()
        if lni and lni.lower() != "nan":
            counsel_lni_to_indices.setdefault(lni, []).append(idx)

    dependency_indices = []
    for _, row in selected.iterrows():
        file_name = str(row.get("FileName", "")).strip()
        if is_counsel(file_name, dar_mode, wc_mode):
            continue

        main_docket = extract_docket_number(file_name, dar_mode, wc_mode)
        if not main_docket:
            continue

        related_lnis = get_related_counsel_lnis(
            main_docket,
            full_df,
            recycled_lni=row.get("RecycledCounselLNI"),
            dar_mode=dar_mode,
            wc_mode=wc_mode,
        )
        for lni in related_lnis:
            for dependency_idx in counsel_lni_to_indices.get(str(lni).strip(), []):
                if dependency_idx not in selected_indices:
                    selected_indices.add(dependency_idx)
                    dependency_indices.append(dependency_idx)

    if dependency_indices:
        selected = pd.concat([selected, df_filtered.loc[dependency_indices]], axis=0)
        selected = selected.loc[~selected.index.duplicated(keep="first")].sort_index()
        logging.info(
            "Parallel router mode added %d related counsel row(s) needed by selected main opinion rows.",
            len(dependency_indices),
        )

    return selected


def _is_counsel_result_row(row, mspb_mode, dar_mode, wc_mode, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    """Return True when a result row should be counted under the counsel bucket."""
    if mspb_mode or itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode:
        return False
    return is_counsel(str(row.get("FileName", "")), dar_mode, wc_mode)


def _empty_result_counts():
    return (0, 0, 0, 0, 0, 0)


def _count_results_for_rows(df, mspb_mode, dar_mode, wc_mode, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False, current_run_only=False):
    counsel_success = 0
    main_success = 0
    counsel_already = 0
    main_already = 0
    counsel_timeout = 0
    main_timeout = 0

    for idx, row in df.iterrows():
        if current_run_only and idx not in status_updates_buffer:
            continue

        is_counsel_file = _is_counsel_result_row(
            row,
            mspb_mode,
            dar_mode,
            wc_mode,
            itc_mode=itc_mode,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
        )
        status = str(status_updates_buffer.get(idx, str(row.get("Status", "")))).strip()
        normalized_status = status.upper()

        if normalized_status == "DONE":
            if is_counsel_file:
                counsel_success += 1
            else:
                main_success += 1
        elif normalized_status == "ALREADY PROCESSED":
            if is_counsel_file:
                counsel_already += 1
            else:
                main_already += 1
        elif normalized_status == "RELATED LNI TIMEOUT":
            if is_counsel_file:
                counsel_timeout += 1
            else:
                main_timeout += 1

    return counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout


def _result_counts_payload(result_counts):
    keys = (
        "counsel_success",
        "main_success",
        "counsel_already",
        "main_already",
        "counsel_timeout",
        "main_timeout",
    )
    values = list(result_counts or ())
    values.extend([0] * (len(keys) - len(values)))
    return dict(zip(keys, values[:len(keys)]))


def _write_error_report_if_needed():
    if not error_log_entries:
        return

    try:
        error_df = pd.DataFrame(error_log_entries)
        timestamp = datetime.datetime.now().strftime("%I-%M-%S_%p").lstrip("0")
        error_folder = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Error Reports"
        error_folder.mkdir(parents=True, exist_ok=True)
        error_path = error_folder / f"Error Report - {timestamp}.xlsx"
        error_df.to_excel(error_path, index=False)
        logging.info(f"Error report saved to {error_path}")
    except Exception as e:
        logging.warning(f"Failed to write error report: {e}")


def _write_router_split_workbook(router_id, batch_type, router_df, output_dir):
    """Write the SADM/DAR rows assigned to one parallel router for documentation."""
    if router_df is None or router_df.empty:
        return

    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        output_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = output_dir / f"Router {router_id} - Case Law Auto-Routing Split.xlsx"
        sheet_name = (
            "ITC Split" if batch_type == "itc"
            else "IRSPLR Split" if batch_type == "irsplr"
            else "OHTAX0 Split" if batch_type == "ohtax0"
            else "MNSUTB Split" if batch_type == "mnsutb"
            else "Counsel Split" if batch_type == "counsel"
            else "Main Split"
        )

        if workbook_path.exists():
            wb = load_workbook(workbook_path)
        else:
            wb = Workbook()

        if sheet_name in wb.sheetnames:
            del wb[sheet_name]

        ws = wb.create_sheet(sheet_name)
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1 and not list(wb["Sheet"].values):
            del wb["Sheet"]

        headers = [
            "Source Excel Row",
            "Router",
            "Batch",
            "Require Cardinal Process",
            "Court Code",
            "File Name",
            "LNI",
            "Tier",
            "Received Date",
            "Time Left",
            "Recycled Counsel LNI",
            "Source Detail",
            "Comments",
            "Decision Date",
            "Status",
        ]
        source_columns = {
            "Require Cardinal Process": "RequireCardinal",
            "Court Code": "CourtCode",
            "File Name": "FileName",
            "LNI": "LNI",
            "Received Date": "ReceivedDate",
            "Recycled Counsel LNI": "RecycledCounselLNI",
            "Source Detail": "SourceDetail",
            "Comments": "Comments",
            "Decision Date": "Decision Date",
        }

        header_font = Font(name="Aptos Display", size=12, bold=True)
        header_fill = PatternFill(start_color="E7CCFC", end_color="E7CCFC", fill_type="solid")
        alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment
            cell.border = border

        status_styles = {
            "DONE": {"bold": True, "color": "00A86B"},
            "ALREADY PROCESSED": {"bold": True, "color": "4F39BC"},
            "ERROR: LNI NOT FOUND": {"bold": True, "color": "E3242B"},
            "ERROR: INVALID LNI FORMAT": {"bold": True, "color": "E3242B"},
            "ERROR: UNABLE TO LOAD IRT FORM WINDOW": {"bold": True, "color": "E3242B"},
            "ERROR": {"bold": True, "color": "E3242B"},
            "RELATED LNI ERROR": {"bold": True, "color": "E3242B"},
            "NO COUNSEL ATTACHED": {"bold": True, "color": "E3242B"},
            "RELATED LNI TIMEOUT": {"bold": True, "color": "E3242B"},
        }

        for output_row, (idx, row) in enumerate(router_df.iterrows(), 2):
            final_status = status_updates_buffer.get(idx, str(row.get("Status", "")))
            values = {
                "Source Excel Row": idx + 2,
                "Router": f"Router {router_id}",
                "Batch": (
                    "ITC" if batch_type == "itc"
                    else "IRSPLR" if batch_type == "irsplr"
                    else "OHTAX0" if batch_type == "ohtax0"
                    else "MNSUTB" if batch_type == "mnsutb"
                    else "Counsel" if batch_type == "counsel"
                    else "Main Opinion"
                ),
                "Status": final_status,
            }
            for header, source_column in source_columns.items():
                values[header] = row.get(source_column, "")

            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=output_row, column=col_num, value=values.get(header, ""))
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.border = border
                if header == "Status":
                    normalized_status = str(final_status).strip().upper()
                    style = status_styles.get(normalized_status)
                    if style:
                        cell.font = Font(bold=style["bold"], color=style["color"])

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max(max_length + 2, 10), 60)

        wb.save(workbook_path)
        logging.info(f"Router split workbook updated: {workbook_path}")
    except Exception as e:
        logging.warning(f"Failed to write router split workbook for Router {router_id}: {e}")


def _run_mspb_worker(worker_id, worker_df, latest_excel, config, driver_path, env_url,
                     create_router, show_error, set_status, update_progress):
    driver = None
    worker_name = f"MSPB Router {worker_id}"
    _set_worker_log_label(worker_name)
    download_dir = (
        Path.home()
        / "Downloads"
        / "Case Law Auto-Routing Resources"
        / "MSPB PDF Downloads"
        / f"Router {worker_id}"
    )
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        logging.info(f"Starting with {len(worker_df)} LNI(s).")
        chrome_options = _build_chrome_options(config, download_dir)
        driver = _create_chrome_driver(driver_path, chrome_options, config.get("headless", False))
        logging.info(f"Navigating to: {env_url}")
        _navigate_with_retries(driver, env_url)

        router = create_router(driver, show_error=show_error, set_status=set_status) if create_router else CaseLawRouter(
            driver,
            show_error=show_error,
            set_status=set_status,
        )
        router.mspb_download_dir = download_dir
        router.mspb_download_dir.mkdir(parents=True, exist_ok=True)
        if not _open_search_inventory_with_recovery(router, driver, env_url, worker_name):
            raise RuntimeError(f"{worker_name} could not open Search Inventory before processing MSPB rows.")
        router.process_rows(worker_df, latest_excel, update_progress, mspb_mode=True)
        logging.info("Completed.")
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Failed: {e}")
        logging.error(f"Traceback: {tb}")
        for idx, row in worker_df.iterrows():
            if idx not in status_updates_buffer:
                status_updates_buffer[idx] = "ERROR"
                error_log_entries.append({
                    "Row": idx + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR",
                    "Error Message": str(e),
                })
        logging.warning(
            "%s failed; final rerun-ready labels and the critical email will be prepared after all routers stop.",
            worker_name,
        )
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            logging.warning("Browser cleanup failed.")
        _clear_worker_log_label()


def _run_parallel_mspb_workflow(update_progress=None, set_status=None, show_success=None, show_error=None,
                                create_router=None, latest_excel=None, df=None, df_filtered=None, config=None):
    config = config or load_config()
    df_filtered = df_filtered if df_filtered is not None else df

    limit = _get_parallel_lni_limit(config)
    requested_workers = _get_parallel_router_count(config)

    selected_df = _select_parallel_rows(df_filtered, limit)
    if selected_df.empty:
        logging.warning("MSPB parallel mode found no valid LNI rows to process.")
        if show_error:
            show_error("MSPB parallel mode found no valid LNI rows to process.")
        return pd.DataFrame(), pd.DataFrame()

    worker_count = min(requested_workers, len(selected_df))
    chunks = _split_dataframe_evenly(selected_df, worker_count)
    total_selected = len(selected_df)
    logging.info(
        "MSPB parallel mode enabled: %d LNI(s), %d router(s), requested limit=%s.",
        total_selected,
        worker_count,
        "all" if limit <= 0 else limit,
    )

    if set_status:
        set_status("MSPB Parallel Batch Started")

    base_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MSPB PDF Downloads"
    base_download_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Setting up ChromeDriver for MSPB parallel routers...")
    driver_path = _resolve_chromedriver_path()
    env_url = {
        "prod": "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/",
        "staging": "https://tcfabstaging.lexisnexis.com/shared/InventoryInvoicing/"
    }.get(config.get("environment", "prod"))

    progress_lock = threading.Lock()
    worker_progress = {worker_id: 0 for worker_id in range(1, len(chunks) + 1)}

    def make_worker_progress(worker_id):
        def update_worker_progress(batch, current, total):
            if batch != "mspb":
                return
            with progress_lock:
                worker_progress[worker_id] = current
                aggregate_current = min(sum(worker_progress.values()), total_selected)
            if update_progress:
                update_progress("mspb", aggregate_current, total_selected)
        return update_worker_progress

    if update_progress:
        update_progress("mspb", 0, total_selected)

    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = []
        for worker_id, chunk in enumerate(chunks, start=1):
            futures.append(executor.submit(
                _run_mspb_worker,
                worker_id,
                chunk,
                latest_excel,
                config,
                driver_path,
                env_url,
                create_router,
                show_error,
                set_status,
                make_worker_progress(worker_id),
            ))

        for future in as_completed(futures):
            future.result()

    if set_status:
        set_status("MSPB Batch Processed")

    rerun_summary = finalize_rerun_ready_statuses(
        df=df,
        latest_excel=None,
        mode="mspb",
        scope_df=selected_df,
        flush=False,
    )
    result_counts = _count_results_for_rows(selected_df, True, False, False, current_run_only=True)
    user_name = clean_display_name(get_full_username())
    if show_success:
        show_success(user_name, *result_counts)

    excel_flushed = False
    try:
        merged_status_map = {idx: status_updates_buffer.get(idx, str(row["Status"])) for idx, row in df.iterrows()}
        flush_status_updates(latest_excel, merged_status_map, mspb_metadata_buffer)
        excel_flushed = True
    except Exception as e:
        logging.warning(f"Failed to write MSPB parallel results to Excel: {e}")
        if show_error:
            show_error(f"Failed to write MSPB parallel results to Excel: {e}")

    _write_error_report_if_needed()
    notify_for_critical_statuses(
        selected_df,
        latest_excel=latest_excel,
        mode="mspb",
        config=config,
        context="MSPB parallel router run",
        run_status_summary=rerun_summary,
    )
    if excel_flushed:
        notify_successful_run(
            latest_excel=latest_excel,
            mode="mspb",
            result_counts=_result_counts_payload(result_counts),
            context="MSPB parallel router run completed.",
            config=config,
        )
    else:
        logging.warning("Run summary email skipped because the mapping sheet was not flushed successfully.")
    logging.info("MSPB parallel mode completed.")
    return pd.DataFrame(), selected_df


def _run_document_router_phase(router_id, batch_type, router_df, full_df, latest_excel, config, driver_path, env_url,
                               create_router, show_error, set_status, update_progress, dar_mode, wc_mode, mode_label,
                               irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    driver = None
    router_name = f"{mode_label} Router {router_id}"
    _set_worker_log_label(router_name)
    download_dir = (
        Path.home()
        / "Downloads"
        / "Case Law Auto-Routing Resources"
        / "Parallel Router Downloads"
        / f"Router {router_id}"
    )
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        logging.info(f"Starting {batch_type} batch with {len(router_df)} LNI(s).")
        chrome_options = _build_chrome_options(config, download_dir)
        driver = _create_chrome_driver(driver_path, chrome_options, config.get("headless", False))
        logging.info(f"Navigating to: {env_url}")
        _navigate_with_retries(driver, env_url)

        router = create_router(driver, show_error=show_error, set_status=set_status) if create_router else CaseLawRouter(
            driver,
            show_error=show_error,
            set_status=set_status,
        )
        router.mspb_download_dir = download_dir / "MSPB PDF Downloads"
        router.mspb_download_dir.mkdir(parents=True, exist_ok=True)
        router.itc_download_dir = download_dir / "ITC PDF Downloads"
        router.itc_download_dir.mkdir(parents=True, exist_ok=True)
        router.irsplr_download_dir = download_dir / "IRSPLR PDF Downloads"
        router.irsplr_download_dir.mkdir(parents=True, exist_ok=True)
        router.ohtax0_download_dir = download_dir / "OHTAX0 PDF Downloads"
        router.ohtax0_download_dir.mkdir(parents=True, exist_ok=True)
        router.mnsutb_download_dir = download_dir / "MNSUTB PDF Downloads"
        router.mnsutb_download_dir.mkdir(parents=True, exist_ok=True)
        router.full_df = full_df
        if not _open_search_inventory_with_recovery(router, driver, env_url, router_name):
            raise RuntimeError(f"{router_name} could not open Search Inventory before processing {batch_type} rows.")
        processed_count, duration = router.process_batch(
            router_df,
            full_df,
            latest_excel,
            update_progress,
            batch_type,
            dar_mode,
            wc_mode,
            mspb_mode=False,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
        )
        logging.info(f"Completed {batch_type} batch.")
        return processed_count, duration
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Failed during {batch_type} batch: {e}")
        logging.error(f"Traceback: {tb}")
        for idx, row in router_df.iterrows():
            if idx not in status_updates_buffer:
                status_updates_buffer[idx] = "ERROR"
                error_log_entries.append({
                    "Row": idx + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR",
                    "Error Message": str(e),
                })
        logging.warning(
            "%s failed during %s; final rerun-ready labels and the critical email will be prepared after all routers stop.",
            router_name,
            batch_type,
        )
        return 0, 0
    finally:
        _write_router_split_workbook(router_id, batch_type, router_df, download_dir)
        try:
            if driver:
                driver.quit()
        except Exception:
            logging.warning("Browser cleanup failed.")
        _clear_worker_log_label()


def _run_parallel_document_phase(batch_type, phase_df, full_df, latest_excel, config, driver_path, env_url,
                                 requested_routers, update_progress, create_router, show_error, set_status,
                                 dar_mode, wc_mode, mode_label, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    if phase_df.empty:
        if update_progress:
            update_progress(batch_type, 0, 0)
        return 0, 0

    router_count = min(requested_routers, len(phase_df))
    chunks = _split_dataframe_evenly(phase_df, router_count)
    total_rows = len(phase_df)
    progress_lock = threading.Lock()
    router_progress = {router_id: 0 for router_id in range(1, len(chunks) + 1)}

    def make_router_progress(router_id):
        def update_router_progress(batch, current, total):
            if batch != batch_type:
                return
            with progress_lock:
                router_progress[router_id] = current
                aggregate_current = min(sum(router_progress.values()), total_rows)
            if update_progress:
                update_progress(batch_type, aggregate_current, total_rows)
        return update_router_progress

    if update_progress:
        update_progress(batch_type, 0, total_rows)

    processed_count = 0
    total_duration = 0
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = []
        for router_id, chunk in enumerate(chunks, start=1):
            futures.append(executor.submit(
                _run_document_router_phase,
                router_id,
                batch_type,
                chunk,
                full_df,
                latest_excel,
                config,
                driver_path,
                env_url,
                create_router,
                show_error,
                set_status,
                make_router_progress(router_id),
                dar_mode,
                wc_mode,
                mode_label,
                irsplr_mode,
                ohtax0_mode,
                mnsutb_mode,
            ))

        for future in as_completed(futures):
            count, duration = future.result()
            processed_count += count or 0
            total_duration += duration or 0

    return processed_count, total_duration


def _run_parallel_document_workflow(update_progress=None, set_status=None, show_success=None, show_error=None,
                                    create_router=None, latest_excel=None, df=None, df_filtered=None, config=None,
                                    dar_mode=False, wc_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    config = config or load_config()
    df_filtered = df_filtered if df_filtered is not None else df

    limit = _get_parallel_lni_limit(config)
    requested_routers = _get_parallel_router_count(config)
    selected_df = _select_parallel_document_rows(
        df_filtered,
        df,
        limit,
        dar_mode,
        wc_mode,
        itc_mode=itc_mode,
        irsplr_mode=irsplr_mode,
        ohtax0_mode=ohtax0_mode,
        mnsutb_mode=mnsutb_mode,
    )

    if selected_df.empty:
        logging.warning("Parallel router mode found no valid LNI rows to process.")
        if show_error:
            show_error("Parallel router mode found no valid LNI rows to process.")
        return pd.DataFrame(), pd.DataFrame()

    if itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode:
        counsel_df = selected_df.iloc[0:0].copy()
        main_df = selected_df.copy()
    else:
        counsel_df, main_df = filter_mapping_data(selected_df, dar_mode, wc_mode, mspb_mode=False)
    mode_label = _get_mode_router_label(
        dar_mode=dar_mode,
        itc_mode=itc_mode,
        irsplr_mode=irsplr_mode,
        ohtax0_mode=ohtax0_mode,
        mnsutb_mode=mnsutb_mode,
    )
    logging.info(
        "%s parallel router mode enabled: %d LNI(s), %d counsel, %d main, requested limit=%s, router instances=%d.",
        mode_label,
        len(selected_df),
        len(counsel_df),
        len(main_df),
        "all" if limit <= 0 else limit,
        min(requested_routers, len(selected_df)),
    )

    logging.info("Setting up ChromeDriver for parallel routers...")
    driver_path = _resolve_chromedriver_path()
    env_url = {
        "prod": "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/",
        "staging": "https://tcfabstaging.lexisnexis.com/shared/InventoryInvoicing/"
    }.get(config.get("environment", "prod"))

    if itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode:
        counsel_count = 0
        counsel_duration = 0
        batch_type = "itc" if itc_mode else "irsplr" if irsplr_mode else "ohtax0" if ohtax0_mode else "mnsutb"
        logging.info("=== Starting Parallel %s Batch ===", mode_label)
        if set_status:
            set_status(f"{mode_label} Batch Started")
        main_count, main_duration = _run_parallel_document_phase(
            batch_type,
            main_df,
            df,
            latest_excel,
            config,
            driver_path,
            env_url,
            requested_routers,
            update_progress,
            create_router,
            show_error,
            set_status,
            dar_mode,
            wc_mode,
            mode_label,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
        )
        if set_status:
            set_status(f"{mode_label} Batch Processed")
    else:
        logging.info("=== Starting Parallel Counsel Batch ===")
        if set_status:
            set_status("Counsel Batch Started")
        counsel_count, counsel_duration = _run_parallel_document_phase(
            "counsel",
            counsel_df,
            df,
            latest_excel,
            config,
            driver_path,
            env_url,
            requested_routers,
            update_progress,
            create_router,
            show_error,
            set_status,
            dar_mode,
            wc_mode,
            mode_label,
            irsplr_mode=False,
        )
        if set_status:
            set_status("Counsel Batch Processed")

        main_df, deferred_main_rows = defer_main_rows_with_failed_counsel(
            main_df,
            df,
            dar_mode=dar_mode,
            wc_mode=wc_mode,
        )
        if deferred_main_rows:
            logging.warning(
                "Deferred %d main opinion row(s) because required counsel did not finish cleanly.",
                len(deferred_main_rows),
            )

        logging.info("=== Starting Parallel Main Opinion Batch ===")
        if set_status:
            set_status("Main Opinion Batch Started")
        main_count, main_duration = _run_parallel_document_phase(
            "main",
            main_df,
            df,
            latest_excel,
            config,
            driver_path,
            env_url,
            requested_routers,
            update_progress,
            create_router,
            show_error,
            set_status,
            dar_mode,
            wc_mode,
            mode_label,
            irsplr_mode=False,
        )
        if set_status:
            set_status("Main Opinion Batch Processed")

    total_count = counsel_count + main_count
    total_time = counsel_duration + main_duration
    if total_count > 0:
        overall_avg = total_time / total_count
        overall_est_per_hour = int(3600 / overall_avg) if overall_avg else 0
        logging.info(
            "[PARALLEL ROUTER SUMMARY] TOTAL: %d LNIs processed in %dm %ds",
            total_count,
            int(total_time // 60),
            int(total_time % 60),
        )
        if itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode:
            logging.info(
                "    - %s: %d LNIs in %dm %ds",
                mode_label,
                main_count,
                int(main_duration // 60),
                int(main_duration % 60),
            )
        else:
            logging.info(
                "    - Counsel: %d LNIs in %dm %ds",
                counsel_count,
                int(counsel_duration // 60),
                int(counsel_duration % 60),
            )
            logging.info(
                "    - Main Opinion: %d LNIs in %dm %ds",
                main_count,
                int(main_duration // 60),
                int(main_duration % 60),
            )
        logging.info("    - Overall Avg: %.1fs/LNI -> Est. %d LNIs/hour", overall_avg, overall_est_per_hour)

    if set_status:
        set_status("Success!")

    summary_df = selected_df if itc_mode or irsplr_mode or ohtax0_mode or mnsutb_mode or limit > 0 else df
    rerun_summary = finalize_rerun_ready_statuses(
        df=df,
        latest_excel=None,
        mode=mode_label.lower(),
        scope_df=selected_df,
        flush=False,
    )
    result_counts = _count_results_for_rows(
        summary_df,
        False,
        dar_mode,
        wc_mode,
        itc_mode=itc_mode,
        irsplr_mode=irsplr_mode,
        ohtax0_mode=ohtax0_mode,
        mnsutb_mode=mnsutb_mode,
        current_run_only=True,
    )
    user_name = clean_display_name(get_full_username())
    if show_success:
        show_success(user_name, *result_counts)

    excel_flushed = False
    try:
        merged_status_map = {idx: status_updates_buffer.get(idx, str(row["Status"])) for idx, row in df.iterrows()}
        flush_status_updates(latest_excel, merged_status_map, mspb_metadata_buffer if mspb_metadata_buffer else None)
        excel_flushed = True
    except Exception as e:
        logging.warning(f"Failed to write parallel router results to Excel: {e}")
        if show_error:
            show_error(f"Failed to write parallel router results to Excel: {e}")

    _write_error_report_if_needed()
    notify_for_critical_statuses(
        selected_df,
        latest_excel=latest_excel,
        mode=mode_label.lower(),
        config=config,
        context=f"{mode_label} parallel router run",
        run_status_summary=rerun_summary,
    )
    if excel_flushed:
        notify_successful_run(
            latest_excel=latest_excel,
            mode=mode_label.lower(),
            result_counts=_result_counts_payload(result_counts),
            context=f"{mode_label} parallel router run completed.",
            config=config,
        )
    else:
        logging.warning("Run summary email skipped because the mapping sheet was not flushed successfully.")
    logging.info("Parallel router mode completed.")
    return counsel_df, main_df


def run_automation_workflow(update_progress=None, set_status=None, show_success=None, show_error=None, total_count=1,
                            create_router=None, latest_excel=None, df=None, dar_mode=False, wc_mode=False, mspb_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
    """
    Main automation workflow that orchestrates the entire process.
    
    Args:
        update_progress: Callback function for progress updates
        set_status: Callback function for status updates
        show_success: Callback function to show success message
        show_error: Callback function to show error messages
        total_count: Total number of items to process
        create_router: Optional function to create a custom router instance
        latest_excel: Path to the Excel file
        df: DataFrame containing the mapping data
        dar_mode: Whether DAR mode is enabled
        wc_mode: Whether WC mode is enabled
        mspb_mode: Whether MSPB mode is enabled
        itc_mode: Whether ITC mode is enabled
        irsplr_mode: Whether IRSPLR mode is enabled
        ohtax0_mode: Whether OHTAX0 mode is enabled
        mnsutb_mode: Whether MNSUTB mode is enabled
    
    Returns:
        Tuple of (counsel_df, main_df) DataFrames
    """
    # Clear the buffer at the start of each run
    status_updates_buffer.clear()
    mspb_metadata_buffer.clear()
    itc_content_fingerprint_buffer.clear()
    error_log_entries.clear()

    try:
        # Use provided latest_excel and df, do not reload
        if latest_excel is None or df is None:
            logging.error("latest_excel and df must be provided by the caller.")
            return
        if df.empty:
            logging.error("Excel data is empty or invalid.")
            return

        # Count already processed rows before filtering
        if itc_mode:
            run_scope_df = df[df.apply(is_itc_row, axis=1)].copy()
            if run_scope_df.empty:
                logging.warning("ITC Autorouter mode found no FDITC000/FDITCALJ rows to process.")
                if show_error:
                    show_error("ITC Autorouter mode found no FDITC000/FDITCALJ rows to process.")
                return pd.DataFrame(), pd.DataFrame()
        elif irsplr_mode:
            run_scope_df = df[df.apply(is_irsplr_row, axis=1)].copy()
            if run_scope_df.empty:
                logging.warning("IRSPLR Autorouter mode found no FDIRSPLR/FDPLR000/FDCCA001 rows to process.")
                if show_error:
                    show_error("IRSPLR Autorouter mode found no FDIRSPLR/FDPLR000/FDCCA001 rows to process.")
                return pd.DataFrame(), pd.DataFrame()
        elif ohtax0_mode:
            run_scope_df = df[df.apply(is_ohtax0_row, axis=1)].copy()
            if run_scope_df.empty:
                logging.warning("OHTAX0 Autorouter mode found no STOHTAX0 rows to process.")
                if show_error:
                    show_error("OHTAX0 Autorouter mode found no STOHTAX0 rows to process.")
                return pd.DataFrame(), pd.DataFrame()
        elif mnsutb_mode:
            run_scope_df = df[df.apply(is_mnsutb_row, axis=1)].copy()
            if run_scope_df.empty:
                logging.warning("MNSUTB Autorouter mode found no STMNSUTB rows to process.")
                if show_error:
                    show_error("MNSUTB Autorouter mode found no STMNSUTB rows to process.")
                return pd.DataFrame(), pd.DataFrame()
        else:
            run_scope_df = df

        completed_status_mask = _completed_status_mask(run_scope_df)
        df_filtered = run_scope_df[~completed_status_mask].copy()
        completed_count = int(completed_status_mask.sum())
        if completed_count:
            logging.info(
                "Skipping %d completed row(s) already marked DONE or ALREADY PROCESSED.",
                completed_count,
            )

        if df_filtered.empty:
            logging.info("No unfinished rows found for this run; nothing new to route.")
            result_counts = _empty_result_counts()
            user_name = clean_display_name(get_full_username())
            if show_success:
                show_success(user_name, *result_counts)
            return pd.DataFrame(), pd.DataFrame()

        config = load_config()
        headless_mode = config.get("headless", False)
        current_mode = "mspb" if mspb_mode else "itc" if itc_mode else "irsplr" if irsplr_mode else "ohtax0" if ohtax0_mode else "mnsutb" if mnsutb_mode else "dar" if dar_mode else "smd"
        start_critical_error_run(latest_excel=latest_excel, mode=current_mode, config=config)
        logging.info(f"Headless mode setting: {headless_mode}")

        if _get_parallel_enabled(config):
            if mspb_mode:
                return _run_parallel_mspb_workflow(
                    update_progress=update_progress,
                    set_status=set_status,
                    show_success=show_success,
                    show_error=show_error,
                    create_router=create_router,
                    latest_excel=latest_excel,
                    df=df,
                    df_filtered=df_filtered,
                    config=config,
                )
            return _run_parallel_document_workflow(
                update_progress=update_progress,
                set_status=set_status,
                show_success=show_success,
                show_error=show_error,
                create_router=create_router,
                latest_excel=latest_excel,
                df=df,
                df_filtered=df_filtered,
                config=config,
                dar_mode=dar_mode,
                wc_mode=wc_mode,
                itc_mode=itc_mode,
                irsplr_mode=irsplr_mode,
                ohtax0_mode=ohtax0_mode,
                mnsutb_mode=mnsutb_mode,
            )

        chrome_options = Options()
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        mspb_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MSPB PDF Downloads"
        mspb_download_dir.mkdir(parents=True, exist_ok=True)
        chrome_options.add_experimental_option("prefs", {
            "download.default_directory": str(mspb_download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        })
        if headless_mode:
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            logging.info("Chrome launched in HEADLESS mode")
        else:
            chrome_options.add_argument("--start-maximized")
            # Removed detach option - it can cause Chrome to close immediately
            logging.info("Chrome launched in VISIBLE mode (headless disabled)")

        logging.info("Setting up ChromeDriver...")
        try:
            driver_path = _resolve_chromedriver_path()
            service = ChromeService(driver_path)
            logging.info("ChromeService created successfully.")
        except Exception as e:
            logging.error(f"Failed to setup ChromeDriver: {e}")
            logging.error(f"ChromeDriver setup traceback: {traceback.format_exc()}")
            raise
        
        logging.info("Creating Chrome browser instance...")
        try:
            driver = ChromeWebDriver(service=service, options=chrome_options)
            logging.info("Chrome instance created successfully.")
        except Exception as e:
            logging.error(f"Failed to create Chrome browser instance: {e}")
            logging.error(f"Chrome creation traceback: {traceback.format_exc()}")
            raise
        
        # If not headless, try to bring window to front
        if not headless_mode:
            try:
                logging.info("Maximizing browser window...")
                driver.maximize_window()
                # Small delay to ensure window is ready
                time.sleep(1.0)
                
                # Try to bring Chrome window to front using Windows API
                try:
                    import win32gui
                    import win32con
                    
                    def enum_handler(hwnd, windows):
                        if win32gui.IsWindowVisible(hwnd):
                            window_title = win32gui.GetWindowText(hwnd)
                            if "chrome" in window_title.lower() or "google chrome" in window_title.lower():
                                windows.append((hwnd, window_title))
                    
                    windows = []
                    win32gui.EnumWindows(enum_handler, windows)
                    
                    if windows:
                        # Get the first Chrome window
                        hwnd, title = windows[0]
                        logging.info(f"Found Chrome window: {title}")
                        # Bring to front
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        logging.info("Chrome window brought to front.")
                except Exception as e:
                    logging.warning(f"Could not bring Chrome window to front using Windows API: {e}")
                
                logging.info("Browser window maximized.")
            except Exception as e:
                logging.warning(f"Could not maximize window: {e}")

        env_url = {
            "prod": "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/",
            "staging": "https://tcfabstaging.lexisnexis.com/shared/InventoryInvoicing/"
        }.get(config.get("environment", "prod"))

        logging.info(f"Navigating to: {env_url}")
        try:
            _navigate_with_retries(driver, env_url)
        except Exception as e:
            logging.error(f"Failed to navigate to {env_url}: {e}")
            logging.error(f"Navigation error traceback: {traceback.format_exc()}")
            raise

        logging.info("Creating router instance...")
        router = create_router(driver, show_error=show_error,
                               set_status=set_status) if create_router else CaseLawRouter(driver, show_error=show_error,
                                                                                          set_status=set_status)
        logging.info("Router instance created. Clicking Search Inventory...")
        if not _open_search_inventory_with_recovery(router, driver, env_url, "single router"):
            raise RuntimeError("Router could not open Search Inventory before processing rows.")
        logging.info("Search Inventory clicked. Starting to process rows...")

        processed_count = 0

        counsel_progress = {"current": 0, "total": 0}
        main_progress = {"current": 0, "total": 0}

        def update_batch_progress(batch, current, total):
            if update_progress:
                update_progress(batch, current, total)

        counsel_df = pd.DataFrame()
        main_df = pd.DataFrame()

        set_status("MSPB Batch Started" if mspb_mode else "ITC Batch Started" if itc_mode else "IRSPLR Batch Started" if irsplr_mode else "OHTAX0 Batch Started" if ohtax0_mode else "MNSUTB Batch Started" if mnsutb_mode else "Counsel Batch Started")
        counsel_df, main_df = router.process_rows(
            df_filtered,
            latest_excel,
            update_batch_progress,
            dar_mode,
            wc_mode,
            mspb_mode=mspb_mode,
            itc_mode=itc_mode,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
        )

        rerun_summary = finalize_rerun_ready_statuses(
            df=df,
            latest_excel=None,
            mode=current_mode,
            scope_df=df_filtered,
            flush=False,
        )
        result_counts = _count_results_for_rows(
            df_filtered,
            mspb_mode,
            dar_mode,
            wc_mode,
            itc_mode=itc_mode,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
            current_run_only=True,
        )
        counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout = result_counts

        user_name = clean_display_name(get_full_username())

        if show_success:
            show_success(user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout)
        else:
            logging.warning("show_success is None, final success signal not emitted!")

        try:
            # Update Excel for all rows, using the merged status map
            merged_status_map = {idx: status_updates_buffer.get(idx, str(row["Status"])) for idx, row in df.iterrows()}
            flush_status_updates(
                latest_excel,
                merged_status_map,
                mspb_metadata_buffer if mspb_metadata_buffer else None,
            )
            _write_error_report_if_needed()
            notify_for_critical_statuses(
                df_filtered,
                latest_excel=latest_excel,
                mode=current_mode,
                config=config,
                context="Single router run",
                run_status_summary=rerun_summary,
            )
            notify_successful_run(
                latest_excel=latest_excel,
                mode=current_mode,
                result_counts={
                    "counsel_success": counsel_success,
                    "main_success": main_success,
                    "counsel_already": counsel_already,
                    "main_already": main_already,
                    "counsel_timeout": counsel_timeout,
                    "main_timeout": main_timeout,
                },
                context="Single router run completed.",
                config=config,
            )
            if driver:
                driver.quit()
        except Exception as e:
            logging.warning(f"Failed to close browser")

        return counsel_df, main_df

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Unexpected error during Run: {e}")
        logging.error(f"Full traceback: {tb}")
        current_mode = locals().get("current_mode", "mspb" if mspb_mode else "itc" if itc_mode else "irsplr" if irsplr_mode else "ohtax0" if ohtax0_mode else "mnsutb" if mnsutb_mode else "dar" if dar_mode else "smd")
        rerun_summary = finalize_rerun_ready_statuses(
            df=df,
            latest_excel=latest_excel,
            mode=current_mode,
            scope_df=locals().get("df_filtered"),
            flush=True,
        )
        notify_critical_error(
            "Unexpected automation crash",
            e,
            latest_excel=latest_excel,
            mode=current_mode,
            traceback_text=tb,
            details={
                "Context": "Unexpected automation crash",
                "Rerun Status Summary": rerun_summary,
            },
            run_status_summary=rerun_summary,
            config=load_config(),
        )
        if show_error:
            show_error(f"Unexpected error: {str(e)}")
        try:
            driver.quit()
        except:
            pass

