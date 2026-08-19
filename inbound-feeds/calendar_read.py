"""Live Calendar read for Daily Planning.

Lists today's events on ULC and Personal Google calendars using Desktop
OAuth tokens from oauth_loop.py. Prints timed events, all-day events, free
blocks, and overlaps. Does not Store events into the vault.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import oauth_loop as loop

CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
)
DEFAULT_DAY_START = time(8, 0)
DEFAULT_DAY_END = time(18, 0)
ACCOUNT_FOR_SOURCE = {
    loop.SOURCE_ULC_CALENDAR: "ulc",
    loop.SOURCE_PERSONAL_CALENDAR: "personal",
}


class AuthError(Exception):
    """Calendar returned 401/403 or the refresh token is dead."""


@dataclass
class CalEvent:
    event_id: str
    summary: str
    start: datetime | None
    end: datetime | None
    all_day: bool
    account: str
    source: str
    organizer: str | None = None


def local_tz() -> timezone | ZoneInfo:
    return datetime.now().astimezone().tzinfo or ZoneInfo("America/Los_Angeles")


def parse_google_datetime(value: str, tz: timezone | ZoneInfo) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def parse_event(
    resource: Mapping[str, Any],
    *,
    account: str,
    source: str,
    tz: timezone | ZoneInfo,
) -> CalEvent | None:
    if str(resource.get("status") or "") == "cancelled":
        return None
    start = resource.get("start") or {}
    end = resource.get("end") or {}
    summary = str(resource.get("summary") or "(no title)").replace("\n", " ")
    event_id = str(resource.get("id") or "")
    organizer_info = resource.get("organizer") or {}
    organizer = None
    if organizer_info and not organizer_info.get("self"):
        organizer = str(
            organizer_info.get("displayName") or organizer_info.get("email") or ""
        ) or None
    if start.get("date") and not start.get("dateTime"):
        return CalEvent(
            event_id=event_id,
            summary=summary,
            start=None,
            end=None,
            all_day=True,
            account=account,
            source=source,
            organizer=organizer,
        )
    start_raw = str(start.get("dateTime") or "")
    end_raw = str(end.get("dateTime") or "")
    if not start_raw or not end_raw:
        return None
    return CalEvent(
        event_id=event_id,
        summary=summary,
        start=parse_google_datetime(start_raw, tz),
        end=parse_google_datetime(end_raw, tz),
        all_day=False,
        account=account,
        source=source,
        organizer=organizer,
    )


def day_window(
    day: date,
    tz: timezone | ZoneInfo,
    start: time = DEFAULT_DAY_START,
    end: time = DEFAULT_DAY_END,
) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, start, tzinfo=tz),
        datetime.combine(day, end, tzinfo=tz),
    )


def rfc3339(moment: datetime) -> str:
    return moment.isoformat()


def merge_busy(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        return []
    ordered = sorted(windows)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def free_blocks(
    window_start: datetime,
    window_end: datetime,
    events: Iterable[CalEvent],
) -> list[tuple[datetime, datetime]]:
    busy: list[tuple[datetime, datetime]] = []
    for event in events:
        if event.all_day or event.start is None or event.end is None:
            continue
        start = max(event.start, window_start)
        end = min(event.end, window_end)
        if start < end:
            busy.append((start, end))
    merged = merge_busy(busy)
    frees: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for start, end in merged:
        if cursor < start:
            frees.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        frees.append((cursor, window_end))
    return frees


def event_conflicts(events: Sequence[CalEvent]) -> list[tuple[CalEvent, CalEvent]]:
    timed = [
        event
        for event in events
        if not event.all_day and event.start is not None and event.end is not None
    ]
    timed.sort(key=lambda event: event.start or datetime.min.replace(tzinfo=timezone.utc))
    found: list[tuple[CalEvent, CalEvent]] = []
    for index, left in enumerate(timed):
        assert left.start is not None and left.end is not None
        for right in timed[index + 1 :]:
            assert right.start is not None and right.end is not None
            if right.start >= left.end:
                break
            if left.start < right.end and right.start < left.end:
                found.append((left, right))
    return found


def load_calendar_credentials(source: str, config_dir: Path | None = None) -> Any:
    cfg = config_dir if config_dir is not None else loop.CONFIG_DIR
    path = loop.token_path_for(source, cfg)
    if not path.is_file():
        raise FileNotFoundError(
            f"No token file at {path}. Run "
            f"./oauth_loop.py --source {source}"
        )
    creds = loop.load_existing_credentials(path, loop.scopes_for(source))
    return loop.refresh_if_needed(creds)


def list_events(
    session: Any,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[Mapping[str, Any]]:
    params = {
        "timeMin": rfc3339(window_start),
        "timeMax": rfc3339(window_end),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 100,
    }
    items: list[Mapping[str, Any]] = []
    page_token: str | None = None
    while True:
        query = dict(params)
        if page_token:
            query["pageToken"] = page_token
        response = session.get(CALENDAR_EVENTS_URL, params=query)
        status = int(response.status_code)
        if status in (401, 403):
            raise AuthError(
                f"Calendar events returned {status}. "
                "Run ./oauth_loop.py --source ulc_calendar --force"
            )
        if status != 200:
            raise RuntimeError(f"Calendar events returned {status}")
        payload = response.json()
        for item in payload.get("items") or []:
            if isinstance(item, dict):
                items.append(item)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return items


def pull_source(
    source: str,
    *,
    day: date,
    tz: timezone | ZoneInfo,
    config_dir: Path | None = None,
    session: Any | None = None,
) -> list[CalEvent]:
    window_start, window_end = day_window(day, tz)
    if session is None:
        creds = load_calendar_credentials(source, config_dir)
        session = loop.authorized_session(creds)
    account = ACCOUNT_FOR_SOURCE[source]
    parsed: list[CalEvent] = []
    for resource in list_events(
        session, window_start=window_start, window_end=window_end
    ):
        event = parse_event(resource, account=account, source=source, tz=tz)
        if event is not None:
            parsed.append(event)
    return parsed


def hhmm(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def render_report(
    *,
    day: date,
    events: Sequence[CalEvent],
    window_start: datetime,
    window_end: datetime,
    accounts: Sequence[str],
) -> str:
    timed = [e for e in events if not e.all_day]
    all_day = [e for e in events if e.all_day]
    timed.sort(key=lambda e: e.start or datetime.min.replace(tzinfo=timezone.utc))
    frees = free_blocks(window_start, window_end, timed)
    conflicts = event_conflicts(timed)
    lines = [
        f"date: {day.isoformat()}",
        f"accounts: {', '.join(accounts) if accounts else '(none)'}",
        f"events: {len(events)}",
        f"timed: {len(timed)}",
        f"all_day: {len(all_day)}",
        f"conflicts: {len(conflicts)}",
        "",
        "## Timed",
        "",
        "| Start | End | Title | Account | Organizer |",
        "| --- | --- | --- | --- | --- |",
    ]
    if timed:
        for event in timed:
            assert event.start is not None and event.end is not None
            title = event.summary.replace("|", "/")
            organizer = (event.organizer or "you").replace("|", "/")
            lines.append(
                f"| {hhmm(event.start)} | {hhmm(event.end)} | {title} | "
                f"{event.account} | {organizer} |"
            )
    else:
        lines.append("| — | — | (none) | — | — |")
    lines.extend(["", "## All-day", ""])
    if all_day:
        for event in all_day:
            title = event.summary.replace("|", "/")
            lines.append(f"- {title} ({event.account})")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Free blocks",
            "",
            "| Start | End | Minutes |",
            "| --- | --- | --- |",
        ]
    )
    if frees:
        for start, end in frees:
            minutes = int((end - start).total_seconds() // 60)
            lines.append(f"| {hhmm(start)} | {hhmm(end)} | {minutes} |")
    else:
        lines.append("| — | — | 0 |")
    lines.extend(["", "## Conflicts", ""])
    if conflicts:
        for left, right in conflicts:
            assert left.start and left.end and right.start and right.end
            lines.append(
                f"- {hhmm(left.start)}–{hhmm(left.end)} {left.summary} "
                f"overlaps {hhmm(right.start)}–{hhmm(right.end)} {right.summary}"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read today's Google Calendar events for Daily Planning. "
            "Reuses calendar token files. Does not write the vault."
        )
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date to read (default: today)",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=loop.calendar_sources(),
        help="Calendar source (repeatable). Default: every source that has a token.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def sources_to_read(args: argparse.Namespace) -> list[str]:
    if args.source:
        return list(args.source)
    cfg = args.config_dir if args.config_dir is not None else loop.CONFIG_DIR
    found = [
        source
        for source in loop.calendar_sources()
        if loop.token_path_for(source, cfg).is_file()
    ]
    return found


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    day = date.fromisoformat(args.date) if args.date else date.today()
    tz = local_tz()
    window_start, window_end = day_window(day, tz)
    sources = sources_to_read(args)
    if not sources:
        print(
            "No calendar token files. Run "
            "./oauth_loop.py --source ulc_calendar",
            file=sys.stderr,
        )
        return 2
    events: list[CalEvent] = []
    accounts: list[str] = []
    for source in sources:
        try:
            pulled = pull_source(
                source, day=day, tz=tz, config_dir=args.config_dir
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except AuthError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(
                f"Token refresh failed: {exc}. "
                f"Run ./oauth_loop.py --source {source} --force",
                file=sys.stderr,
            )
            return 1
        events.extend(pulled)
        accounts.append(ACCOUNT_FOR_SOURCE[source])
    print(
        render_report(
            day=day,
            events=events,
            window_start=window_start,
            window_end=window_end,
            accounts=accounts,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
