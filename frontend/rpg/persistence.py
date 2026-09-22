"""Versioned persistence and one-time rewards for Archivebound."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from utils.rewards import PUBLIC_ACH_DIR, load_user_rewards, save_user_rewards

from .state import ArchiveboundState


SAVE_PATH = PUBLIC_ACH_DIR / "archivebound_save.json"
COMPLETION_COINS = 150


def load_game(path: Path | None = None) -> ArchiveboundState:
    target = path or SAVE_PATH
    try:
        if target.exists():
            with target.open("r", encoding="utf-8") as handle:
                return ArchiveboundState.from_dict(json.load(handle))
    except Exception:
        logging.exception("Archivebound save could not be loaded; using a new save.")
    return ArchiveboundState()


def save_game(state: ArchiveboundState, path: Path | None = None) -> None:
    target = path or SAVE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2)
        temporary.replace(target)
    except Exception:
        logging.exception("Archivebound save could not be written.")


def grant_completion_reward(state: ArchiveboundState) -> bool:
    """Grant the level reward once, even when the ending is replayed."""
    if state.reward_claimed:
        return False
    rewards = load_user_rewards()
    rewards["coins"] = int(rewards.get("coins", 0) or 0) + COMPLETION_COINS
    save_user_rewards(rewards)
    state.reward_claimed = True
    save_game(state)
    logging.info("Archivebound Level 1 reward granted: %s coins.", COMPLETION_COINS)
    return True
