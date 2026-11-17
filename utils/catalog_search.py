"""Small local search index for the Shop and owned Inventory."""
from difflib import SequenceMatcher
import re
import unicodedata

CATEGORY_LABELS = {
    'skin': 'Themes', 'header': 'Wallpapers', 'font': 'Fonts',
    'emoji': 'Emojis', 'badge': 'Achievement Badges', 'game': 'Games',
}
CATEGORY_HINTS = {
    'skin': 'Theme skin colour color palette appearance',
    'header': 'Wallpaper background backdrop image picture',
    'font': 'Font typeface typography lettering text',
    'emoji': 'Emoji emoticon expression face',
    'badge': 'Achievement badge award medal crest title',
    'game': 'Game play puzzle arcade',
}


def search_text(value):
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def rank_catalog(query, entries):
    """Match all partial keywords, with a cautious fallback for small typos."""
    query = search_text(query)
    if not query:
        return []
    terms = query.split()
    found = []
    for index, (reward_id, reward) in enumerate(entries):
        name = search_text(reward.get('display_name') or reward.get('name'))
        category = search_text(CATEGORY_LABELS.get(reward.get('type'), ''))
        haystack = search_text(' '.join((name, category, CATEGORY_HINTS.get(reward.get('type'), ''),
                                        reward_id, reward.get('description', ''))))
        words = haystack.split()
        fuzzy = 0
        for term in terms:
            if term in haystack:
                continue
            if len(term) < 4 or not any(
                    word[0] == term[0] and abs(len(word) - len(term)) <= 2
                    and SequenceMatcher(None, term, word).ratio() >= .78 for word in words):
                break
            fuzzy += 1
        else:
            score = (1000 if name == query else 600 if name.startswith(query) else 350 if query in name else 0)
            score += sum(100 if term in name else 35 if term in category else 5 for term in terms)
            score -= fuzzy * 80
            found.append((-score, index, reward_id, reward))
    found.sort(key=lambda match: (match[0], match[1]))
    return [(reward_id, reward) for _, _, reward_id, reward in found]
