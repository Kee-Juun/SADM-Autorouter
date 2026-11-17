"""Small, Qt-independent status channel to the separate startup UI process."""

import json
import os
import socket


_closed = False


def _send(event, message="", progress=None):
    if _closed:
        return
    try:
        endpoint = os.environ.get("SADM_STARTUP_ENDPOINT", "")
        if not endpoint:
            return
        port, token = endpoint.split(":", 1)
        payload = {"event": event, "message": str(message)[:1000], "token": token}
        if isinstance(progress, (int, float)) and not isinstance(progress, bool) and 0 <= progress <= 100:
            payload["progress"] = min(99, int(progress))
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.2) as channel:
            channel.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    except (ValueError, OSError):
        # Starting the engine directly, or closing its loader, must stay safe.
        pass


def report_startup(message, progress=None):
    """Report a real milestone, optionally with its estimated startup percentage."""
    _send("stage", message, progress)


def close_startup():
    global _closed
    if _closed:
        return
    _send("ready")
    _closed = True


def fail_startup(message):
    global _closed
    if _closed:
        return
    _send("error", message)
    _closed = True
