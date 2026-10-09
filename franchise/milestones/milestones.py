#!/usr/bin/env python3
"""Compute a site's milestone dates from offsets.yaml and sites.yaml.

Every milestone is a date range. Inputs come from sites.yaml, and each other
milestone sits an offset range from one it names, or a phase duration from the
milestone that starts that phase, so a slip in the lease or kickoff date moves
everything downstream. The table it prints has the same
columns as the Junction milestones table in `ULC Franchise Project.md`, and
`--write` rewrites the block between that note's generated-table markers.

Flags mark estimates that pass a fixed limit: the Site Acquisition Deadline,
the studio's Opening Deadline, the GM hard stop before the owner's absence, and
milestones that fall wholly inside that absence. They also flag any phase, such
as presale-membership-sales, whose actual span falls outside its planned range.
"""
from __future__ import annotations

import argparse
import calendar
import datetime
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
START = "<!-- milestones:{site}:start -->"
END = "<!-- milestones:{site}:end -->"


def load_yaml(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def as_range(value):
    """A date becomes (d, d); a two-date list becomes (earliest, latest)."""
    if isinstance(value, (list, tuple)):
        lo, hi = value
        return (lo, hi)
    return (value, value)


def resolve(offsets, inputs):
    """Return {key: (earliest, latest)} for every milestone in offsets."""
    rows = {m["key"]: m for m in offsets["milestones"]}
    phases = {p["key"]: p for p in offsets.get("phases", [])}
    out = {}

    def visit(key, trail=()):
        if key in out:
            return out[key]
        if key in trail:
            raise ValueError(f"offset cycle through {key!r}")
        m = rows[key]
        if m.get("input"):
            if key not in inputs:
                raise ValueError(f"site gives no input for {key!r}")
            out[key] = as_range(inputs[key])
        elif "from_phase" in m and key in inputs:
            out[key] = as_range(inputs[key])
        else:
            if "from_phase" in m:
                phase = phases[m["from_phase"]]
                anchor, (lo_off, hi_off) = phase["start"], phase["duration_days"]
            else:
                anchor, (lo_off, hi_off) = m["anchor"], m["offset_days"]
            a_lo, a_hi = visit(anchor, trail + (key,))
            out[key] = (a_lo + datetime.timedelta(days=lo_off),
                        a_hi + datetime.timedelta(days=hi_off))
        return out[key]

    for key in rows:
        visit(key)
    return out


def add_months(d, n):
    month = d.month - 1 + n
    year, month = d.year + month // 12, month % 12 + 1
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def months_over(deadline, date):
    """Months or parts of a month from deadline to date, the FA's fee unit."""
    n = 0
    while add_months(deadline, n) < date:
        n += 1
    return n


def flags(resolved, limits, away):
    """Return [(key, message)] for estimates that pass a fixed limit."""
    out = []
    lease_lo, lease_hi = resolved["lease-signed"]
    sad, ext = limits["site_acquisition_deadline"], limits["site_acquisition_extended"]
    if lease_hi > ext:
        out.append(("lease-signed", f"Latest date passes even the extended Site Acquisition Deadline of {ext}"))
    elif lease_hi > sad:
        out.append(("lease-signed", f"Latest date is after the Site Acquisition Deadline of {sad}, so it needs the one-time 90-day extension to {ext}"))
    _, open_hi = resolved["soft-open"]
    if open_hi > limits["opening_deadline"]:
        n = months_over(limits["opening_deadline"], open_hi)
        fee = n * limits["opening_extension_fee_per_month"]
        out.append(("soft-open", f"Latest date is {n} months past the Opening Deadline of {limits['opening_deadline']}, about ${fee:,} if the franchisor extends"))
    seat_lo, seat_hi = resolved["gm-in-seat"]
    if seat_hi > limits["gm_hard_stop"]:
        out.append(("gm-in-seat", f"Latest date is after the {limits['gm_hard_stop']} hard stop before the owner leaves"))
    a_lo, a_hi = away
    for key, (lo, hi) in resolved.items():
        if lo >= a_lo and hi <= a_hi:
            out.append((key, f"Falls inside the owner's absence, {a_lo} to {a_hi}"))
    return out


def phase_span(phase, resolved):
    """Return (shortest, longest) days the phase actually spans between its milestones."""
    s_lo, s_hi = resolved[phase["start"]]
    e_lo, e_hi = resolved[phase["end"]]
    return ((e_lo - s_hi).days, (e_hi - s_lo).days)


def phase_pairing(phase, resolved):
    """Return the span with earliest paired to earliest and latest to latest, for display."""
    s_lo, s_hi = resolved[phase["start"]]
    e_lo, e_hi = resolved[phase["end"]]
    return tuple(sorted(((e_lo - s_lo).days, (e_hi - s_hi).days)))


def days(lo, hi):
    return f"{lo} days" if lo == hi else f"{lo} to {hi} days"


def phase_flags(offsets, resolved):
    """Return [(end_key, message)] for phases whose actual span is outside the planned range."""
    out = []
    for p in offsets.get("phases", []):
        lo, hi = p["duration_days"]
        short, long_ = phase_span(p, resolved)
        where = f"{p['key']} runs {days(short, long_)} from {p['start']} to {p['end']}"
        if short > hi:
            out.append((p["end"], f"{where}, at least {short - hi} days over its planned {days(lo, hi)}"))
        elif long_ < lo:
            out.append((p["end"], f"{where}, at least {lo - long_} days under its planned {days(lo, hi)}"))
    return out


def render_phases(offsets, resolved):
    lines = ["| Phase | From | To | Planned | Actual | Basis |",
             "| ----- | ---- | -- | ------- | ------ | ----- |"]
    for p in offsets.get("phases", []):
        lo, hi = p["duration_days"]
        actual = days(*phase_pairing(p, resolved))
        lines.append(f"| `{p['key']}` | `{p['start']}` | `{p['end']}` | {days(lo, hi)} | {actual} | {p['basis']} |")
    return "\n".join(lines)


def fmt(rng):
    lo, hi = rng
    return lo.isoformat() if lo == hi else f"{lo.isoformat()} to {hi.isoformat()}"


def render_table(offsets, resolved, site_basis=None):
    site_basis = site_basis or {}
    lines = ["| Key | Milestone | Estimate | Gantt row | Basis |",
             "| --- | --------- | -------- | --------- | ----- |"]
    for m in offsets["milestones"]:
        key = m["key"]
        row = m.get("gantt_row") or ""
        basis = site_basis.get(key, m["basis"])
        lines.append(f"| `{key}` | {m['label']} | {fmt(resolved[key])} | {row} | {basis} |")
    return "\n".join(lines)


def rewrite_note(path, site, table):
    """Replace the block between a site's markers; fail if the markers are absent."""
    start, end = START.format(site=site), END.format(site=site)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit(f"{path} has no {start} ... {end} block")
    with open(path, "w", encoding="utf-8") as f:
        f.write(pattern.sub(lambda _: f"{start}\n{table}\n{end}", text))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("site", help="site name in sites.yaml, such as junction")
    ap.add_argument("--write", metavar="NOTE", help="rewrite the site's marked block in this note")
    args = ap.parse_args(argv)

    offsets, sites = load_yaml("offsets.yaml"), load_yaml("sites.yaml")
    if args.site not in sites["sites"]:
        raise SystemExit(f"no site {args.site!r} in sites.yaml; have {', '.join(sites['sites'])}")
    site = sites["sites"][args.site]
    resolved = resolve(offsets, site["inputs"])
    table = render_table(offsets, resolved, site.get("basis"))
    if offsets.get("phases"):
        table += "\n\n" + render_phases(offsets, resolved)
    if args.write:
        rewrite_note(args.write, args.site, table)
        print(f"rewrote {args.site} block in {args.write}")
    else:
        print(table)
    for key, msg in (flags(resolved, site["limits"], sites["owner"]["away"])
                     + phase_flags(offsets, resolved)):
        print(f"flag: {key}: {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
