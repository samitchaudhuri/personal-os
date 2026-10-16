#!/usr/bin/env python3
"""Export the opening timeline workbook to a CSV for a Gantt tool.

Each task row of the workbook becomes one CSV row with its category, group,
sample bar start and end, and proposed predecessors from timeline-dependencies.yaml.
Rows stay in their categories, and within a category run in time order, by the site estimate when
there is one and else the bar, with each task after its predecessors in the category.
Bars are the colored cells of the row. Column D is week 1, and column N of the
sheet starts B2 plus seven days times its week number, so dates come from the
anchor date in B2 and not from the formula cells, which hold no cached values
after a script saves the file. A bar's end is the last day of its last week.

With --site, rows that durations.yaml maps to a milestone carry that milestone's key in brackets after its name and the
generator's earliest and latest dates for the site as start and end. The template's bar dates
are sample_start and sample_end. The duration column is the days from start to end, and the constraint column lists the durations.yaml rules
that touch the milestone, as in '45 days after 32', plus any proposed predecessor no rule covers. Rows the generator does not cover leave start and end blank.

With --teamgantt, the CSV takes TeamGantt's work breakdown structure layout
instead: a WBS # column, where 1 is the project, 1.n a group and 1.n.m a task,
and predecessors written as WBS numbers. TeamGantt's free plan holds 40 tasks.
Both layouts drop the rows in SKIP_ROWS, or the rows named by --skip, and hand
their predecessors to their successors.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
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
COLUMNS = ["id", "milestone", "department", "phase", "start", "end", "duration", "constraint",
           "sample_start", "sample_end", "sample_duration", "why"]

# Workbook rows that are not milestones: ongoing activities and borderline setup tasks. Both exports drop
# them unless --skip says otherwise, and their predecessors pass to their successors.
SKIP_ROWS = [13, 21, 33, 35, 36, 37, 40, 42, 44, 47, 48]

# The workbook's group names, shortened for the export.
PHASE_NAMES = {"Site Selection & Legal": "Site Selection", "Lease, Design & Construction": "Lease, Design & Build"}


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
            group = PHASE_NAMES.get(name, name)
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


def predecessor_first(tasks, deps, estimates=None):
    """Return the tasks grouped by category in first-seen order, each category in time order.

    Within a category, a task's time is the start of its site estimate when it has one, else its
    bar start. Each step takes the ready task, one whose predecessors in the category are all
    placed, with the earliest time, and workbook order breaks ties. A predecessor in another
    category does not hold a task back.
    """
    estimates = estimates or {}

    def when(t):
        est = estimates.get(t["row"], ("", (None, None)))[1][0]
        return est or t["start"] or datetime.date.max

    groups = []
    for t in tasks:
        if t["category"] not in groups:
            groups.append(t["category"])
    out = []
    for g in groups:
        left = [t for t in tasks if t["category"] == g]
        mine = {t["row"] for t in left}
        placed = set()
        while left:
            ready = [t for t in left
                     if all(p in placed or p not in mine for p in deps.get(t["row"], {}).get("after", []))]
            nxt = min(ready, key=when)
            left.remove(nxt)
            placed.add(nxt["row"])
            out.append(nxt)
    return out


def build_rows(tasks, deps, estimates=None, rules=None, extras=None):
    """Return CSV rows. estimates maps a Gantt row to (key, (earliest, latest)); rules maps a
    milestone key to its generator rules, as (text, rows the rule says this one comes after). extras maps
    a Gantt row to the further milestones on it, as (id, key, label, (earliest, latest)), which follow it
    as rows of their own."""
    estimates, rules, extras = estimates or {}, rules or {}, extras or {}
    out = []
    for t in tasks:
        d = deps.get(t["row"], {})
        key, est = estimates.get(t["row"], ("", (None, None)))
        texts = [r[0] for r in rules.get(key, [])]
        covered = {x for r in rules.get(key, []) for x in r[1]}
        texts += [f"after <<{p}>>" for p in d.get("after", []) if p not in covered]
        out.append({
            "id": t["row"], "milestone": f"{t['task']} ({key})" if key else t["task"],
            "department": t["category"] or "", "phase": t["group"],
            "start": est[0].isoformat() if est[0] else "",
            "end": est[1].isoformat() if est[1] else "",
            "duration": (est[1] - est[0]).days if est[0] and est[1] else "",
            "constraint": "; ".join(texts),
            "why": d.get("why", ""),
            "sample_start": t["start"].isoformat() if t["start"] else "",
            "sample_end": t["end"].isoformat() if t["end"] else "",
            "sample_duration": (t["end"] - t["start"]).days + 1 if t["start"] else "",
        })
        for xid, xkey, label, (lo, hi) in extras.get(t["row"], []):
            out.append({
                "id": xid, "milestone": f"{label} ({xkey})",
                "department": t["category"] or "", "phase": t["group"],
                "start": lo.isoformat(), "end": hi.isoformat(), "duration": (hi - lo).days,
                "constraint": "; ".join(r[0] for r in rules.get(xkey, [])),
            })
    return renumber(out)


def renumber(rows):
    """Number the rows 1..N in their final order and point every <<old id>> in a constraint at the new number."""
    new = {r["id"]: i for i, r in enumerate(rows, 1)}
    for r in rows:
        r["constraint"] = re.sub(r"<<(.+?)>>", lambda m: str(new[int(m[1]) if m[1].isdigit() else m[1]]),
                                 r["constraint"])
        r["id"] = new[r["id"]]
    return rows


def milestone_ids(durations):
    """Map each milestone key to its CSV id: the Gantt row for the first milestone on a row, then 32.1, 32.2."""
    ids, seen = {}, {}
    for m in durations["milestones"]:
        row = m.get("gantt_row")
        if not row:
            continue
        seen[row] = seen.get(row, 0) + 1
        ids[m["key"]] = row if seen[row] == 1 else f"{row}.{seen[row] - 1}"
    return ids


def milestone_rules():
    """Map each milestone key to the generator rules that date it, as (text, rows it comes after).

    A rule reads '45 days after <<32>>' on the later milestone only, where <<32>> stands for the id of the
    earlier one and build_rows swaps in its final number, from durations.yaml. A milestone with no Gantt row is named by its key, a range reads
    '14-28 days', a rule from the milestone where the row starts is left out because the duration shows it, and a not-before rule reads 'at least 10 days'.
    """
    durations = ms.load_yaml("durations.yaml")
    ids = milestone_ids(durations)
    span_from = {m["key"]: m["span_from"] for m in durations["milestones"] if m.get("span_from")}
    out = {}
    for c in ms.constraints_of(durations):
        span = (f"at least {c.lo} days" if c.hi is None else f"{c.lo} days" if c.hi == c.lo
                else f"{c.lo}-{c.hi} days")
        frm = ids.get(c.frm)
        if span_from.get(c.to) == c.frm:
            continue    # the row begins at that milestone, so its duration already says it
        mark = " (ideal)" if c.kind == "preference" else ""
        out.setdefault(c.to, []).append((f"{span} after " + (f"<<{frm}>>" if frm else c.frm) + mark,
                                         [frm] if frm else []))
    return out


def site_estimates(site):
    """Map each Gantt row to the milestone durations.yaml ties to it, with the site's estimate."""
    durations, sites = ms.load_yaml("durations.yaml"), ms.load_yaml("sites.yaml")
    if site not in sites["sites"]:
        raise SystemExit(f"no site {site!r} in sites.yaml; have {', '.join(sites['sites'])}")
    resolved = ms.resolve(durations, sites["sites"][site]["inputs"])
    out = {}
    for m in durations["milestones"]:
        row = m.get("gantt_row")
        if row and row not in out:
            lo, hi = resolved[m["key"]]
            if m.get("span_from"):
                lo = resolved[m["span_from"]][0]
            out[row] = (m["key"], (lo, hi))
    return out


def extra_milestones(site):
    """Map a Gantt row to its second and later milestones, as (id, key, label, (earliest, latest))."""
    durations, sites = ms.load_yaml("durations.yaml"), ms.load_yaml("sites.yaml")
    resolved = ms.resolve(durations, sites["sites"][site]["inputs"])
    ids, first, out = milestone_ids(durations), {}, {}
    for m in durations["milestones"]:
        row = m.get("gantt_row")
        if not row:
            continue
        if row not in first:
            first[row] = m["key"]
        else:
            out.setdefault(row, []).append((ids[m["key"]], m["key"], m["label"], resolved[m["key"]]))
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
    ap.add_argument("--skip", default=",".join(map(str, SKIP_ROWS)),
                    help="workbook rows to drop, such as 13,33; empty keeps every row (default: SKIP_ROWS)")
    ap.add_argument("--out", help="CSV path; prints to stdout when omitted")
    args = ap.parse_args(argv)

    ws = openpyxl.load_workbook(args.book).worksheets[0]
    tasks = read_tasks(ws)
    deps = load_dependencies()
    check_dependencies(deps, [t["row"] for t in tasks])
    skip = [int(r) for r in args.skip.split(",") if r.strip()]
    kept, kept_deps = drop_rows(tasks, deps, skip)
    if args.teamgantt:
        rows, columns, count = build_teamgantt_rows(kept, kept_deps), TEAMGANTT_COLUMNS, len(kept)
        if count > TEAMGANTT_FREE_TASKS:
            print(f"warning: {count} tasks exceed TeamGantt's free limit of {TEAMGANTT_FREE_TASKS}",
                  file=sys.stderr)
    else:
        est = site_estimates(args.site) if args.site else None
        dated = sorted(set(skip) & set(est or {}))
        if dated:
            raise SystemExit(f"--skip drops rows {dated} that the generator dates")
        rows = build_rows(predecessor_first(kept, kept_deps, est), kept_deps, est, milestone_rules() if est else None,
                          extra_milestones(args.site) if est else None)
        columns, count = COLUMNS, len(rows)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            write_csv(rows, fh, columns)
        print(f"wrote {count} tasks to {args.out}")
    else:
        write_csv(rows, sys.stdout, columns)
    for t in kept:
        if not t["start"]:
            print(f"warning: row {t['row']} {t['task']!r} has no bar", file=sys.stderr)
    early = early_starts(kept, kept_deps)
    if early:
        print(f"note: {len(early)} bars start before a proposed predecessor ends in the template, "
              f"such as row {early[0][0]} before row {early[0][1]}", file=sys.stderr)


if __name__ == "__main__":
    main()
