"""Hermetic tests for Calendar live read (Daily Planning v2.0 phase 1).

Run: ./.venv/bin/python -m unittest discover -s tests -v   (from inbound-feeds/)

These do not call Google. Event parse, free-block math, and conflict detection
are the spec.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime, time
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import calendar_read as cal  # noqa: E402
import oauth_loop as loop  # noqa: E402

TZ = ZoneInfo("America/Los_Angeles")
DAY = date(2026, 8, 13)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 13, hour, minute, tzinfo=TZ)


def _event(**kwargs) -> cal.CalEvent:
    defaults = dict(
        event_id="e1",
        summary="Event",
        start=_dt(10),
        end=_dt(11),
        all_day=False,
        account="ulc",
        source="ulc_calendar",
        organizer=None,
    )
    defaults.update(kwargs)
    return cal.CalEvent(**defaults)


class TestParseEvent(unittest.TestCase):
    def test_timed(self):
        event = cal.parse_event(
            {
                "id": "abc",
                "summary": "Michael",
                "status": "confirmed",
                "start": {"dateTime": "2026-08-13T10:00:00-07:00"},
                "end": {"dateTime": "2026-08-13T10:30:00-07:00"},
            },
            account="ulc",
            source="ulc_calendar",
            tz=TZ,
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertFalse(event.all_day)
        self.assertEqual(event.start, _dt(10))
        self.assertEqual(event.end, _dt(10, 30))
        self.assertEqual(event.summary, "Michael")
        self.assertEqual(event.account, "ulc")

    def test_all_day(self):
        event = cal.parse_event(
            {
                "id": "day",
                "summary": "Out",
                "start": {"date": "2026-08-13"},
                "end": {"date": "2026-08-14"},
            },
            account="personal",
            source="personal_calendar",
            tz=TZ,
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertTrue(event.all_day)
        self.assertIsNone(event.start)

    def test_skips_cancelled(self):
        self.assertIsNone(
            cal.parse_event(
                {
                    "id": "x",
                    "status": "cancelled",
                    "start": {"dateTime": "2026-08-13T10:00:00-07:00"},
                    "end": {"dateTime": "2026-08-13T11:00:00-07:00"},
                },
                account="ulc",
                source="ulc_calendar",
                tz=TZ,
            )
        )

    def test_organizer_captured_when_not_self(self):
        event = cal.parse_event(
            {
                "id": "org",
                "summary": "Weekly Touch Base",
                "organizer": {
                    "email": "anson.switzer@morrowhill.com",
                    "displayName": "Anson Switzer",
                    "self": False,
                },
                "start": {"dateTime": "2026-08-13T11:30:00-07:00"},
                "end": {"dateTime": "2026-08-13T12:00:00-07:00"},
            },
            account="ulc",
            source="ulc_calendar",
            tz=TZ,
        )
        assert event is not None
        self.assertEqual(event.organizer, "Anson Switzer")

    def test_organizer_none_when_self(self):
        event = cal.parse_event(
            {
                "id": "self",
                "summary": "Focus block",
                "organizer": {"email": "samit@example.com", "self": True},
                "start": {"dateTime": "2026-08-13T10:00:00-07:00"},
                "end": {"dateTime": "2026-08-13T10:30:00-07:00"},
            },
            account="ulc",
            source="ulc_calendar",
            tz=TZ,
        )
        assert event is not None
        self.assertIsNone(event.organizer)


class TestFreeBlocks(unittest.TestCase):
    def test_gap_around_one_meeting(self):
        window = cal.day_window(DAY, TZ, time(8), time(18))
        frees = cal.free_blocks(window[0], window[1], [_event()])
        self.assertEqual(frees, [(_dt(8), _dt(10)), (_dt(11), _dt(18))])

    def test_adjacent_meetings_merge_busy(self):
        window = cal.day_window(DAY, TZ)
        events = [
            _event(event_id="a", start=_dt(9), end=_dt(10)),
            _event(event_id="b", start=_dt(10), end=_dt(11)),
        ]
        frees = cal.free_blocks(window[0], window[1], events)
        self.assertEqual(frees[0], (_dt(8), _dt(9)))
        self.assertEqual(frees[1], (_dt(11), _dt(18)))

    def test_all_day_does_not_consume_slots(self):
        window = cal.day_window(DAY, TZ)
        events = [
            _event(event_id="d", summary="PTO", start=None, end=None, all_day=True)
        ]
        frees = cal.free_blocks(window[0], window[1], events)
        self.assertEqual(frees, [(window[0], window[1])])


class TestConflicts(unittest.TestCase):
    def test_overlap(self):
        events = [
            _event(event_id="a", summary="A", start=_dt(10), end=_dt(11)),
            _event(event_id="b", summary="B", start=_dt(10, 30), end=_dt(11, 30)),
        ]
        pairs = cal.event_conflicts(events)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0].summary, "A")
        self.assertEqual(pairs[0][1].summary, "B")

    def test_no_overlap_when_adjacent(self):
        events = [
            _event(event_id="a", start=_dt(10), end=_dt(11)),
            _event(event_id="b", start=_dt(11), end=_dt(12)),
        ]
        self.assertEqual(cal.event_conflicts(events), [])


class TestRender(unittest.TestCase):
    def test_report_has_sections_and_accounts(self):
        window = cal.day_window(DAY, TZ)
        text = cal.render_report(
            day=DAY,
            events=[
                _event(summary="Michael"),
                _event(
                    event_id="c",
                    summary="Anson sync",
                    start=_dt(13),
                    end=_dt(13, 30),
                    organizer="Anson Switzer",
                ),
                _event(
                    event_id="d",
                    summary="Holiday",
                    start=None,
                    end=None,
                    all_day=True,
                    account="personal",
                ),
            ],
            window_start=window[0],
            window_end=window[1],
            accounts=["ulc", "personal"],
        )
        self.assertIn("date: 2026-08-13", text)
        self.assertIn("accounts: ulc, personal", text)
        self.assertIn("## Timed", text)
        self.assertIn("Michael", text)
        self.assertIn("| Anson sync | ulc | Anson Switzer |", text)
        self.assertIn("| Michael | ulc | you |", text)
        self.assertIn("## All-day", text)
        self.assertIn("Holiday", text)
        self.assertIn("## Free blocks", text)
        self.assertIn("## Conflicts", text)
        self.assertIn("- none", text)
        self.assertNotIn("description", text.lower().split("holiday")[0][-40:])


class TestCli(unittest.TestCase):
    def test_missing_token_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            with patch("sys.stderr", StringIO()) as err:
                code = cal.main(["--date", "2026-08-13", "--config-dir", str(cfg)])
            self.assertEqual(code, 2)
            self.assertIn("oauth_loop.py", err.getvalue())

    def test_calendar_401_exits_1(self):
        session = Mock()
        session.get.return_value = Mock(status_code=401)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            dest = loop.token_path_for("ulc_calendar", cfg)
            dest.parent.mkdir(parents=True)
            dest.write_text("{}")
            with patch.object(cal, "load_calendar_credentials", return_value=object()):
                with patch.object(loop, "authorized_session", return_value=session):
                    with patch("sys.stderr", StringIO()) as err:
                        code = cal.main(
                            [
                                "--date",
                                "2026-08-13",
                                "--source",
                                "ulc_calendar",
                                "--config-dir",
                                str(cfg),
                            ]
                        )
            self.assertEqual(code, 1)
            self.assertIn("--force", err.getvalue())


if __name__ == "__main__":
    unittest.main()
