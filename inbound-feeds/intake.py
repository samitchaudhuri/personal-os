"""Pull → Filter → Store for Gmail intake.

Reuses the Desktop OAuth token from oauth_loop.py. Applies Ingress rules from
Intake Rules (implemented here; the markdown note stays authoritative). Writes
one Pulled ULC Gmail or Pulled Personal Gmail intake batch file. Does not open
a browser, write Raw Inputs files, or touch the five Management brain folders.
"""

from __future__ import annotations

import argparse
import base64
import html as html_module
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any, Iterable, Mapping

import oauth_loop as loop

SOURCE_ULC_GMAIL = loop.SOURCE_ULC_GMAIL
SOURCE_PERSONAL_GMAIL = loop.SOURCE_PERSONAL_GMAIL
MAILBOX_OWNER_EMAILS = {
    SOURCE_ULC_GMAIL: "samit.chaudhuri@ultimatelongevitycenters.com",
    SOURCE_PERSONAL_GMAIL: "samit.chaudhuri@gmail.com",
}
SOURCE_ACCOUNTS = {
    SOURCE_ULC_GMAIL: "ulc",
    SOURCE_PERSONAL_GMAIL: "personal",
}
PULLED_SUFFIX = {
    SOURCE_ULC_GMAIL: "Pulled ULC Gmail.md",
    SOURCE_PERSONAL_GMAIL: "Pulled Personal Gmail.md",
}
FRANCHISE_DOMAINS = frozenset(
    {
        "sequelbrands.com",
        "ultimatelongevitycenters.com",
    }
)
CONSUMER_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "live.com",
        "msn.com",
    }
)
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
DROP_LOG_DIR = Path.home() / ".local" / "share" / "personal-os-inbound-feeds" / "drops"

INGRESS_KEEP = "keep"
INGRESS_DROP = "drop"
INGRESS_BORDERLINE = "borderline"

FIVE_MANAGEMENT_FOLDERS = (
    "Management/Team",
    "Management/Portfolios",
    "Management/Decisions",
    "Management/Context",
    "Management/Playbooks",
)

CALENDAR_SUBJECT = re.compile(
    r"(accepted:|declined:|tentative:|invitation updated|updated invitation|"
    r"^invitation:|you('ve| have) been invited|\brsvp\b)",
    re.I,
)
CALENDAR_BODY_NOISE = re.compile(
    r"(view this event|google calendar|yes, I will attend|going\?|"
    r"invitation from Google Calendar)",
    re.I,
)
UNSUBSCRIBE = re.compile(r"\bunsubscribe\b|\bopt[ -]?out\b", re.I)
RECEIPT_SUBJECT = re.compile(
    r"\b(receipt|payment confirmation|your order|order confirmed|"
    r"payment received|thanks for your (order|purchase))\b",
    re.I,
)
DISPUTE = re.compile(
    r"\b(dispute|void|withdraw|does not match|please reverse|do not pay)\b",
    re.I,
)
SUBSTANCE = re.compile(
    r"\b(decision|deadline|loi|letter of intent|site|build-?out|"
    r"please (reply|confirm|review|advise)|need(s)? a reply|"
    r"entity|formation|lease|compliance|franchise|counsel|invoice|"
    r"amendment|operating agreement|articles of organization|"
    r"holdco|opco)\b",
    re.I,
)
MIXED_HOUSEHOLD_LEGAL = re.compile(
    r"\b(living[- ]trust|household|personal legal|holdco)\b",
    re.I,
)
ATTACHMENT_PACK = re.compile(
    r"\b(formation|articles|operating agreement|site report|loi|lease)\b",
    re.I,
)
SELF_ROLE = re.compile(r"(?im)^\s*[-*]?\s*\*?\*?Role:?\*?\*?\s*Self\s*$")


class AuthError(Exception):
    """Gmail returned 401/403 or the refresh token is dead."""


@dataclass
class Contact:
    name: str
    emails: set[str]
    is_self: bool = False


@dataclass
class ParsedMessage:
    gmail_id: str
    thread_id: str
    from_header: str = ""
    to_header: str = ""
    cc_header: str = ""
    date_header: str = ""
    subject: str = ""
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    attachment_names: list[str] = field(default_factory=list)
    thread_excerpt: str = ""


@dataclass
class Classification:
    ingress: str
    reason: str

    @property
    def needs_review(self) -> bool:
        return self.ingress == INGRESS_BORDERLINE


@dataclass
class RunCounts:
    pulled: int = 0
    keep: int = 0
    borderline: int = 0
    drop: int = 0
    skipped_dupe: int = 0


def default_vault_root() -> Path:
    return Path(__file__).resolve().parent.parent / "vault"


def intake_dir(vault_root: Path) -> Path:
    return vault_root / "Management" / "Intake"


def ledger_path(vault_root: Path) -> Path:
    return intake_dir(vault_root) / "Intake Ledger.md"


def pulled_filename(run_date: date, source: str = SOURCE_ULC_GMAIL) -> str:
    try:
        suffix = PULLED_SUFFIX[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc
    return f"{run_date.isoformat()} {suffix}"


def pulled_path(
    vault_root: Path, run_date: date, source: str = SOURCE_ULC_GMAIL
) -> Path:
    name = pulled_filename(run_date, source)
    if "Raw Inputs" in name:
        raise ValueError("Pulled Gmail path must not be a Raw Inputs file")
    return intake_dir(vault_root) / name


def mailbox_owner_email(source: str) -> str:
    try:
        return MAILBOX_OWNER_EMAILS[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def source_account(source: str) -> str:
    try:
        return SOURCE_ACCOUNTS[source]
    except KeyError as exc:
        raise ValueError(f"unknown source: {source}") from exc


def after_date(ledger_date: date | None, today: date) -> date:
    seven_days_ago = today - timedelta(days=7)
    if ledger_date is None:
        return seven_days_ago
    return max(ledger_date, seven_days_ago)


def gmail_after_query(after: date) -> str:
    return (
        f"after:{after.year}/{after.month:02d}/{after.day:02d} "
        "-category:promotions"
    )


def parse_simple_frontmatter(text: str) -> dict[str, Any] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    for raw in text[3:end].splitlines():
        line = raw.rstrip()
        keyed = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if keyed:
            if current_key is not None and current_list is not None:
                data[current_key] = current_list
            current_key = keyed.group(1)
            rest = keyed.group(2).strip()
            if rest in ("", "[]"):
                current_list = []
                if rest == "[]":
                    data[current_key] = []
                    current_key = None
                    current_list = None
            else:
                if (rest.startswith('"') and rest.endswith('"')) or (
                    rest.startswith("'") and rest.endswith("'")
                ):
                    rest = rest[1:-1]
                data[current_key] = rest
                current_list = None
                current_key = None
            continue
        stripped = line.strip()
        if current_list is not None and stripped.startswith("-"):
            item = stripped[1:].strip()
            if (item.startswith('"') and item.endswith('"')) or (
                item.startswith("'") and item.endswith("'")
            ):
                item = item[1:-1]
            current_list.append(item)
    if current_key is not None and current_list is not None:
        data[current_key] = current_list
    return data


def parse_ledger_date(text: str) -> date | None:
    fm = parse_simple_frontmatter(text)
    if not fm:
        return None
    raw = str(fm.get("last_processed_batch_date", "")).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def load_ledger_date(path: Path) -> date | None:
    if not path.is_file():
        return None
    return parse_ledger_date(path.read_text())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _emails_from_note(fm: Mapping[str, Any], text: str) -> set[str]:
    emails: set[str] = set()
    raw = str(fm.get("email", "")).strip()
    if raw and "@" in raw:
        emails.add(raw.lower())
    for match in re.finditer(
        r"(?im)^\s*[-*]?\s*\*?\*?Email:?\*?\*?\s*(\S+@\S+)", text
    ):
        emails.add(match.group(1).strip("<>").lower())
    return {e.rstrip(".,;") for e in emails if "@" in e}


def load_contacts(vault_root: Path) -> list[Contact]:
    contacts: list[Contact] = []
    root = vault_root.resolve()
    for path in root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_simple_frontmatter(text)
        if not fm:
            continue
        categories = " ".join(_as_list(fm.get("categories")))
        if "[[People]]" not in categories:
            continue
        types = [t.strip() for t in _as_list(fm.get("types"))]
        if "contact" not in types:
            continue
        name = _first_heading(text) or path.stem
        body = text[text.find("\n---", 3) + 4 :] if "\n---" in text[3:] else text
        is_self = bool(SELF_ROLE.search(body))
        contacts.append(
            Contact(name=name, emails=_emails_from_note(fm, text), is_self=is_self)
        )
    return contacts


def vendor_domains(contacts: Iterable[Contact], source: str) -> set[str]:
    owner = mailbox_owner_email(source)
    domains: set[str] = set(FRANCHISE_DOMAINS)
    for contact in contacts:
        for email in contact.emails:
            if email == owner:
                continue
            domain = email.rsplit("@", 1)[-1].lower()
            if domain in CONSUMER_MAIL_DOMAINS:
                continue
            domains.add(domain)
    return domains


def parse_addresses(header: str) -> list[tuple[str, str]]:
    if not header.strip():
        return []
    return [
        (name.strip(), addr.lower())
        for name, addr in getaddresses([header])
        if addr
    ]


def participants(message: ParsedMessage) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for header in (message.from_header, message.to_header, message.cc_header):
        for name, addr in parse_addresses(header):
            key = addr or name.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((name, addr))
    return found


def _header(headers: Mapping[str, str], name: str) -> str:
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(name.lower(), "")


def b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
        "utf-8", errors="replace"
    )


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _walk_parts(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield payload
    for part in payload.get("parts") or []:
        if isinstance(part, dict):
            yield from _walk_parts(part)


def parse_gmail_resource(
    resource: Mapping[str, Any], thread_excerpt: str = ""
) -> ParsedMessage:
    payload = resource.get("payload") or {}
    headers = {
        str(h.get("name", "")): str(h.get("value", ""))
        for h in payload.get("headers") or []
        if isinstance(h, dict)
    }
    plain = ""
    html_body = ""
    attachments: list[str] = []
    for part in _walk_parts(payload):
        filename = str(part.get("filename") or "").strip()
        mime = str(part.get("mimeType") or "")
        body = part.get("body") or {}
        data = body.get("data")
        if filename:
            attachments.append(filename)
        if not data:
            continue
        decoded = b64url_decode(str(data))
        if mime == "text/plain" and not plain:
            plain = decoded
        elif mime == "text/html" and not html_body:
            html_body = decoded
    body_text = plain.strip() or strip_html(html_body)
    return ParsedMessage(
        gmail_id=str(resource.get("id") or ""),
        thread_id=str(resource.get("threadId") or ""),
        from_header=_header(headers, "From"),
        to_header=_header(headers, "To"),
        cc_header=_header(headers, "Cc"),
        date_header=_header(headers, "Date"),
        subject=_header(headers, "Subject"),
        body=body_text,
        headers={k.lower(): v for k, v in headers.items()},
        attachment_names=attachments,
        thread_excerpt=thread_excerpt,
    )


def _body_len(message: ParsedMessage) -> int:
    return len(re.sub(r"\s+", " ", message.body).strip())


def is_calendar_noise(message: ParsedMessage) -> bool:
    subject = message.subject
    if not CALENDAR_SUBJECT.search(subject):
        if not CALENDAR_BODY_NOISE.search(message.body):
            return False
    return _body_len(message) < 400 or bool(CALENDAR_BODY_NOISE.search(message.body))


def is_marketing(message: ParsedMessage) -> bool:
    if message.headers.get("list-unsubscribe"):
        return True
    if UNSUBSCRIBE.search(message.body) and _body_len(message) < 1500:
        if not SUBSTANCE.search(message.body):
            return True
    return False


def is_receipt(message: ParsedMessage) -> bool:
    if DISPUTE.search(message.subject) or DISPUTE.search(message.body):
        return False
    return bool(RECEIPT_SUBJECT.search(message.subject))


def contact_match(
    message: ParsedMessage,
    contacts: Iterable[Contact],
    source: str,
) -> Contact | None:
    owner = mailbox_owner_email(source)
    people = [c for c in contacts if not c.is_self and owner not in c.emails]
    for name, addr in participants(message):
        if addr == owner:
            continue
        for contact in people:
            if addr and addr in contact.emails:
                return contact
            if contact.name and name and contact.name.lower() == name.lower():
                return contact
    return None


def participant_domains(message: ParsedMessage, source: str) -> set[str]:
    owner = mailbox_owner_email(source)
    domains: set[str] = set()
    for _, addr in participants(message):
        if not addr or addr == owner:
            continue
        domains.add(addr.rsplit("@", 1)[-1].lower())
    return domains


def classify(
    message: ParsedMessage,
    contacts: Iterable[Contact],
    source: str = SOURCE_ULC_GMAIL,
    known_domains: set[str] | None = None,
) -> Classification:
    domains = known_domains if known_domains is not None else vendor_domains(
        contacts, source
    )
    msg_domains = participant_domains(message, source)

    if is_calendar_noise(message):
        return Classification(INGRESS_DROP, "calendar_rsvp")
    if is_marketing(message):
        return Classification(INGRESS_DROP, "marketing")
    if is_receipt(message):
        return Classification(INGRESS_DROP, "receipt")

    if contact_match(message, contacts, source):
        return Classification(INGRESS_KEEP, "people_contact")

    franchise_hit = bool(msg_domains & FRANCHISE_DOMAINS)
    vendor_hit = bool(msg_domains & (domains - FRANCHISE_DOMAINS))
    known_hit = bool(msg_domains & domains)
    has_substance = bool(SUBSTANCE.search(message.subject) or SUBSTANCE.search(message.body))

    if franchise_hit and has_substance:
        return Classification(INGRESS_KEEP, "franchise_ops")
    if vendor_hit and has_substance:
        return Classification(INGRESS_KEEP, "vendor_thread")

    if known_hit:
        return Classification(INGRESS_BORDERLINE, "new_sender_known_domain")
    if MIXED_HOUSEHOLD_LEGAL.search(message.body) or MIXED_HOUSEHOLD_LEGAL.search(
        message.subject
    ):
        return Classification(INGRESS_BORDERLINE, "mixed_household_legal")
    if message.attachment_names and ATTACHMENT_PACK.search(
        " ".join(message.attachment_names) + " " + message.subject
    ):
        return Classification(INGRESS_BORDERLINE, "attachment_pack")

    if msg_domains and not known_hit:
        return Classification(INGRESS_DROP, "cold_outreach")
    return Classification(INGRESS_BORDERLINE, "unsure")


def existing_gmail_ids(intake: Path, source: str = SOURCE_ULC_GMAIL) -> set[str]:
    found: set[str] = set()
    if not intake.is_dir():
        return found
    suffix = PULLED_SUFFIX[source]
    for path in intake.glob(f"*{suffix}"):
        found.update(re.findall(r"(?m)^gmail_id:\s*(\S+)", path.read_text()))
    return found


def yaml_scalar(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = value.replace("\n", " ").strip()
    if text == "":
        return '""'
    if re.search(r"[:#{}[\],&*?|!<>=%@`]", text) or text[0] in "'\"":
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def section_heading(message: ParsedMessage) -> str:
    subject = message.subject.strip() or message.gmail_id
    subject = subject.replace("\n", " ")
    return subject[:120]


def render_section(message: ParsedMessage, classification: Classification) -> str:
    lines = [
        f"## {section_heading(message)}",
        "",
        "```yaml",
        f"gmail_id: {yaml_scalar(message.gmail_id)}",
        f"thread_id: {yaml_scalar(message.thread_id)}",
        f"from: {yaml_scalar(message.from_header)}",
        f"to: {yaml_scalar(message.to_header)}",
        f"cc: {yaml_scalar(message.cc_header)}",
        f"date: {yaml_scalar(message.date_header)}",
        f"subject: {yaml_scalar(message.subject)}",
        f"ingress: {classification.ingress}",
        f"needs_review: {yaml_scalar(classification.needs_review)}",
        "```",
        "",
        message.body.strip() or "_(no plain-text body)_",
    ]
    if message.thread_excerpt.strip():
        lines.extend(["", "### Thread excerpt", "", message.thread_excerpt.strip()])
    lines.append("")
    return "\n".join(lines)


def render_frontmatter(pulled: datetime, source: str = SOURCE_ULC_GMAIL) -> str:
    iso = pulled.isoformat(timespec="seconds")
    return (
        "---\n"
        f"source: {loop.source_label(source)}\n"
        f"account: {source_account(source)}\n"
        f"pulled: {iso}\n"
        "status: unprocessed\n"
        "---\n"
    )


def merge_batch_file(
    path: Path,
    sections: list[str],
    pulled: datetime,
    source: str = SOURCE_ULC_GMAIL,
) -> str:
    body = "\n".join(sections).rstrip() + "\n"
    if not path.is_file():
        return render_frontmatter(pulled, source) + "\n" + body
    existing = path.read_text()
    existing = re.sub(
        r"(?m)^pulled:\s*.*$",
        f"pulled: {pulled.isoformat(timespec='seconds')}",
        existing,
        count=1,
    )
    if not existing.endswith("\n"):
        existing += "\n"
    return existing.rstrip() + "\n\n" + body


def assert_store_path_allowed(path: Path, vault_root: Path) -> None:
    resolved = path.resolve()
    intake = intake_dir(vault_root).resolve()
    try:
        resolved.relative_to(intake)
    except ValueError as exc:
        raise ValueError(f"store path {resolved} must be under {intake}") from exc
    if "Raw Inputs" in path.name:
        raise ValueError("refusing to write a Raw Inputs file")
    if not re.search(r"Pulled .+ Gmail\.md$", path.name):
        raise ValueError(f"unexpected intake batch filename: {path.name}")
    for folder in FIVE_MANAGEMENT_FOLDERS:
        forbidden = (vault_root / folder).resolve()
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            continue
        raise ValueError(f"refusing to write {folder}")


def store_batch(path: Path, content: str, vault_root: Path) -> None:
    assert_store_path_allowed(path, vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_drop_log(run_date: date, rows: list[tuple[str, str]]) -> Path | None:
    if not rows:
        return None
    DROP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DROP_LOG_DIR.parent, 0o700)
    dest = DROP_LOG_DIR / f"{run_date.isoformat()}.log"
    with dest.open("a", encoding="utf-8") as handle:
        for gmail_id, reason in rows:
            handle.write(f"{gmail_id}\t{reason}\n")
    os.chmod(dest, 0o600)
    return dest


def load_token_credentials(source: str, config_dir: Path | None = None) -> Any:
    cfg = config_dir if config_dir is not None else loop.CONFIG_DIR
    path = loop.token_path_for(source, cfg)
    if not path.is_file():
        raise FileNotFoundError(
            f"No token file at {path}. Run "
            f"./oauth_loop.py --source {source}"
        )
    creds = loop.load_existing_credentials(path, loop.scopes_for(source))
    return loop.refresh_if_needed(creds)


def _raise_for_auth(status: int, what: str, source: str = SOURCE_ULC_GMAIL) -> None:
    if status in (401, 403):
        raise AuthError(
            f"Gmail {what} returned {status}. "
            f"Run ./oauth_loop.py --source {source} --force"
        )


def list_message_ids(
    session: Any, query: str, source: str = SOURCE_ULC_GMAIL
) -> list[str]:
    ids: list[str] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        response = session.get(GMAIL_MESSAGES_URL, params=params)
        _raise_for_auth(response.status_code, "list", source)
        if response.status_code != 200:
            raise RuntimeError(f"Gmail list returned {response.status_code}")
        payload = response.json()
        for item in payload.get("messages") or []:
            msg_id = str(item.get("id") or "")
            if msg_id:
                ids.append(msg_id)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return ids


def get_message(
    session: Any, msg_id: str, source: str = SOURCE_ULC_GMAIL
) -> Mapping[str, Any]:
    response = session.get(
        f"{GMAIL_MESSAGES_URL}/{msg_id}", params={"format": "full"}
    )
    _raise_for_auth(response.status_code, "get", source)
    if response.status_code != 200:
        raise RuntimeError(f"Gmail get returned {response.status_code}")
    return response.json()


def thread_excerpt(session: Any, thread_id: str, current_id: str) -> str:
    if not thread_id:
        return ""
    response = session.get(
        f"{GMAIL_THREADS_URL}/{thread_id}",
        params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
    )
    if response.status_code != 200:
        return ""
    snippets: list[str] = []
    for item in (response.json().get("messages") or []):
        other_id = str(item.get("id") or "")
        if other_id == current_id:
            continue
        snippet = str(item.get("snippet") or "").strip()
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= 3:
            break
    return "\n\n".join(snippets)


def pull_messages(
    session: Any, query: str, source: str = SOURCE_ULC_GMAIL
) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    for msg_id in list_message_ids(session, query, source):
        resource = get_message(session, msg_id, source)
        excerpt = thread_excerpt(
            session, str(resource.get("threadId") or ""), msg_id
        )
        messages.append(parse_gmail_resource(resource, excerpt))
    return messages


def filter_and_store(
    messages: list[ParsedMessage],
    *,
    vault_root: Path,
    source: str,
    run_date: date,
    pulled_at: datetime,
    dry_run: bool = False,
) -> tuple[RunCounts, Path]:
    contacts = load_contacts(vault_root)
    domains = vendor_domains(contacts, source)
    seen = existing_gmail_ids(intake_dir(vault_root), source)
    dest = pulled_path(vault_root, run_date, source)
    counts = RunCounts(pulled=len(messages))
    sections: list[str] = []
    drops: list[tuple[str, str]] = []
    for message in messages:
        if message.gmail_id in seen:
            counts.skipped_dupe += 1
            continue
        classification = classify(
            message, contacts, source=source, known_domains=domains
        )
        if classification.ingress == INGRESS_DROP:
            counts.drop += 1
            drops.append((message.gmail_id, classification.reason))
            continue
        if classification.ingress == INGRESS_KEEP:
            counts.keep += 1
        else:
            counts.borderline += 1
        sections.append(render_section(message, classification))
        seen.add(message.gmail_id)
    if not dry_run:
        if sections:
            content = merge_batch_file(dest, sections, pulled_at, source)
            store_batch(dest, content, vault_root)
        write_drop_log(run_date, drops)
    return counts, dest


def print_counts(
    counts: RunCounts,
    *,
    after: date,
    dest: Path,
    dry_run: bool,
    source: str = SOURCE_ULC_GMAIL,
) -> None:
    print(f"source: {loop.source_label(source)}")
    print(f"window after: {after.isoformat()}")
    print(f"pulled: {counts.pulled}")
    print(f"keep: {counts.keep}")
    print(f"borderline: {counts.borderline}")
    print(f"drop: {counts.drop}")
    print(f"skipped dupe: {counts.skipped_dupe}")
    if dry_run:
        print(f"dry-run, would write: {dest}")
    elif counts.keep or counts.borderline:
        print(f"wrote: {dest}")
    else:
        print(f"no keep/borderline; left {dest} unchanged")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pull ULC or Personal Gmail, filter with Intake Rules, and store "
            "a Pulled intake batch file. Reuses the existing token; does "
            "not open a browser."
        )
    )
    parser.add_argument(
        "--source",
        default=SOURCE_ULC_GMAIL,
        choices=sorted(loop.gmail_sources()),
        help="Token file stem (default: ulc_gmail → ULC Gmail)",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Vault root (default: repo vault/ symlink)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and print counts; do not write the intake batch file.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault_root = args.vault if args.vault is not None else default_vault_root()
    source = args.source
    today = date.today()
    after = after_date(load_ledger_date(ledger_path(vault_root)), today)
    query = gmail_after_query(after)
    try:
        creds = load_token_credentials(source, args.config_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Token refresh failed: {exc}. "
            f"Run ./oauth_loop.py --source {source} --force",
            file=sys.stderr,
        )
        return 1
    session = loop.authorized_session(creds)
    try:
        messages = pull_messages(session, query, source)
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    counts, dest = filter_and_store(
        messages,
        vault_root=vault_root,
        source=source,
        run_date=today,
        pulled_at=datetime.now().astimezone(),
        dry_run=args.dry_run,
    )
    print_counts(
        counts, after=after, dest=dest, dry_run=args.dry_run, source=source
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
