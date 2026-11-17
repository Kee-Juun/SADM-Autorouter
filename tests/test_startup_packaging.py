import unittest

from tools.startup_packaging import filter_foreign_windows_icu


class StartupPackagingTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            ('icuuc.dll', r'C:\tools\poppler\icuuc.dll', 'BINARY'),
            ('icudt78.dll', r'C:\tools\poppler\icudt78.dll', 'BINARY'),
            ('PyQt6/Qt6/bin/Qt6Core.dll', r'C:\python\PyQt6\Qt6Core.dll', 'BINARY'),
            ('icuuc72.dll', r'C:\python\Qt6\icuuc72.dll', 'BINARY'),
            ('icudt72.dll', r'C:\python\Qt6\icudt72.dll', 'BINARY'),
        ]

    def test_windows_icu_cannot_be_shadowed_by_poppler_on_path(self):
        result = filter_foreign_windows_icu(self.entries, use_windows_icu=True)
        self.assertEqual(result, self.entries[2:])

    def test_a_qt_wheel_with_its_own_icu_keeps_its_dependencies(self):
        self.assertEqual(filter_foreign_windows_icu(self.entries, use_windows_icu=False), self.entries)

    def test_no_unversioned_icu_does_not_strip_other_runtime_data(self):
        entries = self.entries[1:]
        self.assertEqual(filter_foreign_windows_icu(entries, use_windows_icu=True), entries)


if __name__ == '__main__':
    unittest.main()
