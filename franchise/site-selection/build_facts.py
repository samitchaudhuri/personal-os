#!/usr/bin/env python3
"""Build combined_facts.csv for ULC site selection (lever 2, config-driven).

Reads L1 (`Site Report*.pdf`) for demographics and AI score, merges the
human-authored `manual_facts.csv` (identity, lease economics, co-tenants/notes,
Placer reads, 1-7 scores), computes the derived columns, and writes
`combined_facts.csv`.

This script is the ONLY writer of combined_facts.csv. You author L1 (the VT
files) and manual_facts.csv; everything else is generated here. Tunables live in
config.yaml (the authoritative home for the numbers); the vault Rules registry
cites that file. See vault Agent/Workflows/Site Selection Scoring.md ->
"Build automation (lever 2)".
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys

import yaml

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    sys.exit("pdfplumber not installed. Run: pip install -r requirements.txt")


# Output column order (matches the existing combined_facts.csv schema).
COLUMNS = [
    "site", "address", "ai_score",
    "sf_target", "gen", "shell",
    "total_rent", "total_bo", "total_ti", "bo_net",
    "psf_rent", "psf_bo", "psf_ti",
    "base_psf", "nnn_psf",
    "gate_afford",
    "pop_1mi", "pop_3mi", "pop_5mi", "hh_3mi",
    "med_income_1mi", "med_income_3mi", "med_income_5mi", "avg_income_3mi",
    "med_age_3mi", "age_25_49_3mi", "age_50_64_3mi", "age_65plus_3mi",
    "pct_income_150k_3mi", "cagr_hist_3mi", "cagr_proj_3mi", "daytime_3mi",
    "fitness_centers_3mi",
    "flag_income_150k", "flag_pop_100k", "flag_age_40plus", "flag_cagr",
    "placer_source", "placer_mon", "placer_tue", "placer_wed", "placer_thu",
    "placer_fri", "placer_sat", "placer_sun", "placer_weekend_ratio", "placer_pattern",
    "score_neighbor", "score_customer", "score_resid", "score_visibility", "composite",
    "co_tenants", "notes",
]

# Columns copied verbatim from manual_facts.csv (human-authored). `territory`
# isn't tracked downstream (the G-territory gate was retired), so it's dropped
# from combined_facts.csv here. `generation` and `ti_psf` are also authored in
# manual_facts.csv but land under the shorter `gen` / `psf_ti` output names —
# see the explicit rename in main() instead of listing them here.
MANUAL_PASSTHROUGH = [
    "address", "sf_target", "base_psf", "nnn_psf",
    "co_tenants", "notes",
    "placer_source", "placer_mon", "placer_tue", "placer_wed", "placer_thu",
    "placer_fri", "placer_sat", "placer_sun",
    "score_neighbor", "score_customer", "score_resid", "score_visibility",
]

PLACER_DAYS = ["placer_mon", "placer_tue", "placer_wed", "placer_thu",
               "placer_fri", "placer_sat", "placer_sun"]

TOK = r"[-$]?[\d.,]+[kKmMbB]?%?"


def parse_num(tok):
    """Parse VT-style tokens: '24k'->24000, '$182k'->182000, '2.9%'->2.9, '1.5m'->1500000."""
    if tok is None:
        return None
    t = str(tok).strip().replace(",", "").replace("$", "")
    if t in ("", "-", "\u2014", "TODO"):
        return None
    pct = t.endswith("%")
    if pct:
        t = t[:-1]
    mult = 1
    if t[-1:].lower() in ("k", "m", "b"):
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[t[-1].lower()]
        t = t[:-1]
    try:
        v = float(t) * mult
    except ValueError:
        return None
    if not pct and mult >= 1000:
        return int(round(v))
    return v


def ring_row(text, label, count=3):
    """Find a metric row (label followed by `count` ring values) and parse them."""
    pat = rf"(?m)^\s*{re.escape(label)}\s+" + r"\s+".join([f"({TOK})"] * count)
    m = re.search(pat, text)
    if not m:
        return [None] * count
    return [parse_num(g) for g in m.groups()]


def fmt(v):
    """Format a computed/parsed value for CSV. None -> 'TODO'."""
    if v is None:
        return "TODO"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, float):
        return str(round(v, 2))
    return str(v)


REPORT_FIELDS = [
    "ai_score", "pop_1mi", "pop_3mi", "pop_5mi", "hh_3mi",
    "med_income_1mi", "med_income_3mi", "med_income_5mi", "avg_income_3mi",
    "med_age_3mi", "age_25_49_3mi", "age_50_64_3mi", "age_65plus_3mi",
    "pct_income_150k_3mi", "cagr_hist_3mi", "cagr_proj_3mi", "daytime_3mi",
    "fitness_centers_3mi",
]


def read_site_report(path):
    """Open the Site Report PDF and parse its text (empty/missing -> all None)."""
    if not path or not os.path.exists(path):
        return parse_report_text("")
    with pdfplumber.open(path) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages)
    return parse_report_text(text)


def parse_report_text(text):
    """Pure: parse Site Report ring-table text into demographics + AI score.

    Kept file-free so tests can feed a captured text fixture. Empty text yields
    an all-None dict (every field becomes TODO downstream).
    """
    out = {k: None for k in REPORT_FIELDS}
    if not text:
        return out

    pop = ring_row(text, "Population")
    inc = ring_row(text, "Median Income")
    out["pop_1mi"], out["pop_3mi"], out["pop_5mi"] = pop
    out["med_income_1mi"], out["med_income_3mi"], out["med_income_5mi"] = inc
    out["hh_3mi"] = ring_row(text, "Households")[1]
    out["avg_income_3mi"] = ring_row(text, "Average Income")[1]
    out["med_age_3mi"] = ring_row(text, "Median Population Age")[1]
    out["age_25_49_3mi"] = ring_row(text, "25-49")[1]
    out["age_50_64_3mi"] = ring_row(text, "50-64")[1]
    out["age_65plus_3mi"] = ring_row(text, "65+")[1]
    out["cagr_hist_3mi"] = ring_row(text, "Historic 2yr CAGR")[1]
    out["cagr_proj_3mi"] = ring_row(text, "Projected 2yr CAGR")[1]
    out["daytime_3mi"] = ring_row(text, "Daytime Population")[1]
    out["fitness_centers_3mi"] = ring_row(text, "Fitness Centers")[1]

    m = re.search(r"(?m)^\s*\$150k\+\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%", text)
    if m:
        out["pct_income_150k_3mi"] = float(m.group(2))
    m = re.search(r"(?m)^\s*(\d{2,3})\s+This model was trained", text)
    if m:
        out["ai_score"] = int(m.group(1))
    return out


DELIVERY_BULLET_RE = re.compile(r"(?im)^-\s*Delivery:\s*(.+?)\s*$")


def classify_shell(text):
    """Map a VT 'About the Space' Delivery bullet to Anson's three rate buckets."""
    t = text.lower()
    if "cold" in t:
        return "cold_dark"
    if "grey" in t or "gray" in t:
        return "grey"
    if "warm" in t:
        return "vanilla"
    return None


def parse_delivery_shell(text):
    """Pure: find the 'About the Space' Delivery bullet and classify its shell type.

    Second-gen sites typically have no such bullet (existing improvements,
    not a raw shell) -> None, formatted as TODO downstream.
    """
    if not text:
        return None
    m = DELIVERY_BULLET_RE.search(text)
    if not m:
        return None
    return classify_shell(m.group(1))


def read_page_md(path):
    """Open the VT _page.md Overview (missing/empty -> no shell classification)."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def compute(row, cfg):
    """Fill computed columns: all-in, gate, flags, placer ratio/pattern, composite."""
    th = cfg["thresholds"]
    base, nnn, sf = parse_num(row.get("base_psf")), parse_num(row.get("nnn_psf")), parse_num(row.get("sf_target"))
    allin = None
    if None not in (base, nnn, sf):
        allin = int(round((base + nnn) * sf / 12))
    row["total_rent"] = fmt(allin)
    row["psf_rent"] = fmt(base + nnn) if None not in (base, nnn) else "TODO"

    ti, sf_ti = parse_num(row.get("psf_ti")), parse_num(row.get("sf_target"))
    total_ti = None
    if None not in (ti, sf_ti):
        total_ti = int(round(ti * sf_ti))
    row["total_ti"] = fmt(total_ti)

    bo_rate = cfg.get("buildout_psf_by_shell", {}).get(row.get("shell"))
    if bo_rate is None and row.get("gen") == "Second":
        bo_rate = cfg.get("buildout_psf_second_gen")
    row["psf_bo"] = fmt(bo_rate)
    total_bo = None
    if None not in (bo_rate, sf):
        total_bo = int(round(bo_rate * sf))
    row["total_bo"] = fmt(total_bo)

    # Capital gap: estimated build-out cost minus the landlord's TI allowance.
    # Positive = the franchisee funds the difference; this is the figure the
    # guarantor build-out loan question (Anson 8/26) is actually asking about.
    bo_net = None
    if None not in (total_bo, total_ti):
        bo_net = total_bo - total_ti
    row["bo_net"] = fmt(bo_net)

    if allin is None:
        row["gate_afford"] = "TODO"
    elif allin <= th["afford_ceiling_hard"]:
        row["gate_afford"] = "pass"
    elif allin <= th["afford_ceiling_hard"] * (1 + th["afford_borderline_pct"]):
        row["gate_afford"] = "borderline"
    else:
        row["gate_afford"] = "fail"

    inc3, pop3, age3 = parse_num(row.get("med_income_3mi")), parse_num(row.get("pop_3mi")), parse_num(row.get("med_age_3mi"))
    row["flag_income_150k"] = "TODO" if inc3 is None else str(inc3 >= th["income_3mi_min"]).upper()
    row["flag_pop_100k"] = "TODO" if pop3 is None else str(pop3 >= th["pop_3mi_min"]).upper()
    row["flag_age_40plus"] = "TODO" if age3 is None else str(age3 >= th["age_3mi_min"]).upper()
    h, p = parse_num(row.get("cagr_hist_3mi")), parse_num(row.get("cagr_proj_3mi"))
    if h is None or p is None:
        row["flag_cagr"] = "TODO"
    else:
        sign = lambda x: "+" if x > 0 else ("-" if x < 0 else "0")
        row["flag_cagr"] = f"hist{sign(h)}/proj{sign(p)}"

    days = [parse_num(row.get(d)) for d in PLACER_DAYS]
    if all(d is not None for d in days):
        wk = sum(days[:5]) / 5.0
        we = (days[5] + days[6]) / 2.0
        ratio = round(we / wk, 2) if wk else None
        row["placer_weekend_ratio"] = f"{ratio:.2f}" if ratio is not None else ""
        row["placer_pattern"] = "weekend-spike" if (ratio and ratio > cfg["placer"]["weekend_spike_ratio"]) else "uniform"
    else:
        row["placer_weekend_ratio"] = ""
        row["placer_pattern"] = ""

    w = cfg["weights"]
    scores = [parse_num(row.get(k)) for k in ("score_neighbor", "score_customer", "score_resid", "score_visibility")]
    if all(s is not None for s in scores):
        comp = (w["neighbor"] * scores[0] + w["customer"] * scores[1]
                + w["resid"] * scores[2] + w["visibility"] * scores[3])
        row["composite"] = fmt(round(comp, 2))
    else:
        row["composite"] = ""
    return row


def main():
    ap = argparse.ArgumentParser(description="Build combined_facts.csv from L1 + manual_facts.csv")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"))
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    base = cfg["drive_base"]
    if not os.path.isabs(base):
        # personal-os repo root is two levels up from this script (franchise/site-selection/).
        base = os.path.join(os.path.dirname(__file__), "..", "..", base)
    comp_dir = os.path.join(base, cfg["comparison_dir"])
    manual_path = os.path.join(comp_dir, cfg["manual_file"])
    out_path = os.path.join(comp_dir, cfg["output_file"])
    names = cfg.get("site_names", {})

    manual = {}
    if os.path.exists(manual_path):
        with open(manual_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                manual[r["site"].strip()] = r
    else:
        print(f"WARN: no manual_facts.csv at {manual_path}", file=sys.stderr)

    slugs = sorted(d for d in os.listdir(base)
                   if os.path.isdir(os.path.join(base, d))
                   and d != cfg["comparison_dir"] and not d.startswith("."))

    rows, warnings = [], []
    for slug in slugs:
        folder = os.path.join(base, slug)
        display = names.get(slug, slug)
        reports = glob.glob(os.path.join(folder, "Site Report*.pdf"))

        row = {c: "" for c in COLUMNS}
        row["site"] = display
        man = manual.get(display, {})
        for c in MANUAL_PASSTHROUGH:
            row[c] = (man.get(c) or "").strip()
        row["gen"] = (man.get("generation") or "").strip()
        row["psf_ti"] = (man.get("ti_psf") or "").strip()

        sr = read_site_report(reports[0] if reports else None)  # None -> all TODO
        for k, v in sr.items():
            row[k] = fmt(v)

        page_paths = glob.glob(os.path.join(folder, "_page.md"))
        page_text = read_page_md(page_paths[0] if page_paths else None)
        row["shell"] = parse_delivery_shell(page_text) or "TODO"

        compute(row, cfg)

        if not reports:
            warnings.append(f"{display}: no Site Report PDF (demographics = TODO)")
        if display not in manual:
            warnings.append(f"{display}: no manual_facts.csv row (lease/text/placer blank)")
        rows.append(row)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if args.dry_run:
        wtr = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
        wtr.writeheader()
        wtr.writerows(rows)
        return

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=COLUMNS)
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"wrote {out_path}: {len(rows)} rows, {len(COLUMNS)} cols")


if __name__ == "__main__":
    main()
