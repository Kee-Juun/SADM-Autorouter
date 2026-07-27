import logging
import time
import datetime
from pathlib import Path
import pandas as pd
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.chrome.options import Options

from core_automation import (
    setup_logging, create_folders, generate_excel, open_excel_file,
    get_latest_excel_file, read_mapping_data, load_config, flush_status_updates,
    clean_display_name, get_full_username, filter_mapping_data
)
from case_law_router import CaseLawRouter


def run_automation_workflow(update_progress=None, set_status=None, show_success=None, show_error=None, total_count=1,
                            create_router=None, latest_excel=None, df=None, dar_mode=False):
    """
    Main automation workflow function that orchestrates the entire automation process.
    
    Args:
        update_progress: Callback function to update progress
        set_status: Callback function to set status
        show_success: Callback function to show success message
        show_error: Callback function to show error message
        total_count: Total number of items to process
        create_router: Function to create router instance
        latest_excel: Path to the latest Excel file
        df: DataFrame containing the data to process
        dar_mode: Whether to run in DAR mode
    
    Returns:
        tuple: (counsel_df, main_df) - DataFrames for counsel and main opinion batches
    """
    # Clear the buffer at the start of each run
    from core_automation import status_updates_buffer, error_log_entries
    status_updates_buffer.clear()
    error_log_entries.clear()

    try:
        # Use provided latest_excel and df, do not reload
        if latest_excel is None or df is None:
            logging.error("latest_excel and df must be provided by the caller.")
            return None, None
        if df.empty:
            logging.error("Excel data is empty or invalid.")
            return None, None

        # Count already processed rows before filtering
        already_processed_df = df[df["Status"].astype(str).str.strip().str.upper() == "ALREADY PROCESSED"]
        initial_counsel_already = already_processed_df["FileName"].apply(lambda x: is_counsel(x, dar_mode)).sum()
        initial_main_already = len(already_processed_df) - initial_counsel_already

        # Filter out already processed rows for the current run
        df_filtered = df[~df["Status"].astype(str).str.strip().str.upper().eq("ALREADY PROCESSED")]

        config = load_config()
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        if config.get("headless", False):
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

        service = ChromeService(ChromeDriverManager().install())
        driver = ChromeWebDriver(service=service, options=chrome_options)

        env_url = {
            "prod": "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/",
            "staging": "https://tcfabstaging.lexisnexis.com/shared/InventoryInvoicing/"
        }.get(config.get("environment", "prod"))

        driver.get(env_url)
        logging.info(f"Navigated to: {env_url}")

        router = create_router(driver, show_error=show_error,
                               set_status=set_status) if create_router else CaseLawRouter(driver, show_error=show_error,
                                                                                           set_status=set_status)
        if not router.click_search_inventory():
            logging.info("Search Inventory did not open on first attempt; refreshing the Inventory page and trying again.")
            driver.get(env_url)
            time.sleep(2)
            if not router.click_search_inventory():
                raise RuntimeError("Router could not open Search Inventory before processing rows.")

        processed_count = 0

        counsel_progress = {"current": 0, "total": 0}
        main_progress = {"current": 0, "total": 0}

        def update_batch_progress(batch, current, total):
            if update_progress:
                update_progress(batch, current, total)

        counsel_df = pd.DataFrame()
        main_df = pd.DataFrame()

        set_status("Counsel Batch Started")
        counsel_df, main_df = router.process_rows(df_filtered, latest_excel, update_batch_progress, dar_mode)

        # Calculate final stats for Counsel and Main batches
        success_statuses = ["DONE"]
        error_keywords = ["ERROR"]

        def classify_status(status):
            if pd.isna(status):
                return "ignored"
            status = str(status).strip().upper()
            if any(err in status for err in error_keywords):
                return "error"
            elif status in success_statuses:
                return "success"
            elif "ALREADY PROCESSED" in status:
                return "already"
            return "ignored"

        # Count statuses for all rows (not just filtered)
        counsel_success = 0
        main_success = 0
        counsel_already = 0
        main_already = 0
        counsel_timeout = 0
        main_timeout = 0
        for idx, row in df.iterrows():
            file_name = row["FileName"]
            is_counsel_file = is_counsel(file_name, dar_mode)
            # Use the latest status from the buffer if present, else the original
            status = status_updates_buffer.get(idx, str(row["Status"]))
            if status == "DONE":
                if is_counsel_file:
                    counsel_success += 1
                else:
                    main_success += 1
            elif status == "ALREADY PROCESSED":
                if is_counsel_file:
                    counsel_already += 1
                else:
                    main_already += 1
            elif status == "RELATED LNI TIMEOUT":
                if is_counsel_file:
                    counsel_timeout += 1
                else:
                    main_timeout += 1

        user_name = clean_display_name(get_full_username())

        if show_success:
            show_success(user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout)
        else:
            logging.warning("show_success is None, final success signal not emitted!")

        try:
            # Update Excel for all rows, using the merged status map
            merged_status_map = {idx: status_updates_buffer.get(idx, str(row["Status"])) for idx, row in df.iterrows()}
            flush_status_updates(latest_excel, merged_status_map)
            if driver:
                driver.quit()
        except Exception as e:
            logging.warning(f"Failed to close browser")

        return counsel_df, main_df

    except Exception as e:
        logging.error(f"Unexpected error during Run")
        if show_error:
            show_error(str(e))
        try:
            driver.quit()
        except:
            pass
        return None, None


def create_excel_and_wait_for_input():
    """
    Create Excel file and wait for user input.
    
    Returns:
        tuple: (file_path, df) - Path to Excel file and DataFrame with data
    """
    try:
        # Setup logging
        setup_logging()
        
        # Create folders
        base_folder = create_folders()
        
        # Generate Excel file
        excel_path = generate_excel(base_folder)
        
        # Open Excel file for user input
        open_excel_file(excel_path)
        
        logging.info("Excel file created and opened. Please fill in the data and save the file.")
        logging.info("Press Enter when you're ready to continue with the automation...")
        input()
        
        # Get the latest Excel file (in case user created a new one)
        latest_excel = get_latest_excel_file(base_folder)
        if not latest_excel:
            logging.error("No Excel file found. Please create and save an Excel file.")
            return None, None
        
        # Read the data
        df = read_mapping_data(latest_excel)
        if df is None or df.empty:
            logging.error("No data found in Excel file or file is invalid.")
            return None, None
        
        logging.info(f"Successfully loaded {len(df)} rows from Excel file.")
        return latest_excel, df
        
    except Exception as e:
        logging.error(f"Error creating Excel and waiting for input: {e}")
        return None, None


def run_automation_with_excel(dar_mode=False):
    """
    Run the automation workflow with Excel file creation and user input.
    
    Args:
        dar_mode: Whether to run in DAR mode
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create Excel and get data
        excel_path, df = create_excel_and_wait_for_input()
        if excel_path is None or df is None:
            return False
        
        # Run the automation workflow
        counsel_df, main_df = run_automation_workflow(
            latest_excel=excel_path,
            df=df,
            dar_mode=dar_mode
        )
        
        if counsel_df is not None and main_df is not None:
            logging.info("Automation completed successfully!")
            return True
        else:
            logging.error("Automation failed.")
            return False
            
    except Exception as e:
        logging.error(f"Error running automation with Excel: {e}")
        return False


def run_automation_with_existing_excel(excel_path, dar_mode=False):
    """
    Run the automation workflow with an existing Excel file.
    
    Args:
        excel_path: Path to the existing Excel file
        dar_mode: Whether to run in DAR mode
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Read the data
        df = read_mapping_data(excel_path)
        if df is None or df.empty:
            logging.error("No data found in Excel file or file is invalid.")
            return False
        
        logging.info(f"Successfully loaded {len(df)} rows from Excel file.")
        
        # Run the automation workflow
        counsel_df, main_df = run_automation_workflow(
            latest_excel=excel_path,
            df=df,
            dar_mode=dar_mode
        )
        
        if counsel_df is not None and main_df is not None:
            logging.info("Automation completed successfully!")
            return True
        else:
            logging.error("Automation failed.")
            return False
            
    except Exception as e:
        logging.error(f"Error running automation with existing Excel: {e}")
        return False


if __name__ == "__main__":
    # Example usage
    print("Case Law Auto-Routing Automation")
    print("=================================")
    print("1. Create new Excel file and run automation")
    print("2. Use existing Excel file")
    print("3. Run in DAR mode")
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        success = run_automation_with_excel(dar_mode=False)
    elif choice == "2":
        excel_path = input("Enter the path to your Excel file: ").strip()
        success = run_automation_with_existing_excel(excel_path, dar_mode=False)
    elif choice == "3":
        success = run_automation_with_excel(dar_mode=True)
    else:
        print("Invalid choice. Exiting.")
        success = False
    
    if success:
        print("Automation completed successfully!")
    else:
        print("Automation failed. Check the logs for details.")
