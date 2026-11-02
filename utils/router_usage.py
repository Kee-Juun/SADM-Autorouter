"""Per-Windows-user router run counts and stable, within-category ordering."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path


def usage_path():
    base = Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home() / '.local' / 'share'
    return base / 'SADM Autorouter' / 'router_usage.json'


def _counts(data):
    if not isinstance(data, dict):
        return {}
    return {mode: count for mode, count in data.items()
            if isinstance(mode, str) and type(count) is int and count >= 0}


def load_router_usage(path=None):
    target = Path(path) if path is not None else usage_path()
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        return _counts(data.get('runs', {})) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_router_run(mode, path=None):
    """Count one launched run. A storage failure must never interrupt routing."""
    if not isinstance(mode, str) or not mode:
        return False
    target = Path(path) if path is not None else usage_path()
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        counts = load_router_usage(target)
        counts[mode] = counts.get(mode, 0) + 1
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp',
                                         dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({'version': 1, 'runs': counts}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return True
    except OSError:
        logging.warning('Could not save router usage; routing will continue.', exc_info=True)
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def rank_router_groups(groups, counts=None):
    """Preserve category order and membership; stable ties use original order."""
    counts = load_router_usage() if counts is None else _counts(counts)
    return tuple((label, tuple(sorted(modes, key=lambda mode: -counts.get(mode, 0))))
                 for label, modes in groups)
