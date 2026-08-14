"""Hermetic tests for the inbound-feeds Desktop OAuth loop.

Run: ./.venv/bin/python -m unittest discover -s tests   (from inbound-feeds/)

These do not call Google. Path rules, authorized_user shape, and the Gmail
probe helper are the spec. The live localhost consent is a manual step.
"""

import json
import stat
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import oauth_loop as loop  # noqa: E402

SAMPLE_USER = {
    "type": "authorized_user",
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "refresh_token": "test-refresh-token",
    "token_uri": loop.TOKEN_URI,
}


class TestSourceAndPaths(unittest.TestCase):
    def test_ulc_gmail_label_and_filename(self):
        self.assertEqual(loop.source_label("ulc_gmail"), "ULC Gmail")
        self.assertEqual(loop.source_token_filename("ulc_gmail"), "ulc_gmail.json")
        self.assertNotEqual(loop.source_token_filename("ulc_gmail"), "ulc.json")

    def test_calendar_sources(self):
        self.assertEqual(loop.source_label("ulc_calendar"), "ULC Calendar")
        self.assertEqual(
            loop.source_token_filename("ulc_calendar"), "ulc_calendar.json"
        )
        self.assertEqual(loop.source_label("personal_calendar"), "Personal Calendar")
        self.assertEqual(
            loop.source_token_filename("personal_calendar"),
            "personal_calendar.json",
        )
        self.assertEqual(loop.source_feed("ulc_calendar"), loop.FEED_CALENDAR)
        self.assertEqual(loop.source_feed("ulc_gmail"), loop.FEED_GMAIL)

    def test_personal_gmail_label_and_filename(self):
        self.assertEqual(loop.source_label("personal_gmail"), "Personal Gmail")
        self.assertEqual(
            loop.source_token_filename("personal_gmail"), "personal_gmail.json"
        )
        self.assertNotEqual(
            loop.source_token_filename("personal_gmail"), "gmail.json"
        )
        self.assertEqual(loop.source_feed("personal_gmail"), loop.FEED_GMAIL)
        self.assertIn("personal_gmail", loop.gmail_sources())

    def test_unknown_source(self):
        for fn in (loop.source_label, loop.source_token_filename):
            with self.assertRaises(ValueError):
                fn("gmail")
            with self.assertRaises(ValueError):
                fn("ulc")

    def test_token_path(self):
        cfg = Path("/tmp/personal-os-inbound-feeds-test-cfg")
        self.assertEqual(
            loop.token_path_for("ulc_gmail", cfg),
            cfg / "tokens" / "ulc_gmail.json",
        )


class TestScope(unittest.TestCase):
    def test_gmail_readonly_is_full_uri(self):
        self.assertEqual(
            loop.GMAIL_READONLY_SCOPE,
            "https://www.googleapis.com/auth/gmail.readonly",
        )
        self.assertNotIn(loop.GMAIL_READONLY_SCOPE, ("gmail.readonly", "gmail"))
        self.assertEqual(loop.SCOPES, [loop.GMAIL_READONLY_SCOPE])

    def test_calendar_readonly_is_full_uri(self):
        self.assertEqual(
            loop.CALENDAR_READONLY_SCOPE,
            "https://www.googleapis.com/auth/calendar.readonly",
        )
        self.assertEqual(
            loop.scopes_for("ulc_calendar"),
            [loop.CALENDAR_READONLY_SCOPE],
        )
        self.assertEqual(
            loop.scopes_for("ulc_gmail"),
            [loop.GMAIL_READONLY_SCOPE],
        )
        self.assertNotEqual(
            loop.scopes_for("ulc_calendar"),
            loop.scopes_for("ulc_gmail"),
        )


class TestAuthorizedUser(unittest.TestCase):
    def test_valid(self):
        loop.validate_authorized_user(SAMPLE_USER)

    def test_missing_refresh_token(self):
        payload = dict(SAMPLE_USER)
        del payload["refresh_token"]
        with self.assertRaises(ValueError):
            loop.validate_authorized_user(payload)

    def test_wrong_type(self):
        payload = dict(SAMPLE_USER, type="service_account")
        with self.assertRaises(ValueError):
            loop.validate_authorized_user(payload)

    def test_from_credentials_json(self):
        class FakeCreds:
            def to_json(self):
                payload = dict(SAMPLE_USER)
                del payload["type"]
                return json.dumps(payload)

        out = loop.authorized_user_from_credentials(FakeCreds())
        self.assertEqual(out["type"], "authorized_user")
        self.assertEqual(out["refresh_token"], "test-refresh-token")


class TestWriteTokenFile(unittest.TestCase):
    def test_writes_under_config_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            repo = Path(tmp) / "personal-os"
            repo.mkdir()
            dest = loop.token_path_for("ulc_gmail", cfg)
            loop.write_token_file(
                dest, SAMPLE_USER, config_dir=cfg, forbidden_trees=[repo]
            )
            written = json.loads(dest.read_text())
            self.assertEqual(written["refresh_token"], "test-refresh-token")
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)

    def test_refuses_repo_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            repo = Path(tmp) / "personal-os"
            repo.mkdir()
            dest = repo / "ulc_gmail.json"
            with self.assertRaises(ValueError):
                loop.write_token_file(
                    dest, SAMPLE_USER, config_dir=cfg, forbidden_trees=[repo]
                )

    def test_refuses_vault_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            vault = Path(tmp) / "vault"
            vault.mkdir()
            dest = vault / "ulc_gmail.json"
            with self.assertRaises(ValueError):
                loop.write_token_file(
                    dest, SAMPLE_USER, config_dir=cfg, forbidden_trees=[vault]
                )


class TestLoadClient(unittest.TestCase):
    def test_env_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            client_path = Path(tmp) / "client.json"
            client_path.write_text(
                json.dumps({"client_id": "file-id", "client_secret": "file-secret"})
            )
            client_id, client_secret = loop.load_client_id_secret(
                environ={
                    loop.ENV_CLIENT_ID: "env-id",
                    loop.ENV_CLIENT_SECRET: "env-secret",
                },
                client_path=client_path,
            )
            self.assertEqual(client_id, "env-id")
            self.assertEqual(client_secret, "env-secret")

    def test_installed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            client_path = Path(tmp) / "client.json"
            client_path.write_text(
                json.dumps(
                    {
                        "installed": {
                            "client_id": "desktop-id",
                            "client_secret": "desktop-secret",
                        }
                    }
                )
            )
            client_id, client_secret = loop.load_client_id_secret(
                environ={}, client_path=client_path
            )
            self.assertEqual(client_id, "desktop-id")
            self.assertEqual(client_secret, "desktop-secret")

    def test_rejects_web_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            client_path = Path(tmp) / "client.json"
            client_path.write_text(
                json.dumps(
                    {"web": {"client_id": "web-id", "client_secret": "web-secret"}}
                )
            )
            with self.assertRaises(ValueError):
                loop.load_client_id_secret(environ={}, client_path=client_path)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                loop.load_client_id_secret(
                    environ={}, client_path=Path(tmp) / "missing.json"
                )


class TestClientConfig(unittest.TestCase):
    def test_desktop_shape(self):
        config = loop.client_config_for("id", "secret")
        installed = config["installed"]
        self.assertEqual(installed["redirect_uris"], ["http://localhost"])
        self.assertEqual(installed["token_uri"], loop.TOKEN_URI)


class TestProbe(unittest.TestCase):
    def test_returns_status_code(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200)
        self.assertEqual(loop.probe_gmail_list(session), 200)
        session.get.assert_called_once_with(
            loop.GMAIL_LIST_URL, params={"maxResults": 1}
        )

    def test_non_200(self):
        session = Mock()
        session.get.return_value = Mock(status_code=401)
        self.assertEqual(loop.probe_gmail_list(session), 401)

    def test_calendar_probe(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200)
        self.assertEqual(loop.probe_calendar_list(session), 200)
        session.get.assert_called_once_with(
            loop.CALENDAR_LIST_URL, params={"maxResults": 1}
        )
        name, status = loop.probe_source(session, "ulc_calendar")
        self.assertEqual(name, "Calendar list")
        self.assertEqual(status, 200)


class TestCli(unittest.TestCase):
    def test_default_source_is_ulc_gmail(self):
        args = loop.parse_args([])
        self.assertEqual(args.source, "ulc_gmail")

    def test_rejects_force_with_probe_only(self):
        with patch("sys.stderr", StringIO()):
            self.assertEqual(loop.main(["--force", "--probe-only"]), 2)


if __name__ == "__main__":
    unittest.main()
