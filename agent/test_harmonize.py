from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harmonize


class HarmonizeTests(unittest.TestCase):
    def test_percent_exact(self):
        row = harmonize.harmonize_value("yield_pct", 12.5, "%", None)
        self.assertEqual((row[1], row[2], row[4]), (12.5, "%", "exact"))

    def test_mass_unit_equivalence(self):
        row = harmonize.harmonize_value("hexanal_conc", 10, "g/kg", "dry basis")
        self.assertEqual((row[1], row[2], row[4]), (10, "mg/g", "converted"))

    def test_incompatible_percent_is_not_guessed(self):
        row = harmonize.harmonize_value("yield_pct", 10, "g/kg", "fresh leaf")
        self.assertEqual(row[1], 10)
        self.assertEqual(row[2], "g/kg")
        self.assertEqual(row[4], "identity_only")

    def test_treatment_ontology(self):
        ph, temp, time, oxygen, sonication, heat, status = harmonize.treatment_features(
            "N2 flushing; ultrasound at pH 7.5, 55 C for 30 min")
        self.assertEqual((ph, temp, time, oxygen, sonication, heat), (7.5, 55, 30, 1, 1, 1))
        self.assertEqual(status, "parsed_needs_review")


if __name__ == "__main__":
    unittest.main()
