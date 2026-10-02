"""Hermetic tests for the milestone generator (milestones.py).

Golden values are the Junction inputs in sites.yaml. Nothing here touches the
vault, Google Drive or Excel; the rewrite test works on a temp file.
"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import milestones as ms  # noqa: E402

D = datetime.date
OFFSETS = ms.load_yaml("offsets.yaml")
SITES = ms.load_yaml("sites.yaml")
JUNCTION = SITES["sites"]["junction"]
AWAY = SITES["owner"]["away"]


def junction():
    return ms.resolve(OFFSETS, JUNCTION["inputs"])


class TestResolve(unittest.TestCase):
    def test_inputs_pass_through(self):
        r = junction()
        self.assertEqual(r["lease-signed"], (D(2026, 11, 30), D(2026, 11, 30)))
        self.assertEqual(r["kickoff-call"], (D(2026, 10, 8), D(2026, 10, 15)))

    def test_gm_in_seat_follows_lease(self):
        self.assertEqual(junction()["gm-in-seat"], (D(2026, 11, 30), D(2026, 11, 30)))

    def test_recruiting_starts_in_october(self):
        lo, hi = junction()["gm-recruiting"]
        self.assertEqual((lo, hi), (D(2026, 10, 1), D(2026, 10, 16)))

    def test_forward_chain_uses_template_durations(self):
        r = junction()
        pt = lambda y, m, d: (D(y, m, d), D(y, m, d))
        self.assertEqual(r["construction-start"], pt(2027, 4, 1))
        self.assertEqual(r["lighting-flooring"], pt(2027, 5, 13))
        self.assertEqual(r["equipment-delivered"], pt(2027, 7, 1))
        self.assertEqual(r["equipment-ordered"], pt(2027, 4, 8))
        self.assertEqual(r["build-complete"], pt(2027, 7, 15))
        self.assertEqual(r["soft-open"], pt(2027, 7, 22))

    def test_template_gaps_from_construction_start(self):
        # Template: construction 11/18, lighting 12/30, install 2/17, CO week of 3/3, open 3/10.
        start = D(2026, 11, 18)
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": start})
        r = ms.resolve(OFFSETS, inputs)
        self.assertEqual(r["lighting-flooring"][0], D(2026, 12, 30))
        self.assertEqual(r["equipment-delivered"][0], D(2027, 2, 17))
        self.assertEqual(r["build-complete"][0], D(2027, 3, 3))
        self.assertEqual(r["soft-open"][0], D(2027, 3, 10))

    def test_rent_starts_150_days_after_delivery(self):
        self.assertEqual(junction()["rent-commences"], (D(2027, 8, 29), D(2027, 8, 29)))

    def test_permits_submitted_within_60_days_of_lease(self):
        self.assertEqual(junction()["permits-submitted"], (D(2026, 11, 30), D(2027, 1, 29)))

    def test_backward_chain_from_soft_open(self):
        r = junction()
        self.assertEqual(r["presale-launch"], (D(2027, 2, 22), D(2027, 4, 23)))
        self.assertEqual(r["vip-start"], (D(2027, 1, 11), D(2027, 3, 12)))
        self.assertEqual(r["grand-opening"], (D(2027, 9, 2), D(2027, 9, 16)))

    def test_delivery_slip_moves_soft_open(self):
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 5, 1)})
        self.assertEqual(ms.resolve(OFFSETS, inputs)["soft-open"][0], D(2027, 8, 21))

    def test_slipping_the_lease_moves_the_gm(self):
        inputs = dict(JUNCTION["inputs"], **{"lease-signed": D(2027, 1, 15)})
        self.assertEqual(ms.resolve(OFFSETS, inputs)["gm-in-seat"][0], D(2027, 1, 15))

    def test_missing_input_is_an_error(self):
        inputs = {k: v for k, v in JUNCTION["inputs"].items() if k != "landlord-delivery"}
        with self.assertRaises(ValueError):
            ms.resolve(OFFSETS, inputs)

    def test_cycle_is_an_error(self):
        looped = {"milestones": [
            {"key": "a", "anchor": "b", "offset_days": [0, 0]},
            {"key": "b", "anchor": "a", "offset_days": [0, 0]}]}
        with self.assertRaises(ValueError):
            ms.resolve(looped, {})


class TestMonthsOver(unittest.TestCase):
    def test_part_of_a_month_counts_as_a_month(self):
        self.assertEqual(ms.months_over(D(2027, 5, 12), D(2027, 7, 15)), 3)

    def test_exact_months(self):
        self.assertEqual(ms.months_over(D(2027, 5, 12), D(2027, 7, 12)), 2)

    def test_end_of_month_clamps(self):
        self.assertEqual(ms.months_over(D(2027, 1, 31), D(2027, 2, 28)), 1)


class TestFlags(unittest.TestCase):
    def messages(self, resolved):
        return dict(ms.flags(resolved, JUNCTION["limits"], AWAY))

    def test_junction_flags_extension_and_opening_fee(self):
        m = self.messages(junction())
        self.assertIn("one-time 90-day extension", m["lease-signed"])
        self.assertIn("3 months past", m["soft-open"])
        self.assertIn("$7,500", m["soft-open"])
        self.assertNotIn("gm-in-seat", m)

    def test_lease_before_deadline_is_clean(self):
        r = dict(junction(), **{"lease-signed": (D(2026, 11, 2), D(2026, 11, 2))})
        self.assertNotIn("lease-signed", self.messages(r))

    def test_lease_past_extended_deadline(self):
        r = dict(junction(), **{"lease-signed": (D(2027, 3, 1), D(2027, 3, 1))})
        self.assertIn("extended", self.messages(r)["lease-signed"])

    def test_gm_after_hard_stop(self):
        r = dict(junction(), **{"gm-in-seat": (D(2027, 1, 15), D(2027, 1, 15))})
        self.assertIn("hard stop", self.messages(r)["gm-in-seat"])

    def test_absence_flag_needs_whole_range_inside(self):
        r = dict(junction(), **{"gm-in-seat": (D(2026, 12, 20), D(2026, 12, 22))})
        self.assertIn("absence", self.messages(r)["gm-in-seat"])


class TestRender(unittest.TestCase):
    def test_table_keeps_keys_and_order(self):
        table = ms.render_table(OFFSETS, junction(), JUNCTION["basis"])
        keys = [line.split("`")[1] for line in table.splitlines()[2:]]
        self.assertEqual(keys, [m["key"] for m in OFFSETS["milestones"]])

    def test_site_basis_overrides_default(self):
        table = ms.render_table(OFFSETS, junction(), JUNCTION["basis"])
        self.assertIn("pending the 10/6 call", table)

    def test_point_and_range_formats(self):
        self.assertEqual(ms.fmt((D(2026, 11, 30), D(2026, 11, 30))), "2026-11-30")
        self.assertEqual(ms.fmt((D(2026, 10, 8), D(2026, 10, 15))), "2026-10-08 to 2026-10-15")


class TestRewrite(unittest.TestCase):
    def test_replaces_only_the_marked_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("before\n<!-- milestones:junction:start -->\nold\n<!-- milestones:junction:end -->\nafter\n")
            ms.rewrite_note(path, "junction", "NEW TABLE")
            with open(path, encoding="utf-8") as f:
                text = f.read()
        self.assertEqual(text, "before\n<!-- milestones:junction:start -->\nNEW TABLE\n<!-- milestones:junction:end -->\nafter\n")

    def test_missing_markers_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("no markers\n")
            with self.assertRaises(SystemExit):
                ms.rewrite_note(path, "junction", "x")


if __name__ == "__main__":
    unittest.main()
