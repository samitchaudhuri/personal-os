"""Hermetic tests for the timeline CSV export (timeline_csv.py).

The workbook is built in memory, so nothing reads Google Drive. The dependency
file is the real one, checked for shape only.
"""
import datetime
import io
import os
import sys
import unittest

import openpyxl
from openpyxl.styles import PatternFill

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timeline_csv as tc  # noqa: E402

D = datetime.date
BAR = PatternFill("solid", fgColor="FF3A7D44")
GRID = PatternFill("solid", fgColor="FFF0EEE9")
LINE = PatternFill("solid", fgColor="FF2C2926")


def book(anchor=datetime.datetime(2026, 6, 12)):
    ws = openpyxl.Workbook().active
    ws["B2"] = anchor
    for col in range(4, 41):
        for row in range(6, 50):
            ws.cell(row, col).fill = GRID
    ws["A6"] = "Group One"
    ws["A7"] = "First task"
    ws["C7"] = "Sales & Ops"
    for col in (4, 5, 6):          # weeks 1 to 3
        ws.cell(7, col).fill = BAR
    ws.cell(7, 40).fill = LINE      # the opening-day line is not a bar
    ws["A8"] = "Second task"
    ws["C8"] = "Marketing"
    ws["A9"] = "Opening"
    return ws


class TestReadTasks(unittest.TestCase):
    def test_bar_dates_come_from_the_anchor_and_week_numbers(self):
        t = tc.read_tasks(book())[0]
        self.assertEqual(t["start"], D(2026, 6, 19))
        self.assertEqual(t["end"], D(2026, 7, 9))

    def test_group_and_category_are_read(self):
        t = tc.read_tasks(book())[0]
        self.assertEqual((t["group"], t["category"]), ("Group One", "Sales & Ops"))

    def test_row_without_a_bar_has_no_dates(self):
        t = tc.read_tasks(book())[1]
        self.assertEqual((t["task"], t["start"], t["end"]), ("Second task", None, None))

    def test_opening_line_is_not_a_bar(self):
        ws = book()
        for col in range(4, 41):
            ws.cell(7, col).fill = GRID
        ws.cell(7, 40).fill = LINE
        self.assertEqual(tc.bar_weeks(ws, 7), [])

    def test_missing_anchor_is_an_error(self):
        with self.assertRaises(ValueError):
            tc.read_tasks(book(anchor="edit me"))


class TestDependencies(unittest.TestCase):
    def test_cycle_is_an_error(self):
        deps = {1: {"after": [2]}, 2: {"after": [1]}}
        with self.assertRaises(ValueError):
            tc.check_dependencies(deps, [1, 2])

    def test_unknown_row_is_an_error(self):
        with self.assertRaises(ValueError):
            tc.check_dependencies({1: {"after": [9]}}, [1, 2])

    def test_real_file_has_no_cycle_and_known_rows(self):
        deps = tc.load_dependencies()
        rows = set(deps) | {p for d in deps.values() for p in d["after"]}
        tc.check_dependencies(deps, rows)
        for row, d in deps.items():
            self.assertTrue(d["after"] and d["why"], row)

    def test_the_two_named_dependencies_are_proposed(self):
        deps = tc.load_dependencies()
        self.assertIn(24, deps[26]["after"])    # lease signed before permits
        self.assertIn(38, deps[43]["after"])    # VIP campaign before founding sales


class TestBuildRows(unittest.TestCase):
    def test_row_carries_dependencies_duration_and_estimate(self):
        tasks = tc.read_tasks(book())
        deps = {7: {"after": [], "why": ""}, 8: {"after": [7], "why": "after the first"}}
        est = {7: ("some-key", (D(2026, 8, 1), D(2026, 8, 5)))}
        rows = tc.build_rows(tasks, deps, est)
        self.assertEqual(rows[0]["sample_duration"], 21)
        self.assertEqual((rows[0]["milestone"], rows[0]["start"]), ("First task (some-key)", "2026-08-01"))
        self.assertEqual((rows[1]["constraint"], rows[1]["start"], rows[1]["sample_start"]), ("after 1", "", ""))

    def test_constraint_reads_as_a_duration_after_an_earlier_row(self):
        r = tc.milestone_rules()
        self.assertNotIn("gm-offer-accepted", r)    # the row starts at gm-sourcing, so its duration says 45 days
        self.assertEqual(r["gm-in-seat"], [("14-28 days after <<32>>", [32])])
        self.assertIn("at least 10 days after permits-received", [t for t, _ in r["construction-start"]])
        self.assertNotIn("lease-signed", r)

    def test_a_second_milestone_on_a_row_gets_its_own_row(self):
        ex = tc.extra_milestones("junction")
        self.assertEqual([(x[0], x[1]) for x in ex[32]], [("32.1", "gm-in-seat")])

    def test_the_gm_row_spans_sourcing_to_the_accepted_offer(self):
        est = tc.site_estimates("junction")[32]
        self.assertEqual((est[0], est[1][0], est[1][1]), ("gm-offer-accepted", D(2026, 10, 6), D(2026, 11, 20)))

    def test_rows_are_numbered_in_order_and_references_follow(self):
        rows = [{"id": 7, "constraint": ""}, {"id": "32.1", "constraint": "5 days after <<7>>"},
                {"id": 9, "constraint": "after <<32.1>>; 3 days after key"}]
        out = tc.renumber(rows)
        self.assertEqual([(r["id"], r["constraint"]) for r in out],
                         [(1, ""), (2, "5 days after 1"), (3, "after 2; 3 days after key")])

    def test_duration_is_the_days_from_start_to_end(self):
        tasks = tc.read_tasks(book())
        rows = tc.build_rows(tasks, {}, {7: ("k", (D(2026, 8, 1), D(2026, 8, 11)))})
        self.assertEqual(rows[0]["duration"], 10)

    def test_early_start_is_reported(self):
        ws = book()
        for col in (5, 6):
            ws.cell(8, col).fill = BAR
        tasks = tc.read_tasks(ws)
        self.assertEqual(tc.early_starts(tasks, {8: {"after": [7]}}), [(8, 7)])

    def test_csv_has_the_header_and_one_line_per_task(self):
        tasks = tc.read_tasks(book())
        out = io.StringIO()
        tc.write_csv(tc.build_rows(tasks, {}), out)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], ",".join(tc.COLUMNS))
        self.assertEqual(len(lines), 1 + len(tasks))

    def test_predecessors_come_before_successors(self):
        tasks = [{"row": r, "category": "g", "start": D(2026, 1, r)} for r in (1, 2, 3)]
        deps = {1: {"after": [3]}, 3: {"after": [2]}}
        self.assertEqual([t["row"] for t in tc.predecessor_first(tasks, deps)], [2, 3, 1])

    def test_time_orders_rows_when_no_dependency_does(self):
        tasks = [{"row": 1, "category": "g", "start": D(2026, 1, 1)}, {"row": 2, "category": "g", "start": D(2026, 2, 1)}]
        est = {1: ("k", (D(2026, 5, 1), None))}
        self.assertEqual([t["row"] for t in tc.predecessor_first(tasks, {}, est)], [2, 1])

    def test_categories_stay_together_in_workbook_order(self):
        tasks = [{"row": 1, "category": "a", "start": D(2026, 3, 1)}, {"row": 2, "category": "b", "start": D(2026, 1, 1)},
                 {"row": 3, "category": "a", "start": D(2026, 2, 1)}]
        self.assertEqual([t["row"] for t in tc.predecessor_first(tasks, {})], [3, 1, 2])

    def test_row_25_stays_on_equipment_ordered_and_new_equipment_milestones_have_no_row(self):
        est = tc.site_estimates("junction")
        self.assertEqual(est[25][0], "equipment-ordered")
        self.assertEqual(est[29][0], "equipment-delivered")
        self.assertNotIn("av-ordered", [k for k, _ in est.values()])
        self.assertNotIn("equipment-paid", [k for k, _ in est.values()])


if __name__ == "__main__":
    unittest.main()
