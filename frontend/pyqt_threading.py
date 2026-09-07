"""
PyQt Threading Module

Contains threading classes for the SADM Auto-Router application.
"""

import logging
import traceback

from PyQt5.QtCore import QThread

from core.smducar import CaseLawRouter
from core.critical_error_notifier import notify_critical_error
from core.rerun_status import finalize_rerun_ready_statuses
from core.smducar_workflow import run_automation_workflow

class WorkerThread(QThread):
    def __init__(self, update_progress, set_status, show_success, show_error, total_count, latest_excel, df, dar_mode=False, wc_mode=False, mspb_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False, mosu00_mode=False):
        super().__init__()
        self.update_progress = update_progress
        self.set_status = set_status
        self.show_success = show_success
        self.show_error = show_error
        self.total_count = total_count
        self.latest_excel = latest_excel
        self.df = df
        self.dar_mode = dar_mode
        self.mspb_mode = mspb_mode
        self.itc_mode = itc_mode
        self.irsplr_mode = irsplr_mode
        self.ohtax0_mode = ohtax0_mode
        self.mnsutb_mode = mnsutb_mode
        self.mosu00_mode = mosu00_mode
        # wc_mode parameter kept for backward compatibility but no longer used
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        self.requestInterruption()
        logging.info("Automation stop requested")

    def run(self):
        try:
            # Ignore late UI callbacks after Reset has requested a stop.
            def update_progress_wrapper(batch, current, total):
                if not self._stop_requested:
                    self.update_progress(batch, current, total)

            def set_status_wrapper(text):
                if not self._stop_requested:
                    self.set_status(text)

            def show_success_wrapper(*args, **kwargs):
                if not self._stop_requested and self.show_success:
                    self.show_success(*args, **kwargs)

            def show_error_wrapper(*args, **kwargs):
                if not self._stop_requested and self.show_error:
                    self.show_error(*args, **kwargs)

            def create_router(driver, show_error, set_status):
                return CaseLawRouter(driver, show_error=show_error, set_status=set_status)

            run_automation_workflow(
                update_progress=update_progress_wrapper,
                set_status=set_status_wrapper,
                show_success=show_success_wrapper,
                show_error=show_error_wrapper,
                total_count=self.total_count,
                create_router=create_router,
                latest_excel=self.latest_excel,
                df=self.df,
                dar_mode=self.dar_mode,
                wc_mode=False,
                mspb_mode=self.mspb_mode,
                itc_mode=self.itc_mode,
                irsplr_mode=self.irsplr_mode,
                ohtax0_mode=self.ohtax0_mode,
                mnsutb_mode=self.mnsutb_mode,
                mosu00_mode=self.mosu00_mode,
            )
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"Error in worker thread: {e}")
            logging.error(f"Worker thread traceback: {tb}")
            mode = "mspb" if self.mspb_mode else "itc" if self.itc_mode else "irsplr" if self.irsplr_mode else "ohtax0" if self.ohtax0_mode else "mnsutb" if self.mnsutb_mode else "mosu00" if self.mosu00_mode else "dar" if self.dar_mode else "smd"
            rerun_summary = finalize_rerun_ready_statuses(
                df=self.df,
                latest_excel=self.latest_excel,
                mode=mode,
                flush=True,
            )
            notify_critical_error(
                "Worker thread crashed",
                e,
                latest_excel=self.latest_excel,
                mode=mode,
                traceback_text=tb,
                details={
                    "Context": "Worker thread crashed",
                    "Rerun Status Summary": rerun_summary,
                },
                run_status_summary=rerun_summary,
            )
            if self.show_error:
                self.show_error(str(e))


