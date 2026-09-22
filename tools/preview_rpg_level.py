"""Render deterministic RPG room and encounter previews for visual QA."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QApplication

from frontend.rpg.level_one import (
    ENEMIES,
    ORDER_INVESTIGATION_IDS,
    ORDER_SHARDS,
    ROOMS,
    ROOM_EXITS,
    ROOM_SAFE_SPAWNS,
)
from frontend.rpg.state import SEALS, ArchiveboundState
from frontend.rpg.window import ArchiveboundCanvas, GAME_HEIGHT, GAME_WIDTH


def draw_debug_layout(image: QImage, canvas: ArchiveboundCanvas) -> None:
    """Overlay the current runtime geometry without changing production rendering."""
    painter = QPainter(image)
    from frontend.rpg.level_one import (
        MEMORY_PLINTHS,
        ORDER_SHARDS,
        ROOM_EXITS,
        ROOM_NAVIGATION,
    )
    from frontend.rpg.state import CLERK_POSITION, VAULT_POSITION

    painter.setBrush(QColor(255, 205, 64, 28))
    painter.setPen(QPen(QColor("#ffd340"), 2))
    navigation = ROOM_NAVIGATION[canvas.state.current_room]
    for area in navigation["walk_areas"]:
        painter.drawRect(QRectF(*area))
    painter.setBrush(QColor(255, 133, 64, 55))
    painter.setPen(QPen(QColor("#ff8540"), 2))
    for blocker in canvas._active_blockers():
        shape = blocker["shape"]
        if shape == "circle":
            x, y = blocker["center"]
            painter.drawEllipse(QPointF(x, y), blocker["radius"], blocker["radius"])
        elif shape == "ellipse":
            x, y = blocker["center"]
            radius_x, radius_y = blocker["radii"]
            painter.drawEllipse(QRectF(x - radius_x, y - radius_y, radius_x * 2, radius_y * 2))
        elif shape == "polygon":
            painter.drawPolygon(QPolygonF([QPointF(*point) for point in blocker["points"]]))
        else:
            painter.drawRect(QRectF(*blocker["rect"]))

    painter.setBrush(QColor(255, 66, 88, 90))
    painter.setPen(QPen(QColor("#ff4258"), 2))
    for exit_spec in ROOM_EXITS[canvas.state.current_room]:
        painter.drawRect(QRectF(*exit_spec["trigger"]))

    targets = []
    room = canvas.state.current_room
    if room == "hub":
        targets = [CLERK_POSITION, VAULT_POSITION]
    elif room == "memory":
        targets = [entry["position"] for entry in MEMORY_PLINTHS]
    elif room == "mercy":
        targets = [ENEMIES["red_tape_wraith"]["position"]]
    elif room == "order":
        targets = list(ORDER_SHARDS.values()) + [ENEMIES["misfiled_mimic"]["position"]]
    painter.setBrush(QColor(74, 233, 205, 34))
    painter.setPen(QPen(QColor("#4ae9cd"), 2))
    for x, y in targets:
        painter.drawEllipse(QPointF(x, y), canvas.INTERACT_DISTANCE, canvas.INTERACT_DISTANCE)
    painter.end()


def render_preview(
    kind: str,
    output: Path,
    debug_layout: bool = False,
    player_position: tuple[float, float] | None = None,
    world_clock: int = 30,
    facing: str = "down",
    moving: bool = False,
    hover_position: tuple[float, float] | None = None,
    investigation_variant: int = 0,
) -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ArchiveboundCanvas()
    canvas.timer.stop()
    canvas.state = ArchiveboundState()
    canvas.resize(GAME_WIDTH, GAME_HEIGHT)
    canvas.world_clock = world_clock
    canvas.facing = facing
    canvas.player_is_moving = moving
    canvas.walk_frame = 2
    if hover_position is not None:
        canvas.hover_position = QPointF(*hover_position)

    if kind in ROOMS:
        canvas.scene = "explore"
        canvas.state.current_room = kind
        canvas.state.player_x, canvas.state.player_y = ROOM_SAFE_SPAWNS[kind]
        if player_position is not None:
            canvas.state.player_x, canvas.state.player_y = player_position
        canvas.state.completed_trials = []
        canvas.state.defeated_enemies = []
        canvas.state.order_shards = []
        canvas.state.memory_progress = 0
    elif kind == "hub_key":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["memory", "mercy", "order"],
            completed_seal_puzzles=["memory", "mercy", "order"],
            key_fragments=["memory", "mercy", "order"],
            fused_key_parts=["memory", "mercy", "order"],
            vault_key_assembled=True,
            inventory=["recall_lens", "appeal_tonic", "reset_compass"],
        )
    elif kind.startswith("memory_future_corruption_"):
        direction = kind.removeprefix("memory_future_corruption_")
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=500, player_y=430)
        canvas.memory_active_archive = "future"
        canvas.memory_attempt_started_tick = 0
        canvas.player_is_moving = True
        canvas.facing = direction
        canvas.walk_frame = 2
        canvas.memory_future_echo_event = None
        canvas.memory_future_corruption_event = {
            "started": world_clock - 9,
            "duration": 16,
        }
    elif kind.startswith("memory_motion_"):
        motion_name = kind.removeprefix("memory_motion_")
        direction = "right"
        if motion_name.startswith("future_"):
            archive_id = "future"
            direction = motion_name.removeprefix("future_")
        else:
            archive_id = motion_name
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=500, player_y=430)
        canvas.memory_active_archive = archive_id
        canvas.memory_attempt_started_tick = 0
        canvas.player_is_moving = True
        canvas.facing = direction
        canvas.keys = {{
            "left": Qt.Key_Left,
            "right": Qt.Key_Right,
            "up": Qt.Key_Up,
            "down": Qt.Key_Down,
        }[direction]}
        canvas._can_walk = lambda _x, _y: True
        for step in range(14):
            canvas.world_clock = 30 + step
            canvas._move_player()
        canvas.world_clock = world_clock
    elif kind.startswith("memory_restoring_"):
        archive_id = kind.removeprefix("memory_restoring_")
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="memory",
            player_x=480,
            player_y=470,
            memory_archives_completed=[archive_id],
            memory_progress=1,
        )
        canvas.memory_restoration_pending = archive_id
        canvas.memory_restoration_started = 0
        canvas.world_clock = world_clock
    elif kind == "memory_active":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=865, player_y=320)
        canvas.memory_active_archive = "future"
        canvas.memory_attempt_started_tick = 0
        canvas.memory_hourglass_location = "north_lockbox"
        canvas.memory_hourglass_found = True
    elif kind == "memory_search":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=430)
        canvas.memory_active_archive = "past"
        canvas.memory_attempt_started_tick = 0
        canvas.memory_hourglass_location = "north_lockbox"
        canvas.memory_hourglass_found = False
    elif kind == "memory_marker_hover":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=426)
    elif kind == "memory_marker_activation":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=426)
        canvas.memory_active_archive = "present"
        canvas.memory_attempt_started_tick = 0
        canvas.memory_activation_effect = {
            "archive_id": "present",
            "started": 0,
            "duration": 32,
        }
    elif kind == "hub_passage_hover":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="hub", player_x=480, player_y=410)
        canvas.hovered_passage_marker = "hub_order"
        canvas.hover_position = QPointF(480, 490)
    elif kind == "memory_locked_hover":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="memory", player_x=865, player_y=320)
        canvas.hovered_passage_marker = "memory_return"
        canvas.hover_position = QPointF(900, 310)
    elif kind == "hub_watch_idle":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="hub", player_x=480, player_y=410)
        canvas.idle_action = "watch"
        canvas.idle_action_frame = 12
    elif kind.startswith("hub_seal_activation_"):
        trial_id = kind.removeprefix("hub_seal_activation_")
        relic = {"memory": "recall_lens", "mercy": "appeal_tonic", "order": "reset_compass"}[trial_id]
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="hub",
            player_x=SEALS[trial_id]["position"][0],
            player_y=SEALS[trial_id]["position"][1] + 72,
            completed_trials=[trial_id],
            inventory=[relic],
        )
        canvas.hub_seal_activation_effect = {
            "trial_id": trial_id,
            "started": 0,
            "duration": 48,
        }
    elif kind == "hub_passage_exit":
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="hub", player_x=480, player_y=620)
        canvas._begin_passage_transition(ROOM_EXITS["hub"][2])
        canvas.world_clock = 6
    elif kind in {"puzzle_memory_lever", "puzzle_memory_fail", "puzzle_memory_success", "puzzle_memory_scroll", "puzzle_memory_scroll_opening", "puzzle_memory_exchange"}:
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["memory"],
            inventory=["recall_lens"],
        )
        canvas._start_seal_puzzle("memory")
        if kind.endswith("scroll"):
            # Slot I contains the longest clue and is the strongest layout stress test.
            canvas.chronometer_open_slot = 0
            canvas.chronometer_scroll_animation = ""
        elif kind.endswith("scroll_opening"):
            canvas.chronometer_open_slot = 0
            canvas.chronometer_scroll_animation = "opening"
            canvas.chronometer_scroll_animation_started = 0
            canvas.world_clock = 14
        elif kind.endswith("exchange"):
            canvas.chronometer_exchange = {"first": 0, "second": 4, "started": 0, "duration": 24}
            canvas.world_clock = 12
        else:
            animation = "lever_pull" if kind.endswith("lever") else "fail" if kind.endswith("fail") else "success"
            canvas._set_chronometer_animation(animation)
            canvas.chronometer_animation_started = 0
        if not kind.endswith(("exchange", "scroll_opening")):
            canvas.world_clock = world_clock
    elif kind == "puzzle_order_motion":
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["order"],
            inventory=["reset_compass"],
        )
        canvas._start_seal_puzzle("order")
        canvas.world_clock = world_clock
        canvas._handle_puzzle_click(canvas._order_puzzle_rects()[1].center())
        canvas.world_clock += 14
    elif kind == "puzzle_order_solved":
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["order"],
            inventory=["reset_compass"],
        )
        canvas._start_seal_puzzle("order")
        canvas.order_rings = [0, 0, 0, 0]
    elif kind.startswith("mercy_appeal_"):
        appeal_id = kind.removeprefix("mercy_appeal_")
        canvas.state = ArchiveboundState(current_room="mercy", player_x=480, player_y=430)
        canvas.world_clock = world_clock
        canvas._start_mercy_appeal(appeal_id)
        canvas.mercy_appeal_clip_started = 0
    elif kind.startswith("puzzle_"):
        trial_id = kind.removeprefix("puzzle_")
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=[trial_id],
            inventory=[{"memory": "recall_lens", "mercy": "appeal_tonic", "order": "reset_compass"}[trial_id]],
        )
        canvas._start_seal_puzzle(trial_id)
    elif kind == "mara_choices":
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["memory", "mercy"],
            completed_seal_puzzles=["memory"],
            key_fragments=["memory"],
            inventory=["recall_lens", "appeal_tonic"],
        )
        canvas._open_mara_conversation()
    elif kind in {"dialogue_mara", "dialogue_archivist", "dialogue_monologue"}:
        canvas.state = ArchiveboundState(current_room="hub", player_x=700, player_y=420)
        lines = [
            ("MARA, SENIOR CLERK", "Something very important, I assume. I tried to pry it out of your hands. But you would not let go of it, even unconscious."),
            ("LAST CLERK", "Well, I don't know where I am, so I don't know what's normal around here."),
        ]
        if kind == "dialogue_monologue":
            canvas.show_dialogue([("LAST CLERK", "I rehearse objections recreationally.")], portraits=True)
        else:
            canvas.show_dialogue(lines, portraits=True)
            if kind == "dialogue_archivist":
                canvas.advance_dialogue()
    elif kind == "vault_intro":
        canvas.state.current_room = "vault"
        canvas._start_vault_intro()
    elif kind == "defeat_cinematic":
        canvas.state.current_room = "vault"
        canvas._start_defeat_cinematic()
        canvas.cinematic_index = 1
    elif kind == "victory_cinematic":
        canvas.state.current_room = "vault"
        canvas._start_victory_cinematic()
        canvas.cinematic_index = 2
    elif kind == "order_investigation_sequence_case_file_scrolled":
        investigation_id = "sequence"
        canvas.state = ArchiveboundState(current_room="order", player_x=480, player_y=430)
        canvas.state.order_case_variants = {investigation_id: 0}
        canvas._start_order_investigation(investigation_id)
        canvas.order_case_file_open = True
        canvas.order_case_file_scroll = 52
    elif kind.startswith("order_investigation_"):
        investigation_id = kind.removeprefix("order_investigation_").removesuffix("_case_file")
        canvas.state = ArchiveboundState(current_room="order", player_x=480, player_y=430)
        canvas.state.order_case_variants = {investigation_id: investigation_variant}
        canvas._start_order_investigation(investigation_id)
        canvas.order_case_file_open = kind.endswith("_case_file")
    elif kind == "mimic_intro":
        canvas.state.current_room = "order"
        canvas._start_mimic_intro()
        canvas.cinematic_index = 2
    elif kind in {"order_shards_ready", "order_gem_ready"}:
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="order",
            player_x=480,
            player_y=455,
            order_shards=list(ORDER_SHARDS),
            order_investigations_completed=list(ORDER_INVESTIGATION_IDS),
        )
        if kind == "order_gem_ready":
            canvas.state.order_fused_shards = list(ORDER_SHARDS)
            canvas.state.order_chest_gem_assembled = True
    else:
        canvas.state.inventory = ["recall_lens", "appeal_tonic", "reset_compass"]
        canvas.state.current_room = ENEMIES[kind]["room"]
        canvas.start_battle(kind)
        canvas.world_clock = world_clock

    image = QImage(GAME_WIDTH, GAME_HEIGHT, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    canvas.render(painter)
    painter.end()
    if debug_layout and kind in ROOMS:
        draw_debug_layout(image, canvas)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(output)):
        raise RuntimeError(f"Could not save preview to {output}")
    canvas.deleteLater()
    app.processEvents()


def main() -> None:
    choices = tuple(ROOMS) + tuple(ENEMIES) + (
        "hub_key", "memory_active", "memory_search", "memory_marker_hover", "memory_marker_activation",
        "memory_motion_past", "memory_motion_present", "memory_motion_future",
        "memory_motion_future_left", "memory_motion_future_up", "memory_motion_future_down",
        "memory_future_corruption_left", "memory_future_corruption_right",
        "memory_future_corruption_up", "memory_future_corruption_down",
        "memory_restoring_past", "memory_restoring_present", "memory_restoring_future",
        "hub_passage_hover", "memory_locked_hover", "hub_watch_idle", "hub_passage_exit",
        "hub_seal_activation_memory", "hub_seal_activation_mercy", "hub_seal_activation_order",
        "puzzle_memory", "puzzle_memory_scroll", "puzzle_memory_scroll_opening", "puzzle_memory_exchange", "puzzle_memory_lever", "puzzle_memory_fail", "puzzle_memory_success",
        "puzzle_mercy", "puzzle_order", "puzzle_order_motion", "puzzle_order_solved", "mara_choices",
        "mercy_appeal_pardon", "mercy_appeal_diversion", "mercy_appeal_cure",
        "dialogue_mara", "dialogue_archivist", "dialogue_monologue",
        "vault_intro", "defeat_cinematic", "victory_cinematic", "mimic_intro",
        "order_shards_ready", "order_gem_ready",
        "order_investigation_identity", "order_investigation_sequence", "order_investigation_authority",
        "order_investigation_sequence_case_file", "order_investigation_sequence_case_file_scrolled",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=choices)
    parser.add_argument("output", type=Path)
    parser.add_argument("--debug-layout", action="store_true")
    parser.add_argument("--player-x", type=float)
    parser.add_argument("--player-y", type=float)
    parser.add_argument("--clock", type=int, default=30)
    parser.add_argument("--facing", choices=("up", "down", "left", "right"), default="down")
    parser.add_argument("--moving", action="store_true")
    parser.add_argument("--hover-x", type=float)
    parser.add_argument("--hover-y", type=float)
    parser.add_argument("--variant", type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    if (args.player_x is None) != (args.player_y is None):
        parser.error("--player-x and --player-y must be supplied together")
    if (args.hover_x is None) != (args.hover_y is None):
        parser.error("--hover-x and --hover-y must be supplied together")
    player_position = None
    if args.player_x is not None:
        player_position = (args.player_x, args.player_y)
    hover_position = None
    if args.hover_x is not None:
        hover_position = (args.hover_x, args.hover_y)
    render_preview(
        args.kind,
        args.output,
        args.debug_layout,
        player_position,
        args.clock,
        args.facing,
        args.moving,
        hover_position,
        args.variant,
    )


if __name__ == "__main__":
    main()
