"""Serializable game state and level definitions for Archivebound."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .level_one import (
    MEMORY_SEQUENCE,
    MEMORY_SEARCH_OBJECTS,
    NARRATIVE_FLAG_IDS,
    ORDER_SHARDS,
    ORDER_INVESTIGATION_IDS,
    RESPONSE_TENDENCY_IDS,
    ROOM_SAFE_SPAWNS,
    TRIAL_IDS,
    TRIAL_REWARDS,
    VALID_ROOM_IDS,
)


LEVEL_ID = "hall_of_pending_things"


@dataclass
class ArchiveboundState:
    """Player progress kept independently from autorouter run state."""

    version: int = 13
    level_id: str = LEVEL_ID
    player_x: float = 480.0
    player_y: float = 525.0
    player_hp: int = 100
    seals: list[str] = field(default_factory=list)
    clerk_met: bool = False
    boss_defeated: bool = False
    level_complete: bool = False
    reward_claimed: bool = False
    current_room: str = "hub"
    completed_trials: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    gold: int = 0
    memory_progress: int = 0
    memory_archives_completed: list[str] = field(default_factory=list)
    memory_hourglass_locations: dict[str, str] = field(default_factory=dict)
    mercy_appeals_completed: list[str] = field(default_factory=list)
    mercy_hearing_completed: bool = False
    order_shards: list[str] = field(default_factory=list)
    order_investigations_completed: list[str] = field(default_factory=list)
    order_case_variants: dict[str, int] = field(default_factory=dict)
    order_corruption: int = 0
    order_fused_shards: list[str] = field(default_factory=list)
    order_chest_gem_assembled: bool = False
    order_chest_unlocked: bool = False
    defeated_enemies: list[str] = field(default_factory=list)
    rewarded_trials: list[str] = field(default_factory=list)
    completed_seal_puzzles: list[str] = field(default_factory=list)
    key_fragments: list[str] = field(default_factory=list)
    fused_key_parts: list[str] = field(default_factory=list)
    vault_key_assembled: bool = False
    vault_key_inserted: bool = False
    vault_opened: bool = False
    hud_collapsed: bool = False
    narrative_flags: list[str] = field(default_factory=list)
    response_tendencies: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: object) -> "ArchiveboundState":
        if not isinstance(raw, dict):
            return cls()
        defaults = cls()
        values = {
            key: raw.get(key, getattr(defaults, key))
            for key in defaults.__dataclass_fields__
        }
        values["version"] = defaults.version
        def clean_list(key: str, allowed=None) -> list[str]:
            source = values.get(key, [])
            if not isinstance(source, (list, tuple, set)):
                return []
            result = [str(value) for value in source]
            if allowed is not None:
                result = [value for value in result if value in allowed]
            return list(dict.fromkeys(result))

        source_version = cls._safe_int(raw.get("version"), 1)
        seals = clean_list("seals", TRIAL_IDS)
        completed = clean_list("completed_trials", TRIAL_IDS)
        if source_version < 4:
            completed = list(dict.fromkeys(completed + seals))
        memory_progress = max(0, min(3, cls._safe_int(values.get("memory_progress"), 0)))
        memory_archives = clean_list("memory_archives_completed", MEMORY_SEQUENCE)
        if source_version < 6 and not memory_archives:
            memory_archives = list(MEMORY_SEQUENCE[:memory_progress])
        defeated = clean_list(
            "defeated_enemies",
            ("red_tape_wraith", "misfiled_mimic"),
        )
        mercy_appeals = clean_list("mercy_appeals_completed", ("pardon", "diversion", "cure"))
        mercy_hearing_completed = bool(values.get("mercy_hearing_completed"))
        order_shards = clean_list("order_shards", tuple(ORDER_SHARDS))
        order_completed = clean_list("order_investigations_completed", ORDER_INVESTIGATION_IDS)
        legacy_investigations = dict(zip(tuple(ORDER_SHARDS), ORDER_INVESTIGATION_IDS))
        for shard_id in order_shards:
            investigation_id = legacy_investigations.get(shard_id)
            if investigation_id and investigation_id not in order_completed:
                order_completed.append(investigation_id)
        if memory_progress >= 3 and "memory" not in completed:
            completed.append("memory")
        # Builds before v11 treated the threshold Wraith as the whole Mercy
        # trial. Preserve those saves as fully complete; new saves must finish
        # all three appeals and the Hearing of Exceptions.
        if source_version < 11 and "red_tape_wraith" in defeated:
            mercy_appeals = ["pardon", "diversion", "cure"]
            mercy_hearing_completed = True
            if "mercy" not in completed:
                completed.append("mercy")
        # Version 11 briefly required a second fight after the investigative
        # hearing. Version 12 removes that duplicate encounter: a completed
        # hearing now resolves the Hall and preserves the player's work.
        if (
            source_version < 12
            and mercy_hearing_completed
            and len(mercy_appeals) == 3
            and "mercy" not in completed
        ):
            completed.append("mercy")
        if "misfiled_mimic" in defeated and "order" not in completed:
            completed.append("order")
        if bool(values.get("boss_defeated")) or bool(values.get("level_complete")):
            completed = list(TRIAL_IDS)
            values["boss_defeated"] = True
            values["level_complete"] = True
        values["completed_trials"] = completed
        if "memory" in completed:
            memory_progress = 3
            memory_archives = list(MEMORY_SEQUENCE)
        if "mercy" in completed and "red_tape_wraith" not in defeated:
            defeated.append("red_tape_wraith")
        if "mercy" in completed:
            mercy_appeals = ["pardon", "diversion", "cure"]
            mercy_hearing_completed = True
        if "order" in completed:
            order_shards = list(ORDER_SHARDS)
            order_completed = list(ORDER_INVESTIGATION_IDS)
            if "misfiled_mimic" not in defeated:
                defeated.append("misfiled_mimic")
        memory_progress = len(memory_archives)
        values["memory_progress"] = memory_progress
        values["memory_archives_completed"] = memory_archives
        valid_memory_locations = {item["id"] for item in MEMORY_SEARCH_OBJECTS}
        raw_locations = values.get("memory_hourglass_locations", {})
        locations = {}
        if isinstance(raw_locations, dict):
            for archive_id in MEMORY_SEQUENCE:
                location = str(raw_locations.get(archive_id, ""))
                if location in valid_memory_locations and location not in locations.values():
                    locations[archive_id] = location
        values["memory_hourglass_locations"] = locations
        values["mercy_appeals_completed"] = mercy_appeals
        values["mercy_hearing_completed"] = mercy_hearing_completed
        values["defeated_enemies"] = defeated
        values["order_shards"] = order_shards
        values["order_investigations_completed"] = order_completed
        raw_variants = values.get("order_case_variants", {})
        variants = {}
        if isinstance(raw_variants, dict):
            for investigation_id in ORDER_INVESTIGATION_IDS:
                variant = cls._safe_int(raw_variants.get(investigation_id), -1)
                if 0 <= variant <= 2:
                    variants[investigation_id] = variant
        values["order_case_variants"] = variants
        values["order_corruption"] = max(0, min(3, cls._safe_int(values.get("order_corruption"), 0)))
        fused_order = clean_list("order_fused_shards", tuple(ORDER_SHARDS))
        if not set(fused_order).issubset(set(order_shards)):
            fused_order = [shard_id for shard_id in fused_order if shard_id in order_shards]
        if bool(values.get("order_chest_gem_assembled")):
            fused_order = list(ORDER_SHARDS)
        values["order_fused_shards"] = fused_order
        values["order_chest_gem_assembled"] = len(fused_order) == len(ORDER_SHARDS)
        if "misfiled_mimic" in defeated:
            values["order_chest_unlocked"] = True
        else:
            values["order_chest_unlocked"] = bool(values.get("order_chest_unlocked"))

        inventory = clean_list("inventory")
        inventory = ["reset_compass" if value == "archive_compass" else value for value in inventory]
        values["inventory"] = list(dict.fromkeys(inventory))
        for trial_id in completed:
            item = TRIAL_REWARDS[trial_id]["item"]
            if item not in values["inventory"]:
                values["inventory"].append(item)
        rewarded = clean_list("rewarded_trials", TRIAL_IDS)
        if "rewarded_trials" not in raw:
            rewarded = list(completed)
        values["rewarded_trials"] = rewarded
        solved = clean_list("completed_seal_puzzles", TRIAL_IDS)
        fragments = clean_list("key_fragments", TRIAL_IDS)
        fused = clean_list("fused_key_parts", TRIAL_IDS)
        if source_version < 4:
            # Version 3 called completed hall trials "seals". Preserve that
            # achievement when introducing the separate main-hall puzzles.
            solved = list(dict.fromkeys(solved + seals + completed))
            fragments = list(dict.fromkeys(fragments + solved))
        elif not solved and seals:
            # Accept the short-lived version-4 alias written by early builds.
            solved = list(seals)
            completed = list(dict.fromkeys(completed + solved))
            values["completed_trials"] = completed
        solved = [trial_id for trial_id in solved if trial_id in completed]
        fragments = [trial_id for trial_id in fragments if trial_id in solved]
        fused = [trial_id for trial_id in fused if trial_id in fragments]
        assembled = bool(values.get("vault_key_assembled"))
        if source_version < 4 and len(fragments) == len(TRIAL_IDS):
            assembled = True
            fused = list(TRIAL_IDS)
        if bool(values.get("boss_defeated")) or bool(values.get("level_complete")):
            solved = list(TRIAL_IDS)
            fragments = list(TRIAL_IDS)
            fused = list(TRIAL_IDS)
            assembled = True
        values["completed_seal_puzzles"] = solved
        values["seals"] = list(solved)
        values["key_fragments"] = fragments
        values["fused_key_parts"] = fused
        values["vault_key_assembled"] = assembled and len(fused) == len(TRIAL_IDS)
        values["vault_key_inserted"] = bool(values.get("vault_key_inserted")) and values["vault_key_assembled"]
        values["vault_opened"] = bool(values.get("vault_opened")) and values["vault_key_inserted"]
        if bool(values.get("boss_defeated")) or bool(values.get("level_complete")):
            values["vault_key_inserted"] = True
            values["vault_opened"] = True
        values["hud_collapsed"] = bool(values.get("hud_collapsed"))
        narrative_flags = clean_list("narrative_flags", NARRATIVE_FLAG_IDS)
        if source_version < 9:
            if bool(values.get("clerk_met")):
                narrative_flags.extend(("opening_seen", "lantern_recognition_seen"))
            for index in range(1, min(3, len(completed)) + 1):
                narrative_flags.append(f"hub_interlude_{index}_seen")
            if "memory" in completed:
                narrative_flags.extend(("memory_threshold_seen", "memory_vey_whisper_heard"))
            if "mercy" in completed:
                narrative_flags.extend(("mercy_threshold_seen", "mercy_testimonies_read"))
            if "order" in completed:
                narrative_flags.extend(("order_threshold_seen", "order_master_docket_seen"))
            if len(solved) == len(TRIAL_IDS):
                narrative_flags.append("key_inscription_seen")
            if bool(values.get("vault_opened")):
                narrative_flags.extend(("pre_vault_conversation_seen", "vault_identity_phrase_heard"))
            if bool(values.get("level_complete")):
                narrative_flags.extend(("pending_human_names_seen", "level_one_epilogue_seen"))
        if source_version < 13 and (
            bool(values.get("clerk_met"))
            or "opening_seen" in narrative_flags
            or completed
            or solved
        ):
            # Existing players already know how to move and interact. Do not
            # strand an established save behind the new onboarding gate.
            narrative_flags.extend((
                "movement_tutorial_started",
                "movement_tutorial_complete",
                "interaction_tutorial_complete",
                "onboarding_complete",
            ))
        values["narrative_flags"] = list(dict.fromkeys(narrative_flags))
        raw_tendencies = values.get("response_tendencies", {})
        tendencies = {}
        if isinstance(raw_tendencies, dict):
            for tendency in RESPONSE_TENDENCY_IDS:
                count = max(0, cls._safe_int(raw_tendencies.get(tendency), 0))
                if count:
                    tendencies[tendency] = count
        values["response_tendencies"] = tendencies
        values["current_room"] = values["current_room"] if values["current_room"] in VALID_ROOM_IDS else "hub"
        values["gold"] = max(0, cls._safe_int(values.get("gold"), 0))
        values["player_hp"] = max(1, min(100, cls._safe_int(values.get("player_hp"), 100)))
        x = cls._safe_float(values.get("player_x"))
        y = cls._safe_float(values.get("player_y"))
        if x is None or y is None or not (64 <= x <= 896 and 205 <= y <= 575):
            x, y = ROOM_SAFE_SPAWNS[values["current_room"]]
        values["player_x"], values["player_y"] = x, y
        values["clerk_met"] = bool(values.get("clerk_met"))
        values["boss_defeated"] = bool(values.get("boss_defeated"))
        values["level_complete"] = bool(values.get("level_complete")) and values["boss_defeated"]
        values["reward_claimed"] = bool(values.get("reward_claimed"))
        return cls(**values)

    @staticmethod
    def _safe_int(value, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


SEALS = {
    "memory": {
        "name": "Seal of Memory",
        "position": (196, 230),
        "color": "#68edf2",
        "line": "The crystal remembers every deadline. None of them remember you kindly.",
    },
    "mercy": {
        "name": "Seal of Mercy",
        "position": (770, 330),
        "color": "#9de7ff",
        "line": "The moon seal accepts your filing. Against its better judgment.",
    },
    "order": {
        "name": "Seal of Order",
        "position": (770, 520),
        "color": "#57d5e8",
        "line": "The final seal clicks awake. Somewhere, a form becomes mandatory.",
    },
}

CLERK_POSITION = (330, 500)
VAULT_POSITION = (480, 172)
