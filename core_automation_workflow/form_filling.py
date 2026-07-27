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
from pathlib import Path
import pandas as pd

from core_automation import (
    status_updates_buffer, error_log_entries, is_counsel, 
    extract_docket_number, resolve_source_detail, get_related_counsel_lnis
)


def handle_counsel_fields(self, row, dar_mode=False):
    comments_xpath = '//*[@id="comments"]'
    additional_comments = str(row.get("Comments", "")).strip()

    try:
        comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, comments_xpath)))
        existing_text = comments_field.get_attribute("value").strip()

        # Build the complete comment text
        comment_parts = []
        
        # Find and add the Main Opinion LNI automatically
        file_name = str(row.get("FileName", "")).strip()
        if file_name:
            docket = CaseLawRouter.format_docket_number(None, file_name, dar_mode)
            if docket:
                # Look for the main opinion LNI in the full dataframe
                main_lnis = [str(r["LNI"]).strip() for _, r in self.full_df.iterrows()
                            if not is_counsel(str(r["FileName"])) and
                            CaseLawRouter.format_docket_number(None, r["FileName"], dar_mode) == docket]

                attached_lnis = []
                for lni in main_lnis:
                    if lni and lni not in existing_text:
                        comment_parts.append(lni)
                        attached_lnis.append(lni)

                if attached_lnis:
                    logging.info(f"Auto-attached {len(attached_lnis)} Main Opinion LNI(s) to comments: {attached_lnis}")
                elif any(lni in existing_text for lni in main_lnis):
                    logging.info("Auto-found Main LNI already present in comments. Skipping.")
                else:
                    logging.warning(f"Could not auto-find Main Opinion LNI for counsel docket: {docket}")
            else:
                logging.warning(f"Could not extract docket number from counsel filename: {file_name}")
        else:
            logging.warning(f"Could not get filename for counsel row")
        
        # Add additional comments if available
        if additional_comments and additional_comments.lower() != "nan":
            comment_parts.append(additional_comments)
            logging.info(f"Adding additional comments to counsel: {additional_comments}")

        # If no new content to add, return early
        if not comment_parts:
            logging.info("No new comments to add for counsel row.")
            return

        # Prepare the new text
        if existing_text:
            if existing_text.endswith('.'):
                existing_text = existing_text[:-1].strip()
            updated_text = f"{existing_text}; {'; '.join(comment_parts)}"
        else:
            updated_text = '; '.join(comment_parts)

        # Clear and fill with retry capability
        max_retries = 2
        for attempt in range(max_retries):
            try:
                comments_field.clear()
                comments_field.send_keys(updated_text)
                logging.info(f"Updated comments field for counsel: {updated_text}")

                # Check for any popup that might have appeared immediately
                try:
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text.strip()
                    alert.accept()

                    if "duplicate document" in alert_text.lower():
                        logging.info("Duplicate alert detected during comment update. Processing...")
                        self.handle_duplicate_lni_popup()
                        # Clear and retry the comment fill
                        comments_field.clear()
                        comments_field.send_keys(updated_text)
                        logging.info("Retried filling comments after duplicate alert")
                except:
                    pass  # No alert present, continue normally

                break  # Successfully filled, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Failed to update comments on attempt {attempt + 1}, retrying...")
                    time.sleep(1)
                else:
                    logging.error(f"Failed to update comments after {max_retries} attempts")

    except Exception as e:
        logging.error(f"Error handling counsel comments field")


def handle_main_opinion_fields(self, row, full_df, row_index, file_path, dar_mode=False):
    case_name_xpath = '//*[@id="caseName"]'
    try:
        field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
        if not field.get_attribute("value").strip():
            self.clear_and_fill_input(case_name_xpath, "RE")
    except Exception as e:
        logging.error(f"Error setting case name")

    # Move Source Detail handling BEFORE clicking 'related'
    source_detail = str(row.get("SourceDetail", "")).strip()
    if source_detail and source_detail.lower() != "nan":
        try:
            resolved_source_detail = resolve_source_detail(source_detail)
            if resolved_source_detail:
                source_detail_dropdown = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="sourceDetails"]'))
                )
                try:
                    source_detail_dropdown.click()
                    logging.info("Source Detail dropdown clicked successfully.")

                    # Duplicate alert check
                    try:
                        WebDriverWait(self.driver, 2).until(EC.alert_is_present())
                        alert = self.driver.switch_to.alert
                        alert_text = alert.text.strip()
                        alert.accept()
                        logging.info(f"Handled alert after dropdown click: {alert_text}")
                        if "duplicate document" in alert_text.lower():
                            self.handle_duplicate_lni_popup()
                    except TimeoutException:
                        pass
                except Exception as e:
                    logging.error(f"Source Detail dropdown is not clickable")
                    return

                # Try selecting the dropdown value
                try:
                    select = Select(source_detail_dropdown)
                    select.select_by_visible_text(resolved_source_detail)
                    logging.info(f"Selected Source Detail: {resolved_source_detail}")
                except UnexpectedAlertPresentException as e:
                    logging.warning(f"Unexpected alert during Source Detail selection")
                    try:
                        alert = self.driver.switch_to.alert
                        alert_text = alert.text.strip()
                        alert.accept()
                        logging.info(f"Handled alert: {alert_text}")
                        if "duplicate document" in alert_text.lower():
                            self.handle_duplicate_lni_popup()
                            # Re-click 'related' again if needed
                            try:
                                related_checkbox = self.driver.find_element(By.XPATH, '//*[@id="related"]')
                                if not related_checkbox.is_selected():
                                    related_checkbox.click()
                                    logging.info("Re-clicked the Related checkbox after alert reset.")
                            except Exception as click_err:
                                logging.warning(f"Failed to re-click Related checkbox: {click_err}")
                    except Exception as alert_err:
                        logging.warning(f"Failed to handle alert gracefully: {alert_err}")

                    # Retry selection
                    try:
                        select = Select(source_detail_dropdown)
                        select.select_by_visible_text(resolved_source_detail)
                        logging.info(f"Retried and selected Source Detail: {resolved_source_detail}")
                    except Exception as retry_err:
                        logging.error(f"Retry failed after alert: {retry_err}")
                except Exception as e:
                    logging.error(f"Error selecting Source Detail value '{resolved_source_detail}'")
            else:
                logging.warning(f"Invalid Source Detail input: {source_detail}")
        except Exception as e:
            logging.error(f"Error finding Source Detail dropdown")

    # Now click the Related checkbox AFTER Source Detail
    try:
        self.click_element('//*[@id="related"]', wait_time=0)
    except Exception as e:
        logging.error(f"Error ticking 'related' checkbox")

    # First handle the related and recycled counsel LNIs
    main_docket = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode)
    related_attached = self.handle_related_ln_is(row, full_df, row_index=row_index, file_path=file_path, dar_mode=dar_mode)
    if not related_attached:
        logging.error(f"Skipping main opinion for docket {main_docket} because no related LNI could be attached.")
        status_updates_buffer[row_index] = "Missing Counsel Information"
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
        return "Missing Counsel Information"

    # Check if both Comments and Route are not interactable
    try:
        comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
        route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

        if not comments_field.is_enabled() and not route_element.is_enabled():
            logging.error("Both Comments and Route dropdown are non-interactable. Skipping Main Opinion.")
            status_updates_buffer[row_index] = "Non-interactable IRT Form"
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return "Non-interactable IRT Form"

    except Exception as e:
        logging.error(f"Error checking Comments/Route interactability")
        status_updates_buffer[row_index] = "Non-interactable IRT Form"
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
        return "Non-interactable IRT Form"

    # Then handle additional comments if they exist
    additional_comments = str(row.get("Comments", "")).strip()
    if additional_comments and additional_comments.lower() != "nan":
        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
            existing_text = comments_field.get_attribute("value").strip()

            # Prepare the new text
            if existing_text:
                if existing_text.endswith('.'):
                    existing_text = existing_text[:-1].strip()
                updated_text = f"{existing_text}; {additional_comments}"
            else:
                updated_text = additional_comments

            # Clear and fill with retry capability
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    comments_field.clear()
                    comments_field.send_keys(updated_text)
                    logging.info(f"Updated comments field with additional comments: {updated_text}")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"Failed to update comments on attempt {attempt + 1}, retrying...")
                        time.sleep(1)
                    else:
                        logging.error(f"Failed to update comments after {max_retries} attempts")

        except Exception as e:
            logging.error(f"Error handling additional comments")


def handle_related_ln_is(self, row, full_df, row_index, file_path, dar_mode=False):
    """Handle related LNIs for main opinion documents"""
    try:
        main_docket = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode)
        recycled_lni = str(row.get("Recycled Counsel LNI", "")).strip()
        
        # Get related counsel LNIs
        related_lnis = get_related_counsel_lnis(main_docket, full_df, recycled_lni, dar_mode)
        
        if not related_lnis:
            logging.warning(f"No related counsel LNIs found for docket {main_docket}")
            return False
        
        # Fill the related LNIs field
        related_lnis_text = "; ".join(related_lnis)
        self.safe_fill_field('//*[@id="relatedLNIs"]', related_lnis_text, "Related LNIs")
        
        logging.info(f"Successfully attached {len(related_lnis)} related counsel LNI(s) for docket {main_docket}")
        return True
        
    except Exception as e:
        logging.error(f"Error handling related LNIs: {e}")
        return False


def fill_irt_form(self, row, full_df, row_index, file_path, skip_ready_check=False, dar_mode=False):
    try:
        file_name = str(row["FileName"]).strip()
        is_counsel_file = is_counsel(file_name)
        lni = str(row["LNI"]).strip()

        # Determine decision date with clear precedence:
        # 1) Explicit Decision Date from Mapping Data sheet (column K)
        # 2) Date derived from Received Date field
        # 3) Date inferred from filename (only if no manual decision date)
        manual_decision_raw = row.get("Decision Date")
        decision_date = None

        # 1) Manual Decision Date from mapping sheet (prime source)
        if manual_decision_raw is not None and str(manual_decision_raw).strip().lower() != "nan":
            try:
                if isinstance(manual_decision_raw, (datetime.date, datetime.datetime)):
                    decision_date = manual_decision_raw.strftime("%m-%d-%Y")
                else:
                    decision_date = str(manual_decision_raw).strip()
                logging.info(f"Using manual Decision Date from mapping sheet: {decision_date}")
            except Exception as e:
                logging.error(f"Error normalizing manual Decision Date '{manual_decision_raw}': {e}")

        # 2) Fallback: derive from Received Date / IRT Received field
        if not decision_date:
            decision_date = self.get_decision_date_from_received()
            if decision_date:
                logging.info(f"Using Decision Date derived from Received Date: {decision_date}")

        # Populate common fields with the chosen decision date (if any)
        self.prepare_common_fields(file_name, decision_date, dar_mode)
        self.handle_any_alert()

        # 3) Additional special logic: only use filename-based Decision Date
        #    when there is NO manual Decision Date on the mapping sheet
        if manual_decision_raw is None or str(manual_decision_raw).strip().lower() == "nan" or str(manual_decision_raw).strip() == "":
            special_decision_date = self.extract_decision_date_from_filename(file_name)
            if special_decision_date:
                try:
                    date_field = self.driver.find_element(By.XPATH, '//*[@id="decisionDate"]')
                    if date_field.is_enabled() and date_field.get_attribute("readonly") != "true":
                        date_field.clear()
                        date_field.send_keys(special_decision_date)
                        logging.info(f"Decision Date set from filename: {special_decision_date}")
                        self.handle_any_alert()
                    else:
                        logging.info("Decision Date field is not interactable. Skipping filename override.")
                except Exception as e:
                    logging.error("Error setting Decision Date from filename")
                    self.handle_any_alert()

        max_attempts = 3 if is_counsel_file else 1
        attempts = 0

        while attempts < max_attempts:
            try:
                if is_counsel_file:
                    handle_counsel_fields(self, row, dar_mode)
                else:
                    handle_main_opinion_fields(self, row, full_df, row_index, file_path, dar_mode)

                self.handle_any_alert()

                # Check Comments and Route fields
                comments_xpath = '//*[@id="comments"]'
                route_xpath = '//*[@id="route"]'
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, comments_xpath)))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, route_xpath)))

                comments_enabled = comments_field.is_enabled()
                route_enabled = route_field.is_enabled()

                # If route is disabled but comments is fine → mark as already processed
                if not route_enabled and comments_enabled:
                    logging.info("Route dropdown is disabled — document already processed. Skipping Save & flagging as ALREADY PROCESSED.")
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                # If both comments and route are disabled → retry (or skip if main)
                if not comments_enabled and not route_enabled:
                    raise Exception("Comments AND Route are both non-interactable")

                break  # Both fields are fine, proceed

            except Exception as e:
                attempts += 1
                logging.warning(f"Attempt {attempts}: Non-interactable IRT form")
                if attempts >= max_attempts:
                    label = "Non-interactable IRT Form"
                    logging.error(f"{label}. Max attempts reached.")
                    if row_index is not None:
                        status_updates_buffer[row_index] = label.upper()
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return label.upper()
                else:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    self.open_lni_in_irt_tab(row)
                    continue

        # Always select the correct route BEFORE clicking Ready to Process
        try:
            route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
            route_element.click()
            self.handle_any_alert()
            dropdown = Select(route_element)
            route_label = "Archive" if is_counsel_file else "Outside Conversion"
            dropdown.select_by_visible_text(route_label)
            self.handle_any_alert()
            logging.info(f"Selected route: {route_label}")
            self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
            self.handle_any_alert()
        except Exception as e:
            logging.error(f"Failed to select route before Ready to Process")
            status_updates_buffer[row_index] = "ROUTE ERROR"
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return "ROUTE ERROR"

        # Proceed to Ready to Process
        overlay_appeared = self.click_ready_checkbox_and_check_overlay(is_counsel_file)
        self.handle_any_alert()
        if overlay_appeared == "ROUTE_ERROR":
            logging.info("Marking as ROUTE ERROR due to route alert after Ready to Process.")
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return "ROUTE ERROR"
        if overlay_appeared == "ALERT_HANDLED":
            logging.info("Alert was handled after Ready to Process, but no overlay appeared. Not flagging as already processed. Returning ALERT_HANDLED.")
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return "ALERT_HANDLED"

        return self.handle_routing_and_save(is_counsel_file, row_index, skip_route_and_ready=True)

    except Exception as e:
        logging.error(f"Error in fill_irt_form()")
        if row_index is not None:
            status_updates_buffer[row_index] = "ERROR"
        return "ERROR"


def handle_routing_and_save(self, is_counsel, row_index, skip_route_and_ready=False):
    save_attempts = 3
    for attempt in range(save_attempts):
        try:
            # Only select route and click Ready to Process if not already done in fill_irt_form
            if not skip_route_and_ready:
                route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                self.driver.execute_script("arguments[0].scrollIntoView(true);", route_element)
                self.handle_any_alert(timeout=2)
                try:
                    try:
                        route_element.click()
                        dropdown = Select(route_element)
                        route_label = "Archive" if is_counsel else "Outside Conversion"
                        dropdown.select_by_visible_text(route_label)
                    except UnexpectedAlertPresentException:
                        self.handle_any_alert()
                        route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                        route_element.click()
                        dropdown = Select(route_element)
                        route_label = "Archive" if is_counsel else "Outside Conversion"
                        dropdown.select_by_visible_text(route_label)
                except Exception as e:
                    logging.warning(f"Exception during route selection. Attempting to handle popups/overlays and retry.")
                    self.handle_unexpected_alert()
                    self.handle_duplicate_overlay()
                    try:
                        self.handle_any_alert()
                        route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                        route_element.click()
                        dropdown = Select(route_element)
                        route_label = "Archive" if is_counsel else "Outside Conversion"
                        dropdown.select_by_visible_text(route_label)
                    except Exception as e2:
                        logging.error(f"Route selection failed after handling popups/overlays: {e2}")
                        return "ROUTE DROPDOWN ERROR"
                self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                logging.info(f"Selected route: {route_label}")
                self.handle_any_alert(timeout=2)
                self.click_ready_checkbox_and_check_overlay(is_counsel)
                self.handle_any_alert(timeout=2)
            
            # Try to save
            try:
                self.click_element('//*[@id="add"]')
                logging.info("Clicked Save button.")
                # Check for alert after save
                try:
                    WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text.strip()
                    alert.accept()
                    logging.info(f"Accepted alert: {alert_text}")
                    if "route = [arc] vendorcode = [arc] workflow = [] is not a valid routing combo" in alert_text.lower():
                        logging.warning(f"Invalid routing combo alert after save (attempt {attempt+1}). Closing form and retrying.")
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        if attempt < save_attempts - 1:
                            self.attempt_open_modify(row_index=row_index)
                            continue  # Retry
                        else:
                            logging.error(f"Failed to save LNI after {save_attempts} attempts due to invalid routing combo.")
                            if row_index is not None:
                                status_updates_buffer[row_index] = "INVALID ROUTING COMBO"
                            return "INVALID ROUTING COMBO"
                except TimeoutException:
                    pass  # No alert after save
                return "DONE"
            except Exception as e:
                logging.info("Save failed, assuming form already processed. Closing window.")
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"
        except Exception as e:
            if self.handle_unexpected_alert():
                logging.info("Continuing after handling an unexpected alert during routing.")
            else:
                logging.error(f"Route selection failed")
            return "ROUTE DROPDOWN ERROR"
    
    # If we get here, all attempts failed
    logging.error(f"Failed to save LNI after {save_attempts} attempts due to invalid routing combo.")
    if row_index is not None:
        status_updates_buffer[row_index] = "INVALID ROUTING COMBO"
    return "INVALID ROUTING COMBO"


def submit_irt_form(self, file_path, row_index):
    try:
        self.safe_alert_accept()
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
        logging.info("IRT Form window closed after submission.")
    except Exception as e:
        logging.error(f"Unhandled error in submit_irt_form()")


def handle_unexpected_alert(self):
    """Handles unexpected alerts, especially for duplicate documents."""
    try:
        alert = WebDriverWait(self.driver, 3).until(EC.alert_is_present())
        alert_text = alert.text
        logging.warning(f"Caught unexpected alert: '{alert_text}'")
        alert.accept()
        if "duplicate document" in alert_text.lower():
            logging.info("Handling duplicate document overlay after unexpected alert.")
            self.handle_duplicate_overlay()
            return True  # Indicates a duplicate was handled
    except TimeoutException:
        return False  # No alert was present
    except Exception as e:
        logging.error(f"Error in handle_unexpected_alert")
        return False
    return False


def is_ready_to_process_enabled(self):
    """Checks if the 'Ready to Process' checkbox is enabled and clickable."""
    try:
        checkbox = WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="readyToProcess"]'))
        )
        return checkbox.is_enabled()
    except TimeoutException:
        logging.error("Could not find the 'Ready to Process' checkbox.")
        return False
    except Exception as e:
        logging.error(f"Error checking 'Ready to Process' checkbox state")
        return False


def click_ready_checkbox_and_check_overlay(self, is_counsel_file):
    """Click the Ready to Process checkbox and handle any overlays that appear"""
    try:
        # Click the Ready to Process checkbox
        ready_checkbox = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="readyToProcess"]'))
        )
        ready_checkbox.click()
        logging.info("Clicked 'Ready to Process' checkbox.")

        # Check for any alert that might appear
        try:
            alert = WebDriverWait(self.driver, 3).until(EC.alert_is_present())
            alert_text = alert.text.strip()
            alert.accept()
            logging.info(f"Accepted alert after Ready to Process: {alert_text}")

            # Check if it's a route-related alert
            if "route" in alert_text.lower() and "error" in alert_text.lower():
                logging.warning("Route error detected after Ready to Process.")
                return "ROUTE_ERROR"

            # Check if it's a duplicate document alert
            if "duplicate document" in alert_text.lower():
                logging.info("Duplicate document alert detected after Ready to Process.")
                self.handle_duplicate_lni_popup()
                return "DUPLICATE_HANDLED"

            # For any other alert, just log it
            logging.info("Alert handled after Ready to Process.")
            return "ALERT_HANDLED"

        except TimeoutException:
            # No alert appeared, which is normal
            logging.info("No alert appeared after Ready to Process. Continuing normally.")
            return "SUCCESS"

    except Exception as e:
        logging.error(f"Error clicking Ready to Process checkbox: {e}")
        return "ERROR"


def open_lni_in_irt_tab(self, row):
    """Re-open LNI in IRT tab for retry scenarios"""
    try:
        lni = str(row["LNI"]).strip()
        if self.handle_lni_search(lni):
            logging.info(f"Successfully re-opened LNI {lni} in IRT tab for retry.")
        else:
            logging.error(f"Failed to re-open LNI {lni} in IRT tab for retry.")
    except Exception as e:
        logging.error(f"Error re-opening LNI in IRT tab: {e}")
