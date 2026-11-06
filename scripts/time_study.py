#!/usr/bin/env python3
"""Quadrant time study from the daily plan table.

The plan table in a daily note carries Quadrant, Start and End columns. This
script totals minutes per quadrant, checks the log for skipped entries, and
keeps one row per day in vault/Agent/Workflows/Time Study.md so the numbers
outlive the daily notes that the weekly review deletes.

    time_study.py check  vault/Daily/2026-11-06.md [--window 06:00-21:00]
    time_study.py log    vault/Daily/2026-11-06.md [--window ...] [--dry-run]
    time_study.py week   --from 2026-10-26 --to 2026-10-30

Dailies written before the switch have no Quadrant column. For those, `check`
and `log` fall back to the old Action Diary table and count each tagged row as
30 minutes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

QUADS = ["Demand", "Business", "Distraction", "Delusion"]
TARGETS = {"Demand": 60, "Business": 20, "Distraction": 10, "Delusion": 10}
GAP_MIN = 15
DIARY_SLOT = 30
REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "vault" / "Agent" / "Workflows" / "Time Study.md"
LEDGER_COLS = ["Date", *QUADS, "Off", "Window", "Source", "Flags"]
SUMMARY_MARK = "## Summary"
RAW_MARK = "## Raw Log"


# ---------------------------------------------------------------- parsing

def split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cells) and any(cells)


def section(lines: list[str], heading_re: str) -> list[str]:
    start = None
    for i, line in enumerate(lines):
        if re.match(heading_re, line):
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if re.match(r"^## ", line):
            break
        out.append(line)
    return out


def tables(lines: list[str]) -> list[list[list[str]]]:
    found: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            cells = split_row(line)
            if not is_separator(cells):
                current.append(cells)
        elif current:
            found.append(current)
            current = []
    if current:
        found.append(current)
    return found


def first_table(lines: list[str], needs: tuple[str, ...] = ()) -> list[list[str]]:
    """First table whose header mentions every word in `needs`."""
    for t in tables(lines):
        head = " ".join(t[0]).lower()
        if all(w in head for w in needs):
            return t
    return []


def parse_clock(raw: str) -> tuple[int, bool] | None:
    """Minutes since midnight and whether an hour of 1 to 5 was read as PM."""
    s = re.sub(r"[*~_`]", "", raw).strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([ap])?m?", s, re.I)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2])
    ap = (m[3] or "").lower()
    if mi > 59 or h > 24:
        return None
    assumed = False
    if ap == "p" and h < 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 5:
        h += 12
        assumed = True
    return h * 60 + mi, assumed


def parse_duration(raw: str) -> int | None:
    m = re.search(r"(\d+)\s*h(?:\s*(\d+)\s*m)?|(\d+)\s*m", raw)
    if not m:
        return None
    if m[1]:
        return int(m[1]) * 60 + int(m[2] or 0)
    return int(m[3])


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clean_label(task: str) -> str:
    s = re.sub(r"\[\[[^\]]*?\\?\|([^\]]*)\]\]", r"\1", task)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"`[^`]*`", "", s)
    s = re.sub(r"[*~✅]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    return s[:60]


def canon_quadrant(raw: str) -> tuple[str | None, bool]:
    """Return (canonical name or None, valid). Empty is (None, True)."""
    word = re.sub(r"[*_`]", "", raw).strip().split(" ")[0].lower() if raw.strip() else ""
    if not word:
        return None, True
    for q in QUADS:
        if word == q.lower():
            return q, True
    if word == "off":
        return "Off", True
    return None, False


# --------------------------------------------------------------- analysis

@dataclass
class Row:
    label: str
    num: str
    start: int
    end: int
    quad: str | None
    est: int | None

    @property
    def minutes(self) -> int:
        return self.end - self.start


@dataclass
class Analysis:
    day: dt.date
    source: str
    minutes: dict[str, int] = field(default_factory=lambda: {q: 0 for q in [*QUADS, "Off"]})
    untagged: int = 0
    rows: list[Row] = field(default_factory=list)
    window: tuple[int, int] = (0, 0)
    covered: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)
    overlaps: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    not_executed: int = 0

    @property
    def window_minutes(self) -> int:
        return self.window[1] - self.window[0]

    @property
    def logged(self) -> int:
        return sum(self.minutes[q] for q in QUADS)

    @property
    def clean(self) -> bool:
        return not (self.gaps or self.overlaps or self.issues)


def parse_window(spec: str | None) -> tuple[int, int] | None:
    if not spec:
        return None
    a, _, b = spec.partition("-")
    pa, pb = parse_clock(a), parse_clock(b)
    if not pa or not pb or pb[0] <= pa[0]:
        raise SystemExit(f"bad --window {spec!r}, expected HH:MM-HH:MM")
    return pa[0], pb[0]


def day_of(path: Path) -> dt.date:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
    if not m:
        raise SystemExit(f"{path.name}: filename must start with YYYY-MM-DD")
    return dt.date.fromisoformat(m[1])


def merge_and_gaps(rows: list[Row], window: tuple[int, int] | None, a: Analysis) -> None:
    ordered = sorted(rows, key=lambda r: (r.start, r.end))
    merged: list[list[int]] = []
    top: Row | None = None
    for r in ordered:
        if top and r.start < top.end:
            a.overlaps.append(
                f"{clock(r.start)} {r.label} starts {min(top.end, r.end) - r.start}m "
                f"before {top.label} ends at {clock(top.end)}"
            )
        if merged and r.start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], r.end)
        else:
            merged.append([r.start, r.end])
        if top is None or r.end > top.end:
            top = r
    ws = min(window[0], merged[0][0]) if window else merged[0][0]
    we = max(window[1], merged[-1][1]) if window else merged[-1][1]
    a.window = (ws, we)
    a.covered = sum(e - s for s, e in merged)
    edges = [ws, *[x for s, e in merged for x in (s, e)], we]
    for i in range(0, len(edges), 2):
        s, e = edges[i], edges[i + 1]
        if e - s > GAP_MIN:
            a.gaps.append((s, e))


def analyze_plan(lines: list[str], day: dt.date, window: tuple[int, int] | None) -> Analysis | None:
    table = first_table(section(lines, r"^##\s+.*Today.s Plan"), ("quadrant", "start", "end"))
    if not table:
        return None
    head = [c.lower().strip("* ") for c in table[0]]

    def col(*names: str) -> int | None:
        for i, h in enumerate(head):
            if any(h.startswith(n) for n in names):
                return i
        return None

    i_task, i_start, i_end, i_quad = col("task"), col("start"), col("end"), col("quadrant")
    if None in (i_task, i_start, i_end, i_quad):
        return None
    i_num, i_time, i_est = col("#"), col("time"), col("est")
    a = Analysis(day=day, source="plan")
    usable: list[Row] = []

    def cell(cells: list[str], i: int | None) -> str:
        return cells[i] if i is not None and i < len(cells) else ""

    for n, cells in enumerate(table[1:], start=1):
        task, time_cell = cell(cells, i_task), cell(cells, i_time).lower()
        low = task.lower()
        if "~~" in task or "cancelled" in low or "skipped by choice" in low or "deferred" in time_cell:
            continue
        num = cell(cells, i_num) or "--"
        label = clean_label(task) or f"row {n}"
        who = f"{'#' + num if num not in ('--', '') else 'row ' + str(n)} {label}"
        raw_s, raw_e = cell(cells, i_start).strip(), cell(cells, i_end).strip()
        empty = lambda v: v in ("", "—", "-")  # noqa: E731
        ps = None if empty(raw_s) else parse_clock(raw_s)
        pe = None if empty(raw_e) else parse_clock(raw_e)
        done = "✅" in task or "done" in time_cell
        if empty(raw_s) and empty(raw_e):
            if done:
                a.issues.append(f"{who}: marked done but has no Start and End")
            elif "**" in task:
                a.issues.append(f"{who}: timed meeting has no Start and End")
            else:
                a.not_executed += 1
            continue
        if (not empty(raw_s) and ps is None) or (not empty(raw_e) and pe is None):
            a.issues.append(f"{who}: cannot read times {raw_s!r} to {raw_e!r}, use HH:MM")
            continue
        if ps is None or pe is None:
            a.issues.append(f"{who}: needs both Start and End, found {raw_s or '—'} and {raw_e or '—'}")
            continue
        if ps[1]:
            a.notes.append(f"{who}: Start {raw_s} read as {clock(ps[0])}")
        if pe[1]:
            a.notes.append(f"{who}: End {raw_e} read as {clock(pe[0])}")
        if pe[0] <= ps[0]:
            a.issues.append(f"{who}: End {clock(pe[0])} is not after Start {clock(ps[0])}")
            continue
        quad, valid = canon_quadrant(cell(cells, i_quad))
        if not valid:
            a.issues.append(f"{who}: quadrant {cell(cells, i_quad)!r} is not Demand, Business, Distraction, Delusion or Off")
        elif quad is None:
            a.issues.append(f"{who}: {clock(ps[0])} to {clock(pe[0])} has no quadrant")
        est = parse_duration(cell(cells, i_est)) if i_est is not None else None
        row = Row(label, num, ps[0], pe[0], quad, est)
        usable.append(row)
        if quad:
            a.minutes[quad] += row.minutes
        else:
            a.untagged += row.minutes
    a.rows = sorted(usable, key=lambda r: r.start)
    if usable:
        merge_and_gaps(usable, window, a)
    else:
        a.issues.append("no row has a Start and End")
    return a


def analyze_diary(lines: list[str], day: dt.date) -> Analysis | None:
    table = first_table(section(lines, r"^##\s+Action Diary"), ("time", "quadrant"))
    if not table:
        return None
    head = [c.lower() for c in table[0]]
    if "quadrant" not in head or "time" not in head:
        return None
    i_t, i_q = head.index("time"), head.index("quadrant")
    a = Analysis(day=day, source="diary")
    slots: list[int] = []
    for cells in table[1:]:
        if i_q >= len(cells) or not cells[i_q].strip():
            continue
        quad, valid = canon_quadrant(cells[i_q])
        t = parse_clock(cells[i_t]) if i_t < len(cells) else None
        if not valid or quad is None:
            a.issues.append(f"{cells[i_t] if i_t < len(cells) else '?'}: quadrant {cells[i_q]!r} is not valid")
            continue
        a.minutes[quad] += DIARY_SLOT
        if t:
            slots.append(t[0])
    if slots:
        a.window = (min(slots), max(slots) + DIARY_SLOT)
        a.covered = len(slots) * DIARY_SLOT
    elif not any(a.minutes.values()):
        a.issues.append("the Action Diary has no tagged rows")
    a.notes.append("Counted from the old Action Diary at 30 minutes a row.")
    return a


def analyze_file(path: Path, window: tuple[int, int] | None) -> Analysis:
    lines = path.read_text(encoding="utf-8").splitlines()
    day = day_of(path)
    result = analyze_plan(lines, day, window) or analyze_diary(lines, day)
    if result is None:
        raise SystemExit(f"{path.name}: no plan table with Quadrant, Start and End, and no Action Diary table")
    return result


# --------------------------------------------------------------- evidence

def file_activity(vault: Path, day: dt.date, skip: Path) -> list[tuple[int, str]]:
    found = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if not f.endswith(".md"):
                continue
            p = Path(root) / f
            if p.resolve() == skip.resolve():
                continue
            try:
                m = dt.datetime.fromtimestamp(p.stat().st_mtime)
            except OSError:
                continue
            if m.date() == day:
                found.append((m.hour * 60 + m.minute, p.stem))
    return sorted(found)


def commits(day: dt.date, s: int, e: int) -> list[str]:
    since, until = f"{day} {clock(s)}", f"{day} {clock(e)}"
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "log", f"--since={since}", f"--until={until}", "--format=%h %s"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line[:70] for line in out.splitlines() if line.strip()]


# ----------------------------------------------------------------- report

def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def report(a: Analysis, path: Path, evidence: bool) -> str:
    out = [f"{a.day} · {a.source} table · window {clock(a.window[0])}–{clock(a.window[1])} ({a.window_minutes}m)" if a.window_minutes
           else f"{a.day} · {a.source} table"]
    out.append("```")
    for q in QUADS:
        out.append(f"{q:<12}{a.minutes[q]:>5}m {pct(a.minutes[q], a.logged):>7}   target {TARGETS[q]}%")
    out.append(f"{'Off':<12}{a.minutes['Off']:>5}m")
    if a.untagged:
        out.append(f"{'Untagged':<12}{a.untagged:>5}m")
    if a.window_minutes:
        out.append(f"Covered {a.covered}m of {a.window_minutes}m = {pct(a.covered, a.window_minutes)}")
    out.append("```")
    if a.rows:
        out.append("Row minutes, for velocity:")
        for r in a.rows:
            est = f"est {r.est}m" if r.est else "est —"
            out.append(f"  {clock(r.start)}–{clock(r.end)} {r.minutes:>3}m  {est:<9} {r.quad or '?':<11} #{r.num} {r.label}")
    if a.not_executed:
        out.append(f"Not executed: {a.not_executed} plan rows have no Start and End.")
    if a.gaps:
        out.append(f"Gaps over {GAP_MIN}m:")
        files = file_activity(path.parent.parent, a.day, path) if evidence else []
        for s, e in a.gaps:
            line = f"  {clock(s)}–{clock(e)} ({e - s}m)"
            if evidence:
                names = [n for t, n in files if s <= t <= e][:6]
                cms = commits(a.day, s, e)[:3]
                if names:
                    line += "  files touched: " + "; ".join(names)
                if cms:
                    line += "  commits: " + "; ".join(cms)
            out.append(line)
        out.append("  Fill each gap, or add an Off row to close it on purpose.")
    for o in a.overlaps:
        out.append(f"Overlap: {o}")
    for i in a.issues:
        out.append(f"Issue: {i}")
    for n in a.notes:
        out.append(f"Note: {n}")
    if a.clean:
        out.append("Clean: no gaps, overlaps or issues.")
    return "\n".join(out)


def flags_for(a: Analysis) -> str:
    parts = []
    if a.gaps:
        parts.append(f"{len(a.gaps)} gaps {sum(e - s for s, e in a.gaps)}m")
    if a.overlaps:
        parts.append(f"{len(a.overlaps)} overlaps")
    if a.issues:
        parts.append(f"{len(a.issues)} issues")
    if a.untagged:
        parts.append(f"{a.untagged}m untagged")
    return "; ".join(parts) or "clean"


# ----------------------------------------------------------------- ledger

def read_ledger(path: Path) -> tuple[str, list[dict[str, str]]]:
    if not path.exists():
        return "# Time Study\n", []
    text = path.read_text(encoding="utf-8")
    head = text.split(f"\n{SUMMARY_MARK}")[0].rstrip() + "\n"
    raw = text.split(f"\n{RAW_MARK}", 1)
    entries = []
    if len(raw) == 2:
        tbl = first_table(raw[1].splitlines(), ("date",))
        if tbl:
            names = tbl[0]
            for cells in tbl[1:]:
                entries.append({n: (cells[i] if i < len(cells) else "") for i, n in enumerate(names)})
    return head, entries


def mins(e: dict[str, str], key: str) -> int:
    try:
        return int(e.get(key, "0") or 0)
    except ValueError:
        return 0


def totals(entries: list[dict[str, str]]) -> dict[str, int]:
    t = {q: sum(mins(e, q) for e in entries) for q in QUADS}
    t["Off"] = sum(mins(e, "Off") for e in entries)
    t["Window"] = sum(mins(e, "Window") for e in entries)
    t["Days"] = len(entries)
    return t


def render_summary(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "_No days logged yet._"
    latest = max(dt.date.fromisoformat(e["Date"]) for e in entries)

    def within(days: int) -> list[dict[str, str]]:
        cut = latest - dt.timedelta(days=days - 1)
        return [e for e in entries if dt.date.fromisoformat(e["Date"]) >= cut]

    periods = [("last 7d", totals(within(7))), ("last 28d", totals(within(28))), ("all time", totals(entries))]
    lines = [f"{'':<13}" + "".join(f"{n:>10}" for n, _ in periods) + f"{'target':>9}"]
    for q in QUADS:
        row = f"{q:<13}"
        for _, t in periods:
            row += f"{pct(t[q], sum(t[x] for x in QUADS)):>10}"
        lines.append(row + f"{TARGETS[q]:>8}%")
    lines.append(f"{'Days':<13}" + "".join(f"{t['Days']:>10}" for _, t in periods))
    lines.append(f"{'Logged hrs':<13}" + "".join(f"{sum(t[x] for x in QUADS) / 60:>10.1f}" for _, t in periods))
    lines.append(f"{'Coverage':<13}" + "".join(
        f"{pct(sum(t[x] for x in QUADS) + t['Off'], t['Window']):>10}" for _, t in periods))
    return f"_Through {latest}. Shares are of tagged minutes and exclude Off. Coverage is tagged plus Off minutes over the logged window._\n\n```\n" + "\n".join(lines) + "\n```"


def write_ledger(path: Path, head: str, entries: list[dict[str, str]]) -> None:
    entries = sorted(entries, key=lambda e: e["Date"])
    rows = ["| " + " | ".join(LEDGER_COLS) + " |", "|" + "---|" * len(LEDGER_COLS)]
    for e in entries:
        rows.append("| " + " | ".join(str(e.get(c, "")) for c in LEDGER_COLS) + " |")
    body = f"{head}\n{SUMMARY_MARK}\n\n{render_summary(entries)}\n\n{RAW_MARK}\n\n" + "\n".join(rows) + "\n"
    path.write_text(body, encoding="utf-8")


def entry_for(a: Analysis) -> dict[str, str]:
    e = {"Date": a.day.isoformat(), "Off": str(a.minutes["Off"]), "Window": str(a.window_minutes),
         "Source": a.source, "Flags": flags_for(a)}
    for q in QUADS:
        e[q] = str(a.minutes[q])
    return e


def upsert(entries: list[dict[str, str]], new: dict[str, str]) -> list[dict[str, str]]:
    return [e for e in entries if e["Date"] != new["Date"]] + [new]


def week_report(entries: list[dict[str, str]], start: dt.date, end: dt.date) -> str:
    def span(s: dt.date, e: dt.date) -> list[dict[str, str]]:
        return [x for x in entries if s <= dt.date.fromisoformat(x["Date"]) <= e]

    cur = span(start, end)
    if not cur:
        return f"No ledger rows between {start} and {end}."
    length = (end - start).days + 1
    prior = span(start - dt.timedelta(days=length), start - dt.timedelta(days=1))
    t, p = totals(cur), totals(prior)
    tl, pl = sum(t[q] for q in QUADS), sum(p[q] for q in QUADS)
    lines = [f"{'':<13}{'min':>6}{'share':>9}{'target':>8}{'last wk':>9}"]
    for q in QUADS:
        lines.append(f"{q:<13}{t[q]:>6}{pct(t[q], tl):>9}{TARGETS[q]:>7}%{pct(p[q], pl) if pl else 'n/a':>9}")
    out = [f"{start} to {end}: {t['Days']} days, {tl / 60:.1f} tagged hours, "
           f"coverage {pct(tl + t['Off'], t['Window'])}.", "```", *lines, "```"]
    odd = [x for x in cur if x.get("Flags") not in ("clean", "")]
    for x in odd:
        out.append(f"{x['Date']} ({x['Source']}): {x['Flags']}")
    return "\n".join(out)


# -------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "log"):
        p = sub.add_parser(name)
        p.add_argument("daily", type=Path)
        p.add_argument("--window", help="HH:MM-HH:MM; default is first Start to last End")
        p.add_argument("--no-evidence", action="store_true", help="skip the file and commit lookup for gaps")
        p.add_argument("--ledger", type=Path, default=LEDGER)
        if name == "log":
            p.add_argument("--dry-run", action="store_true")
    w = sub.add_parser("week")
    w.add_argument("--from", dest="start", required=True, type=dt.date.fromisoformat)
    w.add_argument("--to", dest="end", required=True, type=dt.date.fromisoformat)
    w.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)

    if args.cmd == "week":
        _, entries = read_ledger(args.ledger)
        print(week_report(entries, args.start, args.end))
        return 0

    a = analyze_file(args.daily, parse_window(args.window))
    print(report(a, args.daily, evidence=not args.no_evidence))
    if args.cmd == "check":
        return 0 if a.clean else 1
    head, entries = read_ledger(args.ledger)
    new = entry_for(a)
    if args.dry_run:
        print(f"Would write: {new}")
        return 0
    write_ledger(args.ledger, head, upsert(entries, new))
    print(f"Ledger row for {a.day} written ({new['Flags']}). Rerun after fixing the log to replace it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
