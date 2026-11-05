"""OS version channel selection.

Valid YYYYMMDD values keep the channel they select today. Missing, empty,
Unknown, and malformed values must stay on the baseline channel and must not
qualify for an append or mod update.
"""

import unittest

from tests.harness import probe_channel


def _assert_fail_closed(test, probed):
    test.assertEqual(probed["os_cur_ver"], "Unknown")
    test.assertEqual(probed["source"], "source/")
    test.assertEqual(probed["base_ver"], "3.8.0")
    test.assertEqual(probed["base_date"], "20250211")
    test.assertFalse(probed["append_when_mod_unknown"])
    test.assertFalse(probed["update_when_mod_unknown"])
    test.assertFalse(probed["update_log_exists"])


class UnknownOsVersionTests(unittest.TestCase):
    def test_known_dates_keep_their_channels(self):
        older = probe_channel("20240101\n")
        early = probe_channel("20251101\n")
        mid = probe_channel("20251206\n")
        current = probe_channel("20260520\n")
        noted = probe_channel("20260520\nnote\n")

        self.assertEqual(older["os_cur_ver"], "20240101")
        self.assertEqual(older["source"], "source/")
        self.assertEqual(older["base_ver"], "3.8.0")
        self.assertEqual(older["base_date"], "20250211")
        self.assertFalse(older["append_when_mod_unknown"])
        self.assertFalse(older["update_when_mod_unknown"])

        self.assertEqual(early["os_cur_ver"], "20251101")
        self.assertEqual(early["source"], "source/")
        self.assertEqual(early["base_ver"], "3.8.0")
        self.assertEqual(early["base_date"], "20250211")
        self.assertTrue(early["append_when_mod_unknown"])
        self.assertTrue(early["update_when_mod_unknown"])
        self.assertFalse(early["update_log_exists"])

        self.assertEqual(mid["os_cur_ver"], "20251206")
        self.assertEqual(mid["source"], "390/")
        self.assertEqual(mid["base_ver"], "3.9.0")
        self.assertEqual(mid["base_date"], "20251206")
        self.assertTrue(mid["append_when_mod_unknown"])
        self.assertTrue(mid["update_when_mod_unknown"])

        self.assertEqual(current["os_cur_ver"], "20260520")
        self.assertEqual(current["source"], "400/")
        self.assertEqual(current["base_ver"], "3.9.9")
        self.assertEqual(current["base_date"], "20260520")
        self.assertTrue(current["append_when_mod_unknown"])
        self.assertTrue(current["update_when_mod_unknown"])

        self.assertEqual(noted["os_cur_ver"], "20260520")
        self.assertEqual(noted["source"], "400/")
        self.assertTrue(noted["append_when_mod_unknown"])
        self.assertTrue(noted["update_when_mod_unknown"])

    def test_missing_version_does_not_qualify(self):
        """A missing version.ini is not a new OS."""
        _assert_fail_closed(self, probe_channel(None))

    def test_literal_unknown_does_not_qualify(self):
        """The text Unknown is not an OS date."""
        _assert_fail_closed(self, probe_channel("Unknown\n"))

    def test_empty_version_file_does_not_qualify(self):
        """An empty version.ini is not an OS date."""
        _assert_fail_closed(self, probe_channel(""))

    def test_acceptance_missing_version_does_not_select_400_or_offer_append(self):
        """Promoted acceptance: missing OS version stays fail-closed."""
        _assert_fail_closed(self, probe_channel(None))

    def test_acceptance_literal_unknown_does_not_select_400_or_offer_append(self):
        """Promoted acceptance: the string Unknown stays fail-closed."""
        _assert_fail_closed(self, probe_channel("Unknown\n"))

    def test_acceptance_empty_version_file_does_not_select_400_or_offer_append(self):
        """Promoted acceptance: an empty version file stays fail-closed."""
        _assert_fail_closed(self, probe_channel(""))

    def test_malformed_versions_do_not_qualify(self):
        cases = {
            "mod version string": "4.0.4\n",
            "dashed date": "2026-10-25\n",
            "trailing space": "20260520 \n",
            "leading space": " 20260520\n",
            "seven digits": "2026052\n",
            "nine digits": "202605200\n",
            "uppercase unknown": "UNKNOWN\n",
            "blank first line": "\n20260520\n",
            "whitespace only": "   \n",
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                _assert_fail_closed(self, probe_channel(text))


if __name__ == "__main__":
    unittest.main()
