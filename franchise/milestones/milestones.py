#!/usr/bin/env python3
"""Compute a site's milestone dates from durations.yaml and sites.yaml.

Every milestone is a date range. Inputs come from sites.yaml, and each other
milestone sits a duration range from one it names, or from the latest of several
it names, or a phase duration from the milestone that starts that phase, so a slip in the lease or kickoff date moves
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
from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
START = "<!-- milestones:{site}:start -->"
END = "<!-- milestones:{site}:end -->"


def parse_yaml(text):
    """Load YAML, reading a duration with no earliest date, such as [,-14], as [null,-14]."""
    return yaml.safe_load(re.sub(r"(duration_days:\s*)\[\s*,", r"\1[null,", text))


def load_yaml(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return parse_yaml(f.read())


def as_range(value):
    """A date becomes (d, d); a two-date list becomes (earliest, latest)."""
    if isinstance(value, (list, tuple)):
        lo, hi = value
        return (lo, hi)
    return (value, value)


KINDS = ("estimate", "requirement", "preference")
MAX_PASSES = 5000


@dataclass(frozen=True)
class Constraint:
    """A rule: `to` is dated from `from` by a duration of [lo, hi] days; None means no earliest or no latest date."""
    frm: str
    to: str
    lo: Optional[int]
    hi: Optional[int]
    kind: str
    name: str
    order: int
    phase: Optional[str] = None

    @property
    def not_before(self):
        return self.hi is None

    @property
    def pins(self):
        """A rule with no latest date starts its target as soon as it allows, unless another rule bounds it."""
        return self.not_before


@dataclass(frozen=True)
class Fixed:
    """The source of a range end a site gave."""
    key: str


@dataclass(frozen=True)
class Bound:
    """One end of a milestone's range, the rule that set it, and the end of the source it came from."""
    key: str
    side: str       # "lo" is no earlier than, "hi" is no later than
    at: int
    rule: object
    via: Optional["Bound"] = None
    pin: bool = False


@dataclass
class Conflict:
    key: str
    constraints: list
    short: int
    set_aside: Constraint
    message: str

    @property
    def soft(self):
        return self.set_aside.kind == "preference"


Solution = namedtuple("Solution", "ranges conflicts set_aside_phases")


def ordinal(d):
    return d.toordinal()


def duration(value, label):
    """Return (lo, hi) from [lo, hi], (lo, None) from [lo,] with no latest date, or (None, hi) from [,hi]."""
    if len(value) == 1:
        if value[0] is None:
            raise ValueError(f"{label} has a duration with no limits")
        return value[0], None
    lo, hi = value
    if hi is None:
        raise ValueError(f"{label} writes a duration with no maximum as [{lo},], not with null")
    return lo, hi


def constraints_of(durations):
    """Rules from the `constraints` list, then the phases, in file order."""
    keys = {m["key"] for m in durations["milestones"]}
    out = []
    rows = [dict(c, name=c.get("name")) for c in durations.get("constraints", [])]
    rows += [dict(from_=p["start"], to=p["end"], duration_days=p["duration_days"], kind=p["kind"],
                  name=p["key"], phase=p["key"]) for p in durations.get("phases", [])]
    for i, c in enumerate(rows):
        frm = c.get("from_") or c["from"]
        label = f"rule {frm} to {c['to']}"
        lo, hi = duration(c["duration_days"], label)
        if c["kind"] not in KINDS:
            raise ValueError(f"{label} has kind {c['kind']!r}, not one of {KINDS}")
        for k in (frm, c["to"]):
            if k not in keys:
                raise ValueError(f"rule names unknown milestone {k!r}")
        if lo is not None and hi is not None and hi < lo:
            raise ValueError(f"{label} has hi below lo")
        out.append(Constraint(frm, c["to"], lo, hi, c["kind"], c.get("name") or f"{frm} to {c['to']}",
                              i, c.get("phase")))
    return out


def fixed_ordinals(rows, inputs):
    """Return {key: (earliest, latest)} for events the site fixes, and the set of keys the site fixed."""
    fixed, site_fixed = {}, set()
    for key, m in rows.items():
        if m.get("input"):
            if key not in inputs:
                raise ValueError(f"site gives no input for {key!r}")
        elif not (m.get("fixable") and key in inputs):
            continue
        else:
            site_fixed.add(key)
        lo, hi = as_range(inputs[key])
        fixed[key] = (ordinal(lo), ordinal(hi))
    return fixed, site_fixed


def narrow(keys, fixed, active):
    """Return ({key: (lo, hi)} in ordinals, None), or (None, (lo, hi) bounds of the first empty range).

    Each rule narrows its target to the dates its duration allows from the range of its source. A rule with
    no latest date starts its target as soon as the latest of such rules allows, but only when no other rule
    or site date gives the target a latest date. The ranges only tighten, so the loop settles.
    """
    lo, hi = {}, {}
    for k, (a, b) in fixed.items():
        lo[k], hi[k] = Bound(k, "lo", a, Fixed(k)), Bound(k, "hi", b, Fixed(k))
    pins = {}
    for c in active:
        if c.pins:
            pins.setdefault(c.to, []).append(c)

    def tighten(side, cand):
        table = lo if side == "lo" else hi
        old = table.get(cand.key)
        if old is not None and (cand.at <= old.at if side == "lo" else cand.at >= old.at):
            return False
        table[cand.key] = cand
        return True

    def settle():
        """Apply the rules until no range changes; return the bounds of the first empty range, or None."""
        for _ in range(MAX_PASSES):
            changed = False
            for c in active:
                src_lo, src_hi = lo.get(c.frm), hi.get(c.frm)
                moves = []
                if src_lo and c.lo is not None:
                    moves.append(Bound(c.to, "lo", src_lo.at + c.lo, c, src_lo))
                if src_hi and c.hi is not None:
                    moves.append(Bound(c.to, "hi", src_hi.at + c.hi, c, src_hi))
                for m in moves:
                    if tighten(m.side, m):
                        changed = True
                        if m.key in lo and m.key in hi and lo[m.key].at > hi[m.key].at:
                            return lo[m.key], hi[m.key]
            if not changed:
                return None
        raise ValueError("the rules form a loop that never settles")

    while True:
        empty = settle()
        if empty:
            return None, empty
        ready = []
        for key, rules in pins.items():
            srcs = [(hi.get(c.frm), c) for c in rules]
            if key not in hi and all(b is not None for b, _ in srcs):
                ready.append((key, max(srcs, key=lambda t: t[0].at + t[1].lo)))
        for key, (b, c) in ready:
            hi[key] = Bound(key, "hi", b.at + c.lo, c, b, True)
            if key in lo and lo[key].at > hi[key].at:
                return None, (lo[key], hi[key])
        if not ready:
            break
    for k in keys:
        if k not in lo or k not in hi:
            raise ValueError(f"no rule or site input bounds {k!r}")
    return {k: (lo[k].at, hi[k].at) for k in keys}, None


def day(n):
    return datetime.date.fromordinal(int(n)).isoformat()


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def chain(bound):
    """The bounds that led to this one, from the site's date to the bound itself."""
    out = []
    while bound is not None:
        out.append(bound)
        bound = bound.via
    return out[::-1]


def clause(b):
    """One step of a collision trail: the rule or site date that set the end, and the date it leaves."""
    way = "no earlier than" if b.side == "lo" else "no later than"
    if isinstance(b.rule, Fixed):
        return f"the site gives {b.key} {way} {day(b.at)}"
    if b.pin:
        return f"{b.key} starts as soon as the {b.rule.kind} {b.rule.name} allows, by {day(b.at)}"
    return f"the {b.rule.kind} {b.rule.name} puts {b.key} {way} {day(b.at)}"


def describe(low, high):
    """Return (rules, short days, message) for a milestone whose earliest date passes its latest."""
    short = low.at - high.at
    cons = []
    for b in chain(low) + chain(high):
        if isinstance(b.rule, Constraint) and b.rule not in cons:
            cons.append(b.rule)
    if not cons:
        raise ValueError(f"the site gives {low.key} an empty range")
    cons.sort(key=lambda c: c.order)
    reqs = [c.name for c in cons if c.kind == "requirement"]
    ests = [c.name for c in cons if c.kind == "estimate"]
    prefs = [c.name for c in cons if c.kind == "preference"]
    if prefs:
        others = reqs + ests
        rules = "estimates" if not reqs else "rules"
        head = (f"Ideal missed by {short} days: the preference {join(prefs)} would hold only if the "
                f"{rules} {join(others)} improved by {short} days in total" if others else
                f"Ideal missed by {short} days: the preference {join(prefs)} cannot hold with the fixed dates")
    elif reqs and ests:
        head = (f"{'Requirement' if len(reqs) == 1 else 'Requirements'} {join(reqs)} "
                f"{'is' if len(reqs) == 1 else 'are'} unmet unless the estimates {join(ests)} improve by {short} days in total")
    elif ests:
        head = f"The estimates {join(ests)} cannot all hold and are {short} days apart"
    else:
        head = f"{'Requirement' if len(reqs) == 1 else 'Requirements'} {join(reqs)} cannot hold with the fixed dates, {short} days short"
    trail = (f"{low.key} is no earlier than {day(low.at)}: {'; '.join(clause(b) for b in chain(low))}. "
             f"But {low.key} is no later than {day(high.at)}: {'; '.join(clause(b) for b in chain(high))}")
    return cons, short, f"{head}. {trail}"


def pick_set_aside(cons):
    """Choose the rule that gives: a preference, else a requirement, else an estimate, the last listed first."""
    can_give = [c for c in cons if not c.pins]
    for kind in ("preference", "requirement", "estimate"):
        pool = [c for c in can_give if c.kind == kind]
        if pool:
            return max(pool, key=lambda c: c.order)
    return max(cons, key=lambda c: c.order)


def solve(durations, inputs):
    """Return a Solution: displayed ranges as dates, and the conflicts that were flagged."""
    rows = {m["key"]: m for m in durations["milestones"]}
    fixed, site_fixed = fixed_ordinals(rows, inputs)
    active = [c for c in constraints_of(durations)
              if not (c.to in site_fixed and c.kind == "estimate")]
    conflicts, set_aside_phases = [], set()
    while True:
        found, empty = narrow(list(rows), fixed, active)
        if empty is None:
            break
        cons, short, message = describe(*empty)
        chosen = pick_set_aside(cons)
        conflicts.append(Conflict(chosen.to, cons, short, chosen, message))
        if chosen.phase:
            set_aside_phases.add(chosen.phase)
        active.remove(chosen)
    ranges = {k: (datetime.date.fromordinal(lo), datetime.date.fromordinal(hi))
              for k, (lo, hi) in found.items()}
    return Solution(ranges, conflicts, set_aside_phases)


def resolve(durations, inputs):
    """Return {key: (earliest, latest)} for every milestone in durations."""
    return solve(durations, inputs).ranges


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


def phase_flags(durations, resolved, skip=()):
    """Return [(end_key, message)] for phases whose actual span is outside the planned range."""
    out = []
    for p in durations.get("phases", []):
        if p["key"] in skip:
            continue
        lo, hi = p["duration_days"]
        short, long_ = phase_span(p, resolved)
        where = f"{p['key']} runs {days(short, long_)} from {p['start']} to {p['end']}"
        if short > hi:
            out.append((p["end"], f"{where}, at least {short - hi} days over its planned {days(lo, hi)}"))
        elif long_ < lo:
            out.append((p["end"], f"{where}, at least {lo - long_} days under its planned {days(lo, hi)}"))
    return out


def phase_rows(durations, resolved):
    """[(key, start, end, planned, actual, basis)] for every phase, with planned and actual as (low, high) days."""
    return [(p["key"], p["start"], p["end"], tuple(p["duration_days"]), phase_pairing(p, resolved), p["basis"])
            for p in durations.get("phases", [])]


def set_aside_rows(conflicts):
    """[(rule, kind, collides with, days short)] for the rules set aside, in the order they were set aside."""
    return [(k.set_aside.name, k.set_aside.kind,
             ", ".join(c.name for c in k.constraints if c != k.set_aside), k.short) for k in conflicts]


STATUSES = ("committed", "estimated", "assumed")


def input_rows(durations, site):
    """[(key, milestone, given range, status, basis)] for every date the site gives, in milestone order."""
    basis, status = site.get("basis", {}), site.get("status", {})
    out = []
    for m in durations["milestones"]:
        key = m["key"]
        if key not in site["inputs"]:
            continue
        if status.get(key) not in STATUSES:
            raise ValueError(f"input {key!r} needs a status, one of {STATUSES}")
        out.append((key, m["label"], as_range(site["inputs"][key]), status[key], basis.get(key, m["basis"])))
    return out


def fmt(rng):
    lo, hi = rng
    return lo.isoformat() if lo == hi else f"{lo.isoformat()} to {hi.isoformat()}"


def milestone_rows(durations, resolved, site):
    """[(key, milestone, range, status, gantt row, basis)] for every milestone. An input carries its status, and a
    lease range that other rules narrowed also names the range the site gave. Everything else is computed."""
    given = {r[0]: r for r in input_rows(durations, site)}
    out = []
    for m in durations["milestones"]:
        key = m["key"]
        status, basis = "computed", site.get("basis", {}).get(key, m["basis"])
        if key in given:
            status = given[key][3]
            if given[key][2] != resolved[key]:
                status = f"{status}, given {fmt(given[key][2])}"
        out.append((key, m["label"], resolved[key], status, m.get("gantt_row") or "", basis))
    return out


def render_table(durations, resolved, site):
    lines = ["| Key | Milestone | Estimate | Status | Gantt row | Basis |",
             "| --- | --------- | -------- | ------ | --------- | ----- |"]
    for key, label, rng, status, row, basis in milestone_rows(durations, resolved, site):
        lines.append(f"| `{key}` | {label} | {fmt(rng)} | {status} | {row} | {basis} |")
    return "\n".join(lines)


def flag_lines(durations, solution):
    """Bullets for the rules set aside and the phases off their planned range; empty when nothing is off."""
    out = []
    for rule, kind, others, short in set_aside_rows(solution.conflicts):
        out.append(f"- `{rule}` ({kind}) was set aside, {short} days short against {others}")
    for end, msg in phase_flags(durations, solution.ranges, solution.set_aside_phases):
        out.append(f"- `{end}`: {msg}")
    return out


def render_sections(durations, site, solution):
    """The milestone table with its statuses, then a flags list only when something is off."""
    parts = [("Milestones", "Every milestone with the range of dates the rules allow, computed from the inputs. "
              "Status says how firm each input is, and computed marks a date the rules derive.",
              render_table(durations, solution.ranges, site))]
    flags_ = flag_lines(durations, solution)
    if flags_:
        parts.append(("Flags", "Rules the dates could not satisfy together and phases outside their planned length.",
                      "\n".join(flags_)))
    return "\n\n".join(f"#### {title}\n\n{blurb}\n\n{body}" for title, blurb, body in parts)


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

    sites = load_yaml("sites.yaml")
    if args.site not in sites["sites"]:
        raise SystemExit(f"no site {args.site!r} in sites.yaml; have {', '.join(sites['sites'])}")
    if args.write:
        import tasks     # imported here because tasks imports this module
        for line in tasks.take_actuals(args.site):
            print(f"actual: {line}")
        sites = load_yaml("sites.yaml")
    durations = load_yaml("durations.yaml")
    site = sites["sites"][args.site]
    solution = solve(durations, site["inputs"])
    resolved = solution.ranges
    table = render_sections(durations, site, solution)
    if args.write:
        rewrite_note(args.write, args.site, table)
        print(f"rewrote {args.site} block in {args.write}")
        print(f"moved {tasks.sync_note(args.site, resolved)} task due dates")
    else:
        print(table)
    for key, msg in ([(c.key, c.message) for c in solution.conflicts if not c.soft]
                     + flags(resolved, site["limits"], sites["owner"]["away"])
                     + phase_flags(durations, resolved, solution.set_aside_phases)):
        print(f"flag: {key}: {msg}", file=sys.stderr)
    for c in solution.conflicts:
        if c.soft:
            print(f"warning: {c.key}: {c.message}", file=sys.stderr)


if __name__ == "__main__":
    main()
