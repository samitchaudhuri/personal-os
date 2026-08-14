# Inbound feeds OAuth loop

Localhost Desktop OAuth against Google Cloud project
`personal-os-inbound-feeds`, client `personal-os-inbound-feeds-desktop`. The
script writes one Google `authorized_user` JSON per source and checks that one
Gmail list page returns 200. It does not Pull, Filter, or Store mail. That
work is `os-intake-build`.

Vault design: `Notes/Inbound Feeds Connectors.md` → Token files, OAuth setup
runbook, Design stubs.

## What it writes

| Source | Token file |
| --- | --- |
| ULC Gmail | `~/.config/personal-os-inbound-feeds/tokens/ulc_gmail.json` |

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

## Run

```bash
./.venv/bin/python oauth_loop.py --source ulc_gmail
```

A browser window opens. Sign in as ULC Gmail and Allow. Success prints the
token path and `Gmail list status: 200`.

```bash
./.venv/bin/python oauth_loop.py --source ulc_gmail --probe-only   # reuse token
./.venv/bin/python oauth_loop.py --source ulc_gmail --force        # re-consent
```

Testing-app refresh tokens expire on the order of seven days. Re-run `--force`
when Gmail starts returning auth errors.

## Spec & tests

Rule: run the tests before committing any change to this tool, and keep them
green. The tests are the executable spec. They do not call Google.

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
- Scope is the full `gmail.readonly` URI
- Token writes stay under `~/.config/personal-os-inbound-feeds/tokens/` and
  outside the repo and vault
- `authorized_user` JSON has `refresh_token`, `token_uri`, `client_id`,
  `client_secret`
- Desktop client JSON is accepted; Playground Web client JSON is rejected
- The Gmail list helper returns the HTTP status from a mocked session
