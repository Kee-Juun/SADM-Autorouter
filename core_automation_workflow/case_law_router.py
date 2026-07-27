import logging
import time
import re
import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys

from core_automation import (
    status_updates_buffer, error_log_entries, is_counsel, 
    extract_docket_number, resolve_source_detail, get_related_counsel_lnis, filter_mapping_data
)


class CaseLawRouter:
    def __init__(self, driver, show_error=None, set_status=None):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 60)
        self.long_wait = WebDriverWait(self.driver, 600)
        self.show_error = show_error
        self.set_status = set_status

    def safe_fill_field(self, xpath, value, field_name="Field"):
        try:
            element = self.long_wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

            if not element.is_enabled() or element.get_attribute("readonly") == "true":
                logging.info(f"Skipped {field_name} because it's not interactable.")
                return

            current_val = element.get_attribute("value")
            if current_val and current_val.strip() == str(value).strip():
                logging.info(f"{field_name} already set correctly. Skipping.")
                return

            # Clear and fill in one go
            element.clear()
            element.send_keys(value)
            logging.info(f"{field_name} set to: {value}")

            # Handle any popup that might have appeared immediately
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text.strip()
                alert.accept()

                if "duplicate document" in alert_text.lower():
                    logging.info(f"Duplicate alert detected after {field_name}. Handling...")
                    self.handle_duplicate_lni_popup()
                    # If this was a comments field, retry the fill
                    if field_name == "Comments":
                        element.clear()
                        element.send_keys(value)
                        logging.info(f"Retried filling {field_name} after duplicate alert")
            except:
                pass  # No alert present, continue normally

        except Exception as e:
            logging.error(f"Error filling {field_name}")

    def check_session_validity(self):
        """Check if the current browser session is still valid"""
        try:
            # Try to get the current URL - this will fail if session is invalid
            current_url = self.driver.current_url
            return True
        except Exception as e:
            if "invalid session id" in str(e).lower():
                logging.warning("Invalid session detected. Session may have been closed.")
                return False
            return True

    def search_lni(self, lni_value):
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # Check session validity before attempting search
                if not self.check_session_validity():
                    logging.error("Invalid session detected. Cannot proceed with LNI search.")
                    return False
                
                logging.info(f"Search attempt {attempt + 1} for LNI: {lni_value}")

                # Wait for search field to be present and interactable
                search_field = self.long_wait.until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="documentLNISearch"]'))
                )

                # Clear any existing value
                search_field.clear()
                time.sleep(0.5)  # Small delay to ensure clear is complete

                # Input LNI value
                search_field.send_keys(str(lni_value))
                time.sleep(0.5)  # Small delay to ensure input is complete

                # Click search button
                search_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="search"]'))
                )
                search_button.click()

                # Wait for results
                if self.check_result_available():
                    logging.info(f"Successfully found results for LNI: {lni_value}")
                    return True
                else:
                    logging.warning(f"No results found for LNI: {lni_value}")
                    return False

            except Exception as e:
                error_msg = str(e)
                logging.error(f"Search attempt {attempt + 1} failed: {error_msg}")
                
                # Check if it's a session-related error
                if "invalid session id" in error_msg.lower():
                    logging.error("Session invalid. Cannot retry - browser connection lost.")
                    return False
                
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"All {max_retries} search attempts failed for LNI: {lni_value}")
                    return False

        return False

    def click_search_inventory(self):
        try:
            search_button = self.long_wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="menu"]/table/thead/tr/td[3]/h3/a')))
            search_button.click()
            logging.info("Clicked 'Search Inventory'.")
            return True
        except Exception as e:
            logging.error(f"Failed to click 'Search Inventory': {e}")
            return False

    def is_valid_lni(self, lni):
        pattern = r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-\d{5}-\d{2}$"
        return bool(re.match(pattern, lni))

    def check_result_available(self):
        try:
            self.long_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                                                            "td.searchColumn.ChangeMouseCursorToHand")))
            return True
        except Exception as e:
            logging.warning(f"No LNI result found")
            return False

    def validate_row(self, row, row_index, file_path):
        lni = str(row["LNI"]).strip()
        if not lni:
            status_updates_buffer[row_index] = "ERROR: LNI NOT FOUND"
            return None
        if not self.is_valid_lni(lni):
            status_updates_buffer[row_index] = "ERROR: INVALID LNI FORMAT"
            return None
        return lni

    def handle_lni_search(self, lni):
        self.search_lni(lni)
        if not self.check_result_available():
            return False
        self.click_matching_result()
        return True

    def click_matching_result(self):
        try:
            element = self.long_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "td.searchColumn.ChangeMouseCursorToHand")))
            
            # Try multiple methods to open in new tab
            main_tab = self.driver.current_window_handle
            before_handles = set(self.driver.window_handles)
            
            # Method 1: Try Ctrl+click
            try:
                ActionChains(self.driver).key_down(Keys.CONTROL).click(element).key_up(Keys.CONTROL).perform()
                # Wait for new tab with shorter timeout
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 1 failed. Switching to Method 2...")
            
            # Method 2: Try middle-click (simulate with JavaScript)
            try:
                self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {button: 1, bubbles: true}));", element)
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 2 failed. Switching to Method 3...")
            
            # Method 3: Try right-click and "Open in new tab"
            try:
                ActionChains(self.driver).context_click(element).perform()
                # Look for "Open in new tab" option
                open_new_tab_option = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Open in new tab') or contains(text(), 'Open link in new tab')]"))
                )
                open_new_tab_option.click()
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 3 failed. Switching to New Window Method...")
            
            # If all new tab methods fail, fall back to popup window
            logging.error("All new tab methods failed. Falling back to popup window logic.")
            element.click()
            logging.info("Clicked on matching LNI result (popup window fallback).")
            self._opened_tab = None
            self._main_tab = self.driver.current_window_handle
            
        except Exception as e:
            logging.error(f"Failed to click search result")
            if self.show_error:
                self.show_error(f"Failed to click search result")

    def attempt_open_modify(self, file_path=None, row_index=None, max_attempts=3):
        for attempt in range(1, max_attempts + 1):
            try:
                # Check session validity before attempting to find Modify button
                if not self.check_session_validity():
                    logging.error("Invalid session detected. Cannot proceed with Modify button click.")
                    return False
                
                logging.info(f"Attempt {attempt}/{max_attempts}: Waiting for Modify button...")
                modify_btn = WebDriverWait(self.driver, 120).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="modify"]'))
                )
                modify_btn.click()
                logging.info("Clicked Modify button.")

                # Immediately check for an alert after clicking.
                try:
                    alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                    alert_text = alert.text.strip()
                    alert.accept()
                    logging.info(f"Accepted alert: {alert_text}")

                    # If it's the 'ready to process' alert, we need to retry the click.
                    if "ready to process = [on]" in alert_text.lower():
                        logging.info("IRT Form is not yet ready. Waiting 5 seconds before retrying Modify click...")
                        time.sleep(5)
                        continue
                    # Handle duplicate document alert
                    if "duplicate document" in alert_text.lower():
                        self.handle_duplicate_lni_popup()
                        # After handling, the form is ready for editing
                        return True
                    # Handle DSAR duplicate alert
                    if "dsar" in alert_text.lower() and "duplicate" in alert_text.lower():
                        logging.info("DSAR duplicate alert detected. Checking for additional duplicate document alert...")
                        time.sleep(2)
                        try:
                            # Check for additional duplicate document alert
                            additional_alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                            additional_alert_text = additional_alert.text.strip()
                            additional_alert.accept()
                            logging.info(f"Accepted additional alert after DSAR: {additional_alert_text}")
                            
                            # If it's a duplicate document alert, handle it
                            if "duplicate document" in additional_alert_text.lower():
                                self.handle_duplicate_lni_popup()
                                return True
                        except TimeoutException:
                            logging.info("No additional alert found after DSAR duplicate alert.")
                except TimeoutException:
                    # No alert appeared, which is the successful case.
                    logging.info("No alert found. IRT Form is ready for editing.")
                    return True

            except Exception as e:
                error_msg = str(e)
                logging.warning(f"Attempt {attempt}/{max_attempts} to click Modify button failed: {error_msg}")
                
                # Check if it's a session-related error
                if "invalid session id" in error_msg.lower():
                    logging.error("Session invalid. Cannot retry - browser connection lost.")
                    return False
                
                time.sleep(2)

        # If all attempts fail
        logging.error(f"Failed to enter modify mode after {max_attempts} attempts.")
        if row_index is not None:
            status_updates_buffer[row_index] = "ERROR: MODIFY FAILED"
        return False

    def clear_and_fill_input(self, xpath, value):
        try:
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            except TimeoutException:
                logging.warning(f"Field {xpath} not found after 60s. Checking for alerts/overlays...")
                # Try to handle any alerts/overlays
                try:
                    self.handle_any_alert(timeout=3)
                except Exception as e:
                    logging.info(f"No alert handled or error in handle_any_alert: {e}")
                try:
                    self.handle_duplicate_overlay()
                except Exception as e:
                    logging.info(f"No duplicate overlay handled or error in handle_duplicate_overlay: {e}")
                # Try again after handling
                try:
                    field = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                except TimeoutException:
                    logging.warning(f"Field {xpath} still not found after handling alerts. Waiting up to 300s for slow network...")
                    long_wait = WebDriverWait(self.driver, 300)
                    try:
                        field = long_wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    except TimeoutException:
                        logging.error(f"Field {xpath} not found after an additional 300s. Giving up.")
                        raise
            if field.is_enabled() and field.get_attribute("readonly") != "true":
                field.clear()
                field.send_keys(value)
                logging.info(f"Field at {xpath} cleared and filled with: {value}")
            else:
                logging.info(f"Field at {xpath} is not interactable. Skipping.")
        except Exception as e:
            logging.error(f"Error clearing and filling field at {xpath}: {e}")

    @staticmethod
    def format_docket_number(_, file_name, dar_mode=False):
        # Use the extract_docket_number function for consistent docket extraction
        extracted_docket = extract_docket_number(file_name, dar_mode)
        if extracted_docket:
            return extracted_docket
        
        # Fallback to original SMD logic if extract_docket_number returns None
        file_name = re.sub(r"counsel-\d+", "counsel", str(file_name))
        file_name = re.sub(r'_\d{8}', '', file_name)
        docket = re.sub(r"LDC_SMD_|_PCQ|_E2E|counsel|\.pdf|\.docx|\.doc|\.html|\.htm|\.csv|\.txt", "", file_name)
        return re.sub(r"[a-z]$", "", docket)

    def get_decision_date_from_received(self):
        try:
            received_xpath = '//*[@id="receivedDateAndTime"]'
            field = self.driver.find_element(By.XPATH, received_xpath)

            # Wait up to 2 seconds for the field to have a value
            WebDriverWait(self.driver, 2).until(
                lambda d: d.find_element(By.XPATH, received_xpath).get_attribute("value").strip()
            )
            raw_text = self.driver.find_element(By.XPATH, received_xpath).get_attribute("value").strip()

            logging.info(f"Received date raw value: {raw_text}")

            # Extract and convert the date
            date_part = raw_text.split()[0]
            received_date = datetime.datetime.strptime(date_part, "%m-%d-%Y")
            decision_date = received_date - datetime.timedelta(days=1)
            return decision_date.strftime("%m-%d-%Y")

        except Exception as e:
            logging.error(f"Failed to get decision date")
            fallback_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%m-%d-%Y")
            logging.info(f"Fallback decision date used: {fallback_date}")
            return fallback_date

    def extract_decision_date_from_filename(self, file_name):
        """Extract decision date from filename if present"""
        try:
            # Look for date pattern in filename (MM-DD-YYYY or MM/DD/YYYY)
            date_pattern = r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})'
            match = re.search(date_pattern, str(file_name))
            if match:
                month, day, year = match.groups()
                return f"{int(month):02d}-{int(day):02d}-{year}"
        except Exception as e:
            logging.error(f"Error extracting decision date from filename: {e}")
        return None

    def prepare_common_fields(self, file_name, decision_date=None, dar_mode=False):
        formatted_docket = CaseLawRouter.format_docket_number(None, file_name, dar_mode)

        # If no decision_date is provided, fetch from received field (optional fallback)
        if not decision_date:
            decision_date = self.get_decision_date_from_received()

        # Fill fields only once
        self.safe_fill_field('//*[@id="numberOfPages"]', "1", "Number of Pages")
        self.safe_fill_field('//*[@id="docketNumber"]', formatted_docket, "Docket Number")
        self.safe_fill_field('//*[@id="decisionDate"]', decision_date, "Decision Date")

    def handle_any_alert(self, timeout=3):
        try:
            alert = WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
            alert_text = alert.text.strip()
            alert.accept()
            logging.info(f"Handled alert: {alert_text}")
            if "duplicate document" in alert_text.lower():
                self.handle_duplicate_overlay()
            return True
        except TimeoutException:
            return False

    def handle_duplicate_overlay(self):
        try:
            # Handle UI popup overlay only (not the alert box)
            process_radio = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "processDuplicate"))
            )
            process_radio.click()
            logging.info("Selected 'Process as a New Document' option.")

            continue_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[17]/div[3]/div/button[1]/span"))
            )
            continue_button.click()
            logging.info("Clicked Continue button in Duplicate LNI dialog.")

            WebDriverWait(self.driver, 10).until_not(
                EC.presence_of_element_located((By.CLASS_NAME, "ui-widget-overlay"))
            )
            logging.info("Overlay cleared. Safe to proceed.")
        except Exception as e:
            logging.error(f"Failed to handle duplicate overlay")

    def handle_duplicate_lni_popup(self):
        try:
            # Handle alert if present
            try:
                WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                alert = self.driver.switch_to.alert
                alert_text = alert.text.strip()
                alert.accept()
                logging.info(f"Accepted alert: {alert_text}")

                # If it's not a duplicate alert, return early
                if "duplicate document" not in alert_text.lower():
                    logging.info("Alert was not a duplicate alert. Continuing...")
                    return

            except TimeoutException:
                logging.info("No alert found when checking for duplicate popup.")

            # Handle overlay if present
            try:
                process_radio = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.ID, "processDuplicate"))
                )
                process_radio.click()
                logging.info("Selected 'Process as a New Document' option.")

                continue_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "/html/body/div[17]/div[3]/div/button[1]/span"))
                )
                continue_button.click()
                logging.info("Clicked Continue button in Duplicate LNI dialog.")

                WebDriverWait(self.driver, 10).until_not(
                    EC.presence_of_element_located((By.CLASS_NAME, "ui-widget-overlay"))
                )
                logging.info("Overlay cleared. Safe to proceed.")

            except TimeoutException:
                logging.info("No duplicate overlay found. Continuing...")

        except Exception as e:
            logging.error(f"Error in handle_duplicate_lni_popup: {e}")

    def safe_alert_accept(self):
        try:
            WebDriverWait(self.driver, 5).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            alert_text = alert.text.strip()
            alert.accept()
            logging.info(f"Accepted alert: {alert_text}")

            if "duplicate document" in alert_text.lower():
                logging.info("Duplicate alert detected. Handling duplicate popup dialog...")
                self.handle_duplicate_overlay()

            return alert_text
        except:
            return None

    def click_element(self, xpath, wait_time=None):
        """Generic method to click an element with optional custom wait time"""
        try:
            if wait_time is not None:
                wait = WebDriverWait(self.driver, wait_time)
            else:
                wait = self.wait
            
            element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            element.click()
            logging.info(f"Clicked element: {xpath}")
        except Exception as e:
            logging.error(f"Failed to click element {xpath}: {e}")
            raise

    def open_and_process_form(self, row, full_df, row_index, file_path, retry_count=0, dar_mode=False):
        # Store current tab state
        main_tab = getattr(self, '_main_tab', self.driver.current_window_handle)
        opened_tab = getattr(self, '_opened_tab', None)
        
        # Use attempt_open_modify for robust Modify button and alert handling
        found_modify = self.attempt_open_modify(row_index=row_index)
        
        if found_modify:
            # Proceed with usual workflow
            status = self.fill_irt_form(row, full_df, row_index, file_path, skip_ready_check=True, dar_mode=dar_mode)
            if status == "DONE":
                self.submit_irt_form(file_path, row_index)
                status_updates_buffer[row_index] = status
            
            # After successful processing, clean up tabs
            self._cleanup_tabs(opened_tab, main_tab)
            
        else:
            # Could not find Modify button - implement fresh start strategy
            logging.warning(f"Modify button not found on attempt {retry_count + 1}/3")
            
            # Immediately close IRT form tab and return to main tab
            self._cleanup_tabs(opened_tab, main_tab)
            
            if retry_count < 3:
                # Fresh start: Re-search LNI from the beginning
                logging.info(f"Fresh start: Re-searching LNI and opening form again. Attempt {retry_count + 1}/3")
                
                # Re-search the LNI to get a fresh page
                lni = str(row["LNI"]).strip()
                if self.handle_lni_search(lni):
                    # Recursive call with incremented retry count
                    self.open_and_process_form(row, full_df, row_index, file_path, retry_count=retry_count+1, dar_mode=dar_mode)
                else:
                    logging.error(f"Failed to re-search LNI on attempt {retry_count + 1}")
                    status_updates_buffer[row_index] = "ERROR: LNI RE-SEARCH FAILED"
            else:
                # All 3 attempts failed - log error and move on
                logging.error(f"All 3 attempts failed for row {row_index}. Moving on to next LNI.")
                status_updates_buffer[row_index] = "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS"
    
    def _cleanup_tabs(self, opened_tab, main_tab):
        """Helper method to clean up tabs and return to main tab"""
        try:
            handles = self.driver.window_handles
            
            # Close IRT form tab if it exists
            if opened_tab and opened_tab in handles:
                self.driver.switch_to.window(opened_tab)
                self.driver.close()
                logging.info("Closed IRT form tab.")
            
            # Return to main tab
            if main_tab and main_tab in handles:
                self.driver.switch_to.window(main_tab)
                logging.info("Returned to main tab.")
            elif len(handles) > 0:
                # Fallback: switch to first available tab
                self.driver.switch_to.window(handles[0])
                logging.info("Switched to first available tab.")
                
        except Exception as e:
            logging.error(f"Error during tab cleanup: {e}")
        
        # Reset tab tracking
        self._opened_tab = None
        self._main_tab = None

    def process_batch(self, df, full_df, file_path, update_progress, batch_type, dar_mode=False):
        self.safe_alert_accept()

        processed_rows = 0
        total_rows = len(df)

        # Emit 0/total progress at the start so UI shows batch start immediately
        if update_progress and batch_type in ["counsel", "main"]:
            update_progress(batch_type, 0, total_rows)

            batch_start_time = time.time()
            processed_count = 0
            total_duration = 0

        for full_index in df.index:
            row = df.loc[full_index]
            try:
                if str(row.get("Status", "")).strip().upper() == "ALREADY PROCESSED":
                    logging.info(f"Skipping already processed row {full_index + 2}.")
                    continue

                lni = self.validate_row(row, full_index, file_path)
                if not lni:
                    continue

                # Start timing for this LNI
                lni_start = time.time()

                if not self.handle_lni_search(lni):
                    status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                    continue

                self.open_and_process_form(row, full_df, full_index, file_path, dar_mode=dar_mode)

                # End timing
                lni_duration = time.time() - lni_start
                total_duration += lni_duration
                processed_count += 1

                logging.info(f"[LNI PROCESSING TIME] LNI {lni} processed in {lni_duration:.2f} seconds.")

            except Exception as e:
                logging.error(f"Error processing row {full_index + 2}")
                status_updates_buffer[full_index] = "ERROR"
                error_log_entries.append({
                    "Row": full_index + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR",
                    "Error Message": str(e)
                })
                try:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                except:
                    pass
            finally:
                # Always update progress, regardless of success or error
                processed_rows += 1
                if update_progress and batch_type in ["counsel", "main"]:
                    update_progress(batch_type, processed_rows, total_rows)

        # Final summary log: outside the loop
        if processed_count > 0:
            avg = total_duration / processed_count
            est_per_hour = int(3600 / avg)
            elapsed = time.time() - batch_start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            logging.info(f"[AVERAGE BATCH PROCESSING TIME - LNI/HOUR ESTIMATE] Processed {processed_count} {batch_type} LNIs in {mins}m {secs}s "
                        f"(Avg: {avg:.2f}s/LNI → Est. {est_per_hour} LNIs/hour)")
            
        return processed_count, total_duration

    def process_rows(self, full_df, file_path, update_progress, dar_mode=False):
        counsel_df, main_df = None, None
        try:
            self.full_df = full_df

            counsel_df, main_df = filter_mapping_data(full_df, dar_mode)

            logging.info("=== Starting Counsel Batch ===")
            counsel_count, counsel_duration = self.process_batch(counsel_df, full_df, file_path, update_progress, "counsel", dar_mode)

            if self.set_status:
                self.set_status("Counsel Batch Processed")

            try:
                while len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                logging.info("Cleaned up all leftover popup windows before Main Opinion batch.")
            except Exception as e:
                logging.warning(f"Failed to clean up extra windows")

            logging.info("=== Starting Main Opinion Batch ===")
            if self.set_status:
                self.set_status("Main Opinion Batch Started")
            main_count, main_duration = self.process_batch(main_df, full_df, file_path, update_progress, "main", dar_mode)
            if self.set_status:
                self.set_status("Main Opinion Batch Processed")

            total_count = counsel_count + main_count
            total_time = counsel_duration + main_duration

            if total_count > 0:
                overall_avg = total_time / total_count
                overall_est_per_hour = int(3600 / overall_avg)
                total_mins = int(total_time // 60)
                total_secs = int(total_time % 60)

                counsel_mins = int(counsel_duration // 60)
                counsel_secs = int(counsel_duration % 60)

                main_mins = int(main_duration // 60)
                main_secs = int(main_duration % 60)

                logging.info("[TOTAL AVERAGE PROCESSING TIME SUMMARY - LNI/HOUR ESTIMATE] TOTAL: %d LNIs processed in %dm %ds", total_count, total_mins, total_secs)
                logging.info("    - Counsel: %d LNIs in %dm %ds", counsel_count, counsel_mins, counsel_secs)
                logging.info("    - Main Opinion: %d LNIs in %dm %ds", main_count, main_mins, main_secs)
                logging.info("    - Overall Avg: %.1fs/LNI → Est. %d LNIs/hour", overall_avg, overall_est_per_hour)

            self._last_success_log_time = datetime.datetime.now()
            self._success_message_dismissed = False

            logging.info("Documents Auto-Routed Successfully!")

            if self.set_status:
                self.set_status("Success!")

            if error_log_entries:
                error_df = pd.DataFrame(error_log_entries)
                timestamp = datetime.datetime.now().strftime("%I-%M-%S_%p").lstrip("0")
                error_folder = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Error Reports"
                error_folder.mkdir(parents=True, exist_ok=True)
                error_path = error_folder / f"Error Report - {timestamp}.xlsx"
                error_df.to_excel(error_path, index=False)
                logging.info(f"Error report saved to {error_path}")

            return counsel_df, main_df

        except Exception as e:
            msg = str(e)
            # List of phrases that indicate a normal, non-error outcome
            normal_outcomes = [
                "already processed",
                "No rows to process",
                "No valid data",
                "All documents processed successfully",
                "Some documents processed successfully",
                "All documents were already processed",
                "No new routing needed"
            ]
            if any(phrase in msg for phrase in normal_outcomes):
                logging.info(f"Row processing ended normally: {msg}")
            else:
                logging.error(f"Failed during row processing: {msg}", exc_info=True)
            # Ensure it returns something iterable on failure to prevent UI crash
            return pd.DataFrame(), pd.DataFrame()

    # Import form filling methods
    from form_filling import (
        handle_counsel_fields, handle_main_opinion_fields, handle_related_ln_is,
        fill_irt_form, handle_routing_and_save, submit_irt_form,
        handle_unexpected_alert, is_ready_to_process_enabled,
        click_ready_checkbox_and_check_overlay, open_lni_in_irt_tab
    )
