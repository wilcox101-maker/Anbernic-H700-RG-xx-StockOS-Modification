"""OS version channel selection.

Characterization tests call the real import-time selection in upgrade.py and
record what it does today, including the unknown-version bug. Acceptance tests
state the behavior a later fix should have. They are marked expectedFailure
while the bug is still present, so a fix that makes them pass fails CI until
the marker is removed in that same change.
"""

import unittest

from tests.harness import probe_channel


class UnknownOsVersionTests(unittest.TestCase):
    def test_known_dates_keep_their_channels(self):
        older = probe_channel("20240101\n")
        early = probe_channel("20251101\n")
        mid = probe_channel("20251206\n")
        current = probe_channel("20260520\n")

        self.assertEqual(older["os_cur_ver"], "20240101")
        self.assertEqual(older["source"], "source/")
        self.assertEqual(older["base_ver"], "3.8.0")
        self.assertFalse(older["append_when_mod_unknown"])

        self.assertEqual(early["os_cur_ver"], "20251101")
        self.assertEqual(early["source"], "source/")
        self.assertEqual(early["base_ver"], "3.8.0")
        self.assertEqual(early["base_date"], "20250211")
        self.assertFalse(early["update_log_exists"])

        self.assertEqual(mid["source"], "390/")
        self.assertEqual(mid["base_ver"], "3.9.0")
        self.assertEqual(mid["base_date"], "20251206")

        self.assertEqual(current["source"], "400/")
        self.assertEqual(current["base_ver"], "3.9.9")
        self.assertEqual(current["base_date"], "20260520")

    def test_current_missing_version_selects_400_channel(self):
        """CHARACTERIZATION: a missing version.ini is treated as a new OS."""
        probed = probe_channel(None)
        self.assertEqual(probed["os_cur_ver"], "Unknown")
        self.assertEqual(probed["source"], "400/")
        self.assertEqual(probed["base_ver"], "3.9.9")
        self.assertEqual(probed["base_date"], "20260520")
        self.assertTrue(probed["append_when_mod_unknown"])
        self.assertFalse(probed["update_log_exists"])

    def test_current_literal_unknown_selects_400_channel(self):
        """CHARACTERIZATION: the text Unknown compares as newer than the date gate."""
        probed = probe_channel("Unknown\n")
        self.assertEqual(probed["os_cur_ver"], "Unknown")
        self.assertEqual(probed["source"], "400/")
        self.assertTrue(probed["append_when_mod_unknown"])

    def test_current_empty_version_file_selects_400_channel(self):
        """CHARACTERIZATION: an empty version.ini also becomes Unknown."""
        probed = probe_channel("")
        self.assertEqual(probed["os_cur_ver"], "Unknown")
        self.assertEqual(probed["source"], "400/")
        self.assertTrue(probed["append_when_mod_unknown"])

    @unittest.expectedFailure
    def test_acceptance_missing_version_does_not_select_400_or_offer_append(self):
        """ACCEPTANCE: unknown OS must not take the 4.0.0 channel or the append offer.

        Remove expectedFailure only in the change that fixes upgrade.py.
        """
        probed = probe_channel(None)
        self.assertNotEqual(probed["source"], "400/")
        self.assertFalse(probed["append_when_mod_unknown"])

    @unittest.expectedFailure
    def test_acceptance_literal_unknown_does_not_select_400_or_offer_append(self):
        """ACCEPTANCE: the string Unknown is not an OS date."""
        probed = probe_channel("Unknown\n")
        self.assertNotEqual(probed["source"], "400/")
        self.assertFalse(probed["append_when_mod_unknown"])

    @unittest.expectedFailure
    def test_acceptance_empty_version_file_does_not_select_400_or_offer_append(self):
        """ACCEPTANCE: an unreadable version file is not an OS date."""
        probed = probe_channel("")
        self.assertNotEqual(probed["source"], "400/")
        self.assertFalse(probed["append_when_mod_unknown"])


if __name__ == "__main__":
    unittest.main()
