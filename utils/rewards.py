"""Reward economy, shop catalog, and achievement helpers.

This module owns user reward state so the UI can stay focused on presentation.
User progress is stored outside the packaged app at C:\\Users\\Public\\ach so new
EXE builds can reuse the same awards file instead of resetting progress.
"""

from __future__ import annotations

import datetime as _datetime
import json
import logging
import os
import sys
from pathlib import Path


# Public, version-resilient storage location.
PUBLIC_ACH_DIR = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "ach"
LEGACY_REWARDS_PATH = Path("config/user_rewards.json")
LEGACY_ASSETS_REWARDS_PATH = Path("assets/user_rewards.json")
LEGACY_ROOT_REWARDS_PATH = Path("user_rewards.json")
USER_REWARDS_PATH = PUBLIC_ACH_DIR / "user_rewards.json"
CUSTOM_WALLPAPER_ID = "custom_wallpaper"
CUSTOM_WALLPAPER_DIR = PUBLIC_ACH_DIR / "custom_wallpapers"
DEFAULT_CUSTOM_WALLPAPER = {
    "source_path": "",
    "processed_path": "",
    "zoom": 1.0,
    "offset_x": 0,
    "offset_y": 0,
}
DEFAULT_VISUAL_SETTINGS = {
    "focus_mode": False,
    "quiet_run_mode": False,
}


DEFAULT_EQUIPPED = {
    "skin": None,
    "header": None,
    "emoji": None,
    "badge": None,
    "font": None,
    "game": None,
}

DEFAULT_STATS = {
    "total_runs": 0,
    "total_fresh_documents": 0,
    "clean_runs": 0,
    "best_clean_run_fresh_documents": 0,
    "parallel_runs": 0,
    "max_parallel_routers": 1,
    "modes_completed": [],
    "after_midnight_runs": 0,
}

LEVEL_XP_THRESHOLDS = (
    0,
    25,
    75,
    150,
    250,
    400,
    600,
    850,
    1150,
    1500,
    1900,
    2350,
)

SHOP_SECTIONS = (
    ("skin", "THEMES"),
    ("header", "WALLPAPERS"),
    ("font", "FONTS"),
    ("emoji", "EMOJIS"),
    ("game", "GAMES"),
)

INVENTORY_SECTIONS = (
    ("skin", "THEMES"),
    ("header", "WALLPAPERS"),
    ("font", "FONTS"),
    ("emoji", "EMOJIS"),
    ("badge", "ACHIEVEMENT BADGES"),
    ("game", "GAMES"),
)

REWARD_TYPE_LABELS = {
    "skin": ("Theme", "Themes"),
    # Stored as "header" for backward compatibility with existing user_rewards.json.
    "header": ("Wallpaper", "Wallpapers"),
    "emoji": ("Emoji", "Emojis"),
    "badge": ("Achievement Badge", "Achievement Badges"),
    "font": ("Font", "Fonts"),
    "game": ("Game", "Games"),
}


REWARDS = {
    # Wallpaper cosmetics. Internal type remains "header" for saved-user compatibility.
    CUSTOM_WALLPAPER_ID: {
        "type": "header",
        "name": "Custom Wallpaper",
        "price": 0,
        "purchasable": False,
        "description": "Import, crop, and equip a personal wallpaper from this device.",
    },
    "mochi_wall": {
        "type": "header",
        "name": "Mochi",
        "price": 850,
        "image": "splashcat12.jpg",
        "description": "Sunshine-colored sass with a royal streak. A premium wallpaper for runs that need main-character energy.",
    },
    "nana_wall": {
        "type": "header",
        "name": "Nana",
        "price": 350,
        "image": "splashcat7.jpg",
        "description": "Soft, sleepy, and completely retired from unnecessary drama.",
    },
    "amber_wall": {
        "type": "header",
        "name": "Amber",
        "price": 550,
        "image": "splashcat17.jpg",
        "description": "Warm, classy, and very aware that it improves the room.",
    },
    "cookie_wall": {
        "type": "header",
        "name": "Cookie",
        "price": 750,
        "image": "splashcat18.jpg",
        "description": "A dramatic header for days when the queue has chosen paperwork violence.",
    },
    "luna_wall": {
        "type": "header",
        "name": "Luna",
        "price": 650,
        "image": "splashcat24.jpg",
        "description": "Moody, polished, and ready to supervise the routing desk.",
    },
    "aurora_desk_wall": {
        "type": "header",
        "name": "Aurora Desk",
        "price": 900,
        "image": "aurora_portal_wallpaper.png",
        "description": "A luminous portal wallpaper for operators who like their automation with a little atmosphere.",
    },
    "cyberpunk_command_wall": {
        "type": "header",
        "name": "Cyberpunk Command",
        "price": 980,
        "image": "cyberpunk_command_wallpaper.png",
        "description": "Rainy neon, chrome panels, and enough data glow to make every batch feel illegal in a stylish way.",
    },
    "sugar_glass_wall": {
        "type": "header",
        "name": "Sugar Glass",
        "price": 820,
        "image": "sugar_glass_wallpaper.png",
        "description": "Soft pastel sparkle with polished desk energy. Sweet, pretty, and still very much here to route.",
    },
    "pop_prism_stage_wall": {
        "type": "header",
        "name": "Pop Prism Stage",
        "price": 960,
        "image": "pop_prism_stage_wallpaper.png",
        "description": "A glossy concert-stage wallpaper for operators who want the queue to enter its comeback era.",
    },
    "silcrow_focus_wall": {
        "type": "header",
        "name": "Silcrow Focus",
        "price": 700,
        "image": "silcrow.png",
        "purchasable": False,
        "description": "A focused, symbol-forward wallpaper for serious routing days.",
    },
    "classic_autorouter_wall": {
        "type": "header",
        "name": "Classic Autorouter",
        "price": 250,
        "image": "autotestbg.jpg",
        "purchasable": False,
        "description": "The reliable default mood, cleaned up and ready for another batch.",
    },

    # UI themes. Internal type remains "skin" for saved-user compatibility.
    "ui_skin_blue": {
        "type": "skin",
        "name": "Blue Desk",
        "price": 250,
        "image": "shop_icons/skin_blue_desk.png",
        "description": "A cool blue interface pass for quieter routing days.",
    },
    "ui_skin_ocean": {
        "type": "skin",
        "name": "Ocean Glass",
        "price": 450,
        "image": "shop_icons/skin_ocean_glass.png",
        "description": "A brighter glassy theme with a clean operational feel.",
    },
    "ui_skin_midnight_clerk": {
        "type": "skin",
        "name": "Midnight Clerk",
        "price": 500,
        "image": "shop_icons/skin_midnight_clerk.png",
        "description": "A dark, focused theme for late runs and serious queues.",
    },
    "ui_skin_courtroom_noir": {
        "type": "skin",
        "name": "Courtroom Noir",
        "price": 650,
        "image": "shop_icons/skin_courtroom_noir.png",
        "description": "Restrained, dramatic, and slightly overprepared.",
    },
    "ui_skin_aurora_desk": {
        "type": "skin",
        "name": "Aurora Desk",
        "price": 800,
        "image": "shop_icons/skin_aurora_desk.png",
        "description": "Soft neon controls for operators who want the app to glow back.",
    },

    # Buyable UI font cosmetics. These change the app's user-facing UI voice.
    "ui_font_command_sans": {
        "type": "font",
        "name": "Command Sans",
        "price": 320,
        "font_family": "Bahnschrift",
        "font_fallbacks": ["Segoe UI", "Arial"],
        "preview_text": "Command Sans",
        "description": "Clean tactical lettering for a sharper control-room feel.",
    },
    "ui_font_glass_rounded": {
        "type": "font",
        "name": "Glass Rounded",
        "price": 380,
        "font_family": "Trebuchet MS",
        "font_fallbacks": ["Segoe UI", "Arial"],
        "preview_text": "Glass Rounded",
        "description": "Friendly, modern, and readable without losing personality.",
    },
    "ui_font_circuit_mono": {
        "type": "font",
        "name": "Circuit Mono",
        "price": 420,
        "font_family": "Consolas",
        "font_fallbacks": ["Courier New", "Lucida Console"],
        "preview_text": "Circuit Mono",
        "description": "Terminal-coded energy for operators who like their UI precise.",
    },
    "ui_font_rune_serif": {
        "type": "font",
        "name": "Rune Serif",
        "price": 540,
        "font_family": "Cambria",
        "font_fallbacks": ["Georgia", "Times New Roman"],
        "preview_text": "Rune Serif",
        "description": "A formal fantasy-style serif for dramatic routing victories.",
    },
    "ui_font_signature_glow": {
        "type": "font",
        "name": "Signature Glow",
        "price": 760,
        "font_family": "Brightness",
        "font_fallbacks": ["Segoe Script", "Brush Script MT", "Segoe UI"],
        "font_path": "fonts/Brightness.ttf",
        "preview_text": "Signature Glow",
        "description": "Premium handwritten flair. Fancy enough to be mildly suspicious.",
    },

    # Buyable emoji cosmetics. IDs keep the old badge_emoji_ prefix so existing
    # user_rewards.json files keep their purchases.
    "badge_emoji_fire": {
        "type": "emoji",
        "name": "Fire Emoji",
        "image": "shop_icons/emoji_fire.png",
        "price": 350,
        "description": "For runs that are somehow intense and successful at the same time.",
    },
    "badge_emoji_cool": {
        "type": "emoji",
        "name": "Cool Emoji",
        "image": "shop_icons/emoji_cool.png",
        "price": 400,
        "description": "Calm under pressure, allergic to drama, and still getting the work done.",
    },
    "badge_emoji_heart": {
        "type": "emoji",
        "name": "Purple Heart Emoji",
        "image": "shop_icons/emoji_purple_heart.png",
        "price": 150,
        "description": "Soft energy for hard queues.",
    },
    "badge_emoji_tongue": {
        "type": "emoji",
        "name": "Playful Emoji",
        "image": "shop_icons/emoji_playful.png",
        "price": 100,
        "description": "Chaotic good, but with deliverables.",
    },
    "badge_emoji_thumbs_up": {
        "type": "emoji",
        "name": "Thumbs Up Emoji",
        "image": "shop_icons/emoji_thumbs_up.png",
        "price": 100,
        "description": "Everything is fine. The button said so.",
    },
    "badge_emoji_heart_eyes": {
        "type": "emoji",
        "name": "Heart Eyes Emoji",
        "image": "shop_icons/emoji_heart_eyes.png",
        "price": 150,
        "description": "For anyone who appreciates good formatting and clean routing.",
    },
    "badge_emoji_flex": {
        "type": "emoji",
        "name": "Flex Emoji",
        "image": "shop_icons/emoji_flex.png",
        "price": 120,
        "description": "For operators carrying the batch with suspicious grace.",
    },
    "badge_emoji_rock": {
        "type": "emoji",
        "name": "Rockstar Emoji",
        "image": "shop_icons/emoji_rockstar.png",
        "price": 250,
        "description": "Loud, legendary, and very productive after coffee.",
    },
    "badge_emoji_red_heart": {
        "type": "emoji",
        "name": "Red Heart Emoji",
        "price": 200,
        "image": "shop_icons/emoji_red_heart.png",
        "description": "A supportive little badge for long routing days.",
    },
    "badge_emoji_green_heart": {
        "type": "emoji",
        "name": "Green Heart Emoji",
        "image": "shop_icons/emoji_green_heart.png",
        "price": 120,
        "description": "Fresh, calm, and politely productive.",
    },
    "badge_emoji_heart_eyes_cat": {
        "type": "emoji",
        "name": "Heart Eyes Deluxe Emoji",
        "image": "shop_icons/emoji_heart_eyes_deluxe.png",
        "price": 350,
        "description": "For dramatic appreciation of a clean batch.",
    },
    "badge_emoji_nails": {
        "type": "emoji",
        "name": "Sassy Nails Emoji",
        "image": "shop_icons/emoji_nails.png",
        "price": 450,
        "description": "Emails professionally. Routes with attitude.",
    },

    # Legacy cosmetic markers from older builds. They are no longer sold, but
    # remain equippable for users who already bought them.
    "badge_lni_whisperer": {
        "type": "emoji",
        "name": "LNI Whisperer Marker",
        "image": "shop_icons/badge_lni_whisperer.png",
        "price": 0,
        "purchasable": False,
        "description": "Legacy cosmetic marker retained from an earlier rewards build.",
    },
    "badge_docket_diva": {
        "type": "emoji",
        "name": "Docket Diva Marker",
        "image": "shop_icons/badge_docket_diva.png",
        "price": 0,
        "purchasable": False,
        "description": "Legacy cosmetic marker retained from an earlier rewards build.",
    },
    "badge_queue_slayer": {
        "type": "emoji",
        "name": "Queue Slayer Marker",
        "image": "shop_icons/badge_queue_slayer.png",
        "price": 0,
        "purchasable": False,
        "description": "Legacy cosmetic marker retained from an earlier rewards build.",
    },
    "badge_archive_authority": {
        "type": "emoji",
        "name": "Archive Authority Marker",
        "image": "shop_icons/badge_archive_authority.png",
        "price": 0,
        "purchasable": False,
        "description": "Legacy cosmetic marker retained from an earlier rewards build.",
    },
    "badge_six_router_menace": {
        "type": "emoji",
        "name": "Six Router Menace Marker",
        "image": "shop_icons/badge_six_router_menace.png",
        "price": 0,
        "purchasable": False,
        "description": "Legacy cosmetic marker retained from an earlier rewards build.",
    },

    # Achievement badges. These are earned through run milestones, never bought.
    "achievement_first_route_badge": {
        "type": "badge",
        "name": "First Route Crest",
        "image": "shop_icons/achievement_first_route.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "first_route",
        "description": "Earned by completing the first fresh routed document.",
    },
    "achievement_clean_sweep_badge": {
        "type": "badge",
        "name": "Clean Sweep Aegis",
        "image": "shop_icons/achievement_clean_sweep.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "clean_sweep",
        "description": "Earned by completing a run with no errors or timeouts.",
    },
    "achievement_parallel_boss_badge": {
        "type": "badge",
        "name": "Parallel Command Sigil",
        "image": "shop_icons/achievement_parallel_boss.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "parallel_boss",
        "description": "Earned by completing a fresh run with parallel routers enabled.",
    },
    "achievement_full_bench_badge": {
        "type": "badge",
        "name": "Full Bench Core",
        "image": "shop_icons/achievement_full_bench.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "full_bench",
        "description": "Earned by completing a run with six parallel routers.",
    },
    "achievement_no_misses_badge": {
        "type": "badge",
        "name": "No Misses Vanguard",
        "image": "shop_icons/achievement_no_misses.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "no_misses_25",
        "description": "Earned by routing at least 25 fresh documents in one clean run.",
    },
    "achievement_hundred_club_badge": {
        "type": "badge",
        "name": "Hundred Club Apex",
        "image": "shop_icons/achievement_hundred_club.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "hundred_club",
        "description": "Earned by reaching 100 total fresh routed documents.",
    },
    "achievement_court_hopper_badge": {
        "type": "badge",
        "name": "Court Hopper Relay",
        "image": "shop_icons/achievement_court_hopper.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "court_hopper",
        "description": "Earned by completing successful runs in three different autorouter modes.",
    },
    "achievement_night_shift_badge": {
        "type": "badge",
        "name": "Night Shift Terminal",
        "image": "shop_icons/achievement_night_shift.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "night_shift_legend",
        "description": "Earned by completing a fresh routing run after midnight.",
    },
    "achievement_routing_spark_badge": {
        "type": "badge",
        "name": "Routing Spark",
        "image": "shop_icons/achievement_routing_spark.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "routing_spark",
        "description": "Earned by reaching 10 total fresh routed documents.",
    },
    "achievement_brief_storm_badge": {
        "type": "badge",
        "name": "Brief Storm",
        "image": "shop_icons/achievement_brief_storm.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "brief_storm",
        "description": "Earned by reaching 50 total fresh routed documents.",
    },
    "achievement_calendar_crusher_badge": {
        "type": "badge",
        "name": "Calendar Crusher",
        "image": "shop_icons/achievement_calendar_crusher.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "calendar_crusher",
        "description": "Earned by reaching 750 total fresh routed documents.",
    },
    "achievement_thousand_routes_badge": {
        "type": "badge",
        "name": "Thousand Routes Crown",
        "image": "shop_icons/achievement_thousand_routes.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "thousand_routes",
        "description": "Earned by reaching 1,000 total fresh routed documents.",
    },
    "achievement_docket_warlord_badge": {
        "type": "badge",
        "name": "Docket Warlord",
        "image": "shop_icons/achievement_docket_warlord.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "docket_warlord",
        "description": "Earned by reaching 1,500 total fresh routed documents.",
    },
    "achievement_legendary_circuit_badge": {
        "type": "badge",
        "name": "Legendary Circuit",
        "image": "shop_icons/achievement_legendary_circuit.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "legendary_circuit",
        "description": "Earned by reaching 2,500 total fresh routed documents.",
    },
    "achievement_precision_streak_badge": {
        "type": "badge",
        "name": "Precision Streak",
        "image": "shop_icons/achievement_precision_streak.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "precision_streak_3",
        "description": "Earned by completing 3 clean routing runs.",
    },
    "achievement_audit_proof_badge": {
        "type": "badge",
        "name": "Audit-Proof Aegis",
        "image": "shop_icons/achievement_audit_proof.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "audit_proof_25",
        "description": "Earned by completing 25 clean routing runs.",
    },
    "achievement_immaculate_badge": {
        "type": "badge",
        "name": "Immaculate Record",
        "image": "shop_icons/achievement_immaculate.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "immaculate_50",
        "description": "Earned by completing 50 clean routing runs.",
    },
    "achievement_router_captain_badge": {
        "type": "badge",
        "name": "Router Captain",
        "image": "shop_icons/achievement_router_captain.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "router_captain_5",
        "description": "Earned by completing 5 fresh parallel-router runs.",
    },
    "achievement_router_admiral_badge": {
        "type": "badge",
        "name": "Router Admiral",
        "image": "shop_icons/achievement_router_admiral.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "router_admiral_25",
        "description": "Earned by completing 25 fresh parallel-router runs.",
    },
    "achievement_jurisdiction_juggler_badge": {
        "type": "badge",
        "name": "Jurisdiction Juggler",
        "image": "shop_icons/achievement_jurisdiction_juggler.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "jurisdiction_juggler",
        "description": "Earned by completing fresh runs in 5 autorouter modes.",
    },
    "achievement_full_spectrum_badge": {
        "type": "badge",
        "name": "Full Spectrum Router",
        "image": "shop_icons/achievement_full_spectrum.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "full_spectrum_router",
        "description": "Earned by completing fresh runs in 7 autorouter modes.",
    },
    "achievement_midnight_operator_badge": {
        "type": "badge",
        "name": "Midnight Operator",
        "image": "shop_icons/achievement_midnight_operator.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "midnight_operator_5",
        "description": "Earned by completing 5 fresh routing runs after midnight.",
    },
    "achievement_no_misses_50_badge": {
        "type": "badge",
        "name": "No Misses Elite",
        "image": "shop_icons/achievement_no_misses_50.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "no_misses_50",
        "description": "Earned by routing at least 50 fresh documents in one clean run.",
    },
    "achievement_no_misses_100_badge": {
        "type": "badge",
        "name": "No Misses Apex",
        "image": "shop_icons/achievement_no_misses_100.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "no_misses_100",
        "description": "Earned by routing at least 100 fresh documents in one clean run.",
    },

    # Former title cosmetics, now promoted to achievement badges.
    "title_lni_whisperer": {
        "type": "badge",
        "name": "LNI Whisperer Signal",
        "image": "shop_icons/title_lni_whisperer.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "lni_whisperer",
        "description": "Earned by reaching 25 total fresh routed documents.",
    },
    "title_docket_diva": {
        "type": "badge",
        "name": "Docket Diva Protocol",
        "image": "shop_icons/title_docket_diva.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "docket_diva",
        "description": "Earned by completing fresh runs in two different autorouter modes.",
    },
    "title_queue_slayer": {
        "type": "badge",
        "name": "Queue Slayer Breaker",
        "image": "shop_icons/title_queue_slayer.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "queue_slayer",
        "description": "Earned by reaching 250 total fresh routed documents.",
    },
    "title_archive_authority": {
        "type": "badge",
        "name": "Archive Authority Seal",
        "image": "shop_icons/title_archive_authority.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "archive_authority",
        "description": "Earned by completing 10 clean routing runs.",
    },
    "title_final_reviewer": {
        "type": "badge",
        "name": "Final Reviewer Prime",
        "image": "shop_icons/title_final_reviewer.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "final_reviewer",
        "description": "Earned by reaching 500 total fresh routed documents.",
    },
    "title_six_router_menace": {
        "type": "badge",
        "name": "Six Router Menace",
        "image": "shop_icons/title_six_router_menace.png",
        "price": 0,
        "purchasable": False,
        "achievement_id": "six_router_menace",
        "description": "Earned by running with six parallel routers.",
    },

    # Games.
    "game_tetris": {
        "type": "game",
        "name": "Tetris Game",
        "price": 0,
        "required_xp": 100,
        "image": "tetrisicon.png",
        "unlock_message": "Tetris break privilege unlocked. It is now claimable in the Shop.",
        "description": "A free break-time game earned at 100 XP. Still somehow stressful. Still somehow worth it.",
    },
}


ACHIEVEMENTS = {
    "first_route": {
        "name": "First Route Crest",
        "description": "Complete your first fresh routed document.",
        "requirement": {"type": "total_fresh_documents", "count": 1},
        "coins": 10,
        "xp": 5,
        "badge_reward": "achievement_first_route_badge",
    },
    "routing_spark": {
        "name": "Routing Spark",
        "description": "Reach 10 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 10},
        "coins": 20,
        "xp": 10,
        "badge_reward": "achievement_routing_spark_badge",
    },
    "lni_whisperer": {
        "name": "LNI Whisperer Signal",
        "description": "Reach 25 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 25},
        "coins": 30,
        "xp": 15,
        "badge_reward": "title_lni_whisperer",
    },
    "brief_storm": {
        "name": "Brief Storm",
        "description": "Reach 50 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 50},
        "coins": 35,
        "xp": 15,
        "badge_reward": "achievement_brief_storm_badge",
    },
    "hundred_club": {
        "name": "Hundred Club Apex",
        "description": "Reach 100 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 100},
        "coins": 50,
        "xp": 20,
        "badge_reward": "achievement_hundred_club_badge",
    },
    "queue_slayer": {
        "name": "Queue Slayer Breaker",
        "description": "Reach 250 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 250},
        "coins": 75,
        "xp": 25,
        "badge_reward": "title_queue_slayer",
    },
    "final_reviewer": {
        "name": "Final Reviewer Prime",
        "description": "Reach 500 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 500},
        "coins": 100,
        "xp": 35,
        "badge_reward": "title_final_reviewer",
    },
    "calendar_crusher": {
        "name": "Calendar Crusher",
        "description": "Reach 750 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 750},
        "coins": 125,
        "xp": 40,
        "badge_reward": "achievement_calendar_crusher_badge",
    },
    "thousand_routes": {
        "name": "Thousand Routes Crown",
        "description": "Reach 1,000 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 1000},
        "coins": 175,
        "xp": 50,
        "badge_reward": "achievement_thousand_routes_badge",
    },
    "docket_warlord": {
        "name": "Docket Warlord",
        "description": "Reach 1,500 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 1500},
        "coins": 225,
        "xp": 65,
        "badge_reward": "achievement_docket_warlord_badge",
    },
    "legendary_circuit": {
        "name": "Legendary Circuit",
        "description": "Reach 2,500 total fresh routed documents.",
        "requirement": {"type": "total_fresh_documents", "count": 2500},
        "coins": 350,
        "xp": 90,
        "badge_reward": "achievement_legendary_circuit_badge",
    },
    "clean_sweep": {
        "name": "Clean Sweep Aegis",
        "description": "Complete a run with no errors or timeouts.",
        "requirement": {"type": "clean_runs", "count": 1},
        "coins": 15,
        "xp": 5,
        "badge_reward": "achievement_clean_sweep_badge",
    },
    "precision_streak_3": {
        "name": "Precision Streak",
        "description": "Complete 3 clean routing runs.",
        "requirement": {"type": "clean_runs", "count": 3},
        "coins": 30,
        "xp": 15,
        "badge_reward": "achievement_precision_streak_badge",
    },
    "archive_authority": {
        "name": "Archive Authority Seal",
        "description": "Complete 10 clean routing runs.",
        "requirement": {"type": "clean_runs", "count": 10},
        "coins": 60,
        "xp": 20,
        "badge_reward": "title_archive_authority",
    },
    "audit_proof_25": {
        "name": "Audit-Proof Aegis",
        "description": "Complete 25 clean routing runs.",
        "requirement": {"type": "clean_runs", "count": 25},
        "coins": 100,
        "xp": 35,
        "badge_reward": "achievement_audit_proof_badge",
    },
    "immaculate_50": {
        "name": "Immaculate Record",
        "description": "Complete 50 clean routing runs.",
        "requirement": {"type": "clean_runs", "count": 50},
        "coins": 180,
        "xp": 55,
        "badge_reward": "achievement_immaculate_badge",
    },
    "parallel_boss": {
        "name": "Parallel Command",
        "description": "Complete a fresh run with parallel routers enabled.",
        "requirement": {"type": "parallel_runs", "count": 1},
        "coins": 20,
        "xp": 10,
        "badge_reward": "achievement_parallel_boss_badge",
    },
    "router_captain_5": {
        "name": "Router Captain",
        "description": "Complete 5 fresh parallel-router runs.",
        "requirement": {"type": "parallel_runs", "count": 5},
        "coins": 75,
        "xp": 25,
        "badge_reward": "achievement_router_captain_badge",
    },
    "router_admiral_25": {
        "name": "Router Admiral",
        "description": "Complete 25 fresh parallel-router runs.",
        "requirement": {"type": "parallel_runs", "count": 25},
        "coins": 160,
        "xp": 45,
        "badge_reward": "achievement_router_admiral_badge",
    },
    "full_bench": {
        "name": "Full Bench Core",
        "description": "Run with six parallel routers.",
        "requirement": {"type": "max_parallel_routers", "count": 6},
        "coins": 35,
        "xp": 15,
        "badge_reward": "achievement_full_bench_badge",
    },
    "six_router_menace": {
        "name": "Six Router Menace",
        "description": "Run with six parallel routers.",
        "requirement": {"type": "max_parallel_routers", "count": 6},
        "coins": 50,
        "xp": 20,
        "badge_reward": "title_six_router_menace",
    },
    "no_misses_25": {
        "name": "No Misses Vanguard",
        "description": "Route at least 25 fresh documents in one clean run.",
        "requirement": {"type": "single_clean_run_fresh_documents", "count": 25},
        "coins": 30,
        "xp": 15,
        "badge_reward": "achievement_no_misses_badge",
    },
    "no_misses_50": {
        "name": "No Misses Elite",
        "description": "Route at least 50 fresh documents in one clean run.",
        "requirement": {"type": "single_clean_run_fresh_documents", "count": 50},
        "coins": 90,
        "xp": 30,
        "badge_reward": "achievement_no_misses_50_badge",
    },
    "no_misses_100": {
        "name": "No Misses Apex",
        "description": "Route at least 100 fresh documents in one clean run.",
        "requirement": {"type": "single_clean_run_fresh_documents", "count": 100},
        "coins": 200,
        "xp": 60,
        "badge_reward": "achievement_no_misses_100_badge",
    },
    "docket_diva": {
        "name": "Docket Diva Protocol",
        "description": "Complete fresh runs in two different autorouter modes.",
        "requirement": {"type": "modes_completed", "count": 2},
        "coins": 30,
        "xp": 15,
        "badge_reward": "title_docket_diva",
    },
    "court_hopper": {
        "name": "Court Hopper Relay",
        "description": "Complete successful runs in three different autorouter modes.",
        "requirement": {"type": "modes_completed", "count": 3},
        "coins": 40,
        "xp": 15,
        "badge_reward": "achievement_court_hopper_badge",
    },
    "jurisdiction_juggler": {
        "name": "Jurisdiction Juggler",
        "description": "Complete fresh runs in five different autorouter modes.",
        "requirement": {"type": "modes_completed", "count": 5},
        "coins": 90,
        "xp": 30,
        "badge_reward": "achievement_jurisdiction_juggler_badge",
    },
    "full_spectrum_router": {
        "name": "Full Spectrum Router",
        "description": "Complete fresh runs in seven different autorouter modes.",
        "requirement": {"type": "modes_completed", "count": 7},
        "coins": 180,
        "xp": 55,
        "badge_reward": "achievement_full_spectrum_badge",
    },
    "night_shift_legend": {
        "name": "Night Shift Terminal",
        "description": "Complete a fresh routing run after midnight.",
        "requirement": {"type": "after_midnight_runs", "count": 1},
        "coins": 25,
        "xp": 10,
        "badge_reward": "achievement_night_shift_badge",
    },
    "midnight_operator_5": {
        "name": "Midnight Operator",
        "description": "Complete 5 fresh routing runs after midnight.",
        "requirement": {"type": "after_midnight_runs", "count": 5},
        "coins": 90,
        "xp": 30,
        "badge_reward": "achievement_midnight_operator_badge",
    },
}


def _legacy_rewards_candidates():
    """Return old rewards locations that earlier builds may have used."""
    relative_paths = (
        LEGACY_REWARDS_PATH,
        LEGACY_ASSETS_REWARDS_PATH,
        LEGACY_ROOT_REWARDS_PATH,
    )
    base_dirs = [Path.cwd()]
    if getattr(sys, "frozen", False):
        base_dirs.append(Path(sys.executable).resolve().parent)

    seen = set()
    for base_dir in base_dirs:
        for relative_path in relative_paths:
            candidate = base_dir / relative_path
            key = str(candidate.resolve(strict=False)).lower()
            if key in seen:
                continue
            seen.add(key)
            yield candidate


def _ensure_public_storage_and_migrate() -> None:
    """Ensure public storage exists and copy a legacy rewards file once."""
    try:
        PUBLIC_ACH_DIR.mkdir(parents=True, exist_ok=True)
        if USER_REWARDS_PATH.exists():
            return

        for legacy_path in _legacy_rewards_candidates():
            if not legacy_path.exists():
                continue
            try:
                with open(legacy_path, "r", encoding="utf-8") as handle:
                    legacy_data = json.load(handle)
            except Exception as exc:
                logging.warning(f"Skipped unreadable legacy rewards file {legacy_path}: {exc}")
                continue

            with open(USER_REWARDS_PATH, "w", encoding="utf-8") as handle:
                json.dump(normalize_user_rewards(legacy_data), handle, indent=2)
            logging.info(f"Migrated legacy rewards file to public storage: {legacy_path} -> {USER_REWARDS_PATH}")
            return
    except Exception as exc:
        logging.warning(f"Failed preparing public rewards storage: {exc}")


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_custom_wallpaper_data(value):
    """Normalize custom wallpaper metadata from old or partial reward files."""
    custom_data = dict(DEFAULT_CUSTOM_WALLPAPER)
    if isinstance(value, dict):
        custom_data.update(value)

    custom_data["source_path"] = str(custom_data.get("source_path") or "")
    custom_data["processed_path"] = str(custom_data.get("processed_path") or "")
    custom_data["zoom"] = max(1.0, _as_float(custom_data.get("zoom"), 1.0))
    custom_data["offset_x"] = _as_int(custom_data.get("offset_x"))
    custom_data["offset_y"] = _as_int(custom_data.get("offset_y"))
    return custom_data


def get_custom_wallpaper_dir():
    """Return the per-user custom wallpaper folder, creating it if needed."""
    CUSTOM_WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    return CUSTOM_WALLPAPER_DIR


def get_custom_wallpaper_data(user_data=None):
    """Return normalized custom wallpaper metadata for the current user."""
    data = user_data if user_data is not None else load_user_rewards()
    return _coerce_custom_wallpaper_data((data or {}).get("custom_wallpaper"))


def get_custom_wallpaper_path(user_data=None):
    """Return the processed custom wallpaper path when it exists on disk."""
    processed_path = get_custom_wallpaper_data(user_data).get("processed_path")
    if not processed_path:
        return None
    path = Path(processed_path)
    return path if path.exists() else None


def custom_wallpaper_exists(user_data=None):
    """Return whether a usable custom wallpaper has been imported."""
    return get_custom_wallpaper_path(user_data) is not None


def _has_reward_progress(data):
    """Return whether a rewards payload contains user-earned or purchased state."""
    data = data or {}
    stats = data.get("stats", {}) or {}
    return any(
        [
            _as_int(data.get("xp")) > 0,
            _as_int(data.get("coins")) > 0,
            _as_int(data.get("total_documents_processed")) > 0,
            _as_int(data.get("total_documents")) > 0,
            _as_int(stats.get("total_fresh_documents")) > 0,
            bool(data.get("unlocked")),
            bool(data.get("inventory")),
            bool(data.get("purchased_rewards")),
            bool(data.get("achievements")),
        ]
    )


def _preserve_existing_rewards_if_better(user_data):
    """Avoid overwriting real progress when a caller accidentally passes defaults."""
    data = dict(user_data or {})
    if _has_reward_progress(data):
        return data
    try:
        current = load_user_rewards()
    except Exception:
        return data
    if _has_reward_progress(current):
        logging.warning("Ignored empty rewards payload and preserved existing reward progress.")
        return current
    return data


def set_custom_wallpaper_data(user_data, source_path, processed_path, zoom=1.0, offset_x=0, offset_y=0):
    """Persist custom wallpaper metadata and equip it immediately."""
    logging.info(
        "Saving custom wallpaper metadata: source=%s processed=%s zoom=%s offset=(%s,%s)",
        source_path,
        processed_path,
        zoom,
        offset_x,
        offset_y,
    )
    data = _preserve_existing_rewards_if_better(user_data)
    data["custom_wallpaper"] = _coerce_custom_wallpaper_data(
        {
            "source_path": source_path,
            "processed_path": processed_path,
            "zoom": zoom,
            "offset_x": offset_x,
            "offset_y": offset_y,
        }
    )
    unlocked = _unique_list(data.get("unlocked", []))
    if CUSTOM_WALLPAPER_ID not in unlocked:
        unlocked.append(CUSTOM_WALLPAPER_ID)
    data["unlocked"] = unlocked
    equipped = dict(DEFAULT_EQUIPPED)
    equipped.update(data.get("equipped", {}) or {})
    equipped["header"] = CUSTOM_WALLPAPER_ID
    data["equipped"] = equipped
    saved = save_user_rewards(data)
    logging.info(
        "Custom wallpaper saved and equipped. equipped_header=%s processed_exists=%s",
        saved.get("equipped", {}).get("header"),
        bool(get_custom_wallpaper_path(saved)),
    )
    return saved


def get_visual_settings(user_data=None):
    """Return normalized cosmetic display settings for the current user."""
    data = user_data if user_data is not None else load_user_rewards()
    settings = dict(DEFAULT_VISUAL_SETTINGS)
    settings.update((data or {}).get("visual_settings", {}) or {})
    return {key: bool(settings.get(key)) for key in DEFAULT_VISUAL_SETTINGS}


def is_visual_setting_enabled(setting_key, user_data=None):
    """Return whether a cosmetic display setting is enabled."""
    return bool(get_visual_settings(user_data).get(setting_key))


def set_visual_setting(user_data, setting_key, enabled):
    """Persist a cosmetic display setting without affecting reward ownership."""
    if setting_key not in DEFAULT_VISUAL_SETTINGS:
        raise KeyError(f"Unknown visual setting: {setting_key}")
    data = _preserve_existing_rewards_if_better(user_data)
    settings = get_visual_settings(data)
    settings[setting_key] = bool(enabled)
    data["visual_settings"] = settings
    saved = save_user_rewards(data)
    logging.info("Visual setting saved: %s=%s", setting_key, bool(enabled))
    return saved


def _unique_list(values):
    seen = set()
    result = []
    for value in values or []:
        if value is None:
            continue
        value = str(value)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _minimum_xp_for_level(level):
    level = max(0, _as_int(level))
    if level < len(LEVEL_XP_THRESHOLDS):
        return LEVEL_XP_THRESHOLDS[level]
    return LEVEL_XP_THRESHOLDS[-1] + ((level - len(LEVEL_XP_THRESHOLDS) + 1) * 500)


def calculate_level(total_xp):
    """Calculate the user level from XP."""
    total_xp = max(0, _as_int(total_xp))
    level = 0
    for index, threshold in enumerate(LEVEL_XP_THRESHOLDS):
        if total_xp >= threshold:
            level = index
        else:
            break

    if total_xp >= LEVEL_XP_THRESHOLDS[-1]:
        level = len(LEVEL_XP_THRESHOLDS) - 1
        extra_xp = total_xp - LEVEL_XP_THRESHOLDS[-1]
        level += extra_xp // 500
    return level


def xp_to_next_level(total_xp):
    total_xp = max(0, _as_int(total_xp))
    current_level = calculate_level(total_xp)
    next_threshold = _minimum_xp_for_level(current_level + 1)
    return max(0, next_threshold - total_xp)


def get_level_progress(total_xp):
    """Return XP progress within the current level for compact UI displays."""
    total_xp = max(0, _as_int(total_xp))
    current_level = calculate_level(total_xp)
    current_threshold = _minimum_xp_for_level(current_level)
    next_threshold = _minimum_xp_for_level(current_level + 1)
    level_span = max(1, next_threshold - current_threshold)
    xp_in_level = max(0, total_xp - current_threshold)
    xp_in_level = min(xp_in_level, level_span)
    return {
        "level": current_level,
        "total_xp": total_xp,
        "current_threshold": current_threshold,
        "next_threshold": next_threshold,
        "xp_in_level": xp_in_level,
        "level_span": level_span,
        "xp_to_next": max(0, next_threshold - total_xp),
        "percent": int((xp_in_level / level_span) * 100) if level_span else 0,
    }


def get_level_rewards(level):
    """Return coin rewards and unlock notes for each level."""
    rewards = {
        0: {"coins": 0, "features": [], "message": "Welcome! Process documents to level up."},
        1: {"coins": 25, "features": ["Basic customization"], "message": "Level 1 reached."},
        2: {"coins": 50, "features": ["Shop access", "Inventory access"], "message": "Level 2 reached. Shop and Inventory are unlocked."},
        3: {"coins": 75, "features": ["Advanced badges"], "message": "Level 3 reached. The good shelves are opening."},
        4: {"coins": 100, "features": ["Premium themes"], "message": "Level 4 reached. Premium style unlocked."},
        5: {"coins": 150, "features": ["Elite rewards"], "message": "Level 5 reached. Elite routing energy."},
    }
    return rewards.get(
        _as_int(level),
        {
            "coins": max(25, _as_int(level) * 25),
            "features": [f"Level {level} rewards"],
            "message": f"Level {level} reached.",
        },
    )


def normalize_user_rewards(data):
    """Backfill newer reward fields while preserving old progress and unlocks."""
    data = dict(data or {})

    unlocked = []
    unlocked.extend(data.get("unlocked", []))
    unlocked.extend(data.get("inventory", []))
    unlocked.extend(data.get("purchased_rewards", []))
    unlocked = _unique_list(unlocked)

    legacy_title_equipped = None
    equipped = dict(DEFAULT_EQUIPPED)
    for source in (data.get("equipped_rewards", {}) or {}, data.get("equipped", {}) or {}):
        for reward_type, reward_id in source.items():
            if reward_type in DEFAULT_EQUIPPED:
                equipped[reward_type] = reward_id
            elif reward_type == "title":
                legacy_title_equipped = reward_id
    for reward_type in DEFAULT_EQUIPPED:
        equipped.setdefault(reward_type, None)

    custom_wallpaper = _coerce_custom_wallpaper_data(data.get("custom_wallpaper"))
    data["custom_wallpaper"] = custom_wallpaper
    has_custom_wallpaper = bool(get_custom_wallpaper_path(data))
    if has_custom_wallpaper:
        if CUSTOM_WALLPAPER_ID not in unlocked:
            unlocked.append(CUSTOM_WALLPAPER_ID)
    elif equipped.get("header") == CUSTOM_WALLPAPER_ID:
        equipped["header"] = None

    # Older builds stored buyable emoji cosmetics in the badge slot. Keep the
    # user's item equipped, but move it into the new emoji slot.
    badge_id = equipped.get("badge")
    if badge_id and REWARDS.get(badge_id, {}).get("type") == "emoji":
        equipped["emoji"] = equipped.get("emoji") or badge_id
        equipped["badge"] = None
    data["equipped"] = equipped

    total_docs = max(
        _as_int(data.get("total_documents_processed")),
        _as_int(data.get("total_documents")),
    )
    stats = dict(DEFAULT_STATS)
    stats.update(data.get("stats", {}) or {})
    stats["total_fresh_documents"] = max(_as_int(stats.get("total_fresh_documents")), total_docs)
    stats["total_runs"] = max(0, _as_int(stats.get("total_runs")))
    stats["clean_runs"] = max(0, _as_int(stats.get("clean_runs")))
    stats["best_clean_run_fresh_documents"] = max(0, _as_int(stats.get("best_clean_run_fresh_documents")))
    stats["parallel_runs"] = max(0, _as_int(stats.get("parallel_runs")))
    stats["max_parallel_routers"] = max(1, _as_int(stats.get("max_parallel_routers"), 1))
    stats["after_midnight_runs"] = max(0, _as_int(stats.get("after_midnight_runs")))
    stats["modes_completed"] = _unique_list(stats.get("modes_completed", []))
    data["stats"] = stats
    data["visual_settings"] = get_visual_settings(data)

    legacy_level = _as_int(data.get("level"))
    xp = max(
        _as_int(data.get("xp")),
        total_docs,
        _minimum_xp_for_level(legacy_level),
    )
    data["xp"] = xp
    data["coins"] = max(0, _as_int(data.get("coins")))
    data["total_documents_processed"] = stats["total_fresh_documents"]

    achievements = set(_unique_list(data.get("achievements", [])))
    achievement_reward_grants = set(_unique_list(data.get("achievement_reward_grants", [])))
    if not data.get("achievement_reward_grants"):
        achievement_reward_grants.update(achievements)
    aggregate_run = {
        "fresh_documents": 0,
        "already_processed": 0,
        "clean": False,
        "parallel_routers": stats.get("max_parallel_routers", 1),
    }
    for achievement_id in ACHIEVEMENTS:
        if not _achievement_is_met(achievement_id, stats, aggregate_run):
            continue
        was_unlocked = achievement_id in achievements
        achievements.add(achievement_id)
        if was_unlocked or achievement_id in achievement_reward_grants:
            continue
        achievement = ACHIEVEMENTS.get(achievement_id, {})
        data["coins"] += _as_int(achievement.get("coins"))
        data["xp"] += _as_int(achievement.get("xp"))
        achievement_reward_grants.add(achievement_id)
    data["achievements"] = sorted(achievements)
    data["achievement_reward_grants"] = sorted(achievement_reward_grants)
    data["level"] = calculate_level(data["xp"])

    earned_badges = set()
    for achievement_id in data["achievements"]:
        badge_reward = ACHIEVEMENTS.get(achievement_id, {}).get("badge_reward")
        if badge_reward and badge_reward in REWARDS:
            earned_badges.add(badge_reward)
            unlocked.append(badge_reward)

    filtered_unlocked = []
    for reward_id in _unique_list(unlocked):
        reward = REWARDS.get(reward_id)
        if not reward:
            continue
        required_achievement = reward.get("achievement_id")
        if reward.get("type") == "badge" and required_achievement and reward_id not in earned_badges:
            continue
        if reward_id == CUSTOM_WALLPAPER_ID and not has_custom_wallpaper:
            continue
        filtered_unlocked.append(reward_id)
    data["unlocked"] = _unique_list(filtered_unlocked)

    if legacy_title_equipped and legacy_title_equipped in data["unlocked"] and not equipped.get("badge"):
        equipped["badge"] = legacy_title_equipped
    if equipped.get("header") == CUSTOM_WALLPAPER_ID and CUSTOM_WALLPAPER_ID not in data["unlocked"]:
        equipped["header"] = None
    if equipped.get("badge") and equipped["badge"] not in data["unlocked"]:
        equipped["badge"] = None
    data["equipped"] = equipped
    data["last_run_rewards"] = data.get("last_run_rewards") or {}
    data["notified_privileges"] = _unique_list(data.get("notified_privileges", []))

    return data


def load_user_rewards():
    _ensure_public_storage_and_migrate()
    if USER_REWARDS_PATH.exists():
        try:
            with open(USER_REWARDS_PATH, "r", encoding="utf-8") as handle:
                return normalize_user_rewards(json.load(handle))
        except Exception as exc:
            logging.warning(f"Failed loading user rewards; using defaults: {exc}")
    return normalize_user_rewards({})


def save_user_rewards(user_data):
    _ensure_public_storage_and_migrate()
    USER_REWARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_user_rewards(_preserve_existing_rewards_if_better(user_data))
    with open(USER_REWARDS_PATH, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2)
    return normalized


def reset_user_rewards():
    _ensure_public_storage_and_migrate()
    data = normalize_user_rewards({})
    with open(USER_REWARDS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return data


def get_reward_display_name(reward_id, reward=None):
    reward = reward or REWARDS.get(reward_id, {})
    return str(reward.get("display_name") or reward.get("name") or reward_id)


def get_reward_type_label(reward_type, plural=False):
    """Return user-facing reward type language for legacy internal keys."""
    singular, plural_label = REWARD_TYPE_LABELS.get(
        str(reward_type or ""),
        ("Item", "Items"),
    )
    return plural_label if plural else singular


def get_reward_icon(reward_id, reward=None):
    reward = reward or REWARDS.get(reward_id, {})
    return str(reward.get("emoji") or "").strip()


def get_reward_image_filename(reward_id, reward=None):
    reward = reward or REWARDS.get(reward_id, {})
    return reward.get("image")


def is_reward_purchasable(reward):
    """Return whether a reward can be bought or claimed from the shop."""
    return bool((reward or {}).get("purchasable", True))


def _unlock_xp_privileges(user_data):
    """Return newly available XP-gated shop privileges and mark them notified."""
    notified = set(_unique_list(user_data.get("notified_privileges", [])))
    unlocked_rewards = set(user_data.get("unlocked", []))
    new_privileges = []
    total_xp = _as_int(user_data.get("xp"))

    for reward_id, reward in REWARDS.items():
        required_xp = _as_int(reward.get("required_xp"))
        if required_xp <= 0:
            continue
        if reward_id in unlocked_rewards:
            notified.add(reward_id)
            continue
        if reward_id in notified or total_xp < required_xp:
            continue

        notified.add(reward_id)
        new_privileges.append({
            "reward_id": reward_id,
            "name": get_reward_display_name(reward_id, reward),
            "required_xp": required_xp,
            "message": reward.get("unlock_message", ""),
        })

    user_data["notified_privileges"] = sorted(notified)
    return new_privileges


def get_equipped_title(user_data=None):
    data = normalize_user_rewards(user_data or load_user_rewards())
    title_id = data.get("equipped", {}).get("title")
    if not title_id:
        return ""
    return get_reward_display_name(title_id)


def _is_clean_run(error_count, timeout_count):
    return _as_int(error_count) == 0 and _as_int(timeout_count) == 0


def _is_after_midnight(now):
    return 0 <= now.hour < 6


def _requirement_count(requirement):
    return max(0, _as_int((requirement or {}).get("count")))


def format_achievement_requirement(achievement):
    """Return a readable requirement line for tooltips, reports, and docs."""
    requirement = (achievement or {}).get("requirement") or {}
    count = _requirement_count(requirement)
    requirement_type = requirement.get("type")

    if requirement_type == "total_fresh_documents":
        return f"Reach {count:,} total fresh routed document{'s' if count != 1 else ''}."
    if requirement_type == "clean_runs":
        return f"Complete {count:,} clean routing run{'s' if count != 1 else ''}."
    if requirement_type == "parallel_runs":
        return f"Complete {count:,} fresh parallel-router run{'s' if count != 1 else ''}."
    if requirement_type == "max_parallel_routers":
        return f"Run with {count:,} parallel router{'s' if count != 1 else ''}."
    if requirement_type == "single_clean_run_fresh_documents":
        return f"Route at least {count:,} fresh documents in one clean run."
    if requirement_type == "modes_completed":
        return f"Complete fresh runs in {count:,} different autorouter mode{'s' if count != 1 else ''}."
    if requirement_type == "after_midnight_runs":
        return f"Complete {count:,} fresh routing run{'s' if count != 1 else ''} after midnight."
    return str((achievement or {}).get("description") or "Complete the required routing milestone.")


def _requirement_is_met(requirement, stats, current_run):
    requirement = requirement or {}
    requirement_type = requirement.get("type")
    count = _requirement_count(requirement)
    fresh_documents = _as_int((current_run or {}).get("fresh_documents"))
    is_clean = bool((current_run or {}).get("clean"))

    if requirement_type == "total_fresh_documents":
        return _as_int(stats.get("total_fresh_documents")) >= count
    if requirement_type == "clean_runs":
        return _as_int(stats.get("clean_runs")) >= count
    if requirement_type == "parallel_runs":
        return _as_int(stats.get("parallel_runs")) >= count
    if requirement_type == "max_parallel_routers":
        return _as_int(stats.get("max_parallel_routers"), 1) >= count
    if requirement_type == "single_clean_run_fresh_documents":
        best_clean_run = max(
            _as_int(stats.get("best_clean_run_fresh_documents")),
            fresh_documents if is_clean else 0,
        )
        return best_clean_run >= count
    if requirement_type == "modes_completed":
        return len(_unique_list(stats.get("modes_completed", []))) >= count
    if requirement_type == "after_midnight_runs":
        return _as_int(stats.get("after_midnight_runs")) >= count
    return False


def _achievement_is_met(achievement_id, stats, current_run):
    achievement = ACHIEVEMENTS.get(achievement_id, {})
    requirement = achievement.get("requirement")
    if requirement:
        return _requirement_is_met(requirement, stats or {}, current_run or {})

    fresh_documents = _as_int(current_run.get("fresh_documents"))
    is_clean = bool(current_run.get("clean"))
    parallel_routers = _as_int(current_run.get("parallel_routers"), 1)

    if achievement_id == "first_route":
        return _as_int(stats.get("total_fresh_documents")) >= 1
    if achievement_id == "clean_sweep":
        return _as_int(stats.get("clean_runs")) >= 1
    if achievement_id == "parallel_boss":
        return _as_int(stats.get("parallel_runs")) >= 1
    if achievement_id == "full_bench":
        return _as_int(stats.get("max_parallel_routers"), 1) >= 6
    if achievement_id == "no_misses_25":
        return fresh_documents >= 25 and is_clean
    if achievement_id == "hundred_club":
        return _as_int(stats.get("total_fresh_documents")) >= 100
    if achievement_id == "court_hopper":
        return len(stats.get("modes_completed", [])) >= 3
    if achievement_id == "night_shift_legend":
        return _as_int(stats.get("after_midnight_runs")) >= 1
    if achievement_id == "lni_whisperer":
        return _as_int(stats.get("total_fresh_documents")) >= 25
    if achievement_id == "docket_diva":
        return len(stats.get("modes_completed", [])) >= 2
    if achievement_id == "queue_slayer":
        return _as_int(stats.get("total_fresh_documents")) >= 250
    if achievement_id == "archive_authority":
        return _as_int(stats.get("clean_runs")) >= 10
    if achievement_id == "final_reviewer":
        return _as_int(stats.get("total_fresh_documents")) >= 500
    if achievement_id == "six_router_menace":
        return _as_int(stats.get("max_parallel_routers"), 1) >= 6
    return parallel_routers > 999999


def _unlock_achievements(user_data, current_run):
    unlocked = set(user_data.get("achievements", []))
    unlocked_rewards = set(user_data.get("unlocked", []))
    achievement_reward_grants = set(_unique_list(user_data.get("achievement_reward_grants", [])))
    new_achievements = []
    stats = user_data.get("stats", {})

    for achievement_id, achievement in ACHIEVEMENTS.items():
        if achievement_id in unlocked:
            continue
        if not _achievement_is_met(achievement_id, stats, current_run):
            continue
        unlocked.add(achievement_id)
        badge_reward = achievement.get("badge_reward")
        if badge_reward and badge_reward in REWARDS:
            unlocked_rewards.add(badge_reward)
        achievement_reward_grants.add(achievement_id)
        new_achievements.append({
            "id": achievement_id,
            "name": achievement["name"],
            "coins": _as_int(achievement.get("coins")),
            "xp": _as_int(achievement.get("xp")),
            "badge_reward": badge_reward,
            "badge_name": get_reward_display_name(badge_reward) if badge_reward else "",
        })

    user_data["achievements"] = sorted(unlocked)
    user_data["unlocked"] = sorted(unlocked_rewards)
    user_data["achievement_reward_grants"] = sorted(achievement_reward_grants)
    return new_achievements


def award_run_rewards(user_data, fresh_documents, already_processed=0, error_count=0, timeout_count=0,
                      mode=None, parallel_routers=1, now=None, persist=True):
    """Apply XP, coins, level rewards, and achievements for a completed run."""
    now = now or _datetime.datetime.now()
    data = normalize_user_rewards(user_data)
    old_level = data.get("level", 0)

    fresh_documents = max(0, _as_int(fresh_documents))
    already_processed = max(0, _as_int(already_processed))
    error_count = max(0, _as_int(error_count))
    timeout_count = max(0, _as_int(timeout_count))
    parallel_routers = max(1, _as_int(parallel_routers, 1))
    clean = _is_clean_run(error_count, timeout_count)

    xp_earned = fresh_documents
    coins_earned = fresh_documents
    bonuses = []
    medals = []

    if fresh_documents == 0 and already_processed > 0:
        medals.append("No New Routing")

    if fresh_documents <= 0:
        summary = {
            "fresh_documents": 0,
            "already_processed": already_processed,
            "xp_earned": 0,
            "coins_earned": 0,
            "bonuses": [],
            "medals": _unique_list(medals),
            "new_achievements": [],
            "new_privileges": [],
            "old_level": old_level,
            "new_level": data.get("level", old_level),
            "level_rewards": [],
            "total_xp": data.get("xp", 0),
            "total_coins": data.get("coins", 0),
        }
        data["last_run_rewards"] = summary
        return summary

    if fresh_documents > 0:
        medals.append("Fresh Batch")

    if fresh_documents > 0 and clean:
        bonuses.append({"name": "Clean Sweep bonus", "xp": 5, "coins": 10})
        medals.append("Clean Sweep")

    if fresh_documents >= 25 and clean:
        bonuses.append({"name": "No Misses bonus", "xp": 10, "coins": 15})
        medals.append("No Misses")

    if parallel_routers >= 2 and fresh_documents > 0:
        bonuses.append({"name": "Parallel Router bonus", "xp": 5, "coins": 5})
        medals.append("Parallel Boss" if parallel_routers < 6 else "Full Bench")
        if parallel_routers >= 6:
            bonuses.append({"name": "Full Bench bonus", "xp": 10, "coins": 10})

    if _is_after_midnight(now) and fresh_documents > 0:
        bonuses.append({"name": "Night Shift bonus", "xp": 5, "coins": 5})
        medals.append("Night Shift Legend")

    for bonus in bonuses:
        xp_earned += _as_int(bonus.get("xp"))
        coins_earned += _as_int(bonus.get("coins"))

    stats = data["stats"]
    stats["total_runs"] = _as_int(stats.get("total_runs")) + 1
    stats["total_fresh_documents"] = _as_int(stats.get("total_fresh_documents")) + fresh_documents
    if fresh_documents > 0 and clean:
        stats["clean_runs"] = _as_int(stats.get("clean_runs")) + 1
        stats["best_clean_run_fresh_documents"] = max(
            _as_int(stats.get("best_clean_run_fresh_documents")),
            fresh_documents,
        )
    if parallel_routers >= 2 and fresh_documents > 0:
        stats["parallel_runs"] = _as_int(stats.get("parallel_runs")) + 1
    stats["max_parallel_routers"] = max(_as_int(stats.get("max_parallel_routers"), 1), parallel_routers)
    if _is_after_midnight(now) and fresh_documents > 0:
        stats["after_midnight_runs"] = _as_int(stats.get("after_midnight_runs")) + 1
    if mode and fresh_documents > 0:
        modes = set(stats.get("modes_completed", []))
        modes.add(str(mode).lower())
        stats["modes_completed"] = sorted(modes)

    current_run = {
        "fresh_documents": fresh_documents,
        "already_processed": already_processed,
        "clean": clean,
        "parallel_routers": parallel_routers,
    }
    new_achievements = _unlock_achievements(data, current_run)
    for achievement in new_achievements:
        xp_earned += _as_int(achievement.get("xp"))
        coins_earned += _as_int(achievement.get("coins"))

    data["xp"] = _as_int(data.get("xp")) + xp_earned
    data["coins"] = _as_int(data.get("coins")) + coins_earned
    data["total_documents_processed"] = stats["total_fresh_documents"]
    data["level"] = calculate_level(data["xp"])
    new_privileges = _unlock_xp_privileges(data)

    level_rewards = []
    for level in range(old_level + 1, data["level"] + 1):
        reward = get_level_rewards(level)
        coins = _as_int(reward.get("coins"))
        data["coins"] += coins
        level_rewards.append({
            "level": level,
            "coins": coins,
            "message": reward.get("message", ""),
            "features": reward.get("features", []),
        })

    summary = {
        "fresh_documents": fresh_documents,
        "already_processed": already_processed,
        "xp_earned": xp_earned,
        "coins_earned": coins_earned,
        "bonuses": bonuses,
        "medals": _unique_list(medals),
        "new_achievements": new_achievements,
        "new_privileges": new_privileges,
        "old_level": old_level,
        "new_level": data["level"],
        "level_rewards": level_rewards,
        "total_xp": data["xp"],
        "total_coins": data["coins"],
    }
    data["last_run_rewards"] = summary

    if persist:
        save_user_rewards(data)
    return summary


def format_reward_summary(summary):
    """Return compact HTML for the post-run reward popup."""
    summary = summary or {}
    fresh = _as_int(summary.get("fresh_documents"))
    xp = _as_int(summary.get("xp_earned"))
    coins = _as_int(summary.get("coins_earned"))
    achievements = summary.get("new_achievements") or []
    privileges = summary.get("new_privileges") or []
    medals = summary.get("medals") or []
    level_rewards = summary.get("level_rewards") or []

    if fresh <= 0 and xp <= 0 and coins <= 0 and not achievements and not privileges and not level_rewards:
        return (
            "<div style='text-align:center;'>"
            "<span style='font-size:18px; font-weight:bold; color:#FFFFFF;'>No fresh rewards this run</span><br>"
            "<span style='font-size:13px; color:#DDDDDD;'>Already handled rows stayed safely out of the way.</span>"
            "</div>"
        )

    lines = [
        "<div style='text-align:center;'>",
        "<span style='font-size:26px; font-weight:bold; color:#FFD700;'>Run Rewards</span><br>",
        f"<span style='font-size:18px; color:#FFFFFF;'>+{xp} XP | +{coins} coins</span><br>",
    ]

    if medals:
        lines.append(f"<span style='font-size:13px; color:#BDF7FF;'>Medals: {', '.join(medals[:3])}</span><br>")
    if achievements:
        names = ", ".join(item["name"] for item in achievements[:3])
        lines.append(f"<span style='font-size:13px; color:#C7F464;'>New achievement: {names}</span><br>")
        badge_names = [item.get("badge_name") for item in achievements if item.get("badge_name")]
        if badge_names:
            lines.append(f"<span style='font-size:13px; color:#FFD700;'>Badge unlocked: {', '.join(badge_names[:3])}</span><br>")
    if privileges:
        privilege_names = ", ".join(item["name"] for item in privileges[:3])
        lines.append(f"<span style='font-size:13px; color:#9FE7E5;'>New privilege: {privilege_names} is now claimable in the Shop.</span><br>")
    if level_rewards:
        highest_level = max(item["level"] for item in level_rewards)
        lines.append(f"<span style='font-size:13px; color:#FFB6F2;'>Level up: Level {highest_level}</span><br>")

    lines.append("</div>")
    return "".join(lines)


_ensure_public_storage_and_migrate()
