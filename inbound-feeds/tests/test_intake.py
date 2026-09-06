"""Hermetic tests for ULC Gmail Pull → Filter → Store.

Run: ./.venv/bin/python -m unittest discover -s tests -v   (from inbound-feeds/)

These do not call Google or the live vault. Window math, Intake Rules ingress,
batch frontmatter, and gmail_id dedupe are the spec.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import intake  # noqa: E402
import oauth_loop as loop  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE_VAULT = HERE / "fixtures" / "vault"
GMAIL_PLAIN = HERE / "fixtures" / "gmail" / "plain_message.json"
OWNER = "samit.chaudhuri@ultimatelongevitycenters.com"


def _msg(**kwargs) -> intake.ParsedMessage:
    defaults = dict(
        gmail_id="msg-1",
        thread_id="thread-1",
        from_header=f"Someone <someone@example.com>",
        to_header=f"Samit Chaudhuri <{OWNER}>",
        cc_header="",
        date_header="Tue, 11 Aug 2026 09:00:00 -0700",
        subject="Hello",
        body="Hello",
        headers={},
        attachment_names=[],
        thread_excerpt="",
    )
    defaults.update(kwargs)
    return intake.ParsedMessage(**defaults)


class TestWindow(unittest.TestCase):
    def test_recent_ledger_wins(self):
        self.assertEqual(
            intake.after_date(date(2026, 8, 7), date(2026, 8, 13)),
            date(2026, 8, 7),
        )

    def test_stale_ledger_uses_seven_days(self):
        self.assertEqual(
            intake.after_date(date(2026, 5, 1), date(2026, 8, 13)),
            date(2026, 8, 6),
        )

    def test_missing_ledger_uses_seven_days(self):
        self.assertEqual(
            intake.after_date(None, date(2026, 8, 13)),
            date(2026, 8, 6),
        )

    def test_gmail_query_shape(self):
        self.assertEqual(
            intake.gmail_after_query(date(2026, 8, 7)),
            "after:2026/08/07 -category:promotions",
        )

    def test_gmail_query_with_before(self):
        self.assertEqual(
            intake.gmail_after_query(date(2026, 8, 7), date(2026, 8, 8)),
            "after:2026/08/07 before:2026/08/08 -category:promotions",
        )

    def test_date_chunks_default_one_day_each(self):
        self.assertEqual(
            intake.date_chunks(date(2026, 8, 7), date(2026, 8, 9)),
            [
                (date(2026, 8, 7), date(2026, 8, 8)),
                (date(2026, 8, 8), date(2026, 8, 9)),
                (date(2026, 8, 9), date(2026, 8, 10)),
            ],
        )

    def test_date_chunks_same_day(self):
        self.assertEqual(
            intake.date_chunks(date(2026, 8, 7), date(2026, 8, 7)),
            [(date(2026, 8, 7), date(2026, 8, 8))],
        )

    def test_date_chunks_wider_window(self):
        self.assertEqual(
            intake.date_chunks(date(2026, 8, 1), date(2026, 8, 6), window_days=3),
            [
                (date(2026, 8, 1), date(2026, 8, 4)),
                (date(2026, 8, 4), date(2026, 8, 7)),
            ],
        )

    def test_date_chunks_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            intake.date_chunks(date(2026, 8, 7), date(2026, 8, 9), window_days=0)


class TestLedger(unittest.TestCase):
    def test_fixture_ledger_date(self):
        text = (FIXTURE_VAULT / "Management/Intake/Intake Ledger.md").read_text()
        self.assertEqual(intake.parse_ledger_date(text), date(2026, 8, 7))

    def test_missing_file(self):
        self.assertIsNone(intake.load_ledger_date(Path("/no/such/Intake Ledger.md")))

    def test_unparsable(self):
        self.assertIsNone(intake.parse_ledger_date("---\nlast_processed_batch_date: nope\n---\n"))


class TestContacts(unittest.TestCase):
    def setUp(self):
        self.contacts = intake.load_contacts(FIXTURE_VAULT)
        self.by_name = {c.name: c for c in self.contacts}

    def test_loads_people_contacts_only(self):
        self.assertIn("Don Michael", self.by_name)
        self.assertIn("Gabriel Arechiga", self.by_name)
        self.assertIn("Jack Santaniello", self.by_name)
        self.assertIn("Samit Chaudhuri", self.by_name)
        self.assertNotIn("Naseem Taleb", self.by_name)

    def test_email_and_name_only(self):
        self.assertEqual(
            self.by_name["Don Michael"].emails,
            {"don@ultimatelongevitycenters.com"},
        )
        self.assertEqual(self.by_name["Gabriel Arechiga"].emails, set())

    def test_self_flag(self):
        self.assertTrue(self.by_name["Samit Chaudhuri"].is_self)
        self.assertFalse(self.by_name["Don Michael"].is_self)

    def test_vendor_domains_include_shumaker_not_gmail(self):
        domains = intake.vendor_domains(self.contacts, "ulc_gmail")
        self.assertIn("shumaker.com", domains)
        self.assertIn("ultimatelongevitycenters.com", domains)
        self.assertIn("sequelbrands.com", domains)
        self.assertNotIn("gmail.com", domains)


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.contacts = intake.load_contacts(FIXTURE_VAULT)
        self.domains = intake.vendor_domains(self.contacts, "ulc_gmail")

    def _classify(self, message: intake.ParsedMessage) -> intake.Classification:
        return intake.classify(
            message, self.contacts, source="ulc_gmail", known_domains=self.domains
        )

    def test_people_email_keep(self):
        result = self._classify(
            _msg(
                from_header="Don Michael <don@ultimatelongevitycenters.com>",
                subject="Biweekly notes",
                body="Can we talk Saturday about the site pipeline.",
            )
        )
        self.assertEqual(result.ingress, "keep")
        self.assertEqual(result.reason, "people_contact")
        self.assertFalse(result.needs_review)

    def test_people_display_name_keep(self):
        result = self._classify(
            _msg(
                from_header="Gabriel Arechiga <gabriel@franchiseconsult.example>",
                subject="Marin is open",
                body="San Rafael / Marin County is open. Talk to Cam.",
            )
        )
        self.assertEqual(result.ingress, "keep")
        self.assertEqual(result.reason, "people_contact")

    def test_self_does_not_keep_everything(self):
        result = self._classify(
            _msg(
                from_header=f"Samit Chaudhuri <{OWNER}>",
                to_header="Promo Bot <deals@retail-blast.example>",
                subject="Re: 50% off blenders",
                body="Thanks, not interested.",
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "cold_outreach")

    def test_personal_mailbox_owner_does_not_keep_everything(self):
        result = intake.classify(
            _msg(
                from_header="Samit Chaudhuri <samit.chaudhuri@gmail.com>",
                to_header="Promo Bot <deals@retail-blast.example>",
                subject="Re: 50% off blenders",
                body="Thanks, not interested.",
            ),
            self.contacts,
            source="personal_gmail",
            known_domains=self.domains,
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "cold_outreach")

    def test_calendar_rsvp_drops_even_from_people(self):
        result = self._classify(
            _msg(
                from_header="Don Michael <don@ultimatelongevitycenters.com>",
                subject="Accepted: ULC biweekly",
                body="Don Michael has accepted this invitation.\nView this event in Google Calendar.",
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "calendar_rsvp")

    def test_marketing_list_unsubscribe(self):
        result = self._classify(
            _msg(
                from_header="News <hello@newsletter.example>",
                subject="This week in franchising",
                body="Open our newsletter. Click unsubscribe at the bottom.",
                headers={"list-unsubscribe": "<mailto:unsub@newsletter.example>"},
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "marketing")

    def test_receipt_drops(self):
        result = self._classify(
            _msg(
                from_header="Stripe <receipts@stripe.com>",
                subject="Your receipt from Acme",
                body="Payment received for $12.00. Thank you.",
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "receipt")

    def test_receipt_with_dispute_does_not_drop(self):
        result = self._classify(
            _msg(
                from_header="Lisa Cave <lcave@shumaker.com>",
                subject="Your receipt / invoice",
                body="Please withdraw or void this invoice. It does not match our arrangement.",
            )
        )
        self.assertEqual(result.ingress, "keep")
        self.assertEqual(result.reason, "vendor_thread")

    def test_franchise_substance_keep(self):
        result = self._classify(
            _msg(
                from_header="Ops Desk <ops@sequelbrands.com>",
                subject="LOI deadline for Campbell",
                body="Please review the letter of intent and site build-out step by Friday.",
            )
        )
        self.assertEqual(result.ingress, "keep")
        self.assertEqual(result.reason, "franchise_ops")

    def test_franchise_calendar_accept_still_drops(self):
        result = self._classify(
            _msg(
                from_header="Ops Desk <ops@sequelbrands.com>",
                subject="Accepted: training calendar",
                body="Invitation from Google Calendar. View this event.",
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "calendar_rsvp")

    def test_new_sender_known_vendor_domain_borderline(self):
        result = self._classify(
            _msg(
                from_header="New Associate <associate@shumaker.com>",
                subject="Introducing myself",
                body="I just joined the firm and wanted to say hello.",
            )
        )
        self.assertEqual(result.ingress, "borderline")
        self.assertTrue(result.needs_review)
        self.assertEqual(result.reason, "new_sender_known_domain")

    def test_cold_outreach_drops(self):
        result = self._classify(
            _msg(
                from_header="Pat Sales <pat@coldpipe.example>",
                subject="Quick question about your franchise",
                body="We help franchisees rank on Google. Are you free Thursday?",
            )
        )
        self.assertEqual(result.ingress, "drop")
        self.assertEqual(result.reason, "cold_outreach")

    def test_mixed_household_legal_borderline(self):
        result = self._classify(
            _msg(
                from_header="Trust Desk <desk@estateplanner.example>",
                subject="Living trust managers for HoldCo",
                body="Draft living-trust language that also names the HoldCo.",
            )
        )
        self.assertEqual(result.ingress, "borderline")
        self.assertEqual(result.reason, "mixed_household_legal")

    def test_attachment_pack_borderline(self):
        result = self._classify(
            _msg(
                from_header="Filings <docs@formaco.example>",
                subject="Articles packet",
                body="See attached.",
                attachment_names=["Articles of Organization.pdf"],
            )
        )
        self.assertEqual(result.ingress, "borderline")
        self.assertEqual(result.reason, "attachment_pack")


class TestGmailParse(unittest.TestCase):
    def test_prefers_plain_over_html(self):
        resource = json.loads(GMAIL_PLAIN.read_text())
        parsed = intake.parse_gmail_resource(resource)
        self.assertEqual(parsed.gmail_id, "msg-plain-1")
        self.assertIn("LOI deadline", parsed.body)
        self.assertNotIn("HTML body should not win", parsed.body)
        self.assertEqual(parsed.subject, "LOI deadline Friday")

    def test_html_only_strips_tags(self):
        html = "<p>Please confirm the <b>lease</b> by Friday.</p>"
        encoded = intake.base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        resource = {
            "id": "html-1",
            "threadId": "t-html",
            "payload": {
                "mimeType": "text/html",
                "headers": [{"name": "Subject", "value": "Lease"}],
                "body": {"data": encoded},
            },
        }
        parsed = intake.parse_gmail_resource(resource)
        self.assertIn("Please confirm the lease by Friday.", parsed.body)
        self.assertNotIn("<p>", parsed.body)


class TestPullMessages(unittest.TestCase):
    def _patched_fetch(self, ids):
        return (
            patch.object(intake, "list_message_ids", return_value=ids),
            patch.object(intake, "get_message", return_value={"threadId": "t"}),
            patch.object(intake, "thread_excerpt", return_value=""),
            patch.object(
                intake,
                "parse_gmail_resource",
                side_effect=lambda r, e: _msg(gmail_id="x"),
            ),
        )

    def test_message_pause_throttles_between_fetches_not_before_first(self):
        patches = self._patched_fetch(["a", "b", "c"])
        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(intake.time, "sleep") as sleep_mock:
                messages, skipped = intake.pull_messages(
                    Mock(), "q", message_pause=0.3
                )
        self.assertEqual(len(messages), 3)
        self.assertEqual(skipped, 0)
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_called_with(0.3)

    def test_dupes_are_skipped_without_sleeping_or_fetching(self):
        patches = self._patched_fetch(["a", "b"])
        with patches[0], patches[1] as get_mock, patches[2], patches[3]:
            with patch.object(intake.time, "sleep") as sleep_mock:
                messages, skipped = intake.pull_messages(
                    Mock(), "q", seen={"a"}, message_pause=0.3
                )
        self.assertEqual(skipped, 1)
        self.assertEqual(len(messages), 1)
        get_mock.assert_called_once()
        self.assertEqual(get_mock.call_args.args[1], "b")
        sleep_mock.assert_not_called()

    def test_zero_message_pause_never_sleeps(self):
        patches = self._patched_fetch(["a", "b", "c"])
        with patches[0], patches[1], patches[2], patches[3]:
            with patch.object(intake.time, "sleep") as sleep_mock:
                intake.pull_messages(Mock(), "q", message_pause=0.0)
        sleep_mock.assert_not_called()


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.vault = self.tmp / "vault"
        shutil.copytree(FIXTURE_VAULT, self.vault)
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_filename_and_frontmatter(self):
        dest = intake.pulled_path(self.vault, date(2026, 8, 13))
        self.assertEqual(dest.name, "2026-08-13 Pulled ULC Gmail.md")
        self.assertNotIn("Raw Inputs", dest.name)
        message = _msg(
            gmail_id="keep-1",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Site ask",
            body="Please reply about the Campbell LOI.",
        )
        pulled_at = datetime(2026, 8, 13, 17, 0, tzinfo=timezone.utc)
        counts, path = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=pulled_at,
        )
        self.assertEqual(path, dest)
        self.assertEqual(counts.keep, 1)
        text = dest.read_text()
        self.assertIn("source: ULC Gmail", text)
        self.assertIn("account: ulc", text)
        self.assertIn("status: unprocessed", text)
        self.assertIn("pulled: 2026-08-13T17:00:00+00:00", text)
        self.assertIn("gmail_id: keep-1", text)
        self.assertIn("ingress: keep", text)
        self.assertNotIn("source: ulc\n", text)
        self.assertNotIn("source: gmail", text)

    def test_personal_gmail_filename_and_frontmatter(self):
        dest = intake.pulled_path(
            self.vault, date(2026, 8, 13), "personal_gmail"
        )
        self.assertEqual(dest.name, "2026-08-13 Pulled Personal Gmail.md")
        self.assertNotIn("Raw Inputs", dest.name)
        message = _msg(
            gmail_id="keep-personal-1",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Site ask",
            body="Please reply about the Campbell LOI.",
        )
        counts, path = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="personal_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, 17, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(path, dest)
        self.assertEqual(counts.keep, 1)
        text = dest.read_text()
        self.assertIn("source: Personal Gmail", text)
        self.assertIn("account: personal", text)
        self.assertIn("status: unprocessed", text)
        self.assertNotIn("source: ULC Gmail", text)
        self.assertFalse(
            (self.vault / "Management/Intake/2026-08-13 Pulled ULC Gmail.md").exists()
        )

    def test_skips_existing_gmail_id(self):
        message = _msg(
            gmail_id="already-stored-id",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Duplicate",
            body="Please reply about the site.",
        )
        counts, _ = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(counts.skipped_dupe, 1)
        self.assertEqual(counts.keep, 0)
        self.assertFalse(
            (self.vault / "Management/Intake/2026-08-13 Pulled ULC Gmail.md").exists()
        )

    def test_personal_dedupe_does_not_use_ulc_ids(self):
        message = _msg(
            gmail_id="already-stored-id",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Same id different mailbox",
            body="Please reply about the site.",
        )
        counts, dest = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="personal_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(counts.skipped_dupe, 0)
        self.assertEqual(counts.keep, 1)
        self.assertTrue(dest.exists())

    def test_drops_are_not_written(self):
        message = _msg(
            gmail_id="drop-1",
            from_header="Pat Sales <pat@coldpipe.example>",
            subject="Buy my SEO",
            body="Are you free Thursday?",
        )
        counts, dest = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(counts.drop, 1)
        self.assertFalse(dest.exists())

    def test_borderline_needs_review(self):
        message = _msg(
            gmail_id="border-1",
            from_header="New Associate <associate@shumaker.com>",
            subject="Hello",
            body="I just joined the firm.",
        )
        counts, dest = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(counts.borderline, 1)
        text = dest.read_text()
        self.assertIn("ingress: borderline", text)
        self.assertIn("needs_review: true", text)

    def test_does_not_write_five_management_folders(self):
        message = _msg(
            gmail_id="keep-folders",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Site ask",
            body="Please reply about the Campbell LOI.",
        )
        intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        for folder in (
            "Management/Portfolios",
            "Management/Decisions",
            "Management/Context",
            "Management/Playbooks",
        ):
            self.assertFalse((self.vault / folder).exists())
        self.assertFalse(
            (self.vault / "Management/Intake/2026-08-13 Raw Inputs.md").exists()
        )

    def test_refuses_raw_inputs_store_path(self):
        raw = self.vault / "Management/Intake/2026-08-13 Raw Inputs.md"
        with self.assertRaises(ValueError):
            intake.store_batch(raw, "nope", self.vault)

    def test_dry_run_writes_nothing(self):
        message = _msg(
            gmail_id="dry-1",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="Site ask",
            body="Please reply about the Campbell LOI.",
        )
        counts, dest = intake.filter_and_store(
            [message],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            dry_run=True,
        )
        self.assertEqual(counts.keep, 1)
        self.assertFalse(dest.exists())

    def test_same_day_merge_appends(self):
        pulled_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
        first = _msg(
            gmail_id="keep-a",
            from_header="Don Michael <don@ultimatelongevitycenters.com>",
            subject="First",
            body="Please reply about the site.",
        )
        second = _msg(
            gmail_id="keep-b",
            from_header="Gabriel Arechiga <gabriel@franchiseconsult.example>",
            subject="Second",
            body="Marin is open. Talk to Cam.",
        )
        intake.filter_and_store(
            [first],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=pulled_at,
        )
        intake.filter_and_store(
            [second],
            vault_root=self.vault,
            source="ulc_gmail",
            run_date=date(2026, 8, 13),
            pulled_at=pulled_at,
        )
        text = (self.vault / "Management/Intake/2026-08-13 Pulled ULC Gmail.md").read_text()
        self.assertEqual(text.count("gmail_id: keep-a"), 1)
        self.assertEqual(text.count("gmail_id: keep-b"), 1)


class TestCli(unittest.TestCase):
    def test_default_source_is_ulc_gmail(self):
        args = intake.parse_args([])
        self.assertEqual(args.source, "ulc_gmail")

    def test_accepts_personal_gmail(self):
        args = intake.parse_args(["--source", "personal_gmail"])
        self.assertEqual(args.source, "personal_gmail")

    def test_missing_token_exits_2_without_oauth(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            vault = Path(tmp) / "vault"
            shutil.copytree(FIXTURE_VAULT, vault)
            with patch("sys.stderr", StringIO()) as err:
                with patch.object(intake, "pull_messages") as pull:
                    with patch.object(loop, "run_desktop_oauth") as oauth:
                        code = intake.main(
                            [
                                "--vault",
                                str(vault),
                                "--config-dir",
                                str(cfg),
                            ]
                        )
            self.assertEqual(code, 2)
            self.assertIn("oauth_loop.py", err.getvalue())
            pull.assert_not_called()
            oauth.assert_not_called()

    def test_chunks_by_day_and_persists_before_rate_limit_stops_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            shutil.copytree(FIXTURE_VAULT, vault)
            today = date.today()
            ledger = vault / "Management/Intake/Intake Ledger.md"
            ledger.write_text(
                "---\n"
                f"last_processed_batch_date: {(today - timedelta(days=2)).isoformat()}\n"
                "---\n\n# Intake ledger\n"
            )
            msg_a = _msg(
                gmail_id="chunk-a",
                subject="A",
                from_header="Don Michael <don@ultimatelongevitycenters.com>",
            )
            msg_b = _msg(
                gmail_id="chunk-b",
                subject="B",
                from_header="Don Michael <don@ultimatelongevitycenters.com>",
            )
            rate_limit_error = intake.AuthError("Gmail list returned 403 (rateLimitExceeded)")
            with patch.object(
                intake,
                "pull_messages",
                side_effect=[([msg_a], 0), ([msg_b], 0), rate_limit_error],
            ) as pull:
                with patch.object(intake.time, "sleep") as sleep_mock:
                    with patch.object(
                        intake, "load_token_credentials", return_value=object()
                    ):
                        with patch.object(
                            loop, "authorized_session", return_value=Mock()
                        ):
                            with patch("sys.stderr", StringIO()) as err:
                                code = intake.main(
                                    ["--vault", str(vault), "--pause-seconds", "5"]
                                )
            self.assertEqual(code, 1)
            self.assertEqual(pull.call_count, 3)
            self.assertIn("rateLimitExceeded", err.getvalue())
            # paused between each pair of consecutive chunks (3 chunks -> 2 pauses)
            self.assertEqual(sleep_mock.call_count, 2)
            sleep_mock.assert_called_with(5.0)
            text = (
                vault / f"Management/Intake/{today.isoformat()} Pulled ULC Gmail.md"
            ).read_text()
            self.assertIn("gmail_id: chunk-a", text)
            self.assertIn("gmail_id: chunk-b", text)

    def test_pause_seconds_zero_skips_sleep(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            shutil.copytree(FIXTURE_VAULT, vault)
            today = date.today()
            ledger = vault / "Management/Intake/Intake Ledger.md"
            ledger.write_text(
                "---\n"
                f"last_processed_batch_date: {(today - timedelta(days=1)).isoformat()}\n"
                "---\n\n# Intake ledger\n"
            )
            with patch.object(
                intake, "pull_messages", return_value=([], 0)
            ):
                with patch.object(intake.time, "sleep") as sleep_mock:
                    with patch.object(
                        intake, "load_token_credentials", return_value=object()
                    ):
                        with patch.object(
                            loop, "authorized_session", return_value=Mock()
                        ):
                            code = intake.main(
                                ["--vault", str(vault), "--pause-seconds", "0"]
                            )
            self.assertEqual(code, 0)
            sleep_mock.assert_not_called()

    def test_gmail_401_exits_1_with_force_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            shutil.copytree(FIXTURE_VAULT, vault)
            session = Mock()
            session.get.return_value = Mock(status_code=401)
            with patch.object(intake, "load_token_credentials", return_value=object()):
                with patch.object(loop, "authorized_session", return_value=session):
                    with patch("sys.stderr", StringIO()) as err:
                        code = intake.main(["--vault", str(vault)])
            self.assertEqual(code, 1)
            self.assertIn("--force", err.getvalue())


if __name__ == "__main__":
    unittest.main()
