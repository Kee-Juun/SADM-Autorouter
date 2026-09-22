"""Playable Level 1 window for Out of Spec: The Archivist Trials."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRegion,
    QTransform,
)
from PyQt5.QtWidgets import QMainWindow, QWidget

from core.smducar_config import resource_path

from .level_one import (
    ENEMIES,
    FRAGMENT_TESTIMONIES,
    HALL_PREREQUISITES,
    HALL_SEQUENCE,
    MEMORY_ARCHIVE_RULES,
    MEMORY_PLINTHS,
    MEMORY_SEARCH_OBJECTS,
    MEMORY_SEQUENCE,
    MERCY_APPEALS,
    MERCY_APPEAL_IDS,
    MERCY_CONSEQUENCE_LINKS,
    ORDER_INVESTIGATIONS,
    ORDER_INVESTIGATION_IDS,
    ORDER_ROTOR_RECORDS,
    ORDER_SHARDS,
    ORDER_STATIONS,
    ROOMS,
    ROOM_EXITS,
    ROOM_ENVIRONMENT_SPRITES,
    ROOM_NAVIGATION,
    ROOM_SAFE_SPAWNS,
    SEAL_PUZZLES,
    SEAL_REVELATIONS,
    TRIAL_REWARDS,
)
from .narrative import (
    DEFEAT_CINEMATIC,
    LEVEL_EPILOGUE,
    MIMIC_INTRO,
    OPENING_DIALOGUE,
    ROOM_INTROS,
    VAULT_INTRO,
    VICTORY_CINEMATIC,
)
from .persistence import COMPLETION_COINS, grant_completion_reward, load_game, save_game
from .state import CLERK_POSITION, SEALS, VAULT_POSITION, ArchiveboundState


GAME_WIDTH = 960
GAME_HEIGHT = 640
ASSET_DIR = Path(resource_path("assets/rpg"))
GAME_WINDOW_TITLE = "Out of Spec: The Archivist Trials"
GAME_TITLE = "OUT OF SPEC"
GAME_CAPTION = "THE ARCHIVIST TRIALS"
TITLE_CONTINUE_RECT = QRect(315, 330, 330, 110)
TITLE_NEW_GAME_RECT = QRect(315, 438, 330, 110)
ORDER_TURN_LIMIT = 24

# Primary investigation screens communicate through five-second visual
# reconstructions. Full prose remains available in the optional Case File.
REGISTRY_VISUAL_CAPTIONS = {
    "identity": (
        "Someone removed a name, but left the job behind.",
        "The missing keeper's coat still carries its hourglass key.",
        "Marr records the fault from the east desk.",
        "Vale authorizes the transfer from the gallery.",
        "Rook's iron bell key remains logged with the western stacks.",
    ),
    "sequence": (
        "Names vanish from ink. Their wax impressions remain.",
        "Marr hides one surviving copy beneath her desk.",
        "A Black Sun transfer lowers the docket from public view.",
        "Blue fire reaches the western stacks. Rook sounds the bell.",
    ),
    "authority": (
        "Its clock stopped. Its lamp remained in the living index.",
        "One public desk released it. Another signed its receipt.",
        "Blue flame came first. This impression followed.",
        "The docket still lived when its public window went dark.",
    ),
}

REGISTRY_VISUAL_LABELS = {
    "identity": ("ERASED ROLL", "KEEPER'S COAT", "EAST DESK", "GALLERY", "BELL KEY"),
    "sequence": ("VANISHING INK", "HIDDEN COPY", "BLACK SUN", "BLUE FIRE"),
    "authority": ("HOURGLASS", "CROWN", "ASHEN BELL", "BLACK SUN"),
}

REGISTRY_CHARACTER_TOOLTIPS = {
    "elian_vey": "Maintains the Chronometer and the time records entrusted to it.",
    "lysa_marr": "Copies registry records and checks what changes between versions.",
    "orren_vale": "Authorizes sealed transfers and final registry decisions.",
    "tomas_rook": "Keeps the western bells and answers threats to the archive stacks.",
}

REGISTRY_AUTHORITY_TOOLTIPS = {
    "hourglass": "A keeper's seal used when a disputed record needs time, not disappearance.",
    "registry_crown": "A public transfer mark. Its records normally name both the sending and receiving desks.",
    "ashen_bell": "An emergency impression applied to records threatened by fire, flood, or collapse.",
    "black_sun": "A restricted Chancellery seal. Its destination is omitted from ordinary public indexes.",
}

# Reachable floor sigils beside the three monuments. These positions are also
# the interaction targets, so the art and gameplay cannot drift apart.
HUB_SEAL_MARKER_CENTERS = {
    "memory": (302.0, 326.0),
    "mercy": (642.0, 326.0),
    "order": (652.0, 480.0),
}

ABILITY_ORDER = ("Q", "W", "E", "R")
ABILITY_DEFS = {
    "Q": {"action": "q_slash", "name": "Quill Slash", "cooldown": 0, "color": "#20c9d2"},
    "W": {"action": "w_ward", "name": "File Ward", "cooldown": 2, "color": "#4d82d8"},
    "E": {"action": "e_mark", "name": "Wax Mark", "cooldown": 2, "color": "#d04e66"},
    "R": {"action": "r_redline", "name": "Final Redline", "cooldown": 3, "color": "#c84791"},
}
ITEM_ORDER = ("appeal_tonic", "reset_compass", "recall_lens")
ITEM_DEFS = {
    "recall_lens": {"key": "3", "name": "Recall Lens", "icon": "recall_lens", "icon_group": "quest"},
    "appeal_tonic": {"key": "1", "name": "Appeal Tonic"},
    "reset_compass": {"key": "2", "name": "Reset Compass", "icon": "archive_compass"},
}
MARA_RECOVERY_COST = 15
MERCY_LOOM_AUDIT_LIMIT = 6

RELIC_INFO = {
    "recall_lens": (
        "Recall Lens",
        "Combat relic [3]: grants 1 Focus and Foresight, halving the next incoming attack. Recharges each battle.",
    ),
    "appeal_tonic": ("Appeal Tonic", "A bottled exception earned from the Hall of Mercy."),
    "reset_compass": ("Reset Compass", "A registry compass that points toward corrected order."),
    "fragment_memory": ("Memory Fragment", "One of three vault-key fragments. Remembers every lock."),
    "registry_shard_west": ("Identity Shard", "The restored name of Elian Vey, cut into one-third of a trefoil seal."),
    "registry_shard_east": ("Sequence Shard", "The recovered order of Docket VII-13, cut into one-third of a trefoil seal."),
    "registry_shard_south": ("Authority Shard", "The Black Sun jurisdiction finding, cut into one-third of a trefoil seal."),
    "registry_shard_pair": ("Joined Docket Shards", "Two Registry findings have remembered that they belong together."),
    "registry_chest_gem": ("Master Docket Gem", "A fused three-part seal shaped precisely for the central chest's lock."),
    "fragment_mercy": ("Mercy Fragment", "One of three vault-key fragments. Warm despite precedent."),
    "fragment_order": ("Order Fragment", "One of three vault-key fragments. Insists on proper alignment."),
    "key_pair": ("Joined Fragments", "Two of three key fragments have fused. Add the final fragment."),
    "vault_key": ("Key of the Three Seals", "The completed relic. Drag it into the vault keyhole."),
    "pending_codex": ("Codex of the Unclosed", "The Pending's surviving record. Read it to reveal the road to Level II."),
    "hourglass_past": ("Past Hourglass", "A reversed relic recovered while history was walking backward."),
    "hourglass_present": ("Present Hourglass", "A restless relic that measures only the vanishing now."),
    "hourglass_future": ("Future Hourglass", "A suspended relic whose next grain has not decided to fall."),
}
PUZZLE_MEMORY_ORDER = ("oath", "fracture", "exile", "silence", "return")
PUZZLE_SOCKET_SHAPES = ("triangle", "circle", "square", "star", "diamond")
PUZZLE_MEMORY_CLUES = {
    "oath": "A promise existed before anything could be broken.",
    "fracture": "The promise broke before its keeper was cast out.",
    "exile": "The keeper left while the archive bells still spoke.",
    "silence": "The bells fell quiet before the lantern came home.",
    "return": "Only silence witnessed the lantern's return.",
}


class ArchiveboundWindow(QMainWindow):
    """Standalone host window that keeps the autorouter isolated from game state."""

    def __init__(self, host_window=None):
        super().__init__()
        self.host_window = host_window
        self.setWindowTitle(GAME_WINDOW_TITLE)
        icon_path = ASSET_DIR.parent / "icons" / "archivebound.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setFixedSize(GAME_WIDTH, GAME_HEIGHT)
        self.setCentralWidget(ArchiveboundCanvas(self))
        self.setStyleSheet("background: #080912;")

    def closeEvent(self, event):
        self.centralWidget().persist()
        if self.host_window is not None:
            self.host_window.showNormal()
            self.host_window.raise_()
        super().closeEvent(event)


class ArchiveboundCanvas(QWidget):
    """One-level exploration, dialogue, quest, and turn-based encounter."""

    WALK_BOUNDS = QRectF(64, 205, 832, 370)
    INTERACT_DISTANCE = 92.0
    PLAYER_FOOT_RADIUS = 13.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.backgrounds = {
            room_id: QPixmap(str(ASSET_DIR / details["background"]))
            for room_id, details in ROOMS.items()
        }
        self.title_background = QPixmap(str(ASSET_DIR / "title_bellglass_fire_v3.png"))
        self.title_bellglass_fire_atlas = QPixmap(
            str(ASSET_DIR / "title_bellglass_fire_idle_atlas_v1.png")
        )
        self.title_bellglass_fire_frames = self._uniform_grid_atlas_frames(
            self.title_bellglass_fire_atlas, 4, 1
        )
        self.title_flourish_atlas = QPixmap(
            str(ASSET_DIR / "title_bellglass_title_flourish_atlas_v1.png")
        )
        self.title_flourish_frames = self._uniform_grid_atlas_frames(
            self.title_flourish_atlas, 4, 1
        )
        self.title_smoke_atlas = QPixmap(
            str(ASSET_DIR / "title_bellglass_smoke_idle_atlas_v1.png")
        )
        self.title_smoke_frames = self._uniform_grid_atlas_frames(
            self.title_smoke_atlas, 4, 1
        )
        self.title_sparks_atlas = QPixmap(
            str(ASSET_DIR / "title_bellglass_sparks_idle_atlas_v1.png")
        )
        self.title_sparks_frames = self._uniform_grid_atlas_frames(
            self.title_sparks_atlas, 4, 1
        )
        self.title_continue_button = QPixmap(str(ASSET_DIR / "title_button_continue_v1.png"))
        self.title_new_game_button = QPixmap(str(ASSET_DIR / "title_button_new_game_v1.png"))
        self.environment_sheets = {
            spec["sheet"]: QPixmap(str(ASSET_DIR / spec["sheet"]))
            for specs in ROOM_ENVIRONMENT_SPRITES.values()
            for spec in specs
        }
        self.memory_plinth_state_atlases = {
            archive_id: QPixmap(str(
                ASSET_DIR / f"environment/memory/{archive_id}_state_atlas_v4_aligned.png"
            ))
            for archive_id in MEMORY_SEQUENCE
        }
        self.memory_plinth_incomplete_bases = {
            archive_id: QPixmap(str(
                ASSET_DIR / f"environment/memory/{archive_id}_incomplete_static_v1.png"
            ))
            for archive_id in MEMORY_SEQUENCE
        }
        self.memory_plinth_incomplete_vfx = {
            archive_id: QPixmap(str(
                ASSET_DIR / f"environment/memory/{archive_id}_incomplete_vfx_v1.png"
            ))
            for archive_id in MEMORY_SEQUENCE
        }
        self.hero_sheet = QPixmap(str(ASSET_DIR / "last_clerk_directional_walk_runtime_sheet.png"))
        self.hero_back_sheet = QPixmap(str(ASSET_DIR / "last_clerk_back_walk_runtime_sheet.png"))
        self.hero_side_walk_atlas = QPixmap(str(ASSET_DIR / "last_clerk_side_walk_runtime_sheet_v4.png"))
        self.hero_side_walk_frames = self._side_walk_atlas_frames(self.hero_side_walk_atlas)
        self.hero_idle_sheet = QPixmap(str(ASSET_DIR / "last_clerk_idle_actions_runtime_sheet.png"))
        self.hero_back_idle_sheet = QPixmap(str(ASSET_DIR / "last_clerk_back_idle_actions_runtime_sheet.png"))
        self.hero_idle_frames = self._trimmed_strip_frames(self.hero_idle_sheet, 12)
        self.hero_back_idle_frames = self._trimmed_strip_frames(self.hero_back_idle_sheet, 12)
        self.mara_idle_sheet = QPixmap(str(ASSET_DIR / "mara_idle_sprites.png"))
        self.mara_closeup_sheet = QPixmap(str(ASSET_DIR / "dialogue/mara_closeup_expression_atlas_v2.png"))
        self.hero_closeup_sheet = QPixmap(str(ASSET_DIR / "dialogue/archivist_closeup_expression_atlas_v2.png"))
        self.mara_closeup_situations_sheet = QPixmap(
            str(ASSET_DIR / "dialogue/mara_closeup_situations_atlas_v3.png")
        )
        self.hero_closeup_situations_sheet = QPixmap(
            str(ASSET_DIR / "dialogue/archivist_closeup_situations_atlas_v3.png")
        )
        self.minion_sheet = QPixmap(str(ASSET_DIR / "combat/pending_minion/minion_runtime_sheet.png"))
        self.vault_lock_overlay = QPixmap(str(ASSET_DIR / "environment/hub/vault_lock_overlay.png"))
        self.memory_hourglass_atlas = QPixmap(str(ASSET_DIR / "memory_hourglass_relics_atlas_v1.png"))
        self.memory_search_props_atlas = QPixmap(str(ASSET_DIR / "memory_search_props_atlas_v1.png"))
        self.memory_search_prop_frames = self._memory_prop_frames()
        self.memory_search_prop_glows = {
            prop_id: self._tinted_pixmap(frame, QColor("#72fff1"))
            for prop_id, frame in self.memory_search_prop_frames.items()
        }
        embedded_mask_dir = ASSET_DIR / "environment" / "memory" / "search_masks"
        self.memory_embedded_search_masks = {
            prop["id"]: QPixmap(str(embedded_mask_dir / f"{prop['id']}.png"))
            for prop in MEMORY_SEARCH_OBJECTS
            if prop.get("embedded")
        }
        self.memory_embedded_search_glows = {
            prop_id: self._tinted_pixmap(mask, QColor("#72fff1"))
            for prop_id, mask in self.memory_embedded_search_masks.items()
        }
        embedded_cutout_dir = ASSET_DIR / "environment" / "memory" / "search_cutouts"
        self.memory_embedded_search_frames = {
            prop["id"]: QPixmap(str(embedded_cutout_dir / f"{prop['id']}.png"))
            for prop in MEMORY_SEARCH_OBJECTS
            if prop.get("embedded")
        }
        embedded_detail_dir = ASSET_DIR / "environment" / "memory" / "search_details"
        self.memory_embedded_search_details = {
            prop["id"]: self._tinted_pixmap(
                QPixmap(str(embedded_detail_dir / f"{prop['id']}.png")),
                QColor("#79fff2"),
            )
            for prop in MEMORY_SEARCH_OBJECTS
            if prop.get("embedded")
        }
        self.archive_activation_marker_atlas = QPixmap(
            str(ASSET_DIR / "archive_activation_marker_state_runtime_v6.png")
        )
        archive_marker_frames = self._uniform_grid_atlas_frames(
            self.archive_activation_marker_atlas, 4, 3
        )
        self.archive_activation_marker_frames = {
            "idle": archive_marker_frames[0:4],
            "proximity": archive_marker_frames[4:8],
            "activation": archive_marker_frames[8:12],
        }
        self.archive_activation_beam_atlas = QPixmap(
            str(ASSET_DIR / "archive_activation_beam_overlay_runtime_v1.png")
        )
        self.archive_activation_beam_frames = self._uniform_grid_atlas_frames(
            self.archive_activation_beam_atlas, 4, 1
        )
        self.chronometer_panel = QPixmap(str(ASSET_DIR / "palimpsest_chronometer_panel_v1.png"))
        self.registry_investigation_panel = QPixmap(
            str(ASSET_DIR / "registry_investigation_panel_v1.png")
        )
        self.registry_visual_clip_frames = {}
        for investigation_id in ORDER_INVESTIGATION_IDS:
            atlas = QPixmap(
                str(ASSET_DIR / f"puzzles/lower_registry_{investigation_id}_clip_atlas_v1.png")
            )
            row_count = 5 if investigation_id == "identity" else 4
            frames = self._grid_atlas_cells(atlas, 4, row_count)
            self.registry_visual_clip_frames[investigation_id] = [
                frames[row * 4:(row + 1) * 4]
                for row in range(row_count)
            ]
        registry_portrait_atlas = QPixmap(
            str(ASSET_DIR / "puzzles/lower_registry_portrait_atlas_v1.png")
        )
        portrait_frames = self._grid_atlas_cells(registry_portrait_atlas, 2, 2)
        self.registry_portraits = {
            character_id: portrait_frames[index]
            for index, character_id in enumerate(
                ("elian_vey", "lysa_marr", "orren_vale", "tomas_rook")
            )
            if index < len(portrait_frames)
        }
        self.registry_activation_marker_atlas = QPixmap(
            str(ASSET_DIR / "environment/order/registry_activation_markers_v1.png")
        )
        registry_marker_frames = self._uniform_grid_atlas_frames(
            self.registry_activation_marker_atlas, 4, 3
        )
        self.registry_activation_marker_frames = {
            investigation_id: registry_marker_frames[index * 4:(index + 1) * 4]
            for index, investigation_id in enumerate(ORDER_INVESTIGATION_IDS)
        }
        self.mercy_reliquary_atlas = QPixmap(
            str(ASSET_DIR / "environment/mercy/appeal_reliquaries_atlas_v1.png")
        )
        mercy_reliquary_cells = self._grid_atlas_cells(self.mercy_reliquary_atlas, 4, 3)
        self.mercy_reliquary_frames = {
            appeal_id: mercy_reliquary_cells[index * 4:(index + 1) * 4]
            for index, appeal_id in enumerate(MERCY_APPEAL_IDS)
        }
        self.mercy_hearing_panel = QPixmap(
            str(ASSET_DIR / "puzzles/mercy_hearing_panel_v1.png")
        )
        mercy_cinematic_atlas = QPixmap(
            str(ASSET_DIR / "environment/mercy/appeal_memory_cinematics_atlas_v2.png")
        )
        mercy_cinematic_cells = self._grid_atlas_cells(mercy_cinematic_atlas, 4, 3)
        self.mercy_cinematic_frames = {
            appeal_id: mercy_cinematic_cells[index * 4:(index + 1) * 4]
            for index, appeal_id in enumerate(MERCY_APPEAL_IDS)
        }
        self.mercy_loom_panel = QPixmap(
            str(ASSET_DIR / "puzzles/mercy_consequence_loom_panel_v2.png")
        )
        mercy_token_atlas = QPixmap(
            str(ASSET_DIR / "puzzles/mercy_consequence_tokens_atlas_v1.png")
        )
        self.mercy_loom_tokens = self._grid_atlas_cells(mercy_token_atlas, 4, 1)
        self.registry_chest_gem = QPixmap(
            str(ASSET_DIR / "quest/icons/registry_chest_gem_v1.png")
        )
        self.registry_shard_atlas = QPixmap(
            str(ASSET_DIR / "quest/icons/registry_shard_atlas_v2.png")
        )
        shard_frames = self._uniform_grid_atlas_frames(self.registry_shard_atlas, 3, 1)
        self.registry_shard_frames = {
            shard_id: shard_frames[index]
            for index, shard_id in enumerate(("west", "east", "south"))
            if index < len(shard_frames)
        }
        self.coupled_registry_panel = QPixmap(
            str(ASSET_DIR / "puzzles/coupled_registry_panel_v3.png")
        )
        self.coupled_registry_rotor_atlas = QPixmap(
            str(ASSET_DIR / "puzzles/coupled_registry_rotor_atlas_v2.png")
        )
        self.coupled_registry_rotors = self._uniform_grid_atlas_frames(
            self.coupled_registry_rotor_atlas, 4, 1
        )
        self.coupled_registry_mechanics_atlas = QPixmap(
            str(ASSET_DIR / "puzzles/coupled_registry_mechanics_v2.png")
        )
        self.coupled_registry_mechanics = self._uniform_grid_atlas_frames(
            self.coupled_registry_mechanics_atlas, 4, 2
        )
        self.coupled_registry_component_atlas = QPixmap(
            str(ASSET_DIR / "puzzles/coupled_registry_component_atlas_v2.png")
        )
        self.coupled_registry_drive_components = self._trimmed_grid_atlas_frames(
            self.coupled_registry_component_atlas, 4, 1
        )
        self.hub_seal_marker_atlas = QPixmap(
            str(ASSET_DIR / "environment/hub/seal_activation_markers_v1.png")
        )
        hub_marker_frames = self._uniform_grid_atlas_frames(
            self.hub_seal_marker_atlas, 4, 3
        )
        self.hub_seal_marker_frames = {
            trial_id: hub_marker_frames[index * 4:(index + 1) * 4]
            for index, trial_id in enumerate(("memory", "mercy", "order"))
        }
        self.chronometer_atlases = {
            "activation": QPixmap(str(ASSET_DIR / "chronometer_activation_atlas_v1.png")),
            "lever_pull": QPixmap(str(ASSET_DIR / "chronometer_lever_pull_atlas_v1.png")),
            "fail": QPixmap(str(ASSET_DIR / "chronometer_failure_atlas_v1.png")),
            "success": QPixmap(str(ASSET_DIR / "chronometer_success_atlas_v1.png")),
        }
        self.chronometer_scroll_atlas = QPixmap(str(ASSET_DIR / "chronometer_scroll_tube_atlas_v2.png"))
        self.chronometer_scroll_frames = self._chronometer_scroll_frames()
        self.chronometer_selector_atlas = QPixmap(str(ASSET_DIR / "chronometer_shape_selector_atlas_v2.png"))
        self.chronometer_glyph_frames = self._load_chronometer_glyph_frames()
        memory_trail_assets = {
            "past": "memory_past_trail_atlas_v1.png",
            "present": "memory_present_trail_atlas_v1.png",
        }
        self.memory_trail_atlases = {
            archive_id: QPixmap(str(ASSET_DIR / asset_name))
            for archive_id, asset_name in memory_trail_assets.items()
        }
        self.memory_trail_frames = {
            archive_id: self._memory_trail_atlas_frames(atlas)
            for archive_id, atlas in self.memory_trail_atlases.items()
        }
        self.memory_future_corruption_atlas = QPixmap(
            str(ASSET_DIR / "memory_future_archivist_corruption_atlas_v1.png")
        )
        corruption_frames = self._trimmed_grid_atlas_frames(
            self.memory_future_corruption_atlas, 4, 4
        )
        self.memory_future_corruption_frames = {
            facing: corruption_frames[row * 4:(row + 1) * 4]
            for row, facing in enumerate(("down", "left", "right", "up"))
        }
        self.memory_future_magnetic_wake_atlas = QPixmap(
            str(ASSET_DIR / "memory_future_magnetic_wake_atlas_v1.png")
        )
        self.memory_future_magnetic_wake_frames = self._memory_trail_atlas_frames(
            self.memory_future_magnetic_wake_atlas
        )
        self.passage_arrow_atlas = QPixmap(str(ASSET_DIR / "passage_arrow_atlas_v1.png"))
        self.passage_arrow_frames = self._passage_arrow_frames()
        self.pending_throne_sheet = QPixmap(str(ASSET_DIR / "cinematics/pending_throne_summon_runtime_sheet.png"))
        self.archivist_confrontation_sheet = QPixmap(str(ASSET_DIR / "cinematics/archivist_confrontation_runtime_sheet.png"))
        self.mara_rescue_sheet = QPixmap(str(ASSET_DIR / "cinematics/mara_rescue_runtime_sheet.png"))
        self.pending_victory_sheet = QPixmap(str(ASSET_DIR / "cinematics/pending_victory_runtime_sheet.png"))
        self.hero_combat = self._load_frame_set("combat/archivist", (
            "ready", "q_slash", "w_ward", "e_mark", "r_redline", "hit",
        ))
        self.pending_combat = self._load_frame_set("combat/pending", (
            "idle_a", "idle_b", "windup", "release", "vortex", "hit", "stagger", "defeat",
        ))
        self.trial_enemies = {
            group: self._load_frame_set(f"combat/{group}", ("idle_a", "idle_b", "attack", "hit"))
            for group in ("red_tape", "misfiled_mimic")
        }
        self.quest_icons = self._load_frame_set("quest/icons", (
            "recall_lens", "appeal_tonic", "reset_compass",
            "memory_shard", "memory_key_fragment", "mercy_sigil", "docket_shard",
            "vault_key_relic_runtime", "pending_codex_runtime",
        ))
        self.combat_icons = self._load_frame_set("combat/icons", (
            "q_slash", "w_ward", "e_mark", "r_redline", "appeal_tonic", "archive_compass",
        ))
        self.keys: set[int] = set()
        self.state = load_game()
        self._ensure_memory_hourglass_locations()
        self._ensure_safe_player_position()
        self.scene = "title"
        self.facing = "down"
        self.walk_frame = 0
        self.walk_clock = 0
        self.player_is_moving = False
        self.idle_ticks = 0
        self.idle_action: str | None = None
        self.idle_action_frame = 0
        self.next_idle_action_at = random.randint(210, 360)
        self.world_clock = 0
        self.dialogue: list[tuple[str, str]] = []
        self.dialogue_index = 0
        self.dialogue_choices: list[tuple[str, str]] = []
        self.dialogue_portraits = False
        self.dialogue_after: str | None = None
        self.dialogue_choice_context = "mara"
        self.dialogue_pose_frames = {"mara": 0, "archivist": 0}
        self.mara_response_history: dict[str, list[str]] = {}
        self.mara_topic_uses: dict[str, int] = {}
        self.cinematic_kind = ""
        self.cinematic_steps: list[tuple[int, int, str, str]] = []
        self.cinematic_index = 0
        self.cinematic_after: str | None = None
        self.active_puzzle: str | None = None
        self.puzzle_sequence: list[str] = []
        self.puzzle_socket_order = list(range(5))
        self.puzzle_selected: int | None = None
        self.active_mercy_appeal: str | None = None
        self.mercy_appeal_selection: str | None = None
        self.mercy_appeal_feedback = ""
        self.mercy_appeal_success = False
        self.mercy_appeal_clip_started = 0
        self.mercy_loom_links = {item["id"]: None for item in MERCY_CONSEQUENCE_LINKS}
        self.mercy_loom_selected: str | None = None
        self.mercy_loom_motion: dict | None = None
        self.mercy_loom_audits_used = 0
        self.mercy_loom_feedback = ""
        self.order_rings = [0, 0, 0, 0]
        self.order_last_rotor: int | None = None
        self.order_rotor_animation: dict | None = None
        self.order_turns_used = 0
        self.hub_seal_activation_effect: dict | None = None
        self.active_order_investigation: str | None = None
        self.order_investigation_variant = 0
        self.order_evidence_focus_index = 0
        self.order_visual_clip_started = 0
        self.order_visual_manual_until = 0
        self.order_sequence: list[str] = []
        self.order_selected_index: int | None = None
        self.order_investigation_feedback = ""
        self.order_feedback_success = False
        self.order_case_file_open = False
        self.order_case_file_section = "people"
        self.order_case_file_scroll = 0
        self.order_station_activation_effect: dict | None = None
        self.mercy_station_activation_effect: dict | None = None
        self.order_hint_levels = {investigation_id: 0 for investigation_id in ORDER_INVESTIGATION_IDS}
        self.mimic_classification = "identity"
        self.mimic_sealed_item: str | None = None
        self.mimic_sealed_item_turns = 0
        self.chronometer_animation = ""
        self.chronometer_animation_started = 0
        self.chronometer_pending_result = ""
        self.chronometer_open_slot: int | None = None
        self.chronometer_scroll_animation = ""
        self.chronometer_scroll_animation_started = 0
        self.chronometer_exchange: dict | None = None
        self.passage_transition: dict | None = None
        self.pending_room_narrative: tuple[str, str] | None = None
        self.memory_active_archive: str | None = None
        self.memory_activation_effect: dict | None = None
        self.memory_restoration_pending: str | None = None
        self.memory_restoration_started = 0
        self.memory_attempt_started_tick = 0
        self.memory_hourglass_location: str | None = None
        self.memory_hourglass_found = False
        self.memory_searched_objects: set[str] = set()
        self.dragged_inventory_item: str | None = None
        self.drag_position = QPointF()
        self.hovered_inventory_item: str | None = None
        self.hovered_passage_marker: str | None = None
        self.hovered_memory_archive: str | None = None
        self.hover_position = QPointF()
        self.title_hover_button: str | None = None
        self.title_click_button: str | None = None
        self.toast = ""
        self.toast_ticks = 0
        self.battle_enemy_id = "pending"
        self.boss_hp = ENEMIES["pending"]["max_hp"]
        self.boss_max_hp = ENEMIES["pending"]["max_hp"]
        self.focus = 0
        self.guard = False
        self.boss_marked = False
        self.battle_message = ""
        self.battle_locked = False
        self.hero_combat_pose = "ready"
        self.pending_pose = "idle_a"
        self.enemy_pose = "idle_a"
        self.ability_cooldowns = {key: 0 for key in ABILITY_ORDER}
        self.last_ability_key = None
        self.foresight = False
        self.bleed_damage = 0
        self.battle_items = {item: 1 for item in ITEM_ORDER}
        self.minions: list[dict] = []
        self.battle_phase = 1
        self.particles: list[dict] = []
        self.memory_motion_effects: list[dict] = []
        self.memory_avatar_history: list[dict] = []
        self.memory_future_echo_event: dict | None = None
        self.memory_future_next_echo_tick = 0
        self.memory_future_corruption_event: dict | None = None
        self.memory_future_next_corruption_tick = 0
        self.memory_echo_frame_cache: dict[tuple[str, str, int], QPixmap] = {}
        self._font_family = self._load_font()
        self._title_font_family = self._load_title_font()
        self._title_caption_font_family = self._load_title_caption_font()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    @staticmethod
    def _load_frame_set(relative_directory: str, names) -> dict[str, QPixmap]:
        directory = ASSET_DIR / relative_directory
        return {name: QPixmap(str(directory / f"{name}.png")) for name in names}

    @staticmethod
    def _trimmed_strip_frames(sheet: QPixmap, count: int) -> list[QPixmap]:
        """Trim transparent gutters while preserving a stable per-frame render box."""
        if sheet.isNull():
            return []
        frames = []
        width = sheet.width() // count
        for index in range(count):
            frame = sheet.copy(index * width, 0, width, sheet.height())
            mask = frame.mask()
            region = QRegion(mask)
            bounds = region.boundingRect()
            frames.append(frame.copy(bounds) if not bounds.isEmpty() else frame)
        return frames

    def _memory_prop_frames(self) -> dict[str, QPixmap]:
        if self.memory_search_props_atlas.isNull():
            return {}
        width = self.memory_search_props_atlas.width()
        height = self.memory_search_props_atlas.height()
        frames = {}
        for prop in MEMORY_SEARCH_OBJECTS:
            if prop.get("embedded"):
                continue
            index = prop["atlas_index"]
            atlas = self.memory_search_props_atlas
            columns = 4
            width, height = atlas.width(), atlas.height()
            column, row = index % columns, index // columns
            left = round(column * width / columns)
            right = round((column + 1) * width / columns)
            top = round(row * height / 2)
            bottom = round((row + 1) * height / 2)
            frames[prop["id"]] = atlas.copy(left, top, right - left, bottom - top)
        return frames

    @staticmethod
    def _trimmed_grid_atlas_frames(
        atlas: QPixmap, columns: int, rows: int
    ) -> list[QPixmap]:
        """Extract a regular atlas and remove transparent cell gutters."""
        if atlas.isNull():
            return []
        frames = []
        for index in range(columns * rows):
            column, row = index % columns, index // columns
            left = round(column * atlas.width() / columns)
            right = round((column + 1) * atlas.width() / columns)
            top = round(row * atlas.height() / rows)
            bottom = round((row + 1) * atlas.height() / rows)
            frame = atlas.copy(left, top, right - left, bottom - top)
            bounds = QRegion(frame.mask()).boundingRect()
            frames.append(frame.copy(bounds) if bounds.isValid() else frame)
        return frames

    @staticmethod
    def _uniform_grid_atlas_frames(
        atlas: QPixmap, columns: int, rows: int
    ) -> list[QPixmap]:
        """Extract frames through one shared crop so scale and pivots stay fixed."""
        if atlas.isNull():
            return []
        cells = []
        shared_bounds = QRect()
        cell_width = atlas.width() // columns
        cell_height = atlas.height() // rows
        for index in range(columns * rows):
            column, row = index % columns, index // columns
            cell = atlas.copy(
                column * cell_width,
                row * cell_height,
                cell_width,
                cell_height,
            )
            cells.append(cell)
            bounds = QRegion(cell.mask()).boundingRect()
            if bounds.isValid():
                shared_bounds = bounds if not shared_bounds.isValid() else shared_bounds.united(bounds)
        if not shared_bounds.isValid():
            return cells
        shared_bounds = shared_bounds.adjusted(-4, -4, 4, 4)
        cell_rect = QRect(0, 0, cells[0].width(), cells[0].height())
        shared_bounds = shared_bounds.intersected(cell_rect)
        return [cell.copy(shared_bounds) for cell in cells]

    @staticmethod
    def _grid_atlas_cells(atlas: QPixmap, columns: int, rows: int) -> list[QPixmap]:
        """Extract complete atlas cells without changing their authored registration."""
        if atlas.isNull():
            return []
        frames = []
        for index in range(columns * rows):
            column, row = index % columns, index // columns
            left = round(column * atlas.width() / columns)
            right = round((column + 1) * atlas.width() / columns)
            top = round(row * atlas.height() / rows)
            bottom = round((row + 1) * atlas.height() / rows)
            frames.append(atlas.copy(left, top, right - left, bottom - top))
        return frames

    @staticmethod
    def _side_walk_atlas_frames(atlas: QPixmap) -> list[QPixmap]:
        """Extract an eight-pose profile cycle through one shared stable crop."""
        if atlas.isNull():
            return []
        return ArchiveboundCanvas._uniform_grid_atlas_frames(atlas, 8, 1)

    @staticmethod
    def _memory_trail_atlas_frames(atlas: QPixmap) -> list[QPixmap]:
        """Extract and alpha-trim an authored 4x2 temporal trail atlas."""
        return ArchiveboundCanvas._trimmed_grid_atlas_frames(atlas, 4, 2)

    def _chronometer_scroll_frames(self) -> list[QPixmap]:
        """Extract the four authored cells without their transparent atlas gutters."""
        if self.chronometer_scroll_atlas.isNull():
            return []
        width = self.chronometer_scroll_atlas.width()
        height = self.chronometer_scroll_atlas.height()
        cell_width = width // 2
        cell_height = height // 2
        content_bounds = (
            QRect(190, 11, 259, 632),
            QRect(135, 2, 309, 641),
            QRect(153, 0, 459, 626),
            QRect(0, 0, 600, 628),
        )
        frames = []
        for index, bounds in enumerate(content_bounds):
            if index == 3:
                # The authored open scroll deliberately overhangs 35 px into the
                # lower-left atlas cell. Extracting a strict quadrant amputates
                # its left finial and rail.
                frames.append(
                    self.chronometer_scroll_atlas.copy(
                        576,
                        cell_height,
                        width - 576,
                        height - cell_height,
                    )
                )
                continue
            cell = self.chronometer_scroll_atlas.copy(
                (index % 2) * cell_width,
                (index // 2) * cell_height,
                cell_width,
                cell_height,
            )
            clipped = bounds.intersected(cell.rect())
            frames.append(cell.copy(clipped))
        return frames

    def _passage_arrow_frames(self) -> list[QPixmap]:
        if self.passage_arrow_atlas.isNull():
            return []
        width = self.passage_arrow_atlas.width()
        height = self.passage_arrow_atlas.height()
        content_bounds = (
            QRect(23, 82, 407, 265), QRect(14, 82, 408, 265),
            QRect(115, 6, 216, 438), QRect(112, 10, 221, 393),
            QRect(18, 75, 412, 272), QRect(15, 75, 411, 273),
            QRect(105, 0, 235, 418), QRect(103, 8, 239, 397),
        )
        frames = []
        for index, bounds in enumerate(content_bounds):
            column, row = index % 4, index // 4
            left, right = round(column * width / 4), round((column + 1) * width / 4)
            top, bottom = round(row * height / 2), round((row + 1) * height / 2)
            cell = self.passage_arrow_atlas.copy(left, top, right - left, bottom - top)
            frames.append(cell.copy(bounds.intersected(cell.rect())))
        return frames

    @staticmethod
    def _tinted_pixmap(source: QPixmap, color: QColor) -> QPixmap:
        if source.isNull():
            return QPixmap()
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def _ensure_memory_hourglass_locations(self) -> bool:
        valid_ids = [item["id"] for item in MEMORY_SEARCH_OBJECTS]
        locations = getattr(self.state, "memory_hourglass_locations", {})
        valid = (
            isinstance(locations, dict)
            and set(locations) == set(MEMORY_SEQUENCE)
            and len(set(locations.values())) == len(MEMORY_SEQUENCE)
            and all(value in valid_ids for value in locations.values())
        )
        if valid:
            return False
        choices = random.sample(valid_ids, len(MEMORY_SEQUENCE))
        self.state.memory_hourglass_locations = dict(zip(MEMORY_SEQUENCE, choices))
        return True

    def _reroll_memory_hourglass_location(self, archive_id: str) -> str:
        """Move a retried hourglass without colliding with the other two relics."""
        self._ensure_memory_hourglass_locations()
        valid_ids = [item["id"] for item in MEMORY_SEARCH_OBJECTS]
        previous = self.state.memory_hourglass_locations.get(archive_id)
        occupied = {
            location
            for key, location in self.state.memory_hourglass_locations.items()
            if key != archive_id
        }
        choices = [item for item in valid_ids if item != previous and item not in occupied]
        if not choices:
            choices = [item for item in valid_ids if item != previous]
        location = random.choice(choices)
        self.state.memory_hourglass_locations[archive_id] = location
        save_game(self.state)
        return location

    @staticmethod
    def _load_font() -> str:
        candidates = (
            ASSET_DIR / "PressStart2P-Regular.ttf",
            Path(resource_path("assets/fonts/Kastelov - Axiforma ExtraBold.otf")),
        )
        for path in candidates:
            if path.exists():
                font_id = QFontDatabase.addApplicationFont(str(path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        return "Consolas"

    @staticmethod
    def _load_title_font() -> str:
        path = Path(resource_path("assets/fonts/DarkReborn-Regular.ttf"))
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
        return "Consolas"

    @staticmethod
    def _load_title_caption_font() -> str:
        path = Path(resource_path("assets/fonts/Firlest-Regular.otf"))
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
        return "Consolas"

    def persist(self):
        save_game(self.state)

    def _has_story_flag(self, flag: str) -> bool:
        return flag in self.state.narrative_flags

    def _mark_story_flag(self, flag: str, *, persist: bool = True) -> None:
        if flag not in self.state.narrative_flags:
            self.state.narrative_flags.append(flag)
            if persist:
                save_game(self.state)

    def _record_response_tendency(self, tendency: str) -> None:
        self.state.response_tendencies[tendency] = self.state.response_tendencies.get(tendency, 0) + 1
        save_game(self.state)

    def start_game(self, fresh: bool = False):
        self.memory_activation_effect = None
        self.hub_seal_activation_effect = None
        if fresh:
            previous_reward = self.state.reward_claimed
            self.state = ArchiveboundState(reward_claimed=previous_reward)
            self.memory_restoration_pending = None
            self.memory_restoration_started = 0
        self._ensure_memory_hourglass_locations()
        self.scene = "explore"
        if not self._has_story_flag("opening_seen"):
            self.state.clerk_met = True
            self.show_dialogue(list(OPENING_DIALOGUE), portraits=True, after="opening_choice")
        elif self.state.current_room in {"memory", "mercy", "order"}:
            self._maybe_start_room_narrative("hub", self.state.current_room)
        save_game(self.state)
        self.setFocus()

    def _hall_is_unlocked(self, room_id: str) -> bool:
        """Return whether the next chapter is available in the authored order."""
        if room_id not in HALL_PREREQUISITES:
            return True
        if room_id in self.state.completed_trials:
            return True
        if room_id == "memory":
            return "onboarding_complete" in getattr(self.state, "narrative_flags", [])
        previous = HALL_PREREQUISITES[room_id]
        return (
            previous in self.state.completed_trials
            and previous in self.state.completed_seal_puzzles
        )

    def _next_story_hall(self) -> str | None:
        for room_id in HALL_SEQUENCE:
            if room_id not in self.state.completed_trials:
                return room_id
            if room_id not in self.state.completed_seal_puzzles:
                return None
        return None

    def _hall_lock_message(self, room_id: str) -> str:
        if "onboarding_complete" not in getattr(self.state, "narrative_flags", []):
            return "Mara is still waiting. Learn the Hall's first two rules before choosing a door."
        previous = HALL_PREREQUISITES.get(room_id)
        if room_id == "mercy":
            if previous not in self.state.completed_trials:
                return "The Mercy passage stays dark. The Hall will not weigh a life whose memory is still missing."
            return "The Mercy passage is listening, but the Seal of Memory still holds the door shut."
        if room_id == "order":
            if previous not in self.state.completed_trials:
                return "The Registry refuses you. It will not impose order before you have heard what order costs."
            return "The Registry stair remains sealed until the Seal of Mercy accepts your judgment."
        return "That passage is not ready to remember you yet."

    def tick(self):
        self.world_clock += 1
        if self.memory_active_archive and self.scene != "explore":
            # Search dialogue should not quietly consume the player's timed trial.
            self.memory_attempt_started_tick += 1
        self._tick_chronometer_animation()
        self._tick_chronometer_scroll_animation()
        self._tick_chronometer_exchange()
        self._tick_order_rotor_animation()
        self._tick_mercy_loom_motion()
        if self.toast_ticks > 0:
            self.toast_ticks -= 1
        if self.scene == "explore":
            if self.hub_seal_activation_effect:
                self._tick_hub_seal_activation()
                self._update_particles()
                self.update()
                return
            if self.order_station_activation_effect:
                self._tick_order_station_activation()
                self._update_particles()
                self.update()
                return
            if self.mercy_station_activation_effect:
                self._tick_mercy_station_activation()
                self._update_particles()
                self.update()
                return
            if self.memory_activation_effect:
                # Hold movement and the challenge clock while the selected
                # floor rune visibly locks into its Archive.
                self.memory_attempt_started_tick += 1
                self._tick_memory_activation_effect()
                self._update_particles()
                self.update()
                return
            if self.memory_restoration_pending:
                self._tick_memory_restoration()
                self._update_particles()
                self.update()
                return
            if self.passage_transition:
                self._tick_passage_transition()
                self._update_particles()
                self._update_memory_motion_effects()
                self.update()
                return
            self._resolve_player_penetration()
            self._move_player()
            self._tick_memory_attempt()
            self._check_room_transition()
            self._check_enemy_proximity()
        elif self.scene == "battle":
            self._update_battle_idle_pose()
        self._update_particles()
        self._update_memory_motion_effects()
        self.update()

    def _move_player(self):
        dx = int(Qt.Key_Right in self.keys) - int(Qt.Key_Left in self.keys)
        dy = int(Qt.Key_Down in self.keys) - int(Qt.Key_Up in self.keys)
        if not dx and not dy:
            self.player_is_moving = False
            self.walk_frame = (self.world_clock // 30) % 2
            if not hasattr(self, "idle_ticks"):
                self.idle_ticks = 0
                self.idle_action = None
                self.idle_action_frame = 0
                self.next_idle_action_at = 300
            ArchiveboundCanvas._advance_player_idle(self)
            return
        self.player_is_moving = True
        self.idle_ticks = 0
        self.idle_action = None
        previous_x = self.state.player_x
        previous_y = self.state.player_y
        previous_facing = self.facing
        previous_walk_frame = self.walk_frame
        length = math.sqrt(dx * dx + dy * dy)
        speed = 4.0
        memory_archive = getattr(self, "memory_active_archive", None)
        if self.state.current_room == "memory" and memory_archive:
            movement = MEMORY_ARCHIVE_RULES[memory_archive]["movement"]
            if movement == "reversed":
                dx, dy = -dx, -dy
            elif movement == "accelerated":
                speed = 7.25
            elif movement == "slowed":
                speed = 1.75
        next_x = self.state.player_x + speed * dx / length
        next_y = self.state.player_y + speed * dy / length
        if self._can_walk(next_x, self.state.player_y):
            self.state.player_x = next_x
        if self._can_walk(self.state.player_x, next_y):
            self.state.player_y = next_y
        moved = (
            abs(self.state.player_x - previous_x) > 0.01
            or abs(self.state.player_y - previous_y) > 0.01
        )
        if (
            moved
            and "movement_tutorial_started" in getattr(self.state, "narrative_flags", [])
            and "movement_tutorial_complete" not in getattr(self.state, "narrative_flags", [])
            and hasattr(self, "_mark_story_flag")
        ):
            self._mark_story_flag("movement_tutorial_complete")
            self._toast("Good. Now walk to Mara and press Space to speak.")
        if dy < 0:
            self.facing = "up"
        elif dy > 0:
            self.facing = "down"
        elif dx < 0:
            self.facing = "left"
        elif dx > 0:
            self.facing = "right"
        self.walk_clock += 1
        if self.walk_clock % 4 == 0:
            frame_count = 8 if self.facing in ("left", "right") else 4
            self.walk_frame = (self.walk_frame + 1) % frame_count
        if memory_archive and (
            abs(self.state.player_x - previous_x) > 0.01
            or abs(self.state.player_y - previous_y) > 0.01
        ):
            self.memory_avatar_history.append({
                "archive": memory_archive,
                "x": previous_x,
                "y": previous_y,
                "facing": previous_facing,
                "frame": previous_walk_frame,
                "life": {"past": 10, "present": 13, "future": 18}[memory_archive],
                "max": {"past": 10, "present": 13, "future": 18}[memory_archive],
            })
            self.memory_avatar_history = self.memory_avatar_history[-16:]
            self._emit_memory_motion_effects(
                memory_archive,
                previous_x,
                previous_y,
                self.state.player_x - previous_x,
                self.state.player_y - previous_y,
            )

    def _emit_memory_motion_effects(
        self,
        archive_id: str,
        x: float,
        y: float,
        move_x: float,
        move_y: float,
    ) -> None:
        """Emit archive-specific movement feedback without changing movement physics."""
        if archive_id == "past" and self.world_clock % 2 == 0:
            self.memory_motion_effects.append({
                "kind": "rewind_mote",
                "archive": archive_id,
                "x": x + random.uniform(-28, 28),
                "y": y - random.uniform(18, 78),
                "vx": move_x * random.uniform(0.2, 0.45),
                "vy": move_y * random.uniform(0.2, 0.45),
                "life": random.randint(18, 28),
                "max": 28,
                "size": random.uniform(2.0, 4.5),
            })
        elif archive_id == "future" and self.world_clock % 4 == 0:
            self.memory_motion_effects.append({
                "kind": "suspended_mote",
                "archive": archive_id,
                "x": x + random.uniform(-30, 30),
                "y": y - random.uniform(16, 82),
                "vx": random.uniform(-0.08, 0.08),
                "vy": random.uniform(-0.12, 0.03),
                "life": random.randint(34, 52),
                "max": 52,
                "size": random.uniform(2.5, 5.0),
                "phase": random.random() * math.tau,
            })
        if archive_id == "future":
            if self.world_clock >= self.memory_future_next_echo_tick:
                self._start_future_echo_event(move_x, move_y)
            elif (
                not self.memory_future_echo_event
                and not self.memory_future_corruption_event
                and self.world_clock >= self.memory_future_next_corruption_tick
            ):
                self._start_future_corruption_event()

        # Prevent an unusually long challenge from accumulating stale VFX.
        if len(self.memory_motion_effects) > 90:
            self.memory_motion_effects = self.memory_motion_effects[-90:]

    def _update_memory_motion_effects(self) -> None:
        alive = []
        for effect in self.memory_motion_effects:
            effect["life"] -= 1
            if effect["life"] <= 0:
                continue
            effect["x"] += effect.get("vx", 0.0)
            effect["y"] += effect.get("vy", 0.0)
            if effect["kind"] == "suspended_mote":
                effect["x"] += math.sin(self.world_clock / 6 + effect["phase"]) * 0.12
            alive.append(effect)
        self.memory_motion_effects = alive
        history = []
        for snapshot in self.memory_avatar_history:
            snapshot["life"] -= 1
            if snapshot["life"] > 0:
                history.append(snapshot)
        self.memory_avatar_history = history
        event = self.memory_future_echo_event
        if event and self.world_clock >= event["started"] + event["duration"]:
            self.memory_future_echo_event = None
        corruption = self.memory_future_corruption_event
        if corruption and self.world_clock >= corruption["started"] + corruption["duration"]:
            self.memory_future_corruption_event = None

    def _start_future_corruption_event(self) -> None:
        """Briefly let the Future Archive corrupt the real Archivist."""
        duration = random.randint(14, 20)
        self.memory_future_corruption_event = {
            "started": self.world_clock,
            "duration": duration,
        }
        self.memory_future_next_corruption_tick = (
            self.world_clock + duration + random.randint(28, 70)
        )

    def _start_future_echo_event(self, _move_x: float, _move_y: float) -> None:
        """Stage a sparse cluster of divergent futures around the moving hero."""
        # The large capture event replaces the quieter personal corruption so
        # the two readable beats never compete for the same silhouette.
        self.memory_future_corruption_event = None
        duration = random.randint(24, 38)
        roll = random.random()
        echo_count = 3 if roll < 0.12 else 2 if roll < 0.48 else 1
        placements = []
        forward_x, forward_y = {
            "up": (0.0, -1.0), "down": (0.0, 1.0),
            "left": (-1.0, 0.0), "right": (1.0, 0.0),
        }[self.facing]
        direction_names = {
            (0.0, -1.0): "north", (0.0, 1.0): "south",
            (-1.0, 0.0): "west", (1.0, 0.0): "east",
        }
        # A possible future should disagree with the real one: it may turn
        # back or branch ninety degrees, but never continue straight ahead.
        branch_vectors = [
            (-forward_x, -forward_y),
            (-forward_y, forward_x),
            (forward_y, -forward_x),
        ]
        random.shuffle(branch_vectors)
        facings = ("up", "down", "left", "right")
        for index in range(echo_count):
            offset_x, offset_y = branch_vectors[index]
            direction_name = direction_names[(offset_x, offset_y)]
            distance = random.uniform(44.0, 72.0)
            placements.append({
                "x": self.state.player_x + offset_x * distance,
                "y": self.state.player_y + offset_y * distance,
                "axis_x": offset_x,
                "axis_y": offset_y,
                "direction": direction_name,
                "facing": random.choice(facings),
                "frame": random.randint(0, 7),
                "cadence": random.choice((3, 4, 5)),
                "motion_span": random.uniform(5.0, 11.0),
                "seed": random.randint(0, 10000),
            })
        self.memory_future_echo_event = {
            "started": self.world_clock,
            "duration": duration,
            "echoes": placements,
            "facing": self.facing,
        }
        silence = random.randint(48, 105)
        if random.random() < 0.18:
            silence += random.randint(36, 72)
        self.memory_future_next_echo_tick = self.world_clock + duration + silence
        self.memory_future_next_corruption_tick = (
            self.world_clock + duration + random.randint(18, 42)
        )

    def _advance_player_idle(self):
        """Keep breathing dominant and punctuate it with rare authored actions."""
        self.idle_ticks += 1
        actions = {
            "watch": (4, 5, 5, 4),
            "bag": (6, 7, 7, 6),
            "book": (8, 9, 9, 8),
            "impatient": (10, 11, 11, 10),
        }
        if self.idle_action:
            frames = actions[self.idle_action]
            self.idle_action_frame += 1
            if self.idle_action_frame >= len(frames) * 12:
                self.idle_action = None
                self.idle_action_frame = 0
                self.idle_ticks = 0
                self.next_idle_action_at = random.randint(240, 420)
            return
        if self.idle_ticks >= self.next_idle_action_at:
            self.idle_action = random.choice(tuple(actions))
            self.idle_action_frame = 0

    def _player_idle_frame(self) -> int:
        if self.idle_action:
            frames = {
                "watch": (4, 5, 5, 4),
                "bag": (6, 7, 7, 6),
                "book": (8, 9, 9, 8),
                "impatient": (10, 11, 11, 10),
            }[self.idle_action]
            return frames[min(len(frames) - 1, self.idle_action_frame // 12)]
        breathing = (0, 1, 2, 3, 2, 1)
        return breathing[(self.idle_ticks // 10) % len(breathing)]

    def _can_walk(self, x: float, y: float) -> bool:
        point = QPointF(x, y)
        navigation = ROOM_NAVIGATION[self.state.current_room]
        if not any(QRectF(*area).contains(point) for area in navigation["walk_areas"]):
            return False
        for blocker in self._active_blockers():
            shape = blocker["shape"]
            if shape == "circle":
                radius = blocker["radius"] + self.PLAYER_FOOT_RADIUS
                if self._distance((x, y), blocker["center"]) < radius:
                    return False
            elif shape == "ellipse":
                center_x, center_y = blocker["center"]
                radius_x, radius_y = blocker["radii"]
                radius_x += self.PLAYER_FOOT_RADIUS
                radius_y += self.PLAYER_FOOT_RADIUS
                if ((x - center_x) / radius_x) ** 2 + ((y - center_y) / radius_y) ** 2 < 1:
                    return False
            elif shape == "polygon":
                polygon = QPolygonF([QPointF(*vertex) for vertex in blocker["points"]])
                if polygon.containsPoint(point, Qt.OddEvenFill):
                    return False
                vertices = blocker["points"]
                for index, start in enumerate(vertices):
                    end = vertices[(index + 1) % len(vertices)]
                    if ArchiveboundCanvas._distance_to_segment((x, y), start, end) < self.PLAYER_FOOT_RADIUS:
                        return False
            else:
                radius = self.PLAYER_FOOT_RADIUS
                if QRectF(*blocker["rect"]).adjusted(-radius, -radius, radius, radius).contains(point):
                    return False
        return True

    @staticmethod
    def _distance_to_segment(point, start, end) -> float:
        px, py = point
        ax, ay = start
        bx, by = end
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return math.dist(point, start)
        projection = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared))
        return math.hypot(px - (ax + projection * dx), py - (ay + projection * dy))

    def _active_blockers(self):
        blockers = list(ROOM_NAVIGATION[self.state.current_room]["blockers"])
        if self.state.current_room == "order" and "misfiled_mimic" in self.state.defeated_enemies:
            blockers = [blocker for blocker in blockers if blocker.get("id") != "mimic_chest"]
        if self.state.current_room == "hub":
            blockers.append({"shape": "circle", "center": CLERK_POSITION, "radius": 22})
        elif self.state.current_room == "mercy":
            enemy_id = ArchiveboundCanvas._active_mercy_enemy_id(self)
            if enemy_id:
                blockers.append({"shape": "circle", "center": ENEMIES[enemy_id]["position"], "radius": 58})
        return blockers

    def _ensure_safe_player_position(self):
        point = QPointF(self.state.player_x, self.state.player_y)
        inside_exit = any(
            QRectF(*exit_spec["trigger"]).contains(point)
            for exit_spec in ROOM_EXITS[self.state.current_room]
        )
        if inside_exit:
            self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS[self.state.current_room]
        elif not self._can_walk(self.state.player_x, self.state.player_y):
            self._resolve_player_penetration()

    def _resolve_player_penetration(self) -> None:
        """Push stale or migrated coordinates to the nearest legal floor point."""
        if self._can_walk(self.state.player_x, self.state.player_y):
            return
        origin_x, origin_y = self.state.player_x, self.state.player_y
        for radius in range(4, 129, 4):
            for step in range(32):
                angle = math.tau * step / 32
                candidate_x = origin_x + math.cos(angle) * radius
                candidate_y = origin_y + math.sin(angle) * radius
                if self._can_walk(candidate_x, candidate_y):
                    self.state.player_x = candidate_x
                    self.state.player_y = candidate_y
                    self.keys.clear()
                    return
        self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS[self.state.current_room]
        self.keys.clear()

    def _check_room_transition(self):
        point = QPointF(self.state.player_x, self.state.player_y)
        for exit_spec in ROOM_EXITS[self.state.current_room]:
            if QRectF(*exit_spec["trigger"]).contains(point):
                destination = exit_spec["room"]
                if (
                    self.state.current_room == "hub"
                    and not ArchiveboundCanvas._hall_is_unlocked(self, destination)
                ):
                    self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS["hub"]
                    self.keys.clear()
                    self._toast(ArchiveboundCanvas._hall_lock_message(self, destination))
                    return
                if self.state.current_room == "memory":
                    if len(self.state.memory_archives_completed) < len(MEMORY_SEQUENCE):
                        self.state.player_x = 905
                        self.state.player_y = 320
                        self.keys.clear()
                        self._toast("The return passage is sealed. Restore all three Archives to leave.")
                        return
                    self._cancel_memory_attempt()
                if self.state.current_room == "order" and "order" not in self.state.completed_trials:
                    self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS["order"]
                    self.keys.clear()
                    self._toast(
                        "The Registry stair has sealed behind you. Restore Docket VII-13 and survive what it contains before leaving."
                    )
                    return
                if self.state.current_room == "mercy" and "mercy" not in self.state.completed_trials:
                    self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS["mercy"]
                    self.keys.clear()
                    self._toast(
                        "The return passage is sealed. Finish the three appeals and expose the hidden claimant."
                    )
                    return
                if hasattr(self, "passage_transition"):
                    self._begin_passage_transition(exit_spec)
                else:
                    ArchiveboundCanvas._commit_room_transition(self, exit_spec)
                return

    def _commit_room_transition(self, exit_spec: dict) -> None:
        previous_room = self.state.current_room
        self.state.current_room = exit_spec["room"]
        self.state.player_x, self.state.player_y = exit_spec["spawn"]
        self.facing = exit_spec["facing"]
        self.keys.clear()
        save_game(self.state)
        self._toast(f"Entered {ROOMS[self.state.current_room]['name']}.")
        if hasattr(self, "pending_room_narrative"):
            self.pending_room_narrative = (previous_room, self.state.current_room)

    @staticmethod
    def _passage_direction_from_trigger(trigger: tuple[int, int, int, int]) -> str:
        x, y, width, height = trigger
        if x <= 1:
            return "left"
        if x + width >= GAME_WIDTH - 1:
            return "right"
        if y <= 1:
            return "up"
        return "down"

    @staticmethod
    def _passage_entry_direction(spawn: tuple[float, float]) -> str:
        x, y = spawn
        if x < 140:
            return "right"
        if x > GAME_WIDTH - 140:
            return "left"
        if y < 230:
            return "down"
        return "up"

    @staticmethod
    def _direction_vector(direction: str) -> tuple[float, float]:
        return {
            "left": (-1.0, 0.0),
            "right": (1.0, 0.0),
            "up": (0.0, -1.0),
            "down": (0.0, 1.0),
        }[direction]

    def _begin_passage_transition(self, exit_spec: dict) -> None:
        direction = self._passage_direction_from_trigger(exit_spec["trigger"])
        self.keys.clear()
        self.player_is_moving = True
        self.facing = direction
        self.passage_transition = {
            "phase": "exit",
            "started": self.world_clock,
            "duration": 10,
            "exit_spec": exit_spec,
            "start": (self.state.player_x, self.state.player_y),
            "direction": direction,
        }

    def _tick_passage_transition(self) -> None:
        transition = self.passage_transition
        if not transition:
            return
        age = self.world_clock - transition["started"]
        self.walk_frame = (age // 2) % 4
        if age < transition["duration"]:
            return
        if transition["phase"] == "exit":
            exit_spec = transition["exit_spec"]
            self._commit_room_transition(exit_spec)
            direction = self._passage_entry_direction(exit_spec["spawn"])
            dx, dy = self._direction_vector(direction)
            spawn_x, spawn_y = exit_spec["spawn"]
            self.facing = direction
            self.passage_transition = {
                "phase": "enter",
                "started": self.world_clock,
                "duration": 10,
                "exit_spec": exit_spec,
                "start": (spawn_x - dx * 76, spawn_y - dy * 76),
                "end": (spawn_x, spawn_y),
                "direction": direction,
            }
            return
        self.passage_transition = None
        self.player_is_moving = False
        self.walk_frame = 0
        pending = self.pending_room_narrative
        self.pending_room_narrative = None
        if pending:
            self._maybe_start_room_narrative(*pending)

    def _maybe_start_room_narrative(self, previous_room: str, room_id: str) -> None:
        if room_id == "hub" and previous_room in {"memory", "mercy", "order"}:
            self._maybe_start_hub_interlude(previous_room)
            return
        flag = f"{room_id}_threshold_seen"
        if room_id not in {"memory", "mercy", "order"} or self._has_story_flag(flag):
            return
        self._mark_story_flag(flag)
        self.show_dialogue(list(ROOM_INTROS[room_id]), portraits=True)

    def _maybe_start_hub_interlude(self, previous_room: str) -> None:
        count = min(3, len(self.state.completed_trials))
        if count <= 0:
            return
        flag = f"hub_interlude_{count}_seen"
        if self._has_story_flag(flag):
            return
        self._mark_story_flag(flag)
        relic_name = TRIAL_REWARDS.get(previous_room, {}).get("label", "relic")
        if count == 1:
            self.show_choices(
                "MARA",
                "There you are. I was about to come after you, which would have been difficult and embarrassing.",
                [
                    ("vulnerable", "Were you worried about me?"),
                    ("practical", f"Tell me what the {relic_name} does."),
                    ("humorous", "I knew you would miss me."),
                ],
                context="interlude_1",
            )
        elif count == 2:
            self.show_dialogue([
                ("MARA", "Here. Before you ask, it is only tea."),
                ("LAST CLERK", "What is it?"),
                ("MARA", "I just told you."),
                ("LAST CLERK", "You said 'only.' That made it suspicious."),
                ("MARA", "Lysa Marr taught me the recipe. She stole it from a records banquet."),
                ("LAST CLERK", "You smiled when you said her name."),
                ("MARA", "She also stole six sugared pears. Drink your tea."),
            ], portraits=True)
        else:
            self.show_dialogue([
                ("MARA", "Sit down."),
                ("LAST CLERK", "I am fine."),
                ("MARA", "You are bleeding on a six-hundred-year-old rug."),
                ("LAST CLERK", "You felt the blow, did you not?"),
                ("MARA", "Before the lantern carried your voice."),
                ("LAST CLERK", "Has that happened before?"),
                ("MARA", "No. And I would like one minute in which that is not the worst answer available."),
            ], portraits=True)

    def _passage_transition_render_state(self) -> tuple[float, float, float]:
        transition = self.passage_transition
        if not transition:
            return self.state.player_x, self.state.player_y, 1.0
        progress = min(1.0, max(0.0, (self.world_clock - transition["started"]) / transition["duration"]))
        eased = progress * progress * (3 - 2 * progress)
        if transition["phase"] == "exit":
            start_x, start_y = transition["start"]
            dx, dy = self._direction_vector(transition["direction"])
            return start_x + dx * 76 * eased, start_y + dy * 76 * eased, 1.0 - 0.82 * eased
        start_x, start_y = transition["start"]
        end_x, end_y = transition["end"]
        return (
            start_x + (end_x - start_x) * eased,
            start_y + (end_y - start_y) * eased,
            0.18 + 0.82 * eased,
        )

    def _check_enemy_proximity(self):
        """Start hostile encounters when an alert enemy can reach the player."""
        enemy_id = None
        if self.state.current_room == "mercy":
            enemy_id = self._active_mercy_enemy_id()
        if enemy_id is None:
            return
        enemy = ENEMIES[enemy_id]
        if self._distance((self.state.player_x, self.state.player_y), enemy["position"]) <= 128:
            self.keys.clear()
            self.start_battle(enemy_id)

    def _active_mercy_enemy_id(self) -> str | None:
        defeated = getattr(self.state, "defeated_enemies", [])
        if self.state.mercy_hearing_completed and "red_tape_wraith" not in defeated:
            return "red_tape_wraith"
        return None

    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        key = event.key()
        self.keys.add(key)
        if self.scene == "title":
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self.start_game(False)
        elif self.scene == "dialogue":
            if self.dialogue_choices and Qt.Key_1 <= key <= Qt.Key_9:
                self._choose_dialogue(key - Qt.Key_1)
            elif not self.dialogue_choices and key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self.advance_dialogue()
        elif self.scene == "cinematic" and key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._advance_cinematic()
        elif self.scene == "seal_puzzle" and key == Qt.Key_Escape:
            self.scene = "explore"
        elif self.scene == "order_investigation" and key == Qt.Key_Escape:
            if self.order_case_file_open:
                self.order_case_file_open = False
            else:
                self.scene = "explore"
                self.active_order_investigation = None
            self.keys.discard(key)
            self.update()
            return
        elif self.scene == "mercy_appeal" and key == Qt.Key_Escape:
            self.scene = "explore"
            self.active_mercy_appeal = None
            self.keys.discard(key)
            self.update()
            return
        elif self.scene == "explore" and key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.interact()
        elif self.scene == "battle" and not self.battle_locked:
            ability_keys = {
                Qt.Key_Q: "Q", Qt.Key_W: "W", Qt.Key_E: "E", Qt.Key_R: "R",
            }
            item_keys = {
                Qt.Key_1: "appeal_tonic",
                Qt.Key_2: "reset_compass",
                Qt.Key_3: "recall_lens",
            }
            if key in ability_keys:
                self.battle_action(ability_keys[key])
            elif key in item_keys:
                self.use_battle_item(item_keys[key])
        elif self.scene == "ending" and key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.scene = "explore"
        if key == Qt.Key_H and self.scene == "explore":
            self._toggle_exploration_hud()
        elif key == Qt.Key_Escape and self.scene != "seal_puzzle":
            self.window().close()

    def keyReleaseEvent(self, event: QKeyEvent):
        if not event.isAutoRepeat():
            self.keys.discard(event.key())

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point = event.pos()
        if self.scene == "title":
            if TITLE_CONTINUE_RECT.contains(point):
                self._press_title_button("continue")
            elif TITLE_NEW_GAME_RECT.contains(point):
                self._press_title_button("new_game")
        elif self.scene == "dialogue":
            if self.dialogue_choices:
                for index, rect in enumerate(self._dialogue_choice_rects()):
                    if rect.contains(point):
                        self._choose_dialogue(index)
                        return
            else:
                self.advance_dialogue()
        elif self.scene == "cinematic":
            self._advance_cinematic()
        elif self.scene == "seal_puzzle":
            self._handle_puzzle_click(point)
        elif self.scene == "order_investigation":
            self._handle_order_investigation_click(point)
        elif self.scene == "mercy_appeal":
            self._handle_mercy_appeal_click(point)
        elif self.scene == "explore":
            if self.state.current_room == "memory" and self._handle_memory_world_click(point):
                return
            if self.state.current_room == "hub" and self._vault_keyhole_rect().contains(point):
                self._activate_vault_keyhole()
                return
            if self._hud_toggle_rect().contains(point):
                self._toggle_exploration_hud()
                return
            if not self.state.hud_collapsed:
                for item, rect in self._explore_item_rects().items():
                    if rect.contains(point):
                        self.dragged_inventory_item = item
                        self.drag_position = QPointF(point)
                        return
        elif self.scene == "battle" and not self.battle_locked:
            for key, rect in self._ability_rects().items():
                if rect.contains(point):
                    self.battle_action(key)
                    return
            for item, rect in self._item_rects().items():
                if rect.contains(point):
                    self.use_battle_item(item)
                    break
        elif self.scene == "ending":
            self.scene = "explore"

    def mouseMoveEvent(self, event):
        self.hover_position = QPointF(event.pos())
        if self.scene == "title":
            if TITLE_CONTINUE_RECT.contains(event.pos()):
                hovered = "continue"
            elif TITLE_NEW_GAME_RECT.contains(event.pos()):
                hovered = "new_game"
            else:
                hovered = None
            self.title_hover_button = hovered
            self.setCursor(Qt.PointingHandCursor if hovered else Qt.ArrowCursor)
            self.update()
            return
        self.title_hover_button = None
        self.setCursor(Qt.ArrowCursor)
        self.hovered_inventory_item = None
        self.hovered_passage_marker = None
        self.hovered_memory_archive = None
        if self.scene == "explore":
            for marker in self._passage_marker_specs():
                if marker["rect"].contains(event.pos()):
                    self.hovered_passage_marker = marker["id"]
                    break
            if self.state.current_room == "memory":
                for archive_id in MEMORY_SEQUENCE:
                    if self._memory_archive_rect(archive_id).contains(event.pos()):
                        self.hovered_memory_archive = archive_id
                        break
        if self.scene == "explore" and not self.state.hud_collapsed:
            for item, rect in self._explore_item_rects().items():
                if rect.contains(event.pos()):
                    self.hovered_inventory_item = item
                    break
        if self.dragged_inventory_item:
            self.drag_position = QPointF(event.pos())
        self.update()

    def leaveEvent(self, event):
        if self.title_hover_button is not None:
            self.title_hover_button = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def _press_title_button(self, action: str) -> None:
        """Give a menu control enough time to show its authored press state."""
        if self.title_click_button is not None:
            return
        self.title_click_button = action
        self.update()
        QTimer.singleShot(100, lambda choice=action: self._finish_title_button_press(choice))

    def _finish_title_button_press(self, action: str) -> None:
        if self.title_click_button != action:
            return
        self.title_click_button = None
        self.start_game(action == "new_game")

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragged_inventory_item:
            return
        source = self.dragged_inventory_item
        self.dragged_inventory_item = None
        source_rect = self._explore_item_rects().get(source)
        if source == "registry_chest_gem":
            if self.state.current_room == "order" and self._order_chest_lock_drop_rect().contains(event.pos()):
                self._unlock_registry_chest()
            else:
                self._toast("The Master Docket Gem belongs in the matching trefoil socket on the central chest.")
            self.update()
            return
        if source.startswith("hourglass_"):
            archive_id = source.removeprefix("hourglass_")
            if self._memory_archive_drop_rect(archive_id).contains(event.pos()):
                self._complete_memory_archive(archive_id)
            else:
                self._toast("That hourglass belongs in its matching Archive mechanism.")
            self.update()
            return
        if source == "pending_codex" and source_rect and source_rect.contains(event.pos()):
            self.show_dialogue([
                ("CODEX OF THE UNCLOSED", "The first page names a deeper registry beneath the Archive: THE COURT OF ERASED NAMES."),
                ("MARA", "Level Two, apparently. Because one cursed bureaucracy would have lacked ambition."),
            ], portraits=True)
            return
        if (
            source == "vault_key"
            and self.state.current_room == "hub"
            and self._vault_keyhole_drop_rect().contains(event.pos())
        ):
            self.state.vault_key_inserted = True
            save_game(self.state)
            self._burst(VAULT_POSITION, QColor("#f5d276"), 48)
            self._toast("THE KEY HAS TAKEN ROOT. CLICK THE LOCK.")
            self.update()
            return
        for target, rect in self._explore_item_rects().items():
            if target != source and rect.contains(event.pos()):
                if source.startswith("registry_") or target.startswith("registry_"):
                    self._try_fuse_registry_shards(source, target)
                else:
                    self._try_fuse_key_items(source, target)
                break
        self.update()

    def wheelEvent(self, event):
        if self.scene == "order_investigation" and self.order_case_file_open:
            step = -52 if event.angleDelta().y() > 0 else 52
            self.order_case_file_scroll = max(0, min(self._order_case_file_max_scroll(), self.order_case_file_scroll + step))
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def show_dialogue(self, lines: list[tuple[str, str]], portraits: bool = False, after: str | None = None):
        self.dialogue = lines
        self.dialogue_index = 0
        self.dialogue_choices = []
        self.dialogue_portraits = portraits
        self.dialogue_after = after
        self.dialogue_choice_context = "mara"
        self.scene = "dialogue"
        self._advance_dialogue_pose()

    def show_choices(
        self,
        speaker: str,
        text: str,
        choices: list[tuple[str, str]],
        *,
        context: str = "mara",
    ):
        self.dialogue = [(speaker, text)]
        self.dialogue_index = 0
        self.dialogue_choices = choices
        self.dialogue_portraits = True
        self.dialogue_after = None
        self.dialogue_choice_context = context
        self.scene = "dialogue"
        self._advance_dialogue_pose()

    def advance_dialogue(self):
        self.dialogue_index += 1
        if self.dialogue_index >= len(self.dialogue):
            after = self.dialogue_after
            self.dialogue = []
            self.dialogue_choices = []
            self.dialogue_portraits = False
            self.dialogue_after = None
            self.scene = "explore"
            self._run_dialogue_after(after)
        else:
            self._advance_dialogue_pose()
        self.update()

    def _choose_dialogue(self, index: int):
        if not 0 <= index < len(self.dialogue_choices):
            return
        choice_id, _ = self.dialogue_choices[index]
        self.dialogue_choices = []
        context = self.dialogue_choice_context
        if context == "opening":
            self._handle_opening_choice(choice_id)
        elif context.startswith("interlude_"):
            self._handle_interlude_choice(context, choice_id)
        else:
            self._handle_mara_choice(choice_id)
        self._advance_dialogue_pose()
        self.update()

    def _run_dialogue_after(self, after: str | None) -> None:
        if not after:
            return
        if after == "opening_choice":
            self.show_choices(
                "LAST CLERK",
                "I still have several questions.",
                [
                    ("practical", "What exactly is wrong with this place?"),
                    ("vulnerable", "Why can't I remember my name?"),
                    ("humorous", "Is waking up beside a talking building normal here?"),
                ],
                context="opening",
            )
        elif after == "start_movement_tutorial":
            self._mark_story_flag("movement_tutorial_started")
            self._toast("Use the arrow keys to walk to Mara.")
        elif after == "enter_vault":
            self._enter_vault()
        elif after == "summon_mercy_wraith":
            self.start_battle("red_tape_wraith")
        elif after.startswith("complete_trial:"):
            self._complete_trial(after.split(":", 1)[1])
        elif after == "finish_level_ending":
            self.scene = "ending"
            self.battle_locked = True

    def _handle_opening_choice(self, choice_id: str) -> None:
        responses = {
            "practical": [
                ("LAST CLERK", "What exactly is wrong with this place?"),
                ("MARA", "Several rooms stopped working. The Hall of Memory went first."),
                ("LAST CLERK", "A room can stop working?"),
                ("MARA", "This one can. I will explain when you can stand without swaying."),
            ],
            "vulnerable": [
                ("LAST CLERK", "Why can't I remember my name?"),
                ("MARA", "I don't know yet."),
                ("LAST CLERK", "You called me the Last Clerk."),
                ("MARA", "That is what the Archive called you. It is a title, not an answer."),
                ("LAST CLERK", "Good. I don't think I like it."),
                ("MARA", "Neither do I."),
            ],
            "humorous": [
                ("LAST CLERK", "Is waking up beside a talking building normal here?"),
                ("MARA", "No. Usually people use the beds."),
                ("LAST CLERK", "Good. I was worried I had broken some local custom."),
                ("MARA", "Only several laws of nature. We can discuss those later."),
            ],
        }
        tendency = choice_id if choice_id in responses else "practical"
        self._record_response_tendency(tendency)
        self._mark_story_flag("opening_seen", persist=False)
        self._mark_story_flag("lantern_recognition_seen", persist=False)
        lines = responses[tendency] + [
            ("MARA", "One thing at a time. Walk over here."),
            ("LAST CLERK", "Why?"),
            ("MARA", "Because I would like to know whether your legs work before I send you anywhere."),
            ("LAST CLERK", "That is the first completely reasonable thing you've said."),
            ("MARA", "Enjoy it. The western passage is the only door that will open."),
            ("MARA", "Take the lantern. The rear clasp sticks."),
            ("LAST CLERK", "Not if you turn it twice before closing."),
            ("MARA", "How did you know that?"),
            ("LAST CLERK", "I don't know."),
            ("MARA", "All right. One mystery at a time."),
        ]
        save_game(self.state)
        self.show_dialogue(lines, portraits=True, after="start_movement_tutorial")

    def _handle_interlude_choice(self, context: str, choice_id: str) -> None:
        tendency = choice_id if choice_id in {"practical", "vulnerable", "humorous"} else "practical"
        self._record_response_tendency(tendency)
        responses = {
            "vulnerable": (
                "LAST CLERK", "Were you worried about me?",
                "MARA", "Yes. Do not make me say it twice.",
            ),
            "practical": (
                "LAST CLERK", "Tell me what this relic does.",
                "MARA", "It opens the matching seal, but only after the Hall has marked you with what happened inside. The founders did not trust borrowed answers.",
            ),
            "humorous": (
                "LAST CLERK", "I knew you would miss me.",
                "MARA", "I missed knowing whether you were alive. The rest remains under review.",
            ),
        }
        first_speaker, first_line, second_speaker, second_line = responses[tendency]
        self.show_dialogue([(first_speaker, first_line), (second_speaker, second_line)], portraits=True)

    @staticmethod
    def _dialogue_speaker_role(speaker: str) -> str | None:
        normalized = speaker.upper()
        if "MARA" in normalized:
            return "mara"
        if "LAST CLERK" in normalized or "ARCHIVIST" in normalized:
            return "archivist"
        return None

    def _active_dialogue_role(self) -> str | None:
        if not self.dialogue or not self.dialogue_portraits:
            return None
        speaker = self.dialogue[min(self.dialogue_index, len(self.dialogue) - 1)][0]
        return self._dialogue_speaker_role(speaker)

    def _advance_dialogue_pose(self):
        """Select an authored pose that matches the active line's intent."""
        role = self._active_dialogue_role()
        if not role or not self.dialogue:
            return
        speaker, text = self.dialogue[min(self.dialogue_index, len(self.dialogue) - 1)]
        self.dialogue_pose_frames[role] = self._dialogue_pose_for_line(role, speaker, text)

    @staticmethod
    def _dialogue_pose_for_line(role: str, speaker: str, text: str) -> int:
        """Map conversational subtext to the sixteen authored portrait poses."""
        line = f"{speaker} {text}".lower()
        if "tea" in line or "cup" in line:
            return 4
        if role == "mara":
            if any(word in line for word in ("ridiculous", "absurd", "offensive", "annoy", "uncharitable")):
                return 8
            if any(word in line for word in ("evidence", "proof", "theory", "suspicion", "guess", "determining")):
                return 9
            if any(word in line for word in ("easy", "all right", "better than", "deserve better", "i'm here")):
                return 10
            if any(word in line for word in ("century", "souls", "lost", "remembered", "my friend")):
                return 11
            if any(word in line for word in ("warning", "listen", "do not", "don't", "never")):
                return 12
            if any(word in line for word in ("relief", "glad", "whole again", "there you are")):
                return 13
            if any(word in line for word in ("funny", "joke", "lovely", "amusing")):
                return 14
            if any(word in line for word in ("over there", "that hall", "the vault", "go on")):
                return 15
        else:
            if any(word in line for word in ("i don't understand", "confused", "what does", "why would")):
                return 8
            if any(word in line for word in ("careful", "watching", "something moved", "not alone")):
                return 9
            if any(word in line for word in ("record", "clue", "deduce", "the page", "the docket")):
                return 10
            if any(word in line for word in ("i'm here", "we can", "you are not", "trust me")):
                return 11
            if any(word in line for word in ("lost", "gone", "couldn't save", "remember her")):
                return 12
            if any(word in line for word in ("behind us", "get back", "incoming", "run")):
                return 13
            if any(word in line for word in ("thank you", "finally", "we did it", "good to see")):
                return 14
            if any(word in line for word in ("i'll do it", "then we fight", "show me", "let's go")):
                return 15
        if any(word in line for word in ("hurt", "wound", "worried", "fear", "afraid", "friend", "gone", "remember my name")):
            return 2
        if any(word in line for word in ("how", "first", "take the", "place the", "join", "relic", "seal", "archive", "means")):
            return 3
        if any(word in line for word in ("wait", "do not", "must", "danger", "inside", "turn the key", "ready")):
            return 7 if role == "mara" else 5
        if any(word in line for word in ("always?", "what?", "recogniz", "familiar", "true one")):
            return 6
        if any(word in line for word in ("lovely", "dramatic", "furniture", "promotion", "miss me", "rebrand")):
            return 1
        return 0

    def _dialogue_speaker_side(self, role: str | None) -> str:
        if role == "mara":
            speaker_x, other_x = CLERK_POSITION[0], self.state.player_x
        elif role == "archivist":
            speaker_x, other_x = self.state.player_x, CLERK_POSITION[0]
        else:
            return "center"
        return "left" if speaker_x <= other_x else "right"

    def _dialogue_layout(self) -> tuple[str | None, str, QRectF, QRectF]:
        role = self._active_dialogue_role()
        side = self._dialogue_speaker_side(role)
        if side == "center":
            return role, side, QRectF(), QRectF(70, 448, 820, 154)
        x = 24 if side == "left" else 526
        portrait = QRectF(x, 70, 410, 390)
        dialogue = QRectF(x + 6, 424, 404, 180)
        return role, side, portrait, dialogue

    def _start_vault_intro(self):
        self._mark_story_flag("vault_identity_phrase_heard")
        self._start_cinematic("intro", list(VAULT_INTRO), after="start_pending")

    def _start_cinematic(self, kind: str, steps: list[tuple[int, int, str, str]], after: str):
        self.keys.clear()
        self.cinematic_kind = kind
        self.cinematic_steps = steps
        self.cinematic_index = 0
        self.cinematic_after = after
        self.scene = "cinematic"

    def _advance_cinematic(self):
        self.cinematic_index += 1
        if self.cinematic_index < len(self.cinematic_steps):
            return
        after = self.cinematic_after
        self.cinematic_steps = []
        self.cinematic_index = 0
        self.cinematic_after = None
        if after == "start_pending":
            self.start_battle("pending")
        elif after == "start_mimic":
            self.start_battle("misfiled_mimic")
        elif after == "recover_to_hub":
            self._finish_defeat_recovery()
        elif after == "complete_level":
            self._finish_level_victory()

    def _start_defeat_cinematic(self):
        self._start_cinematic("defeat", list(DEFEAT_CINEMATIC), after="recover_to_hub")

    def _start_victory_cinematic(self):
        self._start_cinematic("victory", list(VICTORY_CINEMATIC), after="complete_level")

    def _start_mimic_intro(self):
        self._start_cinematic("mimic_intro", list(MIMIC_INTRO), after="start_mimic")

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.dist(a, b)

    def interact(self):
        handlers = {
            "hub": self._interact_hub,
            "memory": self._interact_memory,
            "mercy": self._interact_mercy,
            "order": self._interact_order,
            "vault": lambda: self.start_battle("pending") if not self.state.boss_defeated else None,
        }
        handlers[self.state.current_room]()

    def _nearest(self, targets: dict[str, tuple[float, float]]) -> tuple[float, str]:
        player = (self.state.player_x, self.state.player_y)
        return min((self._distance(player, position), target) for target, position in targets.items())

    def _interact_hub(self):
        targets = {"clerk": CLERK_POSITION, "vault": VAULT_POSITION}
        targets.update({f"seal:{trial_id}": HUB_SEAL_MARKER_CENTERS[trial_id] for trial_id in SEALS})
        distance, target = self._nearest(targets)
        if not self._has_story_flag("onboarding_complete"):
            mara_distance = self._distance(
                (self.state.player_x, self.state.player_y), CLERK_POSITION
            )
            if not self._has_story_flag("movement_tutorial_complete"):
                self._toast("Use the arrow keys first. Mara is waiting near the south-west desk.")
                return
            if mara_distance > self.INTERACT_DISTANCE:
                self._toast("Walk closer to Mara, then press Space to speak.")
                return
            self._mark_story_flag("interaction_tutorial_complete", persist=False)
            self._mark_story_flag("onboarding_complete")
            self.show_dialogue([
                ("LAST CLERK", "All right. My legs work."),
                ("MARA", "Good. Use the arrow keys to move. Press Space when you want to inspect something or speak to someone."),
                ("LAST CLERK", "Including the building?"),
                ("MARA", "Especially the building. It gets offended when ignored."),
                ("MARA", "Go through the west passage. If the lantern brightens near something, stand close and press Space."),
                ("LAST CLERK", "What am I looking for?"),
                ("MARA", "Anything that behaves like it should not be alive."),
                ("LAST CLERK", "That does not narrow it down."),
                ("MARA", "You're learning quickly."),
            ], portraits=True)
            return
        if distance > self.INTERACT_DISTANCE:
            next_hall = self._next_story_hall()
            if next_hall:
                self._toast(
                    f"The way forward is {ROOMS[next_hall]['name']}. The other passages are still sealed."
                )
            else:
                self._toast(
                    "Bring the current hall's relic to its matching seal. Understanding comes before access."
                )
            return
        if target == "clerk":
            self._open_mara_conversation()
        elif target.startswith("seal:"):
            self._interact_seal(target.split(":", 1)[1])
        elif not self.state.vault_key_assembled:
            missing = 3 - len(self.state.key_fragments)
            line = (
                "The fragments are complete, but still separate. Drag them together in the relic belt."
                if missing == 0
                else f"The vault rejects the attempt. {missing} key fragment{'s' if missing != 1 else ''} remain."
            )
            self.show_dialogue([("THE VAULT", line)])
        elif self.state.boss_defeated:
            self.show_dialogue([("THE QUIET VAULT", "The oldest pending request has finally been closed.")])
        elif not self.state.vault_key_inserted:
            self.show_dialogue([("THE VAULT", "The key is whole. Drag it from the relic belt into the illuminated keyhole.")])
        else:
            self._toast("The lock is waiting. Click the inserted key.")

    @staticmethod
    def _vault_keyhole_rect() -> QRect:
        return QRect(458, 88, 44, 58)

    @staticmethod
    def _vault_keyhole_drop_rect() -> QRect:
        return QRect(420, 55, 120, 125)

    def _activate_vault_keyhole(self):
        if self.state.boss_defeated:
            self.show_dialogue([("THE QUIET VAULT", "The oldest pending request has finally been closed.")])
        elif not self.state.vault_key_assembled:
            self._interact_hub()
        elif not self.state.vault_key_inserted:
            self._toast("Drag the completed key from your relic belt to this lock.")
        elif not self._has_story_flag("pre_vault_conversation_seen"):
            self._mark_story_flag("pre_vault_conversation_seen")
            self.show_dialogue([
                ("MARA", "Once that door opens, I cannot follow you."),
                ("LAST CLERK", "You waited until my hand was on the key to mention that."),
                ("MARA", "I kept hoping the rule had changed."),
                ("LAST CLERK", "Did it?"),
                ("MARA", "No."),
                ("LAST CLERK", "Why are you bound here?"),
                ("MARA", "The night of the Bellglass Fire, the Hall wrote my name into its foundation ledger. I have not crossed this threshold since."),
                ("LAST CLERK", "That is not the whole answer."),
                ("MARA", "No."),
                ("LAST CLERK", "Will I get the rest?"),
                ("MARA", "If you come back."),
                ("LAST CLERK", "I will."),
            ], portraits=True, after="enter_vault")
        else:
            self._enter_vault()

    def _enter_vault(self) -> None:
        self.state.vault_opened = True
        self.state.current_room = "vault"
        self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS["vault"]
        save_game(self.state)
        self._start_vault_intro()

    def _interact_seal(self, trial_id: str):
        puzzle = SEAL_PUZZLES[trial_id]
        expected = next((
            item for item in HALL_SEQUENCE
            if item in self.state.completed_trials
            and item not in self.state.completed_seal_puzzles
        ), None)
        if trial_id in self.state.completed_seal_puzzles:
            self.show_dialogue([(SEALS[trial_id]["name"].upper(), "Its fragment is already yours. The seal declines to perform an encore.")])
        elif expected and trial_id != expected:
            self.show_dialogue([(
                SEALS[trial_id]["name"].upper(),
                f"The mechanism stays cold. {SEALS[expected]['name']} holds the next line of the record.",
            )])
        elif puzzle["relic"] not in self.state.inventory:
            lines = [(
                SEALS[trial_id]["name"].upper(),
                f"A hollow in the mechanism matches the {puzzle['relic_name']}. The relic lies somewhere in the {ROOMS[trial_id]['name']}.",
            )]
            if trial_id == "memory":
                lines.extend([
                    ("MARA", "Stop. That machine will not open for you yet."),
                    ("LAST CLERK", "Why not?"),
                    ("MARA", "It needs something called the Recall Lens. The Hall of Memory should release it when all three clocks are working again."),
                    ("LAST CLERK", "So I fix three impossible clocks to earn permission from the larger impossible clock."),
                    ("MARA", "That is the situation, yes."),
                ])
            self.show_dialogue(lines, portraits=trial_id == "memory")
        else:
            self._begin_hub_seal_activation(trial_id)

    def _begin_hub_seal_activation(self, trial_id: str) -> None:
        """Let the selected Hall seal visibly engage before opening its puzzle."""
        if self.hub_seal_activation_effect:
            return
        self.keys.clear()
        self.hub_seal_activation_effect = {
            "trial_id": trial_id,
            "started": self.world_clock,
            "duration": 24,
        }

    def _tick_hub_seal_activation(self) -> None:
        effect = self.hub_seal_activation_effect
        if not effect or self.world_clock - effect["started"] < effect["duration"]:
            return
        trial_id = effect["trial_id"]
        self.hub_seal_activation_effect = None
        self._start_seal_puzzle(trial_id)

    def _open_mara_conversation(self):
        # A fresh approach starts a fresh conversational session. During one
        # session Mara will answer a topic three times, then retire it.
        self.mara_topic_uses.clear()
        self.mara_response_history.clear()
        greeting = self._mara_pick("greeting", (
            "What happened? You have that look again.",
            "You have been staring at the lantern for a full minute. What is it?",
            "Back already? Are you hurt?",
            "Go on. Ask.",
            "What did the room do this time?",
        ))
        self.show_choices("MARA, SENIOR CLERK", greeting, self._mara_menu_choices())

    def _mara_menu_choices(self) -> list[tuple[str, str]]:
        choices = [
            ("guidance", "What should I do next?"),
            ("status", "How am I doing? Be honest."),
            ("tips", "What am I overlooking?"),
            ("mara", "Why are you helping me?"),
        ]
        if len(self.state.completed_trials) >= 3:
            choices.append(("connection", "You felt my injury. What does that mean?"))
        elif len(self.state.completed_trials) >= 2:
            choices.append(("lysa", "Who was Lysa Marr?"))
        elif self._has_story_flag("lantern_recognition_seen"):
            choices.append(("familiar", "Why do I seem familiar to you?"))
        if self.state.completed_trials:
            choices.append(("seals", "How do the main-hall seals work?"))
        if len(self.state.key_fragments) >= 2:
            choices.append(("fusion", "What do I do with these fragments?"))
        if self.state.player_hp < 100:
            choices.append(("recover", f"Patch me up ({MARA_RECOVERY_COST} gold)."))
        if len(choices) >= 8:
            choices = [choice for choice in choices if choice[0] != "status"]
        choices = [
            choice for choice in choices
            if choice[0] in {"recover", "leave"} or self.mara_topic_uses.get(choice[0], 0) < 3
        ]
        choices.append(("leave", "That's enough wisdom for now."))
        return choices

    def _mara_pick(self, topic: str, responses: tuple[str, ...] | list[str]) -> str:
        """Choose an unused answer for this conversation before recycling."""
        history = self.mara_response_history.setdefault(topic, [])
        available = [line for line in responses if line not in history] or list(responses)
        response = random.choice(available)
        history.append(response)
        return response

    def _continue_mara_conversation(self, topic: str, responses: tuple[str, ...] | list[str]) -> None:
        self.show_choices("MARA", self._mara_pick(topic, responses), self._mara_menu_choices())

    def _handle_mara_choice(self, choice_id: str):
        if choice_id == "leave":
            line = self._mara_pick("leave", (
                "All right. Call through the lantern if something changes.",
                "Be careful. If a room offers you anything, ask me first.",
                "I will be here when you get back.",
                "Go on. I should probably look busy.",
            ))
            self.show_dialogue([("MARA", line)], portraits=True)
            return
        if choice_id != "recover":
            self.mara_topic_uses[choice_id] = self.mara_topic_uses.get(choice_id, 0) + 1
        if choice_id == "recover":
            if self.state.gold < MARA_RECOVERY_COST:
                responses = (
                    f"The binding salts cost {MARA_RECOVERY_COST}. You have {self.state.gold}. Sit down anyway; I can stop the bleeding.",
                    f"You are short of the {MARA_RECOVERY_COST} gold. I can clean the wound now, but the deeper repair needs fresh salts.",
                    f"Not enough. Sit. I can still make sure you leave with the same number of organs.",
                )
                self._continue_mara_conversation("recover_insufficient", responses)
                return
            restored = 100 - self.state.player_hp
            self.state.gold -= MARA_RECOVERY_COST
            self.state.player_hp = 100
            save_game(self.state)
            responses = (
                f"There. {restored} strength restored. Move your shoulder. Slowly.",
                f"Finished. I restored {restored}. Try not to tear it open again before I put the bandages away.",
                f"That will hold. {restored} strength restored. Tell me if your hand starts going numb.",
            )
            self._continue_mara_conversation("recover_success", responses)
            return
        if choice_id == "fusion":
            self._continue_mara_conversation("fusion", (
                "Put any two fragments together in the relic belt. When they join, add the third.",
                "Start with two pieces, then add the last one. The order doesn't matter.",
                "Join two first, then the third. And keep your fingers clear when it closes.",
            ))
            return
        if choice_id == "seals":
            unsolved = [SEALS[item]["name"] for item in SEALS if item not in self.state.completed_seal_puzzles]
            if unsolved:
                responses = (
                    "Each relic opens its matching seal. Bring it close and the mechanism should wake up.",
                    "Take each hall relic to the seal that matches it. Then solve whatever the seal shows you.",
                    f"You still need to open {', '.join(unsolved)}. Bring the matching relics to them.",
                )
            else:
                responses = (
                    "All three seals have released their fragments. Assemble the key in your relic belt.",
                    "You have all three fragments. Put them together in the relic belt.",
                    "That's every piece. Assemble the key, then bring it to the Vault lock.",
                )
            self._continue_mara_conversation("seals_open" if unsolved else "seals_done", responses)
            return
        if choice_id == "status":
            trials = len(self.state.completed_trials)
            seals = len(self.state.completed_seal_puzzles)
            if self.state.vault_key_inserted:
                key_state = "The key is in the lock, waiting for your nerve."
            elif self.state.vault_key_assembled:
                key_state = "The key is whole and considerably more confident than you look."
            else:
                fragments = len(self.state.key_fragments)
                key_state = f"You carry {fragments} of the three key fragments."
            responses = (
                f"You're doing well. {trials} halls cleared, {seals} seals answered, and your health is {self.state.player_hp}. {key_state}",
                f"Better than I expected. That was praise, by the way. You've cleared {trials} halls and answered {seals} seals. {key_state}",
                f"So far: {trials} halls cleared, {seals} seals answered, and {self.state.player_hp} health. {key_state}",
            )
            self._continue_mara_conversation("status", responses)
            return
        if choice_id == "tips":
            if not self.state.completed_trials:
                responses = (
                    "Start with Memory through the west passage. Restore all three Archives and bring back the Recall Lens.",
                    "Memory first. When the lantern brightens near an object, stand close and press Space to inspect it.",
                    "The west passage is open. The other two aren't, so at least the Archive has made one decision for us.",
                )
            elif len(self.state.completed_trials) < 3:
                last_complete = self.state.completed_trials[-1]
                if last_complete not in self.state.completed_seal_puzzles:
                    seal_name = SEALS[last_complete]["name"]
                    responses = (
                        f"Take the relic to {seal_name} in this room. Solve the seal and the next passage should open.",
                        f"Your next stop is {seal_name}. Bring the relic you just found.",
                        f"Wake {seal_name} with the relic, then solve its mechanism.",
                    )
                else:
                    next_hall = self._next_story_hall()
                    hall_name = ROOMS[next_hall]["name"] if next_hall else "the next hall"
                    responses = (
                        f"{hall_name} is open now. Follow the newly awakened passage.",
                        f"Go to {hall_name}. The passage should recognize the relic you brought back.",
                        f"The next passage leads to {hall_name}. The other one is still locked.",
                    )
            elif len(self.state.completed_seal_puzzles) < 3:
                responses = (
                    "Take each relic to its matching seal. Look over the whole mechanism before you start moving anything.",
                    "You've cleared the halls. Now use the relics on their seals in the main room.",
                    "The relics aren't souvenirs. Each one opens a seal, so try not to lose them.",
                )
            elif not self.state.vault_key_assembled:
                responses = (
                    "Join any two fragments in the belt, then add the third.",
                    "Put two pieces together first. Once they lock, add the last one.",
                    "Any pair will work. Join them, then complete the key with the third fragment.",
                )
            elif not self.state.vault_key_inserted:
                responses = (
                    "Drag the completed key into the glowing lock above us.",
                    "Put the key in the illuminated keyhole. Then step back, just in case.",
                    "The key is ready. Place it in the Vault lock when you are prepared to go inside.",
                )
            else:
                responses = (
                    "Turn the key when you're ready. Inside, the Shadow Clerks will keep returning while The Pending is alive.",
                    "Fight through the Shadow Clerks, but focus on The Pending whenever you get an opening.",
                    "Don't spend the whole fight on the clerks. They keep coming back until their master falls.",
                )
            tip_state = (
                f"tips_{len(self.state.completed_trials)}_"
                f"{len(self.state.completed_seal_puzzles)}_"
                f"{self.state.vault_key_assembled}_{self.state.vault_key_inserted}"
            )
            self._continue_mara_conversation(tip_state, responses)
            return
        if choice_id == "mara":
            self._continue_mara_conversation("mara", (
                "Because I was here when this place started failing. I couldn't stop it then. I can help you now.",
                "I have watched other people go into that Vault alone. None of them came back. I won't pretend that doesn't matter anymore.",
                "Because everyone deserves at least one person who remembers their name. Even if we haven't found yours yet.",
                "At first? Guilt. Now I just want you to come back alive. There. Honest enough?",
            ))
            return
        if choice_id == "familiar":
            self._continue_mara_conversation("familiar", (
                "Sometimes you move like someone I knew. Then you speak, and you are completely yourself again. I don't know what it means.",
                "You knew how to fix the lantern clasp before I told you. There have been a few things like that. They might matter. They might not.",
                "Yes, you feel familiar. But I am not going to decide who you are because you remind me of someone I miss.",
            ))
            return
        if choice_id == "lysa":
            self._continue_mara_conversation("lysa", (
                "Lysa Marr copied records for Elian Vey. She once found a missing comma in a thousand-page decree and talked about it for a week.",
                "The Council called Lysa difficult whenever she proved one of them wrong. It happened often.",
                "She was my friend. We never found her after the fire. I don't know whether that makes me hopeful or foolish.",
            ))
            return
        if choice_id == "connection":
            self._continue_mara_conversation("connection", (
                "I felt the blow when it hit you. Not sympathy. The pain itself. I do not know why.",
                "For one second I knew exactly where you were hurt. I have theories, but right now they are only theories.",
                "It may mean we were connected before you woke up. I need more evidence before I tell you anything stronger than that.",
            ))
            return
        incomplete = [ROOMS[item]["name"] for item in SEALS if item not in self.state.completed_trials]
        unsolved = [SEALS[item]["name"] for item in SEALS if item not in self.state.completed_seal_puzzles]
        if not self._has_story_flag("onboarding_complete"):
            text = "Come closer and talk to me. Let's make sure you can move before we worry about anything else."
        elif self.state.completed_trials and self.state.completed_trials[-1] not in self.state.completed_seal_puzzles:
            trial_id = self.state.completed_trials[-1]
            text = f"Bring the {TRIAL_REWARDS[trial_id]['label']} to {SEALS[trial_id]['name']}. Solve it and the next passage should open."
        elif incomplete:
            next_hall = self._next_story_hall()
            text = f"Your next path is {ROOMS[next_hall]['name']}. It's the only new passage that opened."
        elif unsolved:
            text = f"Take the relics to the seals. Start with {unsolved[0]}."
        elif not self.state.vault_key_assembled:
            text = "Fuse the three fragments in the relic belt. They should form the Vault key."
        elif not self.state.vault_key_inserted:
            text = "The key is whole. Drag it into the glowing keyhole above us."
        else:
            text = "The key is in place. Click it when you're ready. And take your time."
        alternatives = self._mara_guidance_alternatives(incomplete, unsolved)
        self._continue_mara_conversation("guidance", (text, *alternatives))

    def _mara_guidance_alternatives(self, incomplete: list[str], unsolved: list[str]) -> tuple[str, str]:
        if incomplete:
            if self.state.completed_trials and self.state.completed_trials[-1] not in self.state.completed_seal_puzzles:
                trial_id = self.state.completed_trials[-1]
                return (
                    f"Use the {TRIAL_REWARDS[trial_id]['label']} on {SEALS[trial_id]['name']}. That should open the next door.",
                    f"Solve {SEALS[trial_id]['name']} here in the main room. You already have the relic it needs.",
                )
            next_hall = self._next_story_hall()
            return (
                f"Only {ROOMS[next_hall]['name']} is open. Follow that passage.",
                f"Go to {ROOMS[next_hall]['name']}. The other passages will open later.",
            )
        if unsolved:
            return (
                f"You cleared the halls, but {unsolved[0]} still blocks the Vault. Bring it the matching relic.",
                f"Try {unsolved[0]} next. Use its relic and solve the mechanism.",
            )
        if not self.state.vault_key_assembled:
            return (
                "The fragments are ready. Join them in the relic belt to make the key.",
                "Bring all three fragments together in the relic belt. They should lock into place.",
            )
        if not self.state.vault_key_inserted:
            return (
                "Carry the key to the glowing lock above us. Then stand back.",
                "Put the completed key in the illuminated lock. We don't know what will happen next.",
            )
        return (
            "Everything is ready. Turn the key when you are.",
            "The lock is waiting. Take a breath first if you need one.",
        )

    def _start_seal_puzzle(self, trial_id: str):
        self.active_puzzle = trial_id
        self.puzzle_selected = None
        if trial_id == "memory":
            self.puzzle_sequence = ["exile", "oath", "return", "fracture", "silence"]
            self.puzzle_socket_order = list(range(5))
            self.chronometer_open_slot = None
            self.chronometer_scroll_animation = ""
            self.chronometer_exchange = None
            self._set_chronometer_animation("intro")
        elif trial_id == "mercy":
            self.mercy_loom_links = {item["id"]: None for item in MERCY_CONSEQUENCE_LINKS}
            self.mercy_loom_selected = None
            self.mercy_loom_motion = None
            self.mercy_loom_audits_used = 0
            self.mercy_loom_feedback = ""
        else:
            self.order_rings = [1, 2, 2, 2]
            self.order_rotor_animation = None
            self.order_last_rotor = None
            self.order_turns_used = 0
        self.keys.clear()
        self.scene = "seal_puzzle"

    def _handle_puzzle_click(self, point):
        if self.active_puzzle == "order" and self.order_rotor_animation:
            return
        if self.active_puzzle == "memory" and (
            self.chronometer_animation in {"lever_pull", "fail", "success"}
            or self.chronometer_scroll_animation
            or self.chronometer_exchange
        ):
            return
        if QRect(24, 24, 92, 34).contains(point):
            self.scene = "explore"
            return
        if self.active_puzzle == "memory":
            if self.chronometer_open_slot is not None:
                if self._chronometer_parchment_rect().contains(point):
                    self._set_chronometer_scroll_animation("closing")
                return
            for index, rect in enumerate(self._memory_puzzle_rects()):
                if rect.contains(point):
                    self.chronometer_open_slot = index
                    self._set_chronometer_scroll_animation("opening")
                    return
            for index, rect in enumerate(self._memory_selector_rects()):
                if rect.contains(point):
                    if self.puzzle_selected is None:
                        self.puzzle_selected = index
                    else:
                        first = self.puzzle_selected
                        self.puzzle_selected = None
                        if first != index:
                            self.chronometer_exchange = {
                                "first": first,
                                "second": index,
                                "started": self.world_clock,
                                "duration": 24,
                            }
                    return
            if self._chronometer_lever_rect().contains(point):
                self.chronometer_pending_result = (
                    "success" if tuple(self.puzzle_sequence) == PUZZLE_MEMORY_ORDER else "fail"
                )
                self._set_chronometer_animation("lever_pull")
        elif self.active_puzzle == "mercy":
            if self.mercy_loom_motion:
                return
            for consequence_id, rect in self._mercy_loom_source_rects().items():
                if rect.contains(point):
                    if self.mercy_loom_links[consequence_id] is not None:
                        self.mercy_loom_links[consequence_id] = None
                        self.mercy_loom_feedback = "That thread has been returned to the shuttle."
                    self.mercy_loom_selected = consequence_id
                    return
            for destination_id, rect in self._mercy_loom_destination_rects().items():
                if rect.contains(point) and self.mercy_loom_selected:
                    consequence_id = self.mercy_loom_selected
                    for linked_id, linked_destination in self.mercy_loom_links.items():
                        if linked_id != consequence_id and linked_destination == destination_id:
                            self.mercy_loom_links[linked_id] = None
                    self.mercy_loom_links[consequence_id] = destination_id
                    self.mercy_loom_motion = {
                        "token": consequence_id,
                        "started": self.world_clock,
                        "duration": 20,
                    }
                    self.mercy_loom_feedback = (
                        "Thread seated. The Loom will judge the full account, not one convenient answer."
                    )
                    self.mercy_loom_selected = None
                    return
            if self._mercy_loom_wheel_rect().contains(point):
                expected = {item["id"]: item["id"] for item in MERCY_CONSEQUENCE_LINKS}
                if self.mercy_loom_links == expected:
                    self._complete_seal_puzzle("mercy")
                else:
                    self.mercy_loom_audits_used += 1
                    correct = {
                        consequence_id
                        for consequence_id, destination_id in self.mercy_loom_links.items()
                        if destination_id == consequence_id
                    }
                    for consequence_id in self.mercy_loom_links:
                        if consequence_id not in correct:
                            self.mercy_loom_links[consequence_id] = None
                    remaining = MERCY_LOOM_AUDIT_LIMIT - self.mercy_loom_audits_used
                    if remaining <= 0:
                        self.mercy_loom_links = {
                            item["id"]: None for item in MERCY_CONSEQUENCE_LINKS
                        }
                        self.mercy_loom_selected = None
                        self.mercy_loom_audits_used = 0
                        self.mercy_loom_feedback = (
                            "The Loom rejects the account and clears every thread. "
                            "Read the recovered appeals again before rebuilding it."
                        )
                    else:
                        self.mercy_loom_feedback = (
                            f"Audit held {len(correct)} of 4 threads. The mismatched threads were released. "
                            f"{remaining} audit{'s' if remaining != 1 else ''} remain."
                        )
                    self._toast(self.mercy_loom_feedback)
        elif self.active_puzzle == "order":
            for index, rect in enumerate(self._order_puzzle_rects()):
                if rect.contains(point):
                    self.order_last_rotor = index
                    affected_rotors = ((index - 1) % 4, index, (index + 1) % 4)
                    for affected in affected_rotors:
                        self.order_rings[affected] = (self.order_rings[affected] + 1) % 4
                    self.order_turns_used += 1
                    self.order_rotor_animation = {
                        "affected": affected_rotors,
                        "clicked": index,
                        "started": self.world_clock,
                        "duration": 36,
                    }
                    return
            if QRect(390, 485, 180, 44).contains(point):
                if self.order_rings == [0, 0, 0, 0]:
                    self._complete_seal_puzzle("order")
                else:
                    self._toast("The registry is still misaligned. Close, but ancient machinery does not grade on vibes.")

    def _tick_order_rotor_animation(self) -> None:
        """Finish each rotor cycle before restoring input or rejecting the attempt."""
        animation = self.order_rotor_animation
        if not animation:
            return
        elapsed = self.world_clock - animation["started"]
        if elapsed < animation["duration"]:
            return
        self.order_rotor_animation = None
        if self.order_rings == [0, 0, 0, 0] or self.order_turns_used < ORDER_TURN_LIMIT:
            return

        self.active_puzzle = None
        self.order_last_rotor = None
        self.show_dialogue([
            (
                "SEAL OF ORDER",
                "Eight turns. The registry locks every wheel at once and rejects the filing. "
                "Step onto its seal again when you are ready to submit a less adventurous theory.",
            )
        ])

    def _complete_seal_puzzle(self, trial_id: str):
        if trial_id not in self.state.completed_seal_puzzles:
            self.state.completed_seal_puzzles.append(trial_id)
        if trial_id not in self.state.key_fragments:
            self.state.key_fragments.append(trial_id)
        self.state.seals = list(self.state.completed_seal_puzzles)
        save_game(self.state)
        details = SEAL_PUZZLES[trial_id]
        self._burst(SEALS[trial_id]["position"], QColor(SEALS[trial_id]["color"]), 44)
        next_hall = next((
            room_id for room_id in HALL_SEQUENCE
            if room_id not in self.state.completed_trials
        ), None)
        unlock_lines = []
        if next_hall and self._hall_is_unlocked(next_hall):
            unlock_lines = [
                ("THE MAIN HALL", f"A lock releases. The passage to {ROOMS[next_hall]['name']} answers with a single breath."),
                ("MARA", f"There. {ROOMS[next_hall]['name']} is open."),
                ("LAST CLERK", "You sound relieved."),
                ("MARA", "I am. Go before the Hall changes its mind."),
            ]
        self.show_dialogue([
            (SEALS[trial_id]["name"].upper(), "The mechanism groans, considers one final objection, and loses."),
            *SEAL_REVELATIONS[trial_id],
            ("FRAGMENT TESTIMONY", FRAGMENT_TESTIMONIES[trial_id]),
            ("LAST CLERK", f"The {details['fragment_name']} fits the relic belt. One piece of the Vault key."),
            *unlock_lines,
        ])

    def _set_chronometer_animation(self, animation: str) -> None:
        self.chronometer_animation = animation
        self.chronometer_animation_started = self.world_clock
        if animation == "fail":
            self._burst((480, 365), QColor("#b74165"), 24)
        elif animation == "success":
            self.puzzle_selected = None
            self._burst((480, 365), QColor("#f5d479"), 42)

    def _tick_chronometer_animation(self) -> None:
        if not self.chronometer_animation:
            return
        elapsed = self.world_clock - self.chronometer_animation_started
        limits = {"intro": 42, "interaction": 14, "lever_pull": 28, "fail": 34, "success": 48}
        if elapsed < limits[self.chronometer_animation]:
            return
        finished = self.chronometer_animation
        self.chronometer_animation = ""
        if finished == "lever_pull":
            result = self.chronometer_pending_result or "fail"
            self.chronometer_pending_result = ""
            self._set_chronometer_animation(result)
            if result == "fail":
                self._toast("CONSISTENT, BUT FALSE. The Chronometer accepts the story and rejects the truth.")
            return
        if finished == "success" and self.scene == "seal_puzzle" and self.active_puzzle == "memory":
            self._complete_seal_puzzle("memory")

    def _set_chronometer_scroll_animation(self, animation: str) -> None:
        self.chronometer_scroll_animation = animation
        self.chronometer_scroll_animation_started = self.world_clock

    def _tick_chronometer_scroll_animation(self) -> None:
        if not self.chronometer_scroll_animation:
            return
        if self.world_clock - self.chronometer_scroll_animation_started < 28:
            return
        finished = self.chronometer_scroll_animation
        self.chronometer_scroll_animation = ""
        if finished == "closing":
            self.chronometer_open_slot = None

    def _tick_chronometer_exchange(self) -> None:
        if not self.chronometer_exchange:
            return
        exchange = self.chronometer_exchange
        if self.world_clock - exchange["started"] < exchange["duration"]:
            return
        first, second = exchange["first"], exchange["second"]
        self.puzzle_sequence[first], self.puzzle_sequence[second] = (
            self.puzzle_sequence[second], self.puzzle_sequence[first]
        )
        self.puzzle_socket_order[first], self.puzzle_socket_order[second] = (
            self.puzzle_socket_order[second], self.puzzle_socket_order[first]
        )
        self.chronometer_exchange = None
        self._set_chronometer_animation("interaction")

    @staticmethod
    def _memory_puzzle_rects():
        return [QRect(242 + index * 88, 205, 72, 154) for index in range(5)]

    @staticmethod
    def _memory_selector_rects():
        return [QRect(238 + index * 88, 364, 80, 68) for index in range(5)]

    @staticmethod
    def _chronometer_parchment_rect() -> QRect:
        return QRect(205, 112, 550, 448)

    @staticmethod
    def _chronometer_parchment_text_rects() -> dict[str, QRectF]:
        """Readable zones inside the authored scroll's ornamental frame."""
        target = QRectF(205, 112, 550, 448)
        return {
            "clue": target.adjusted(120, 184, -120, -160),
            "return": target.adjusted(120, 288, -120, -130),
        }

    @staticmethod
    def _chronometer_title_rect() -> QRectF:
        return QRectF(155, 105, 650, 35)

    @staticmethod
    def _chronometer_lever_rect() -> QRect:
        return QRect(690, 382, 118, 145)

    @staticmethod
    def _chronometer_instruction_rect() -> QRectF:
        return QRectF(205, 548, 550, 25)

    @staticmethod
    def _chronometer_lever_label_rect() -> QRectF:
        return QRectF(686, 505, 126, 22)

    @staticmethod
    def _mercy_loom_source_rects() -> dict[str, QRect]:
        return {
            item["id"]: QRect(74, 100 + index * 112, 126, 92)
            for index, item in enumerate(MERCY_CONSEQUENCE_LINKS)
        }

    @staticmethod
    def _mercy_loom_destination_rects() -> dict[str, QRect]:
        return {
            item["id"]: QRect(760, 100 + index * 112, 126, 92)
            for index, item in enumerate(MERCY_CONSEQUENCE_LINKS)
        }

    @staticmethod
    def _mercy_loom_wheel_rect() -> QRect:
        return QRect(397, 470, 166, 108)

    def _tick_mercy_loom_motion(self) -> None:
        if not self.mercy_loom_motion:
            return
        elapsed = self.world_clock - self.mercy_loom_motion["started"]
        if elapsed >= self.mercy_loom_motion["duration"]:
            self.mercy_loom_motion = None

    @staticmethod
    def _order_puzzle_rects():
        # These are the authored axle centers in coupled_registry_panel_v3 after
        # it is mapped into the puzzle viewport. The sockets are intentionally
        # not spaced at one uniform interval, so deriving later positions from
        # the first rotor makes the registration drift progressively right.
        socket_centers = ((267, 261), (405, 261), (554, 261), (693, 261))
        return [QRect(x - 55, y - 55, 110, 110) for x, y in socket_centers]

    def _interact_memory(self):
        if "memory" in self.state.completed_trials:
            self.show_dialogue([
                ("HALL OF MEMORY", "Three hours rest in their proper places. The room finally exhales."),
                ("LAST CLERK", "They're all working. I wasn't completely sure that would happen."),
            ])
            return
        if self.memory_activation_effect:
            self._toast("The Archive rune is locking in. Temporal systems are booting; please enjoy the ominous glow.")
            return
        nearby_props = [
            prop for prop in MEMORY_SEARCH_OBJECTS
            if self._memory_prop_is_in_range(prop)
        ]
        if self.memory_active_archive:
            if not nearby_props:
                self._toast("Stand beside one of the glowing objects and press Space. Archaeology, but with a timer.")
                return
            prop = min(
                nearby_props,
                key=lambda item: self._distance(
                    (self.state.player_x, self.state.player_y), item["position"]
                ),
            )
            self._search_memory_object(prop)
            return
        archive_id = next((
            plinth["id"] for plinth in MEMORY_PLINTHS
            if QRectF(*plinth["activation_rect"]).contains(
                QPointF(self.state.player_x, self.state.player_y)
            )
        ), None)
        if archive_id:
            self._start_memory_attempt(archive_id)
            return
        self._toast("Step onto an Archive sigil and press Space. Try to look authorized.")

    def _memory_prop_is_in_range(self, prop: dict) -> bool:
        """Use radial reach for free props and approach bands for furniture."""
        if "interaction_radius" in prop:
            return self._distance(
                (self.state.player_x, self.state.player_y), prop["position"]
            ) <= prop["interaction_radius"]
        zone = QRectF(*prop["interaction_rect"])
        return zone.contains(QPointF(self.state.player_x, self.state.player_y))

    @staticmethod
    def _memory_archive_rect(archive_id: str) -> QRect:
        x, y = next(item["position"] for item in MEMORY_PLINTHS if item["id"] == archive_id)
        return QRect(x - 76, y - 96, 152, 150)

    @staticmethod
    def _memory_archive_drop_rect(archive_id: str) -> QRect:
        return ArchiveboundCanvas._memory_archive_rect(archive_id).adjusted(-16, -12, 16, 18)

    def _start_memory_attempt(self, archive_id: str) -> None:
        if archive_id in self.state.memory_archives_completed:
            self.show_dialogue([(
                f"{archive_id.upper()} ARCHIVE",
                "Its hourglass is seated and the record is stable. Do not celebrate loudly; history may hear you.",
            )])
            return
        if self.memory_active_archive:
            if archive_id == self.memory_active_archive:
                self._toast("That Archive is already open. Search the glowing objects; time is literally running.")
            else:
                self._toast(f"Finish the {self.memory_active_archive.title()} Archive first. Time refuses to multitask.")
            return
        self.memory_active_archive = archive_id
        self.memory_avatar_history.clear()
        self.memory_motion_effects.clear()
        self.memory_future_echo_event = None
        self.memory_future_corruption_event = None
        self.memory_future_next_echo_tick = (
            self.world_clock + random.randint(18, 45)
            if archive_id == "future"
            else self.world_clock
        )
        self.memory_future_next_corruption_tick = (
            self.world_clock + random.randint(7, 18)
            if archive_id == "future"
            else self.world_clock
        )
        self.memory_attempt_started_tick = self.world_clock
        self.memory_hourglass_location = self._reroll_memory_hourglass_location(archive_id)
        self.memory_hourglass_found = False
        self.memory_searched_objects.clear()
        self.keys.clear()
        self.memory_activation_effect = {
            "archive_id": archive_id,
            "started": self.world_clock,
            "duration": 32,
        }

    def _tick_memory_activation_effect(self) -> None:
        effect = self.memory_activation_effect
        if not effect or self.world_clock - effect["started"] < effect["duration"]:
            return
        archive_id = effect["archive_id"]
        self.memory_activation_effect = None
        rule = MEMORY_ARCHIVE_RULES[archive_id]
        self._burst(next(item["position"] for item in MEMORY_PLINTHS if item["id"] == archive_id), QColor("#c778ff"), 26)
        self.show_dialogue([
            (f"{archive_id.upper()} ARCHIVE", rule["brief"]),
            ("THE ARCHIVE SPEAKS", rule["guidance"]),
        ])

    def _handle_memory_world_click(self, point) -> bool:
        if self.memory_activation_effect:
            self._toast("The Archive rune is locking into place.")
            return True
        if self.memory_restoration_pending:
            self._toast("The Archive is rebuilding. Temporal masonry still has union rules.")
            return True
        for archive_id in MEMORY_SEQUENCE:
            if self._memory_archive_rect(archive_id).contains(point):
                plinth = next(item for item in MEMORY_PLINTHS if item["id"] == archive_id)
                if not QRectF(*plinth["activation_rect"]).contains(
                    QPointF(self.state.player_x, self.state.player_y)
                ):
                    self._toast("Stand inside the glowing sigil first. The Archive cannot verify you from across the room.")
                else:
                    self._start_memory_attempt(archive_id)
                return True
        for prop in MEMORY_SEARCH_OBJECTS:
            if QRect(*prop["rect"]).contains(point):
                if not self._memory_prop_is_in_range(prop):
                    self._toast(f"Move beside the {prop['label'].lower()}, then press Space. Telepathy is not installed.")
                else:
                    self._search_memory_object(prop)
                return True
        return False

    def _search_memory_object(self, prop: dict) -> None:
        if not self.memory_active_archive:
            self.show_dialogue([(
                prop["label"].upper(),
                "The object is ordinary and firmly closed. One of the Archives may remember it differently.",
            )])
            return
        if self.memory_hourglass_found:
            self._toast("The hourglass is already in your belt. Return it before the Archive closes.")
            return
        if prop["id"] in self.memory_searched_objects:
            self._toast(random.choice((
                "You check again. Nothing has changed, including your opinion of the dust.",
                "Still empty. The second look was thorough; the third would be personal.",
                "You already searched this. Either trust yourself or begin charging the furniture rent.",
            )))
            return
        self.memory_searched_objects.add(prop["id"])
        if prop["id"] == self.memory_hourglass_location:
            self.memory_hourglass_found = True
            self._burst(prop["position"], QColor("#f2c96c"), 30)
            archive_name = self.memory_active_archive.title()
            self.show_dialogue([(
                f"{archive_name.upper()} HOURGLASS FOUND",
                f"The {archive_name} Hourglass unfolds from the {prop['label'].lower()}. Its frame is warm. Return it to the {archive_name} Archive before the last grain falls.",
            )])
        else:
            lore = prop.get("lore", {})
            message = lore.get(
                self.memory_active_archive,
                "Only dust answers the awakened Archive.",
            )
            self.show_dialogue([(prop["label"].upper(), message)])

    def _complete_memory_archive(self, archive_id: str) -> None:
        if archive_id != self.memory_active_archive or not self.memory_hourglass_found:
            self._toast("The Archive does not recognize this hourglass.")
            return
        if archive_id not in self.state.memory_archives_completed:
            self.state.memory_archives_completed.append(archive_id)
        self.state.memory_progress = len(self.state.memory_archives_completed)
        position = next(item["position"] for item in MEMORY_PLINTHS if item["id"] == archive_id)
        self._burst(position, QColor("#f4cf70"), 38)
        self._clear_memory_attempt()
        self.memory_restoration_pending = archive_id
        self.memory_restoration_started = self.world_clock
        self.keys.clear()
        self.player_is_moving = False

    def _tick_memory_restoration(self) -> None:
        """Hold the room long enough to show every authored rebuild frame."""
        archive_id = self.memory_restoration_pending
        if not archive_id or self.world_clock - self.memory_restoration_started < 48:
            return
        self.memory_restoration_pending = None
        self.memory_restoration_started = 0
        if self.state.memory_progress == len(MEMORY_SEQUENCE):
            self._complete_trial("memory")
            return
        save_game(self.state)
        self.show_dialogue([(
            f"{archive_id.upper()} ARCHIVE RESTORED",
            f"The hourglass clicks into place. {self.state.memory_progress}/3 lost hours have returned.",
        )])

    def _tick_memory_attempt(self) -> None:
        if self.state.current_room != "memory" or not self.memory_active_archive:
            return
        rule = MEMORY_ARCHIVE_RULES[self.memory_active_archive]
        if self.world_clock - self.memory_attempt_started_tick >= rule["seconds"] * 30:
            archive_id = self.memory_active_archive
            self._clear_memory_attempt()
            self.keys.clear()
            self.show_dialogue([(
                f"{archive_id.upper()} ARCHIVE CLOSED",
                "The last grain falls. The hourglass vanishes, and the room releases you.",
            )])

    def _clear_memory_attempt(self) -> None:
        self.memory_active_archive = None
        self.memory_activation_effect = None
        self.memory_avatar_history.clear()
        self.memory_future_echo_event = None
        self.memory_future_next_echo_tick = 0
        self.memory_future_corruption_event = None
        self.memory_future_next_corruption_tick = 0
        self.memory_attempt_started_tick = 0
        self.memory_hourglass_location = None
        self.memory_hourglass_found = False
        self.memory_searched_objects.clear()

    def _cancel_memory_attempt(self) -> None:
        if self.memory_active_archive:
            self._clear_memory_attempt()
            self.keys.clear()
            self._toast("The Archive closes. Its hourglass has moved to another hiding place.")

    def _interact_mercy(self):
        remaining = {
            appeal_id: MERCY_APPEALS[appeal_id]["position"]
            for appeal_id in MERCY_APPEAL_IDS
            if appeal_id not in self.state.mercy_appeals_completed
        }
        if remaining:
            distance, appeal_id = self._nearest({
                item_id: (
                    QRectF(*MERCY_APPEALS[item_id]["activation_rect"]).center().x(),
                    QRectF(*MERCY_APPEALS[item_id]["activation_rect"]).center().y(),
                )
                for item_id in remaining
            })
            zone = QRectF(*MERCY_APPEALS[appeal_id]["activation_rect"]).adjusted(-14, -14, 14, 14)
            if not zone.contains(QPointF(self.state.player_x, self.state.player_y)):
                self._toast(
                    f"Appeals heard: {len(self.state.mercy_appeals_completed)}/3. "
                    "Stand on a reliquary's floor seal and press Space."
                )
                return
            self._begin_mercy_station_activation(appeal_id)
            return
        if not self.state.mercy_hearing_completed:
            if self._distance((self.state.player_x, self.state.player_y), (480, 365)) > 115:
                self._toast("The three findings point toward the central hearing dais.")
                return
            self.state.mercy_hearing_completed = True
            save_game(self.state)
            if "red_tape_wraith" in self.state.defeated_enemies:
                # Compatibility for saves created by the older guardian-first flow.
                self._complete_trial("mercy")
                return
            self.show_dialogue([
                ("THE CENTRAL HEARING", "Three restored findings enter the record. Red cords pull tight beneath the floor."),
                ("LAST CLERK", "Please tell me that sound means we finished."),
                ("MARA, THROUGH THE LANTERN", "It means the Hall can no longer hide who paid for its mercy."),
                ("RED TAPE WRAITH", "UNAUTHORIZED CLAIMANTS RESTORED. CORRECTION REQUIRED."),
                ("LAST CLERK", "Of course the paperwork is angry."),
                ("MARA", "You found the truth it was built to bury. Now it has to face you."),
            ], portraits=True, after="summon_mercy_wraith")
            return
        if "red_tape_wraith" not in self.state.defeated_enemies:
            self._toast("The restored hearing has summoned its enforcer. Finish what the evidence began.")
            return
        if "mercy" not in self.state.completed_trials:
            self._complete_trial("mercy")
            return
        self.show_dialogue([
            ("HALL OF MERCY", "Every granted appeal now names both its relief and its cost."),
            ("LAST CLERK", "So every favor had a bill. They just hid who paid it."),
        ])

    def _begin_mercy_station_activation(self, appeal_id: str) -> None:
        if self.mercy_station_activation_effect:
            return
        self.keys.clear()
        self.mercy_station_activation_effect = {
            "appeal_id": appeal_id,
            "started": self.world_clock,
            "duration": 24,
        }

    def _tick_mercy_station_activation(self) -> None:
        effect = self.mercy_station_activation_effect
        if not effect or self.world_clock - effect["started"] < effect["duration"]:
            return
        appeal_id = effect["appeal_id"]
        self.mercy_station_activation_effect = None
        self._start_mercy_appeal(appeal_id)

    def _start_mercy_appeal(self, appeal_id: str) -> None:
        self.active_mercy_appeal = appeal_id
        self.mercy_appeal_selection = None
        self.mercy_appeal_feedback = ""
        self.mercy_appeal_success = False
        self.mercy_appeal_clip_started = self.world_clock
        self.keys.clear()
        self.scene = "mercy_appeal"

    @staticmethod
    def _mercy_appeal_option_rects() -> list[QRect]:
        return [QRect(112 + index * 248, 458, 232, 58) for index in range(3)]

    def _handle_mercy_appeal_click(self, point) -> None:
        if QRect(24, 24, 92, 34).contains(point):
            self.scene = "explore"
            self.active_mercy_appeal = None
            return
        appeal_id = self.active_mercy_appeal
        if not appeal_id:
            return
        appeal = MERCY_APPEALS[appeal_id]
        for option, rect in zip(appeal["options"], self._mercy_appeal_option_rects()):
            if rect.contains(point):
                self.mercy_appeal_selection = option[0]
                self.mercy_appeal_success = option[0] == appeal["answer"]
                self.mercy_appeal_feedback = (
                    appeal["finding"] if self.mercy_appeal_success
                    else "That answer explains the relief, but it leaves the transferred cost hidden."
                )
                return
        if QRect(350, 554, 260, 38).contains(point):
            if not self.mercy_appeal_success:
                self._toast("The reliquary refuses a finding that still erases the payer.")
                return
            if appeal_id not in self.state.mercy_appeals_completed:
                self.state.mercy_appeals_completed.append(appeal_id)
                self.state.gold += 8
            save_game(self.state)
            self.scene = "explore"
            self.active_mercy_appeal = None
            self._burst(appeal["position"], QColor("#72eee4"), 34)
            self.show_dialogue([
                (appeal["title"], appeal["finding"]),
                ("LAST CLERK", f"That's {len(self.state.mercy_appeals_completed)} of the three appeals. I need to hear the rest."),
            ])

    def _ensure_order_case_variants(self) -> None:
        changed = False
        for investigation_id in ORDER_INVESTIGATION_IDS:
            if investigation_id not in self.state.order_case_variants:
                self.state.order_case_variants[investigation_id] = random.randrange(
                    len(ORDER_INVESTIGATIONS[investigation_id])
                )
                changed = True
        if changed:
            save_game(self.state)

    def _start_order_investigation(self, investigation_id: str) -> None:
        if investigation_id in self.state.order_investigations_completed:
            self.show_dialogue([(
                ORDER_STATIONS[investigation_id]["title"].upper(),
                "This finding is already restored to Docket VII-13. The station has nothing left to hide, which must be uncomfortable for it.",
            )])
            return
        self._ensure_order_case_variants()
        self.active_order_investigation = investigation_id
        self.order_investigation_variant = self.state.order_case_variants[investigation_id]
        self.order_evidence_focus_index = 0
        self.order_visual_clip_started = self.world_clock
        self.order_visual_manual_until = 0
        self.order_selected_index = None
        self.order_investigation_feedback = ""
        self.order_feedback_success = False
        self.order_case_file_open = False
        case = self._order_current_case()
        if investigation_id == "sequence":
            answer = list(case["answer"])
            self.order_sequence = list(answer)
            while self.order_sequence == answer:
                random.shuffle(self.order_sequence)
        else:
            self.order_sequence = []
        self.keys.clear()
        self.scene = "order_investigation"

    def _order_current_case(self) -> dict:
        investigation_id = self.active_order_investigation or "identity"
        return ORDER_INVESTIGATIONS[investigation_id][self.order_investigation_variant]

    @staticmethod
    def _order_investigation_leave_rect() -> QRect:
        return QRect(102, 61, 92, 32)

    @staticmethod
    def _order_investigation_submit_rect() -> QRect:
        return QRect(378, 542, 204, 42)

    @staticmethod
    def _order_case_file_rect() -> QRect:
        return QRect(754, 61, 106, 32)

    @staticmethod
    def _order_hint_rect() -> QRect:
        return QRect(642, 61, 100, 32)

    @staticmethod
    def _order_case_file_close_rect() -> QRect:
        return QRect(742, 83, 82, 30)

    @staticmethod
    def _order_case_file_sections() -> tuple[str, ...]:
        return ("people", "seals", "chronology", "findings")

    @staticmethod
    def _order_case_file_viewport_rect() -> QRect:
        return QRect(310, 148, 500, 346)

    def _order_case_file_tab_rects(self) -> dict[str, QRect]:
        return {
            section: QRect(142, 154 + index * 58, 150, 45)
            for index, section in enumerate(self._order_case_file_sections())
        }

    @staticmethod
    def _order_case_file_scroll_rects() -> tuple[QRect, QRect]:
        return QRect(770, 505, 34, 28), QRect(730, 505, 34, 28)

    def _order_case_file_entry_count(self) -> int:
        return len(self._order_case_file_entries(self.order_case_file_section))

    def _order_case_file_max_scroll(self) -> int:
        content_height = self._order_case_file_entry_count() * 92 + 18
        return max(0, content_height - self._order_case_file_viewport_rect().height())

    def _order_investigation_option_rects(self) -> list[QRect]:
        if self.active_order_investigation == "identity":
            return [QRect(642, 155 + index * 112, 218, 102) for index in range(3)]
        if self.active_order_investigation == "authority":
            return [QRect(642, 155 + index * 78, 218, 68) for index in range(4)]
        return [QRect(642, 155 + index * 78, 218, 68) for index in range(4)]

    def _order_investigation_evidence_rects(self) -> dict[str, QRectF]:
        """Lay out one cinematic reconstruction and its visual chapter controls."""
        return {
            "panel": QRectF(90, 145, 536, 349),
            "clip": QRectF(102, 156, 512, 288),
            "caption": QRectF(110, 447, 496, 20),
            "tabs": QRectF(108, 470, 500, 18),
        }

    @staticmethod
    def _registry_visual_row(investigation_id: str, option_id: str) -> int:
        """Map an answer/event id to its matching visual reconstruction row."""
        rows = {
            "identity": {
                "elian_vey": 1,
                "lysa_marr": 2,
                "orren_vale": 3,
                "tomas_rook": 4,
            },
            "sequence": {
                "vanishing_petitions": 0,
                "secret_copy": 1,
                "black_seal": 2,
                "bellglass_fire": 3,
            },
            "authority": {
                "hourglass": 0,
                "registry_crown": 1,
                "ashen_bell": 2,
                "black_sun": 3,
            },
        }
        return rows.get(investigation_id, {}).get(option_id, 0)

    def _registry_visible_visual_rows(self, investigation_id: str) -> tuple[int, ...]:
        """Return only reconstructions relevant to the current puzzle variant."""
        if investigation_id != "identity":
            return (0, 1, 2, 3)
        case = self._order_current_case()
        candidate_rows = tuple(
            self._registry_visual_row(investigation_id, option[0])
            for option in case["options"]
        )
        return (0, *candidate_rows)

    def _registry_visual_frame(self, investigation_id: str, row: int) -> QPixmap:
        """Return the current frame of a five-second four-frame reconstruction."""
        rows = self.registry_visual_clip_frames.get(investigation_id, ())
        if not rows:
            return QPixmap()
        row = max(0, min(row, len(rows) - 1))
        frames = rows[row]
        if not frames:
            return QPixmap()
        elapsed = max(0, self.world_clock - self.order_visual_clip_started)
        frame_index = min(len(frames) - 1, (elapsed * len(frames)) // 152)
        return frames[frame_index]

    def _paint_registry_visual_clip(
        self, painter: QPainter, investigation_id: str, layout: dict[str, QRectF]
    ):
        """Paint the selected reconstruction without exposing developer terminology."""
        labels = REGISTRY_VISUAL_LABELS.get(investigation_id, ())
        captions = REGISTRY_VISUAL_CAPTIONS.get(investigation_id, ())
        visible_rows = tuple(
            row for row in self._registry_visible_visual_rows(investigation_id)
            if row < len(labels) and row < len(captions)
        )
        row_count = max(1, len(visible_rows))
        focus = max(0, min(self.order_evidence_focus_index, row_count - 1))
        source_row = visible_rows[focus] if visible_rows else 0
        rows = self.registry_visual_clip_frames.get(investigation_id, ())
        frames = rows[source_row] if source_row < len(rows) else ()

        clip_rect = layout["clip"]
        clip_path = QPainterPath()
        clip_path.addRoundedRect(clip_rect, 7, 7)
        painter.save()
        painter.setClipPath(clip_path)
        painter.fillRect(clip_rect, QColor(1, 5, 8, 255))
        if frames:
            elapsed = max(0, self.world_clock - self.order_visual_clip_started)
            progress = min(1.0, elapsed / 152.0)
            frame_position = progress * (len(frames) - 1)
            frame_index = min(len(frames) - 1, int(frame_position))
            next_index = min(len(frames) - 1, frame_index + 1)
            blend = frame_position - frame_index
            blend = blend * blend * (3.0 - 2.0 * blend)
            painter.setOpacity(1.0)
            self._draw_pixmap_cover(painter, clip_rect, frames[frame_index])
            if next_index != frame_index and blend > 0.0:
                painter.setOpacity(blend)
                self._draw_pixmap_cover(painter, clip_rect, frames[next_index])
            painter.setOpacity(1.0)
        else:
            painter.setPen(QColor("#9bcac4"))
            self._draw_fitted_text(
                painter, clip_rect.adjusted(24, 20, -24, -20),
                "The recovered memory is temporarily unreadable.",
                8, 5.5, False, Qt.AlignCenter | Qt.TextWordWrap,
            )
        painter.restore()

        painter.setPen(QColor("#f1ddb0"))
        self._draw_fitted_text(
            painter, layout["caption"], captions[source_row], 7.2, 5.2, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        for index, tab_rect in enumerate(
            self._registry_clue_tab_rects(layout["tabs"], row_count)
        ):
            selected = index == focus
            self._panel(
                painter, tab_rect,
                QColor(35, 84, 78, 248) if selected else QColor(5, 24, 27, 235),
                QColor("#7ef3e2") if selected else QColor("#66583a"),
                2 if selected else 1,
            )
            painter.setPen(QColor("#ffffff") if selected else QColor("#b8cbc7"))
            self._draw_fitted_text(
                painter, tab_rect.adjusted(5, 3, -5, -3), labels[visible_rows[index]],
                5.8, 4.2, True, Qt.AlignCenter | Qt.TextSingleLine,
            )

    @staticmethod
    def _registry_clue_tab_rects(area: QRectF, clue_count: int) -> list[QRectF]:
        if clue_count <= 0 or area.isEmpty():
            return []
        gap = 8.0
        width = (area.width() - gap * (clue_count - 1)) / clue_count
        return [
            QRectF(area.left() + index * (width + gap), area.top(), width, area.height())
            for index in range(clue_count)
        ]

    def _handle_order_investigation_click(self, point) -> None:
        if self.order_case_file_open:
            if self._order_case_file_close_rect().contains(point):
                self.order_case_file_open = False
                self.order_case_file_scroll = 0
                return
            for section, rect in self._order_case_file_tab_rects().items():
                if rect.contains(point):
                    self.order_case_file_section = section
                    self.order_case_file_scroll = 0
                    self.update()
                    return
            down_rect, up_rect = self._order_case_file_scroll_rects()
            if down_rect.contains(point):
                self.order_case_file_scroll = min(self._order_case_file_max_scroll(), self.order_case_file_scroll + 72)
            elif up_rect.contains(point):
                self.order_case_file_scroll = max(0, self.order_case_file_scroll - 72)
            return
        if self._order_case_file_rect().contains(point):
            self.order_case_file_open = True
            self.order_case_file_section = {
                "identity": "people",
                "sequence": "chronology",
                "authority": "seals",
            }.get(self.active_order_investigation, "findings")
            self.order_case_file_scroll = 0
            return
        if self._order_hint_rect().contains(point):
            self._advance_order_hint()
            return
        if self._order_investigation_leave_rect().contains(point):
            self.scene = "explore"
            self.active_order_investigation = None
            return
        case = self._order_current_case()
        evidence_layout = self._order_investigation_evidence_rects()
        for index, rect in enumerate(
            self._registry_clue_tab_rects(evidence_layout["tabs"], 4)
        ):
            if rect.contains(point):
                self.order_evidence_focus_index = index
                self.order_visual_clip_started = self.world_clock
                self.order_visual_manual_until = self.world_clock + 152
                self.order_investigation_feedback = ""
                return
        rects = self._order_investigation_option_rects()
        for index, rect in enumerate(rects):
            if not rect.contains(point):
                continue
            self.order_investigation_feedback = ""
            if self.active_order_investigation == "sequence":
                event_id = self.order_sequence[index]
                sequence_frames = {
                    "vanishing_petitions": 0,
                    "secret_copy": 1,
                    "black_seal": 2,
                    "bellglass_fire": 3,
                }
                self.order_evidence_focus_index = sequence_frames.get(event_id, index)
                self.order_visual_clip_started = self.world_clock
                self.order_visual_manual_until = self.world_clock + 152
                if self.order_selected_index is None:
                    self.order_selected_index = index
                elif self.order_selected_index == index:
                    self.order_selected_index = None
                else:
                    first = self.order_selected_index
                    self.order_sequence[first], self.order_sequence[index] = (
                        self.order_sequence[index], self.order_sequence[first]
                    )
                    self.order_selected_index = None
                    self._burst((480, 340), QColor("#67e8dd"), 12)
            else:
                self.order_selected_index = index
            return
        if not self._order_investigation_submit_rect().contains(point):
            return
        if self.order_selected_index is None and self.active_order_investigation != "sequence":
            self.order_investigation_feedback = "Choose a finding before asking the Registry to judge it."
            return
        if self.active_order_investigation == "sequence":
            correct = tuple(self.order_sequence) == tuple(case["answer"])
        else:
            option_id = case["options"][self.order_selected_index][0]
            correct = option_id == case["answer"]
        if correct:
            self._complete_order_investigation()
        else:
            self._fail_order_investigation()

    def _fail_order_investigation(self) -> None:
        self.state.order_corruption = min(3, self.state.order_corruption + 1)
        penalty = 0
        if self.state.order_corruption >= 3:
            penalty = min(10, self.state.player_hp - 1)
            self.state.player_hp -= penalty
        self.order_selected_index = None
        investigation_id = self.active_order_investigation or "identity"
        self.order_hint_levels[investigation_id] = min(3, self.order_hint_levels.get(investigation_id, 0) + 1)
        guidance = self._order_hint_text(investigation_id)
        if penalty:
            self.order_investigation_feedback = (
                f"The false filing feeds the Registry and takes {penalty} HP. {guidance}"
            )
        elif investigation_id == "sequence":
            answer = tuple(self._order_current_case()["answer"])
            correct = sum(left == right for left, right in zip(self.order_sequence, answer))
            self.order_investigation_feedback = (
                f"{correct}/4 entries are correctly placed. The Registry preserves your work. {guidance}"
            )
        else:
            self.order_investigation_feedback = f"The Registry rejects that finding. {guidance}"
        self.order_feedback_success = False
        self._burst((480, 330), QColor("#b73f74"), 30)
        save_game(self.state)

    def _advance_order_hint(self) -> None:
        investigation_id = self.active_order_investigation or "identity"
        level = min(3, self.order_hint_levels.get(investigation_id, 0) + 1)
        self.order_hint_levels[investigation_id] = level
        self.order_investigation_feedback = self._order_hint_text(investigation_id)
        self.order_feedback_success = True

    def _order_hint_text(self, investigation_id: str) -> str:
        hints = {
            "identity": (
                "Ignore rank. Follow the object found with the missing keeper.",
                "The hourglass key belonged to the Chronometer keeper. The surviving initials are E.V.",
                "The erased keeper was Elian Vey.",
            ),
            "sequence": (
                "Ask what each writer must already have known before writing the next scrap.",
                "The keeper found the loss. The copyist preserved it. A Chancellor ordered the transfer. The fire followed.",
                "Use this order: discovery, copy, Black Sun order, western fire.",
            ),
            "authority": (
                "Separate the seal that commanded the transfer from those that witnessed or protested it.",
                "The Hourglass objected, the Crown handled routine work, and the Bell was added after the fire.",
                "The command came from the Chancellor's Black Sun.",
            ),
        }
        level = max(1, self.order_hint_levels.get(investigation_id, 1))
        return hints[investigation_id][min(level, 3) - 1]

    def _complete_order_investigation(self) -> None:
        investigation_id = self.active_order_investigation or "identity"
        station = ORDER_STATIONS[investigation_id]
        if investigation_id not in self.state.order_investigations_completed:
            self.state.order_investigations_completed.append(investigation_id)
        shard_id = station["shard_id"]
        if shard_id not in self.state.order_shards:
            self.state.order_shards.append(shard_id)
        self.state.order_corruption = max(0, self.state.order_corruption - 1)
        count = len(self.state.order_investigations_completed)
        self._burst(station["position"], QColor("#7cf3df"), 38)
        self.active_order_investigation = None
        self.scene = "explore"
        save_game(self.state)
        findings = {
            "identity": "RESTORED ENTRY: ELIAN VEY, CHRONOMETER KEEPER.",
            "sequence": "RESTORED ORDER: LOSS, COPY, TRANSFER, FIRE.",
            "authority": "RESTORED AUTHORITY: ORREN VALE, BLACK SUN SEAL.",
        }
        if count == len(ORDER_INVESTIGATION_IDS):
            self._mark_story_flag("order_master_docket_seen", persist=False)
            save_game(self.state)
            self.show_dialogue([
                ("MASTER DOCKET VII-13", findings[investigation_id]),
                ("THE THREE SHARDS", "Their broken edges turn toward one another. Together, they match the trefoil lock on the central chest."),
                ("LAST CLERK", "Vey found the petitions. Marr copied them. Vale sealed the transfer before the fire."),
                ("MARA", "That is the story the surviving pieces tell."),
                ("LAST CLERK", "You do not believe it?"),
                ("MARA", "I believe someone chose which pieces survived."),
                ("LAST CLERK", "So we keep looking."),
            ])
        else:
            reactions = {
                "identity": [
                    ("INDEX OF IDENTITY", findings[investigation_id]),
                    ("LAST CLERK", "They scraped away his name and left the hourglass hanging from his coat."),
                    ("MARA", "That was not careless."),
                    ("LAST CLERK", "Or a hurried one."),
                ],
                "sequence": [
                    ("LEDGER OF SEQUENCE", findings[investigation_id]),
                    ("LAST CLERK", "Marr hid the copy before the Chancellor signed the transfer. The fire came after."),
                    ("MARA", "Read the date again."),
                    ("LAST CLERK", "I did."),
                    ("LAST CLERK", "You expected that."),
                    ("MARA", "I hoped I was wrong."),
                ],
                "authority": [
                    ("SEAL OF AUTHORITY", findings[investigation_id]),
                    ("LAST CLERK", "Vale's seal did not merely approve the transfer. It made the transfer legal."),
                    ("MARA", "He did not hide the order. He made the Archive defend it."),
                ],
            }
            self.show_dialogue(reactions[investigation_id])

    def _begin_order_station_activation(self, investigation_id: str) -> None:
        if self.order_station_activation_effect:
            return
        self.keys.clear()
        self.order_station_activation_effect = {
            "investigation_id": investigation_id,
            "started": self.world_clock,
            "duration": 24,
        }

    def _tick_order_station_activation(self) -> None:
        effect = self.order_station_activation_effect
        if not effect or self.world_clock - effect["started"] < effect["duration"]:
            return
        investigation_id = effect["investigation_id"]
        self.order_station_activation_effect = None
        self._start_order_investigation(investigation_id)

    def _interact_order(self):
        remaining = {
            investigation_id: details["position"]
            for investigation_id, details in ORDER_STATIONS.items()
            if investigation_id not in self.state.order_investigations_completed
        }
        if remaining:
            distance, investigation_id = self._nearest({
                station_id: (
                    QRectF(*ORDER_STATIONS[station_id]["activation_rect"]).center().x(),
                    QRectF(*ORDER_STATIONS[station_id]["activation_rect"]).center().y(),
                )
                for station_id in remaining
            })
            activation_zone = QRectF(*ORDER_STATIONS[investigation_id]["activation_rect"]).adjusted(-12, -12, 12, 12)
            if not activation_zone.contains(QPointF(self.state.player_x, self.state.player_y)):
                self._toast(
                    f"Restore Docket VII-13: {len(self.state.order_investigations_completed)}/3 findings recovered. "
                    "Stand on a station's floor sigil, then press Space."
                )
                return
            self._begin_order_station_activation(investigation_id)
            return
        enemy_id = "misfiled_mimic"
        if enemy_id in self.state.defeated_enemies:
            self.show_dialogue([
                ("LOWER REGISTRY", "DOCKET VII-13 RESTORED. CONTRADICTIONS PRESERVED."),
                ("LAST CLERK", "Good. I was beginning to think it only preserved lies."),
            ])
        elif self.state.order_chest_unlocked:
            self._start_mimic_intro()
        elif self.state.order_chest_gem_assembled:
            self._toast("Drag the Master Docket Gem from your relic belt into the chest's matching trefoil lock.")
        else:
            self._toast("The three docket shards resonate in your belt. Fuse them before opening the suspiciously generous chest.")

    @staticmethod
    def _registry_parts_for_item(item: str) -> set[str]:
        if item.startswith("registry_shard_") and item != "registry_shard_pair":
            return {item.removeprefix("registry_shard_")}
        return set()

    def _try_fuse_registry_shards(self, source: str, target: str) -> None:
        fused = set(self.state.order_fused_shards)
        source_parts = fused if source == "registry_shard_pair" else self._registry_parts_for_item(source)
        target_parts = fused if target == "registry_shard_pair" else self._registry_parts_for_item(target)
        combined = source_parts | target_parts
        if len(combined) < 2 or not combined.issubset(set(self.state.order_shards)):
            self._toast("Only the three Registry shards fit this seal. The docket rejects creative accounting.")
            return
        self.state.order_fused_shards = [shard_id for shard_id in ORDER_SHARDS if shard_id in combined]
        if len(combined) == len(ORDER_SHARDS):
            self.state.order_chest_gem_assembled = True
            self._burst((480, 570), QColor("#f4bf55"), 42)
            self._toast("MASTER DOCKET GEM FORGED - drag it into the central chest's trefoil lock.")
        else:
            self._burst((480, 570), QColor("#7ce9df"), 24)
            self._toast("Two docket shards joined. Add the final finding to complete the chest gem.")
        save_game(self.state)

    @staticmethod
    def _order_chest_lock_drop_rect() -> QRect:
        return QRect(450, 276, 60, 54)

    def _unlock_registry_chest(self) -> None:
        if not self.state.order_chest_gem_assembled or self.state.order_chest_unlocked:
            return
        self.state.order_chest_unlocked = True
        save_game(self.state)
        self._burst(ENEMIES["misfiled_mimic"]["position"], QColor("#f2b34f"), 56)
        self.show_dialogue([
            ("THE CENTRAL CHEST", "The gem seats itself in the lock. Three tumblers answer from somewhere deep inside."),
            ("LAST CLERK", "Three tumblers."),
            ("MARA, THROUGH THE LANTERN", "Step back."),
            ("LAST CLERK", "You say that often."),
            ("THE CENTRAL CHEST", "The lid opens. Something wet blinks between the ledgers."),
            ("LAST CLERK", "Not often enough."),
        ], after="start_mimic")

    def _complete_trial(self, trial_id: str):
        if trial_id in self.state.completed_trials:
            return
        reward = TRIAL_REWARDS[trial_id]
        self.state.completed_trials.append(trial_id)
        if reward["item"] not in self.state.inventory:
            self.state.inventory.append(reward["item"])
        if trial_id not in self.state.rewarded_trials:
            self.state.gold += reward["gold"]
            self.state.rewarded_trials.append(trial_id)
        self.state.player_hp = min(100, self.state.player_hp + 20)
        save_game(self.state)
        details = SEALS[trial_id]
        self._burst((480, 310), QColor(details["color"]), 40)
        lead = []
        if trial_id == "memory" and not self._has_story_flag("memory_vey_whisper_heard"):
            self._mark_story_flag("memory_vey_whisper_heard", persist=False)
            lead = [
                ("THE HALL OF MEMORY", "The three restored hours strike together. A blue lens rises from the joined light."),
                ("VOICE INSIDE THE RECALL LENS", "Mara?"),
                ("LAST CLERK", "You heard that?"),
                ("MARA", "Heard what?"),
                ("LAST CLERK", "A man's voice. He said your name."),
                ("MARA", "What did he sound like?"),
                ("LAST CLERK", "Like he had been trying to reach you for a long time."),
                ("MARA", "Bring me the Lens. Please."),
            ]
        elif trial_id == "mercy" and not self._has_story_flag("mercy_testimonies_read"):
            self._mark_story_flag("mercy_testimonies_read", persist=False)
            lead = [
                ("THE HEARING OF EXCEPTIONS", "Three grants. Three concealed invoices. Silence made none of them lawful."),
                ("LAST CLERK", "Every happy ending left someone outside the frame."),
                ("THE HALL", "THE OMITTED CLAIMANTS ARE RESTORED TO THE RECORD."),
                ("MARA, THROUGH THE LANTERN", "Good. This time the Hall counted everyone."),
                ("THE APPEAL TONIC", "The vial fills only after the Hall records both relief and consequence."),
            ]
        elif trial_id == "order":
            lead = [
                ("LOWER REGISTRY", "DOCKET VII-13 RESTORED. MOTIVE: UNFILED. FINAL RECIPIENT: ERASED."),
                ("LAST CLERK", "It gave us the order, not the reason."),
                ("MARA, THROUGH THE LANTERN", "And easier to bury. Bring the docket back."),
            ]
        save_game(self.state)
        self.show_dialogue(lead + [
            ("HALL TRIAL COMPLETE", f"The {reward['label']} settles into your palm. The Hall releases {reward['gold']} gold with it."),
            ("LAST CLERK", "It gave me gold."),
            ("MARA, THROUGH THE LANTERN", "Count it later. Bring the relic back to the main hall."),
            ("MARA", f"Take the {reward['label']} to {SEALS[trial_id]['name']}. The seal will ask what you understood, not only what you found."),
        ])

    def _toggle_exploration_hud(self):
        self.state.hud_collapsed = not self.state.hud_collapsed
        self.dragged_inventory_item = None
        save_game(self.state)

    @staticmethod
    def _hud_toggle_rect() -> QRect:
        return QRect(898, 548, 42, 36)

    def _explore_items(self) -> list[str]:
        items = [item for item in ITEM_ORDER if item in self.state.inventory]
        if self.memory_active_archive and self.memory_hourglass_found:
            items.append(f"hourglass_{self.memory_active_archive}")
        if "pending_codex" in self.state.inventory:
            items.append("pending_codex")
        if self.state.current_room == "order" and "misfiled_mimic" not in self.state.defeated_enemies:
            if self.state.order_chest_gem_assembled:
                if not self.state.order_chest_unlocked:
                    items.append("registry_chest_gem")
            else:
                fused_order = set(self.state.order_fused_shards)
                for shard_id in self.state.order_shards:
                    if shard_id not in fused_order:
                        items.append(f"registry_shard_{shard_id}")
                if len(fused_order) >= 2:
                    items.append("registry_shard_pair")
        if self.state.vault_key_assembled:
            if not self.state.vault_key_inserted:
                items.append("vault_key")
            return items
        fused = set(self.state.fused_key_parts)
        for trial_id in self.state.key_fragments:
            if trial_id not in fused:
                items.append(f"fragment_{trial_id}")
        if len(fused) >= 2:
            items.append("key_pair")
        return items

    def _explore_item_rects(self) -> dict[str, QRect]:
        items = self._explore_items()
        slot_width = 64
        gap = 12
        total = len(items) * slot_width + max(0, len(items) - 1) * gap
        start_x = max(165, int((GAME_WIDTH - total) / 2))
        return {item: QRect(start_x + index * (slot_width + gap), 562, slot_width, 58) for index, item in enumerate(items)}

    @staticmethod
    def _key_parts_for_item(item: str) -> set[str]:
        if item.startswith("fragment_"):
            return {item.removeprefix("fragment_")}
        return set()

    def _try_fuse_key_items(self, source: str, target: str):
        fused = set(self.state.fused_key_parts)
        source_parts = fused if source == "key_pair" else self._key_parts_for_item(source)
        target_parts = fused if target == "key_pair" else self._key_parts_for_item(target)
        combined = source_parts | target_parts
        if len(combined) < 2 or not combined.issubset(set(self.state.key_fragments)):
            self._toast("Only key fragments fuse here. The relic belt is magical, not a junk drawer.")
            return
        self.state.fused_key_parts = [trial_id for trial_id in SEALS if trial_id in combined]
        if len(combined) == len(SEALS):
            self.state.vault_key_assembled = True
            self._burst((480, 570), QColor("#f3d37a"), 42)
            first_assembly = not self._has_story_flag("key_inscription_seen")
            self._mark_story_flag("key_inscription_seen", persist=False)
            if first_assembly:
                self.show_dialogue([
                    ("MEMORY FRAGMENT", "Seven names remained in wax after they vanished from ink."),
                    ("MERCY FRAGMENT", "Each unanswered cost was charged to someone the record refused to name."),
                    ("ORDER FRAGMENT", "The Black Sun carried the petitions below review."),
                    ("THE COMPLETED KEY", "WE WERE NOT GONE. WE WERE WAITING."),
                    ("LAST CLERK", "That is not an inscription."),
                    ("MARA, THROUGH THE LANTERN", "No. It is a message."),
                ])
            else:
                self._toast("VAULT KEY ASSEMBLED - three impossible fragments, one suspiciously cooperative lock.")
        else:
            self._burst((480, 575), QColor("#67e9e3"), 24)
            self._toast("Two fragments joined. Add the final piece before they reconsider.")
        save_game(self.state)

    def start_battle(self, enemy_id: str = "pending"):
        enemy = ENEMIES[enemy_id]
        self.scene = "battle"
        self.battle_enemy_id = enemy_id
        self.boss_max_hp = enemy["max_hp"]
        self.boss_hp = self.boss_max_hp
        self.state.player_hp = max(1, self.state.player_hp)
        self.focus = 0
        self.guard = False
        self.boss_marked = False
        self.battle_locked = False
        self.hero_combat_pose = "ready"
        self.pending_pose = "idle_a"
        self.enemy_pose = "idle_a"
        self.ability_cooldowns = {key: 0 for key in ABILITY_ORDER}
        self.last_ability_key = None
        self.foresight = False
        self.bleed_damage = 0
        self.battle_items = {item: int(item in self.state.inventory) for item in ITEM_ORDER}
        self.minions = [
            {"hp": 30, "max_hp": 30, "respawn": 0},
            {"hp": 30, "max_hp": 30, "respawn": 0},
            {"hp": 30, "max_hp": 30, "respawn": 0},
        ] if enemy_id == "pending" else []
        self.battle_phase = 1
        self.mimic_sealed_item = None
        self.mimic_sealed_item_turns = 0
        if enemy_id == "misfiled_mimic":
            self.mimic_classification = random.choice(ORDER_INVESTIGATION_IDS)
        self.battle_message = {
            "pending": "Shadow Clerks close ranks around The Pending. Break their guard to reach the throne.",
            "red_tape_wraith": "The Red Tape Wraith tightens every rejected appeal into a single red cord.",
            "misfiled_mimic": "A false classification burns across the Mimic. Answer it with the matching discipline.",
        }[enemy_id]
        self._burst((480, 260), QColor("#a855f7"), 34)
        if enemy_id == "pending":
            for position in self._minion_positions():
                self._burst(position, QColor("#9e4bdf"), 28)

    def _set_enemy_pose(self, pose: str):
        if self.battle_enemy_id == "pending":
            self.pending_pose = pose
        else:
            self.enemy_pose = pose

    def _ability_cooldown(self, key: str) -> int:
        return max(0, self.ability_cooldowns.get(key, 0))

    def _update_battle_idle_pose(self):
        if self.battle_locked:
            return
        self.hero_combat_pose = "ready"
        if self.battle_enemy_id == "pending" and self.boss_hp <= self.boss_max_hp * 0.3:
            self.pending_pose = "stagger" if (self.world_clock // 30) % 2 == 0 else "idle_b"
        else:
            pose = "idle_a" if (self.world_clock // 30) % 2 == 0 else "idle_b"
            self._set_enemy_pose(pose)

    def battle_action(self, key: str):
        if self.battle_locked:
            return
        definition = ABILITY_DEFS.get(key)
        if definition is None:
            return
        cooldown = self._ability_cooldown(key)
        if cooldown:
            self.battle_message = f"{definition['name']} needs {cooldown}s before it can be used again."
            return
        if key == "R" and self.focus < 3:
            self.battle_message = f"Final Redline needs 3 Focus. You have {self.focus}."
            return

        self.battle_locked = True
        self.hero_combat_pose = definition["action"]
        self._set_enemy_pose("hit")
        self.ability_cooldowns[key] = definition["cooldown"]
        self.last_ability_key = key

        if self.bleed_damage:
            self.state.player_hp = max(1, self.state.player_hp - self.bleed_damage)
            self.bleed_damage = 0

        minion_target = self._first_living_minion() if self.battle_enemy_id == "pending" else None
        if key == "Q" and minion_target is not None:
            minion_damage = random.randint(17, 23)
            self._damage_minion(minion_target, minion_damage)
            damage = 0
            self.focus = min(3, self.focus + 1)
            self.battle_message = f"Quill Slash deals {minion_damage} to a Shadow Clerk. Its outline remains bound to the throne."
        elif key == "Q":
            damage = self._marked_damage(random.randint(17, 23))
            self.focus = min(3, self.focus + 1)
            self.battle_message = f"Quill Slash deals {damage}. Black ink tears across the enemy's record."
        elif key == "W":
            damage = self._marked_damage(random.randint(7, 11))
            self.guard = True
            self.focus = min(3, self.focus + 1)
            self.battle_message = f"File Ward deals {damage} and braces for impact."
        elif key == "E":
            damage = random.randint(10, 14)
            self.boss_marked = True
            self.focus = min(3, self.focus + 1)
            self.battle_message = f"Wax Mark deals {damage}. The next damaging skill is amplified."
        else:
            damage = self._marked_damage(random.randint(40, 50))
            self.focus = 0
            self.battle_message = f"FINAL REDLINE deals {damage}. The marked clause splits from the record."
            self._burst((700, 275), QColor("#ff668f"), 30)
            if self.battle_enemy_id == "pending":
                for index, minion in enumerate(self.minions):
                    if minion["hp"] > 0:
                        self._damage_minion(index, 24)

        if self.battle_enemy_id == "misfiled_mimic" and damage > 0:
            if self.mimic_classification not in ORDER_INVESTIGATION_IDS:
                self.mimic_classification = "identity"
            required = {"identity": "Q", "sequence": "W", "authority": "E"}[self.mimic_classification]
            if key == "R":
                damage = round(damage * 1.25)
                self.battle_message += " Final Redline cuts across every false classification."
            elif key == required:
                damage = round(damage * 1.6)
                self.battle_message += f" {self.mimic_classification.title()} is restored; the false drawer tears open."
            else:
                damage = max(1, round(damage * 0.55))
                self.battle_message += f" The {self.mimic_classification.title()} sigil absorbs the mismatched filing."
            choices = [item for item in ORDER_INVESTIGATION_IDS if item != self.mimic_classification]
            next_classification = random.choice(choices)
            self.mimic_classification = (
                next_classification if next_classification in ORDER_INVESTIGATION_IDS else choices[0]
            )

        if self.battle_enemy_id == "pending" and damage > 0:
            living = sum(1 for minion in self.minions if minion["hp"] > 0)
            if living:
                original = damage
                damage = max(1, round(damage * 0.35))
                self.battle_message += f" The Shadow Court absorbs {original - damage}."
        self.boss_hp -= damage
        self.boss_hp = max(0, self.boss_hp)
        if self.boss_hp == 0:
            for minion in self.minions:
                minion["hp"] = 0
                minion["respawn"] = -1
            self._set_enemy_pose("defeat" if self.battle_enemy_id == "pending" else "hit")
            self.battle_message = f"{ENEMIES[self.battle_enemy_id]['name']} is defeated. Its binding mark goes dark."
            self._burst((700, 260), QColor("#66f6e8"), 55)
            QTimer.singleShot(1200, self._win_battle)
            return
        if self.battle_enemy_id == "pending" and self.battle_phase == 1 and self.boss_hp <= self.boss_max_hp // 2:
            self.battle_phase = 2
            for minion in self.minions:
                minion["hp"] = minion["max_hp"]
                minion["respawn"] = 0
            self.pending_pose = "vortex"
            self.battle_message = "The Pending opens the Final Docket. The names inside begin speaking at once; the Shadow Court reforms faster."
            self._burst((700, 250), QColor("#d34cff"), 60)
        self._burst((700, 275), QColor(definition["color"]), 18)
        QTimer.singleShot(680, self._boss_turn)

    def _first_living_minion(self) -> int | None:
        return next((index for index, minion in enumerate(self.minions) if minion["hp"] > 0), None)

    def _damage_minion(self, index: int, damage: int):
        minion = self.minions[index]
        minion["hp"] = max(0, minion["hp"] - damage)
        if minion["hp"] == 0 and self.boss_hp > 0:
            minion["respawn"] = 2
            self._burst(self._minion_positions()[index], QColor("#9c55dc"), 20)

    def _marked_damage(self, damage: int) -> int:
        if not self.boss_marked:
            return damage
        self.boss_marked = False
        return round(damage * 1.3)

    def use_battle_item(self, item: str):
        if self.battle_locked or self.battle_items.get(item, 0) <= 0:
            return
        if item == self.mimic_sealed_item and self.mimic_sealed_item_turns > 0:
            self.battle_message = (
                f"The Mimic has swallowed {RELIC_INFO[item][0]}. It returns in "
                f"{self.mimic_sealed_item_turns} turn{'s' if self.mimic_sealed_item_turns != 1 else ''}."
            )
            return
        if item == "recall_lens":
            self.focus = min(3, self.focus + 1)
            self.foresight = True
            self.hero_combat_pose = "e_mark"
            self.battle_message = "The Recall Lens grants 1 Focus. For an instant, you remember the enemy's next movement before it happens."
        elif item == "appeal_tonic":
            if self.state.player_hp >= 100:
                self.battle_message = "Your HP is already full. Save the Appeal Tonic."
                return
            healed = min(35, 100 - self.state.player_hp)
            self.state.player_hp += healed
            self.hero_combat_pose = "w_ward"
            self.battle_message = f"Appeal Tonic restores {healed} HP. It tastes of bitter berries and hot copper."
        else:
            if not any(self._ability_cooldown(key) for key in ABILITY_ORDER):
                self.battle_message = "The Reset Compass finds no exhausted ability to restore."
                return
            self.ability_cooldowns = {key: 0 for key in ABILITY_ORDER}
            self.hero_combat_pose = "e_mark"
            self.battle_message = "The Reset Compass turns backward. Every ability is ready again."
        self.battle_items[item] -= 1
        self.last_ability_key = None
        self.battle_locked = True
        QTimer.singleShot(620, self._boss_turn)

    def _boss_turn(self):
        if self.scene != "battle" or self.boss_hp <= 0:
            return
        self.hero_combat_pose = "ready"
        self._set_enemy_pose("windup" if self.battle_enemy_id == "pending" else "attack")
        self.battle_message = f"{ENEMIES[self.battle_enemy_id]['name']} gathers itself to strike."
        QTimer.singleShot(330, self._resolve_boss_attack)

    def _resolve_boss_attack(self):
        if self.scene != "battle" or self.boss_hp <= 0:
            return
        enemy = ENEMIES[self.battle_enemy_id]
        attack = random.choice(enemy["attacks"])
        damage = random.randint(*enemy["damage_range"])
        effect = ""
        if self.battle_enemy_id == "red_tape_wraith":
            if attack == "Binding Clause":
                self.ability_cooldowns["W"] = max(2, self.ability_cooldowns["W"])
                effect = " File Ward is bound for one turn."
            elif attack == "Crimson Continuance":
                healed = min(6, self.boss_max_hp - self.boss_hp)
                self.boss_hp += healed
                effect = f" The Wraith recovers {healed} HP."
            else:
                damage += 3
                effect = " The clause lands with procedural enthusiasm."
        elif self.battle_enemy_id == "misfiled_mimic":
            if attack == "Drawer Slam":
                damage += 4
                effect = " The filing hardware was not decorative."
            elif attack == "Paper Cut Exhibit":
                self.bleed_damage = 4
                effect = " Your next action costs 4 HP."
            elif attack == "Missing Attachment":
                available = [item for item, count in self.battle_items.items() if count > 0]
                if available:
                    sealed_item = random.choice(available)
                    self.mimic_sealed_item = sealed_item if sealed_item in available else available[0]
                    self.mimic_sealed_item_turns = 2
                    effect = f" It swallows {RELIC_INFO[self.mimic_sealed_item][0]} for one turn."
                else:
                    drained = min(1, self.focus)
                    self.focus -= drained
                    effect = f" It finds no relic and steals {drained} Focus instead."
            elif attack == "False Classification":
                self.mimic_classification = random.choice(ORDER_INVESTIGATION_IDS)
                effect = " The active sigil is forcibly reclassified."
            else:
                healed = min(7, self.boss_max_hp - self.boss_hp)
                self.boss_hp += healed
                effect = f" A duplicate record restores {healed} HP."
        elif attack == "Request for Clarification":
            drained = min(1, self.focus)
            self.focus -= drained
            effect = f" You lose {drained} Focus."
        elif attack == "Infinite Attachment":
            damage += 4
            effect = " The attachment has attachments."
        else:
            damage += 2
            effect = " Reply All remains undefeated as a concept."
        if self.battle_enemy_id == "pending":
            attendants = sum(1 for minion in self.minions if minion["hp"] > 0)
            if attendants:
                escort_damage = sum(random.randint(2, 4) for _ in range(attendants))
                damage += escort_damage
                effect += f" {attendants} Shadow Clerk{'s' if attendants != 1 else ''} add {escort_damage} damage."
            if self.battle_phase == 2:
                damage += 4
                effect += " The Final Docket adds 4 damage."
        if self.guard:
            damage = max(1, damage // 2)
            suffix = " Your ward catches most of it."
        else:
            suffix = ""
        if self.foresight:
            damage = max(1, damage // 2)
            self.foresight = False
            suffix += " Recall Lens predicts the impact."
        self.guard = False
        self.state.player_hp = max(0, self.state.player_hp - damage)
        if self.battle_enemy_id == "pending":
            self.pending_pose = "vortex" if attack == "Infinite Attachment" else "release"
        else:
            self.enemy_pose = "attack"
        self.hero_combat_pose = "hit"
        enemy_name = enemy["name"]
        self.battle_message = f"{enemy_name} uses {attack} for {damage}.{suffix}{effect}"
        self._burst((255, 340), QColor("#9b6cff"), 16)
        if self.state.player_hp <= 0:
            self.battle_locked = True
            QTimer.singleShot(850, self._recover_from_defeat)
        else:
            QTimer.singleShot(620, self._finish_boss_turn)

    def _finish_boss_turn(self):
        if self.scene != "battle":
            return
        self.hero_combat_pose = "ready"
        for key, remaining in self.ability_cooldowns.items():
            if key != self.last_ability_key:
                self.ability_cooldowns[key] = max(0, remaining - 1)
        self.last_ability_key = None
        if getattr(self, "mimic_sealed_item_turns", 0) > 0:
            self.mimic_sealed_item_turns -= 1
            if self.mimic_sealed_item_turns == 0:
                self.mimic_sealed_item = None
        if getattr(self, "battle_enemy_id", None) == "pending" and getattr(self, "boss_hp", 0) > 0:
            revived = 0
            for minion in self.minions:
                if minion["hp"] == 0 and minion["respawn"] > 0:
                    minion["respawn"] = max(0, minion["respawn"] - (2 if self.battle_phase == 2 else 1))
                    if minion["respawn"] == 0:
                        minion["hp"] = minion["max_hp"]
                        revived += 1
            if revived:
                self.battle_message = f"{revived} Shadow Clerk{'s reform' if revived != 1 else ' reforms'} from names still bound to the Final Docket."
        self.battle_locked = False
        self._update_battle_idle_pose()

    def _recover_from_defeat(self):
        self._start_defeat_cinematic()

    def _finish_defeat_recovery(self):
        self.state.player_hp = 100
        self.state.current_room = "hub"
        self.state.player_x, self.state.player_y = ROOM_SAFE_SPAWNS["hub"]
        first_memory_check = not self._has_story_flag("first_vault_defeat_memory_check_seen")
        if first_memory_check:
            self._mark_story_flag("first_vault_defeat_memory_check_seen", persist=False)
        save_game(self.state)
        lines = [
            ("MARA", "Stay down."),
            ("LAST CLERK", "I was not going anywhere."),
            ("MARA", "You were trying to stand."),
            ("LAST CLERK", "Did we win?"),
            ("MARA", "No. But you are alive, and the Vault is still open."),
        ]
        if first_memory_check:
            lines.extend([
                ("MARA", "Before you entered, what did I ask you to bring back?"),
                ("LAST CLERK", "The same number of souls."),
                ("MARA", "All right."),
                ("LAST CLERK", "You thought I forgot."),
                ("MARA", "For a moment, you looked at me and there was nothing there."),
                ("LAST CLERK", "Mara--"),
                ("MARA", "Not yet. Just stay with me."),
            ])
        self.show_dialogue(lines, portraits=True)

    def _win_battle(self):
        if self.battle_enemy_id != "pending":
            enemy = ENEMIES[self.battle_enemy_id]
            if self.battle_enemy_id not in self.state.defeated_enemies:
                self.state.defeated_enemies.append(self.battle_enemy_id)
            if self.battle_enemy_id == "red_tape_wraith":
                save_game(self.state)
                self.scene = "explore"
                self.battle_locked = True
                self.state.player_x, self.state.player_y = 480, 410
                if (
                    self.state.mercy_hearing_completed
                    and len(self.state.mercy_appeals_completed) == len(MERCY_APPEAL_IDS)
                ):
                    self.show_dialogue([
                        ("RED TAPE WRAITH", "APPEAL CLOSED. CONSEQUENCES... RETURNED."),
                        ("LAST CLERK", "It was protecting the lie."),
                        ("MARA, THROUGH THE LANTERN", "Yes. The rulings fed it every time a cost disappeared from the record."),
                        ("LAST CLERK", "Then let's make sure the record remembers everyone this time."),
                    ], portraits=True, after="complete_trial:mercy")
                else:
                    # Older saves may have fought the guardian before the
                    # hearing. Keep their progress valid and let them finish
                    # the three appeals without forcing a second battle.
                    self.show_dialogue([
                        ("RED TAPE WRAITH", "The binding cords fall. Three reliquaries wake around the chamber."),
                        ("LAST CLERK", "Was that the guard?"),
                        ("MARA, THROUGH THE LANTERN", "It used to be a clerk."),
                        ("LAST CLERK", "That is worse."),
                        ("MARA", "The reliquaries are awake. Hear each appeal, and look for the person missing from its happy ending."),
                    ])
                return
            self._complete_trial(enemy["trial"])
            self.battle_locked = True
            return
        self._start_victory_cinematic()

    def _finish_level_victory(self):
        self.state.boss_defeated = True
        self.state.level_complete = True
        self.state.player_hp = max(1, self.state.player_hp)
        if "pending_codex" not in self.state.inventory:
            self.state.inventory.append("pending_codex")
            self.state.gold += 150
        rewarded = grant_completion_reward(self.state)
        first_epilogue = not self._has_story_flag("level_one_epilogue_seen")
        if first_epilogue:
            self._mark_story_flag("pending_human_names_seen", persist=False)
            self._mark_story_flag("level_one_epilogue_seen", persist=False)
            self._mark_story_flag("orin_post_credit_seen", persist=False)
        save_game(self.state)
        self._burst((480, 300), QColor("#66f6e8"), 70)
        self.toast = f"LEVEL COMPLETE  +{COMPLETION_COINS} COINS" if rewarded else "LEVEL COMPLETE"
        if first_epilogue:
            self.show_dialogue(list(LEVEL_EPILOGUE), portraits=True, after="finish_level_ending")
        else:
            self.scene = "ending"
            self.battle_locked = True

    def _toast(self, text: str):
        self.toast = text
        self.toast_ticks = 75

    def _burst(self, position, color: QColor, count: int):
        x, y = position
        for _ in range(count):
            angle = random.random() * math.tau
            speed = random.uniform(0.5, 3.0)
            self.particles.append({
                "x": float(x), "y": float(y),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 0.5,
                "life": random.randint(22, 50),
                "max": 50,
                "color": QColor(color),
                "size": random.randint(2, 5),
            })

    def _update_particles(self):
        alive = []
        for particle in self.particles:
            particle["x"] += particle["vx"]
            particle["y"] += particle["vy"]
            particle["vy"] += 0.025
            particle["life"] -= 1
            if particle["life"] > 0:
                alive.append(particle)
        self.particles = alive

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self.scene == "seal_puzzle":
            # Do not spend a frame painting the room and HUD underneath a
            # focused puzzle stage; they are intentionally absent here.
            self._paint_seal_puzzle(painter)
        elif self.scene == "title":
            self._paint_title_background(painter)
            self._paint_title(painter)
        else:
            background = self.backgrounds.get(self.state.current_room, self.backgrounds["hub"])
            painter.drawPixmap(self.rect(), background)
            painter.fillRect(self.rect(), QColor(4, 5, 15, 26))
            if self.scene == "cinematic":
                self._paint_cinematic(painter)
            elif self.scene == "battle":
                self._paint_battle(painter)
            else:
                self._paint_world(painter)
                if self.scene == "dialogue":
                    self._paint_dialogue(painter)
                elif self.scene == "order_investigation":
                    self._paint_order_investigation(painter)
                elif self.scene == "mercy_appeal":
                    self._paint_mercy_appeal(painter)
                elif self.scene == "ending":
                    self._paint_ending(painter)
        # World particles belong to the room behind the interface. Keeping them
        # visible over a seal puzzle breaks the focused, self-contained stage.
        if self.scene != "seal_puzzle":
            self._paint_particles(painter)

    def _paint_cinematic(self, painter: QPainter):
        if not self.cinematic_steps:
            return
        first_frame, second_frame, speaker, text = self.cinematic_steps[self.cinematic_index]
        painter.fillRect(self.rect(), QColor(3, 3, 12, 82))
        if self.cinematic_kind == "intro":
            if first_frame <= 2:
                throne_cycle = (0, 0, 1, 0, 2, 0)
                first_frame = throne_cycle[(self.world_clock // 22) % len(throne_cycle)]
            if second_frame <= 3:
                hero_cycle = (0, 0, 1, 0, 2, 0, 3, 0)
                second_frame = hero_cycle[(self.world_clock // 24) % len(hero_cycle)]
            boss_target = (
                QRectF(374, 74, 212, 230)
                if self.cinematic_index <= 2
                else QRectF(300, 48, 360, 390)
            )
            self._paint_sheet_cell(painter, self.pending_throne_sheet, first_frame, 6, boss_target)
            self._paint_sheet_cell(painter, self.archivist_confrontation_sheet, second_frame, 6, QRectF(55, 220, 300, 280))
        elif self.cinematic_kind == "defeat":
            self._paint_sheet_cell(painter, self.mara_rescue_sheet, first_frame, 4, QRectF(145, 58, 670, 470))
        elif self.cinematic_kind == "mimic_intro":
            mimic = self.trial_enemies.get("misfiled_mimic", {}).get(
                "idle_b" if first_frame % 2 else "idle_a", QPixmap()
            )
            if not mimic.isNull():
                self._draw_pixmap_contained(painter, QRectF(485, 72, 360, 390), mimic)
            hero = self.hero_combat.get("ready", QPixmap())
            if not hero.isNull():
                self._draw_pixmap_contained(painter, QRectF(80, 145, 315, 320), hero)
        else:
            self._paint_sheet_cell(painter, self.pending_victory_sheet, first_frame, 4, QRectF(120, 65, 720, 450))
        rect = QRectF(54, 488, 852, 126)
        self._panel(painter, rect, QColor(5, 7, 17, 244), QColor("#7ae7df"), 2)
        painter.setPen(QColor("#f0d078"))
        self._draw_fitted_text(painter, QRectF(78, 502, 790, 22), speaker, 10, 6.5, True, Qt.AlignLeft | Qt.AlignVCenter)
        painter.setPen(QColor("#edf2f3"))
        self._draw_fitted_text(painter, QRectF(78, 531, 770, 52), text, 9.5, 6.5, False, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        painter.setPen(QColor("#77e8df"))
        self._draw_fitted_text(painter, QRectF(760, 589, 108, 14), "CONTINUE >", 6.5, 4.5, True, Qt.AlignRight)

    def _paint_sheet_cell(self, painter: QPainter, sheet: QPixmap, frame: int, count: int, target: QRectF):
        if sheet.isNull():
            return
        width = sheet.width() / count
        source = QRectF(frame * width, 0, width, sheet.height())
        self._draw_pixmap_contained(painter, target, sheet.copy(source.toRect()))

    def _font(self, size: float, bold: bool = False, family: str | None = None) -> QFont:
        font = QFont(family or self._font_family)
        font.setPointSizeF(float(size))
        font.setWeight(QFont.Bold if bold else QFont.Normal)
        return font

    def _draw_fitted_text(
        self,
        painter: QPainter,
        rect: QRectF | QRect,
        text: str,
        max_size: float,
        min_size: float = 7.0,
        bold: bool = False,
        flags: int = Qt.AlignCenter | Qt.TextWordWrap,
        font_family: str | None = None,
    ) -> float:
        """Draw text at the largest half-point size that fits its assigned box."""
        target = QRectF(rect)
        selected = self._font(min_size, bold, font_family)
        step = int(round(max_size * 2))
        minimum = int(round(min_size * 2))
        while step >= minimum:
            candidate = self._font(step / 2, bold, font_family)
            bounds = QFontMetricsF(candidate).boundingRect(target, int(flags), text)
            if bounds.width() <= target.width() + 0.5 and bounds.height() <= target.height() + 0.5:
                selected = candidate
                break
            step -= 1
        painter.setFont(selected)
        painter.save()
        # Preserve any parent viewport/card clipping. Replacing the clip here
        # allowed partially scrolled labels to paint over dossier headers.
        painter.setClipRect(target, Qt.IntersectClip)
        painter.drawText(target, int(flags), text)
        painter.restore()
        return selected.pointSizeF()

    def _paint_title_background(self, painter: QPainter):
        """Layer authored Bellglass-Fire frames over the lore-specific title art."""
        if self.title_background.isNull():
            painter.drawPixmap(self.rect(), self.backgrounds["hub"])
            return
        painter.drawPixmap(self.rect(), self.title_background)
        if not self.title_bellglass_fire_frames:
            return
        frame = self.title_bellglass_fire_frames[(self.world_clock // 9) % len(self.title_bellglass_fire_frames)]
        painter.save()
        painter.setOpacity(0.42)
        self._draw_pixmap_contained(painter, QRectF(18, 386, 146, 196), frame)
        painter.translate(GAME_WIDTH, 0)
        painter.scale(-1, 1)
        self._draw_pixmap_contained(painter, QRectF(18, 386, 146, 196), frame)
        painter.restore()

        smoke_frame = self.title_smoke_frames[(self.world_clock // 15) % len(self.title_smoke_frames)] if self.title_smoke_frames else QPixmap()
        if not smoke_frame.isNull():
            painter.save()
            painter.setOpacity(0.30)
            self._draw_pixmap_cover(painter, QRectF(-26, 452, 1012, 188), smoke_frame, 0.80)
            painter.restore()

        sparks_frame = self.title_sparks_frames[(self.world_clock // 10) % len(self.title_sparks_frames)] if self.title_sparks_frames else QPixmap()
        if not sparks_frame.isNull():
            painter.save()
            painter.setOpacity(0.36)
            self._draw_pixmap_contained(painter, QRectF(-24, 126, 210, 330), sparks_frame)
            painter.translate(GAME_WIDTH, 0)
            painter.scale(-1, 1)
            self._draw_pixmap_contained(painter, QRectF(-24, 126, 210, 330), sparks_frame)
            painter.restore()

    def _paint_title(self, painter: QPainter):
        title_wash = QLinearGradient(0, 0, 0, GAME_HEIGHT)
        title_wash.setColorAt(0.0, QColor(2, 4, 13, 68))
        title_wash.setColorAt(0.42, QColor(3, 5, 15, 124))
        title_wash.setColorAt(1.0, QColor(2, 3, 10, 92))
        painter.fillRect(self.rect(), title_wash)

        title_frame = (self.world_clock // 11) % 4
        title_bob = int(round(math.sin(self.world_clock / 15.0) * 1.5))
        caption_bob = int(round(math.sin(self.world_clock / 17.0 + 1.1)))
        flourish = self.title_flourish_frames[title_frame] if self.title_flourish_frames else QPixmap()
        if not flourish.isNull():
            painter.save()
            painter.setOpacity(0.72)
            self._draw_pixmap_cover(painter, QRectF(204, 194 + title_bob, 552, 48), flourish, 0.57)
            painter.restore()

        painter.setPen(QColor("#f8f3df"))
        self._draw_fitted_text(
            painter, QRect(20, 42 + title_bob, 920, 205), GAME_TITLE, 72, 48, False,
            font_family=self._title_font_family,
        )
        painter.setPen(QColor("#8bf5ef"))
        self._draw_fitted_text(
            painter, QRect(124, 244 + caption_bob, 712, 42), GAME_CAPTION, 30, 16, False,
            font_family=self._title_caption_font_family,
        )
        self._paint_title_button(
            painter, TITLE_CONTINUE_RECT, "CONTINUE", "continue", self.title_continue_button
        )
        self._paint_title_button(
            painter, TITLE_NEW_GAME_RECT, "NEW GAME", "new_game", self.title_new_game_button
        )
        painter.setPen(QColor(170, 175, 195))
        self._draw_fitted_text(
            painter,
            QRect(80, 574, 800, 24),
            "ARROW KEYS TO MOVE   |   SPACE / ENTER TO INTERACT   |   QWER IN COMBAT   |   ESC TO EXIT",
            9,
            6,
            flags=Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _paint_world(self, painter: QPainter):
        dynamic_draws = [(self.state.player_y, self._paint_hero)]
        if self.state.current_room == "memory":
            self._paint_memory_search_props(painter)
            self._paint_memory_archive_activation_markers(painter)
            for spec in ROOM_ENVIRONMENT_SPRITES["memory"]:
                dynamic_draws.append((spec["position"][1], lambda target, item=spec: self._paint_environment_sprite(target, item)))
        else:
            if self.state.current_room == "order":
                self._paint_order_station_activation_markers(painter)
            self._paint_environment_sprites(painter)
            if self.state.current_room == "mercy":
                self._paint_mercy_reliquaries(painter)
                self._paint_mercy_activation_markers(painter)
            if self.state.current_room == "hub":
                # Hall markers sit on the seal platforms. Painting them after
                # the authored plinth sprites keeps their perimeter readable.
                self._paint_hub_seal_activation_markers(painter)
        if self.state.current_room == "hub":
            dynamic_draws.append((CLERK_POSITION[1], self._paint_clerk))
        elif self.state.current_room == "mercy":
            enemy_id = self._active_mercy_enemy_id()
            if enemy_id:
                enemy = ENEMIES[enemy_id]
                dynamic_draws.append((enemy["position"][1], lambda target, eid=enemy_id: self._paint_trial_enemy(target, eid)))
        for _, draw in sorted(dynamic_draws, key=lambda entry: entry[0]):
            draw(painter)
        if self.state.current_room == "memory":
            self._paint_memory_trial(painter)
        if self.state.current_room == "hub":
            self._paint_vault_lock(painter)
        elif self.state.current_room == "order":
            self._paint_order_chest_lock(painter)
        self._paint_room_passage_labels(painter)
        self._paint_hud(painter)
        self._paint_exploration_inventory(painter)
        if self.hovered_passage_marker:
            self._paint_passage_tooltip(painter, self.hovered_passage_marker)
        if self.hovered_memory_archive:
            self._paint_memory_archive_tooltip(painter, self.hovered_memory_archive)
        if self.toast_ticks > 0:
            self._paint_toast(painter, self.toast)

    def _paint_room_passage_labels(self, painter: QPainter) -> None:
        """Render authored animated wayfinders; names are revealed only on hover."""
        frame = (self.world_clock // 18) % 2
        travel = 3.5 * math.sin(self.world_clock / 7)
        for marker in self._passage_marker_specs():
            marker_frame = 0 if marker.get("locked") else frame
            target = QRectF(marker["rect"])
            if not marker.get("locked"):
                direction = marker["direction"]
                if direction == "left":
                    target.translate(travel, 0)
                elif direction == "right":
                    target.translate(-travel, 0)
                elif direction == "up":
                    target.translate(0, travel)
                else:
                    target.translate(0, -travel)
            painter.save()
            painter.setOpacity(0.45 if marker.get("locked") else 0.92)
            self._paint_passage_arrow_frame(
                painter,
                marker["direction"],
                marker_frame,
                target,
            )
            painter.restore()

    def _paint_clerk(self, painter: QPainter):
        x, y = CLERK_POSITION
        if not self.mara_idle_sheet.isNull():
            frame = self._mara_idle_frame()
            cell_width = self.mara_idle_sheet.width() // 4
            source = QRect(frame * cell_width, 0, cell_width, self.mara_idle_sheet.height())
            idle_bob = -1 if frame == 1 else 0
            painter.drawPixmap(
                QRectF(x - 34, y - 91 + idle_bob, 68, 106),
                self.mara_idle_sheet,
                QRectF(source),
            )
        label_rect = self._safe_world_label_rect(QRectF(x - 50, y + 15, 100, 20))
        if label_rect:
            painter.setPen(QColor("#f7d372"))
            self._draw_fitted_text(painter, label_rect, "MARA", 8, 6, True)

    def _mara_idle_frame(self) -> int:
        """Give Mara a continuous one-second breathing and gesture cycle."""
        sequence = (0, 1, 0, 2, 0, 1, 0, 3)
        return sequence[(self.world_clock // 30) % len(sequence)]

    def _paint_memory_search_props(self, painter: QPainter) -> None:
        for prop in MEMORY_SEARCH_OBJECTS:
            searched = prop["id"] in self.memory_searched_objects
            search_enabled = (
                self.memory_active_archive
                and not self.memory_hourglass_found
                and not searched
            )
            if prop.get("embedded"):
                if search_enabled:
                    self._paint_embedded_memory_search_outline(painter, prop)
                continue
            frame = self.memory_search_prop_frames.get(prop["id"], QPixmap())
            if frame.isNull():
                continue
            target = QRectF(*prop["rect"])
            if search_enabled:
                glow = self.memory_search_prop_glows.get(prop["id"], QPixmap())
                pulse = 0.14 + 0.07 * (0.5 + 0.5 * math.sin(self.world_clock / 10 + prop["atlas_index"]))
                offsets = ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, -2), (-2, 2), (2, 2))
                painter.save()
                painter.setOpacity(pulse)
                for dx, dy in offsets:
                    painter.drawPixmap(target.translated(dx, dy), glow, QRectF(glow.rect()))
                painter.restore()
            painter.save()
            painter.setOpacity(0.48 if searched else 0.9)
            painter.drawPixmap(target, frame, QRectF(frame.rect()))
            painter.restore()

    def _paint_embedded_memory_search_outline(self, painter: QPainter, prop: dict) -> None:
        """Pulse along baked furniture edges without tinting its whole crop."""
        glow = self.memory_embedded_search_glows.get(prop["id"], QPixmap())
        if glow.isNull():
            return
        target = QRectF(*prop["rect"])
        phase = self.world_clock / 11 + sum(ord(char) for char in prop["id"]) * 0.07
        pulse = 0.5 + 0.5 * math.sin(phase)
        painter.save()
        painter.setOpacity(0.20 + 0.12 * pulse)
        painter.drawPixmap(target, glow, QRectF(glow.rect()))
        frame = self.memory_embedded_search_frames.get(prop["id"], QPixmap())
        if not frame.isNull():
            painter.setOpacity(1.0)
            painter.drawPixmap(target, frame, QRectF(frame.rect()))
        details = self.memory_embedded_search_details.get(prop["id"], QPixmap())
        if not details.isNull():
            painter.setOpacity(0.12 + 0.08 * pulse)
            painter.drawPixmap(target, details, QRectF(details.rect()))
        painter.restore()

    def _paint_memory_archive_activation_markers(self, painter: QPainter) -> None:
        """Animate idle, proximity, and rune-lock states at exact floor zones."""
        if self.memory_restoration_pending:
            return
        if not all(self.archive_activation_marker_frames.values()):
            return
        player = QPointF(self.state.player_x, self.state.player_y)
        effect = self.memory_activation_effect
        for plinth in MEMORY_PLINTHS:
            if plinth["id"] in self.state.memory_archives_completed:
                continue
            zone = QRectF(*plinth["activation_rect"])
            if effect:
                if plinth["id"] != effect["archive_id"]:
                    continue
                age = max(0, self.world_clock - effect["started"])
                frame_index = min(3, age * 4 // max(1, effect["duration"]))
                frame = self.archive_activation_marker_frames["activation"][frame_index]
                # Keep the same floor width while giving the rim-origin beams
                # vertical room to rise around the hero.
                target = QRectF(zone.center().x() - 41, zone.center().y() - 50, 82, 92)
                opacity = 1.0
            elif self.memory_active_archive:
                continue
            elif zone.contains(player):
                frame = self.archive_activation_marker_frames["proximity"][(self.world_clock // 5) % 4]
                target = QRectF(zone.center().x() - 41, zone.center().y() - 50, 82, 92)
                opacity = 1.0
            else:
                frame = self.archive_activation_marker_frames["idle"][(self.world_clock // 10) % 4]
                target = zone.adjusted(-10, -9, 10, 9)
                opacity = 0.76
            painter.save()
            painter.setOpacity(opacity)
            self._draw_pixmap_contained(painter, target, frame)
            if effect and self.archive_activation_beam_frames:
                beam = self.archive_activation_beam_frames[frame_index]
                beam_target = QRectF(
                    zone.center().x() - 45,
                    zone.center().y() - 155,
                    90,
                    175,
                )
                painter.setOpacity((0.78, 0.94, 1.0, 0.56)[frame_index])
                painter.drawPixmap(beam_target, beam, QRectF(beam.rect()))
            painter.restore()

    def _paint_order_station_activation_markers(self, painter: QPainter) -> None:
        """Give every Registry discipline its own compact floor sigil."""
        player = QPointF(self.state.player_x, self.state.player_y)
        effect = self.order_station_activation_effect
        for investigation_id, station in ORDER_STATIONS.items():
            if investigation_id in self.state.order_investigations_completed:
                continue
            frames = self.registry_activation_marker_frames.get(investigation_id, ())
            if not frames:
                continue
            zone = QRectF(*station["activation_rect"])
            if effect and effect["investigation_id"] == investigation_id:
                age = max(0, self.world_clock - effect["started"])
                frame_index = min(3, age * 4 // max(1, effect["duration"]))
                opacity = 1.0
            elif effect:
                continue
            elif zone.adjusted(-12, -12, 12, 12).contains(player):
                frame_index = 1 + (self.world_clock // 7) % 2
                opacity = 0.98
            else:
                frame_index = 0
                opacity = 0.78
            target = QRectF(zone.center().x() - 42, zone.center().y() - 32, 84, 64)
            painter.save()
            painter.setOpacity(opacity)
            self._draw_pixmap_contained(painter, target, frames[frame_index])
            painter.restore()

    def _paint_hub_seal_activation_markers(self, painter: QPainter) -> None:
        """Render compact sigils on reachable floor beside each Hall seal."""
        player = QPointF(self.state.player_x, self.state.player_y)
        effect = self.hub_seal_activation_effect
        for trial_id, details in SEALS.items():
            if trial_id in self.state.completed_seal_puzzles:
                continue
            frames = self.hub_seal_marker_frames.get(trial_id, ())
            if len(frames) < 4:
                continue
            marker_center = QPointF(*HUB_SEAL_MARKER_CENTERS[trial_id])
            distance = math.hypot(player.x() - marker_center.x(), player.y() - marker_center.y())
            if effect and effect["trial_id"] == trial_id:
                age = max(0, self.world_clock - effect["started"])
                frame_index = min(3, 2 + age * 2 // max(1, effect["duration"]))
                opacity = 1.0
                scale = 1.05 + 0.03 * math.sin(age / 2.4)
            elif effect:
                continue
            elif distance <= self.INTERACT_DISTANCE + 34:
                frame_index = 1
                opacity = 0.96
                scale = 1.02
            else:
                frame_index = 0
                opacity = 0.70
                scale = 1.0
            width, height = 104 * scale, 92 * scale
            target = QRectF(
                marker_center.x() - width / 2,
                marker_center.y() - height / 2,
                width,
                height,
            )
            painter.save()
            painter.setOpacity(opacity)
            self._draw_pixmap_contained(painter, target, frames[frame_index])
            painter.restore()

    def _paint_memory_trial(self, painter: QPainter):
        # Active archive status lives in the existing top-left HUD so the
        # northern alcove and its searchable silhouette remain unobstructed.
        return

    def _paint_order_chest_lock(self, painter: QPainter) -> None:
        if (
            self.state.order_chest_unlocked
            or "misfiled_mimic" in self.state.defeated_enemies
        ):
            return
        rect = QRectF(self._order_chest_lock_drop_rect())
        # The unopened chest remains physically still. Only its lock gives a
        # brief, infrequent glint before the Master Docket Gem is assembled.
        glint_age = self.world_clock % 96
        if glint_age < 18:
            progress = glint_age / 17
            strength = math.sin(math.pi * progress)
            center = rect.center()
            radius = 4 + 8 * strength
            painter.save()
            painter.setPen(QPen(QColor(255, 224, 133, int(210 * strength)), 1.4))
            painter.drawLine(QPointF(center.x() - radius, center.y()), QPointF(center.x() + radius, center.y()))
            painter.drawLine(QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius))
            painter.restore()
        if not self.state.order_chest_gem_assembled:
            return
        pulse = 0.5 + 0.5 * math.sin(self.world_clock / 6)
        glow = QColor("#f4c45f")
        glow.setAlpha(int(120 + 90 * pulse))
        painter.save()
        painter.setPen(QPen(glow, 3 + 2 * pulse))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 17, 17)
        painter.restore()

    def _safe_world_label_rect(self, rect: QRectF) -> QRectF | None:
        """Keep world labels from painting across the Archivist sprite."""
        hero_x, hero_y, _opacity = self._passage_transition_render_state()
        hero_rect = QRectF(hero_x - 39, hero_y - 84, 78, 92).adjusted(-4, -3, 4, 3)
        if not rect.intersects(hero_rect):
            return rect
        raised = rect.translated(0, -34)
        return raised if not raised.intersects(hero_rect) else None

    def _paint_environment_sprites(self, painter: QPainter) -> None:
        """Draw authored four-frame scenery sprites over the cleaned room art."""
        for spec in ROOM_ENVIRONMENT_SPRITES[self.state.current_room]:
            self._paint_environment_sprite(painter, spec)

    def _environment_sprite_frame(self, spec: dict, collected: bool = False) -> int:
        """Choose a scenery frame without revealing a dormant story beat early."""
        if spec.get("state") == "dormant_mimic":
            return ((self.world_clock // 5) % 4) if self.state.order_chest_unlocked else 0
        return 0 if collected else ((self.world_clock + spec.get("phase", 0)) // 10) % 4

    def _paint_environment_sprite(self, painter: QPainter, spec: dict) -> None:
        if spec.get("state") == "dormant_mimic" and "misfiled_mimic" in self.state.defeated_enemies:
            return
        if self.state.current_room == "memory" and spec["id"] in MEMORY_SEQUENCE:
            self._paint_memory_plinth_sprite(painter, spec)
            return
        sheet = self.environment_sheets.get(spec["sheet"], QPixmap())
        if sheet.isNull():
            return
        frame_width = sheet.width() // 4
        collected = spec.get("shard_id") in self.state.order_shards
        frame = self._environment_sprite_frame(spec, collected)
        source = QRectF(frame * frame_width, 0, frame_width, sheet.height())
        painter.save()
        if collected:
            painter.setOpacity(0.38)
        painter.drawPixmap(QRectF(*spec["rect"]), sheet, source)
        painter.restore()

    def _paint_memory_plinth_sprite(self, painter: QPainter, spec: dict) -> None:
        """Render incomplete, restoring, or restored Archive artwork."""
        archive_id = spec["id"]
        target = QRectF(*spec["rect"])
        restored = (
            archive_id in self.state.memory_archives_completed
            or "memory" in self.state.completed_trials
        )
        if self.memory_restoration_pending == archive_id:
            base = self.memory_plinth_incomplete_bases.get(archive_id, QPixmap())
            sheet = self.environment_sheets.get(spec["sheet"], QPixmap())
            effects = self.memory_plinth_incomplete_vfx.get(archive_id, QPixmap())
            if base.isNull() or sheet.isNull():
                return
            age = max(0, self.world_clock - self.memory_restoration_started)
            progress = min(1.0, age / 48.0)
            completed_frame_width = sheet.width() // 4
            completed_frame = min(3, int(progress * 4))
            painter.save()
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(target, base, QRectF(base.rect()))
            painter.restore()
            painter.save()
            painter.setOpacity(progress)
            painter.drawPixmap(
                target,
                sheet,
                QRectF(completed_frame * completed_frame_width, 0, completed_frame_width, sheet.height()),
            )
            painter.restore()
            if not effects.isNull():
                frame_width = effects.width() // 4
                frame = min(3, age // 12)
                painter.save()
                painter.setOpacity(0.55 + 0.35 * math.sin(progress * math.pi))
                painter.drawPixmap(
                    target,
                    effects,
                    QRectF(frame * frame_width, 0, frame_width, effects.height()),
                )
                painter.restore()
            return
        if not restored:
            base = self.memory_plinth_incomplete_bases.get(archive_id, QPixmap())
            effects = self.memory_plinth_incomplete_vfx.get(archive_id, QPixmap())
            if base.isNull():
                return
            frame = ((self.world_clock + spec.get("phase", 0)) // 12) % 4
            painter.drawPixmap(target, base, QRectF(base.rect()))
            if not effects.isNull():
                frame_width = effects.width() // 4
                source = QRectF(frame * frame_width, 0, frame_width, effects.height())
                painter.drawPixmap(target, effects, source)
            return
        sheet = self.environment_sheets.get(spec["sheet"], QPixmap())
        if sheet.isNull():
            return
        frame_width = sheet.width() // 4
        frame = ((self.world_clock + spec.get("phase", 0)) // 10) % 4
        source = QRectF(frame * frame_width, 0, frame_width, sheet.height())
        painter.drawPixmap(target, sheet, source)

    def _paint_memory_archive_tooltip(self, painter: QPainter, archive_id: str) -> None:
        plinth = next(item for item in MEMORY_PLINTHS if item["id"] == archive_id)
        x, y = plinth["position"]
        restored = (
            archive_id in self.state.memory_archives_completed
            or "memory" in self.state.completed_trials
        )
        if self.memory_restoration_pending == archive_id:
            status = "RESTORING"
        elif restored:
            status = "RESTORED"
        elif self.memory_active_archive == archive_id:
            status = "ACTIVE"
        else:
            status = "DORMANT"
        rect = QRectF(max(12, min(GAME_WIDTH - 212, x - 100)), y - 154, 200, 58)
        self._panel(painter, rect, QColor(5, 8, 18, 238), QColor("#66e7df"), 1)
        painter.setPen(QColor("#f2d276"))
        self._draw_fitted_text(
            painter, rect.adjusted(12, 7, -12, -29),
            f"{archive_id.title()} Archive", 8.5, 6, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#d9f7f3"))
        self._draw_fitted_text(
            painter, rect.adjusted(12, 30, -12, -7), status, 7, 5.5, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _paint_trial_enemy(self, painter: QPainter, enemy_id: str):
        enemy = ENEMIES[enemy_id]
        frames = self.trial_enemies[enemy["sprite_group"]]
        frame_name = "idle_a" if (self.world_clock // 30) % 2 == 0 else "idle_b"
        pixmap = frames.get(frame_name, QPixmap())
        x, y = enemy["position"]
        bob = -2 if frame_name == "idle_b" else 0
        self._draw_pixmap_contained(painter, QRectF(x - 72, y - 128 + bob, 144, 144), pixmap)

    def _paint_mercy_reliquaries(self, painter: QPainter) -> None:
        """Render the three authored appeal devices as anchored world objects."""
        for appeal_id in MERCY_APPEAL_IDS:
            details = MERCY_APPEALS[appeal_id]
            frames = self.mercy_reliquary_frames.get(appeal_id, [])
            if not frames:
                continue
            completed = appeal_id in self.state.mercy_appeals_completed
            frame = 3 if completed else (self.world_clock // 14) % 3
            x, y = details["position"]
            painter.save()
            painter.setOpacity(0.72 if completed else 1.0)
            self._draw_pixmap_contained(
                painter,
                QRectF(x - 82, y - 102, 164, 132),
                frames[min(frame, len(frames) - 1)],
            )
            painter.restore()

    def _paint_mercy_activation_markers(self, painter: QPainter) -> None:
        if self.state.mercy_hearing_completed:
            return
        effect_id = (
            self.mercy_station_activation_effect.get("appeal_id")
            if self.mercy_station_activation_effect else None
        )
        for index, appeal_id in enumerate(MERCY_APPEAL_IDS):
            if appeal_id in self.state.mercy_appeals_completed:
                continue
            rect = QRectF(*MERCY_APPEALS[appeal_id]["activation_rect"])
            player_near = rect.adjusted(-14, -14, 14, 14).contains(
                QPointF(self.state.player_x, self.state.player_y)
            )
            state_name = "activation" if effect_id == appeal_id else ("proximity" if player_near else "idle")
            frames = self.archive_activation_marker_frames.get(state_name, [])
            if frames:
                frame = (self.world_clock // 5) % len(frames)
                self._draw_pixmap_contained(painter, rect.adjusted(-12, -9, 12, 9), frames[frame])
            else:
                painter.setPen(QPen(QColor("#67e9e3"), 2))
                painter.drawEllipse(rect)

    def _passage_marker_specs(self) -> list[dict]:
        room = self.state.current_room
        locked_memory_exit = len(self.state.memory_archives_completed) < len(MEMORY_SEQUENCE)
        locked_mercy_exit = "mercy" not in self.state.completed_trials
        locked_order_exit = "order" not in self.state.completed_trials
        markers = {
            "hub": [
                {
                    "id": "hub_memory", "rect": QRect(18, 242, 78, 60), "direction": "left",
                    "name": "Hall of Memory", "locked": not self._hall_is_unlocked("memory"),
                    "detail": "Begin here: recover what the Archive forgot" if self._hall_is_unlocked("memory") else self._hall_lock_message("memory"),
                },
                {
                    "id": "hub_mercy", "rect": QRect(864, 242, 78, 60), "direction": "right",
                    "name": "Hall of Mercy", "locked": not self._hall_is_unlocked("mercy"),
                    "detail": "The next chapter is open" if self._hall_is_unlocked("mercy") else self._hall_lock_message("mercy"),
                },
                {
                    "id": "hub_order", "rect": QRect(448, 466, 64, 70), "direction": "down",
                    "name": "Lower Registry", "locked": not self._hall_is_unlocked("order"),
                    "detail": "The Registry will receive you" if self._hall_is_unlocked("order") else self._hall_lock_message("order"),
                },
            ],
            "memory": [
                {
                    "id": "memory_return",
                    "rect": QRect(864, 284, 78, 60),
                    "direction": "right",
                    "name": "Return to the Main Hall",
                    "locked": locked_memory_exit,
                    "detail": "Restore all three Archives to leave" if locked_memory_exit else "The passage has reopened",
                },
            ],
            "mercy": [
                {
                    "id": "mercy_return",
                    "rect": QRect(18, 284, 78, 60),
                    "direction": "left",
                    "name": "Return to the Main Hall",
                    "locked": locked_mercy_exit,
                    "detail": (
                        "The Hall releases no witness before the hearing closes"
                        if locked_mercy_exit else "The appeal passage has reopened"
                    ),
                },
            ],
            "order": [
                {
                    "id": "order_return",
                    "rect": QRect(448, 88, 64, 70),
                    "direction": "up",
                    "name": "Return to the Main Hall",
                    "locked": locked_order_exit,
                    "detail": (
                        "Restore Docket VII-13 and survive its final filing"
                        if locked_order_exit
                        else "The Registry stair has released you"
                    ),
                },
            ],
            "vault": [],
        }
        return markers.get(room, [])

    def _paint_passage_arrow_frame(
        self,
        painter: QPainter,
        direction: str,
        frame: int,
        target: QRectF,
    ) -> None:
        if not self.passage_arrow_frames:
            return
        directions = ("left", "right", "up", "down")
        column = directions.index(direction)
        self._draw_pixmap_contained(painter, target, self.passage_arrow_frames[frame * 4 + column])

    def _paint_passage_tooltip(self, painter: QPainter, marker_id: str) -> None:
        marker = next((item for item in self._passage_marker_specs() if item["id"] == marker_id), None)
        if not marker:
            return
        marker_rect = QRectF(marker["rect"])
        width, height = 300, 64
        x = max(12, min(GAME_WIDTH - width - 12, int(marker_rect.center().x() - width / 2)))
        y = marker_rect.bottom() + 8 if marker_rect.top() < 170 else marker_rect.top() - height - 8
        rect = QRectF(x, y, width, height)
        border = QColor("#b96a75" if marker.get("locked") else "#67ddd7")
        self._panel(painter, rect, QColor(5, 8, 18, 246), border, 1)
        painter.setPen(QColor("#f0d27a"))
        self._draw_fitted_text(
            painter, rect.adjusted(13, 7, -13, -35), marker["name"].upper(), 8, 5.5, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        detail = marker.get("detail", "Pass through the marked doorway")
        painter.setPen(QColor("#e4eef0"))
        self._draw_fitted_text(
            painter, rect.adjusted(13, 31, -13, -7), detail, 7, 5, False,
            Qt.AlignCenter | Qt.TextWordWrap,
        )

    @staticmethod
    def _directional_walk_source(sheet_width: int, sheet_height: int, facing: str, frame: int) -> QRect:
        """Address one cell in the flattened down/left/right movement strip."""
        cell_width = sheet_width // 12
        row = {"down": 0, "left": 1, "right": 2}.get(facing, 0)
        index = row * 4 + frame % 4
        return QRect(index * cell_width, 0, cell_width, sheet_height)

    def _paint_hero(self, painter: QPainter):
        x, y, opacity = self._passage_transition_render_state()
        painter.save()
        painter.setOpacity(opacity)
        self._paint_memory_motion_vfx(painter, x, y)
        if self.hero_sheet.isNull():
            painter.setBrush(QColor("#56e2e1"))
            painter.drawEllipse(QPointF(x, y), 16, 16)
            painter.restore()
            return
        idle_frames = self.hero_back_idle_frames if self.facing == "up" else self.hero_idle_frames
        target = QRectF(x - 45, y - 84, 90, 92)
        corruption_frame = self._future_corruption_frame()
        if not corruption_frame.isNull():
            # Corruption adds horizontal tears and displaced limbs. Fitting the
            # wider silhouette inside the normal box would make the Archivist
            # visibly shrink, so preserve his height and floor anchor instead.
            # The generated directions reserve different amounts of room for
            # temporal spill. Small direction-specific corrections keep the
            # body close to its normal silhouette without a size jump.
            height_scale = {
                "down": 1.05,
                "left": 1.10,
                "right": 1.10,
                "up": 1.10,
            }[self.facing]
            corruption_target = self._fixed_height_floor_target(
                target, corruption_frame, height_scale=height_scale
            )
            painter.drawPixmap(
                corruption_target, corruption_frame, QRectF(corruption_frame.rect())
            )
            self._paint_memory_motion_foreground(painter, x, y)
            painter.restore()
            return
        if not self.player_is_moving and not self.passage_transition and idle_frames:
            frame = idle_frames[self._player_idle_frame()]
            self._draw_pixmap_contained(painter, target, frame)
            painter.restore()
            return
        if self.facing in ("left", "right") and len(self.hero_side_walk_frames) >= 8:
            frame = self.hero_side_walk_frames[self.walk_frame % 8]
            if self.facing == "right":
                frame = frame.transformed(QTransform().scale(-1, 1))
            self._draw_pixmap_contained(painter, target, frame)
            self._paint_memory_motion_foreground(painter, x, y)
            painter.restore()
            return
        if self.facing == "up" and not self.hero_back_sheet.isNull():
            sheet = self.hero_back_sheet
            cell_w = sheet.width() // 4
            cell_h = sheet.height()
            source = QRect(self.walk_frame * cell_w, 0, cell_w, cell_h)
        else:
            sheet = self.hero_sheet
            source = self._directional_walk_source(
                sheet.width(), sheet.height(), self.facing, self.walk_frame
            )
        bob = 1 if self.walk_frame in (1, 3) else 0
        target.translate(0, -bob)
        painter.drawPixmap(target, sheet, QRectF(source))
        self._paint_memory_motion_foreground(painter, x, y)
        painter.restore()

    def _hero_motion_frame(self, facing: str, frame_index: int) -> QPixmap:
        """Return one complete movement frame for a temporal afterimage."""
        if facing in ("left", "right") and len(self.hero_side_walk_frames) >= 8:
            frame = self.hero_side_walk_frames[frame_index % 8]
            return frame.transformed(QTransform().scale(-1, 1)) if facing == "right" else frame
        if facing == "up" and not self.hero_back_sheet.isNull():
            cell_width = self.hero_back_sheet.width() // 4
            return self.hero_back_sheet.copy(
                (frame_index % 4) * cell_width,
                0,
                cell_width,
                self.hero_back_sheet.height(),
            )
        if self.hero_sheet.isNull():
            return QPixmap()
        return self.hero_sheet.copy(
            self._directional_walk_source(
                self.hero_sheet.width(), self.hero_sheet.height(), facing, frame_index
            )
        )

    def _future_corruption_frame(self) -> QPixmap:
        """Return the authored personal-corruption phase for the real hero."""
        if (
            self.state.current_room != "memory"
            or self.memory_active_archive != "future"
            or not self.player_is_moving
            or self.memory_future_echo_event
            or not self.memory_future_corruption_event
        ):
            return QPixmap()
        event = self.memory_future_corruption_event
        age = self.world_clock - event["started"]
        if age < 0 or age >= event["duration"]:
            return QPixmap()
        progress = age / max(1, event["duration"] - 1)
        if progress < 0.20:
            phase = 0
        elif progress < 0.46:
            phase = 1
        elif progress < 0.74:
            phase = 2
        else:
            phase = 3
        frames = self.memory_future_corruption_frames.get(self.facing, [])
        return frames[phase] if len(frames) > phase else QPixmap()

    def _memory_echo_frame(self, archive_id: str, facing: str, frame_index: int) -> QPixmap:
        cycle = 8 if facing in ("left", "right") else 4
        key = (archive_id, facing, frame_index % cycle)
        if key not in self.memory_echo_frame_cache:
            source = self._hero_motion_frame(facing, frame_index)
            color = {
                "past": QColor(174, 116, 255, 210),
                "present": QColor(75, 245, 238, 220),
                "future": QColor(114, 151, 255, 190),
            }[archive_id]
            self.memory_echo_frame_cache[key] = self._tinted_pixmap(source, color)
        return self.memory_echo_frame_cache[key]

    def _paint_memory_motion_vfx(self, painter: QPainter, hero_x: float, hero_y: float) -> None:
        """Paint temporal trails behind the hero in the active Memory challenge."""
        active = self.memory_active_archive if self.state.current_room == "memory" else None
        if not active and not self.memory_motion_effects:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if active == "future":
            if self.memory_future_echo_event:
                self._paint_future_magnetic_wake(painter, hero_x, hero_y)
                self._paint_memory_avatar_afterimages(painter, active)
            elif self.player_is_moving:
                self._paint_future_magnetic_wake(painter, hero_x, hero_y)
        elif active and self.player_is_moving:
            self._paint_authored_memory_trail(painter, active, hero_x, hero_y)
            self._paint_memory_avatar_afterimages(painter, active)

        for effect in self.memory_motion_effects:
            ratio = max(0.0, effect["life"] / effect["max"])
            kind = effect["kind"]
            archive_id = effect["archive"]
            color = QColor(
                205 if archive_id == "past" else 132,
                139 if archive_id == "past" else 180,
                255,
                int((175 if archive_id == "past" else 125) * ratio),
            )
            size = effect["size"] * (0.7 + 0.3 * ratio)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            if kind == "rewind_mote":
                painter.drawPolygon(QPolygonF([
                    QPointF(effect["x"], effect["y"] - size),
                    QPointF(effect["x"] + size, effect["y"]),
                    QPointF(effect["x"], effect["y"] + size),
                    QPointF(effect["x"] - size, effect["y"]),
                ]))
            else:
                painter.drawEllipse(QPointF(effect["x"], effect["y"]), size, size)
        painter.restore()

    def _paint_memory_avatar_afterimages(self, painter: QPainter, archive_id: str) -> None:
        """Render mechanic-specific echoes from the Archivist's actual recent poses."""
        if archive_id == "future":
            self._paint_future_echo_event(painter)
            return
        snapshots = [
            snapshot for snapshot in reversed(self.memory_avatar_history)
            if snapshot["archive"] == archive_id
        ]
        if not snapshots:
            return

        if archive_id == "past":
            # Sample exact two-frame intervals: -2, -4, -6, and -8. The oldest
            # echo is painted first so the nearest remains visually dominant.
            delayed_poses = snapshots[1:8:2]
            for delay_index in range(len(delayed_poses) - 1, -1, -1):
                snapshot = delayed_poses[delay_index]
                original = self._hero_motion_frame(snapshot["facing"], snapshot["frame"])
                frame = self._memory_echo_frame(
                    archive_id, snapshot["facing"], snapshot["frame"]
                )
                target = QRectF(snapshot["x"] - 45, snapshot["y"] - 84, 90, 92)
                # Fan the sampled poses farther backward so the two-frame
                # intervals remain individually legible at the sprite's scale.
                lag_distance = delay_index * 8
                lag_offset = {
                    "left": (lag_distance, 0),
                    "right": (-lag_distance, 0),
                    "up": (0, lag_distance),
                    "down": (0, -lag_distance),
                }[snapshot["facing"]]
                target.translate(*lag_offset)
                ratio = max(0.65, snapshot["life"] / snapshot["max"])
                age_falloff = 1.0 - delay_index * 0.16
                painter.save()
                painter.setOpacity(0.48 * age_falloff * ratio)
                painter.drawPixmap(target, original, QRectF(original.rect()))
                painter.setCompositionMode(QPainter.CompositionMode_Screen)
                painter.setOpacity(0.72 * age_falloff * ratio)
                direction_offset = {
                    "left": (4, 0), "right": (-4, 0),
                    "up": (0, 4), "down": (0, -4),
                }[snapshot["facing"]]
                painter.drawPixmap(
                    target.translated(*direction_offset), frame, QRectF(frame.rect())
                )
                painter.restore()
            return

        if archive_id == "present":
            for index, snapshot in enumerate(snapshots[1::3][:4]):
                frame = self._memory_echo_frame(archive_id, snapshot["facing"], snapshot["frame"])
                ratio = snapshot["life"] / snapshot["max"]
                opacity = (0.68 - index * 0.11) * ratio
                target = QRectF(snapshot["x"] - 45, snapshot["y"] - 84, 90, 92)
                original = self._hero_motion_frame(snapshot["facing"], snapshot["frame"])
                painter.save()
                painter.setOpacity(opacity * 0.72)
                painter.drawPixmap(target, original, QRectF(original.rect()))
                painter.setCompositionMode(QPainter.CompositionMode_Screen)
                painter.setOpacity(opacity * 0.48)
                for dx, dy in ((-3, 0), (3, 0), (0, -2), (0, 2)):
                    painter.drawPixmap(target.translated(dx, dy), frame, QRectF(frame.rect()))
                painter.setOpacity(opacity * 0.82)
                painter.drawPixmap(target, frame, QRectF(frame.rect()))
                painter.restore()
            return

    def _paint_future_echo_event(self, painter: QPainter) -> None:
        """Animate sparse divergent futures without introducing a major threat."""
        event = self.memory_future_echo_event
        if not event:
            return
        age = self.world_clock - event["started"]
        duration = event["duration"]
        if age < 0 or age >= duration:
            return
        progress = age / max(1, duration - 1)
        envelope = min(1.0, progress / 0.16, (1.0 - progress) / 0.24)
        for index, possibility in enumerate(event["echoes"]):
            flicker = (age + possibility["seed"]) % 9
            flicker_alpha = (1.0, 0.62, 0.94, 0.44, 0.86, 0.28, 0.78, 0.52, 0.92)[flicker]
            own_frame = possibility["frame"] + age // possibility["cadence"]
            original = self._hero_motion_frame(possibility["facing"], own_frame)
            glow = self._memory_echo_frame(
                "future", possibility["facing"], own_frame
            )
            projected = dict(possibility)
            # Alternate selves pace opposite or perpendicular to the real hero.
            step = math.sin((age + possibility["seed"] % 11) * 0.34)
            projected["x"] += possibility["axis_x"] * possibility["motion_span"] * step
            projected["y"] += possibility["axis_y"] * possibility["motion_span"] * step
            self._paint_future_possibility_echo(
                painter,
                original,
                glow,
                projected,
                index,
                envelope * flicker_alpha,
            )

    def _paint_future_possibility_echo(
        self,
        painter: QPainter,
        frame: QPixmap,
        glow: QPixmap,
        possibility: dict,
        echo_index: int,
        opacity: float,
    ) -> None:
        """Paint a grounded alternate self with persistent temporal corruption."""
        if frame.isNull() or opacity <= 0.0:
            return
        target = QRectF(possibility["x"] - 45, possibility["y"] - 84, 90, 92)
        painter.save()
        shadow = QRectF(target.center().x() - 24, target.bottom() - 8, 48, 11)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(34, 48, 92, int(100 * opacity)))
        painter.drawEllipse(shadow)
        painter.setOpacity((0.62 - echo_index * 0.08) * opacity)
        slice_count = 6
        source_height = frame.height() / slice_count
        target_height = target.height() / slice_count
        for slice_index in range(slice_count):
            seed = possibility["seed"] + self.world_clock + slice_index * 7
            offset = (-7, 5, -3, 8, -5, 4)[seed % 6]
            source = QRectF(0, slice_index * source_height, frame.width(), source_height + 0.5)
            destination = QRectF(
                target.x() + offset,
                target.y() + slice_index * target_height,
                target.width(),
                target_height + 0.5,
            )
            painter.drawPixmap(destination, frame, source)
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        painter.setOpacity((0.30 - echo_index * 0.04) * opacity)
        painter.drawPixmap(target.translated(-3, 1), glow, QRectF(glow.rect()))
        painter.restore()

    def _paint_authored_memory_trail(
        self,
        painter: QPainter,
        archive_id: str,
        hero_x: float,
        hero_y: float,
    ) -> None:
        """Render the generated trail atlas behind the avatar in its travel direction."""
        frames = self.memory_trail_frames.get(archive_id, [])
        if not frames:
            return
        cadence = {"past": 4, "present": 2, "future": 6}[archive_id]
        frame = frames[(self.world_clock // cadence) % len(frames)]
        rotation = {"right": 0, "down": 90, "left": 180, "up": -90}[self.facing]
        opacity = {"past": 0.84, "present": 0.88, "future": 0.88}[archive_id]
        length = {"past": 220, "present": 235, "future": 224}[archive_id]
        thickness = {"past": 108, "present": 98, "future": 126}[archive_id]
        painter.save()
        painter.translate(hero_x, hero_y - 40)
        painter.rotate(rotation)
        painter.setOpacity(opacity)
        scale = min(length / max(1, frame.width()), thickness / max(1, frame.height()))
        draw_width = frame.width() * scale
        draw_height = frame.height() * scale
        # Anchor the authored bright tip at the avatar instead of centering the
        # image inside a wider box and accidentally leaving a visual gap.
        painter.drawPixmap(
            QRectF(-draw_width + 8, -draw_height / 2, draw_width, draw_height),
            frame,
            QRectF(frame.rect()),
        )
        painter.restore()

    def _paint_future_magnetic_wake(
        self, painter: QPainter, hero_x: float, hero_y: float
    ) -> None:
        """Keep a compact magnetic burden behind ordinary Future movement."""
        frames = self.memory_future_magnetic_wake_frames
        if not frames:
            return
        frame = frames[(self.world_clock // 3) % len(frames)]
        rotation = {"right": 0, "down": 90, "left": 180, "up": -90}[self.facing]
        pulsing = self.memory_future_corruption_event is not None
        length = 178 if pulsing else 142
        thickness = 94 if pulsing else 76
        opacity = 0.84 if pulsing else 0.52
        painter.save()
        painter.translate(hero_x, hero_y - 40)
        painter.rotate(rotation)
        painter.setOpacity(opacity)
        scale = min(length / max(1, frame.width()), thickness / max(1, frame.height()))
        draw_width = frame.width() * scale
        draw_height = frame.height() * scale
        painter.drawPixmap(
            QRectF(-draw_width + 7, -draw_height / 2, draw_width, draw_height),
            frame,
            QRectF(frame.rect()),
        )
        painter.restore()

    def _paint_memory_motion_foreground(self, painter: QPainter, hero_x: float, hero_y: float) -> None:
        """Add restrained front-layer accents so the effect wraps around the avatar."""
        archive_id = self.memory_active_archive if self.state.current_room == "memory" else None
        if not archive_id or not self.player_is_moving:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if archive_id == "present":
            for index in range(3):
                angle = self.world_clock * 0.7 + index * math.tau / 3
                x = hero_x + math.cos(angle) * 24
                y = hero_y - 42 + math.sin(angle) * 31
                painter.setPen(QPen(QColor(255, 220, 104, 185), 2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(x, y), QPointF(x + math.cos(angle) * 7, y + math.sin(angle) * 7))
        elif archive_id == "past":
            painter.setPen(QPen(QColor(223, 184, 255, 105), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawPoint(QPointF(hero_x + 17, hero_y - 56))
            painter.drawPoint(QPointF(hero_x - 20, hero_y - 30))
        painter.restore()

    def _paint_vault_lock(self, painter: QPainter):
        """Render the lock on the hall side; the vault interior is already beyond it."""
        rect = QRectF(self._vault_keyhole_rect())
        pulse = 0.55 + 0.35 * math.sin(self.world_clock / 8)
        painter.save()
        if not self.vault_lock_overlay.isNull() and not self.state.boss_defeated:
            self._draw_pixmap_contained(painter, QRectF(352, 12, 256, 178), self.vault_lock_overlay)
        if self.state.vault_key_assembled and not self.state.vault_key_inserted:
            glow = QColor("#62f0e7")
            glow.setAlpha(int(120 + 100 * pulse))
            painter.setPen(QPen(glow, 6))
            painter.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), 16, 16)
        if self.state.vault_key_inserted:
            key = self.quest_icons.get("vault_key_relic_runtime", QPixmap())
            painter.setOpacity(0.92)
            self._draw_pixmap_contained(painter, rect.adjusted(-6, -6, 6, 6), key)
            painter.setOpacity(1)
        if self.state.vault_key_assembled and not self.state.vault_key_inserted:
            painter.setPen(QColor("#dffef8"))
            self._draw_fitted_text(painter, QRectF(405, 174, 150, 19), "DRAG KEY TO LOCK", 7, 5, True)
        elif self.state.vault_key_inserted and not self.state.boss_defeated:
            painter.setPen(QColor("#f7df84"))
            self._draw_fitted_text(painter, QRectF(405, 174, 150, 19), "CLICK TO OPEN", 7, 5, True)
        painter.restore()

    def _paint_hud(self, painter: QPainter):
        room = ROOMS[self.state.current_room]
        self._panel(painter, QRectF(18, 16, 390, 82), QColor(7, 10, 22, 218))
        painter.setPen(QColor("#f2d482"))
        self._draw_fitted_text(
            painter, QRectF(35, 27, 350, 24), room["name"].upper(), 11, 7, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        objective = self._memory_trial_hud_text() if self.memory_active_archive else self._room_objective()
        painter.setPen(QColor("#a8f5ef"))
        self._draw_fitted_text(
            painter, QRectF(35, 58, 350, 23), objective, 9, 6, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        self._panel(painter, QRectF(735, 18, 207, 64), QColor(7, 10, 22, 218))
        painter.setPen(QColor("#dce8ef"))
        self._draw_fitted_text(
            painter, QRectF(750, 27, 177, 20), "SPACE  INTERACT", 8, 6, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#f2d482"))
        self._draw_fitted_text(
            painter, QRectF(750, 52, 177, 18), f"GOLD  {self.state.gold}", 8, 6, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _memory_trial_hud_text(self) -> str:
        archive_id = self.memory_active_archive
        if not archive_id:
            return self._room_objective()
        if self.memory_hourglass_found:
            return f"{archive_id.upper()}  |  DRAG HOURGLASS TO ARCHIVE"
        elapsed = max(0, self.world_clock - self.memory_attempt_started_tick) // 30
        limit = MEMORY_ARCHIVE_RULES[archive_id]["seconds"]
        if archive_id == "future":
            time_text = f"{elapsed // 60}:{elapsed % 60:02d} / 2:00"
        else:
            remaining = max(0, limit - elapsed)
            time_text = f"{remaining // 60}:{remaining % 60:02d} LEFT"
        return f"{archive_id.upper()}  |  SEARCH ROOM  |  {time_text}"

    def _paint_exploration_inventory(self, painter: QPainter):
        toggle = self._hud_toggle_rect()
        self._panel(painter, QRectF(toggle), QColor(8, 12, 24, 232), QColor("#65ded8"))
        painter.setPen(QColor("#e9f7f4"))
        self._draw_fitted_text(painter, toggle, "v" if self.state.hud_collapsed else "^", 13, 8, True)
        if self.state.hud_collapsed:
            painter.setPen(QColor("#90aaa9"))
            self._draw_fitted_text(
                painter, QRectF(735, 555, 155, 20), "SHOW RELIC BELT  [H]", 7, 5, True,
                Qt.AlignRight | Qt.AlignVCenter | Qt.TextSingleLine,
            )
            return
        self._panel(painter, QRectF(96, 548, 768, 82), QColor(5, 8, 18, 238), QColor("#3aa9a6"))
        painter.setPen(QColor("#f0d27a"))
        self._draw_fitted_text(
            painter, QRectF(108, 554, 120, 18), "RELIC BELT", 7.5, 5.5, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#91aaa9"))
        self._draw_fitted_text(
            painter, QRectF(690, 554, 158, 18), "DRAG FRAGMENTS TO FUSE", 6, 4.5, True,
            Qt.AlignRight | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        for item, rect in self._explore_item_rects().items():
            self._paint_relic_slot(painter, item, rect, item == self.dragged_inventory_item)
        if not self._explore_items():
            painter.setPen(QColor("#8da4aa"))
            self._draw_fitted_text(
                painter, QRectF(265, 577, 430, 28), "NO RELICS YET  |  COMPLETE A SIDE-HALL TRIAL", 7.5, 5.5, True,
                Qt.AlignCenter | Qt.TextSingleLine,
            )
        if self.dragged_inventory_item:
            floating = QRectF(self.drag_position.x() - 28, self.drag_position.y() - 28, 56, 56)
            painter.save()
            painter.setOpacity(0.82)
            self._paint_relic_slot(painter, self.dragged_inventory_item, floating.toRect(), False)
            painter.restore()
        if self.hovered_inventory_item and not self.dragged_inventory_item:
            self._paint_relic_tooltip(painter, self.hovered_inventory_item)

    def _paint_relic_slot(self, painter: QPainter, item: str, rect: QRect, dragging: bool):
        painter.setBrush(QColor(12, 20, 34, 150 if dragging else 245))
        painter.setPen(QPen(QColor("#d9bf69" if "key" in item or "fragment" in item else "#56c8c5"), 1))
        painter.drawRoundedRect(QRectF(rect), 5, 5)
        if item == "registry_chest_gem" and not self.registry_chest_gem.isNull():
            self._draw_pixmap_contained(painter, QRectF(rect).adjusted(5, 4, -5, -4), self.registry_chest_gem)
            return
        if item.startswith("registry_shard_"):
            if item == "registry_shard_pair":
                parts = [
                    shard_id for shard_id in ("west", "east", "south")
                    if shard_id in self.state.order_fused_shards
                ]
                for index, shard_id in enumerate(parts[:2]):
                    frame = self.registry_shard_frames.get(shard_id, QPixmap())
                    if not frame.isNull():
                        self._draw_pixmap_contained(
                            painter, QRectF(rect.x() + 4 + index * 28, rect.y() + 5, 30, 46), frame
                        )
            else:
                shard_id = item.removeprefix("registry_shard_")
                shard_icon = self.registry_shard_frames.get(shard_id, QPixmap())
                if not shard_icon.isNull():
                    target = QRectF(rect).adjusted(8, 6, -8, -6)
                    self._draw_pixmap_contained(
                        painter, target,
                        shard_icon,
                    )
            return
        if item.startswith("hourglass_") and not self.memory_hourglass_atlas.isNull():
            index = MEMORY_SEQUENCE.index(item.removeprefix("hourglass_"))
            cell_width = self.memory_hourglass_atlas.width() / 3
            source = QRectF(index * cell_width, 0, cell_width, self.memory_hourglass_atlas.height())
            painter.drawPixmap(QRectF(rect).adjusted(5, 4, -5, -4), self.memory_hourglass_atlas, source)
            return
        icon_name = {
            "fragment_memory": "memory_key_fragment",
            "fragment_mercy": "mercy_sigil",
            "fragment_order": "docket_shard",
            "pending_codex": "pending_codex_runtime",
        }.get(item, ITEM_DEFS.get(item, {}).get("icon", item))
        icon_group = self.quest_icons if item in {"recall_lens", "pending_codex", "vault_key"} or item.startswith("fragment_") else self.combat_icons
        icon = icon_group.get(icon_name, QPixmap())
        if item == "vault_key":
            icon = self.quest_icons.get("vault_key_relic_runtime", QPixmap())
            if not icon.isNull():
                self._draw_pixmap_contained(painter, QRectF(rect).adjusted(6, 4, -6, -4), icon)
        elif item == "key_pair":
            pair_icons = (
                self.quest_icons.get("memory_key_fragment", QPixmap()),
                self.quest_icons.get("mercy_sigil", QPixmap()),
            )
            for index, pair_icon in enumerate(pair_icons):
                if not pair_icon.isNull():
                    self._draw_pixmap_contained(
                        painter, QRectF(rect.x() + 5 + index * 23, rect.y() + 7, 31, 38), pair_icon
                    )
        elif not icon.isNull():
            painter.drawPixmap(rect.adjusted(7, 5, -7, -5), icon)
        count = "1/3" if item.startswith("fragment_") else "2/3" if item == "key_pair" else ""
        if count:
            badge = QRectF(rect.right() - 25, rect.y() + 4, 21, 16)
            painter.setBrush(QColor(4, 8, 17, 225))
            painter.setPen(QPen(QColor("#e9d277"), 1))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor("#ffffff"))
            self._draw_fitted_text(painter, badge, count, 6.5, 4.5, True, Qt.AlignCenter | Qt.TextSingleLine)

    def _paint_relic_tooltip(self, painter: QPainter, item: str):
        name, description = RELIC_INFO.get(item, (item.replace("_", " ").title(), "A relic of the archive."))
        width, height = 300, 76
        x = max(12, min(GAME_WIDTH - width - 12, int(self.hover_position.x() - width / 2)))
        y = 468
        rect = QRectF(x, y, width, height)
        self._panel(painter, rect, QColor(5, 9, 19, 246), QColor("#d8c06e"), 1)
        painter.setPen(QColor("#f2d37a"))
        self._draw_fitted_text(painter, rect.adjusted(14, 8, -14, -47), name.upper(), 8, 5.5, True, Qt.AlignLeft | Qt.AlignVCenter)
        painter.setPen(QColor("#d5e2e5"))
        self._draw_fitted_text(painter, rect.adjusted(14, 31, -14, -8), description, 7.5, 5.5, False, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)

    def _room_objective(self) -> str:
        room_id = self.state.current_room
        if room_id == "hub":
            if not self._has_story_flag("movement_tutorial_started"):
                return "LISTEN TO MARA"
            if not self._has_story_flag("movement_tutorial_complete"):
                return "USE ARROW KEYS TO MOVE"
            if not self._has_story_flag("onboarding_complete"):
                return "APPROACH MARA  |  PRESS SPACE"
            if self.state.vault_key_inserted:
                return "CLICK THE VAULT LOCK"
            if self.state.vault_key_assembled:
                return "DRAG THE KEY INTO THE VAULT LOCK"
            for trial_id in HALL_SEQUENCE:
                if trial_id not in self.state.completed_trials:
                    return f"ENTER {ROOMS[trial_id]['name'].upper()}"
                if trial_id not in self.state.completed_seal_puzzles:
                    return f"AWAKEN {SEALS[trial_id]['name'].upper()}"
            return f"SEALS  {len(self.state.completed_seal_puzzles)}/3  |  KEY  {len(self.state.key_fragments)}/3"
        if room_id == "vault":
            if self.state.boss_defeated:
                return "READ THE CODEX OF THE UNCLOSED"
            return ROOMS[room_id]["objective"].upper()
        if room_id == "memory":
            return "RECALL LENS ACQUIRED" if "memory" in self.state.completed_trials else f"ARCHIVES RESTORED  {self.state.memory_progress}/3"
        if room_id == "mercy":
            if "mercy" in self.state.completed_trials:
                return "APPEAL TONIC ACQUIRED"
            appeals = len(self.state.mercy_appeals_completed)
            if appeals < len(MERCY_APPEAL_IDS):
                return f"MEMORIES HEARD  {appeals}/3"
            if not self.state.mercy_hearing_completed:
                return "RETURN TO THE CENTRAL DAIS"
            if "red_tape_wraith" not in self.state.defeated_enemies:
                return "DEFEAT THE SUMMONED WRAITH"
            return "THE OMITTED CLAIMANTS ARE ON RECORD"
        if "order" in self.state.completed_trials:
            return "RESET COMPASS ACQUIRED"
        findings = len(self.state.order_investigations_completed)
        if findings == len(ORDER_INVESTIGATION_IDS):
            if self.state.order_chest_unlocked:
                return "THE REWARD CHEST WAS HUNGRY"
            if self.state.order_chest_gem_assembled:
                return "DRAG MASTER DOCKET GEM TO CHEST"
            return "FUSE THE THREE DOCKET SHARDS"
        return f"DOCKET VII-13  {findings}/3  |  CORRUPTION  {self.state.order_corruption}/3"

    @staticmethod
    def _dialogue_panel_path(rect: QRectF, tail_x: float | None = None) -> QPainterPath:
        """Build one continuous speech-panel silhouette with no tail seam."""
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        radius = 8.0
        path = QPainterPath()
        path.moveTo(left + radius, top)
        if tail_x is not None:
            path.lineTo(tail_x - 15, top)
            path.lineTo(tail_x, top - 18)
            path.lineTo(tail_x + 15, top)
        path.lineTo(right - radius, top)
        path.quadTo(QPointF(right, top), QPointF(right, top + radius))
        path.lineTo(right, bottom - radius)
        path.quadTo(QPointF(right, bottom), QPointF(right - radius, bottom))
        path.lineTo(left + radius, bottom)
        path.quadTo(QPointF(left, bottom), QPointF(left, bottom - radius))
        path.lineTo(left, top + radius)
        path.quadTo(QPointF(left, top), QPointF(left + radius, top))
        path.closeSubpath()
        return path

    def _paint_dialogue(self, painter: QPainter):
        if not self.dialogue:
            return
        speaker, text = self.dialogue[min(self.dialogue_index, len(self.dialogue) - 1)]
        role, side, portrait_rect, rect = self._dialogue_layout()
        if role:
            painter.fillRect(self.rect(), QColor(3, 4, 12, 84))
            frame = self.dialogue_pose_frames[role]
            if role == "mara":
                sheet = self.mara_closeup_situations_sheet if frame >= 8 else self.mara_closeup_sheet
            else:
                sheet = self.hero_closeup_situations_sheet if frame >= 8 else self.hero_closeup_sheet
            self._paint_dialogue_portrait(
                painter,
                sheet,
                frame % 8,
                portrait_rect,
                mirror=side == "right",
            )

        tail_x = None
        if role:
            tail_x = rect.left() + 78 if side == "left" else rect.right() - 78
        painter.setPen(QPen(QColor("#61ddd8"), 2))
        painter.setBrush(QColor(8, 9, 20, 242))
        painter.drawPath(self._dialogue_panel_path(rect, tail_x))
        painter.setPen(QColor("#f1d17d"))
        self._draw_fitted_text(
            painter, QRectF(rect.x() + 22, rect.y() + 14, rect.width() - 44, 25), speaker, 11, 7, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#eef0f4"))
        self._draw_fitted_text(
            painter, QRectF(rect.x() + 22, rect.y() + 47, rect.width() - 44, rect.height() - 79), text, 10.5, 7,
            flags=Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
        )
        if self.dialogue_choices:
            for index, ((_, label), choice_rect) in enumerate(zip(self.dialogue_choices, self._dialogue_choice_rects())):
                self._panel(painter, QRectF(choice_rect), QColor(18, 25, 43, 247), QColor("#8d82ce"))
                painter.setPen(QColor("#edf4f2"))
                self._draw_fitted_text(
                    painter, choice_rect.adjusted(12, 4, -12, -4), f"{index + 1}. {label}", 7.5, 5.5, True,
                    Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                )
        else:
            painter.setPen(QColor("#72ece6"))
            self._draw_fitted_text(
                painter, QRectF(rect.right() - 132, rect.bottom() - 29, 108, 18), "NEXT  >", 8.5, 6, True,
                Qt.AlignRight | Qt.AlignVCenter | Qt.TextSingleLine,
            )

    def _paint_dialogue_portrait(
        self,
        painter: QPainter,
        sheet: QPixmap,
        frame: int,
        target: QRectF,
        mirror: bool = False,
    ):
        if not mirror:
            self._paint_portrait_frame(painter, sheet, frame, target)
            return
        painter.save()
        painter.translate(target.right(), 0)
        painter.scale(-1, 1)
        self._paint_portrait_frame(
            painter,
            sheet,
            frame,
            QRectF(0, target.y(), target.width(), target.height()),
        )
        painter.restore()

    def _paint_portrait_frame(self, painter: QPainter, sheet: QPixmap, frame: int, target: QRectF):
        if sheet.isNull():
            return
        columns = 4
        rows = 2 if sheet.height() * 2 > sheet.width() else 1
        frame %= columns * rows
        cell_width = sheet.width() / columns
        cell_height = sheet.height() / rows
        source = QRectF(
            (frame % columns) * cell_width,
            (frame // columns) * cell_height,
            cell_width,
            cell_height,
        )
        self._draw_pixmap_contained(painter, target, sheet.copy(source.toRect()))

    def _dialogue_choice_rects(self) -> list[QRect]:
        _role, side, _portrait, _dialogue = self._dialogue_layout()
        x = 518 if side == "left" else 28
        if side == "center":
            x = 510
        return [QRect(x, 354 + index * 35, 414, 31) for index in range(len(self.dialogue_choices))]

    def _paint_seal_puzzle(self, painter: QPainter):
        trial_id = self.active_puzzle or "memory"
        puzzle = SEAL_PUZZLES[trial_id]
        # Seal puzzles replace the room rather than behaving like translucent
        # popups. This hides the world HUD, relic belt, room art, and any other
        # visual noise while preserving each puzzle's authored panel artwork.
        painter.fillRect(self.rect(), QColor("#010207"))
        puzzle_rect = QRectF(120, 78, 720, 478)
        if trial_id == "memory" and not self.chronometer_panel.isNull():
            painter.save()
            panel_shape = QPainterPath()
            panel_shape.addRoundedRect(puzzle_rect, 54, 54)
            painter.setClipPath(panel_shape)
            self._paint_chronometer_frame(painter, puzzle_rect)
            self._paint_chronometer_edge_vignette(painter, puzzle_rect)
            painter.restore()
            self._paint_chronometer_title_backdrop(painter)
        elif trial_id == "order" and not self.coupled_registry_panel.isNull():
            painter.save()
            painter.drawPixmap(puzzle_rect, self.coupled_registry_panel, QRectF(self.coupled_registry_panel.rect()))
            painter.fillRect(puzzle_rect, QColor(2, 5, 12, 35))
            self._paint_chronometer_edge_vignette(painter, puzzle_rect)
            painter.restore()
            self._paint_chronometer_title_backdrop(painter)
        else:
            self._panel(painter, puzzle_rect, QColor(8, 12, 25, 246), QColor(SEALS[trial_id]["color"]), 2)
        self._button(painter, QRect(24, 24, 92, 34), "< LEAVE", "#29334d", small=True)
        painter.setPen(QColor("#f2d482"))
        self._draw_fitted_text(
            painter,
            self._chronometer_title_rect() if trial_id == "memory" else QRectF(155, 105, 650, 35),
            puzzle["name"].upper(),
            16,
            9,
            True,
            flags=Qt.AlignCenter | Qt.TextSingleLine,
        )
        if trial_id != "memory":
            painter.setPen(QColor("#d8e8ec"))
            instruction_rect = QRectF(175, 148, 610, 42) if trial_id != "order" else QRectF(200, 145, 560, 34)
            self._draw_fitted_text(painter, instruction_rect, puzzle["instruction"], 9.5, 6.5)
        if trial_id == "memory":
            self._paint_memory_puzzle(painter)
        elif trial_id == "mercy":
            self._paint_mercy_puzzle(painter)
        else:
            self._paint_order_puzzle(painter)

    def _paint_memory_puzzle(self, painter: QPainter):
        moving = set()
        if self.chronometer_exchange:
            moving = {self.chronometer_exchange["first"], self.chronometer_exchange["second"]}
        for index in range(5):
            if index not in moving:
                self._paint_chronometer_assembly(painter, index, index)
        if self.chronometer_exchange:
            exchange = self.chronometer_exchange
            first, second = exchange["first"], exchange["second"]
            progress = min(1.0, max(0.0, (self.world_clock - exchange["started"]) / exchange["duration"]))
            eased = progress * progress * (3 - 2 * progress)
            arc = math.sin(math.pi * eased) * 70
            self._paint_chronometer_assembly(painter, first, first, destination=second, progress=eased, arc=-arc)
            self._paint_chronometer_assembly(painter, second, second, destination=first, progress=eased, arc=arc)
        painter.setPen(QColor("#b8fff8"))
        self._draw_fitted_text(
            painter,
            self._chronometer_instruction_rect(),
            "INSPECT TUBES  |  SELECT TWO SOCKETS TO EXCHANGE",
            8,
            4.8,
            True,
        )
        painter.setPen(QColor("#fff0b0"))
        self._draw_fitted_text(painter, self._chronometer_lever_label_rect(), "PULL LEVER", 6.5, 4.5, True)
        self._paint_open_chronometer_scroll(painter)

    def _paint_chronometer_assembly(
        self,
        painter: QPainter,
        content_index: int,
        position_index: int,
        destination: int | None = None,
        progress: float = 0.0,
        arc: float = 0.0,
    ) -> None:
        tube_rects = self._memory_puzzle_rects()
        selector_rects = self._memory_selector_rects()
        tube = QRectF(tube_rects[position_index])
        selector = QRectF(selector_rects[position_index])
        if destination is not None:
            destination_tube = QRectF(tube_rects[destination])
            dx = (destination_tube.x() - tube.x()) * progress
            tube.translate(dx, arc)
            selector.translate(dx, arc)
        tube_frame = 1 if self.chronometer_open_slot == content_index else 0
        self._paint_scroll_atlas_frame(painter, tube_frame, tube)
        hovered = destination is None and selector.contains(self.hover_position)
        active = destination is not None or content_index == self.puzzle_selected or hovered
        glyph_index = self.puzzle_socket_order[content_index]
        self._paint_chronometer_selector(painter, glyph_index, active, selector)

    def _paint_chronometer_selector(
        self,
        painter: QPainter,
        glyph_index: int,
        active: bool,
        target: QRectF,
    ) -> None:
        if self.chronometer_selector_atlas.isNull():
            return
        width = self.chronometer_selector_atlas.width()
        height = self.chronometer_selector_atlas.height()
        left, right = round(glyph_index * width / 5), round((glyph_index + 1) * width / 5)
        row = 1 if active else 0
        top, bottom = round(row * height / 2), round((row + 1) * height / 2)
        frame = self.chronometer_selector_atlas.copy(left, top, right - left, bottom - top)
        self._draw_pixmap_contained(painter, target, frame)

    def _paint_chronometer_glyph(self, painter: QPainter, glyph_index: int, target: QRectF) -> None:
        """Render a visibly centered crest, ignoring uneven atlas transparency."""
        if not self.chronometer_glyph_frames:
            return
        self._draw_pixmap_contained(painter, target, self.chronometer_glyph_frames[glyph_index])

    def _load_chronometer_glyph_frames(self) -> list[QPixmap]:
        """Extract complete dormant crests using their authored, non-grid bounds."""
        if self.chronometer_selector_atlas.isNull():
            return []
        # The generated crests are wider than one fifth of the atlas and cross
        # nominal cell edges. These bounds preserve each complete top-row crest
        # while stopping before the active-row glow begins around y=380.
        source_bounds = (
            QRect(49, 8, 358, 364),
            QRect(432, 9, 359, 363),
            QRect(807, 9, 366, 363),
            QRect(1192, 9, 358, 363),
            QRect(1575, 9, 357, 363),
        )
        frames = []
        for bounds in source_bounds:
            frame = self.chronometer_selector_atlas.copy(bounds)
            painted_bounds = QRegion(frame.mask()).boundingRect()
            frames.append(frame.copy(painted_bounds) if painted_bounds.isValid() else frame)
        return frames

    def _paint_scroll_atlas_frame(
        self,
        painter: QPainter,
        frame: int,
        target: QRectF,
        preserve_aspect: bool = True,
    ) -> None:
        if not self.chronometer_scroll_frames:
            return
        pixmap = self.chronometer_scroll_frames[frame]
        if preserve_aspect:
            self._draw_pixmap_contained(painter, target, pixmap)
        else:
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

    def _paint_open_chronometer_scroll(self, painter: QPainter) -> None:
        if self.chronometer_open_slot is None:
            return
        target = QRectF(self._chronometer_parchment_rect())
        animation = self.chronometer_scroll_animation
        age = max(0, self.world_clock - self.chronometer_scroll_animation_started)
        step = min(3, age // 7)
        frame = 3 - step if animation == "closing" else step if animation == "opening" else 3
        painter.fillRect(self.rect(), QColor(2, 3, 9, 185))
        if frame < 3:
            cartridge_target = QRectF(260, 150, 440, 390)
            self._paint_scroll_atlas_frame(painter, frame, cartridge_target, preserve_aspect=True)
        else:
            self._paint_scroll_atlas_frame(painter, frame, target, preserve_aspect=False)
        if frame < 3:
            return
        clue = self.puzzle_sequence[self.chronometer_open_slot]
        text_rects = self._chronometer_parchment_text_rects()
        glyph_index = self.puzzle_socket_order[self.chronometer_open_slot]
        self._paint_chronometer_glyph(
            painter,
            glyph_index,
            QRectF(target.center().x() - 29, target.y() + 92, 58, 58),
        )
        painter.setPen(QColor("#2c2018"))
        self._draw_fitted_text(
            painter,
            text_rects["clue"],
            PUZZLE_MEMORY_CLUES[clue],
            10.5,
            7,
            flags=Qt.AlignCenter | Qt.TextWordWrap,
        )
        painter.setPen(QColor("#6b4628"))
        self._draw_fitted_text(
            painter,
            text_rects["return"],
            "CLICK TO RETURN",
            6.5,
            4.5,
            True,
        )

    @staticmethod
    def _paint_chronometer_edge_vignette(painter: QPainter, target: QRectF) -> None:
        """Feather the panel into the overlay without hard rectangular edges."""
        edge = 68.0
        fades = (
            (QRectF(target.left(), target.top(), edge, target.height()),
             QPointF(target.left(), 0), QPointF(target.left() + edge, 0)),
            (QRectF(target.right() - edge, target.top(), edge, target.height()),
             QPointF(target.right(), 0), QPointF(target.right() - edge, 0)),
            (QRectF(target.left(), target.top(), target.width(), edge),
             QPointF(0, target.top()), QPointF(0, target.top() + edge)),
            (QRectF(target.left(), target.bottom() - edge, target.width(), edge),
             QPointF(0, target.bottom()), QPointF(0, target.bottom() - edge)),
        )
        for rect, start, end in fades:
            gradient = QLinearGradient(start, end)
            gradient.setColorAt(0.0, QColor(2, 4, 12, 225))
            gradient.setColorAt(1.0, QColor(2, 4, 12, 0))
            painter.fillRect(rect, QBrush(gradient))

    @staticmethod
    def _paint_chronometer_title_backdrop(painter: QPainter) -> None:
        """Build a soft oblate title vignette instead of a hard-edged strip."""
        painter.save()
        painter.setPen(Qt.NoPen)
        outer = QRectF(142, 88, 676, 94)
        for inset, alpha in ((0, 22), (13, 30), (27, 42), (42, 58)):
            painter.setBrush(QColor(3, 5, 14, alpha))
            painter.drawEllipse(outer.adjusted(inset, inset * 0.22, -inset, -inset * 0.22))
        painter.restore()

    def _paint_chronometer_frame(self, painter: QPainter, target: QRectF) -> None:
        animation = self.chronometer_animation
        age = max(0, self.world_clock - self.chronometer_animation_started)
        atlas_name = "activation"
        frame = 3
        if animation == "intro":
            frame = min(3, age // 10)
        elif animation == "interaction":
            frame = (1, 2, 3, 2)[min(3, age // 4)]
        elif animation == "lever_pull":
            atlas_name = "lever_pull"
            frame = min(3, age // 7)
        elif animation == "fail":
            atlas_name = "fail"
            frame = min(3, age // 8)
        elif animation == "success":
            atlas_name = "success"
            frame = min(3, age // 12)
        atlas = self.chronometer_atlases.get(atlas_name, QPixmap())
        if atlas.isNull():
            painter.drawPixmap(target, self.chronometer_panel, QRectF(self.chronometer_panel.rect()))
            return
        cell_width = atlas.width() / 2
        cell_height = atlas.height() / 2
        source = QRectF((frame % 2) * cell_width, (frame // 2) * cell_height, cell_width, cell_height)
        painter.fillRect(target, QColor("#090812"))
        painter.drawPixmap(target, atlas, source)

    def _paint_mercy_puzzle(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#010207"))
        stage = QRectF(42, 62, 876, 526)
        if not self.mercy_loom_panel.isNull():
            self._draw_pixmap_cover(painter, stage, self.mercy_loom_panel)
        painter.fillRect(stage, QColor(2, 5, 10, 42))
        self._paint_chronometer_edge_vignette(painter, stage)
        self._button(painter, QRect(24, 24, 92, 34), "< LEAVE", "#26383c", small=True)
        painter.setPen(QColor("#f1d277"))
        self._draw_fitted_text(
            painter, QRectF(205, 22, 550, 40), "THE CONSEQUENCE LOOM", 16, 10, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#a2f0e9"))
        self._draw_fitted_text(
            painter, QRectF(205, 66, 550, 30),
            "TRACE EACH GRANT TO THE RECORD THAT PAID FOR IT. AUDIT ALL FOUR THREADS.",
            8, 5.6, True, Qt.AlignCenter | Qt.TextSingleLine,
        )
        source_rects = self._mercy_loom_source_rects()
        destination_rects = self._mercy_loom_destination_rects()
        token_by_id = {
            item["id"]: self.mercy_loom_tokens[index]
            for index, item in enumerate(MERCY_CONSEQUENCE_LINKS)
            if index < len(self.mercy_loom_tokens)
        }
        for item in MERCY_CONSEQUENCE_LINKS:
            consequence_id = item["id"]
            source_rect = QRectF(source_rects[consequence_id])
            destination_id = self.mercy_loom_links[consequence_id]
            if destination_id:
                painter.setBrush(QColor(1, 3, 8, 190))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(source_rect.adjusted(18, 7, -18, -7))
            token_rect = source_rect.adjusted(22, 5, -22, -5)
            if destination_id:
                token_rect = QRectF(destination_rects[destination_id]).adjusted(22, 5, -22, -5)
            motion = self.mercy_loom_motion
            if motion and motion["token"] == consequence_id:
                progress = min(
                    1.0,
                    (self.world_clock - motion["started"]) / max(1, motion["duration"]),
                )
                eased = progress * progress * (3.0 - 2.0 * progress)
                start = source_rect.adjusted(22, 5, -22, -5)
                end = QRectF(destination_rects[destination_id]).adjusted(22, 5, -22, -5)
                token_rect = QRectF(
                    start.x() + (end.x() - start.x()) * eased,
                    start.y() + (end.y() - start.y()) * eased,
                    start.width(),
                    start.height(),
                )
            selected = self.mercy_loom_selected == consequence_id
            if selected:
                glow = token_rect.adjusted(-7, -7, 7, 7)
                painter.setBrush(QColor(86, 246, 229, 70))
                painter.setPen(QPen(QColor("#8ff7ef"), 2))
                painter.drawEllipse(glow)
            token = token_by_id.get(consequence_id, QPixmap())
            if not token.isNull():
                self._draw_pixmap_contained(painter, token_rect, token)

        hover_text = ""
        for item in MERCY_CONSEQUENCE_LINKS:
            if source_rects[item["id"]].contains(self.hover_position.toPoint()):
                hover_text = f"{item['source']}: {item['finding']}"
            if destination_rects[item["id"]].contains(self.hover_position.toPoint()):
                hover_text = item["destination"]
        if hover_text:
            painter.fillRect(QRectF(200, 64, 560, 32), QColor(2, 6, 12, 232))
            painter.setPen(QColor("#e9f7f4"))
            self._draw_fitted_text(
                painter, QRectF(218, 68, 524, 24), hover_text, 7.2, 5.2, False,
                Qt.AlignCenter | Qt.TextWordWrap,
            )
        elif self.mercy_loom_feedback:
            painter.fillRect(QRectF(190, 64, 580, 38), QColor(2, 6, 12, 232))
            painter.setPen(QColor("#e9f7f4"))
            self._draw_fitted_text(
                painter, QRectF(208, 68, 544, 30), self.mercy_loom_feedback, 7.2, 5.1, False,
                Qt.AlignCenter | Qt.TextWordWrap,
            )
        wheel = self._mercy_loom_wheel_rect()
        painter.setPen(QPen(QColor(242, 208, 112, 150), 2))
        painter.setBrush(Qt.NoBrush)
        pulse = 2 + int((math.sin(self.world_clock / 9.0) + 1) * 2)
        painter.drawEllipse(QRectF(wheel).adjusted(pulse, pulse, -pulse, -pulse))
        painter.setPen(QColor("#f1d277"))
        self._draw_fitted_text(
            painter, QRectF(wheel).adjusted(20, 35, -20, -35),
            "AUDIT LOOM", 8, 5.8, True, Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#d8c58c"))
        self._draw_fitted_text(
            painter, QRectF(690, 548, 190, 22),
            f"AUDITS {self.mercy_loom_audits_used}/{MERCY_LOOM_AUDIT_LIMIT}",
            7, 5.2, True, Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _paint_mercy_appeal(self, painter: QPainter) -> None:
        appeal_id = self.active_mercy_appeal
        if not appeal_id:
            return
        appeal = MERCY_APPEALS[appeal_id]
        painter.fillRect(self.rect(), QColor(1, 3, 8, 244))
        self._panel(painter, QRectF(42, 26, 876, 580), QColor(3, 9, 14, 250), QColor("#8d7745"), 1)
        self._button(painter, QRect(60, 42, 100, 34), "< LEAVE", "#26383c", small=True)
        painter.setPen(QColor("#f2d276"))
        self._draw_fitted_text(
            painter, QRectF(205, 38, 550, 38), appeal["title"], 15, 9, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        visual_rect = QRectF(94, 86, 772, 306)
        self._panel(painter, visual_rect, QColor(1, 4, 8, 252), QColor("#557d78"), 1)
        frames = self.mercy_cinematic_frames.get(appeal_id, [])
        frame = 0
        if frames:
            clip_rect = visual_rect.adjusted(4, 4, -4, -4)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(clip_rect, 5, 5)
            elapsed = max(0, self.world_clock - self.mercy_appeal_clip_started)
            frame_position = (elapsed % (32 * len(frames))) / 32.0
            frame = int(frame_position) % len(frames)
            next_frame = (frame + 1) % len(frames)
            blend = frame_position - int(frame_position)
            blend = blend * blend * (3.0 - 2.0 * blend)
            painter.save()
            painter.setClipPath(clip_path)
            self._draw_pixmap_cover(painter, clip_rect, frames[frame], focus_y=0.48)
            if blend > 0.0:
                painter.setOpacity(blend)
                self._draw_pixmap_cover(painter, clip_rect, frames[next_frame], focus_y=0.48)
            painter.restore()
        painter.fillRect(QRectF(94, 352, 772, 40), QColor(1, 4, 8, 185))
        painter.setPen(QColor("#f3e2b0"))
        self._draw_fitted_text(
            painter, QRectF(116, 356, 728, 31), appeal["beats"][frame], 7.8, 5.8, False,
            Qt.AlignCenter | Qt.TextWordWrap,
        )
        painter.setPen(QColor("#8ff4ed"))
        self._draw_fitted_text(
            painter, QRectF(170, 402, 620, 42), appeal["question"], 10, 7, True,
            Qt.AlignCenter | Qt.TextWordWrap,
        )
        for option, rect in zip(appeal["options"], self._mercy_appeal_option_rects()):
            selected = self.mercy_appeal_selection == option[0]
            self._panel(
                painter, QRectF(rect),
                QColor("#173b3c") if selected else QColor(8, 24, 27, 245),
                QColor("#79eee5") if selected else QColor("#8d7745"), 2 if selected else 1,
            )
            painter.setPen(QColor("#f1d57a"))
            self._draw_fitted_text(
                painter, QRectF(rect).adjusted(12, 8, -12, -8), option[1], 8.5, 6, True,
                Qt.AlignCenter | Qt.TextSingleLine,
            )
        hover_detail = ""
        for option, rect in zip(appeal["options"], self._mercy_appeal_option_rects()):
            if rect.contains(self.hover_position.toPoint()):
                hover_detail = option[2]
                break
        if self.mercy_appeal_feedback:
            painter.setPen(QColor("#9ff2eb") if self.mercy_appeal_success else QColor("#ef9b98"))
            self._draw_fitted_text(
                painter, QRectF(110, 520, 740, 28), self.mercy_appeal_feedback, 6.8, 5.2, True,
                Qt.AlignCenter | Qt.TextWordWrap,
            )
        elif hover_detail:
            painter.setPen(QColor("#d8e9e5"))
            self._draw_fitted_text(
                painter, QRectF(110, 520, 740, 28), hover_detail, 6.8, 5.2, False,
                Qt.AlignCenter | Qt.TextWordWrap,
            )
        self._button(painter, QRect(350, 554, 260, 38), "RECORD FINDING", "#2c9289", small=True)

    def _paint_order_investigation(self, painter: QPainter):
        investigation_id = self.active_order_investigation or "identity"
        station = ORDER_STATIONS[investigation_id]
        case = self._order_current_case()
        painter.fillRect(self.rect(), QColor(2, 5, 10, 208))
        if not self.registry_investigation_panel.isNull():
            painter.drawPixmap(self.rect(), self.registry_investigation_panel)
        else:
            self._panel(painter, QRectF(72, 34, 816, 570), QColor(7, 20, 22, 250), QColor("#bf9850"), 2)
        painter.fillRect(QRectF(85, 48, 790, 548), QColor(2, 11, 13, 48))

        self._button(painter, self._order_investigation_leave_rect(), "< LEAVE", "#24363b", small=True)
        painter.setPen(QColor("#f0d27b"))
        self._draw_fitted_text(
            painter, QRectF(238, 48, 385, 31), station["title"].upper(), 15, 9, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        self._button(painter, self._order_hint_rect(), "HINT", "#6f5631", small=True)
        self._button(painter, self._order_case_file_rect(), "CASE FILE", "#274b49", small=True)
        action_text = {
            "identity": "CHOOSE THE PERSON WHO FITS THE EVIDENCE",
            "sequence": "PUT THE FOUR SURVIVING SCRAPS IN ORDER",
            "authority": "WHICH SEAL BURIED A LIVING DOCKET?",
        }[investigation_id]
        painter.setPen(QColor("#83eee6"))
        self._draw_fitted_text(
            painter, QRectF(190, 83, 430, 25), action_text, 8.5, 6, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#b8d6d0"))
        self._draw_fitted_text(
            painter, QRectF(145, 113, 470, 21), "CASE FILE: DISCOVERED EVIDENCE   |   HINT: ONE STEP AT A TIME",
            6.7, 5.2, True, Qt.AlignCenter | Qt.TextSingleLine,
        )

        gauge = QRectF(704, 113, 136, 13)
        self._bar(painter, gauge, self.state.order_corruption, 3, "#d9a044", "#b92668")
        painter.setPen(QColor("#eedbb0"))
        self._draw_fitted_text(
            painter, QRectF(680, 128, 180, 18), f"REGISTRY CORRUPTION  {self.state.order_corruption}/3",
            6.5, 4.5, True, Qt.AlignCenter | Qt.TextSingleLine,
        )

        evidence_rects = self._order_investigation_evidence_rects()
        self._panel(painter, evidence_rects["panel"], QColor(2, 16, 17, 238), QColor("#a98a48"), 1)
        self._paint_registry_visual_clip(painter, investigation_id, evidence_rects)

        rects = self._order_investigation_option_rects()
        if investigation_id == "sequence":
            event_text = dict(case["events"])
            entries = [(event_id, event_text[event_id]) for event_id in self.order_sequence]
        else:
            entries = [(option[0], "\n".join(option[1:])) for option in case["options"]]
        for index, ((_, label), rect) in enumerate(zip(entries, rects)):
            selected = index == self.order_selected_index
            fill = QColor(33, 72, 67, 242) if selected else QColor(4, 22, 23, 232)
            border = QColor("#82f3df") if selected else QColor("#9b7c3f")
            self._panel(painter, QRectF(rect), fill, border, 2 if selected else 1)
            painter.setPen(QColor("#ffffff") if selected else QColor("#e4dcc2"))
            option_id = entries[index][0]
            if investigation_id == "identity":
                portrait = self.registry_portraits.get(option_id, QPixmap())
                card_rect = QRectF(rect).adjusted(2, 2, -2, -2)
                self._draw_pixmap_cover(painter, card_rect, portrait, focus_y=0.36)
                painter.fillRect(
                    QRectF(card_rect.left(), card_rect.bottom() - 33, card_rect.width(), 33),
                    QColor(2, 10, 13, 218),
                )
                if QRectF(rect).contains(self.hover_position):
                    painter.fillRect(card_rect, QColor(80, 235, 220, 28))
                text_rect = QRectF(rect.x() + 8, rect.bottom() - 32, rect.width() - 16, 27)
                display_name = next(
                    (option[1] for option in case["options"] if option[0] == option_id), label
                )
                painter.setPen(QColor("#ffffff"))
                self._draw_fitted_text(
                    painter, text_rect, display_name, 7.6, 5.4, True,
                    Qt.AlignCenter | Qt.TextSingleLine,
                )
            else:
                row = self._registry_visual_row(investigation_id, option_id)
                visual_rows = self.registry_visual_clip_frames.get(investigation_id, ())
                thumbnail = (
                    visual_rows[row][1]
                    if row < len(visual_rows) and len(visual_rows[row]) > 1
                    else QPixmap()
                )
                thumb_width = 64 if investigation_id == "sequence" else 78
                thumb_rect = QRectF(
                    rect.x() + 6, rect.y() + 5, thumb_width, rect.height() - 10
                )
                self._draw_pixmap_cover(painter, thumb_rect, thumbnail)
                text_rect = QRectF(rect).adjusted(thumb_width + 14, 6, -10, -6)
                if investigation_id == "sequence":
                    short_labels = {
                        "vanishing_petitions": "Names vanish from ink",
                        "secret_copy": "Marr hides a surviving copy",
                        "black_seal": "A sealed transfer is authorized",
                        "bellglass_fire": "Blue fire reaches the stacks",
                    }
                    label = f"{index + 1}.  {short_labels.get(option_id, label)}"
                elif investigation_id == "authority":
                    label = next(
                        (option[1] for option in case["options"] if option[0] == option_id),
                        label,
                    )
                self._draw_fitted_text(
                    painter, text_rect, label,
                    7.5 if investigation_id == "sequence" else 7.1, 5.0, True,
                    Qt.AlignCenter | Qt.TextWordWrap,
                )

        if investigation_id in {"identity", "authority"}:
            hovered_index = next(
                (
                    index
                    for index, rect in enumerate(rects)
                    if QRectF(rect).contains(self.hover_position)
                ),
                None,
            )
            if hovered_index is not None and hovered_index < len(entries):
                option_id = entries[hovered_index][0]
                tooltip_map = (
                    REGISTRY_CHARACTER_TOOLTIPS
                    if investigation_id == "identity"
                    else REGISTRY_AUTHORITY_TOOLTIPS
                )
                tooltip = tooltip_map.get(option_id, "")
                if tooltip:
                    tooltip_rect = QRectF(635, 498, 232, 38)
                    self._panel(
                        painter, tooltip_rect, QColor(3, 12, 17, 248),
                        QColor("#73ddd4"), 1,
                    )
                    painter.setPen(QColor("#dcefeb"))
                    self._draw_fitted_text(
                        painter, tooltip_rect.adjusted(9, 5, -9, -5), tooltip,
                        6.1, 4.5, False, Qt.AlignCenter | Qt.TextWordWrap,
                    )

        if self.order_investigation_feedback:
            painter.setPen(QColor("#7df1dc") if self.order_feedback_success else QColor("#ff9aa9"))
            self._draw_fitted_text(
                painter, QRectF(180, 508, 600, 30), self.order_investigation_feedback,
                7.5, 5, True, Qt.AlignCenter | Qt.TextWordWrap,
            )
        submit = {
            "identity": "RESTORE IDENTITY",
            "sequence": "SEAL CHRONOLOGY",
            "authority": "RESTORE AUTHORITY",
        }[investigation_id]
        self._button(painter, self._order_investigation_submit_rect(), submit, "#2b8077", small=True)
        if investigation_id == "sequence":
            painter.setPen(QColor("#abcfc9"))
            self._draw_fitted_text(
                painter, QRectF(200, 592, 560, 18), "SELECT TWO SCRAPS TO SWAP THEM",
                6.5, 4.5, True, Qt.AlignCenter | Qt.TextSingleLine,
            )
        if self.order_case_file_open:
            self._paint_order_case_file(painter)

    def _order_case_file_entries(self, section: str) -> tuple[tuple[str, str], ...]:
        findings = set(self.state.order_investigations_completed)
        active = self.active_order_investigation
        case = self._order_current_case()

        if active == "identity" and "identity" not in findings:
            people = tuple(
                (name.upper(), role)
                for _option_id, name, role in case["options"]
            )
        else:
            people_entries = []
            if "identity" in findings:
                people_entries.append((
                    "ELIAN VEY  /  CONFIRMED",
                    "Chronometer keeper. Identified by the hourglass key, the initials E.V., and Marr's surviving note.",
                ))
            if "sequence" in findings:
                people_entries.append((
                    "LYSA MARR  /  CONFIRMED",
                    "Deputy registrar and copyist. Hid a duplicate of Docket VII-13 before the transfer and fire.",
                ))
            if "authority" in findings:
                people_entries.append((
                    "ORREN VALE  /  CONFIRMED",
                    "Chancellor of Final Disposition. His Black Sun seal authorized the transfer below public review.",
                ))
            people = tuple(people_entries) or ((
                "NO IDENTITIES RECOVERED",
                "No verified name has been recovered from the damaged docket.",
            ),)

        if active == "authority" and "authority" not in findings:
            seals = tuple(
                (name.upper(), role)
                for _option_id, name, role in case["options"]
            )
        elif "authority" in findings:
            seals = ((
                "BLACK SUN  /  CONFIRMED",
                "The only recovered seal with authority to transfer a living docket beneath public review.",
            ),)
        else:
            seals = ((
                "NO SEAL REFERENCES RECOVERED",
                "A seal station must be examined before its marks can enter the file.",
            ),)

        if active == "sequence" and "sequence" not in findings:
            event_text = dict(case["events"])
            chronology = tuple(
                (f"LOOSE SCRAP {index + 1}", event_text[event_id])
                for index, event_id in enumerate(self.order_sequence)
            )
        elif "sequence" in findings:
            chronology = (
                ("1  KEEPER'S COUNT", "Vey records seven petitions missing from ink but still present in wax."),
                ("2  COPYIST'S NOTE", "Marr hides a duplicate before the official docket can be altered."),
                ("3  TRANSFER ORDER", "Vale affixes the Black Sun and sends the living docket below review."),
                ("4  BELLWRIGHT'S REPORT", "Blue fire reaches the western stacks after the transfer."),
            )
        else:
            chronology = ((
                "NO CHRONOLOGY RECOVERED",
                "The surviving scraps have not yet been examined at the Ledger of Sequence.",
            ),)

        finding_entries = []
        if "identity" in findings:
            finding_entries.append(("IDENTITY", "Elian Vey was deliberately removed from the keeper's line."))
        if "sequence" in findings:
            finding_entries.append(("SEQUENCE", "The disappearance was discovered before the copy, transfer, and fire."))
        if "authority" in findings:
            finding_entries.append(("AUTHORITY", "Orren Vale's Black Sun seal authorized the hidden transfer."))
        confirmed_findings = tuple(finding_entries) or ((
            "EMPTY MASTER DOCKET",
            "Solve a Registry station to add the first confirmed finding.",
        ),)

        sections = {
            "people": people,
            "seals": seals,
            "chronology": chronology,
            "findings": confirmed_findings,
        }
        return sections.get(section, sections["people"])

    def _paint_order_case_file(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(1, 4, 8, 205))
        dossier = QRectF(112, 62, 736, 500)
        self._panel(painter, dossier, QColor(5, 17, 20, 252), QColor("#d1aa57"), 2)
        self._button(painter, self._order_case_file_close_rect(), "CLOSE", "#3a4548", small=True)
        painter.setPen(QColor("#f2d27b"))
        self._draw_fitted_text(
            painter, QRectF(230, 78, 500, 36), "DOCKET VII-13  /  CASE FILE", 14, 8.5, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#80ded7"))
        self._draw_fitted_text(
            painter, QRectF(220, 112, 520, 20), "SELECT A REGISTER  |  MOUSE WHEEL OR ARROWS TO SCROLL",
            7.2, 5.2, True, Qt.AlignCenter | Qt.TextSingleLine,
        )

        labels = {
            "people": "PERSONS",
            "seals": "SEALS",
            "chronology": "CHRONOLOGY",
            "findings": "FINDINGS",
        }
        for section, rect in self._order_case_file_tab_rects().items():
            active = section == self.order_case_file_section
            self._button(painter, rect, labels[section], "#2c7770" if active else "#25363b", small=True)

        viewport = self._order_case_file_viewport_rect()
        self._panel(painter, QRectF(viewport), QColor(2, 12, 16, 238), QColor("#6f633d"), 1)
        painter.save()
        painter.setClipRect(viewport.adjusted(8, 8, -8, -8))
        y = viewport.top() + 12 - self.order_case_file_scroll
        for title, body in self._order_case_file_entries(self.order_case_file_section):
            card = QRectF(viewport.left() + 12, y, viewport.width() - 38, 80)
            self._panel(painter, card, QColor(8, 25, 28, 238), QColor("#365e5a"), 1)
            painter.setPen(QColor("#f1cf74"))
            self._draw_fitted_text(
                painter, card.adjusted(14, 8, -14, -48), title, 8.8, 6.2, True,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
            )
            painter.setPen(QColor("#d4e1dd"))
            self._draw_fitted_text(
                painter, card.adjusted(14, 31, -14, -8), body, 8.2, 6, False,
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            )
            y += 92
        painter.restore()

        down_rect, up_rect = self._order_case_file_scroll_rects()
        self._button(painter, up_rect, "^", "#334a4c", small=True)
        self._button(painter, down_rect, "v", "#334a4c", small=True)
        track = QRectF(818, viewport.top() + 10, 7, viewport.height() - 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#182c30"))
        painter.drawRoundedRect(track, 3, 3)
        maximum = self._order_case_file_max_scroll()
        thumb_height = max(56.0, track.height() * min(1.0, viewport.height() / max(viewport.height(), self._order_case_file_entry_count() * 92 + 18)))
        thumb_y = track.top() if maximum == 0 else track.top() + (track.height() - thumb_height) * self.order_case_file_scroll / maximum
        painter.setBrush(QColor("#5ad8cf"))
        painter.drawRoundedRect(QRectF(track.left(), thumb_y, track.width(), thumb_height), 3, 3)

        painter.setPen(QColor("#87e7df"))
        self._draw_fitted_text(
            painter, QRectF(250, 530, 460, 18), "ONLY VERIFIED EVIDENCE IS ENTERED HERE.",
            7, 5, True, Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _paint_coupled_registry_idle_mechanics(self, painter: QPainter) -> None:
        """Drive independent gears from the active rotor while fixed chains stay fixed."""
        if not self.coupled_registry_mechanics:
            return
        panel_rect = QRectF(120, 78, 720, 478)
        animation = self.order_rotor_animation
        affected: tuple[int, ...] = ()
        drive_turn = 0.0
        if animation:
            progress = min(1.0, max(0.0, (self.world_clock - animation["started"]) / animation["duration"]))
            drive_turn = self._registry_drive_turn(progress)
            affected = tuple(animation["affected"])
        gear_specs = (
            (302, 201, 29, 0, 1, (0,)),
            (340, 263, 24, 1, -1, (0, 1)),
            (378, 201, 27, 0, -1, (1,)),
            (480, 210, 30, 1, 1, (1, 2)),
            (582, 201, 27, 0, -1, (2,)),
            (620, 263, 24, 1, 1, (2, 3)),
            (658, 201, 29, 0, 1, (3,)),
        )
        painter.save()
        panel_clip = QPainterPath()
        panel_clip.addRoundedRect(panel_rect, 12, 12)
        painter.setClipPath(panel_clip)
        for center_x, center_y, radius, asset_index, direction, drivers in gear_specs:
            gear = self.coupled_registry_mechanics[asset_index]
            engaged = any(driver in affected for driver in drivers)
            turn = direction * (self.world_clock * 0.24 + (drive_turn if engaged else 0.0))
            painter.save()
            painter.translate(center_x, center_y)
            painter.rotate(turn)
            self._draw_pixmap_contained(
                painter, QRectF(-radius, -radius, radius * 2, radius * 2), gear
            )
            painter.restore()

        # The drive is assembled from independent generated components. Its
        # wheel, gear, rod, and piston therefore share one continuous crank
        # angle instead of dissolving between differently registered drawings.
        if len(self.coupled_registry_drive_components) == 4:
            self._paint_registry_continuous_drive(
                painter,
                drive_turn,
                active=bool(animation),
            )
        vial = self.coupled_registry_mechanics[5]
        drive_pulse = math.sin(math.pi * progress) if animation else 0.0
        pulse = min(1.0, 0.72 + 0.12 * (0.5 + 0.5 * math.sin(self.world_clock / 7)) + drive_pulse * 0.28)
        for x in (350, 610):
            painter.save()
            painter.setOpacity(pulse)
            self._draw_pixmap_contained(painter, QRectF(x, 366, 28, 76), vial)
            painter.restore()
        painter.restore()

    def _paint_registry_continuous_drive(
        self,
        painter: QPainter,
        drive_turn: float,
        *,
        active: bool,
    ) -> None:
        """Render one closed crank cycle from stable, independently anchored parts."""
        housing, gear, rod, regulator = self.coupled_registry_drive_components
        opacity = 0.68 if active else 0.50

        # This wheel is a secondary governor, so it sits behind the piston and
        # remains visually quieter than the four playable registry rotors.
        regulator_center = QPointF(480.0, 389.0)
        painter.save()
        painter.setOpacity(opacity * 0.86)
        painter.translate(regulator_center)
        painter.rotate(drive_turn)
        self._draw_pixmap_contained(
            painter, QRectF(-55.0, -55.0, 110.0, 110.0), regulator
        )
        painter.restore()

        painter.save()
        painter.setOpacity(opacity)
        self._draw_pixmap_contained(painter, QRectF(451.0, 252.0, 58.0, 135.0), housing)
        painter.restore()

        # A slider-crank converts the gear's rotation into vertical piston
        # travel. Both endpoints return to the exact same coordinates at 360°.
        gear_center, crank_pin, piston_pin = self._registry_drive_geometry(drive_turn)

        painter.save()
        painter.setOpacity(opacity * 0.96)
        self._paint_component_between(painter, rod, piston_pin, crank_pin, 16.0)
        painter.restore()

        painter.save()
        painter.setOpacity(opacity)
        painter.translate(gear_center)
        painter.rotate(-drive_turn * 2.0)
        self._draw_pixmap_contained(painter, QRectF(-29.0, -29.0, 58.0, 58.0), gear)
        painter.restore()

    @staticmethod
    def _registry_drive_geometry(drive_turn: float) -> tuple[QPointF, QPointF, QPointF]:
        """Return stable gear, crank, and piston pivots for one closed drive cycle."""
        theta = math.radians(-drive_turn)
        gear_center = QPointF(510.0, 365.0)
        crank_radius = 14.0
        crank_pin = QPointF(
            gear_center.x() + math.cos(theta) * crank_radius,
            gear_center.y() + math.sin(theta) * crank_radius,
        )
        piston_pin = QPointF(480.0, 311.0 + (1.0 - math.cos(theta)) * 10.0)
        return gear_center, crank_pin, piston_pin

    def _paint_component_between(
        self,
        painter: QPainter,
        component: QPixmap,
        start: QPointF,
        end: QPointF,
        thickness: float,
    ) -> None:
        """Draw a horizontal component between two pivots without changing its ends."""
        delta_x = end.x() - start.x()
        delta_y = end.y() - start.y()
        length = math.hypot(delta_x, delta_y)
        if length <= 0.01:
            return
        midpoint = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        painter.save()
        painter.translate(midpoint)
        painter.rotate(math.degrees(math.atan2(delta_y, delta_x)))
        self._draw_pixmap_contained(
            painter,
            QRectF(-length / 2.0 - 7.0, -thickness / 2.0, length + 14.0, thickness),
            component,
        )
        painter.restore()

    @staticmethod
    def _registry_drive_turn(progress: float) -> float:
        """Return one eased revolution whose endpoint is the resting tooth alignment."""
        bounded = min(1.0, max(0.0, progress))
        eased = bounded * bounded * (3.0 - 2.0 * bounded)
        return eased * 360.0

    def _paint_registry_north_lock(self, painter: QPainter, rect: QRect, index: int) -> None:
        """Use an authored north-lock halo instead of a generic solved circle."""
        if len(self.coupled_registry_mechanics) < 7:
            return
        halo = self.coupled_registry_mechanics[6]
        phase = 0.5 + 0.5 * math.sin(self.world_clock / 7 + index * 1.3)
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        painter.setOpacity(0.56 + 0.28 * phase)
        target = QRectF(rect).adjusted(-11 - phase * 2, -11 - phase * 2, 11 + phase * 2, 11 + phase * 2)
        self._draw_pixmap_contained(painter, target, halo)
        painter.restore()

    def _paint_order_puzzle(self, painter: QPainter):
        self._paint_coupled_registry_idle_mechanics(painter)
        labels = ("IDENTITY", "SEQUENCE", "AUTHORITY", "CONCORDANCE")
        animation = self.order_rotor_animation
        progress = 1.0
        affected: tuple[int, ...] = ()
        if animation:
            progress = min(1.0, max(0.0, (self.world_clock - animation["started"]) / animation["duration"]))
            affected = tuple(animation["affected"])
        for index, (value, rect) in enumerate(zip(self.order_rings, self._order_puzzle_rects())):
            rotor = self.coupled_registry_rotors[index] if index < len(self.coupled_registry_rotors) else QPixmap()
            if rotor.isNull():
                continue
            eased = progress * progress * (3.0 - 2.0 * progress)
            angle = value * 90.0
            if index in affected:
                angle -= (1.0 - eased) * 90.0
            center = QRectF(rect).center()
            painter.save()
            painter.translate(center)
            painter.rotate(angle)
            self._draw_pixmap_contained(
                painter,
                QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height()),
                rotor,
            )
            painter.restore()
            shimmer = 0.06 + 0.08 * (0.5 + 0.5 * math.sin(self.world_clock / 8 + index * 1.7))
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode_Screen)
            painter.setOpacity(shimmer)
            painter.translate(center)
            painter.rotate(angle)
            self._draw_pixmap_contained(
                painter,
                QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height()),
                rotor,
            )
            painter.restore()
            if value == 0:
                self._paint_registry_north_lock(painter, rect, index)
            if index in affected and len(self.coupled_registry_mechanics) >= 8:
                engagement = self.coupled_registry_mechanics[7]
                impact = math.sin(math.pi * progress)
                painter.save()
                painter.setCompositionMode(QPainter.CompositionMode_Screen)
                painter.setOpacity(max(0.0, impact) * 0.72)
                self._draw_pixmap_contained(
                    painter, QRectF(rect).adjusted(-8, -8, 8, 8), engagement
                )
                painter.restore()
            painter.setPen(QColor("#f2d482"))
            self._draw_fitted_text(
                painter,
                QRectF(rect.x() - 12, rect.bottom() + 5, rect.width() + 24, 18),
                labels[index],
                6.2,
                4.5,
                True,
                Qt.AlignCenter | Qt.TextSingleLine,
            )
        painter.setPen(QColor("#b8fff8"))
        if self.order_last_rotor is None:
            registry_text = "TURN A ROTOR TO READ WHAT THAT REGISTRY CONTROLS."
        else:
            rotor_name, rotor_record = ORDER_ROTOR_RECORDS[self.order_last_rotor]
            registry_text = f"{rotor_name}: {rotor_record}"
        self._draw_fitted_text(
            painter,
            QRectF(190, 430, 580, 42),
            registry_text,
            7.2,
            5.0,
            True,
            Qt.AlignCenter | Qt.TextWordWrap,
        )
        turns_left = max(0, ORDER_TURN_LIMIT - self.order_turns_used)
        painter.setPen(QColor("#d8bd73"))
        self._draw_fitted_text(
            painter,
            QRectF(576, 493, 176, 24),
            f"TURNS LEFT  {turns_left}/{ORDER_TURN_LIMIT}",
            6.6,
            5.0,
            True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        button_label = "MECHANISM CYCLING" if animation else "STAMP REGISTRY"
        button_color = "#34363b" if animation else "#725829"
        self._button(painter, QRect(390, 486, 180, 42), button_label, button_color, small=True)

    def _paint_battle(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(4, 3, 14, 108))
        enemy = ENEMIES[self.battle_enemy_id]
        painter.setPen(QColor("#f1d17d"))
        self._draw_fitted_text(painter, QRect(250, 22, 460, 32), enemy["name"], 13, 8, True)
        if self.battle_enemy_id == "pending":
            boss_pixmap = self.pending_combat.get(self.pending_pose, QPixmap())
        else:
            boss_pixmap = self.trial_enemies[enemy["sprite_group"]].get(self.enemy_pose, QPixmap())
        if not boss_pixmap.isNull():
            boss_target = QRectF(640, 74, 265, 330) if self.battle_enemy_id == "pending" else QRectF(555, 64, 330, 358)
            self._draw_pixmap_contained(painter, boss_target, boss_pixmap)
        if self.battle_enemy_id == "pending":
            self._paint_pending_minions(painter)
        self._paint_hero_battle(painter)
        self._bar(painter, QRectF(574, 60, 272, 13), self.boss_hp, self.boss_max_hp, "#9c4dcc", "#e34d79")
        if self.boss_marked:
            painter.setPen(QColor("#ff98a9"))
            self._draw_fitted_text(painter, QRectF(574, 78, 272, 16), "WAX MARKED", 7.5, 5.5, True)
        if self.battle_enemy_id == "misfiled_mimic":
            required = {"identity": "Q  QUILL SLASH", "sequence": "W  FILE WARD", "authority": "E  WAX MARK"}
            colors = {"identity": "#66e5dc", "sequence": "#e4bc62", "authority": "#dd6d9b"}
            sigil_rect = QRectF(570, 80, 282, 31)
            self._panel(painter, sigil_rect, QColor(4, 11, 20, 235), QColor(colors[self.mimic_classification]), 2)
            painter.setPen(QColor(colors[self.mimic_classification]))
            self._draw_fitted_text(
                painter, sigil_rect.adjusted(8, 3, -8, -3),
                f"{self.mimic_classification.upper()}  >  {required[self.mimic_classification]}",
                7.5, 5.5, True, Qt.AlignCenter | Qt.TextSingleLine,
            )
        self._panel(painter, QRectF(38, 411, 884, 55), QColor(8, 9, 20, 238), QColor("#544d80"))
        painter.setPen(QColor("#eff0f4"))
        self._draw_fitted_text(painter, QRectF(60, 419, 840, 38), self.battle_message, 9.5, 6.5)
        self._paint_combat_hud(painter)

    @staticmethod
    def _minion_positions() -> tuple[tuple[int, int], ...]:
        return ((500, 246), (590, 365), (866, 365))

    def _paint_pending_minions(self, painter: QPainter):
        if self.minion_sheet.isNull():
            return
        frame_width = self.minion_sheet.width() / 4
        for index, (minion, (x, y)) in enumerate(zip(self.minions, self._minion_positions())):
            if minion["hp"] > 0:
                attacking = self.battle_locked and self.pending_pose in {"windup", "release", "vortex"}
                frame = 2 if attacking else (self.world_clock // 24 + index) % 2
                opacity = 1.0
            elif minion["respawn"] < 0:
                frame, opacity = 3, 0.55
            else:
                frame, opacity = 3, 0.32 + 0.12 * math.sin(self.world_clock / 5 + index)
            source = QRectF(frame * frame_width, 0, frame_width, self.minion_sheet.height())
            painter.save()
            painter.setOpacity(opacity)
            target = QRectF(x - 52, y - 102, 104, 118)
            self._draw_pixmap_contained(painter, target, self.minion_sheet.copy(source.toRect()))
            painter.restore()
            if minion["hp"] > 0:
                self._bar(painter, QRectF(x - 34, y + 8, 68, 7), minion["hp"], minion["max_hp"], "#5b2b8f", "#b765ee")
            elif minion["respawn"] > 0:
                painter.setPen(QColor("#c9a5ec"))
                self._draw_fitted_text(painter, QRectF(x - 45, y + 4, 90, 16), f"REFORMS {minion['respawn']}", 5.5, 4, True)

    def _paint_combat_hud(self, painter: QPainter):
        self._panel(painter, QRectF(12, 476, 936, 151), QColor(5, 8, 18, 246), QColor("#5ed7d4"), 1)
        portrait = QRectF(25, 489, 90, 104)
        painter.setBrush(QColor("#10172a"))
        painter.setPen(QPen(QColor("#cdbd70"), 2))
        painter.drawRoundedRect(portrait, 4, 4)
        ready = self.hero_combat.get("ready", QPixmap())
        if not ready.isNull():
            self._draw_pixmap_contained(painter, portrait.adjusted(4, 4, -4, -4), ready)

        painter.setPen(QColor("#f0d17b"))
        self._draw_fitted_text(
            painter, QRectF(126, 491, 196, 19), "THE LAST CLERK", 9, 6.5, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        self._bar(painter, QRectF(126, 518, 196, 14), self.state.player_hp, 100, "#159b72", "#59e7b1")
        painter.setPen(QColor("#e9eef2"))
        self._draw_fitted_text(
            painter, QRectF(126, 537, 196, 17), f"HP  {self.state.player_hp} / 100", 7, 5.5, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#e7c967"))
        self._draw_fitted_text(
            painter, QRectF(126, 562, 196, 19), f"FOCUS  {'◆' * self.focus}{'◇' * (3 - self.focus)}", 8, 5.5, True,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
        )

        for key, rect in self._ability_rects().items():
            self._paint_ability_slot(painter, key, rect)
        for item, rect in self._item_rects().items():
            self._paint_item_slot(painter, item, rect)

        painter.setPen(QColor("#82909f"))
        self._draw_fitted_text(
            painter, QRectF(817, 493, 117, 18), "TRIAL RELICS", 7, 5.5, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.setPen(QColor("#a9b5c3"))
        self._draw_fitted_text(painter, QRectF(817, 577, 117, 34), "CLICK OR PRESS\nTHE SHOWN KEY", 6.5, 5)

    @staticmethod
    def _ability_rects() -> dict[str, QRect]:
        return {key: QRect(347 + index * 88, 493, 76, 76) for index, key in enumerate(ABILITY_ORDER)}

    @staticmethod
    def _item_rects() -> dict[str, QRect]:
        return {
            "appeal_tonic": QRect(820, 516, 34, 40),
            "reset_compass": QRect(859, 516, 34, 40),
            "recall_lens": QRect(898, 516, 34, 40),
        }

    def _paint_ability_slot(self, painter: QPainter, key: str, rect: QRect):
        definition = ABILITY_DEFS[key]
        cooldown = self._ability_cooldown(key)
        unavailable = key == "R" and self.focus < 3
        painter.setBrush(QColor("#111a2a"))
        painter.setPen(QPen(QColor(definition["color"]), 2 if not cooldown and not unavailable else 1))
        painter.drawRoundedRect(QRectF(rect), 5, 5)
        icon = self.combat_icons.get(definition["action"], QPixmap())
        if not icon.isNull():
            painter.drawPixmap(rect.adjusted(4, 4, -4, -4), icon)
        if cooldown or unavailable:
            painter.setBrush(QColor(2, 5, 12, 178))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(rect.adjusted(3, 3, -3, -3)), 4, 4)
        if cooldown:
            painter.setPen(QColor("#ffffff"))
            self._draw_fitted_text(painter, rect, str(cooldown), 18, 10, True)
        elif unavailable:
            painter.setPen(QColor("#e6c96b"))
            self._draw_fitted_text(painter, rect, "3 FOCUS", 7, 5, True)

        key_rect = QRectF(rect.x() + 4, rect.y() + 4, 19, 19)
        painter.setBrush(QColor(5, 8, 18, 224))
        painter.setPen(QPen(QColor("#e6d379"), 1))
        painter.drawRoundedRect(key_rect, 3, 3)
        painter.setPen(QColor("#ffffff"))
        self._draw_fitted_text(painter, key_rect, key, 8, 6, True)
        painter.setPen(QColor("#d7e2ea"))
        self._draw_fitted_text(
            painter, QRectF(rect.x() - 5, rect.bottom() + 4, rect.width() + 10, 29),
            definition["name"].upper(), 6.5, 4.5, True,
        )

    def _paint_item_slot(self, painter: QPainter, item: str, rect: QRect):
        definition = ITEM_DEFS[item]
        count = self.battle_items.get(item, 0)
        painter.setBrush(QColor("#111a2a"))
        painter.setPen(QPen(QColor("#6faab5") if count else QColor("#424b58"), 1))
        painter.drawRoundedRect(QRectF(rect), 4, 4)
        icon_group = self.quest_icons if definition.get("icon_group") == "quest" else self.combat_icons
        icon = icon_group.get(definition.get("icon", item), QPixmap())
        if not icon.isNull():
            painter.drawPixmap(rect.adjusted(3, 3, -3, -3), icon)
        sealed = item == self.mimic_sealed_item and self.mimic_sealed_item_turns > 0
        if not count or sealed:
            painter.fillRect(rect.adjusted(2, 2, -2, -2), QColor(2, 5, 12, 176))
        if sealed:
            painter.setPen(QColor("#ff85a7"))
            self._draw_fitted_text(painter, rect.adjusted(2, 3, -2, -3), "SEALED", 5.5, 4, True)
        key_rect = QRectF(rect.x() + 2, rect.y() + 2, 15, 15)
        painter.setBrush(QColor(5, 8, 18, 220))
        painter.setPen(QPen(QColor("#e6d379"), 1))
        painter.drawRoundedRect(key_rect, 2, 2)
        painter.setPen(QColor("#ffffff"))
        self._draw_fitted_text(painter, key_rect, definition["key"], 7, 5, True)
        painter.setPen(QColor("#cbd6de"))
        self._draw_fitted_text(
            painter, QRectF(rect.x() - 5, rect.bottom() + 2, rect.width() + 10, 20),
            definition["name"].upper(), 5.5, 4, True,
        )

    @staticmethod
    def _draw_pixmap_contained(painter: QPainter, target: QRectF, pixmap: QPixmap):
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return
        scale = min(target.width() / pixmap.width(), target.height() / pixmap.height())
        width = pixmap.width() * scale
        height = pixmap.height() * scale
        fitted = QRectF(
            target.center().x() - width / 2,
            target.center().y() - height / 2,
            width,
            height,
        )
        painter.drawPixmap(fitted, pixmap, QRectF(pixmap.rect()))

    @staticmethod
    def _draw_pixmap_cover(
        painter: QPainter, target: QRectF, pixmap: QPixmap, focus_y: float = 0.5
    ):
        """Fill a target with a centered crop, like a cinematic cover frame."""
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return
        target_ratio = target.width() / max(1.0, target.height())
        source_ratio = pixmap.width() / max(1.0, float(pixmap.height()))
        if source_ratio > target_ratio:
            source_height = float(pixmap.height())
            source_width = source_height * target_ratio
            source = QRectF(
                (pixmap.width() - source_width) / 2.0, 0.0,
                source_width, source_height,
            )
        else:
            source_width = float(pixmap.width())
            source_height = source_width / target_ratio
            source_top = pixmap.height() * focus_y - source_height / 2.0
            source_top = max(0.0, min(pixmap.height() - source_height, source_top))
            source = QRectF(
                0.0, source_top,
                source_width, source_height,
            )
        painter.drawPixmap(target, pixmap, source)

    @staticmethod
    def _fixed_height_floor_target(
        target: QRectF, pixmap: QPixmap, height_scale: float = 1.0
    ) -> QRectF:
        """Scale a sprite by height while keeping its feet on a stable baseline."""
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return QRectF()
        height = target.height() * height_scale
        width = pixmap.width() * height / pixmap.height()
        return QRectF(
            target.center().x() - width / 2,
            target.bottom() - height,
            width,
            height,
        )

    def _paint_hero_battle(self, painter: QPainter):
        pixmap = self.hero_combat.get(self.hero_combat_pose, QPixmap())
        if pixmap.isNull():
            return
        target = QRectF(62, 74, 330, 340)
        if self.hero_combat_pose == "ready" and not self.battle_locked:
            idle_frame = (self.world_clock // 30) % 2
            if idle_frame:
                target.adjust(-2, -3, 2, 1)
        self._draw_pixmap_contained(painter, target, pixmap)

    def _paint_ending(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor(3, 5, 12, 178))
        self._panel(painter, QRectF(180, 125, 600, 360), QColor(8, 10, 22, 242), QColor("#e2c36f"), 2)
        painter.setPen(QColor("#6ef0e7"))
        self._draw_fitted_text(painter, QRectF(210, 165, 540, 30), "LEVEL I COMPLETE", 14, 8, True)
        painter.setPen(QColor("#f5e8bb"))
        self._draw_fitted_text(painter, QRectF(210, 214, 540, 55), "THE BELL IS QUIET", 25, 13, True)
        painter.setPen(QColor("#e5e5ed"))
        self._draw_fitted_text(
            painter,
            QRectF(245, 290, 470, 76),
            "The Pending has been closed after several centuries and one strongly worded lantern.",
            11,
            7,
        )
        painter.setPen(QColor("#f0cf73"))
        self._draw_fitted_text(
            painter, QRectF(210, 375, 540, 27), f"FIRST CLEAR REWARD: {COMPLETION_COINS} COINS", 12, 7.5, True,
        )
        painter.setPen(QColor("#71ece2"))
        self._draw_fitted_text(
            painter, QRectF(210, 405, 540, 24), "BOSS LOOT: 150 GOLD + CODEX OF THE UNCLOSED", 9.5, 6, True,
        )
        painter.setPen(QColor("#aeb4c8"))
        self._draw_fitted_text(
            painter, QRectF(210, 444, 540, 20), "PRESS ENTER TO INSPECT THE DROPPED CODEX", 8, 5.5,
            flags=Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _paint_particles(self, painter: QPainter):
        painter.setPen(Qt.NoPen)
        for particle in self.particles:
            color = QColor(particle["color"])
            color.setAlpha(max(0, min(255, int(255 * particle["life"] / particle["max"]))))
            painter.setBrush(color)
            size = particle["size"]
            painter.drawRect(QRectF(particle["x"], particle["y"], size, size))

    def _paint_toast(self, painter: QPainter, text: str):
        rect = QRectF(225, 112, 510, 44)
        self._panel(painter, rect, QColor(6, 9, 19, 230), QColor("#6be7df"))
        painter.setPen(QColor("#edf4f2"))
        self._draw_fitted_text(painter, rect.adjusted(12, 5, -12, -5), text, 9, 6, True)

    def _paint_title_button(
        self, painter: QPainter, rect: QRect, text: str, button_id: str, plate: QPixmap
    ) -> None:
        hovering = self.title_hover_button == button_id
        pressed = self.title_click_button == button_id
        target = QRectF(rect).translated(0, 3 if pressed else -2 if hovering else 0)
        if plate.isNull():
            self._button(painter, target.toRect(), text, "#2b8077")
            return
        if hovering or pressed:
            glow = QColor("#75f5ed" if button_id == "continue" else "#c987ff")
            glow.setAlpha(190 if pressed else 122)
            painter.save()
            painter.setPen(QPen(glow, 2 if pressed else 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(target.adjusted(36, 32, -36, -32), 8, 8)
            painter.restore()
        self._draw_pixmap_contained(painter, target, plate)
        painter.setPen(QColor("#fbf5de"))
        self._draw_fitted_text(
            painter,
            target.adjusted(74, 42, -74, -42),
            text,
            13,
            8,
            True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )

    def _button(self, painter, rect: QRect, text: str, color: str, small: bool = False):
        painter.setPen(QPen(QColor("#d7c778"), 1))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(rect), 5, 5)
        painter.setPen(QColor("#f9f7eb"))
        self._draw_fitted_text(
            painter,
            QRectF(rect).adjusted(10, 6, -10, -6),
            text,
            10 if small else 12,
            6.5,
            True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )

    @staticmethod
    def _panel(painter, rect: QRectF, fill: QColor, border: QColor | None = None, width: int = 1):
        painter.setBrush(fill)
        painter.setPen(QPen(border or QColor(93, 209, 206, 130), width))
        painter.drawRoundedRect(rect, 5, 5)

    @staticmethod
    def _bar(painter, rect: QRectF, value: int, maximum: int, start: str, end: str):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(11, 12, 24, 220))
        painter.drawRoundedRect(rect, 3, 3)
        ratio = max(0.0, min(1.0, value / maximum))
        fill = QRectF(rect.x() + 2, rect.y() + 2, max(0, (rect.width() - 4) * ratio), rect.height() - 4)
        from PyQt5.QtGui import QLinearGradient
        gradient = QLinearGradient(fill.topLeft(), fill.topRight())
        gradient.setColorAt(0, QColor(start))
        gradient.setColorAt(1, QColor(end))
        painter.setBrush(gradient)
        painter.drawRoundedRect(fill, 2, 2)
