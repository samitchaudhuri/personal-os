#!/usr/bin/env python3
"""Export the opening timeline workbook to a CSV for a Gantt tool.

Each task row of the workbook becomes one CSV row with its group, category,
bar start and end, and proposed predecessors from timeline-dependencies.yaml.
Bars are the colored cells of the row. Column D is week 1, and column N of the
sheet starts B2 plus seven days times its week number, so dates come from the
anchor date in B2 and not from the formula cells, which hold no cached values
after a script saves the file. A bar's end is the last day of its last week.

With --site, rows that offsets.yaml maps to a milestone also carry that
milestone's key and the generator's estimate for the site, beside the bar.

With --teamgantt, the CSV takes TeamGantt's work breakdown structure layout
instead: a WBS # column, where 1 is the project, 1.n a group and 1.n.m a task,
and predecessors written as WBS numbers. TeamGantt's free plan holds 40 tasks,
so --skip drops optional rows and hands their predecessors to their successors.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys

import openpyxl

import milestones as ms

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BOOK = os.path.join(HERE, "..", "..", "gdrive", "private", "ULC-personal", "Development",
                            "Opening Timeline", "ULC Los Gatos Opening Timeline.xlsx")
FIRST_ROW, LAST_ROW = 6, 49
FIRST_WEEK_COL, LAST_WEEK_COL = 4, 40
# Fills that draw the grid, not a bar, and the dark line that marks opening day.
NEUTRAL = {"FFF0EEE9", "FFFCFAF5", "FFFFFFFF"}
OPENING_LINE = "FF2C2926"
COLUMNS = ["row", "task", "group", "category", "start", "end", "duration_days", "predecessors",
           "why", "milestone", "estimate_start", "estimate_end"]


def bar_weeks(ws, row):
    """Return the week numbers of the row's bar cells, week 1 being column D."""
    weeks = []
    for col in range(FIRST_WEEK_COL, LAST_WEEK_COL + 1):
        fill = ws.cell(row, col).fill
        if fill.fill_type != "solid" or fill.fgColor.type != "rgb":
            continue
        if fill.fgColor.rgb in NEUTRAL or fill.fgColor.rgb == OPENING_LINE:
            continue
        weeks.append(col - FIRST_WEEK_COL + 1)
    return weeks


def week_start(anchor, week):
    return anchor + datetime.timedelta(days=7 * week)


def read_tasks(ws):
    """Return [{row, task, group, category, start, end}] for the workbook's task rows."""
    anchor = ws["B2"].value
    if isinstance(anchor, datetime.datetime):
        anchor = anchor.date()
    if not isinstance(anchor, datetime.date):
        raise ValueError("B2 does not hold the franchise agreement date")
    tasks, group = [], None
    for row in range(FIRST_ROW, LAST_ROW + 1):
        name = (ws.cell(row, 1).value or "").strip()
        category = ws.cell(row, 3).value
        if not name:
            continue
        if category is None and not bar_weeks(ws, row):
            group = name
            continue
        weeks = bar_weeks(ws, row)
        start = end = None
        if weeks:
            start = week_start(anchor, weeks[0])
            end = week_start(anchor, weeks[-1]) + datetime.timedelta(days=6)
        tasks.append({"row": row, "task": name, "group": group, "category": category,
                      "start": start, "end": end})
    return tasks


def load_dependencies(path=None):
    path = path or os.path.join(HERE, "timeline-dependencies.yaml")
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["dependencies"]


def check_dependencies(deps, rows):
    """Raise if a dependency names a missing row or the graph has a cycle."""
    known = set(rows)
    for row, d in deps.items():
        for p in d["after"]:
            if row not in known or p not in known:
                raise ValueError(f"dependency {p} -> {row} names a row that is not a task")
    state = {}

    def visit(r, trail=()):
        if state.get(r) == "done":
            return
        if r in trail:
            raise ValueError(f"dependency cycle through row {r}")
        for p in deps.get(r, {}).get("after", []):
            visit(p, trail + (r,))
        state[r] = "done"

    for r in deps:
        visit(r)


def early_starts(tasks, deps):
    """Return [(row, predecessor)] where the template bar starts before its predecessor ends."""
    by_row = {t["row"]: t for t in tasks}
    out = []
    for t in tasks:
        for p in deps.get(t["row"], {}).get("after", []):
            pred = by_row[p]
            if t["start"] and pred["end"] and t["start"] <= pred["end"]:
                out.append((t["row"], p))
    return out


def build_rows(tasks, deps, estimates=None):
    """Return CSV rows. estimates maps a Gantt row to (key, (earliest, latest))."""
    estimates = estimates or {}
    out = []
    for t in tasks:
        d = deps.get(t["row"], {})
        key, est = estimates.get(t["row"], ("", (None, None)))
        out.append({
            "row": t["row"], "task": t["task"], "group": t["group"], "category": t["category"] or "",
            "start": t["start"].isoformat() if t["start"] else "",
            "end": t["end"].isoformat() if t["end"] else "",
            "duration_days": (t["end"] - t["start"]).days + 1 if t["start"] else "",
            "predecessors": ";".join(str(p) for p in d.get("after", [])),
            "why": d.get("why", ""),
            "milestone": key,
            "estimate_start": est[0].isoformat() if est[0] else "",
            "estimate_end": est[1].isoformat() if est[1] else "",
        })
    return out


def site_estimates(site):
    """Map each Gantt row to the milestone offsets.yaml ties to it, with the site's estimate."""
    offsets, sites = ms.load_yaml("offsets.yaml"), ms.load_yaml("sites.yaml")
    if site not in sites["sites"]:
        raise SystemExit(f"no site {site!r} in sites.yaml; have {', '.join(sites['sites'])}")
    resolved = ms.resolve(offsets, sites["sites"][site]["inputs"])
    out = {}
    for m in offsets["milestones"]:
        row = m.get("gantt_row")
        if row and row not in out:
            out[row] = (m["key"], resolved[m["key"]])
    return out


TEAMGANTT_COLUMNS = ["WBS #", "Name", "Start date", "End date", "Predecessors", "Comments"]
TEAMGANTT_FREE_TASKS = 40


def drop_rows(tasks, deps, skip):
    """Remove the skipped rows; their successors inherit their predecessors."""
    skip = set(skip)
    known = {t["row"] for t in tasks}
    if skip - known:
        raise ValueError(f"--skip names rows that are not tasks: {sorted(skip - known)}")

    def after(row):
        out = []
        for p in deps.get(row, {}).get("after", []):
            for q in (after(p) if p in skip else [p]):
                if q not in out:
                    out.append(q)
        return out

    kept = [t for t in tasks if t["row"] not in skip]
    new_deps = {t["row"]: {**deps.get(t["row"], {}), "after": after(t["row"])} for t in kept}
    return kept, new_deps


def build_teamgantt_rows(tasks, deps, project="ULC Opening Timeline"):
    """Return rows in TeamGantt's WBS layout, grouped in workbook order."""
    wbs, rows, groups = {}, [{"WBS #": "1", "Name": project}], []
    for t in tasks:
        if t["group"] not in groups:
            groups.append(t["group"])
    counts = dict.fromkeys(groups, 0)
    for t in tasks:
        counts[t["group"]] += 1
        wbs[t["row"]] = f"1.{groups.index(t['group']) + 1}.{counts[t['group']]}"
    for g, name in enumerate(groups, 1):
        rows.append({"WBS #": f"1.{g}", "Name": name})
        for t in tasks:
            if t["group"] != name:
                continue
            d = deps.get(t["row"], {})
            rows.append({
                "WBS #": wbs[t["row"]], "Name": t["task"],
                "Start date": t["start"].isoformat() if t["start"] else "",
                "End date": t["end"].isoformat() if t["end"] else "",
                "Predecessors": ";".join(wbs[p] for p in d.get("after", [])),
                "Comments": d.get("why", ""),
            })
    return rows


def write_csv(rows, fh, columns=COLUMNS):
    w = csv.DictWriter(fh, fieldnames=columns, restval="", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=DEFAULT_BOOK, help="the opening timeline workbook")
    ap.add_argument("--site", help="add the generator's estimates for this site, such as junction")
    ap.add_argument("--teamgantt", action="store_true", help="write TeamGantt's WBS import layout")
    ap.add_argument("--skip", default="", help="Gantt rows to drop, such as 13,33; used with --teamgantt")
    ap.add_argument("--out", help="CSV path; prints to stdout when omitted")
    args = ap.parse_args(argv)

    ws = openpyxl.load_workbook(args.book).worksheets[0]
    tasks = read_tasks(ws)
    deps = load_dependencies()
    check_dependencies(deps, [t["row"] for t in tasks])
    if args.skip and not args.teamgantt:
        ap.error("--skip is for --teamgantt")
    if args.teamgantt:
        skip = [int(r) for r in args.skip.split(",") if r.strip()]
        kept, kept_deps = drop_rows(tasks, deps, skip)
        rows, columns, count = build_teamgantt_rows(kept, kept_deps), TEAMGANTT_COLUMNS, len(kept)
        if count > TEAMGANTT_FREE_TASKS:
            print(f"warning: {count} tasks exceed TeamGantt's free limit of {TEAMGANTT_FREE_TASKS}",
                  file=sys.stderr)
    else:
        rows = build_rows(tasks, deps, site_estimates(args.site) if args.site else None)
        columns, count = COLUMNS, len(rows)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            write_csv(rows, fh, columns)
        print(f"wrote {count} tasks to {args.out}")
    else:
        write_csv(rows, sys.stdout, columns)
    for t in tasks:
        if not t["start"]:
            print(f"warning: row {t['row']} {t['task']!r} has no bar", file=sys.stderr)
    early = early_starts(tasks, deps)
    if early:
        print(f"note: {len(early)} bars start before a proposed predecessor ends in the template, "
              f"such as row {early[0][0]} before row {early[0][1]}", file=sys.stderr)


if __name__ == "__main__":
    main()
