"""Persistent item history and the Inventory's default priority order."""
import math
import time


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def normalized_history(value):
    if not isinstance(value, dict):
        return {}
    return {key: {'acquired_at': _number(item.get('acquired_at')),
                  'use_count': int(_number(item.get('use_count')))}
            for key, item in value.items() if isinstance(key, str) and isinstance(item, dict)}


def record_acquisition(user_data, reward_id, *, now=None):
    history = normalized_history(user_data.get('item_history'))
    item = history.setdefault(reward_id, {'acquired_at': 0, 'use_count': 0})
    if not item['acquired_at']:
        item['acquired_at'] = _number(time.time() if now is None else now)
    user_data['item_history'] = history


def record_usage(user_data, reward_id):
    history = normalized_history(user_data.get('item_history'))
    item = history.setdefault(reward_id, {'acquired_at': 0, 'use_count': 0})
    item['use_count'] += 1
    user_data['item_history'] = history


def inventory_order(entries, user_data):
    """Equipped first, acquisition newest first, use count highest first, stable fallback.

    Unknown legacy acquisition dates remain unknown instead of being backdated.
    Search relevance can use this order to resolve equally ranked matches.
    """
    equipped = user_data.get('equipped') or {}
    history = normalized_history(user_data.get('item_history'))

    def priority(pair):
        index, (reward_id, reward) = pair
        item = history.get(reward_id, {})
        return (0 if equipped.get(reward.get('type')) == reward_id else 1,
                -item.get('acquired_at', 0), -item.get('use_count', 0), index)

    return [entry for _, entry in sorted(enumerate(entries), key=priority)]
