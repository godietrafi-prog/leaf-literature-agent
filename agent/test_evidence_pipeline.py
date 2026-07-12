from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_pipeline as ep
import digitize_plot as dp


class EvidencePipelineTests(unittest.TestCase):
    def test_mean_sd_pattern(self):
        match = ep.MEAN_SD_RE.search("1.84 ± 0.48 a")
        self.assertEqual(float(match.group("mean")), 1.84)
        self.assertEqual(float(match.group("error")), 0.48)

    def test_split_cells_can_be_rejoined(self):
        row = "hexanal | 1.84 | ± | 0.48 | a"
        joined = ep.re.sub(r"\s*\|\s*(±|\+/-)\s*\|?\s*", r" \1 ", row)
        match = ep.MEAN_SD_RE.search(joined)
        self.assertEqual((float(match.group("mean")), float(match.group("error"))), (1.84, 0.48))

    def test_split_decimal_can_be_rejoined(self):
        row = "0.14 | ± | 0. | 03 b"
        joined = ep.re.sub(r"(?<=\d\.)\s*\|\s*(?=\d)", "", row)
        joined = ep.re.sub(r"\s*\|\s*(±|\+/-)\s*\|?\s*", r" \1 ", joined)
        match = ep.MEAN_SD_RE.search(joined)
        self.assertEqual(float(match.group("error")), 0.03)

    def test_quantity_and_unit(self):
        blob = "hexanal concentration (ppbv)"
        self.assertEqual(ep.infer_quantity(blob), "hexanal_conc")
        self.assertEqual(ep.infer_unit(blob), "ppbv")

    def test_percentage_guardrail(self):
        row = {
            "paper_id": "x", "quantity": "yield_pct", "value": 120, "unit": "%",
            "source_location": "Table 1", "extraction_mode": "table_native",
            "status": "needs_review",
        }
        self.assertIn("percentage outside 0..100", ep.validation_errors(row))

    def test_graph_requires_calibration_metadata(self):
        row = {
            "paper_id": "x", "quantity": "yield_pct", "value": 50, "unit": "%",
            "source_location": "Figure 1", "extraction_mode": "graph_digitized",
            "status": "approved",
        }
        errors = ep.validation_errors(row)
        self.assertTrue(any("figure_label" in error for error in errors))

    def test_approved_row_requires_semantic_review(self):
        row = {
            "paper_id": "x", "quantity": "hexanal_conc", "value": 1.2, "unit": "ppbv",
            "sd_error": 0.1, "error_type": "reported_dispersion_unknown",
            "source_location": "Table 1", "extraction_mode": "table_native",
            "status": "approved",
        }
        errors = ep.validation_errors(row)
        self.assertIn("approved row requires treatment_condition", errors)
        self.assertIn("approved row requires resolved error_type", errors)

    def test_linear_axis_calibration(self):
        axis = {"pixel1": 100, "value1": 0, "pixel2": 500, "value2": 80, "scale": "linear"}
        self.assertAlmostEqual(dp.axis_value(300, axis), 40)

    def test_log_axis_calibration(self):
        axis = {"pixel1": 0, "value1": 1, "pixel2": 100, "value2": 100, "scale": "log10"}
        self.assertAlmostEqual(dp.axis_value(50, axis), 10)


if __name__ == "__main__":
    unittest.main()
