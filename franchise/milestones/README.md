# Milestone generator

Computes a site's milestone dates from one offsets file, so the Junction milestones table in `vault/Notes/ULC Franchise Project.md` stops drifting from the plan when the lease or opening date moves. The method and the reason for a single offsets file are in the vault note under "Plan for generating the milestone tables". Task: `ulc-milestone-generator`.

## Files

`offsets.yaml` holds one row per milestone. A milestone is an input that a site supplies, or sits an offset range in days from another milestone. The forward chain runs from landlord delivery through buildout and inspection to soft open, and the backward chain runs from soft open to presale launch, the VIP phase and the GM. Keys are stable names that vault goals and targets link to.

`sites.yaml` holds each site's inputs, such as the lease signing target and the soft-open date, plus the contract limits the generator flags against. The contract dates are copied from the vault's Contract dates table and are not derived.

`milestones.py` resolves the chains as date ranges and prints the table. With `--write NOTE` it rewrites the block between `<!-- milestones:SITE:start -->` and `<!-- milestones:SITE:end -->` in that note and fails if the markers are missing.

## Run

```bash
cd franchise/milestones && ./.venv/bin/python milestones.py junction
```

Flags go to stderr: a lease date after the Site Acquisition Deadline, a soft open past the Opening Deadline with the extension fee, a GM date after the hard stop before the owner's absence, and any milestone wholly inside that absence.

## Tests

```bash
cd franchise/milestones && ./.venv/bin/python -m unittest discover -s tests
```

## Not built yet

A permit-received date and permit review time, and Mark's and MMP's confirmation of the template's buildout durations. The Gantt CSV for `ulc-timeline-csv`. A second site and the combined table with sites as columns. Markers in the vault note, so `--write` has not been run against it.
