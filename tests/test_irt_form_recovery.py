import unittest
from unittest.mock import Mock, patch

from core.smducar_config import status_updates_buffer
from core.smducar_router import CaseLawRouter


class IRTFormRecoveryTests(unittest.TestCase):
    def setUp(self):
        status_updates_buffer.clear()

    def tearDown(self):
        status_updates_buffer.clear()

    def test_main_terminal_status_stops_fill_before_form_checks(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.prepare_common_fields = Mock()
        router.handle_any_alert = Mock()
        router.handle_main_opinion_fields = Mock(return_value="RELATED LNI ATTACH FAILED")

        row = {"FileName": "MOSU00_123.pdf", "LNI": "6KMY-TEST"}
        with patch("core.smducar_router.is_counsel", return_value=False):
            result = router.fill_irt_form(row, {}, 0, "sample.pdf")

        self.assertEqual(result, "RELATED LNI ATTACH FAILED")
        router.handle_main_opinion_fields.assert_called_once()

    def test_failed_related_attachment_does_not_close_the_irt_tab(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.wait = Mock()
        router.wait.until.side_effect = Exception("case name intentionally unavailable")
        router.click_element = Mock()
        router.handle_related_ln_is = Mock(return_value=False)
        router.driver = Mock()
        row = {"FileName": "MOSU00_123.pdf", "LNI": "6KMY-TEST"}
        status_updates_buffer[4] = "RELATED LNI ATTACH FAILED"

        result = router.handle_main_opinion_fields(row, {}, 4, "sample.pdf")

        self.assertEqual(result, "RELATED LNI ATTACH FAILED")
        router.driver.close.assert_not_called()

    def test_mosu_save_does_not_click_when_the_dialog_is_gone(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.clear_mosu00_duplicate_dialog_before_table_save = Mock()
        router.wait_for_mosu00_table_case_spinner = Mock()
        router.is_mosu00_table_case_form_visible = Mock(return_value=False)
        router.click_mosu00_table_save_with_dom_fallback = Mock()

        self.assertFalse(router.click_mosu00_table_case_save_button())
        router.click_mosu00_table_save_with_dom_fallback.assert_not_called()

    def test_mosu_save_uses_dom_fallback_when_dialog_is_visible(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.clear_mosu00_duplicate_dialog_before_table_save = Mock()
        router.wait_for_mosu00_table_case_spinner = Mock()
        router.is_mosu00_table_case_form_visible = Mock(return_value=True)
        router.click_mosu00_table_save_with_dom_fallback = Mock(return_value=True)

        self.assertTrue(router.click_mosu00_table_case_save_button())
        router.click_mosu00_table_save_with_dom_fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
