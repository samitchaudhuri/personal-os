#!/usr/bin/env python3
"""Fill the center placeholders of the ULC membership agreement template.

Reads a center data file such as ``los-gatos.yaml`` and replaces each listed
``<KEY>`` placeholder in the template's Word XML. A field whose value is null
keeps its placeholder, and so do the member fields, the Kite merge fields, the
contract dates and the signature blocks. The summary lists what is still
unfilled so a guess never passes for a fact.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import zipfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-samit.chaudhuri@ultimatelongevitycenters.com"
    / "My Drive/ULC-Franchisor/Operations/Presale"
    / "Sample: California ULC Membership Agreement (CA-RD).docx"
)
PLACEHOLDER = re.compile(r"&lt;([A-Za-z0-9]+)&gt;|\{\{([A-Za-z]+)\}\}")
XML_PARTS = re.compile(r"word/(document|header\d*|footer\d*)\.xml$")


def load_fields(path: Path) -> tuple[dict, dict[str, dict]]:
    data = yaml.safe_load(path.read_text())
    by_key: dict[str, dict] = {}
    for field in data["fields"]:
        for key in field["keys"]:
            if key in by_key:
                raise ValueError(f"{key} is listed twice in {path.name}")
            by_key[key] = field
    return data, by_key


def fill(xml: str, by_key: dict[str, dict]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def repl(match: re.Match) -> str:
        key = match.group(1)
        field = by_key.get(key) if key else None
        if field is None or field["value"] is None:
            return match.group(0)
        counts[key] = counts.get(key, 0) + 1
        return html.escape(str(field["value"]), quote=False)

    return PLACEHOLDER.sub(repl, xml), counts


def generate(template: Path, data_path: Path, out: Path) -> dict:
    data, by_key = load_fields(data_path)
    filled: dict[str, int] = {}
    left: dict[str, int] = {}
    with zipfile.ZipFile(template) as src, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if XML_PARTS.match(item.filename):
                text, counts = fill(raw.decode("utf-8"), by_key)
                for key, n in counts.items():
                    filled[key] = filled.get(key, 0) + n
                for m in PLACEHOLDER.finditer(text):
                    name = m.group(1) or m.group(2)
                    left[name] = left.get(name, 0) + 1
                raw = text.encode("utf-8")
            dst.writestr(item, raw)
    return {"filled": filled, "left": left, "by_key": by_key}


def summary(result: dict) -> str:
    by_key, left = result["by_key"], result["left"]
    lines = [f"filled {sum(result['filled'].values())} placeholders"]
    for key, field in by_key.items():
        if field["value"] is None:
            lines.append(f"  unfilled, open: {key} ({left.get(key, 0)}x) - {field['basis']}")
        elif field["status"] != "committed":
            lines.append(f"  {field['status']}: {key} = {field['value']}")
    kite = sorted(k for k in left if k not in by_key)
    lines.append("left for Kite and the member at signing: " + ", ".join(kite))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "los-gatos.yaml")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", type=Path, help="output .docx; defaults to out/<output_name>")
    args = parser.parse_args(argv)

    if not args.template.exists():
        print(f"template not found: {args.template}", file=sys.stderr)
        return 1
    data, _ = load_fields(args.data)
    out = args.out or HERE / "out" / data["output_name"]
    out.parent.mkdir(parents=True, exist_ok=True)
    result = generate(args.template, args.data, out)
    print(f"wrote {out}")
    print(summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
