"""Localhost Desktop OAuth loop for inbound feeds.

Writes Google authorized_user JSON for one source and probes one list page
(Gmail or Calendar). Does not Pull, Filter, or Store mail, and does not
materialize calendar events.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = [GMAIL_READONLY_SCOPE]
GMAIL_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"

FEED_GMAIL = "gmail"
FEED_CALENDAR = "calendar"

SOURCE_ULC_GMAIL = "ulc_gmail"
SOURCE_PERSONAL_GMAIL = "personal_gmail"
SOURCE_ULC_CALENDAR = "ulc_calendar"
SOURCE_PERSONAL_CALENDAR = "personal_calendar"
SOURCE_LABELS = {
    SOURCE_ULC_GMAIL: "ULC Gmail",
    SOURCE_PERSONAL_GMAIL: "Personal Gmail",
    SOURCE_ULC_CALENDAR: "ULC Calendar",
    SOURCE_PERSONAL_CALENDAR: "Personal Calendar",
}
SOURCE_TOKEN_FILES = {
    SOURCE_ULC_GMAIL: "ulc_gmail.json",
    SOURCE_PERSONAL_GMAIL: "personal_gmail.json",
    SOURCE_ULC_CALENDAR: "ulc_calendar.json",
    SOURCE_PERSONAL_CALENDAR: "personal_calendar.json",
}
SOURCE_FEEDS = {
    SOURCE_ULC_GMAIL: FEED_GMAIL,
    SOURCE_PERSONAL_GMAIL: FEED_GMAIL,
    SOURCE_ULC_CALENDAR: FEED_CALENDAR,
    SOURCE_PERSONAL_CALENDAR: FEED_CALENDAR,
}
SOURCE_SCOPES = {
    SOURCE_ULC_GMAIL: [GMAIL_READONLY_SCOPE],
    SOURCE_PERSONAL_GMAIL: [GMAIL_READONLY_SCOPE],
    SOURCE_ULC_CALENDAR: [CALENDAR_READONLY_SCOPE],
    SOURCE_PERSONAL_CALENDAR: [CALENDAR_READONLY_SCOPE],
}

CONFIG_DIR = Path.home() / ".config" / "personal-os-inbound-feeds"
CLIENT_FILE = CONFIG_DIR / "client.json"
ENV_CLIENT_ID = "PERSONAL_OS_INBOUND_FEEDS_CLIENT_ID"
ENV_CLIENT_SECRET = "PERSONAL_OS_INBOUND_FEEDS_CLIENT_SECRET"

AUTHORIZED_USER_REQUIRED_KEYS = (
    "refresh_token",
    "token_uri",
    "client_id",
    "client_secret",
)


def source_label(source: str) -> str:
    try:
        return SOURCE_LABELS[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def source_token_filename(source: str) -> str:
    try:
        return SOURCE_TOKEN_FILES[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def source_feed(source: str) -> str:
    try:
        return SOURCE_FEEDS[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def scopes_for(source: str) -> list[str]:
    try:
        return list(SOURCE_SCOPES[source])
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def calendar_sources() -> list[str]:
    return sorted(s for s, feed in SOURCE_FEEDS.items() if feed == FEED_CALENDAR)


def gmail_sources() -> list[str]:
    return sorted(s for s, feed in SOURCE_FEEDS.items() if feed == FEED_GMAIL)


def token_path_for(source: str, config_dir: Path = CONFIG_DIR) -> Path:
    return config_dir / "tokens" / source_token_filename(source)


def default_forbidden_trees() -> list[Path]:
    repo_root = Path(__file__).resolve().parent.parent
    trees = [repo_root]
    vault = repo_root / "vault"
    if vault.exists():
        trees.append(vault.resolve())
    return trees


def assert_token_path_allowed(
    path: Path,
    config_dir: Path = CONFIG_DIR,
    forbidden_trees: list[Path] | None = None,
) -> None:
    resolved = path.resolve()
    tokens_dir = (config_dir / "tokens").resolve()
    try:
        resolved.relative_to(tokens_dir)
    except ValueError as exc:
        raise ValueError(
            f"token path {resolved} must be under {tokens_dir}"
        ) from exc
    trees = forbidden_trees if forbidden_trees is not None else default_forbidden_trees()
    for tree in trees:
        tree_resolved = tree.resolve()
        try:
            resolved.relative_to(tree_resolved)
        except ValueError:
            continue
        raise ValueError(f"token path {resolved} is inside {tree_resolved}")


def validate_authorized_user(data: Mapping[str, Any]) -> None:
    missing = [key for key in AUTHORIZED_USER_REQUIRED_KEYS if not data.get(key)]
    if missing:
        raise ValueError(
            "authorized_user JSON missing " + ", ".join(missing)
        )
    token_type = data.get("type")
    if token_type is not None and token_type != "authorized_user":
        raise ValueError(f"unexpected token type: {token_type}")


def write_token_file(
    path: Path,
    payload: Mapping[str, Any],
    *,
    config_dir: Path = CONFIG_DIR,
    forbidden_trees: list[Path] | None = None,
) -> None:
    validate_authorized_user(payload)
    assert_token_path_allowed(
        path, config_dir=config_dir, forbidden_trees=forbidden_trees
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def load_client_id_secret(
    *,
    environ: Mapping[str, str] | None = None,
    client_path: Path | None = None,
) -> tuple[str, str]:
    env = environ if environ is not None else os.environ
    env_id = str(env.get(ENV_CLIENT_ID, "")).strip()
    env_secret = str(env.get(ENV_CLIENT_SECRET, "")).strip()
    if env_id and env_secret:
        return env_id, env_secret
    path = client_path if client_path is not None else CLIENT_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"Set {ENV_CLIENT_ID} and {ENV_CLIENT_SECRET}, or write Desktop "
            f"client JSON to {path}"
        )
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("client JSON must be an object")
    if "web" in data and "installed" not in data:
        raise ValueError(
            "Web client JSON is the Playground probe; use the Desktop client "
            "personal-os-inbound-feeds-desktop"
        )
    installed = data.get("installed")
    if isinstance(installed, dict):
        client_id = str(installed.get("client_id", "")).strip()
        client_secret = str(installed.get("client_secret", "")).strip()
    else:
        client_id = str(data.get("client_id", "")).strip()
        client_secret = str(data.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        raise ValueError("client JSON needs client_id and client_secret")
    return client_id, client_secret


def client_config_for(client_id: str, client_secret: str) -> dict[str, Any]:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


def probe_gmail_list(session: Any) -> int:
    response = session.get(GMAIL_LIST_URL, params={"maxResults": 1})
    return int(response.status_code)


def probe_calendar_list(session: Any) -> int:
    response = session.get(CALENDAR_LIST_URL, params={"maxResults": 1})
    return int(response.status_code)


def probe_source(session: Any, source: str) -> tuple[str, int]:
    if source_feed(source) == FEED_CALENDAR:
        return "Calendar list", probe_calendar_list(session)
    return "Gmail list", probe_gmail_list(session)


def authorized_user_from_credentials(creds: Any) -> dict[str, Any]:
    payload = json.loads(creds.to_json())
    if "type" not in payload:
        payload["type"] = "authorized_user"
    if not payload.get("token_uri"):
        payload["token_uri"] = TOKEN_URI
    validate_authorized_user(payload)
    return payload


def run_desktop_oauth(
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
    label: str = "ULC Gmail",
) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow

    used_scopes = scopes if scopes is not None else SCOPES
    flow = InstalledAppFlow.from_client_config(
        client_config_for(client_id, client_secret),
        scopes=used_scopes,
    )
    return flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message=(
            f"Open the browser window to grant {label} read access.\n"
            "If it does not open, visit: {url}\n"
        ),
        success_message="You can close this tab and return to the terminal.",
    )


def load_existing_credentials(path: Path, scopes: list[str] | None = None) -> Any:
    from google.oauth2.credentials import Credentials

    used = scopes if scopes is not None else SCOPES
    return Credentials.from_authorized_user_file(str(path), used)


def refresh_if_needed(creds: Any) -> Any:
    from google.auth.transport.requests import Request

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def authorized_session(creds: Any) -> Any:
    from google.auth.transport.requests import AuthorizedSession

    return AuthorizedSession(creds)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Localhost Desktop OAuth for inbound feeds. Writes authorized_user "
            "JSON and probes one Gmail or Calendar list page. Does not store "
            "mail or events."
        )
    )
    parser.add_argument(
        "--source",
        default=SOURCE_ULC_GMAIL,
        choices=sorted(SOURCE_TOKEN_FILES),
        help="Token file stem (default: ulc_gmail → ULC Gmail)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore an existing token file and run the browser consent again.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Reuse the existing token file; do not open a browser.",
    )
    parser.add_argument(
        "--print-token-path",
        action="store_true",
        help="Print the token path for --source and exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    label = source_label(args.source)
    path = token_path_for(args.source)
    if args.print_token_path:
        print(path)
        return 0
    if args.probe_only and args.force:
        print("Use either --probe-only or --force, not both.", file=sys.stderr)
        return 2

    scopes = scopes_for(args.source)
    creds = None
    if args.probe_only:
        if not path.is_file():
            print(f"No token file at {path}", file=sys.stderr)
            return 2
        creds = load_existing_credentials(path, scopes)
        creds = refresh_if_needed(creds)
        write_token_file(path, authorized_user_from_credentials(creds))
        print(f"Reused token for {label}: {path}")
    elif path.is_file() and not args.force:
        creds = load_existing_credentials(path, scopes)
        creds = refresh_if_needed(creds)
        write_token_file(path, authorized_user_from_credentials(creds))
        print(f"Reused token for {label}: {path}")
    else:
        try:
            client_id, client_secret = load_client_id_secret()
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        creds = run_desktop_oauth(
            client_id, client_secret, scopes=scopes, label=label
        )
        write_token_file(path, authorized_user_from_credentials(creds))
        print(f"Wrote token for {label}: {path}")

    probe_name, status = probe_source(authorized_session(creds), args.source)
    print(f"{probe_name} status: {status}")
    if status != 200:
        print(f"Expected 200 from {probe_name} for {label}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
