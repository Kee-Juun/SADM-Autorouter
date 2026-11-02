"""IRSPLR's browser-first PDF check. Never downloads or extracts the source."""

import logging
import time

from .irsplr_extractor import IRSPLRCorruptDocument, IRSPLRDocumentReviewRequired


def browser_pdf_state(driver, read_viewer_error):
    error = read_viewer_error()
    if error:
        return "failed"
    state = driver.execute_script(r"""
        function visible(el) {
            if (!el.getClientRects().length) return false;
            for (let node = el; node; node = node.parentElement || node.getRootNode().host) {
                const style = getComputedStyle(node);
                if (node.hidden || node.getAttribute('aria-hidden') === 'true' ||
                    style.display === 'none' || style.visibility === 'hidden') return false;
            }
            return true;
        }
        function scan(root) {
            let loaded = false;
            for (const el of root.querySelectorAll('*')) {
                if (el.tagName === 'VIEWER-PASSWORD-DIALOG' && visible(el)) return 'password';
                // Public UI properties; an embed or an empty page counter is
                // not evidence that Chrome has actually parsed any PDF pages.
                if (el.tagName === 'VIEWER-TOOLBAR' && visible(el) &&
                    Number(el.docLength) > 0 && Number(el.loadProgress) >= 100) loaded = true;
                if (el.shadowRoot) {
                    const state = scan(el.shadowRoot);
                    if (state === 'password') return state;
                    if (state === 'loaded') loaded = true;
                }
            }
            return loaded ? 'loaded' : 'loading';
        }
        return scan(document);
    """)
    if state in {"loaded", "password"}:
        return state

    # Chrome's PDF viewer can be a cross-origin child frame. Its accessibility
    # PDF root with page children is positive evidence, including image scans.
    def parsed_pages(tree):
        return any(
            not node.get("ignored")
            and str(node.get("role", {}).get("value", "")).lower() == "pdfroot"
            and node.get("childIds")
            for node in tree.get("nodes", [])
        )

    def frames(tree):
        for child in tree.get("childFrames", []):
            yield child["frame"]["id"]
            yield from frames(child)

    try:
        if parsed_pages(driver.execute_cdp_cmd("Accessibility.getFullAXTree", {})):
            return "loaded"
        tree = driver.execute_cdp_cmd("Page.getFrameTree", {}).get("frameTree", {})
        for frame_id in frames(tree):
            if parsed_pages(driver.execute_cdp_cmd("Accessibility.getFullAXTree", {"frameId": frame_id})):
                return "loaded"
    except Exception:
        # An unsupported accessibility command is not proof of corruption.
        logging.debug("IRSPLR PDF accessibility readiness check unavailable.", exc_info=True)
    return "loading"


def confirm_browser_pdf(driver, read_viewer_error, source_headers, *, timeout=45):
    """Require loaded pages, or a repeated explicit failure after one reload.

    A persistent viewer failure is only confirmed against an accessible PDF
    response. Login/network/HTTP failures remain manual review, not exclusion.
    """
    deadline = time.monotonic() + timeout
    loaded_since = None
    failure_since = None
    retried = False
    last_log = -10
    while time.monotonic() < deadline:
        now = time.monotonic()
        state = browser_pdf_state(driver, read_viewer_error)
        if state == "password":
            raise IRSPLRDocumentReviewRequired("PASSWORD PROTECTED - supply an unlocked PDF; corruption is not verified")
        if state == "loaded":
            failure_since = None
            if loaded_since is None:
                loaded_since = now
            if now - loaded_since >= 1:
                # Do not let a late error dialog race the readiness signal.
                if not read_viewer_error():
                    logging.info("IRSPLR browser-first check passed: Chrome has loaded PDF pages.")
                    return
        else:
            loaded_since = None
        if state == "failed":
            if failure_since is None:
                failure_since = now
            if now - failure_since >= 2:
                if not retried:
                    logging.info("IRSPLR viewer reported Failed to load PDF; reloading once to confirm.")
                    driver.refresh()
                    retried = True
                    failure_since = None
                    deadline = time.monotonic() + timeout
                else:
                    headers = source_headers() or {}
                    content_type = str(headers.get("content_type", "")).lower()
                    length = str(headers.get("content_length", "")).strip()
                    if headers.get("ok") and "application/pdf" in content_type and length != "0":
                        raise IRSPLRCorruptDocument(
                            "LOAD FAILED - Chrome repeatedly displayed Failed to load PDF document after one reload; "
                            "the source is accessible as a PDF but cannot be opened in the browser"
                        )
                    raise IRSPLRDocumentReviewRequired(
                        "VIEWER LOAD FAILED - source access could not be confirmed "
                        f"(HTTP {headers.get('status', 'unavailable')}); check access or supply a working PDF; corruption is not verified"
                    )
        elif state != "loaded":
            failure_since = None
        if now - last_log >= 10:
            logging.info("IRSPLR browser-first check: waiting for PDF pages (%s).", state)
            last_log = now
        time.sleep(0.5)
    raise IRSPLRDocumentReviewRequired(
        "BROWSER CHECK UNCONFIRMED - PDF pages did not finish loading; retry or supply a working PDF; corruption is not verified"
    )
