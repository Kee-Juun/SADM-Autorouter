import datetime
import unittest
from pathlib import Path

from frontend.badge_effects import BADGE_EFFECTS
from PIL import Image
from utils.rewards import (
    ACHIEVEMENTS,
    PROGRESSION_ACHIEVEMENTS,
    award_run_rewards,
    normalize_user_rewards,
    record_failed_run,
)


class RewardProgressionTests(unittest.TestCase):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

    def fresh_user(self):
        return normalize_user_rewards({"xp": 0, "coins": 0})

    def test_progression_catalog_has_unique_requirements_and_rewards(self):
        requirement_keys = []
        badge_rewards = []
        for achievement_id, achievement in ACHIEVEMENTS.items():
            requirement = achievement["requirement"]
            requirement_keys.append((
                requirement.get("type"),
                requirement.get("mode"),
                requirement.get("count"),
                requirement.get("min_documents"),
            ))
            badge_rewards.append(achievement["badge_reward"])

        self.assertEqual(len(requirement_keys), len(set(requirement_keys)))
        self.assertEqual(len(badge_rewards), len(set(badge_rewards)))
        self.assertGreaterEqual(len(PROGRESSION_ACHIEVEMENTS), 20)

    def test_every_new_badge_has_transparent_art_and_unique_vfx_frames(self):
        effect_keys = []
        for definition in PROGRESSION_ACHIEVEMENTS:
            icon_path = self.PROJECT_ROOT / "assets" / "images" / "shop_icons" / definition["image"]
            self.assertTrue(icon_path.is_file(), definition["name"])
            with Image.open(icon_path) as image:
                self.assertEqual(image.mode, "RGBA", definition["name"])
                self.assertEqual(image.size, (256, 256), definition["name"])
                self.assertEqual(image.getpixel((0, 0))[3], 0, definition["name"])

            effect_key = BADGE_EFFECTS.get(definition["badge_reward"])
            self.assertTrue(effect_key, definition["name"])
            effect_keys.append(effect_key)
            frames = sorted((self.PROJECT_ROOT / "assets" / "images" / "badge_vfx" / effect_key).glob("*.png"))
            self.assertEqual(len(frames), 32, definition["name"])

        self.assertEqual(len(effect_keys), len(set(effect_keys)))

    def test_clean_streak_resets_on_a_run_with_errors(self):
        data = self.fresh_user()
        for _ in range(3):
            award_run_rewards(data, 1, now=datetime.datetime(2026, 9, 13, 12), persist=False)
        self.assertEqual(data["stats"]["best_clean_run_streak"], 3)
        self.assertIn("precision_streak_3", data["achievements"])

        award_run_rewards(data, 1, error_count=1, persist=False)
        self.assertEqual(data["stats"]["current_clean_run_streak"], 0)
        self.assertTrue(data["stats"]["last_run_had_failures"])

    def test_mode_mastery_and_clean_document_totals(self):
        data = self.fresh_user()
        award_run_rewards(data, 250, mode="mspb", duration_seconds=18000, persist=False)
        self.assertEqual(data["stats"]["mode_fresh_documents"]["mspb"], 250)
        self.assertEqual(data["stats"]["total_clean_fresh_documents"], 250)
        self.assertIn("mspb_mastery", data["achievements"])

    def test_recovery_requires_a_recorded_failure_then_clean_fresh_run(self):
        data = self.fresh_user()
        record_failed_run(data, persist=False)
        award_run_rewards(data, 3, persist=False)
        self.assertEqual(data["stats"]["recovery_runs"], 1)
        self.assertIn("back_online", data["achievements"])

    def test_speed_badge_requires_minimum_batch_size(self):
        too_small = self.fresh_user()
        award_run_rewards(too_small, 5, duration_seconds=60, persist=False)
        self.assertNotIn("swift_filing", too_small["achievements"])

        qualifying = self.fresh_user()
        award_run_rewards(qualifying, 25, duration_seconds=1800, persist=False)
        self.assertIn("swift_filing", qualifying["achievements"])
        self.assertEqual(qualifying["stats"]["best_clean_documents_per_hour"], 50.0)

    def test_six_router_menace_is_not_a_duplicate_of_full_bench(self):
        data = self.fresh_user()
        award_run_rewards(data, 1, parallel_routers=6, persist=False)
        self.assertIn("full_bench", data["achievements"])
        self.assertNotIn("six_router_menace", data["achievements"])

        for _ in range(9):
            award_run_rewards(data, 1, parallel_routers=6, persist=False)
        self.assertIn("six_router_menace", data["achievements"])

    def test_long_term_milestones_extend_past_5500(self):
        data = self.fresh_user()
        award_run_rewards(data, 10000, error_count=1, persist=False)
        self.assertIn("archive_colossus_5500", data["achievements"])
        self.assertIn("ten_thousand_mandate", data["achievements"])
        self.assertNotIn("endless_index_25000", data["achievements"])

    def test_legacy_profile_migration_preserves_progress_and_is_idempotent(self):
        legacy = {
            "xp": 8350,
            "coins": 2831,
            "level": 23,
            "achievements": ["first_run"],
            "owned_rewards": ["silcrow_badge"],
            "stats": {"total_fresh_documents": 6000},
        }

        migrated = normalize_user_rewards(legacy)
        self.assertGreaterEqual(migrated["xp"], 8350)
        self.assertGreaterEqual(migrated["coins"], 2831)
        self.assertIn("first_run", migrated["achievements"])
        self.assertIn("silcrow_badge", migrated["owned_rewards"])
        self.assertIn("archive_colossus_5500", migrated["achievements"])

        migrated_again = normalize_user_rewards(migrated)
        self.assertEqual(migrated_again["xp"], migrated["xp"])
        self.assertEqual(migrated_again["coins"], migrated["coins"])
        self.assertEqual(migrated_again["achievements"], migrated["achievements"])


if __name__ == "__main__":
    unittest.main()
