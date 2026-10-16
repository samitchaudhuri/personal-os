import csv
import datetime as dt
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

import openpyxl
from openpyxl.chart import LineChart, Reference

import ramp
import timeline_csv as tc

D = dt.date
COLUMNS = ["id", "milestone", "key", "start", "end", "duration", "rule", "preference", "why", "department", "phase",
           "sample_row", "sample_start", "sample_end", "sample_duration"]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, restval="", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def lookup(r, col):
    c = "D" if col == "F" else "E"
    return (f'=IF(D{r}="Fixed",E{r},IFERROR(INDEX(Timeline!${c}$2:${c}$100,MATCH(D{r},Timeline!$B$2:$B$100,0))+{col}{r},0))')


def make_ramp(path):
    wb = openpyxl.Workbook()
    wb.active.title = "Sites"
    s = wb["Sites"]
    s.append(["Site", "Name", "Lease sign", "Delivery", "Open"])
    s.append(["Site 1", "One"] + [f'=INDEX(Timeline!$D$2:$D$100,MATCH("{k}",Timeline!$B$2:$B$100,0))'
                                  for k in ("lease-signed", "landlord-delivery", "soft-open")])
    d = wb.create_sheet("Draws")
    d.append(["Draw ID", "Site", "Purpose", "Anchor", "Fixed date", "Start", "End", "Start date", "End date"])
    d.append(["FEE", "Site 1", "Fee", "Fixed", D(2026, 6, 15), None, None, "=E2", "=E2"])
    d.append(["BO", "Site 1", "Build-out", "construction-start", None, 30, 30, lookup(3, "F"), lookup(3, "G")])
    ramp_ws = wb.create_sheet("Ramp")
    for row in ([1, 2, 3], [4, 5, 6]):
        ramp_ws.append(row)
    chart = LineChart()
    chart.add_data(Reference(ramp_ws, min_col=1, max_col=3, min_row=1, max_row=2), from_rows=True)
    ramp_ws.add_chart(chart, "E2")
    wb.save(path)


ROWS = [
    {"id": 1, "milestone": "Lease signed", "key": "lease-signed", "start": "2026-11-30", "end": "2026-12-14"},
    {"id": 2, "milestone": "Landlord delivers", "key": "landlord-delivery", "start": "2027-02-08", "end": "2027-02-08"},
    {"id": 3, "milestone": "Construction Begins", "key": "construction-start", "start": "2027-02-08", "end": "2027-02-18"},
    {"id": 4, "milestone": "Soft open", "key": "soft-open", "start": "2027-05-31", "end": "2027-06-10"},
    {"id": 5, "milestone": "Undated task", "key": "", "start": "", "end": ""},
]


class RampCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.csv, self.xlsx = self.dir / "timeline.csv", self.dir / "ramp.xlsx"
        write_csv(self.csv, ROWS)
        make_ramp(self.xlsx)

    def tearDown(self):
        self.tmp.cleanup()


class TestSync(RampCase):
    def test_copies_the_keyed_dated_rows(self):
        self.assertEqual(ramp.sync(self.csv, self.xlsx), 4)
        ws = openpyxl.load_workbook(self.xlsx)[ramp.TIMELINE]
        got = {r[1]: (r[3].date(), r[4].date()) for r in ws.iter_rows(min_row=2, max_col=5, values_only=True) if r[1]}
        self.assertEqual(got["construction-start"], (D(2027, 2, 8), D(2027, 2, 18)))
        self.assertEqual(len(got), 4)
        self.assertEqual(ws["H2"].value, ramp.sha256(self.csv))

    def test_keeps_the_original_chart_bytes(self):
        before = zipfile.ZipFile(self.xlsx).read("xl/charts/chart1.xml")
        ramp.sync(self.csv, self.xlsx)
        z = zipfile.ZipFile(self.xlsx)
        self.assertEqual(z.read("xl/charts/chart1.xml"), before)
        self.assertEqual(len(openpyxl.load_workbook(self.xlsx)["Ramp"]._charts), 1)

    def test_a_second_sync_replaces_the_tab(self):
        ramp.sync(self.csv, self.xlsx)
        write_csv(self.csv, ROWS[:3])
        ramp.sync(self.csv, self.xlsx)
        ws = openpyxl.load_workbook(self.xlsx)[ramp.TIMELINE]
        self.assertEqual([r[1] for r in ws.iter_rows(min_row=2, max_col=2, values_only=True) if r[1]],
                         ["lease-signed", "landlord-delivery", "construction-start"])

    def test_refuses_while_excel_has_the_file_open(self):
        (self.dir / "~$ramp.xlsx").write_text("")
        with self.assertRaises(SystemExit):
            ramp.sync(self.csv, self.xlsx)


class TestCheck(RampCase):
    def test_passes_right_after_a_sync(self):
        ramp.sync(self.csv, self.xlsx)
        problems, notes = ramp.check(self.csv, self.xlsx)
        self.assertEqual(problems, [])
        self.assertIn("FEE", notes[0])

    def test_fails_when_the_csv_moves_after_the_sync(self):
        ramp.sync(self.csv, self.xlsx)
        rows = [dict(r, start="2027-03-01") if r["key"] == "construction-start" else r for r in ROWS]
        write_csv(self.csv, rows)
        problems, _ = ramp.check(self.csv, self.xlsx)
        self.assertTrue(any("construction-start" in p and "2027-03-01" in p for p in problems))
        self.assertTrue(any("changed after the last sync" in p for p in problems))

    def test_fails_when_a_draw_names_a_key_the_csv_does_not_date(self):
        ramp.sync(self.csv, self.xlsx)
        wb = openpyxl.load_workbook(self.xlsx)
        wb["Draws"]["D3"] = "permit-received"
        wb.save(self.xlsx)
        problems, _ = ramp.check(self.csv, self.xlsx)
        self.assertTrue(any("permit-received" in p and "does not date" in p for p in problems))

    def test_fails_on_a_typed_draw_date_and_a_typed_site_date(self):
        ramp.sync(self.csv, self.xlsx)
        wb = openpyxl.load_workbook(self.xlsx)
        wb["Draws"]["H3"] = D(2027, 3, 10)
        wb["Sites"]["E2"] = D(2027, 5, 31)
        wb.save(self.xlsx)
        problems, _ = ramp.check(self.csv, self.xlsx)
        self.assertTrue(any("typed date in column H" in p for p in problems))
        self.assertTrue(any("Sites!E2" in p for p in problems))

    def test_fails_without_a_timeline_tab(self):
        problems, _ = ramp.check(self.csv, self.xlsx)
        self.assertEqual(len(problems), 1)
        self.assertIn("no Timeline tab", problems[0])

    def test_timeline_rows_skip_undated_and_unkeyed_rows(self):
        self.assertEqual(sorted(ramp.timeline_rows(self.csv)),
                         ["construction-start", "landlord-delivery", "lease-signed", "soft-open"])


class TestCsvHook(RampCase):
    def conf(self, csv_path=None):
        return {"timeline_csv": csv_path or self.csv, "ramp": self.xlsx}

    def test_rewriting_the_published_csv_syncs_a_workbook_that_has_a_timeline_tab(self):
        ramp.sync(self.csv, self.xlsx)
        write_csv(self.csv, [dict(r, end="2027-06-20") if r["key"] == "soft-open" else r for r in ROWS])
        self.assertTrue(ramp.check(self.csv, self.xlsx)[0])
        with mock.patch.object(ramp, "outputs", return_value=self.conf()):
            tc.sync_ramp("junction", self.csv)
        self.assertEqual(ramp.check(self.csv, self.xlsx)[0], [])

    def test_a_csv_written_elsewhere_or_a_workbook_without_the_tab_is_left_alone(self):
        before = self.xlsx.read_bytes()
        with mock.patch.object(ramp, "outputs", return_value=self.conf()):
            tc.sync_ramp("junction", self.csv)
        other = self.dir / "other.csv"
        write_csv(other, ROWS)
        with mock.patch.object(ramp, "outputs", return_value=self.conf()):
            tc.sync_ramp("junction", other)
        self.assertEqual(self.xlsx.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
