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
        self.assertEqual(rows[0]["duration_days"], 21)
        self.assertEqual((rows[0]["milestone"], rows[0]["estimate_start"]), ("some-key", "2026-08-01"))
        self.assertEqual((rows[1]["predecessors"], rows[1]["start"]), ("7", ""))

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


if __name__ == "__main__":
    unittest.main()
