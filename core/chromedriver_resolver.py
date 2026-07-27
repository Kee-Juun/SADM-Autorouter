"""
ChromeDriver resolution helpers.

The webdriver_manager fallback URL still returns ChromeDriver 114 when Chrome
version detection fails. That is fatal for modern Chrome, so we independently
detect Chrome, force webdriver_manager to use that version, and validate the
resolved driver before a router starts.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from webdriver_manager.chrome import ChromeDriverManager


VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")


class ChromeDriverVersionMismatch(Exception):
    """Raised when webdriver_manager returns a driver for the wrong Chrome major."""


def _parse_version(text):
    if not text:
        return None
    match = VERSION_RE.search(str(text))
    return match.group(1) if match else None


def _major(version_text):
    version = _parse_version(version_text)
    if not version:
        return None
    return version.split(".", 1)[0]


def _read_chrome_version_from_registry():
    if os.name != "nt":
        return None

    try:
        import winreg
    except Exception:
        return None

    registry_locations = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon", "version"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
            "version",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
            "version",
        ),
    ]

    for root, key_path, value_name in registry_locations:
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
            version = _parse_version(value)
            if version:
                logging.info(f"Detected Chrome version from registry: {version}")
                return version
        except OSError:
            continue
    return None


def _read_file_version(exe_path):
    try:
        import win32api

        info = win32api.GetFileVersionInfo(str(exe_path), "\\")
        ms = info["FileVersionMS"]
        ls = info["FileVersionLS"]
        version = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
        return _parse_version(version)
    except Exception:
        return None


def _candidate_chrome_paths():
    candidates = []
    for env_name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    return candidates


def detect_chrome_version():
    version = _read_chrome_version_from_registry()
    if version:
        return version

    for chrome_path in _candidate_chrome_paths():
        if not chrome_path.exists():
            continue
        version = _read_file_version(chrome_path)
        if version:
            logging.info(f"Detected Chrome version from {chrome_path}: {version}")
            return version

    logging.warning("Could not independently detect the installed Chrome version.")
    return None


def _find_chromedriver_exe(initial_path):
    initial_path = Path(initial_path)
    if initial_path.is_dir():
        candidate = initial_path / "chromedriver.exe"
        if candidate.exists():
            return str(candidate)
        for candidate in initial_path.rglob("chromedriver.exe"):
            return str(candidate)

    if initial_path.name.lower() == "chromedriver.exe" and initial_path.exists():
        return str(initial_path)

    driver_dir = initial_path.parent
    candidate = driver_dir / "chromedriver.exe"
    if candidate.exists():
        return str(candidate)
    for candidate in driver_dir.rglob("chromedriver.exe"):
        return str(candidate)
    return None


def _get_chromedriver_version(driver_path):
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [driver_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
    except Exception as exc:
        logging.warning(f"Could not read ChromeDriver version from {driver_path}: {exc}")
        return None

    return _parse_version((result.stdout or "") + " " + (result.stderr or ""))


def _candidate_bundled_chromedriver_paths():
    base_dirs = []
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        base_dirs.append(Path(frozen_base))

    try:
        base_dirs.append(Path(__file__).resolve().parent.parent)
    except Exception:
        pass

    base_dirs.append(Path.cwd())

    relative_paths = (
        Path("chromedriver.exe"),
        Path("chromedriver") / "chromedriver.exe",
        Path("drivers") / "chromedriver.exe",
        Path("assets") / "drivers" / "chromedriver.exe",
    )

    candidates = []
    seen = set()
    for base_dir in base_dirs:
        for relative_path in relative_paths:
            candidate = base_dir / relative_path
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                candidates.append(candidate)
    return candidates


def _candidate_cached_chromedriver_paths():
    cache_root = Path.home() / ".wdm" / "drivers" / "chromedriver"
    if not cache_root.exists():
        return []

    candidates = list(cache_root.rglob("chromedriver.exe"))
    return sorted(candidates, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)


def _find_compatible_existing_driver(chrome_version):
    chrome_major = _major(chrome_version)
    if not chrome_major:
        return None

    candidates = _candidate_bundled_chromedriver_paths() + _candidate_cached_chromedriver_paths()
    if not candidates:
        logging.info("No bundled or cached ChromeDriver candidates found before download.")
        return None

    for candidate in candidates:
        driver_version = _get_chromedriver_version(str(candidate))
        driver_major = _major(driver_version)
        if driver_major == chrome_major:
            logging.info(
                "Using existing ChromeDriver before download: %s (driver=%s, chrome=%s)",
                candidate,
                driver_version or "unknown",
                chrome_version,
            )
            return str(candidate)

    logging.info("No bundled or cached ChromeDriver matched installed Chrome major %s.", chrome_major)
    return None


def _clear_chromedriver_cache():
    cache_root = Path.home() / ".wdm" / "drivers" / "chromedriver"
    try:
        resolved = cache_root.resolve()
    except Exception:
        resolved = cache_root

    expected_suffix = Path(".wdm") / "drivers" / "chromedriver"
    if tuple(resolved.parts[-3:]) != tuple(expected_suffix.parts):
        logging.warning(f"Refusing to clear unexpected ChromeDriver cache path: {resolved}")
        return

    if resolved.exists():
        logging.warning(f"Clearing ChromeDriver cache after version mismatch: {resolved}")
        shutil.rmtree(resolved, ignore_errors=True)


def _install_driver(driver_version=None):
    start_time = time.time()
    if driver_version:
        logging.info(f"Requesting ChromeDriver for detected Chrome version: {driver_version}")
        initial_path = ChromeDriverManager(driver_version=driver_version).install()
    else:
        logging.info("Requesting ChromeDriver through default ChromeDriverManager detection.")
        initial_path = ChromeDriverManager().install()

    elapsed = time.time() - start_time
    logging.info(f"ChromeDriverManager completed in {elapsed:.1f} seconds. Initial path: {initial_path}")

    driver_path = _find_chromedriver_exe(initial_path)
    if not driver_path or not Path(driver_path).exists():
        raise Exception(f"ChromeDriver chromedriver.exe not found. Searched in: {initial_path}")
    if not driver_path.lower().endswith(".exe"):
        raise Exception(f"ChromeDriver path does not point to .exe file: {driver_path}")
    return driver_path


def resolve_chromedriver_path():
    logging.info("Using ChromeDriverManager to get compatible ChromeDriver...")
    logging.info("Detecting Chrome version and downloading matching ChromeDriver...")
    logging.info("This may take 10-30 seconds on first run or when Chrome is updated. Please wait...")

    chrome_version = detect_chrome_version()
    existing_driver = _find_compatible_existing_driver(chrome_version)
    if existing_driver:
        logging.info(f"Using ChromeDriver at: {existing_driver}")
        return existing_driver

    attempts = []
    if chrome_version:
        attempts.append(chrome_version)
    attempts.append(None)

    last_error = None
    for attempt_number, driver_version in enumerate(attempts, start=1):
        try:
            driver_path = _install_driver(driver_version)
            driver_version_text = _get_chromedriver_version(driver_path)
            logging.info(f"Resolved ChromeDriver version: {driver_version_text or 'unknown'}")

            chrome_major = _major(chrome_version)
            driver_major = _major(driver_version_text)
            if chrome_major and driver_major and chrome_major != driver_major:
                message = (
                    f"ChromeDriver major version mismatch: Chrome {chrome_version} "
                    f"requires major {chrome_major}, but resolved driver is {driver_version_text} "
                    f"at {driver_path}."
                )
                raise ChromeDriverVersionMismatch(message)

            if chrome_major and not driver_major:
                logging.warning("Could not verify ChromeDriver major version; proceeding with resolved driver.")

            logging.info(f"Using ChromeDriver at: {driver_path}")
            return driver_path
        except ChromeDriverVersionMismatch as exc:
            last_error = exc
            logging.warning(str(exc))
            if attempt_number < len(attempts):
                _clear_chromedriver_cache()
                logging.info("Retrying ChromeDriver download after clearing mismatched cache.")
                continue
            break
        except Exception as exc:
            last_error = exc
            logging.warning(f"ChromeDriver resolution attempt {attempt_number}/{len(attempts)} failed: {exc}")
            if attempt_number < len(attempts):
                continue
            break

    raise Exception(
        "Could not resolve a ChromeDriver compatible with the installed Chrome browser. "
        "The machine could not download ChromeDriver and no compatible cached/bundled driver was found. "
        "Please connect to internet/VPN or allow access to ChromeDriver download hosts, then retry."
    ) from last_error
