# Inbound feeds

Localhost Desktop OAuth against Google Cloud project
`personal-os-inbound-feeds`, client `personal-os-inbound-feeds-desktop`. Connect
is `oauth_loop.py`. ULC Gmail Pull → Filter → Store is `intake.py`. Calendar
live read for Daily Planning is `calendar_read.py`. Vault design:
`Notes/Inbound Feeds Connectors.md` → Token files, OAuth setup runbook,
Design stubs. Filter policy: `Management/Intake/Intake Rules.md`.

## What Connect writes

| Source | Token file |
| --- | --- |
| ULC Gmail | `~/.config/personal-os-inbound-feeds/tokens/ulc_gmail.json` |
| Personal Gmail | `~/.config/personal-os-inbound-feeds/tokens/personal_gmail.json` |
| ULC Calendar | `~/.config/personal-os-inbound-feeds/tokens/ulc_calendar.json` |
| Personal Calendar | `~/.config/personal-os-inbound-feeds/tokens/personal_calendar.json` |

The file is Google `authorized_user` JSON (`refresh_token`, `token_uri`,
`client_id`, `client_secret`). Mode `0600`. Never put this directory under
`personal-os/` or the vault.

Client ID and Secret stay in the password manager. The loop copies them into
the token file because `google-auth-oauthlib` expects that shape.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Credentials, pick one:

- Env: `PERSONAL_OS_INBOUND_FEEDS_CLIENT_ID` and
  `PERSONAL_OS_INBOUND_FEEDS_CLIENT_SECRET`
- File: `~/.config/personal-os-inbound-feeds/client.json` as either Google's
  Desktop `installed` JSON or `{"client_id": "...", "client_secret": "..."}`

Do not paste secrets into chat or vault notes. The Playground Web client is
rejected; use the Desktop client.

## Connect

```bash
./.venv/bin/python oauth_loop.py --source ulc_gmail
./.venv/bin/python oauth_loop.py --source personal_gmail
./.venv/bin/python oauth_loop.py --source ulc_calendar
./.venv/bin/python oauth_loop.py --source personal_calendar
```

A browser window opens. Sign in as that Account and Allow. Success prints the
token path and `Gmail list status: 200` or `Calendar list status: 200`.

```bash
./.venv/bin/python oauth_loop.py --source ulc_gmail --probe-only   # reuse token
./.venv/bin/python oauth_loop.py --source ulc_calendar --force     # re-consent
```

Testing-app refresh tokens expire on the order of seven days. Re-run `--force`
when Gmail or Calendar starts returning auth errors. `intake.py` and
`calendar_read.py` reuse these tokens and do not open a browser. If the file
is missing, run Connect. If the API returns 401 or 403 after a refresh, run
`--force`.

## Pull → Filter → Store

```bash
./.venv/bin/python intake.py --source ulc_gmail
./.venv/bin/python intake.py --source personal_gmail
./.venv/bin/python intake.py --source ulc_gmail --dry-run
```

Chat triggers on Management Intake Processing, so you do not type these
commands: `pull raw inputs` (both sources, stop), `process raw inputs`
(inventory only), `pull and process raw inputs` (Friday default).

`--vault` defaults to the repo `vault/` symlink. The script reads
`last_processed_batch_date` on `Management/Intake/Intake Ledger.md` and Pulls
after `max(that date, today minus 7 days)`. An optional Gmail query
excludes Promotions; Intake Rules still decide keep, drop, and borderline.

Store writes
`Management/Intake/YYYY-MM-DD Pulled ULC Gmail.md` or
`YYYY-MM-DD Pulled Personal Gmail.md` (run date). Frontmatter is
`source: ULC Gmail` or `source: Personal Gmail`, `account: ulc` or
`account: personal`, `pulled`, `status: unprocessed`. One `##`
section per keep or borderline message, with a `gmail_id` YAML block. Drops
are omitted. A `gmail_id` already present in any Pulled file of that type is
skipped. The script never writes Raw Inputs files or the five Management
brain folders, and it does not bump the ledger date.

`--dry-run` prints keep / borderline / drop / skipped-dupe counts and writes
nothing to the vault. A live run may append drop reasons (id and reason only)
under `~/.local/share/personal-os-inbound-feeds/drops/`.

## Calendar live read

```bash
./.venv/bin/python calendar_read.py
./.venv/bin/python calendar_read.py --date 2026-08-13
```

Daily Planning runs this at sequence time. It reads primary calendars for
every calendar token that exists (ULC and Personal), then prints timed
events, all-day events, free blocks from 08:00–18:00 local, and overlaps.
It does not write the vault. Missing tokens exit 2 with an oauth_loop hint.
Auth errors exit 1 with `--force`.

## Spec & tests

Rule: run the tests before committing any change to this tool, and keep them
green. The tests are the executable spec. They do not call Google or the live
vault.

Hard gate (pre-commit hook): a tracked hook blocks any commit that touches this
tool if its tests fail. Install once per clone:

```bash
bash hooks/install.sh
```

The dispatcher runs this tool's tests when `inbound-feeds/` files are staged.
Emergency bypass (discouraged): `git commit --no-verify`.

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

What they pin down:

- Source name ULC Gmail maps to `ulc_gmail.json`, not `ulc.json` or `gmail.json`
- Source name Personal Gmail maps to `personal_gmail.json`, not `gmail.json`
- Scope is the full `gmail.readonly` URI
- Token writes stay under `~/.config/personal-os-inbound-feeds/tokens/` and
  outside the repo and vault
- `authorized_user` JSON has `refresh_token`, `token_uri`, `client_id`,
  `client_secret`
- Desktop client JSON is accepted; Playground Web client JSON is rejected
- The Gmail list helper returns the HTTP status from a mocked session
- Intake filename is `YYYY-MM-DD Pulled ULC Gmail.md` with frontmatter
  `source: ULC Gmail`, `account: ulc`, `status: unprocessed`
- Pull window uses the ledger date when it is within seven days, otherwise
  the last seven days
- Missing token exits 2 without opening OAuth; mocked Gmail 401 exits 1 with
  a `--force` hint
- People `types: contact` keep on email or display name; the mailbox owner
  and Role Self do not keep the whole inbox
- Calendar RSVP, marketing `List-Unsubscribe`, and receipts drop even when a
  People contact is on the thread
- Sequel / ULC mail with substance keeps; empty calendar-accept from that
  domain still drops
- New sender on a known vendor domain is borderline with `needs_review: true`
- Cold outreach drops; `gmail_id` already in a Pulled file is skipped
- Store refuses Raw Inputs paths and does not write the five Management
  folders
- Calendar sources map to `ulc_calendar.json` and `personal_calendar.json`
  with the full `calendar.readonly` URI
- Free blocks subtract timed events from 08:00–18:00; adjacent events do not
  count as conflicts; cancelled events are skipped
- Missing calendar token exits 2; mocked Calendar 401 exits 1 with a
  `--force` hint
