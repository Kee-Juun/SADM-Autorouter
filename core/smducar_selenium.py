"""
Selenium and WebDriver utilities for SADM Autorouter.

This module handles:
- Chrome WebDriver launch and configuration
- Retry decorators for click operations
- Dropdown selection utilities
"""

import logging
import time
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from .smducar_config import load_config
from .chromedriver_resolver import resolve_chromedriver_path


def launch_chrome_driver():
    """
    Launch Chrome WebDriver with appropriate configuration.
    Uses config to determine headless mode.
    
    Returns:
        ChromeWebDriver: Chrome WebDriver instance, or None on failure
    """
    try:
        config = load_config()
        headless_mode = config.get("headless", False)
        logging.info(f"Headless mode setting: {headless_mode}")

        chrome_options = Options()
        if headless_mode:
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            logging.info("Chrome launched in HEADLESS mode")
        else:
            chrome_options.add_argument("--start-maximized")
            # Removed detach option - it can cause Chrome to close immediately
            logging.info("Chrome launched in VISIBLE mode (headless disabled)")

        service = ChromeService(resolve_chromedriver_path())
        driver = ChromeWebDriver(service=service, options=chrome_options)
        
        # If not headless, try to bring window to front
        if not headless_mode:
            try:
                driver.maximize_window()
                # Small delay to ensure window is ready
                time.sleep(0.5)
            except Exception as e:
                logging.warning(f"Could not maximize window: {e}")
        
        logging.info("Chrome browser launched successfully.")
        return driver
    except Exception as e:
        logging.error(f"Chrome launch failed")
        return None


def retry_click(max_attempts=1, delay=0.5):
    """
    Decorator for retrying click operations.
    Currently configured for 1 attempt only.
    
    Args:
        max_attempts: Maximum number of attempts (default: 1)
        delay: Delay between attempts in seconds (default: 0.5)
    
    Returns:
        decorator: Function decorator
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if result:
                        return True
                except Exception as e:
                    logging.warning(f"{func.__name__} failed on attempt {attempt}")
                    time.sleep(delay)
            logging.error(f"{func.__name__} failed after {max_attempts} attempt(s)")
            return False

        return wrapper

    return decorator


def select_dropdown_by_text(driver, element_id, visible_text):
    """
    Select a dropdown option by visible text and trigger change event.
    
    Args:
        driver: Selenium WebDriver instance
        element_id: ID of the dropdown element
        visible_text: Text of the option to select
    
    Returns:
        None (logs errors on failure)
    """
    try:
        select = Select(driver.find_element(By.ID, element_id))
        select.select_by_visible_text(visible_text)
        driver.execute_script(f"document.getElementById('{element_id}').dispatchEvent(new Event('change'))")
        logging.info(f"Selected '{visible_text}' from dropdown '{element_id}'.")
    except Exception as e:
        logging.error(f"Could not select dropdown option from '{element_id}'")

