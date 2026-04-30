#!/usr/bin/env python3
"""Prune archived Composer agents from Cursor state.vscdb (macOS).

Keeps chats where NOT (isArchived and lastUpdatedAt <= cutoff).

Default cutoff: start of 2026-04-23 in America/Los_Angeles (sessions with no
updates after local 2026-04-22).

  python3 scripts/prune_cursor_agents.py          # dry run
  python3 scripts/prune_cursor_agents.py --apply  # Cursor must be quit first!

"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

try:
    import zoneinfo

    TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
except Exception:
    TZ = datetime.now().astimezone().tzinfo  # noqa: DTZ007

DEFAULT_CUTOFF = datetime(2026, 4, 23, 0, 0, 0, tzinfo=TZ)
DB = os.path.expanduser(
    "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
)
HEAD_KEY = "composer.composerHeaders"


def ts_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write changes (still copies DB backup before KV deletes)",
    )
    parser.add_argument(
        "--by-created-at",
        action="store_true",
        help="compare createdAt instead of lastUpdatedAt to cutoff",
    )
    args = parser.parse_args()
    cutoff = ts_ms(DEFAULT_CUTOFF)

    if not os.path.isfile(DB):
        print("missing DB:", DB)
        return 2

    con = sqlite3.connect(DB)
    row = con.execute(
        "SELECT value FROM ItemTable WHERE key=?",
        (HEAD_KEY,),
    ).fetchone()
    if not row:
        print("no", HEAD_KEY, "entry")
        return 2

    data = json.loads(row[0])
    heads: list = data.get("allComposers") or []

    cmp_key = "createdAt" if args.by_created_at else "lastUpdatedAt"

    to_drop: list[dict] = []
    keep: list[dict] = []
    for h in heads:
        if not h.get("isArchived"):
            keep.append(h)
            continue
        t = int(h.get(cmp_key, 0) or 0)
        if t <= cutoff:
            to_drop.append(h)
        else:
            keep.append(h)

    print(f"Cutoff ({cmp_key}) <= {DEFAULT_CUTOFF.isoformat()}  →  ms {cutoff}")
    print(f"Will remove {len(to_drop)} archived head(s); keep {len(keep)} total.")

    for h in sorted(to_drop, key=lambda x: x.get(cmp_key, 0)):
        ts_h = datetime.fromtimestamp((h.get(cmp_key, 0) or 0) / 1000, TZ)
        print(f"  - {h.get('composerId')}  {ts_h.date()}  {h.get('name')!r}")

    if not args.apply:
        print("\nDry run only; pass --apply to delete.")
        return 0

    backup = DB + ".pre-prune-backup.sqlite"
    shutil.copy2(DB, backup)
    print("Backed up:", backup)

    # UUID substring for composerId matches bubbleId:, checkpointId:, etc.
    # No ESCAPE layer needed — UUIDs do not include LIKE wildcards (% or _).
    for h in to_drop:
        cid = h["composerId"]
        cur = con.execute(
            "DELETE FROM cursorDiskKV WHERE key LIKE ?",
            (f"%{cid}%",),
        )
        deleted = cur.rowcount or 0
        if deleted:
            print(f"deleted {deleted} KV row(s) for {cid}")

    data["allComposers"] = keep
    con.execute(
        "UPDATE ItemTable SET value=? WHERE key=?",
        (json.dumps(data, separators=(",", ":")), HEAD_KEY),
    )
    con.commit()
    print("Updated composer headers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
