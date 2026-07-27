import json
import os
from pathlib import Path
import logging

REWARDS = {
    "mochi_wall": {
        "type": "wallpaper",
        "name": "Mochi",
        "price": 850,
        "preview": None,
        "description": "Sunshine-colored sass with a royal streak. Mochi thrives in chaos, knocks over your drink, then blinks like it’s your fault. She's perfect, obviously."
    },
    "nana_wall": {
        "type": "wallpaper",
        "name": "Nana",
        "price": 350,
        "preview": None,
        "description": "Sleepy, snuggly, and retired from all responsibilities. Nana dreams of fish, naps, and a world without vacuum cleaners."
    },
    "amber_wall": {
        "type": "wallpaper",
        "name": "Amber",
        "price": 550,
        "preview": None,
        "description": "She’s classy, sassy, and glows like a warm autumn day. Amber acts like she runs the place—because, well, she does."
    },
    "cookie_wall": {
        "type": "wallpaper",
        "name": "Cookie",
        "price": 750,
        "preview": None,
        "description": "A disgruntled sock thief with a face like Monday morning. Cookie has big ‘I didn’t sign up for this’ energy, and we respect that."
    },
    "luna_wall": {
        "type": "wallpaper",
        "name": "Luna",
        "price": 650,
        "preview": None,
        "description": "Mysterious, dramatic, and 100% convinced she’s a moon goddess. Luna only appears when the vibes are right (and there's tuna)."
    },
    "badge_emoji_fire": {
        "type": "badge",
        "name": "🔥 Fire Badge",
        "price": 350,
        "preview": None,
        "description": "Operating at 200%, smiling through the blaze. Everything’s on fire, but somehow it’s working. Might be a crisis. Might be a breakthrough. No one’s sure."
    },
    "badge_emoji_cool": {
        "type": "badge",
        "name": "😎 Cool Badge",
        "price": 400,
        "preview": None,
        "description": "Comes in late, nails the presentation, leaves with iced coffee and zero explanation. Cool under pressure, allergic to drama, and 87% done with everyone."
    },
    "badge_emoji_heart": {
        "type": "badge",
        "name": "💜 Purple Heart Badge",
        "price": 150,
        "preview": None,
        "description": "Emotionally stable. Probably. Has strong opinions about font choices and stronger opinions about team synergy. Will hype you up, fix your slide deck, and guilt-trip you into drinking water."
    },
    "badge_emoji_tongue": {
        "type": "badge",
        "name": "😛 Tongue Out Badge",
        "price": 100,
        "preview": None,
        "description": "Chaotic good in human form. Brings snacks, makes jokes, somehow still meets deadlines. Unfiltered. Unbothered. Unemployed? Not yet."
    },
    "badge_emoji_thumbs_up": {
        "type": "badge",
        "name": "👍 Thumbs Up Badge",
        "price": 100,
        "preview": None,
        "description": "Communicates exclusively through reaction emojis and ironic enthusiasm. Everything's fine. Probably."
    },
    "badge_emoji_heart_eyes": {
        "type": "badge",
        "name": "😍 Heart Eyes Badge",
        "price": 150,
        "preview": None,
        "description": "Falls in love with good fonts, free food, and people who send calendar invites properly. Expressive, extra, and excellent."
    },
    "badge_emoji_flex": {
        "type": "badge",
        "name": "💪 Flexing Arm Badge",
        "price": 120,
        "preview": None,
        "description": "Too strong for this job. Has carried entire teams and several group chats. Might be tired, but looks great doing it."
    },
    "badge_emoji_rock": {
        "type": "badge",
        "name": "🤘 Rockstar Badge",
        "price": 250,
        "preview": None,
        "description": "One spreadsheet away from quitting and starting a band. Loud, legendary, and weirdly productive after 4 PM."
    },
    "badge_emoji_red_heart": {
        "type": "badge",
        "name": "❤️ Red Heart Badge",
        "price": 600,
        "preview": None,
        "description": "Corporate romantic. Says 'love this!' in comments and means it. Powered by passion, caffeine, and a tiny bit of delusion."
    },
    "badge_emoji_green_heart": {
        "type": "badge",
        "name": "💚 Green Heart Badge",
        "price": 120,
        "preview": None,
        "description": "Soft on the outside, spreadsheets on the inside. Calm, collected, but will fight for office plants and lunch breaks with equal passion."
    },
    "badge_emoji_heart_eyes_cat": {
        "type": "badge",
        "name": "😻 Heart Eyes Cat Badge",
        "price": 350,
        "preview": None,
        "description": "Lurks in the background until it’s time to shine. Equal parts adorable and unhinged. Doesn’t ask for attention—steals it with sparkle and spreadsheets."
    },
    "badge_emoji_nails": {
        "type": "badge",
        "name": "💅 Sassy Nails Badge",
        "price": 450,
        "preview": None,
        "description": "Emails like a professional, lives like a drama. Deadlines fear them. So do passive-aggressive coworkers."
    },
    "game_tetris": {
        "type": "game",
        "name": "Tetris Game",
        "price": 1000,
        "preview": None,
        "description": "Classic block-dropping game that turns your five-minute break into a high-stakes battle against gravity and poor decisions. Still oddly satisfying after all these years."
    },
    # Add more rewards as needed
}

# Public, version-resilient storage location
PUBLIC_ACH_DIR = Path(os.environ.get("PUBLIC", r"C:\\Users\\Public")) / "ach"
LEGACY_REWARDS_PATH = Path("config/user_rewards.json")
USER_REWARDS_PATH = PUBLIC_ACH_DIR / "user_rewards.json"


def _ensure_public_storage_and_migrate() -> None:
    """Ensure public storage exists and migrate legacy rewards file once.

    Migration strategy:
    - If legacy file exists and public file does not, move legacy file to public path.
    - Always ensure the public directory exists.
    """
    try:
        PUBLIC_ACH_DIR.mkdir(parents=True, exist_ok=True)
        if LEGACY_REWARDS_PATH.exists() and not USER_REWARDS_PATH.exists():
            LEGACY_REWARDS_PATH.replace(USER_REWARDS_PATH)
    except Exception as exc:
        logging.warning(f"Failed preparing public rewards storage: {exc}")


# Prepare storage and migrate on import so all subsequent calls use public path
_ensure_public_storage_and_migrate()

def calculate_level(total_documents):
    """Calculate level based on total documents processed"""
    return total_documents // 50

def get_level_rewards(level):
    """Get rewards for reaching a specific level"""
    rewards = {
        0: {"coins": 0, "features": [], "message": "Welcome! Process documents to level up!"},
        1: {"coins": 25, "features": ["Basic customization"], "message": "Level 1! You unlocked basic customization!"},
        2: {"coins": 50, "features": ["Shop access"], "message": "Level 2! Shop is now unlocked!"},
        3: {"coins": 75, "features": ["Advanced rewards"], "message": "Level 3! Advanced features unlocked!"},
        4: {"coins": 100, "features": ["Premium rewards"], "message": "Level 4! Premium features unlocked!"},
        5: {"coins": 150, "features": ["Elite rewards"], "message": "Level 5! Elite features unlocked!"},
    }
    return rewards.get(level, {"coins": level * 25, "features": [f"Level {level} rewards"], "message": f"Level {level}! New rewards unlocked!"})

def load_user_rewards():
    if USER_REWARDS_PATH.exists():
        with open(USER_REWARDS_PATH, "r") as f:
            data = json.load(f)
            return data
    # Default structure for production users - start from scratch
    default_data = {
        "coins": 0,  # Production users start with 0 coins
        "level": 0,
        "total_documents_processed": 0,
        "unlocked": [],
        "equipped": {"skin": None, "header": None, "badge": None, "game": None}
    }
    return default_data

def save_user_rewards(user_data):
    USER_REWARDS_PATH.parent.mkdir(exist_ok=True)
    with open(USER_REWARDS_PATH, "w") as f:
        json.dump(user_data, f, indent=2)

def reset_user_rewards():
    data = {
        "coins": 0,  # Production reset - start from scratch
        "level": 0,
        "total_documents_processed": 0,
        "unlocked": [],
        "equipped": {"skin": None, "header": None, "badge": None, "game": None}
    }
    with open(USER_REWARDS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return data 