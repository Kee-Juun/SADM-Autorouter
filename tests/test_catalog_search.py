import unittest
from utils.catalog_search import rank_catalog


class CatalogSearchTests(unittest.TestCase):
    ENTRIES = [
        ('ocean', {'name': 'Ocean Glass', 'type': 'skin', 'description': 'Blue and teal colours.'}),
        ('moon', {'name': 'Moonlit Archive', 'type': 'header', 'description': 'A quiet night sky.'}),
        ('type', {'name': 'Dark Reborn', 'type': 'font', 'description': 'Angular lettering.'}),
        ('precision', {'name': 'Precision Streak Frost', 'type': 'badge', 'description': 'Complete 5 clean runs.'}),
    ]

    def ids(self, query, entries=None):
        return [key for key, _ in rank_catalog(query, self.ENTRIES if entries is None else entries)]

    def test_partial_words_and_multiword_fragments(self):
        self.assertEqual(self.ids('OCE gla'), ['ocean'])
        self.assertEqual(self.ids('preci fro'), ['precision'])

    def test_category_synonyms_and_description_terms(self):
        self.assertEqual(self.ids('background'), ['moon'])
        self.assertEqual(self.ids('typeface'), ['type'])
        self.assertEqual(self.ids('badge clean'), ['precision'])

    def test_small_typo_is_tolerated(self):
        self.assertEqual(self.ids('wallpapr'), ['moon'])

    def test_all_keywords_are_required(self):
        self.assertEqual(self.ids('ocean badge'), [])
        self.assertEqual(self.ids('not-found-xyz'), [])

    def test_exact_names_rank_before_description_matches(self):
        extra = ('other', {'name': 'Other Theme', 'type': 'skin', 'description': 'Inspired by Ocean Glass.'})
        self.assertEqual(self.ids('Ocean Glass', [extra] + self.ENTRIES)[0], 'ocean')

    def test_search_cannot_return_items_outside_supplied_inventory(self):
        self.assertEqual(self.ids('Moon', self.ENTRIES[:1]), [])
        self.assertEqual(self.ids(''), [])


if __name__ == '__main__':
    unittest.main()
