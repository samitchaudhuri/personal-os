# franchise

This folder holds the build tools that support franchise work. Scripts, config, and tests live here in git so they can be versioned and reviewed. The business files those tools read and write, such as VisionTrack captures, comparison CSVs, underwriting docs, and generated plans, live in Google Drive and are reached from this repo through `gdrive/private/ULC-personal/`.

It sits next to `presentations/` as another domain tooling umbrella: franchise tools here, deck tooling there. One-off utilities stay in `scripts/`.

## Tools in this folder

`site-selection/` builds the site comparison workbook from VisionTrack inputs and hand-entered facts. The stable method is in the vault at `Agent/Workflows/Site Selection Scoring.md`.

`ulc-business-plan/` merges staging markdown into the lender business plan template. The runbook is in the vault at `Notes/ULC Business Plan Runbook.md`.

Each tool has its own README with setup, run commands, and the test rule for that tool.
