import datetime
import unittest
from unittest.mock import Mock, PropertyMock, patch

import pandas as pd
from selenium.common.exceptions import NoAlertPresentException

from core.smducar_router import CaseLawRouter


class IRTDecisionDateTests(unittest.TestCase):
    DATE_XPATH = '//*[@id="decisionDate"]'

    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock()
        self.router.long_wait = Mock()
        self.field = Mock()
        self.field.is_enabled.return_value = True
        self.current_value = ""
        self.field.get_attribute.side_effect = lambda name: self.current_value if name == "value" else None
        self.router.long_wait.until.return_value = self.field
        alert = patch.object(type(self.router.driver.switch_to), "alert", new_callable=PropertyMock, create=True)
        alert.start().side_effect = NoAlertPresentException()
        self.addCleanup(alert.stop)

    def test_mapping_dates_are_normalized_to_month_day_year(self):
        for value in (
            "10/22/2026", "10-22-2026", "2026-10-22", "2026/10/22", "10/22/26", " 10/22/2026 ",
            datetime.date(2026, 10, 22), datetime.datetime(2026, 10, 22, 15, 30), pd.Timestamp("2026-10-22"),
        ):
            with self.subTest(value=value):
                self.assertEqual(self.router.normalize_mapping_decision_date(value), "10-22-2026")
        self.assertEqual(self.router.normalize_mapping_decision_date("1/2/2026"), "01-02-2026")

    def test_missing_dates_remain_missing_without_fabricating_a_fallback(self):
        for value in (None, "", " ", float("nan"), pd.NaT, "NaT", "None", "nan"):
            with self.subTest(value=value):
                self.assertIsNone(self.router.normalize_mapping_decision_date(value))

    def test_unrecognized_or_invalid_dates_are_not_guessed(self):
        for value in ("not a date", "02/30/2026", "13/22/2026"):
            with self.subTest(value=value):
                self.assertEqual(self.router.normalize_mapping_decision_date(value), value)

    def test_same_day_in_different_formats_is_never_cleared_or_retyped(self):
        for existing, requested in (
            ("10-22-2026", "10/22/2026"),
            ("10/22/2026", "10-22-2026"),
            ("2026-10-22", "10/22/2026"),
            ("10-22-2026", datetime.datetime(2026, 10, 22)),
            ("01-02-2026", "1/2/2026"),
            (" 10/22/2026 ", "10-22-2026"),
        ):
            with self.subTest(existing=existing, requested=requested):
                self.current_value = existing
                self.field.clear.reset_mock()
                self.field.send_keys.reset_mock()
                self.router.safe_fill_field(self.DATE_XPATH, requested, "Decision Date")
                self.field.clear.assert_not_called()
                self.field.send_keys.assert_not_called()
                self.field.click.assert_not_called()

    def test_blank_date_is_filled_in_irt_format(self):
        for value in ("10/22/2026", "2026-10-22", datetime.date(2026, 10, 22)):
            with self.subTest(value=value):
                self.field.clear.reset_mock()
                self.field.send_keys.reset_mock()
                self.router.safe_fill_field(self.DATE_XPATH, value, "Decision Date")
                self.field.clear.assert_called_once()
                self.field.send_keys.assert_called_once_with("10-22-2026")

    def test_genuinely_different_date_is_updated(self):
        self.current_value = "10-21-2026"
        self.router.safe_fill_field(self.DATE_XPATH, "10/22/2026", "Decision Date")
        self.field.clear.assert_called_once()
        self.field.send_keys.assert_called_once_with("10-22-2026")

    def test_missing_requested_date_does_not_erase_existing_irt_date(self):
        self.current_value = "10-22-2026"
        self.router.safe_fill_field(self.DATE_XPATH, None, "Decision Date")
        self.field.clear.assert_not_called()
        self.field.send_keys.assert_not_called()

    def test_non_date_fields_do_not_receive_date_formatting(self):
        self.router.safe_fill_field('//*[@id="docketNumber"]', "10/22/2026", "Docket Number")
        self.field.send_keys.assert_called_once_with("10/22/2026")

    def test_disabled_date_is_not_changed(self):
        self.field.is_enabled.return_value = False
        self.router.safe_fill_field(self.DATE_XPATH, "10/22/2026", "Decision Date")
        self.field.clear.assert_not_called()
        self.field.send_keys.assert_not_called()

    def test_readonly_date_is_not_changed(self):
        self.field.get_attribute.side_effect = lambda name: "true" if name == "readonly" else "10-21-2026"
        self.router.safe_fill_field(self.DATE_XPATH, "10/22/2026", "Decision Date")
        self.field.clear.assert_not_called()
        self.field.send_keys.assert_not_called()

    def test_counsel_still_uses_main_opinions_date_even_when_it_is_text(self):
        df = pd.DataFrame([
            {"FileName": "LDC_SMD_SC101636_E2E.pdf", "Decision Date": "9/29/2026"},
            {"FileName": "LDC_SMD_SC101636counsel_E2E.pdf", "Decision Date": "9/30/2026"},
        ])
        result = self.router.find_main_opinion_date_for_counsel(
            "SC101636", "LDC_SMD_SC101636counsel_E2E.pdf", full_df=df,
        )
        self.assertEqual(result, "09-29-2026")


if __name__ == "__main__":
    unittest.main()
