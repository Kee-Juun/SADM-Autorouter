from html.parser import HTMLParser
import unittest
from unittest.mock import Mock, patch

from core.critical_error_notifier import (
    _build_success_email_body, _build_critical_email_body, _render_email_html,
    _send_outlook_email, _email_signature,
    _attachment_line, REPORT_ATTACHMENT_LINES, SUCCESS_SUBJECTS,
)


class EmailMarkup(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.text = []
        self.elements = []
        self._stack = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        parent = self._stack[-1] if self._stack else None
        node = {"tag": tag, "attrs": dict(attrs), "parent": parent, "children": []}
        self.elements.append(node)
        if parent is not None:
            parent["children"].append(node)
        if tag not in {"br", "meta", "hr", "img", "link", "input"}:
            self._stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self._stack)-1, -1, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data):
        self.text.append(data)


class EmailHTMLTests(unittest.TestCase):
    def test_tables_have_outlook_cell_spacing_before_and_after_them(self):
        body = (
            "Hi Kevin,\n\nRun Results:\n- Total Routed: 24\nA note directly after the table.\n\n"
            "More Details:\n- Already Processed: 2\n\nSuggested Next Steps:\n1. Review the sheet.\n\nThanks,"
        )
        parsed = EmailMarkup(_render_email_html(body))
        tables = [node for node in parsed.elements
                  if node['tag'] == 'table' and node['attrs'].get('aria-label') == 'Report details']
        self.assertEqual(len(tables), 2)
        for table in tables:
            cell = table['parent']
            self.assertEqual(cell['tag'], 'td')
            self.assertIn('padding:0 0 20px;', cell['attrs']['style'])
            row = cell['parent']
            siblings = [node for node in row['parent']['children'] if node['tag'] == 'tr']
            position = next(i for i, node in enumerate(siblings) if node is row)
            preceding_cell = siblings[position-1]['children'][0]
            self.assertIn('padding:0 0 20px;', preceding_cell['attrs']['style'])
            self.assertNotIn('margin-bottom', table['attrs']['style'])

    def test_retired_recap_heading_and_attachment_joke_are_not_rendered(self):
        self.assertNotIn('The Run Recap', SUCCESS_SUBJECTS)
        for critical, body in (
            (False, _build_success_email_body('smd', {'main_success': 2}, 'reports')),
            (True, _build_critical_email_body({'mode': 'smd'}, 'reports')),
        ):
            markup = _render_email_html(body, critical=critical)
            self.assertNotIn('THE RUN RECAP', markup.upper())
            self.assertNotIn('Future-you is covered', markup)
            self.assertIn('SADM Autorouter', markup)

    def test_attachment_copy_rotates_without_repeats_or_cycle_boundary_duplicates(self):
        with patch('core.critical_error_notifier._attachment_copy_remaining', []), \
                patch('core.critical_error_notifier._last_attachment_copy', ''), \
                patch('core.critical_error_notifier._email_random.shuffle', side_effect=lambda values: None):
            count = len(REPORT_ATTACHMENT_LINES)
            first = [_attachment_line() for _ in range(count)]
            second = [_attachment_line() for _ in range(count)]
        self.assertEqual(set(first), set(REPORT_ATTACHMENT_LINES))
        self.assertEqual(set(second), set(REPORT_ATTACHMENT_LINES))
        self.assertNotEqual(first[-1], second[0])
        for line in first + second:
            self.assertIn('run', line.lower())
            self.assertIn('log', line.lower())
            self.assertIn('mapping sheet', line)

    def test_both_templates_use_the_current_users_first_name(self):
        with patch("core.critical_error_notifier.get_full_username", return_value="Libuna, Kevin John (Operations)"):
            for body in (
                _build_success_email_body("irsplr", {}, "reports"),
                _build_critical_email_body({"mode": "smd"}, "reports"),
            ):
                self.assertIn("Thanks,\n\nKevin's Autorouter", body)
                self.assertNotIn("- Kevin's Autorouter", body)
                self.assertTrue(body.startswith("Hi Kevin,\n"))
                self.assertNotIn("Your SMD Autorouter", body)
                markup = _render_email_html(body)
                self.assertIn('Thanks,</p></td></tr><tr><td valign="top" style="padding:0 0 20px;', markup)
                self.assertIn(">Kevin&#x27;s Autorouter</p>", markup)

    def test_lowercase_first_name_and_email_headings_are_capitalized(self):
        with patch("core.critical_error_notifier.get_full_username", return_value="kevin john libuna"):
            body = _build_critical_email_body({"mode": "smd"}, "reports")
        self.assertTrue(body.startswith("Hi Kevin,\n"))
        self.assertIn("What Needs Attention:", body)
        self.assertIn("Suggested Next Steps:", body)
        self.assertIn("Action Needed", _render_email_html(body, critical=True))

    def test_signature_handles_names_and_missing_identity(self):
        for full_name, expected in (("Dena Hall", "Dena's Autorouter"),
                                    ("  ", "Your Autorouter"),
                                    ("User", "Your Autorouter")):
            with self.subTest(name=full_name), patch("core.critical_error_notifier.get_full_username", return_value=full_name):
                self.assertEqual(_email_signature(), expected)
        with patch("core.critical_error_notifier.get_full_username", side_effect=RuntimeError("unavailable")):
            self.assertEqual(_email_signature(), "Your Autorouter")

    def test_success_counts_are_table_cells_with_correct_values(self):
        body = _build_success_email_body("smd", {"counsel_success": 9, "main_success": 15}, "C:/reports")
        markup = _render_email_html(body)
        parsed = EmailMarkup(markup)
        self.assertIn("th", parsed.tags)
        self.assertIn("td", parsed.tags)
        for label, value in (("Total Routed", "24"), ("Counsel Routed", "9")):
            i = parsed.text.index(label)
            self.assertEqual(parsed.text[i + 1], value)
        self.assertNotIn("- Total Routed:", markup)

    def test_critical_details_and_next_steps_are_retained(self):
        body = _build_critical_email_body({"mode": "smd", "title": "Counsel not ready", "lni": "TEST-LNI"}, "C:/reports")
        parsed = EmailMarkup(_render_email_html(body, critical=True))
        self.assertIn("Action Needed", parsed.text)
        self.assertIn("TEST-LNI", parsed.text)
        self.assertIn("ol", parsed.tags)
        self.assertIn("li", parsed.tags)

    def test_dynamic_content_cannot_inject_html(self):
        markup = _render_email_html('Hi team,\n\nDetails:\n- Error: <script>alert("x")</script> & more\n\nC:/<reports>')
        self.assertNotIn("script", EmailMarkup(markup).tags)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("&amp; more", markup)
        self.assertIn("C:/&lt;reports&gt;", markup)

    def test_outlook_sends_html_and_preserves_recipient_and_attachment(self):
        outlook = Mock()
        mail = outlook.CreateItem.return_value
        config = {"critical_error_user_email": "user@example.com",
                  "critical_error_developer_email": "dev@example.com"}
        with patch("pythoncom.CoInitialize"), patch("pythoncom.CoUninitialize"), \
                patch("win32com.client.Dispatch", return_value=outlook), \
                patch("core.critical_error_notifier.Path.exists", return_value=True):
            self.assertTrue(_send_outlook_email("Test report", "Results:\n- Routed: 24", ["log.txt"], config, critical=True))
        self.assertEqual(mail.BodyFormat, 2)
        self.assertIn("Action Needed", mail.HTMLBody)
        self.assertIn("<th", mail.HTMLBody)
        self.assertEqual(mail.Subject, "Test report")
        self.assertEqual(mail.To, "user@example.com; dev@example.com")
        mail.Attachments.Add.assert_called_once()
        mail.Send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
