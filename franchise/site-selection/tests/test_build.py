"""Hermetic tests for the site-selection builder.

Run: ./.venv/bin/python -m unittest discover -s tests   (from franchise/site-selection/)
or:  ./.venv/bin/python tests/test_build.py

These do NOT touch Google Drive. The Site Report parser is exercised against a
committed text fixture (tests/fixtures/camden_report.txt) captured from a real VT
PDF, so if VisionTrack changes their layout or a dependency drifts, the parser
assertions fail loudly and tell you exactly which field broke.
"""
import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_facts as bf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "camden_report.txt")
CONFIG = os.path.join(os.path.dirname(HERE), "config.yaml")


class TestParseNum(unittest.TestCase):
    def test_units(self):
        self.assertEqual(bf.parse_num("24k"), 24000)
        self.assertEqual(bf.parse_num("$182k"), 182000)
        self.assertEqual(bf.parse_num("1.5m"), 1500000)
        self.assertEqual(bf.parse_num("467k"), 467000)
        self.assertEqual(bf.parse_num("2.9%"), 2.9)
        self.assertEqual(bf.parse_num("-0.7%"), -0.7)
        self.assertEqual(bf.parse_num("41"), 41)

    def test_blanks(self):
        for v in ("", "TODO", "-", None):
            self.assertIsNone(bf.parse_num(v))


class TestParseReport(unittest.TestCase):
    """Golden values for Camden Park's Site Report (the spec the parser must meet)."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.d = bf.parse_report_text(f.read())

    def test_population_all_rings(self):
        self.assertEqual(self.d["pop_1mi"], 24000)
        self.assertEqual(self.d["pop_3mi"], 190000)
        self.assertEqual(self.d["pop_5mi"], 467000)

    def test_income(self):
        self.assertEqual(self.d["med_income_1mi"], 182000)
        self.assertEqual(self.d["med_income_3mi"], 170000)
        self.assertEqual(self.d["avg_income_3mi"], 246000)

    def test_age_bands(self):
        self.assertEqual(self.d["med_age_3mi"], 42)
        self.assertEqual(self.d["age_25_49_3mi"], 63000)
        self.assertEqual(self.d["age_50_64_3mi"], 39000)
        self.assertEqual(self.d["age_65plus_3mi"], 34000)

    def test_growth_and_daytime(self):
        self.assertEqual(self.d["cagr_hist_3mi"], 3.4)
        self.assertEqual(self.d["cagr_proj_3mi"], -0.8)
        self.assertEqual(self.d["daytime_3mi"], 155000)

    def test_affluence_and_competition(self):
        self.assertEqual(self.d["pct_income_150k_3mi"], 54.6)
        self.assertEqual(self.d["fitness_centers_3mi"], 104)

    def test_ai_score_and_households(self):
        self.assertEqual(self.d["ai_score"], 81)
        self.assertEqual(self.d["hh_3mi"], 70000)

    def test_empty_text_is_all_none(self):
        empty = bf.parse_report_text("")
        self.assertTrue(all(v is None for v in empty.values()))
        self.assertEqual(set(empty), set(bf.REPORT_FIELDS))


class TestCompute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CONFIG, encoding="utf-8") as f:
            cls.cfg = yaml.safe_load(f)

    def _row(self, **kw):
        r = {k: "" for k in bf.COLUMNS}
        r.update(kw)
        return r

    def test_gate_boundaries(self):
        # ceiling 17000 (Don 7/8 NorCal), borderline within +10% -> 18700.
        cases = {
            10272: "pass",       # base 39 + nnn 16.08 @ 2238 SF (Camden)
            13172: "pass",       # El Gato — was borderline under old $12.5K ceiling
            17000: "pass",       # exactly at ceiling
            17789: "borderline", # SC Square / Walnut asking
            18700: "borderline",
            19000: "fail",
        }
        for allin, expected in cases.items():
            # pick base/nnn/sf that yield this monthly all-in: (base+nnn)*sf/12 = allin
            r = self._row(sf_target="1200", base_psf=str(allin * 12 / 1200), nnn_psf="0")
            bf.compute(r, self.cfg)
            self.assertEqual(r["gate_afford"], expected, f"allin={allin}")

    def test_gate_todo_when_missing(self):
        r = self._row(sf_target="2000", base_psf="60", nnn_psf="TODO")
        bf.compute(r, self.cfg)
        self.assertEqual(r["total_rent"], "TODO")
        self.assertEqual(r["gate_afford"], "TODO")

    def test_total_ti(self):
        r = self._row(sf_target="2399", ti_psf="85")
        bf.compute(r, self.cfg)
        self.assertEqual(r["total_ti"], "203915")

    def test_total_ti_todo_when_missing(self):
        r = self._row(sf_target="2399", ti_psf="TODO")
        bf.compute(r, self.cfg)
        self.assertEqual(r["total_ti"], "TODO")

    def test_flags(self):
        r = self._row(med_income_3mi="170000", pop_3mi="190000", med_age_3mi="42",
                      cagr_hist_3mi="3.4", cagr_proj_3mi="-0.8")
        bf.compute(r, self.cfg)
        self.assertEqual(r["flag_income_150k"], "TRUE")
        self.assertEqual(r["flag_pop_100k"], "TRUE")
        self.assertEqual(r["flag_age_40plus"], "TRUE")
        self.assertEqual(r["flag_cagr"], "hist+/proj-")

    def test_flags_false(self):
        r = self._row(med_income_3mi="135000", pop_3mi="90000", med_age_3mi="35",
                      cagr_hist_3mi="1.0", cagr_proj_3mi="2.0")
        bf.compute(r, self.cfg)
        self.assertEqual(r["flag_income_150k"], "FALSE")
        self.assertEqual(r["flag_pop_100k"], "FALSE")
        self.assertEqual(r["flag_age_40plus"], "FALSE")
        self.assertEqual(r["flag_cagr"], "hist+/proj+")

    def test_placer_uniform_vs_spike(self):
        days = dict(placer_mon="100000", placer_tue="100000", placer_wed="100000",
                    placer_thu="100000", placer_fri="100000")
        uniform = self._row(placer_sat="105000", placer_sun="105000", **days)
        bf.compute(uniform, self.cfg)
        self.assertEqual(uniform["placer_weekend_ratio"], "1.05")
        self.assertEqual(uniform["placer_pattern"], "uniform")

        spike = self._row(placer_sat="200000", placer_sun="200000", **days)
        bf.compute(spike, self.cfg)
        self.assertEqual(spike["placer_weekend_ratio"], "2.00")
        self.assertEqual(spike["placer_pattern"], "weekend-spike")

    def test_placer_blank_when_incomplete(self):
        r = self._row(placer_mon="100000")  # missing the rest
        bf.compute(r, self.cfg)
        self.assertEqual(r["placer_weekend_ratio"], "")
        self.assertEqual(r["placer_pattern"], "")

    def test_composite(self):
        r = self._row(score_neighbor="6", score_customer="5", score_resid="4", score_visibility="7")
        bf.compute(r, self.cfg)
        # 0.30*6 + 0.25*5 + 0.25*4 + 0.20*7 = 1.8 + 1.25 + 1.0 + 1.4 = 5.45
        self.assertEqual(r["composite"], "5.45")

    def test_composite_blank_until_scored(self):
        r = self._row(score_neighbor="6")  # incomplete
        bf.compute(r, self.cfg)
        self.assertEqual(r["composite"], "")

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(self.cfg["weights"].values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
