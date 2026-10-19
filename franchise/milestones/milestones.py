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


def load_yaml(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def as_range(value):
    """A date becomes (d, d); a two-date list becomes (earliest, latest)."""
    if isinstance(value, (list, tuple)):
        lo, hi = value
        return (lo, hi)
    return (value, value)


KINDS = ("estimate", "requirement", "preference")
INF = float("inf")
REF = "@"  # the reference node; a date is its ordinal day number


@dataclass(frozen=True)
class Constraint:
    """`to` minus `from` is within [lo, hi] days; hi None means not before."""
    frm: str
    to: str
    lo: int
    hi: Optional[int]
    kind: str
    name: str
    order: int
    phase: Optional[str] = None

    @property
    def not_before(self):
        return self.hi is None


@dataclass(frozen=True)
class Edge:
    """x[dst] <= x[src] + w, from a rule, a fixed date or a start-as-soon-as bound."""
    src: str
    dst: str
    w: float
    source: object
    forward: bool = True


@dataclass(frozen=True)
class Fixed:
    key: str


@dataclass(frozen=True)
class Closure:
    key: str
    rule: Constraint


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


def constraints_of(durations):
    """Rules from the `constraints` list, then the phases, in file order."""
    keys = {m["key"] for m in durations["milestones"]}
    out = []
    rows = [dict(c, name=c.get("name")) for c in durations.get("constraints", [])]
    rows += [dict(from_=p["start"], to=p["end"], duration_days=p["duration_days"], kind=p["kind"],
                  name=p["key"], phase=p["key"]) for p in durations.get("phases", [])]
    for i, c in enumerate(rows):
        frm = c.get("from_") or c["from"]
        lo, hi = c["duration_days"]
        if c["kind"] not in KINDS:
            raise ValueError(f"rule {frm} to {c['to']} has kind {c['kind']!r}, not one of {KINDS}")
        for k in (frm, c["to"]):
            if k not in keys:
                raise ValueError(f"rule names unknown milestone {k!r}")
        if hi is not None and hi < lo:
            raise ValueError(f"rule {frm} to {c['to']} has hi below lo")
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
        elif not (m.get("site_can_fix") and key in inputs):
            continue
        else:
            site_fixed.add(key)
        lo, hi = as_range(inputs[key])
        fixed[key] = (ordinal(lo), ordinal(hi))
    return fixed, site_fixed


def shortest(nodes, edges, start, reverse=False):
    """Bellman-Ford distances from start; a negative cycle would never settle, callers check first."""
    dist = {n: INF for n in nodes}
    dist[start] = 0
    for _ in range(len(nodes)):
        changed = False
        for e in edges:
            s, d = (e.dst, e.src) if reverse else (e.src, e.dst)
            if dist[s] + e.w < dist[d]:
                dist[d] = dist[s] + e.w
                changed = True
        if not changed:
            break
    return dist


def negative_cycle(nodes, edges):
    """Return the edges of one negative cycle in order, or None."""
    dist = {n: 0 for n in nodes}
    pred = {n: None for n in nodes}
    moved = None
    for _ in range(len(nodes) + 1):
        moved = None
        for e in edges:
            if dist[e.src] + e.w < dist[e.dst]:
                dist[e.dst] = dist[e.src] + e.w
                pred[e.dst] = e
                moved = e.dst
        if moved is None:
            return None
    x = moved
    for _ in range(len(nodes)):
        x = pred[x].src
    cycle, cur = [], x
    while True:
        e = pred[cur]
        cycle.append(e)
        cur = e.src
        if cur == x:
            break
    cycle.reverse()
    for i, e in enumerate(cycle):
        if e.src == REF:
            return cycle[i:] + cycle[:i]
    return cycle


def stn(keys, fixed, active):
    """Return ({key: (lo, hi)} in ordinals, None), or (None, cycle) when the rules collide."""
    nodes = [REF] + list(keys)
    base = []
    for c in active:
        if c.hi is not None:
            base.append(Edge(c.frm, c.to, c.hi, c, True))
        base.append(Edge(c.to, c.frm, -c.lo, c, False))
    for k, (lo, hi) in fixed.items():
        base.append(Edge(REF, k, hi, Fixed(k)))
        base.append(Edge(k, REF, -lo, Fixed(k), False))
    not_before = {}
    for c in active:
        if c.not_before:
            not_before.setdefault(c.to, []).append(c)
    closure = {}
    while True:
        edges = base + [Edge(REF, k, w, Closure(k, g)) for k, (w, g) in closure.items()]
        cycle = negative_cycle(nodes, edges)
        if cycle:
            return None, cycle
        hi = shortest(nodes, edges, REF)
        lo = shortest(nodes, edges, REF, reverse=True)
        changed = False
        for k, gs in not_before.items():
            vals = [(hi[g.frm] + g.lo, g) for g in gs]
            if any(v == INF for v, _ in vals):
                continue
            w, rule = max(vals, key=lambda t: t[0])
            if w < hi[k]:
                closure[k] = (w, rule)
                changed = True
        if not changed:
            break
    for k in keys:
        if hi[k] == INF or lo[k] == INF:
            raise ValueError(f"no rule or site input bounds {k!r}")
    return {k: (-lo[k], hi[k]) for k in keys}, None


def day(n):
    return datetime.date.fromordinal(int(n)).isoformat()


def span_words(n):
    return f"{abs(n)} days"


def clause(e, at):
    """One step of a collision trail: the rule, and the latest date it leaves the event."""
    c = e.source
    if isinstance(c, Closure):
        return f"{e.dst} starts as soon as {c.rule.name} allows, by {day(at)}"
    if e.forward:
        rel = "after" if e.w >= 0 else "before"
        what = f"puts {e.dst} at most {span_words(e.w)} {rel} {e.src}" if e.w >= 0 else \
            f"puts {e.dst} at least {span_words(e.w)} before {e.src}"
    else:
        what = f"puts {e.dst} at most {span_words(e.w)} after {e.src}" if e.w >= 0 else \
            f"puts {e.dst} at least {span_words(e.w)} before {e.src}"
    return f"the {c.kind} {c.name} {what}, by {day(at)}"


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def describe(cycle):
    """Return (constraints, short days, message) for a negative cycle."""
    short = -int(sum(e.w for e in cycle))
    cons = []
    for e in cycle:
        c = e.source.rule if isinstance(e.source, Closure) else e.source
        if isinstance(c, Constraint) and c not in cons:
            cons.append(c)
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
    if cycle[0].src != REF or cycle[-1].dst != REF:
        return cons, short, head
    at = cycle[0].w
    first = cycle[0]
    parts = [f"{first.dst} starts as soon as {first.source.rule.name} allows, by {day(at)}"
             if isinstance(first.source, Closure) else f"{first.dst} is no later than {day(at)}"]
    for e in cycle[1:-2]:
        at += e.w
        parts.append(clause(e, at))
    last, back = cycle[-2], cycle[-1]
    floor = -back.w
    c = last.source.rule if isinstance(last.source, Closure) else last.source
    parts.append(f"but {last.dst} is no earlier than {day(floor)}, and the {c.kind} {c.name} "
                 f"then puts {last.src} no earlier than {day(floor - last.w)}")
    return cons, short, head + ". " + "; ".join(parts)


def pick_set_aside(cons, cycle):
    """Choose the rule that gives: a preference, else a requirement, else an estimate, the last listed first."""
    can_give = [c for c in cons if not c.not_before]
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
        bounds, cycle = stn(list(rows), fixed, active)
        if cycle is None:
            break
        cons, short, message = describe(cycle)
        chosen = pick_set_aside(cons, cycle)
        conflicts.append(Conflict(chosen.to, cons, short, chosen, message))
        if chosen.phase:
            set_aside_phases.add(chosen.phase)
        active.remove(chosen)
    ranges = {k: (datetime.date.fromordinal(lo), datetime.date.fromordinal(hi))
              for k, (lo, hi) in bounds.items()}
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
