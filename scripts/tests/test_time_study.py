"""Hermetic tests for time_study.py.

Run from the repo root: python3 -m unittest discover -s scripts/tests -v
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time_study as ts  # noqa: E402

PLAN = """\
## 🎯 Today's Plan

| # | Time | Task | Priority | Type | Est. | Quadrant | Start | End |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 9:30 | [[Next Actions#Recurring\\|Drill]] ✅ | 🔼 | Mechanical | 30m (adj: 38m) | Business | 09:30 | 10:00 |
| 2 | 10:00 | Write memo | ⏫ | Thinking | 45m | Demand | 10:00 | 10:45 |
| -- | **11:00** | **Meet Don** | | | **60m** | Demand | 11:00 | 12:00 |
| -- | 12:00 | *Lunch* | | | 30m | | | |
| 3 | 1:00 | Ask Donna | 🔼 | Mechanical | 20m | | | |
| -- | | Unplanned email | | | none | Distraction | 1:30 | 2:00 |
| 4 | deferred | Later | | | 10m | | | |

### Notes

| ignored | table |
"""


def analyze(text: str, window=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "2026-11-06.md"
        p.write_text(text, encoding="utf-8")
        return ts.analyze_file(p, window)


class ClockTests(unittest.TestCase):
    def test_24_hour_and_suffixes(self):
        self.assertEqual(ts.parse_clock("09:30"), (570, False))
        self.assertEqual(ts.parse_clock("**11:00**"), (660, False))
        self.assertEqual(ts.parse_clock("1:15pm"), (795, False))
        self.assertEqual(ts.parse_clock("12:10am"), (10, False))

    def test_early_afternoon_hours_read_as_pm(self):
        self.assertEqual(ts.parse_clock("1:15"), (795, True))
        self.assertEqual(ts.parse_clock("12:30"), (750, False))
        self.assertEqual(ts.parse_clock("6:00"), (360, False))

    def test_garbage(self):
        self.assertIsNone(ts.parse_clock("soon"))
        self.assertIsNone(ts.parse_clock("9:75"))

    def test_duration_takes_the_base_estimate(self):
        self.assertEqual(ts.parse_duration("30m (adj: 38m)"), 30)
        self.assertEqual(ts.parse_duration("1h15m"), 75)
        self.assertEqual(ts.parse_duration("**60m**"), 60)
        self.assertIsNone(ts.parse_duration("none"))


class PlanTests(unittest.TestCase):
    def test_minutes_by_quadrant_and_escaped_pipes(self):
        a = analyze(PLAN)
        self.assertEqual(a.source, "plan")
        self.assertEqual(a.minutes["Business"], 30)
        self.assertEqual(a.minutes["Demand"], 45 + 60)
        self.assertEqual(a.minutes["Distraction"], 30)
        self.assertEqual(a.logged, 165)
        self.assertEqual(a.rows[0].label, "Drill")
        self.assertEqual(a.rows[0].est, 30)

    def test_unexecuted_and_deferred_rows_are_not_flagged(self):
        a = analyze(PLAN)
        self.assertEqual(a.not_executed, 2)  # lunch and Ask Donna
        self.assertFalse(any("Donna" in i or "Later" in i for i in a.issues))

    def test_gap_found_between_spans(self):
        a = analyze(PLAN)
        self.assertEqual(a.gaps, [(720, 810)])  # 12:00 to 13:30
        self.assertFalse(a.clean)
        self.assertEqual(a.window, (570, 840))
        self.assertEqual(a.covered, 165)

    def test_off_row_closes_a_gap(self):
        text = PLAN.replace("| -- | 12:00 | *Lunch* | | | 30m | | | |",
                            "| -- | 12:00 | *Lunch* | | | 90m | Off | 12:00 | 13:30 |")
        a = analyze(text)
        self.assertEqual(a.gaps, [])
        self.assertEqual(a.minutes["Off"], 90)
        self.assertEqual(a.logged, 165)
        self.assertTrue(a.clean)

    def test_done_row_without_times_is_an_issue(self):
        text = PLAN.replace("| 3 | 1:00 | Ask Donna |", "| 3 | done | Ask Donna ✅ |")
        a = analyze(text)
        self.assertTrue(any("Donna" in i and "no Start" in i for i in a.issues))

    def test_bold_meeting_without_times_is_an_issue(self):
        text = PLAN.replace("| Demand | 11:00 | 12:00 |", "| | | |")
        a = analyze(text)
        self.assertTrue(any("meeting" in i for i in a.issues))

    def test_cancelled_meeting_is_ignored(self):
        text = PLAN.replace("**Meet Don**", "~~Meet Don~~ *cancelled*").replace("| Demand | 11:00 | 12:00 |", "| | | |")
        a = analyze(text)
        self.assertFalse(any("Don" in i for i in a.issues))

    def test_missing_quadrant_and_bad_quadrant(self):
        a = analyze(PLAN.replace("| Demand | 10:00 | 10:45 |", "| | 10:00 | 10:45 |"))
        self.assertEqual(a.untagged, 45)
        self.assertTrue(any("no quadrant" in i for i in a.issues))
        b = analyze(PLAN.replace("| Demand | 10:00 | 10:45 |", "| Chores | 10:00 | 10:45 |"))
        self.assertTrue(any("Chores" in i for i in b.issues))

    def test_half_filled_and_backwards_times(self):
        a = analyze(PLAN.replace("| Demand | 10:00 | 10:45 |", "| Demand | 10:00 | |"))
        self.assertTrue(any("needs both" in i for i in a.issues))
        b = analyze(PLAN.replace("| Demand | 10:00 | 10:45 |", "| Demand | 10:45 | 10:00 |"))
        self.assertTrue(any("not after" in i for i in b.issues))

    def test_overlap_reported_and_coverage_not_double_counted(self):
        a = analyze(PLAN.replace("| Demand | 10:00 | 10:45 |", "| Demand | 09:45 | 10:45 |"))
        self.assertEqual(len(a.overlaps), 1)
        self.assertIn("15m", a.overlaps[0])
        self.assertEqual(a.covered, 75 + 60 + 30)
        self.assertLessEqual(a.covered, a.window_minutes)

    def test_window_adds_edge_gaps(self):
        a = analyze(PLAN, ts.parse_window("08:00-15:00"))
        self.assertIn((480, 570), a.gaps)
        self.assertIn((840, 900), a.gaps)

    def test_assumed_pm_is_noted(self):
        a = analyze(PLAN)
        self.assertTrue(any("1:30" in n and "13:30" in n for n in a.notes))

    def test_all_clean_day(self):
        text = PLAN.replace("| -- | 12:00 | *Lunch* | | | 30m | | | |",
                            "| -- | 12:00 | *Lunch* | | | 90m | Off | 12:00 | 13:30 |")
        self.assertTrue(analyze(text).clean)


DIARY = """\
## Action Diary

| | Urgent | Planned |
| --- | --- | --- |
| Serves a goal | Demand | Business |

| Time | Activity | Quadrant | Outcome/Notes |
| ----- | -------- | -------- | ------------- |
| 08:30 | Resume | Demand | x |
| 09:00 | Resume | Demand | x |
| 09:30 | | | |
| 19:00 | Drill | Business | |
"""


class DiaryFallbackTests(unittest.TestCase):
    def test_old_diary_counts_half_hours(self):
        a = analyze(DIARY)
        self.assertEqual(a.source, "diary")
        self.assertEqual(a.minutes["Demand"], 60)
        self.assertEqual(a.minutes["Business"], 30)


class LedgerTests(unittest.TestCase):
    def test_upsert_replaces_the_same_day(self):
        a = analyze(PLAN)
        e1 = ts.entry_for(a)
        e2 = dict(e1, Demand="999")
        rows = ts.upsert(ts.upsert([], e1), e2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Demand"], "999")

    def test_round_trip_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Time Study.md"
            path.write_text("# Time Study\n\nIntro text.\n", encoding="utf-8")
            head, entries = ts.read_ledger(path)
            self.assertEqual(entries, [])
            for day, dem in (("2026-11-02", "300"), ("2026-11-03", "200")):
                entries = ts.upsert(entries, {"Date": day, "Demand": dem, "Business": "100",
                                              "Distraction": "0", "Delusion": "0", "Off": "20",
                                              "Window": "480", "Source": "plan", "Flags": "clean"})
            ts.write_ledger(path, head, entries)
            head2, again = ts.read_ledger(path)
            self.assertIn("Intro text.", head2)
            self.assertEqual([e["Date"] for e in again], ["2026-11-02", "2026-11-03"])
            self.assertEqual(again[0]["Demand"], "300")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count(ts.SUMMARY_MARK), 1)
            self.assertIn("all time", text)
            self.assertIn("71.4%", text)  # 500 of 700 tagged minutes

    def test_week_report_compares_prior_week(self):
        def e(day, d, b):
            return {"Date": day, "Demand": str(d), "Business": str(b), "Distraction": "0",
                    "Delusion": "0", "Off": "0", "Window": "500", "Source": "plan", "Flags": "clean"}
        entries = [e("2026-10-27", 100, 100), e("2026-11-03", 300, 100)]
        out = ts.week_report(entries, dt.date(2026, 11, 2), dt.date(2026, 11, 8))
        self.assertIn("75.0%", out)   # this week's Demand share
        self.assertIn("50.0%", out)   # last week's Demand share


if __name__ == "__main__":
    unittest.main()
