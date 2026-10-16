"""Keep the funding ramp workbook on the opening timeline CSV.

The ramp's Draws tab names a milestone key and day offsets for every draw the timeline dates, and a Timeline tab
holds the CSV's keyed rows for it to look up. `sync` copies the CSV into the Timeline tab and `check` fails when the
workbook no longer agrees with the CSV, so a draw cannot sit on a date the timeline has moved. The paths come from
`outputs` in sites.yaml.
"""
import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl

import milestones as ms

TIMELINE = "Timeline"
LOOKUP_LAST = 100                  # the lookup formulas read Timeline rows 2 to this row
LEGACY_ANCHORS = {"Fixed", "Lease sign", "Delivery", "Open"}
SITE_ANCHORS = {"C": "lease-signed", "D": "landlord-delivery", "E": "soft-open"}   # Sites tab columns on Site 1's row
DATE_FORMAT = "yyyy-mm-dd"


def outputs(site):
    """The CSV and ramp paths for a site from sites.yaml, with ~ expanded."""
    conf = ms.load_yaml("sites.yaml")["sites"][site].get("outputs") or {}
    return {k: Path(v).expanduser() for k, v in conf.items()}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timeline_rows(csv_path):
    """Keyed, dated rows of the CSV as {key: (id, milestone, start, end)}."""
    out = {}
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["key"] and r["start"] and r["end"]:
                out[r["key"]] = (int(r["id"]), r["milestone"],
                                 dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"]))
    return out


def as_date(value):
    return value.date() if isinstance(value, dt.datetime) else value if isinstance(value, dt.date) else None


# ---- sync -------------------------------------------------------------------------------------------------

def sync(csv_path, xlsx_path, recalc=False):
    """Copy the CSV's keyed rows into the workbook's Timeline tab, keeping its charts and everything else."""
    xlsx_path = Path(xlsx_path)
    lock = xlsx_path.with_name(f"~${xlsx_path.name}")
    if lock.exists():
        raise SystemExit(f"{xlsx_path.name} is open in Excel ({lock.name} exists); close it and rerun")
    rows = timeline_rows(csv_path)
    wb = openpyxl.load_workbook(xlsx_path)
    if TIMELINE in wb.sheetnames:
        del wb[TIMELINE]
    ws = wb.create_sheet(TIMELINE)
    ws.append(["Id", "Key", "Milestone", "Start", "End"])
    for key, (i, name, start, end) in sorted(rows.items(), key=lambda kv: kv[1][0]):
        ws.append([i, key, name, start, end])
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=5):
        for c in row:
            c.number_format = DATE_FORMAT
    meta = [("Source", Path(csv_path).name), ("CSV sha256", sha256(csv_path)),
            ("Synced", dt.datetime.now().replace(microsecond=0)),
            ("Do not type here", "ramp.py sync rewrites this tab from the CSV; the Draws tab looks up Key, Start and End")]
    for n, (label, value) in enumerate(meta, 1):
        ws.cell(n, 7, label)
        ws.cell(n, 8, value)
    for col, width in zip("ABCDEGH", (6, 34, 52, 12, 12, 18, 66)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    wb.calculation.fullCalcOnLoad = True
    originals = zipfile.ZipFile(xlsx_path)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False, dir=xlsx_path.parent) as tmp:
        tmp_path = Path(tmp.name)
    try:
        wb.save(tmp_path)
        restore_charts(originals, tmp_path)
        originals.close()
        os.replace(tmp_path, xlsx_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    if recalc:
        recalculate(xlsx_path)
    return len(rows)


def restore_charts(original, new_path):
    """openpyxl rewrites charts and loses some of their formatting, so put the original chart parts back."""
    parts = {n: original.read(n) for n in original.namelist()
             if re.fullmatch(r"xl/(charts/[^/]+\.xml|drawings/drawing\d+\.xml|drawings/_rels/drawing\d+\.xml\.rels)", n)}
    if not parts:
        return
    with zipfile.ZipFile(new_path) as z:
        present = set(z.namelist())
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    missing = set(parts) - present
    if missing:
        raise SystemExit(f"the rewritten workbook lacks chart parts {sorted(missing)}; the original is untouched")
    with zipfile.ZipFile(new_path, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            z.writestr(info, parts.get(info.filename, data))


def recalculate(xlsx_path):
    """Open the workbook in Excel so it recalculates and stores fresh values, then save and close it."""
    script = f'''tell application "Microsoft Excel"
  set wb to open workbook workbook file name POSIX file "{Path(xlsx_path).resolve()}"
  calculate full
  save wb
  close wb saving no
end tell'''
    done = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    if done.returncode:
        print(f"warning: Excel could not recalculate the ramp ({done.stderr.strip()}); it recalculates when opened",
              file=sys.stderr)


# ---- check ------------------------------------------------------------------------------------------------

def check(csv_path, xlsx_path):
    """Return (problems, notes) comparing the workbook with the CSV."""
    rows = timeline_rows(csv_path)
    wb = openpyxl.load_workbook(xlsx_path)
    cached = openpyxl.load_workbook(xlsx_path, data_only=True)
    problems, notes = [], []
    if TIMELINE not in wb.sheetnames:
        return [f"the workbook has no {TIMELINE} tab; run ramp.py sync"], notes
    tl = wb[TIMELINE]
    stored = {r[1]: (as_date(r[3]), as_date(r[4])) for r in tl.iter_rows(min_row=2, values_only=True) if r[1]}
    for key, (_, _, start, end) in rows.items():
        if key not in stored:
            problems.append(f"Timeline tab lacks {key}, which the CSV dates {start} to {end}")
        elif stored[key] != (start, end):
            problems.append(f"Timeline tab has {key} at {stored[key][0]} to {stored[key][1]} but the CSV says {start} to {end}")
    for key in stored.keys() - rows.keys():
        problems.append(f"Timeline tab has {key}, which the CSV no longer dates")
    if tl["H2"].value != sha256(csv_path):
        problems.append("the CSV changed after the last sync, so the Timeline tab is stale")

    sites = wb["Sites"]
    for col in SITE_ANCHORS:
        v = sites[f"{col}2"].value
        if not (isinstance(v, str) and v.startswith("=") and "Timeline!" in v):
            problems.append(f"Sites!{col}2 holds a typed {sites[f'{col}1'].value} date; it should look up {SITE_ANCHORS[col]}")

    draws, vals = wb["Draws"], cached["Draws"]
    fixed = []
    for r in range(2, draws.max_row + 1):
        ident, anchor = draws.cell(r, 1).value, draws.cell(r, 4).value
        if not ident or not anchor or str(ident).startswith("Amounts"):
            continue
        if anchor in LEGACY_ANCHORS:
            if anchor == "Fixed" and str(draws.cell(r, 2).value) == "Site 1":
                fixed.append(f"{ident} {as_date(draws.cell(r, 5).value)}")
            continue
        if anchor not in rows:
            problems.append(f"draw {ident} anchors to {anchor}, which the CSV does not date")
            continue
        f, g = draws.cell(r, 6).value or 0, draws.cell(r, 7).value or 0
        _, _, start, end = rows[anchor]
        want = (start + dt.timedelta(days=f), end + dt.timedelta(days=g))
        for col, expect in ((8, want[0]), (9, want[1])):
            formula = draws.cell(r, col).value
            if not (isinstance(formula, str) and "Timeline!" in formula):
                problems.append(f"draw {ident} has a typed date in column {'HI'[col - 8]}; it should look up {anchor}")
            got = as_date(vals.cell(r, col).value)
            if got is not None and got != expect:
                problems.append(f"draw {ident} shows {got} in column {'HI'[col - 8]} but {anchor} puts it at {expect}; "
                                "open the workbook in Excel to recalculate")
    if fixed:
        notes.append("Site 1 draws on typed dates, which no milestone moves: " + ", ".join(fixed))
    return problems, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["sync", "check"])
    ap.add_argument("--site", default="junction")
    ap.add_argument("--csv", help="timeline CSV; default is outputs.timeline_csv in sites.yaml")
    ap.add_argument("--ramp", help="ramp workbook; default is outputs.ramp in sites.yaml")
    ap.add_argument("--recalc", action="store_true", help="after a sync, recalculate the workbook in Excel")
    ap.add_argument("--skip-missing", action="store_true", help="with check, exit quietly when a file is absent, as when Drive is not mounted")
    args = ap.parse_args(argv)
    conf = outputs(args.site)
    csv_path, ramp = Path(args.csv) if args.csv else conf.get("timeline_csv"), Path(args.ramp) if args.ramp else conf.get("ramp")
    if not csv_path or not ramp:
        raise SystemExit(f"set outputs.timeline_csv and outputs.ramp for {args.site} in sites.yaml, or pass --csv and --ramp")
    if args.command == "sync":
        print(f"synced {sync(csv_path, ramp, args.recalc)} milestones from {csv_path.name} into {ramp.name}")
        return
    if args.skip_missing and not (csv_path.exists() and ramp.exists()):
        print(f"skipped: {csv_path if not csv_path.exists() else ramp} is not available")
        return
    problems, notes = check(csv_path, ramp)
    for n in notes:
        print(f"note: {n}")
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    if problems:
        raise SystemExit(f"{len(problems)} problem(s): the ramp does not follow the timeline; run ramp.py sync")
    print(f"ok: {ramp.name} follows {csv_path.name}")


if __name__ == "__main__":
    main()
