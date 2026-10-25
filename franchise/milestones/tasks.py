#!/usr/bin/env python3
"""Keep vault task due dates on the generator's dates.

A task that delivers a milestone carries `[milestone:: key]` after its description, or `[milestone:: key, earliest]`
to take the earliest end of the key's range, since the default is the latest end, the date by which the work must be
done. `check` lists every open tagged task whose due date differs from that date and fails when there is one, and
`sync` rewrites those due dates. A task with no tag is left alone, so a task no milestone covers keeps its hand-set
date. The note path comes from `outputs.tasks` in sites.yaml.

The other direction exists for one case. A checked tagged task has the date it finished in its `✅` stamp, and when its
milestone is one a site can give, `actuals` writes that date into the site's inputs in sites.yaml as committed, so
the schedule rebases on what happened. A computed milestone is never set this way, since the generator would
recompute it on the next run.
"""
import argparse
import datetime as dt
import re
import sys
from collections import namedtuple
from pathlib import Path

import yaml

import milestones as ms
import ramp

TAG = re.compile(r"\[milestone:: *([a-z0-9-]+)(?:, *(earliest|latest))?\]")
DUE = re.compile(r"📅 (\d{4}-\d{2}-\d{2})")
ID = re.compile(r"🆔 ([a-z0-9-]+)")
OPEN = re.compile(r"^\s*- \[ \] #task")
DONE = re.compile(r"^\s*- \[x\] #task")
DONE_ON = re.compile(r"✅ (\d{4}-\d{2}-\d{2})")
DEFAULT_END = "latest"

Drift = namedtuple("Drift", "line task key end due target")


def target(dates, key, end):
    """The date a task tagged with this key and end should be due, from {key: (earliest, latest)}."""
    if key not in dates:
        raise ValueError(f"no milestone {key!r} in the generator's dates")
    return dates[key][0 if end == "earliest" else 1]


def tagged(text):
    """[(index, task id, key, end, due)] for every open task that carries a milestone tag; due is a string or None."""
    out = []
    for i, line in enumerate(text.splitlines()):
        m = TAG.search(line)
        if not (m and OPEN.match(line)):
            continue
        task, due = ID.search(line), DUE.search(line)
        out.append((i, task.group(1) if task else f"line {i + 1}", m.group(1), m.group(2) or DEFAULT_END,
                    due.group(1) if due else None))
    return out


def drifts(text, dates):
    """Every open tagged task whose due date is not the generator's date for its key and end."""
    out = []
    for i, task, key, end, due in tagged(text):
        want = target(dates, key, end).isoformat()
        if due != want:
            out.append(Drift(i + 1, task, key, end, due, want))
    return out


def sync(text, dates):
    """The text with each drifted task's due date rewritten, or a due date added when it has none."""
    lines = text.split("\n")
    for d in drifts(text, dates):
        line = lines[d.line - 1]
        lines[d.line - 1] = DUE.sub(f"📅 {d.target}", line) if d.due else f"{line} 📅 {d.target}"
    return "\n".join(lines)


def completed(text):
    """[(task id, key, date finished)] for every checked tagged task that has a completion stamp."""
    out = []
    for i, line in enumerate(text.splitlines()):
        m, done = TAG.search(line), DONE_ON.search(line)
        if m and done and DONE.match(line):
            task = ID.search(line)
            out.append((task.group(1) if task else f"line {i + 1}", m.group(1), dt.date.fromisoformat(done.group(1))))
    return out


def settable(durations):
    """The milestone keys a site can give a date for, which are its inputs and the ones marked fixable."""
    return {m["key"] for m in durations["milestones"] if m.get("input") or m.get("fixable")}


def block(lines, start):
    """The index just past the indented block that begins at lines[start]."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
        end += 1
    while not lines[end - 1].strip():
        end -= 1
    return end


def set_line(lines, start, end, key, value, comment=None):
    """Set `key: value` in the block lines[start:end], keeping its indent, and return the new end."""
    pattern = re.compile(rf"^(\s+){re.escape(key)}:")
    for i in range(start, end):
        m = pattern.match(lines[i])
        if m:
            lines[i] = f"{m.group(1)}{key}: {value}" + (f"  # {comment}" if comment else "")
            return end
    indent = re.match(r"\s*", lines[start]).group(0)
    lines.insert(end, f"{indent}{key}: {value}" + (f"  # {comment}" if comment else ""))
    return end + 1


def apply_actuals(sites_text, site, durations, done):
    """(new sites.yaml text, [message]) with each finished task's date written as a committed input of the site. A task
    whose milestone is not one a site can give, or whose date is already the input, changes nothing."""
    conf = yaml.safe_load(sites_text)["sites"][site]
    ok, changes = settable(durations), []
    lines = sites_text.split("\n")
    for task, key, date in done:
        if key not in ok:
            continue
        if conf["inputs"].get(key) == date and conf.get("status", {}).get(key) == "committed":
            continue
        top = lines.index(f"  {site}:")
        site_end = block(lines, top)
        inputs = next(i for i in range(top, site_end) if lines[i] == "    inputs:")
        set_line(lines, inputs + 1, block(lines, inputs), key, date.isoformat(), f"finished, task {task}")
        status = next(i for i in range(top, len(lines)) if lines[i] == "    status:")
        set_line(lines, status + 1, block(lines, status), key, "committed")
        changes.append(f"{key}: {conf['inputs'].get(key, 'not given')} becomes {date} from task {task}")
    return "\n".join(lines), changes


def take_actuals(site):
    """Write the finished tagged tasks' dates into sites.yaml, and return the messages."""
    sites = Path(ms.HERE) / "sites.yaml"
    note = ramp.outputs(site).get("tasks")
    if note is None:
        return []
    new, changes = apply_actuals(sites.read_text(encoding="utf-8"), site, ms.load_yaml("durations.yaml"),
                                 completed(note.read_text(encoding="utf-8")))
    if changes:
        sites.write_text(new, encoding="utf-8")
    return changes


def sync_note(site, dates):
    """Rewrite the drifted due dates in the site's tasks note, when sites.yaml names one. Returns how many moved."""
    note = ramp.outputs(site).get("tasks")
    if note is None:
        return 0
    text = note.read_text(encoding="utf-8")
    moved = len(drifts(text, dates))
    if moved:
        note.write_text(sync(text, dates), encoding="utf-8")
    return moved


def describe(d):
    return (f"{d.task}: due {d.due or 'not set'}, but {d.key} ({d.end}) is {d.target}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("check", "sync", "actuals"))
    ap.add_argument("site", help="site name in sites.yaml, such as junction")
    ap.add_argument("--note", help="the note to read, in place of outputs.tasks")
    args = ap.parse_args(argv)

    sites = ms.load_yaml("sites.yaml")
    if args.site not in sites["sites"]:
        raise SystemExit(f"no site {args.site!r} in sites.yaml; have {', '.join(sites['sites'])}")
    if args.command == "actuals":
        changes = take_actuals(args.site)
        print("\n".join(changes) or "no finished task changes an input")
        return
    note = Path(args.note).expanduser() if args.note else ramp.outputs(args.site).get("tasks")
    if note is None:
        raise SystemExit(f"no outputs.tasks for {args.site!r} in sites.yaml and no --note given")
    text = note.read_text(encoding="utf-8")
    dates = ms.solve(ms.load_yaml("durations.yaml"), sites["sites"][args.site]["inputs"]).ranges
    try:
        found = drifts(text, dates)
    except ValueError as e:
        raise SystemExit(str(e))
    for d in found:
        print(describe(d))
    if args.command == "check":
        print(f"{len(tagged(text))} tagged tasks, {len(found)} off the generator")
        sys.exit(1 if found else 0)
    if found:
        note.write_text(sync(text, dates), encoding="utf-8")
    print(f"moved {len(found)} due dates in {note}")


if __name__ == "__main__":
    main()
