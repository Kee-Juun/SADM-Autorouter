"""Regression tests for Archivebound save and reward behavior."""

import hashlib
import math
import unittest
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt
from PyQt5.QtGui import QFontMetricsF, QImage
from PyQt5.QtWidgets import QApplication

from frontend.rpg.persistence import COMPLETION_COINS, grant_completion_reward, load_game, save_game
from frontend.rpg.level_one import (
    ENEMIES,
    MEMORY_ARCHIVE_RULES,
    MEMORY_PLINTHS,
    MEMORY_SEARCH_OBJECTS,
    MEMORY_SEQUENCE,
    MERCY_CONSEQUENCE_LINKS,
    ORDER_INVESTIGATION_IDS,
    ORDER_INVESTIGATIONS,
    ORDER_STATIONS,
    ORDER_SHARDS,
    ROOM_EXITS,
    ROOM_ENVIRONMENT_SPRITES,
    ROOM_NAVIGATION,
    ROOM_SAFE_SPAWNS,
    TRIAL_REWARDS,
)
from frontend.rpg.state import CLERK_POSITION, SEALS, VAULT_POSITION, ArchiveboundState
from frontend.rpg.window import (
    ABILITY_ORDER,
    HUB_SEAL_MARKER_CENTERS,
    ORDER_TURN_LIMIT,
    REGISTRY_CHARACTER_TOOLTIPS,
    REGISTRY_AUTHORITY_TOOLTIPS,
    REGISTRY_VISUAL_CAPTIONS,
    REGISTRY_VISUAL_LABELS,
    ArchiveboundCanvas,
)


class ArchiveboundPersistenceTests(unittest.TestCase):
    def _temporary_save_path(self):
        test_temp_root = Path.cwd() / "tmp"
        test_temp_root.mkdir(parents=True, exist_ok=True)
        path = test_temp_root / f"archivebound_test_{uuid.uuid4().hex}.json"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(path.with_suffix(".tmp").unlink, missing_ok=True)
        return path

    def test_save_round_trip_preserves_progress(self):
        state = ArchiveboundState(
            player_x=312.5,
            player_y=441.0,
            seals=["memory", "order"],
            clerk_met=True,
            narrative_flags=["opening_seen", "lantern_recognition_seen"],
            response_tendencies={"humorous": 2},
        )
        path = self._temporary_save_path()
        save_game(state, path)
        loaded = load_game(path)

        self.assertEqual(loaded.seals, ["memory", "order"])
        self.assertTrue(loaded.clerk_met)
        self.assertEqual(loaded.player_x, 312.5)
        self.assertEqual(loaded.narrative_flags, ["opening_seen", "lantern_recognition_seen"])
        self.assertEqual(loaded.response_tendencies, {"humorous": 2})

    def test_memory_archive_briefs_stay_in_world_and_distinguish_each_curse(self):
        past = MEMORY_ARCHIVE_RULES["past"]["brief"].lower()
        present = MEMORY_ARCHIVE_RULES["present"]["brief"].lower()
        future = MEMORY_ARCHIVE_RULES["future"]["brief"].lower()

        self.assertIn("history", past)
        self.assertIn("living hour", present)
        self.assertIn("possible self", future)
        self.assertNotEqual(past, present)
        for brief in (past, present, future):
            self.assertNotIn("echo", brief)
            self.assertNotIn("frame", brief)
            self.assertNotIn("controls", brief)

    def test_every_memory_search_object_has_archive_specific_lore(self):
        expected_archives = set(MEMORY_SEQUENCE)

        for prop in MEMORY_SEARCH_OBJECTS:
            self.assertEqual(set(prop["lore"]), expected_archives, prop["id"])
            self.assertEqual(len(set(prop["lore"].values())), 3, prop["id"])
            self.assertTrue(all(message.strip() for message in prop["lore"].values()))

    def test_old_save_migrates_seals_and_reset_compass(self):
        loaded = ArchiveboundState.from_dict({
            "version": 1,
            "seals": ["memory", "order"],
            "inventory": ["archive_compass"],
        })

        self.assertEqual(loaded.completed_trials, ["memory", "order"])
        self.assertIn("recall_lens", loaded.inventory)
        self.assertIn("reset_compass", loaded.inventory)
        self.assertNotIn("archive_compass", loaded.inventory)
        self.assertEqual(loaded.completed_seal_puzzles, ["memory", "order"])
        self.assertEqual(loaded.key_fragments, ["memory", "order"])

    def test_legacy_order_shards_migrate_to_named_investigations(self):
        loaded = ArchiveboundState.from_dict({
            "version": 7,
            "order_shards": ["west", "south"],
        })

        self.assertEqual(loaded.order_investigations_completed, ["identity", "authority"])
        self.assertEqual(loaded.order_shards, ["west", "south"])
        self.assertEqual(loaded.version, 13)

    def test_version_eight_progress_migrates_passed_narrative_beats(self):
        loaded = ArchiveboundState.from_dict({
            "version": 8,
            "clerk_met": True,
            "completed_trials": ["memory", "mercy"],
            "completed_seal_puzzles": ["memory"],
            "vault_opened": False,
        })

        self.assertIn("opening_seen", loaded.narrative_flags)
        self.assertIn("memory_vey_whisper_heard", loaded.narrative_flags)
        self.assertIn("mercy_testimonies_read", loaded.narrative_flags)
        self.assertIn("hub_interlude_1_seen", loaded.narrative_flags)
        self.assertIn("hub_interlude_2_seen", loaded.narrative_flags)
        self.assertNotIn("hub_interlude_3_seen", loaded.narrative_flags)

    def test_legacy_mercy_guardian_clear_migrates_as_full_trial(self):
        loaded = ArchiveboundState.from_dict({
            "version": 10,
            "defeated_enemies": ["red_tape_wraith"],
        })

        self.assertIn("mercy", loaded.completed_trials)
        self.assertEqual(loaded.mercy_appeals_completed, ["pardon", "diversion", "cure"])
        self.assertTrue(loaded.mercy_hearing_completed)

    def test_current_mercy_guardian_clear_keeps_appeals_open(self):
        loaded = ArchiveboundState.from_dict({
            "version": 11,
            "defeated_enemies": ["red_tape_wraith"],
        })

        self.assertNotIn("mercy", loaded.completed_trials)
        self.assertEqual(loaded.mercy_appeals_completed, [])
        self.assertFalse(loaded.mercy_hearing_completed)

    def test_version_eleven_completed_hearing_skips_removed_second_fight(self):
        loaded = ArchiveboundState.from_dict({
            "version": 11,
            "defeated_enemies": ["red_tape_wraith"],
            "mercy_appeals_completed": ["pardon", "diversion", "cure"],
            "mercy_hearing_completed": True,
        })

        self.assertIn("mercy", loaded.completed_trials)
        self.assertIn("appeal_tonic", loaded.inventory)

    def test_pre_tutorial_save_migrates_without_replaying_onboarding(self):
        loaded = ArchiveboundState.from_dict({
            "version": 12,
            "clerk_met": True,
            "narrative_flags": ["opening_seen"],
        })

        self.assertIn("movement_tutorial_complete", loaded.narrative_flags)
        self.assertIn("interaction_tutorial_complete", loaded.narrative_flags)
        self.assertIn("onboarding_complete", loaded.narrative_flags)

    def test_legacy_full_clear_keeps_vault_access(self):
        loaded = ArchiveboundState.from_dict({
            "version": 3,
            "completed_trials": ["memory", "mercy", "order"],
            "seals": ["memory", "mercy", "order"],
        })

        self.assertTrue(loaded.vault_key_assembled)
        self.assertEqual(loaded.fused_key_parts, ["memory", "mercy", "order"])

    def test_completed_legacy_save_migrates_through_open_vault(self):
        loaded = ArchiveboundState.from_dict({
            "version": 4,
            "boss_defeated": True,
            "level_complete": True,
        })

        self.assertTrue(loaded.vault_key_assembled)
        self.assertTrue(loaded.vault_key_inserted)
        self.assertTrue(loaded.vault_opened)

    def test_level_one_has_reversible_passages_and_unique_rewards(self):
        self.assertEqual(len(MEMORY_SEQUENCE), 3)
        self.assertEqual(len(ORDER_SHARDS), 3)
        self.assertEqual(len({reward["item"] for reward in TRIAL_REWARDS.values()}), 3)
        destinations = {exit_spec["room"] for exit_spec in ROOM_EXITS["hub"]}
        self.assertEqual(destinations, {"memory", "mercy", "order"})
        for room_id in destinations:
            self.assertTrue(any(exit_spec["room"] == "hub" for exit_spec in ROOM_EXITS[room_id]))

    def test_contradictory_progress_is_normalized(self):
        loaded = ArchiveboundState.from_dict({
            "memory_progress": 3,
            "defeated_enemies": ["red_tape_wraith", "misfiled_mimic"],
            "completed_trials": [],
            "seals": [],
        })

        self.assertEqual(loaded.completed_trials, ["memory", "mercy", "order"])
        self.assertEqual(loaded.seals, loaded.completed_trials)
        self.assertEqual(loaded.order_shards, list(ORDER_SHARDS))
        self.assertEqual(set(loaded.inventory), {"recall_lens", "appeal_tonic", "reset_compass"})

    def test_version_five_memory_progress_migrates_to_named_archives(self):
        loaded = ArchiveboundState.from_dict({"version": 5, "memory_progress": 2})

        self.assertEqual(loaded.memory_archives_completed, ["past", "present"])
        self.assertEqual(loaded.memory_progress, 2)

    def test_hourglass_locations_round_trip_as_three_unique_search_props(self):
        locations = {
            archive_id: MEMORY_SEARCH_OBJECTS[index]["id"]
            for index, archive_id in enumerate(MEMORY_SEQUENCE)
        }
        state = ArchiveboundState(memory_hourglass_locations=locations)
        path = self._temporary_save_path()
        save_game(state, path)
        loaded = load_game(path)

        self.assertEqual(loaded.memory_hourglass_locations, locations)
        self.assertEqual(len(set(loaded.memory_hourglass_locations.values())), 3)

    def test_invalid_coordinates_use_room_safe_spawn(self):
        loaded = ArchiveboundState.from_dict({
            "current_room": "memory",
            "player_x": "not-a-coordinate",
            "player_y": None,
        })

        self.assertEqual((loaded.player_x, loaded.player_y), ROOM_SAFE_SPAWNS["memory"])

    def test_corrupt_save_falls_back_to_new_game(self):
        path = self._temporary_save_path()
        path.write_text("not-json", encoding="utf-8")
        loaded = load_game(path)

        self.assertEqual(loaded.seals, [])
        self.assertFalse(loaded.level_complete)

    def test_completion_reward_is_granted_only_once(self):
        state = ArchiveboundState(level_complete=True)
        rewards = {"coins": 40}
        with patch("frontend.rpg.persistence.load_user_rewards", return_value=rewards), \
             patch("frontend.rpg.persistence.save_user_rewards") as save_rewards, \
             patch("frontend.rpg.persistence.save_game"):
            self.assertTrue(grant_completion_reward(state))
            self.assertFalse(grant_completion_reward(state))

        self.assertEqual(rewards["coins"], 40 + COMPLETION_COINS)
        save_rewards.assert_called_once()


class ArchivistCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _movement_subject(self):
        subject = SimpleNamespace(
            keys=set(),
            state=ArchiveboundState(player_x=480, player_y=400),
            facing="down",
            walk_frame=0,
            walk_clock=0,
            world_clock=0,
        )
        subject._can_walk = lambda x, y: QRectF(64, 205, 832, 370).contains(x, y)
        return subject

    @staticmethod
    def _navigation_subject(room_id: str, **state_values):
        state = ArchiveboundState(current_room=room_id, **state_values)
        subject = SimpleNamespace(state=state, PLAYER_FOOT_RADIUS=13.0)
        subject._distance = lambda first, second: __import__("math").dist(first, second)
        subject._active_blockers = lambda: ArchiveboundCanvas._active_blockers(subject)
        subject._can_walk = lambda x, y: ArchiveboundCanvas._can_walk(subject, x, y)
        return subject

    @staticmethod
    def _path_exists(subject, target_predicate) -> bool:
        step = 8
        start = tuple(round(value / step) * step for value in ROOM_SAFE_SPAWNS[subject.state.current_room])
        queue = deque((start,))
        visited = {start}
        while queue:
            x, y = queue.popleft()
            if target_predicate(x, y):
                return True
            for point in ((x - step, y), (x + step, y), (x, y - step), (x, y + step)):
                if point not in visited and subject._can_walk(*point):
                    visited.add(point)
                    queue.append(point)
        return False

    def test_exploration_movement_uses_arrows_not_wasd(self):
        subject = self._movement_subject()
        subject.keys = {Qt.Key_W}
        ArchiveboundCanvas._move_player(subject)
        self.assertEqual((subject.state.player_x, subject.state.player_y), (480, 400))

        subject.keys = {Qt.Key_Up}
        ArchiveboundCanvas._move_player(subject)
        self.assertLess(subject.state.player_y, 400)
        self.assertEqual(subject.facing, "up")

    def test_flattened_directional_sheet_selects_one_complete_frame(self):
        cell_width = 280
        sheet_width = cell_width * 12
        sheet_height = 260
        expected_indices = {"down": 0, "left": 4, "right": 8}
        for facing, start_index in expected_indices.items():
            for frame in range(4):
                source = ArchiveboundCanvas._directional_walk_source(
                    sheet_width, sheet_height, facing, frame
                )
                self.assertEqual(source, QRect((start_index + frame) * cell_width, 0, cell_width, sheet_height))

    def test_idle_animation_advances_on_one_second_cadence(self):
        subject = self._movement_subject()
        subject.world_clock = 30
        ArchiveboundCanvas._move_player(subject)

        self.assertEqual(subject.walk_frame, 1)
        self.assertEqual(ArchiveboundCanvas._mara_idle_frame(SimpleNamespace(world_clock=30)), 1)

    def test_hub_lower_passage_unlocks_only_after_memory_and_mercy_arcs(self):
        subject = SimpleNamespace(
            state=ArchiveboundState(current_room="hub", player_x=480, player_y=620),
            keys={Qt.Key_Down},
            toast="",
            facing="down",
        )
        subject._toast = lambda message: setattr(subject, "toast", message)
        with patch("frontend.rpg.window.save_game"):
            ArchiveboundCanvas._check_room_transition(subject)

        self.assertEqual(subject.state.current_room, "hub")
        self.assertIn("Mara is still waiting", subject.toast)

        subject.state.narrative_flags = ["onboarding_complete"]
        subject.state.completed_trials = ["memory", "mercy"]
        subject.state.completed_seal_puzzles = ["memory", "mercy"]
        subject.state.player_x, subject.state.player_y = (480, 620)
        subject.keys = {Qt.Key_Down}
        with patch("frontend.rpg.window.save_game"):
            ArchiveboundCanvas._check_room_transition(subject)

        self.assertEqual(subject.state.current_room, "order")
        self.assertEqual((subject.state.player_x, subject.state.player_y), (480, 185))
        self.assertFalse(subject.keys)
        self.assertIn("Lower Registry", subject.toast)

    def test_memory_return_passage_stays_locked_until_all_archives_are_restored(self):
        locked = SimpleNamespace(
            state=ArchiveboundState(
                current_room="memory",
                player_x=950,
                player_y=320,
                memory_archives_completed=["past", "present"],
            ),
            keys={Qt.Key_Right},
            toast="",
            facing="right",
        )
        locked._toast = lambda message: setattr(locked, "toast", message)
        locked._cancel_memory_attempt = lambda: None
        ArchiveboundCanvas._check_room_transition(locked)

        self.assertEqual(locked.state.current_room, "memory")
        self.assertEqual((locked.state.player_x, locked.state.player_y), (905, 320))
        self.assertIn("Restore all three Archives", locked.toast)

        locked.state.memory_archives_completed.append("future")
        locked.state.player_x = 950
        locked.keys = {Qt.Key_Right}
        with patch("frontend.rpg.window.save_game"):
            ArchiveboundCanvas._check_room_transition(locked)
        self.assertEqual(locked.state.current_room, "hub")

    def test_lower_registry_return_stays_locked_until_its_trial_is_complete(self):
        locked = SimpleNamespace(
            state=ArchiveboundState(current_room="order", player_x=480, player_y=10),
            keys={Qt.Key_Up},
            toast="",
            facing="up",
        )
        locked._toast = lambda message: setattr(locked, "toast", message)

        ArchiveboundCanvas._check_room_transition(locked)

        self.assertEqual(locked.state.current_room, "order")
        self.assertEqual((locked.state.player_x, locked.state.player_y), ROOM_SAFE_SPAWNS["order"])
        self.assertIn("Restore Docket VII-13", locked.toast)

        locked.state.completed_trials.append("order")
        locked.state.player_x, locked.state.player_y = (480, 10)
        with patch("frontend.rpg.window.save_game"):
            ArchiveboundCanvas._check_room_transition(locked)
        self.assertEqual(locked.state.current_room, "hub")

    def test_room_blockers_prevent_walking_through_props(self):
        subject = SimpleNamespace(
            state=ArchiveboundState(current_room="memory"),
            PLAYER_FOOT_RADIUS=13.0,
        )
        subject._distance = lambda first, second: __import__("math").dist(first, second)
        subject._active_blockers = lambda: ArchiveboundCanvas._active_blockers(subject)

        self.assertFalse(ArchiveboundCanvas._can_walk(subject, 165, 315))
        self.assertTrue(ArchiveboundCanvas._can_walk(subject, 340, 400))

    def test_every_tangible_static_prop_has_collision(self):
        for room_id, navigation in ROOM_NAVIGATION.items():
            self.assertTrue(navigation["blockers"], f"{room_id} has no solid scenery")
            subject = self._navigation_subject(room_id)
            for blocker in navigation["blockers"]:
                if blocker["shape"] in {"circle", "ellipse"}:
                    point = blocker["center"]
                elif blocker["shape"] == "polygon":
                    points = blocker["points"]
                    point = (
                        sum(vertex[0] for vertex in points) / len(points),
                        sum(vertex[1] for vertex in points) / len(points),
                    )
                else:
                    x, y, width, height = blocker["rect"]
                    point = (x + width / 2, y + height / 2)
                self.assertFalse(subject._can_walk(*point), f"Walk-through prop in {room_id}: {point}")

    def test_environment_sprite_anchors_are_not_walkable(self):
        for room_id, sprites in ROOM_ENVIRONMENT_SPRITES.items():
            subject = self._navigation_subject(room_id)
            for sprite in sprites:
                self.assertFalse(
                    subject._can_walk(*sprite["position"]),
                    f"Walk-through environment sprite in {room_id}: {sprite['position']}",
                )

    def test_memory_labels_effects_and_colliders_share_artwork_centers(self):
        effects = ROOM_ENVIRONMENT_SPRITES["memory"]
        blockers = ROOM_NAVIGATION["memory"]["blockers"][:3]
        self.assertEqual(
            [plinth["position"] for plinth in MEMORY_PLINTHS],
            [effect["position"] for effect in effects],
        )
        self.assertEqual(
            [plinth["position"][0] for plinth in MEMORY_PLINTHS],
            [blocker["center"][0] for blocker in blockers],
        )
        self.assertEqual({effect["id"] for effect in effects}, {"past", "present", "future"})

    def test_environment_sprite_sheets_have_four_transparent_frames(self):
        asset_root = Path.cwd() / "assets" / "rpg"
        for sprites in ROOM_ENVIRONMENT_SPRITES.values():
            for sprite in sprites:
                image = QImage(str(asset_root / sprite["sheet"]))
                self.assertFalse(image.isNull(), sprite["sheet"])
                self.assertTrue(image.hasAlphaChannel(), sprite["sheet"])
                self.assertEqual(image.width() % 4, 0, sprite["sheet"])
                frame_width = image.width() // 4
                fingerprints = set()
                for index in range(4):
                    frame = image.copy(index * frame_width, 0, frame_width, image.height())
                    bits = frame.constBits()
                    bits.setsize(frame.sizeInBytes())
                    fingerprints.add(hashlib.sha256(bits.asstring(frame.sizeInBytes())).digest())
                    self.assertTrue(
                        all(frame.pixelColor(x, 0).alpha() == 0 for x in range(frame.width())),
                        f"Top-edge clipping in {sprite['sheet']} frame {index}",
                    )
                    self.assertTrue(
                        all(frame.pixelColor(x, frame.height() - 1).alpha() == 0 for x in range(frame.width())),
                        f"Bottom-edge clipping in {sprite['sheet']} frame {index}",
                    )
                self.assertEqual(len(fingerprints), 4, f"Repeated idle frame in {sprite['sheet']}")

    def test_memory_relic_and_search_atlases_preserve_transparency(self):
        asset_root = Path.cwd() / "assets" / "rpg"
        for name, minimum_width, minimum_height in (
            ("memory_hourglass_relics_atlas_v1.png", 900, 300),
            ("memory_search_props_atlas_v1.png", 1200, 600),
        ):
            image = QImage(str(asset_root / name))
            self.assertFalse(image.isNull(), name)
            self.assertTrue(image.hasAlphaChannel(), name)
            self.assertGreaterEqual(image.width(), minimum_width, name)
            self.assertGreaterEqual(image.height(), minimum_height, name)

        chronometer = QImage(str(asset_root / "palimpsest_chronometer_panel_v1.png"))
        self.assertFalse(chronometer.isNull())

    def test_chronometer_animation_atlases_have_four_authored_frames(self):
        asset_root = Path.cwd() / "assets" / "rpg"
        for name in (
            "chronometer_activation_atlas_v1.png",
            "chronometer_lever_pull_atlas_v1.png",
            "chronometer_failure_atlas_v1.png",
            "chronometer_success_atlas_v1.png",
        ):
            image = QImage(str(asset_root / name))
            self.assertFalse(image.isNull(), name)
            self.assertEqual(image.width() % 2, 0, name)
            self.assertEqual(image.height() % 2, 0, name)
            fingerprints = set()
            for row in range(2):
                for column in range(2):
                    frame = image.copy(
                        column * image.width() // 2,
                        row * image.height() // 2,
                        image.width() // 2,
                        image.height() // 2,
                    )
                    bits = frame.constBits()
                    bits.setsize(frame.sizeInBytes())
                    fingerprints.add(hashlib.sha256(bits.asstring(frame.sizeInBytes())).digest())
            self.assertEqual(len(fingerprints), 4, name)

    def test_memory_prop_glows_follow_sprite_alpha_instead_of_rectangles(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        for prop_id, frame in canvas.memory_search_prop_frames.items():
            glow = canvas.memory_search_prop_glows[prop_id]
            source_image = frame.toImage()
            glow_image = glow.toImage()
            self.assertEqual(source_image.size(), glow_image.size())
            self.assertEqual(source_image.pixelColor(0, 0).alpha(), 0, prop_id)
            self.assertEqual(glow_image.pixelColor(0, 0).alpha(), 0, prop_id)
            self.assertTrue(
                any(
                    glow_image.pixelColor(x, y).alpha() > 0
                    for y in range(0, glow_image.height(), max(1, glow_image.height() // 12))
                    for x in range(0, glow_image.width(), max(1, glow_image.width() // 12))
                ),
                prop_id,
            )

    def test_all_memory_search_objects_have_shape_following_highlights(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        for prop in MEMORY_SEARCH_OBJECTS:
            if prop.get("embedded"):
                mask = canvas.memory_embedded_search_masks[prop["id"]].toImage()
                self.assertFalse(mask.isNull(), prop["id"])
                self.assertEqual((mask.width(), mask.height()), tuple(prop["rect"][2:]), prop["id"])
                corner_alpha = (
                    mask.pixelColor(0, 0).alpha(),
                    mask.pixelColor(mask.width() - 1, 0).alpha(),
                    mask.pixelColor(0, mask.height() - 1).alpha(),
                    mask.pixelColor(mask.width() - 1, mask.height() - 1).alpha(),
                )
                self.assertIn(0, corner_alpha, prop["id"])
                self.assertTrue(any(
                    mask.pixelColor(x, y).alpha() > 0
                    for y in range(0, mask.height(), max(1, mask.height() // 12))
                    for x in range(0, mask.width(), max(1, mask.width() // 12))
                ), prop["id"])
                self.assertFalse(canvas.memory_embedded_search_details[prop["id"]].isNull())
            else:
                self.assertIn(prop["id"], canvas.memory_search_prop_glows)

    def test_static_collisions_are_object_shaped(self):
        for room_id, navigation in ROOM_NAVIGATION.items():
            shapes = {blocker["shape"] for blocker in navigation["blockers"]}
            self.assertLessEqual(shapes, {"ellipse", "polygon"}, f"Broad blocker returned in {room_id}")

    def test_hub_passages_use_narrow_reciprocal_floor_corridors(self):
        subject = self._navigation_subject("hub")
        self.assertTrue(subject._can_walk(12, 270))
        self.assertTrue(subject._can_walk(948, 270))
        self.assertFalse(subject._can_walk(12, 190))
        self.assertFalse(subject._can_walk(948, 400))

    def test_seal_collision_stops_the_player_without_entering_the_prop(self):
        subject = self._navigation_subject("hub")
        subject.state.player_x = 340
        subject.state.player_y = 230
        subject.keys = {Qt.Key_Left}
        subject.facing = "left"
        subject.walk_frame = 0
        subject.walk_clock = 0
        subject.world_clock = 0
        for _ in range(40):
            ArchiveboundCanvas._move_player(subject)

        self.assertTrue(subject._can_walk(subject.state.player_x, subject.state.player_y))
        self.assertGreater(subject.state.player_x, 275)
        self.assertEqual(subject.state.player_y, 230)

    def test_stale_position_inside_plinth_is_pushed_to_nearest_floor(self):
        subject = self._navigation_subject("memory")
        subject.state.player_x = 480
        subject.state.player_y = 350
        subject.keys = {Qt.Key_Left}

        ArchiveboundCanvas._resolve_player_penetration(subject)

        self.assertTrue(subject._can_walk(subject.state.player_x, subject.state.player_y))
        self.assertLessEqual(
            __import__("math").dist((480, 350), (subject.state.player_x, subject.state.player_y)),
            128,
        )
        self.assertFalse(subject.keys)

    def test_player_stops_before_each_memory_plinth_from_above(self):
        for plinth in MEMORY_PLINTHS:
            subject = self._navigation_subject("memory")
            subject.state.player_x = plinth["position"][0]
            # Start below the north archive-bank collision margin. The former
            # y=205 coordinate is inside the player's expanded cabinet hull at
            # the west and east lanes, so it cannot represent a valid approach.
            subject.state.player_y = 215
            subject.keys = {Qt.Key_Down}
            subject.facing = "down"
            subject.walk_frame = 0
            subject.walk_clock = 0
            subject.world_clock = 0

            for _ in range(80):
                ArchiveboundCanvas._move_player(subject)

            self.assertTrue(subject._can_walk(subject.state.player_x, subject.state.player_y))
            self.assertLessEqual(subject.state.player_y, 235, f"Entered {plinth['id']} effect footprint from above")

    def test_every_passage_spawn_is_walkable(self):
        for exits in ROOM_EXITS.values():
            for exit_spec in exits:
                subject = SimpleNamespace(
                    state=ArchiveboundState(current_room=exit_spec["room"]),
                    PLAYER_FOOT_RADIUS=13.0,
                )
                subject._distance = lambda first, second: __import__("math").dist(first, second)
                subject._active_blockers = lambda current=subject: ArchiveboundCanvas._active_blockers(current)
                self.assertTrue(
                    ArchiveboundCanvas._can_walk(subject, *exit_spec["spawn"]),
                    f"Blocked spawn into {exit_spec['room']}: {exit_spec['spawn']}",
                )

    def test_every_exit_and_interaction_is_reachable(self):
        interaction_targets = {
            "hub": (CLERK_POSITION, VAULT_POSITION),
            "memory": tuple(entry["position"] for entry in MEMORY_PLINTHS),
            "mercy": (ENEMIES["red_tape_wraith"]["position"],),
            "order": tuple(ORDER_SHARDS.values()),
        }
        for room_id, targets in interaction_targets.items():
            subject = self._navigation_subject(room_id)
            for exit_spec in ROOM_EXITS[room_id]:
                trigger = QRectF(*exit_spec["trigger"])
                self.assertTrue(
                    self._path_exists(subject, lambda x, y, area=trigger: area.contains(x, y)),
                    f"No walkable path to {room_id} exit",
                )
            for target in targets:
                interaction_radius = 127 if room_id == "memory" else 92
                self.assertTrue(
                    self._path_exists(
                        subject,
                        lambda x, y, point=target, radius=interaction_radius: subject._distance((x, y), point) <= radius,
                    ),
                    f"No walkable interaction position for {room_id} target {target}",
                )

        memory_subject = self._navigation_subject("memory")
        for prop in MEMORY_SEARCH_OBJECTS:
            self.assertTrue(
                self._path_exists(
                    memory_subject,
                    lambda x, y, point=prop["position"]: memory_subject._distance((x, y), point) <= 134,
                ),
                f"No walkable search position for memory prop {prop['id']}",
            )

        mimic_subject = self._navigation_subject("order", order_shards=list(ORDER_SHARDS))
        mimic_position = ENEMIES["misfiled_mimic"]["position"]
        self.assertTrue(self._path_exists(
            mimic_subject,
            lambda x, y: mimic_subject._distance((x, y), mimic_position) <= 122,
        ))

    def test_cooldowns_advance_by_turn_not_wall_clock(self):
        subject = SimpleNamespace(ability_cooldowns={"Q": 0, "W": 2, "E": 1, "R": 3})
        self.assertEqual(ArchiveboundCanvas._ability_cooldown(subject, "W"), 2)

        subject.scene = "battle"
        subject.hero_combat_pose = "hit"
        subject.last_ability_key = "W"
        subject.battle_locked = True
        subject._update_battle_idle_pose = lambda: None
        ArchiveboundCanvas._finish_boss_turn(subject)
        self.assertEqual(subject.ability_cooldowns, {"Q": 0, "W": 2, "E": 0, "R": 2})
        self.assertFalse(subject.battle_locked)

    def test_legacy_exit_position_is_relocated_to_safe_floor(self):
        subject = SimpleNamespace(
            state=ArchiveboundState(current_room="hub", player_x=480, player_y=620),
            PLAYER_FOOT_RADIUS=13.0,
        )
        subject._distance = lambda first, second: __import__("math").dist(first, second)
        subject._active_blockers = lambda: ArchiveboundCanvas._active_blockers(subject)
        subject._can_walk = lambda x, y: ArchiveboundCanvas._can_walk(subject, x, y)
        ArchiveboundCanvas._ensure_safe_player_position(subject)

        self.assertEqual((subject.state.player_x, subject.state.player_y), ROOM_SAFE_SPAWNS["hub"])

    def test_enemy_families_apply_distinct_turn_effects(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(inventory=["recall_lens", "appeal_tonic", "reset_compass"])
        canvas.start_battle("red_tape_wraith")
        with patch("frontend.rpg.window.random.choice", return_value="Binding Clause"), \
             patch("frontend.rpg.window.random.randint", return_value=10), \
             patch("frontend.rpg.window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            canvas.battle_action("Q")
        self.assertEqual(canvas.ability_cooldowns["W"], 1)
        self.assertLess(canvas.state.player_hp, 100)

        canvas.state.player_hp = 100
        canvas.start_battle("misfiled_mimic")
        with patch("frontend.rpg.window.random.choice", return_value="Missing Attachment"), \
             patch("frontend.rpg.window.random.randint", return_value=12), \
             patch("frontend.rpg.window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            canvas.battle_action("Q")
        self.assertEqual(canvas.focus, 1)
        self.assertIsNotNone(canvas.mimic_sealed_item)
        self.assertEqual(canvas.mimic_sealed_item_turns, 1)

    def test_order_investigations_restore_one_cohesive_master_docket(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")

        with patch("frontend.rpg.window.save_game"), patch.object(canvas, "show_dialogue"):
            for investigation_id in ORDER_INVESTIGATION_IDS:
                canvas.active_order_investigation = investigation_id
                canvas._complete_order_investigation()

        self.assertEqual(canvas.state.order_investigations_completed, list(ORDER_INVESTIGATION_IDS))
        self.assertEqual(set(canvas.state.order_shards), set(ORDER_SHARDS))
        self.assertEqual(canvas._room_objective(), "FUSE THE THREE DOCKET SHARDS")

    def test_wrong_registry_finding_builds_persistent_corruption(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order", player_hp=100)
        canvas.active_order_investigation = "identity"

        with patch("frontend.rpg.window.save_game"):
            canvas._fail_order_investigation()
            canvas._fail_order_investigation()
            canvas._fail_order_investigation()

        self.assertEqual(canvas.state.order_corruption, 3)
        self.assertEqual(canvas.state.player_hp, 90)

    def test_sequence_failure_preserves_work_and_reports_partial_progress(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")
        canvas.active_order_investigation = "sequence"
        canvas.order_investigation_variant = 0
        canvas.order_sequence = list(reversed(ORDER_INVESTIGATIONS["sequence"][0]["answer"]))
        attempted = list(canvas.order_sequence)

        with patch("frontend.rpg.window.save_game"):
            canvas._fail_order_investigation()

        self.assertEqual(canvas.order_sequence, attempted)
        self.assertIn("entries are correctly placed", canvas.order_investigation_feedback)
        self.assertIn("Registry preserves your work", canvas.order_investigation_feedback)

    def test_registry_hints_escalate_without_exposing_every_answer_at_once(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.active_order_investigation = "sequence"

        canvas._advance_order_hint()
        first = canvas.order_investigation_feedback
        canvas._advance_order_hint()
        second = canvas.order_investigation_feedback
        canvas._advance_order_hint()
        third = canvas.order_investigation_feedback

        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)
        self.assertIn("discovery, copy, Black Sun order", third)

    def test_registry_header_controls_do_not_overlap_title_or_instruction(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        title = QRect(238, 48, 385, 31)
        instruction = QRect(190, 83, 430, 25)
        for control in (canvas._order_hint_rect(), canvas._order_case_file_rect()):
            self.assertFalse(control.intersects(title))
            self.assertFalse(control.intersects(instruction))

    def test_case_file_opens_and_closes_inside_an_investigation(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")
        canvas.state.order_case_variants = {"identity": 0}
        canvas._start_order_investigation("identity")

        canvas._handle_order_investigation_click(canvas._order_case_file_rect().center())
        self.assertTrue(canvas.order_case_file_open)
        canvas._handle_order_investigation_click(canvas._order_case_file_close_rect().center())
        self.assertFalse(canvas.order_case_file_open)

    def test_case_file_categories_and_scroll_are_independently_accessible(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")
        canvas.state.order_case_variants = {"sequence": 0}
        canvas._start_order_investigation("sequence")
        canvas.order_case_file_open = True

        chronology = canvas._order_case_file_tab_rects()["chronology"]
        canvas._handle_order_investigation_click(chronology.center())
        self.assertEqual(canvas.order_case_file_section, "chronology")
        self.assertEqual(canvas.order_case_file_scroll, 0)
        down, _up = canvas._order_case_file_scroll_rects()
        canvas._handle_order_investigation_click(down.center())
        self.assertGreater(canvas.order_case_file_scroll, 0)

    def test_case_file_grows_from_recovered_evidence_instead_of_leaking_answers(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")

        untouched_people = canvas._order_case_file_entries("people")
        untouched_seals = canvas._order_case_file_entries("seals")
        self.assertIn("NO IDENTITIES", untouched_people[0][0])
        self.assertIn("NO SEAL", untouched_seals[0][0])
        self.assertFalse(any("ELIAN VEY" in title for title, _body in untouched_people))
        self.assertFalse(any("BLACK SUN" in title for title, _body in untouched_seals))

        canvas.state.order_case_variants = {"identity": 0}
        canvas._start_order_investigation("identity")
        candidate_names = {title for title, _body in canvas._order_case_file_entries("people")}
        self.assertIn("ELIAN VEY", candidate_names)
        self.assertNotIn("CONFIRMED", " ".join(candidate_names))

        canvas.state.order_investigations_completed.append("identity")
        confirmed_people = canvas._order_case_file_entries("people")
        self.assertTrue(any("ELIAN VEY  /  CONFIRMED" == title for title, _body in confirmed_people))
        self.assertFalse(any("ORREN VALE  /  CONFIRMED" == title for title, _body in confirmed_people))

    def test_fitted_text_preserves_parent_scroll_clip(self):
        from PyQt5.QtGui import QColor, QPainter

        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        image = QImage(120, 80, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setClipRect(QRect(0, 0, 20, 20))
        painter.setPen(QColor("#ffffff"))
        canvas._draw_fitted_text(
            painter, QRectF(40, 30, 70, 30), "MUST STAY CLIPPED", 10, 6, True,
            Qt.AlignCenter | Qt.TextSingleLine,
        )
        painter.end()
        self.assertTrue(all(
            image.pixelColor(x, y).alpha() == 0
            for y in range(image.height())
            for x in range(image.width())
        ))

    def test_registry_room_centerline_and_generated_shard_atlas(self):
        from PIL import Image

        authority = ORDER_STATIONS["authority"]
        authority_marker = QRectF(*authority["activation_rect"]).center()
        chest = next(spec for spec in ROOM_ENVIRONMENT_SPRITES["order"] if spec["id"] == "mimic_chest")
        self.assertEqual(authority["position"][0], 480)
        self.assertEqual(authority_marker.x(), 480)
        self.assertEqual(chest["position"][0], 480)
        self.assertLess(chest["position"][1], authority["position"][1])

        atlas = Image.open(Path("assets/rpg/quest/icons/registry_shard_atlas_v2.png")).convert("RGBA")
        self.assertEqual(atlas.width % 3, 0)
        cell_width = atlas.width // 3
        frames = [atlas.crop((index * cell_width, 0, (index + 1) * cell_width, atlas.height)) for index in range(3)]
        self.assertTrue(all(frame.getchannel("A").getbbox() for frame in frames))
        self.assertEqual(len({hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames}), 3)
        for frame in frames:
            left, top, right, bottom = frame.getchannel("A").getbbox()
            self.assertLess(abs((left + right) / 2 - frame.width / 2), frame.width * 0.035)
            self.assertLess(abs((top + bottom) / 2 - frame.height / 2), frame.height * 0.035)

    def test_mimic_classification_rewards_the_matching_discipline(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState()
        canvas.start_battle("misfiled_mimic")
        canvas.mimic_classification = "identity"

        with patch("frontend.rpg.window.random.randint", return_value=20), \
             patch("frontend.rpg.window.random.choice", side_effect=lambda choices: choices[0]), \
             patch("frontend.rpg.window.QTimer.singleShot"):
            canvas.battle_action("Q")

        self.assertEqual(canvas.boss_hp, ENEMIES["misfiled_mimic"]["max_hp"] - 32)
        self.assertIn("Identity is restored", canvas.battle_message)

    def test_completed_investigations_do_not_auto_trigger_the_mimic_reveal(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        mimic_position = ENEMIES["misfiled_mimic"]["position"]
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="order",
            player_x=mimic_position[0],
            player_y=mimic_position[1],
            order_shards=list(ORDER_SHARDS),
            order_investigations_completed=list(ORDER_INVESTIGATION_IDS),
        )

        canvas._check_enemy_proximity()

        self.assertEqual(canvas.scene, "explore")

    def test_registry_shards_fuse_then_unlock_chest_before_mimic_reveal(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="order",
            order_shards=list(ORDER_SHARDS),
            order_investigations_completed=list(ORDER_INVESTIGATION_IDS),
        )

        with patch("frontend.rpg.window.save_game"):
            canvas._try_fuse_registry_shards("registry_shard_west", "registry_shard_east")
            self.assertFalse(canvas.state.order_chest_gem_assembled)
            self.assertEqual(canvas.state.order_fused_shards, ["west", "east"])
            canvas._try_fuse_registry_shards("registry_shard_pair", "registry_shard_south")
            self.assertTrue(canvas.state.order_chest_gem_assembled)
            self.assertIn("registry_chest_gem", canvas._explore_items())
            canvas._unlock_registry_chest()

        self.assertTrue(canvas.state.order_chest_unlocked)
        self.assertEqual(canvas.scene, "dialogue")
        self.assertEqual(canvas.dialogue_after, "start_mimic")

    def test_registry_station_activation_uses_floor_marker_before_investigation(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        marker = QRectF(*ORDER_STATIONS["identity"]["activation_rect"]).center()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(current_room="order", player_x=marker.x(), player_y=marker.y())

        with patch("frontend.rpg.window.save_game"):
            canvas._interact_order()

        self.assertEqual(canvas.scene, "explore")
        self.assertEqual(canvas.order_station_activation_effect["investigation_id"], "identity")
        canvas.world_clock = canvas.order_station_activation_effect["duration"]
        with patch("frontend.rpg.window.save_game"):
            canvas._tick_order_station_activation()
        self.assertEqual(canvas.scene, "order_investigation")
        self.assertEqual(canvas.active_order_investigation, "identity")

    def test_every_registry_activation_marker_is_walkable(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order")
        for station in ORDER_STATIONS.values():
            center = QRectF(*station["activation_rect"]).center()
            self.assertTrue(canvas._can_walk(center.x(), center.y()), station["title"])

    def test_side_hall_reward_does_not_solve_main_hall_seal(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState()
        with patch("frontend.rpg.window.save_game"):
            canvas._complete_trial("memory")

        self.assertIn("memory", canvas.state.completed_trials)
        self.assertIn("recall_lens", canvas.state.inventory)
        self.assertNotIn("memory", canvas.state.completed_seal_puzzles)
        self.assertNotIn("memory", canvas.state.key_fragments)

    def test_each_seal_puzzle_grants_only_its_fragment(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            completed_trials=["memory"],
            inventory=["recall_lens"],
        )
        with patch("frontend.rpg.window.save_game"):
            canvas._start_seal_puzzle("memory")
            rects = canvas._memory_selector_rects()
            # exile,oath,return,fracture,silence -> oath,fracture,exile,silence,return
            for first, second in ((0, 1), (1, 3), (2, 3), (3, 4)):
                canvas._handle_puzzle_click(rects[first].center())
                canvas._handle_puzzle_click(rects[second].center())
                canvas.world_clock += 24
                canvas._tick_chronometer_exchange()
            canvas._handle_puzzle_click(canvas._chronometer_lever_rect().center())
            canvas.world_clock += 28
            canvas._tick_chronometer_animation()
            canvas.world_clock += 48
            canvas._tick_chronometer_animation()

        self.assertEqual(canvas.state.completed_seal_puzzles, ["memory"])
        self.assertEqual(canvas.state.key_fragments, ["memory"])

    def test_chronometer_exchanges_complete_tube_and_shape_assemblies(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas._start_seal_puzzle("memory")
        original_clues = list(canvas.puzzle_sequence)
        original_shapes = list(canvas.puzzle_socket_order)
        rects = canvas._memory_selector_rects()

        canvas._handle_puzzle_click(rects[0].center())
        canvas._handle_puzzle_click(rects[4].center())
        self.assertIsNotNone(canvas.chronometer_exchange)
        self.assertEqual(canvas.puzzle_sequence, original_clues)
        self.assertEqual(canvas.puzzle_socket_order, original_shapes)

        canvas.world_clock += 24
        canvas._tick_chronometer_exchange()
        self.assertIsNone(canvas.chronometer_exchange)
        self.assertEqual(canvas.puzzle_sequence[0], original_clues[4])
        self.assertEqual(canvas.puzzle_sequence[4], original_clues[0])
        self.assertEqual(canvas.puzzle_socket_order[0], original_shapes[4])
        self.assertEqual(canvas.puzzle_socket_order[4], original_shapes[0])

    def test_live_passage_transition_hides_room_swap_between_walk_phases(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            current_room="hub",
            player_x=480,
            player_y=620,
            completed_trials=["memory", "mercy"],
            completed_seal_puzzles=["memory", "mercy"],
            narrative_flags=["onboarding_complete"],
        )
        canvas.scene = "explore"

        with patch("frontend.rpg.window.save_game"):
            canvas._check_room_transition()
            self.assertEqual(canvas.state.current_room, "hub")
            self.assertEqual(canvas.passage_transition["phase"], "exit")

            canvas.world_clock += 10
            canvas._tick_passage_transition()
            self.assertEqual(canvas.state.current_room, "order")
            self.assertEqual(canvas.passage_transition["phase"], "enter")
            self.assertEqual(canvas.facing, "down")

            canvas.world_clock += 10
            canvas._tick_passage_transition()
            self.assertIsNone(canvas.passage_transition)
            self.assertEqual((canvas.state.player_x, canvas.state.player_y), (480, 185))

    def test_wayfinders_are_compact_and_world_labels_avoid_the_hero(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=742, player_y=405)

        marker = canvas._passage_marker_specs()[0]
        self.assertLessEqual(marker["rect"].width(), 78)
        self.assertLessEqual(marker["rect"].height(), 70)
        original = QRectF(677, 339, 130, 20)
        safe = canvas._safe_world_label_rect(original)
        self.assertTrue(safe is None or not safe.intersects(QRectF(699, 318, 86, 98)))

    def test_chronometer_scrolls_hide_clues_until_a_tube_is_opened(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(completed_trials=["memory"], inventory=["recall_lens"])
        canvas._start_seal_puzzle("memory")

        canvas._handle_puzzle_click(canvas._memory_puzzle_rects()[2].center())
        self.assertEqual(canvas.chronometer_open_slot, 2)
        self.assertEqual(canvas.chronometer_scroll_animation, "opening")

        canvas.world_clock += 28
        canvas._tick_chronometer_scroll_animation()
        self.assertEqual(canvas.chronometer_scroll_animation, "")
        canvas._handle_puzzle_click(canvas._chronometer_parchment_rect().center())
        self.assertEqual(canvas.chronometer_scroll_animation, "closing")
        canvas.world_clock += 28
        canvas._tick_chronometer_scroll_animation()
        self.assertIsNone(canvas.chronometer_open_slot)

    def test_chronometer_footer_and_parchment_text_have_separate_readable_zones(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        instruction = canvas._chronometer_instruction_rect()
        lever_label = canvas._chronometer_lever_label_rect()
        self.assertFalse(instruction.intersects(lever_label))
        self.assertGreater(instruction.top(), lever_label.bottom())

        parchment = QRectF(canvas._chronometer_parchment_rect())
        text_rects = canvas._chronometer_parchment_text_rects()
        self.assertNotIn("slot", text_rects)
        for rect in text_rects.values():
            self.assertTrue(parchment.contains(rect))
            self.assertGreaterEqual(rect.left() - parchment.left(), 90)
            self.assertGreaterEqual(parchment.right() - rect.right(), 90)
        self.assertGreaterEqual(text_rects["clue"].width(), 310)
        self.assertLessEqual(text_rects["clue"].bottom(), text_rects["return"].top())
        self.assertAlmostEqual(text_rects["return"].center().x(), parchment.center().x())
        self.assertAlmostEqual(canvas._chronometer_title_rect().center().x(), 480)

    def test_chronometer_scroll_atlas_has_four_authored_frames(self):
        asset = QImage(str(Path.cwd() / "assets" / "rpg" / "chronometer_scroll_tube_atlas_v2.png"))
        self.assertFalse(asset.isNull())
        self.assertTrue(asset.hasAlphaChannel())
        self.assertGreater(asset.width(), 1000)
        self.assertGreater(asset.height(), 1000)
        quadrants = [
            asset.copy((index % 2) * (asset.width() // 2), (index // 2) * (asset.height() // 2), asset.width() // 2, asset.height() // 2)
            for index in range(4)
        ]
        signatures = {bytes(frame.bits().asstring(frame.sizeInBytes())) for frame in quadrants}
        self.assertEqual(len(signatures), 4)

        for name in ("chronometer_shape_selector_atlas_v2.png", "passage_arrow_atlas_v1.png"):
            atlas = QImage(str(Path.cwd() / "assets" / "rpg" / name))
            self.assertFalse(atlas.isNull(), name)
            self.assertTrue(atlas.hasAlphaChannel(), name)

    def test_chronometer_requires_recall_lens_and_mara_explains_where_to_find_it(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub")
        canvas._interact_seal("memory")

        self.assertEqual(canvas.scene, "dialogue")
        self.assertIn("Recall Lens", " ".join(text for _speaker, text in canvas.dialogue))
        self.assertIn("Hall of Memory", " ".join(text for _speaker, text in canvas.dialogue))
        self.assertTrue(any(speaker == "MARA" for speaker, _text in canvas.dialogue))

    def test_dialogue_portrait_pose_changes_only_when_player_advances(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub", player_x=700, player_y=420)
        canvas.show_dialogue([
            ("MARA", "Tea before you go?"),
            ("LAST CLERK", "Yes. Tea sounds good."),
        ], portraits=True)

        initial = dict(canvas.dialogue_pose_frames)
        canvas.world_clock += 300
        canvas.tick()
        self.assertEqual(canvas.dialogue_pose_frames, initial)
        self.assertEqual(canvas._active_dialogue_role(), "mara")

        canvas.advance_dialogue()
        self.assertEqual(canvas._active_dialogue_role(), "archivist")
        self.assertEqual(canvas.dialogue_pose_frames["mara"], 4)
        self.assertEqual(canvas.dialogue_pose_frames["archivist"], 4)

    def test_dialogue_layout_tracks_active_speaker_world_position(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub", player_x=700, player_y=420)
        canvas.show_dialogue([
            ("MARA, SENIOR CLERK", "Left desk, naturally."),
            ("LAST CLERK", "Right side, equally naturally."),
        ], portraits=True)

        self.assertEqual(canvas._dialogue_layout()[1], "left")
        canvas.advance_dialogue()
        self.assertEqual(canvas._dialogue_layout()[1], "right")

    def test_dialogue_monologue_shows_only_its_speaker(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub", player_x=700, player_y=420)
        canvas.show_dialogue([("LAST CLERK", "I rehearse objections recreationally.")], portraits=True)

        role, side, portrait, dialogue = canvas._dialogue_layout()
        self.assertEqual(role, "archivist")
        self.assertEqual(side, "right")
        self.assertFalse(portrait.isEmpty())
        self.assertLess(portrait.left(), dialogue.right())

    def test_mara_varies_repeated_answers_and_keeps_the_conversation_open(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub", player_hp=83)

        canvas._handle_mara_choice("status")
        first = canvas.dialogue[0][1]
        self.assertTrue(canvas.dialogue_choices)
        self.assertEqual(canvas.scene, "dialogue")

        canvas._handle_mara_choice("status")
        second = canvas.dialogue[0][1]
        self.assertNotEqual(first, second)
        self.assertTrue(canvas.dialogue_choices)

    def test_mara_retires_a_question_after_three_answers_until_next_conversation(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub", player_hp=83)
        canvas._open_mara_conversation()

        answers = []
        for _ in range(3):
            canvas._handle_mara_choice("status")
            answers.append(canvas.dialogue[0][1])

        self.assertEqual(len(set(answers)), 3)
        self.assertNotIn("status", {choice_id for choice_id, _label in canvas.dialogue_choices})

        canvas._handle_mara_choice("leave")
        canvas.advance_dialogue()
        canvas._open_mara_conversation()
        self.assertIn("status", {choice_id for choice_id, _label in canvas.dialogue_choices})

    def test_dialogue_expression_atlases_and_registry_art_are_loaded(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        self.assertFalse(canvas.mara_closeup_sheet.isNull())
        self.assertFalse(canvas.hero_closeup_sheet.isNull())
        self.assertFalse(canvas.mara_closeup_situations_sheet.isNull())
        self.assertFalse(canvas.hero_closeup_situations_sheet.isNull())
        self.assertTrue(canvas.mara_closeup_sheet.hasAlphaChannel())
        self.assertTrue(canvas.hero_closeup_sheet.hasAlphaChannel())
        self.assertTrue(canvas.mara_closeup_situations_sheet.hasAlphaChannel())
        self.assertTrue(canvas.hero_closeup_situations_sheet.hasAlphaChannel())
        self.assertEqual(len(canvas.coupled_registry_rotors), 4)
        self.assertFalse(canvas.coupled_registry_panel.isNull())

    def test_dormant_registry_chest_stays_still_until_the_reveal(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="order", order_chest_unlocked=False)
        chest = next(spec for spec in ROOM_ENVIRONMENT_SPRITES["order"] if spec["id"] == "mimic_chest")

        for tick in (0, 5, 18, 47, 95):
            canvas.world_clock = tick
            self.assertEqual(canvas._environment_sprite_frame(chest), 0)

        canvas.state.order_chest_unlocked = True
        canvas.world_clock = 5
        self.assertEqual(canvas._environment_sprite_frame(chest), 1)

    def test_coupled_registry_click_animates_the_clicked_rotor_and_neighbors(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.active_puzzle = "order"
        canvas.scene = "seal_puzzle"
        canvas.order_rings = [1, 2, 2, 2]

        canvas._handle_puzzle_click(canvas._order_puzzle_rects()[1].center())

        self.assertEqual(canvas.order_rings, [2, 3, 3, 2])
        self.assertEqual(set(canvas.order_rotor_animation["affected"]), {0, 1, 2})
        self.assertEqual(canvas.order_rotor_animation["clicked"], 1)
        self.assertEqual(canvas.order_last_rotor, 1)
        self.assertEqual(canvas.order_turns_used, 1)

    def test_coupled_registry_locks_all_input_until_the_mechanism_finishes(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas._start_seal_puzzle("order")
        first = canvas._order_puzzle_rects()[1].center()
        second = canvas._order_puzzle_rects()[2].center()

        canvas._handle_puzzle_click(first)
        rings_during_cycle = list(canvas.order_rings)
        canvas._handle_puzzle_click(second)
        canvas._handle_puzzle_click(QPoint(30, 30))

        self.assertEqual(canvas.order_rings, rings_during_cycle)
        self.assertEqual(canvas.order_turns_used, 1)
        self.assertEqual(canvas.scene, "seal_puzzle")

        animation = canvas.order_rotor_animation
        canvas.world_clock = animation["started"] + animation["duration"]
        canvas._tick_order_rotor_animation()
        self.assertIsNone(canvas.order_rotor_animation)

        canvas._handle_puzzle_click(second)
        self.assertEqual(canvas.order_turns_used, 2)

    def test_coupled_registry_rejects_an_unsolved_final_turn_then_resets_on_reactivation(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas._start_seal_puzzle("order")
        canvas.order_turns_used = ORDER_TURN_LIMIT - 1

        canvas._handle_puzzle_click(canvas._order_puzzle_rects()[1].center())
        animation = canvas.order_rotor_animation
        canvas.world_clock = animation["started"] + animation["duration"]
        canvas._tick_order_rotor_animation()

        self.assertIsNone(canvas.active_puzzle)
        self.assertEqual(canvas.scene, "dialogue")
        self.assertIn("rejects the filing", canvas.dialogue[0][1])

        canvas.advance_dialogue()
        canvas._start_seal_puzzle("order")
        self.assertEqual(canvas.order_turns_used, 0)
        self.assertEqual(canvas.order_rings, [1, 2, 2, 2])

    def test_coupled_registry_allows_a_solution_on_the_final_turn(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas._start_seal_puzzle("order")
        canvas.order_rings = [3, 3, 0, 3]
        canvas.order_turns_used = ORDER_TURN_LIMIT - 1

        canvas._handle_puzzle_click(canvas._order_puzzle_rects()[0].center())
        animation = canvas.order_rotor_animation
        canvas.world_clock = animation["started"] + animation["duration"]
        canvas._tick_order_rotor_animation()

        self.assertEqual(canvas.order_rings, [0, 0, 0, 0])
        self.assertEqual(canvas.active_puzzle, "order")
        self.assertEqual(canvas.scene, "seal_puzzle")
        self.assertIsNone(canvas.order_rotor_animation)

    def test_mercy_and_order_mechanisms_expose_story_records_during_play(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        canvas._start_seal_puzzle("mercy")
        canvas._handle_puzzle_click(canvas._mercy_loom_source_rects()["river"].center())
        canvas._handle_puzzle_click(canvas._mercy_loom_destination_rects()["river"].center())
        self.assertEqual(canvas.mercy_loom_links["river"], "river")
        self.assertIsNotNone(canvas.mercy_loom_motion)

        canvas._start_seal_puzzle("order")
        canvas._handle_puzzle_click(canvas._order_puzzle_rects()[2].center())
        self.assertEqual(canvas.order_last_rotor, 2)

    def test_mercy_loom_uses_exclusive_sockets_and_audits_wrong_threads(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas._start_seal_puzzle("mercy")

        sources = canvas._mercy_loom_source_rects()
        destinations = canvas._mercy_loom_destination_rects()
        canvas._handle_puzzle_click(sources["sentence"].center())
        canvas._handle_puzzle_click(destinations["river"].center())
        canvas.mercy_loom_motion = None
        canvas._handle_puzzle_click(sources["memory"].center())
        canvas._handle_puzzle_click(destinations["river"].center())

        self.assertIsNone(canvas.mercy_loom_links["sentence"])
        self.assertEqual(canvas.mercy_loom_links["memory"], "river")

        canvas.mercy_loom_motion = None
        canvas._handle_puzzle_click(canvas._mercy_loom_wheel_rect().center())

        self.assertEqual(canvas.mercy_loom_audits_used, 1)
        self.assertTrue(all(link is None for link in canvas.mercy_loom_links.values()))
        self.assertIn("Audit held 0 of 4", canvas.mercy_loom_feedback)

    def test_coupled_registry_uses_independent_mechanical_components(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        self.assertFalse(canvas.coupled_registry_mechanics_atlas.isNull())
        self.assertEqual(len(canvas.coupled_registry_mechanics), 8)
        self.assertTrue(all(not frame.isNull() for frame in canvas.coupled_registry_mechanics))
        self.assertFalse(canvas.coupled_registry_component_atlas.isNull())
        self.assertEqual(len(canvas.coupled_registry_drive_components), 4)
        self.assertTrue(all(not frame.isNull() for frame in canvas.coupled_registry_drive_components))

    def test_coupled_registry_drive_cycle_advances_forward_without_reversing(self):
        turns = [
            ArchiveboundCanvas._registry_drive_turn(step / 36)
            for step in range(37)
        ]
        geometries = [ArchiveboundCanvas._registry_drive_geometry(turn) for turn in turns]

        self.assertEqual(turns[0], 0.0)
        self.assertEqual(turns[-1], 360.0)
        self.assertEqual(sorted(turns), turns)
        self.assertEqual(turns[-1] % 360.0, turns[0])
        for first, last in zip(geometries[0], geometries[-1]):
            self.assertAlmostEqual(first.x(), last.x(), places=6)
            self.assertAlmostEqual(first.y(), last.y(), places=6)
        crank_positions = [geometry[1] for geometry in geometries]
        step_distances = [
            math.hypot(right.x() - left.x(), right.y() - left.y())
            for left, right in zip(crank_positions, crank_positions[1:])
        ]
        self.assertLess(max(step_distances), 7.0)

    def test_registry_clues_represent_every_displayed_candidate(self):
        for variant in ORDER_INVESTIGATIONS["identity"]:
            evidence = " ".join((variant["brief"], *variant["clues"])).lower()
            for _option_id, name, _role in variant["options"]:
                self.assertIn(name.split()[-1].lower(), evidence)
        for variant in ORDER_INVESTIGATIONS["authority"]:
            evidence = " ".join((variant["brief"], *variant["clues"])).lower()
            for token in ("hourglass", "crown", "bell", "black sun"):
                self.assertIn(token, evidence)

    def test_every_registry_clue_variant_fits_its_evidence_panel(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        for investigation_id in ORDER_INVESTIGATIONS:
            canvas.active_order_investigation = investigation_id
            layout = canvas._order_investigation_evidence_rects()
            first_option = canvas._order_investigation_option_rects()[0]
            self.assertLessEqual(layout["panel"].right(), first_option.left() - 8)
            captions = REGISTRY_VISUAL_CAPTIONS[investigation_id]
            labels = REGISTRY_VISUAL_LABELS[investigation_id]
            expected_asset_rows = 5 if investigation_id == "identity" else 4
            visible_rows = canvas._registry_visible_visual_rows(investigation_id)
            tabs = canvas._registry_clue_tab_rects(layout["tabs"], len(visible_rows))
            self.assertEqual(len(captions), expected_asset_rows)
            self.assertEqual(len(labels), expected_asset_rows)
            self.assertEqual(len(tabs), 4)
            for caption in captions:
                caption_bounds = QFontMetricsF(canvas._font(5.2, True)).boundingRect(
                    layout["caption"], int(Qt.AlignCenter | Qt.TextSingleLine), caption
                )
                self.assertLessEqual(caption_bounds.width(), layout["caption"].width() + 0.5)

    def test_identity_visual_reel_contains_only_the_displayed_candidates(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.active_order_investigation = "identity"

        for variant_index, variant in enumerate(ORDER_INVESTIGATIONS["identity"]):
            canvas.order_investigation_variant = variant_index
            visible_rows = canvas._registry_visible_visual_rows("identity")
            expected_rows = (0,) + tuple(
                canvas._registry_visual_row("identity", option[0])
                for option in variant["options"]
            )
            self.assertEqual(visible_rows, expected_rows)
            self.assertEqual(len(set(visible_rows)), 4)

    def test_identity_choices_have_full_portrait_cards_and_neutral_role_tooltips(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.active_order_investigation = "identity"

        rects = canvas._order_investigation_option_rects()
        self.assertEqual(len(rects), 3)
        self.assertTrue(all(rect.width() >= 210 and rect.height() >= 100 for rect in rects))
        for option_id in ("elian_vey", "lysa_marr", "orren_vale", "tomas_rook"):
            self.assertIn(option_id, REGISTRY_CHARACTER_TOOLTIPS)
            self.assertLessEqual(len(REGISTRY_CHARACTER_TOOLTIPS[option_id]), 90)

    def test_authority_choices_use_deductive_tooltips_without_revealing_the_answer(self):
        self.assertEqual(
            set(REGISTRY_AUTHORITY_TOOLTIPS),
            {"hourglass", "registry_crown", "ashen_bell", "black_sun"},
        )
        for tooltip in REGISTRY_AUTHORITY_TOOLTIPS.values():
            self.assertLessEqual(len(tooltip), 110)
            self.assertNotIn("answer", tooltip.lower())
        for variant in ORDER_INVESTIGATIONS["authority"]:
            for _option_id, _name, description in variant["options"]:
                self.assertNotIn("final disposition", description.lower())
                self.assertNotIn("sealed transfer", description.lower())

    def test_registry_evidence_tabs_reveal_one_clue_at_a_time(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.active_order_investigation = "authority"
        canvas.order_investigation_variant = 0
        canvas.order_evidence_focus_index = 0
        canvas.scene = "order_investigation"
        case = canvas._order_current_case()
        layout = canvas._order_investigation_evidence_rects()
        tabs = canvas._registry_clue_tab_rects(layout["tabs"], len(case["clues"]))

        canvas._handle_order_investigation_click(tabs[2].center().toPoint())

        self.assertEqual(canvas.order_evidence_focus_index, 2)

    def test_hub_seals_have_unique_authored_marker_states(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        self.assertFalse(canvas.hub_seal_marker_atlas.isNull())
        self.assertEqual(set(canvas.hub_seal_marker_frames), {"memory", "mercy", "order"})
        self.assertTrue(all(len(frames) == 4 for frames in canvas.hub_seal_marker_frames.values()))
        signatures = {
            bytes(frames[0].toImage().bits().asstring(frames[0].toImage().sizeInBytes()))
            for frames in canvas.hub_seal_marker_frames.values()
        }
        self.assertEqual(len(signatures), 3)

    def test_hub_seal_markers_are_walkable_floor_controls_and_interaction_targets(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="hub")
        relics = {"memory": "recall_lens", "mercy": "appeal_tonic", "order": "reset_compass"}

        for trial_id, center in HUB_SEAL_MARKER_CENTERS.items():
            self.assertTrue(canvas._can_walk(*center), trial_id)
            self.assertGreater(math.dist(center, SEALS[trial_id]["position"]), 100)
            canvas.state = ArchiveboundState(
                current_room="hub",
                player_x=center[0],
                player_y=center[1],
                completed_trials=[trial_id],
                inventory=[relics[trial_id]],
                narrative_flags=["onboarding_complete"],
            )
            canvas.scene = "explore"
            canvas.hub_seal_activation_effect = None
            canvas._interact_hub()
            self.assertEqual(canvas.hub_seal_activation_effect["trial_id"], trial_id)

    def test_hub_seal_activation_finishes_before_opening_puzzle(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["order"],
            inventory=["reset_compass"],
        )

        canvas._interact_seal("order")
        self.assertEqual(canvas.scene, "title")
        self.assertEqual(canvas.hub_seal_activation_effect["trial_id"], "order")
        canvas.world_clock = canvas.hub_seal_activation_effect["duration"]
        canvas._tick_hub_seal_activation()

        self.assertEqual(canvas.scene, "seal_puzzle")
        self.assertEqual(canvas.active_puzzle, "order")
        self.assertIsNone(canvas.hub_seal_activation_effect)

    def test_mara_menu_reacts_to_progress_and_recovery(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            current_room="hub",
            completed_trials=["memory"],
            key_fragments=["memory", "mercy"],
            player_hp=60,
            gold=30,
        )

        choice_ids = {choice_id for choice_id, _label in canvas._mara_menu_choices()}
        self.assertTrue({"seals", "fusion", "recover"}.issubset(choice_ids))

        with patch("frontend.rpg.window.save_game"):
            canvas._handle_mara_choice("recover")

        updated_ids = {choice_id for choice_id, _label in canvas.dialogue_choices}
        self.assertEqual(canvas.state.player_hp, 100)
        self.assertNotIn("recover", updated_ids)
        self.assertIn("guidance", updated_ids)

    def test_opening_choice_records_tendency_and_story_flags(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        with patch("frontend.rpg.window.save_game"):
            canvas.start_game(fresh=True)
            while canvas.scene == "dialogue" and not canvas.dialogue_choices:
                canvas.advance_dialogue()
            self.assertEqual(canvas.dialogue_choice_context, "opening")
            canvas._choose_dialogue(1)

        self.assertEqual(canvas.state.response_tendencies["vulnerable"], 1)
        self.assertIn("opening_seen", canvas.state.narrative_flags)
        self.assertIn("lantern_recognition_seen", canvas.state.narrative_flags)

    def test_opening_teaches_movement_then_interaction_before_memory_unlocks(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState()
        with patch("frontend.rpg.window.save_game"):
            canvas._handle_opening_choice("practical")
            while canvas.scene == "dialogue":
                canvas.advance_dialogue()

            self.assertIn("movement_tutorial_started", canvas.state.narrative_flags)
            self.assertFalse(canvas._hall_is_unlocked("memory"))

            canvas.keys = {Qt.Key_Left}
            canvas._can_walk = lambda _x, _y: True
            canvas._move_player()
            self.assertIn("movement_tutorial_complete", canvas.state.narrative_flags)

            canvas.state.player_x, canvas.state.player_y = CLERK_POSITION
            canvas._interact_hub()

        self.assertIn("interaction_tutorial_complete", canvas.state.narrative_flags)
        self.assertIn("onboarding_complete", canvas.state.narrative_flags)
        self.assertTrue(canvas._hall_is_unlocked("memory"))

    def test_halls_unlock_in_lesson_seal_sequence(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(narrative_flags=["onboarding_complete"])

        self.assertTrue(canvas._hall_is_unlocked("memory"))
        self.assertFalse(canvas._hall_is_unlocked("mercy"))
        self.assertFalse(canvas._hall_is_unlocked("order"))

        canvas.state.completed_trials.append("memory")
        self.assertFalse(canvas._hall_is_unlocked("mercy"))
        canvas.state.completed_seal_puzzles.append("memory")
        self.assertTrue(canvas._hall_is_unlocked("mercy"))

        canvas.state.completed_trials.append("mercy")
        self.assertFalse(canvas._hall_is_unlocked("order"))
        canvas.state.completed_seal_puzzles.append("mercy")
        self.assertTrue(canvas._hall_is_unlocked("order"))

    def test_first_completed_hall_starts_one_hub_interlude(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(completed_trials=["memory"])
        with patch("frontend.rpg.window.save_game"):
            canvas._maybe_start_hub_interlude("memory")
            original_dialogue = list(canvas.dialogue)
            canvas._maybe_start_hub_interlude("memory")

        self.assertEqual(canvas.dialogue_choice_context, "interlude_1")
        self.assertIn("hub_interlude_1_seen", canvas.state.narrative_flags)
        self.assertEqual(canvas.dialogue, original_dialogue)

    def test_level_victory_runs_epilogue_before_ending(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState()
        with patch("frontend.rpg.window.save_game"), \
             patch("frontend.rpg.window.grant_completion_reward", return_value=False):
            canvas._finish_level_victory()
            self.assertEqual(canvas.scene, "dialogue")
            self.assertIn("pending_human_names_seen", canvas.state.narrative_flags)
            self.assertIn("level_one_epilogue_seen", canvas.state.narrative_flags)
            self.assertIn("orin_post_credit_seen", canvas.state.narrative_flags)
            while canvas.scene == "dialogue":
                canvas.advance_dialogue()

        self.assertEqual(canvas.scene, "ending")

    def test_chronometer_failure_animates_before_allowing_retry(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(completed_trials=["memory"], inventory=["recall_lens"])
        canvas._start_seal_puzzle("memory")
        canvas._handle_puzzle_click(canvas._chronometer_lever_rect().center())

        self.assertEqual(canvas.chronometer_animation, "lever_pull")
        canvas.world_clock += 28
        canvas._tick_chronometer_animation()
        self.assertEqual(canvas.chronometer_animation, "fail")
        self.assertNotIn("memory", canvas.state.completed_seal_puzzles)
        canvas.world_clock += 34
        canvas._tick_chronometer_animation()
        self.assertEqual(canvas.chronometer_animation, "")

    def test_memory_archive_attempts_can_start_in_any_order(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=742, player_y=430)
        hidden = [item["id"] for item in MEMORY_SEARCH_OBJECTS[:3]]
        relocated = MEMORY_SEARCH_OBJECTS[4]["id"]
        with patch("frontend.rpg.window.random.sample", return_value=hidden), \
             patch("frontend.rpg.window.random.choice", return_value=relocated), \
             patch("frontend.rpg.window.save_game"):
            canvas._start_memory_attempt("future")

        self.assertEqual(canvas.memory_active_archive, "future")
        self.assertEqual(canvas.memory_hourglass_location, relocated)
        self.assertEqual(len(set(canvas.state.memory_hourglass_locations.values())), 3)

    def test_new_game_and_task_retries_relocate_hourglasses(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        first = [item["id"] for item in MEMORY_SEARCH_OBJECTS[:3]]
        second = [item["id"] for item in MEMORY_SEARCH_OBJECTS[3:6]]
        canvas.state = ArchiveboundState(current_room="memory")
        with patch("frontend.rpg.window.random.sample", side_effect=[first, second]), \
             patch("frontend.rpg.window.random.choice", side_effect=[second[0], second[1]]), \
             patch("frontend.rpg.window.save_game"):
            canvas._ensure_memory_hourglass_locations()
            original = dict(canvas.state.memory_hourglass_locations)
            canvas._start_memory_attempt("past")
            first_retry = canvas.memory_hourglass_location
            canvas._clear_memory_attempt()
            canvas._start_memory_attempt("past")
            second_retry = canvas.memory_hourglass_location
            self.assertNotEqual(first_retry, original["past"])
            self.assertNotEqual(second_retry, first_retry)
            canvas.start_game(fresh=True)

        self.assertEqual(list(canvas.state.memory_hourglass_locations.values()), second)

    def test_past_archive_reverses_arrow_movement(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=470)
        canvas.memory_active_archive = "past"
        canvas.keys = {Qt.Key_Right}
        canvas._can_walk = lambda _x, _y: True
        original_x = canvas.state.player_x
        canvas._move_player()

        self.assertLess(canvas.state.player_x, original_x)
        self.assertEqual(canvas.facing, "left")

    def test_each_memory_motion_challenge_emits_distinct_vfx(self):
        expected = {
            "past": {"rewind_mote"},
            "present": set(),
            "future": {"suspended_mote"},
        }
        for archive_id, expected_kinds in expected.items():
            canvas = ArchiveboundCanvas()
            self.addCleanup(canvas.deleteLater)
            canvas.timer.stop()
            canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=470)
            canvas.memory_active_archive = archive_id
            canvas.world_clock = 12
            canvas.keys = {Qt.Key_Right}
            canvas._can_walk = lambda _x, _y: True
            canvas._move_player()

            kinds = {effect["kind"] for effect in canvas.memory_motion_effects}
            self.assertTrue(expected_kinds.issubset(kinds), archive_id)
            self.assertEqual(len(canvas.memory_avatar_history), 1)
            self.assertEqual(canvas.memory_avatar_history[0]["archive"], archive_id)
            if archive_id == "future":
                self.assertEqual(len(canvas.memory_future_magnetic_wake_frames), 8)
                self.assertTrue(all(
                    not frame.isNull()
                    for frame in canvas.memory_future_magnetic_wake_frames
                ))
            else:
                self.assertEqual(len(canvas.memory_trail_frames[archive_id]), 8)
                self.assertTrue(all(
                    not frame.isNull()
                    for frame in canvas.memory_trail_frames[archive_id]
                ))
            self.assertEqual(len(canvas.hero_side_walk_frames), 8)
            self.assertTrue(all(not frame.isNull() for frame in canvas.hero_side_walk_frames))
            self.assertEqual(
                len({(frame.width(), frame.height()) for frame in canvas.hero_side_walk_frames}),
                1,
            )
            self.assertEqual(
                {(frame.width(), frame.height()) for frame in canvas.hero_side_walk_frames},
                {(260, 400)},
            )
            fingerprints = set()
            floor_rows = []
            for frame in canvas.hero_side_walk_frames:
                image = frame.toImage()
                bits = image.constBits()
                bits.setsize(image.sizeInBytes())
                fingerprints.add(hashlib.sha256(bits.asstring(image.sizeInBytes())).digest())
                occupied = [
                    y for y in range(image.height())
                    if any(image.pixelColor(x, y).alpha() > 32 for x in range(image.width()))
                ]
                floor_rows.append(max(occupied))
            self.assertEqual(len(fingerprints), 8)
            self.assertLessEqual(max(floor_rows) - min(floor_rows), 1)

    def test_future_echoes_are_sparse_spaced_possibility_events(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=470)
        canvas.memory_active_archive = "future"
        canvas.world_clock = 30
        canvas.keys = {Qt.Key_Right}
        canvas._can_walk = lambda _x, _y: True
        canvas._move_player()

        event = canvas.memory_future_echo_event
        self.assertIsNotNone(event)
        self.assertIn(len(event["echoes"]), (1, 2, 3))
        self.assertEqual(
            len({possibility["direction"] for possibility in event["echoes"]}),
            len(event["echoes"]),
        )
        self.assertNotIn("east", {possibility["direction"] for possibility in event["echoes"]})
        for possibility in event["echoes"]:
            delta_x = possibility["x"] - canvas.state.player_x
            delta_y = possibility["y"] - canvas.state.player_y
            distance = math.hypot(
                delta_x,
                delta_y,
            )
            self.assertGreaterEqual(distance, 44.0)
            self.assertLessEqual(distance, 72.0)
            self.assertTrue(abs(delta_x) < 0.001 or abs(delta_y) < 0.001)
        self.assertGreaterEqual(
            canvas.memory_future_next_echo_tick - event["started"] - event["duration"],
            48,
        )
        self.assertNotIn("captured_index", event)
        self.assertNotIn("portal_x", event)
        self.assertEqual(len(canvas.memory_future_magnetic_wake_frames), 8)
        self.assertTrue(all(not frame.isNull() for frame in canvas.memory_future_magnetic_wake_frames))
        self.assertEqual(
            {facing: len(frames) for facing, frames in canvas.memory_future_corruption_frames.items()},
            {"down": 4, "left": 4, "right": 4, "up": 4},
        )
        self.assertTrue(all(
            not frame.isNull()
            for frames in canvas.memory_future_corruption_frames.values()
            for frame in frames
        ))
        normal_target = QRectF(435, 386, 90, 92)
        direction_scales = {"down": 1.05, "left": 1.10, "right": 1.10, "up": 1.10}
        for facing, frames in canvas.memory_future_corruption_frames.items():
            corruption_targets = [
                canvas._fixed_height_floor_target(
                    normal_target, frame, height_scale=direction_scales[facing]
                )
                for frame in frames
            ]
            expected_height = normal_target.height() * direction_scales[facing]
            self.assertTrue(all(
                abs(rect.height() - expected_height) < 0.001
                for rect in corruption_targets
            ))
            self.assertTrue(all(
                rect.bottom() == normal_target.bottom()
                for rect in corruption_targets
            ))

    def test_future_archive_waits_before_its_first_capture_event(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=470)
        canvas.world_clock = 90
        with patch.object(canvas, "_reroll_memory_hourglass_location", return_value="lockbox"):
            canvas._start_memory_attempt("future")

        self.assertIsNone(canvas.memory_future_echo_event)
        self.assertGreaterEqual(canvas.memory_future_next_echo_tick - canvas.world_clock, 18)
        self.assertLessEqual(canvas.memory_future_next_echo_tick - canvas.world_clock, 45)
        self.assertGreaterEqual(canvas.memory_future_next_corruption_tick - canvas.world_clock, 7)
        self.assertLessEqual(canvas.memory_future_next_corruption_tick - canvas.world_clock, 18)

    def test_future_personal_corruption_pulses_between_capture_events(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=470)
        canvas.memory_active_archive = "future"
        canvas.world_clock = 60
        canvas.memory_future_next_echo_tick = 999
        canvas.memory_future_next_corruption_tick = 60
        canvas.keys = {Qt.Key_Right}
        canvas._can_walk = lambda _x, _y: True

        canvas._move_player()

        event = canvas.memory_future_corruption_event
        self.assertIsNotNone(event)
        self.assertGreaterEqual(event["duration"], 14)
        self.assertLessEqual(event["duration"], 20)
        self.assertFalse(canvas._future_corruption_frame().isNull())
        self.assertGreaterEqual(
            canvas.memory_future_next_corruption_tick - event["started"] - event["duration"],
            28,
        )

        canvas._start_future_echo_event(1.0, 0.0)
        self.assertIsNone(canvas.memory_future_corruption_event)
        self.assertTrue(canvas._future_corruption_frame().isNull())

    def test_recall_lens_grants_foresight_and_recharges_each_battle(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(inventory=["recall_lens"])
        canvas.start_battle("red_tape_wraith")

        with patch("frontend.rpg.window.QTimer.singleShot"):
            canvas.use_battle_item("recall_lens")

        self.assertEqual(canvas.focus, 1)
        self.assertTrue(canvas.foresight)
        self.assertEqual(canvas.battle_items["recall_lens"], 0)
        canvas.start_battle("misfiled_mimic")
        self.assertEqual(canvas.battle_items["recall_lens"], 1)

    def test_memory_attempt_timeout_restores_normal_state(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        canvas.memory_active_archive = "present"
        canvas.memory_attempt_started_tick = 100
        canvas.memory_hourglass_location = MEMORY_SEARCH_OBJECTS[0]["id"]
        canvas.memory_hourglass_found = True
        canvas.world_clock = 100 + MEMORY_ARCHIVE_RULES["present"]["seconds"] * 30
        canvas._tick_memory_attempt()

        self.assertIsNone(canvas.memory_active_archive)
        self.assertFalse(canvas.memory_hourglass_found)
        self.assertEqual(canvas.scene, "dialogue")

    def test_matching_hourglass_drag_commits_archive_and_all_three_grant_lens(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        with patch("frontend.rpg.window.save_game"):
            for archive_id in MEMORY_SEQUENCE:
                canvas.memory_active_archive = archive_id
                canvas.memory_hourglass_found = True
                canvas._complete_memory_archive(archive_id)
                self.assertEqual(canvas.memory_restoration_pending, archive_id)
                canvas.world_clock += 48
                canvas._tick_memory_restoration()

        self.assertEqual(canvas.state.memory_archives_completed, list(MEMORY_SEQUENCE))
        self.assertIn("memory", canvas.state.completed_trials)
        self.assertIn("recall_lens", canvas.state.inventory)
        self.assertTrue(all(
            not canvas.memory_plinth_state_atlases[archive_id].isNull()
            for archive_id in MEMORY_SEQUENCE
        ))
        self.assertTrue(all(
            not canvas.memory_plinth_incomplete_bases[archive_id].isNull()
            and not canvas.memory_plinth_incomplete_vfx[archive_id].isNull()
            for archive_id in MEMORY_SEQUENCE
        ))
        self.assertTrue(all(
            canvas.memory_plinth_state_atlases[archive_id].width() % 4 == 0
            and canvas.memory_plinth_state_atlases[archive_id].height() % 3 == 0
            for archive_id in MEMORY_SEQUENCE
        ))

    def test_memory_space_interaction_searches_nearest_hiding_place(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        prop = MEMORY_SEARCH_OBJECTS[0]
        canvas.state = ArchiveboundState(current_room="memory")
        canvas.memory_active_archive = "past"
        canvas.memory_hourglass_location = MEMORY_SEARCH_OBJECTS[-1]["id"]
        zone = QRect(*prop["interaction_rect"])
        canvas.state.player_x, canvas.state.player_y = zone.center().x(), zone.center().y()
        with patch.object(canvas, "show_dialogue"), patch("frontend.rpg.window.save_game"):
            canvas._interact_memory()
        self.assertIn(prop["id"], canvas.memory_searched_objects)

    def test_memory_search_requires_the_objects_tight_approach_zone(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        prop = MEMORY_SEARCH_OBJECTS[0]
        canvas.state = ArchiveboundState(current_room="memory", player_x=480, player_y=240)
        canvas.memory_active_archive = "past"
        canvas.memory_hourglass_location = prop["id"]
        with patch.object(canvas, "show_dialogue"), patch("frontend.rpg.window.save_game"):
            canvas._interact_memory()
        self.assertNotIn(prop["id"], canvas.memory_searched_objects)
        self.assertNotIn("Choose an Archive", canvas.toast)
        self.assertIn("glowing objects", canvas.toast)

    def test_every_memory_search_approach_zone_is_walkable(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        for prop in MEMORY_SEARCH_OBJECTS:
            center = QRect(*prop["interaction_rect"]).center()
            self.assertTrue(canvas._can_walk(center.x(), center.y()), prop["id"])
            max_width = 210 if prop["id"] in {"west_archive_bank", "east_book_bank"} else 160
            self.assertLessEqual(prop["interaction_rect"][2], max_width, prop["id"])
            max_height = 72 if prop["id"] in {"west_archive_bank", "east_book_bank"} else 52
            self.assertLessEqual(prop["interaction_rect"][3], max_height, prop["id"])

    def test_archive_cabinets_have_reachable_front_bands_and_solid_bodies(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        for prop_id in ("west_archive_bank", "east_book_bank"):
            prop = next(item for item in MEMORY_SEARCH_OBJECTS if item["id"] == prop_id)
            zone = QRectF(*prop["interaction_rect"])
            approach = zone.center()
            self.assertTrue(canvas._can_walk(approach.x(), approach.y()), prop_id)
            canvas.state.player_x, canvas.state.player_y = approach.x(), approach.y()
            self.assertTrue(canvas._memory_prop_is_in_range(prop), prop_id)
            self.assertFalse(
                canvas._can_walk(prop["position"][0], prop["position"][1]),
                prop_id,
            )

            # Reproduce actual upward movement: the first legal point against
            # the cabinet collision must already be searchable.
            approach_x = zone.center().x()
            nearest_legal_y = next(
                y for y in range(180, 301)
                if canvas._can_walk(approach_x, y)
            )
            canvas.state.player_x, canvas.state.player_y = approach_x, nearest_legal_y
            self.assertTrue(canvas._memory_prop_is_in_range(prop), prop_id)

    def test_both_scriptorium_desks_are_searchable_from_their_front_zones(self):
        for prop_id in ("west_scriptorium_desk", "east_scriptorium_desk"):
            canvas = ArchiveboundCanvas()
            self.addCleanup(canvas.deleteLater)
            canvas.timer.stop()
            prop = next(item for item in MEMORY_SEARCH_OBJECTS if item["id"] == prop_id)
            zone = QRect(*prop["interaction_rect"])
            canvas.state = ArchiveboundState(
                current_room="memory",
                player_x=zone.center().x(),
                player_y=zone.center().y(),
            )
            canvas.memory_active_archive = "past"
            canvas.memory_hourglass_location = "north_lockbox"
            with patch.object(canvas, "show_dialogue"), patch("frontend.rpg.window.save_game"):
                canvas._interact_memory()
            self.assertIn(prop_id, canvas.memory_searched_objects)

    def test_small_memory_props_have_reachable_multidirectional_interaction(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        for prop in MEMORY_SEARCH_OBJECTS:
            radius = prop.get("interaction_radius")
            if not radius:
                continue
            reachable = []
            for index in range(24):
                angle = math.tau * index / 24
                x = prop["position"][0] + math.cos(angle) * radius * 0.82
                y = prop["position"][1] + math.sin(angle) * radius * 0.82
                if canvas._can_walk(x, y):
                    canvas.state.player_x, canvas.state.player_y = x, y
                    if canvas._memory_prop_is_in_range(prop):
                        reachable.append((x, y))
            self.assertGreaterEqual(len(reachable), 4, prop["id"])

        astrolabe = next(item for item in MEMORY_SEARCH_OBJECTS if item["id"] == "wall_astrolabe")
        canvas.state.player_x, canvas.state.player_y = 105, 418
        self.assertTrue(canvas._can_walk(105, 418))
        self.assertTrue(canvas._memory_prop_is_in_range(astrolabe))
        gears = next(item for item in MEMORY_SEARCH_OBJECTS if item["id"] == "gear_debris")
        canvas.state.player_x, canvas.state.player_y = 635, 445
        self.assertTrue(canvas._can_walk(635, 445))
        self.assertTrue(canvas._memory_prop_is_in_range(gears))

    def test_activation_vfx_has_transparent_top_falloff(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        marker = canvas.archive_activation_marker_atlas.toImage()
        marker_row = marker.height() * 2 // 3
        self.assertTrue(all(
            marker.pixelColor(x, marker_row).alpha() == 0
            for x in range(marker.width())
        ))
        beams = canvas.archive_activation_beam_atlas.toImage()
        self.assertTrue(all(
            beams.pixelColor(x, 0).alpha() == 0
            for x in range(beams.width())
        ))

    def test_archive_floor_sigils_match_walkable_activation_zones(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        self.assertEqual(
            set(canvas.archive_activation_marker_frames),
            {"idle", "proximity", "activation"},
        )
        self.assertTrue(all(
            len(frames) == 4
            for frames in canvas.archive_activation_marker_frames.values()
        ))
        self.assertEqual(len(canvas.archive_activation_beam_frames), 4)
        self.assertTrue(all(not frame.isNull() for frame in canvas.archive_activation_beam_frames))
        for plinth in MEMORY_PLINTHS:
            zone = QRect(*plinth["activation_rect"])
            center = zone.center()
            self.assertTrue(canvas._can_walk(center.x(), center.y()), plinth["id"])
        past = next(item for item in MEMORY_PLINTHS if item["id"] == "past")
        center = QRect(*past["activation_rect"]).center()
        canvas.state.player_x, canvas.state.player_y = center.x(), center.y()
        with patch.object(canvas, "show_dialogue"), patch("frontend.rpg.window.save_game"):
            canvas._interact_memory()
        self.assertEqual(canvas.memory_active_archive, "past")
        self.assertEqual(canvas.memory_activation_effect["archive_id"], "past")
        canvas.world_clock = canvas.memory_activation_effect["duration"]
        with patch.object(canvas, "show_dialogue") as dialogue:
            canvas._tick_memory_activation_effect()
        self.assertIsNone(canvas.memory_activation_effect)
        dialogue.assert_called_once()

    def test_active_memory_timer_uses_hud_instead_of_world_center(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="memory")
        canvas.memory_active_archive = "past"
        canvas.world_clock = 300
        canvas.memory_attempt_started_tick = 0
        self.assertIn("PAST", canvas._memory_trial_hud_text())
        self.assertIn("0:50 LEFT", canvas._memory_trial_hud_text())

    def test_incomplete_and_completed_memory_plinths_share_rendered_scale(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()

        def solid_bounds(pixmap):
            image = pixmap.toImage()
            points = [
                (x, y)
                for y in range(image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 180
            ]
            xs, ys = zip(*points)
            return QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

        for archive_id in MEMORY_SEQUENCE:
            base = canvas.memory_plinth_incomplete_bases[archive_id]
            completed = canvas.environment_sheets[
                next(
                    spec["sheet"]
                    for spec in ROOM_ENVIRONMENT_SPRITES["memory"]
                    if spec["id"] == archive_id
                )
            ]
            complete_width = completed.width() // 4
            complete_frame = completed.copy(0, 0, complete_width, completed.height())
            base_bounds = solid_bounds(base)
            complete_bounds = solid_bounds(complete_frame)
            self.assertAlmostEqual(
                base_bounds.width() / base.width(),
                complete_bounds.width() / complete_width,
                delta=0.02,
            )
            self.assertAlmostEqual(
                base_bounds.height() / base.height(),
                complete_bounds.height() / completed.height(),
                delta=0.02,
            )

    def test_completed_future_plinth_keeps_one_floor_anchor(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        spec = next(
            item for item in ROOM_ENVIRONMENT_SPRITES["memory"] if item["id"] == "future"
        )
        sheet = canvas.environment_sheets[spec["sheet"]]
        frame_width = sheet.width() // 4
        anchors = []
        for frame_index in range(4):
            image = sheet.copy(
                frame_index * frame_width, 0, frame_width, sheet.height()
            ).toImage()
            lower_y = int(image.height() * 0.68)
            points = [
                (x, y)
                for y in range(lower_y, image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 180
            ]
            xs, ys = zip(*points)
            sorted_x = sorted(xs)
            anchors.append((sorted_x[len(sorted_x) // 2], max(ys)))
        self.assertEqual(len(set(anchors)), 1, anchors)

    def test_key_fragments_require_two_drag_fusions(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            completed_trials=["memory", "mercy", "order"],
            completed_seal_puzzles=["memory", "mercy", "order"],
            key_fragments=["memory", "mercy", "order"],
        )
        with patch("frontend.rpg.window.save_game"):
            canvas._try_fuse_key_items("fragment_memory", "fragment_mercy")
            self.assertFalse(canvas.state.vault_key_assembled)
            self.assertEqual(canvas.state.fused_key_parts, ["memory", "mercy"])
            canvas._try_fuse_key_items("key_pair", "fragment_order")

        self.assertTrue(canvas.state.vault_key_assembled)
        self.assertEqual(canvas._explore_items()[-1], "vault_key")

    def test_hostile_enemy_auto_engages_at_proximity(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="mercy",
            player_x=390,
            player_y=365,
            mercy_hearing_completed=True,
        )

        canvas._check_enemy_proximity()

        self.assertEqual(canvas.scene, "battle")
        self.assertEqual(canvas.battle_enemy_id, "red_tape_wraith")

    def test_mercy_wraith_does_not_exist_before_the_hearing_is_completed(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="mercy",
            player_x=390,
            player_y=365,
        )

        canvas._check_enemy_proximity()

        self.assertEqual(canvas.scene, "explore")
        self.assertIsNone(canvas._active_mercy_enemy_id())

    def test_mercy_hearing_summons_wraith_only_after_all_three_appeals(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="mercy",
            mercy_appeals_completed=["pardon", "diversion", "cure"],
            player_x=480,
            player_y=365,
        )

        with patch("frontend.rpg.window.save_game"):
            canvas._interact_mercy()

        self.assertTrue(canvas.state.mercy_hearing_completed)
        self.assertEqual(canvas.scene, "dialogue")
        self.assertEqual(canvas.dialogue_after, "summon_mercy_wraith")
        while canvas.scene == "dialogue":
            canvas.advance_dialogue()
        self.assertEqual(canvas.scene, "battle")
        self.assertEqual(canvas.battle_enemy_id, "red_tape_wraith")

    def test_mercy_threshold_guardian_does_not_complete_the_hall(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(current_room="mercy")
        canvas.start_battle("red_tape_wraith")

        with patch("frontend.rpg.window.save_game"):
            canvas._win_battle()

        self.assertIn("red_tape_wraith", canvas.state.defeated_enemies)
        self.assertNotIn("mercy", canvas.state.completed_trials)
        self.assertEqual(canvas.scene, "dialogue")

    def test_mercy_central_hearing_completes_hall_without_second_fight(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            current_room="mercy",
            defeated_enemies=["red_tape_wraith"],
            mercy_appeals_completed=["pardon", "diversion", "cure"],
            mercy_hearing_completed=False,
        )
        canvas.state.player_x, canvas.state.player_y = 480, 365

        with patch("frontend.rpg.window.save_game"):
            canvas._interact_mercy()

        self.assertIn("mercy", canvas.state.completed_trials)
        self.assertIn("appeal_tonic", canvas.state.inventory)
        self.assertTrue(canvas.state.mercy_hearing_completed)
        self.assertEqual(canvas.scene, "dialogue")

    def test_vault_boss_requires_inserted_key_and_deliberate_click(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.scene = "explore"
        canvas.state = ArchiveboundState(
            current_room="hub",
            player_x=480,
            player_y=172,
            completed_trials=["memory", "mercy", "order"],
            completed_seal_puzzles=["memory", "mercy", "order"],
            key_fragments=["memory", "mercy", "order"],
            fused_key_parts=["memory", "mercy", "order"],
            vault_key_assembled=True,
        )
        canvas._check_enemy_proximity()
        self.assertEqual(canvas.scene, "explore")
        canvas._activate_vault_keyhole()
        self.assertEqual(canvas.state.current_room, "hub")

        canvas.state.vault_key_inserted = True
        with patch("frontend.rpg.window.save_game"):
            canvas._activate_vault_keyhole()
            self.assertEqual(canvas.state.current_room, "hub")
            self.assertEqual(canvas.scene, "dialogue")
            self.assertIn("pre_vault_conversation_seen", canvas.state.narrative_flags)
            while canvas.scene == "dialogue":
                canvas.advance_dialogue()
        self.assertEqual(canvas.state.current_room, "vault")
        self.assertTrue(canvas.state.vault_opened)
        self.assertEqual(canvas.scene, "cinematic")

    def test_order_and_mercy_locks_require_full_verification(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.state = ArchiveboundState(
            completed_trials=["mercy", "order"],
            inventory=["appeal_tonic", "reset_compass"],
        )
        with patch("frontend.rpg.window.save_game"):
            canvas._start_seal_puzzle("mercy")
            canvas.mercy_loom_links = {
                item["id"]: item["id"] for item in MERCY_CONSEQUENCE_LINKS
            }
            canvas._handle_puzzle_click(canvas._mercy_loom_wheel_rect().center())
            self.assertIn("mercy", canvas.state.completed_seal_puzzles)

            canvas.scene = "explore"
            canvas._start_seal_puzzle("order")
            ring_rects = canvas._order_puzzle_rects()
            for index in (0, 1, 3):
                canvas._handle_puzzle_click(ring_rects[index].center())
                animation = canvas.order_rotor_animation
                canvas.world_clock = animation["started"] + animation["duration"]
                canvas._tick_order_rotor_animation()
            self.assertEqual(canvas.order_rings, [0, 0, 0, 0])
            canvas._handle_puzzle_click(QRect(390, 485, 180, 44).center())
            self.assertIn("order", canvas.state.completed_seal_puzzles)

    def test_coupled_registry_rotors_use_the_authored_socket_centers(self):
        centers = [
            (QRectF(rect).center().x(), QRectF(rect).center().y())
            for rect in ArchiveboundCanvas._order_puzzle_rects()
        ]

        self.assertEqual(
            centers,
            [(267.0, 261.0), (405.0, 261.0), (554.0, 261.0), (693.0, 261.0)],
        )

    def test_all_seal_puzzles_replace_the_room_with_an_opaque_focus_stage(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.resize(960, 680)
        canvas.scene = "seal_puzzle"

        with (
            patch.object(canvas, "_paint_world") as paint_world,
            patch.object(canvas, "_paint_particles") as paint_particles,
        ):
            for puzzle_id in ("memory", "mercy", "order"):
                canvas.active_puzzle = puzzle_id
                image = canvas.grab().toImage()
                self.assertEqual(image.pixelColor(0, 0).name(), "#010207")

        paint_world.assert_not_called()
        paint_particles.assert_not_called()

    def test_pending_minions_reform_until_boss_is_defeated(self):
        canvas = ArchiveboundCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.timer.stop()
        canvas.start_battle("pending")
        canvas._damage_minion(0, 999)
        self.assertEqual(canvas.minions[0]["respawn"], 2)
        canvas._finish_boss_turn()
        self.assertEqual(canvas.minions[0]["hp"], 0)
        canvas._finish_boss_turn()
        self.assertEqual(canvas.minions[0]["hp"], canvas.minions[0]["max_hp"])

    def test_new_runtime_sheets_keep_content_inside_each_cell(self):
        from PIL import Image

        sheets = {
            "last_clerk_directional_walk_runtime_sheet.png": 12,
            "last_clerk_back_walk_runtime_sheet.png": 4,
            "last_clerk_idle_actions_runtime_sheet.png": 12,
            "last_clerk_back_idle_actions_runtime_sheet.png": 12,
            "dialogue/mara_closeup_idle_runtime_sheet.png": 4,
            "dialogue/archivist_closeup_idle_runtime_sheet.png": 4,
            "combat/pending_minion/minion_runtime_sheet.png": 4,
            "cinematics/pending_throne_summon_runtime_sheet.png": 6,
            "cinematics/archivist_confrontation_runtime_sheet.png": 6,
            "cinematics/mara_rescue_runtime_sheet.png": 4,
            "cinematics/pending_victory_runtime_sheet.png": 4,
        }
        for relative, count in sheets.items():
            image = Image.open(Path("assets/rpg") / relative).convert("RGBA")
            self.assertEqual(image.width % count, 0)
            cell_width = image.width // count
            for index in range(count):
                frame = image.crop((index * cell_width, 0, (index + 1) * cell_width, image.height))
                bounds = frame.getchannel("A").getbbox()
                self.assertIsNotNone(bounds, f"{relative} frame {index}")
                self.assertGreater(bounds[0], 0)
                self.assertGreater(bounds[1], 0)
                self.assertLess(bounds[2], frame.width)
                self.assertLess(bounds[3], frame.height)

    def test_exploration_frames_keep_a_consistent_character_scale(self):
        from PIL import Image

        all_heights = []
        for relative, count in (
            ("last_clerk_directional_walk_runtime_sheet.png", 12),
            ("last_clerk_back_walk_runtime_sheet.png", 4),
            ("last_clerk_idle_actions_runtime_sheet.png", 12),
            ("last_clerk_back_idle_actions_runtime_sheet.png", 12),
        ):
            image = Image.open(Path("assets/rpg") / relative).convert("RGBA")
            cell_width = image.width // count
            heights = []
            for index in range(count):
                frame = image.crop((index * cell_width, 0, (index + 1) * cell_width, image.height))
                bounds = frame.getchannel("A").point(lambda value: 255 if value > 12 else 0).getbbox()
                self.assertIsNotNone(bounds)
                heights.append(bounds[3] - bounds[1])
            all_heights.extend(heights)
            self.assertEqual(min(heights), max(heights), relative)
        self.assertEqual(min(all_heights), max(all_heights))

    def test_all_qwer_abilities_have_runtime_frames(self):
        from PIL import Image

        expected = {"Q": "q_slash", "W": "w_ward", "E": "e_mark", "R": "r_redline"}
        self.assertEqual(set(ABILITY_ORDER), set(expected))
        for action in expected.values():
            path = Path("assets/rpg/combat/archivist") / f"{action}.png"
            self.assertTrue(path.is_file())
            image = Image.open(path).convert("RGBA")
            bounds = image.getchannel("A").point(lambda value: 0 if value <= 12 else value).getbbox()
            self.assertIsNotNone(bounds)
            self.assertGreater(bounds[0], 0)
            self.assertGreater(bounds[1], 0)
            self.assertLess(bounds[2], image.width)
            self.assertLess(bounds[3], image.height)

    def test_pending_has_eight_independent_uncropped_frames(self):
        from PIL import Image

        names = ("idle_a", "idle_b", "windup", "release", "vortex", "hit", "stagger", "defeat")
        for name in names:
            image = Image.open(Path("assets/rpg/combat/pending") / f"{name}.png").convert("RGBA")
            bounds = image.getchannel("A").getbbox()
            self.assertIsNotNone(bounds)
            self.assertGreater(bounds[0], 0)
            self.assertGreater(bounds[1], 0)
            self.assertLess(bounds[2], image.width)
            self.assertLess(bounds[3], image.height)

    def test_trial_enemy_frames_do_not_touch_sprite_boundaries(self):
        from PIL import Image

        for group in ("red_tape", "misfiled_mimic"):
            for name in ("idle_a", "idle_b", "attack", "hit"):
                image = Image.open(Path("assets/rpg/combat") / group / f"{name}.png").convert("RGBA")
                bounds = image.getchannel("A").getbbox()
                self.assertIsNotNone(bounds)
                self.assertGreater(bounds[0], 0)
                self.assertGreater(bounds[1], 0)
                self.assertLess(bounds[2], image.width)
                self.assertLess(bounds[3], image.height)


if __name__ == "__main__":
    unittest.main()
