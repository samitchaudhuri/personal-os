# Milestone generator

Computes a site's milestone dates from one offsets file, so the Junction milestones table in `vault/Notes/ULC Franchise Project.md` stops drifting from the plan when the lease or opening date moves. The method and the reason for a single offsets file are in the vault note under "Plan for generating the milestone tables". Task: `ulc-milestone-generator`.

## Terms

A milestone is a dated event, such as lease signed. An input is a milestone whose date the site gives, and every input has a status. Committed means somebody fixed the date, estimated means a forecast, and assumed means a date we plan around until someone commits. An estimate is a duration someone forecasts, such as Fibr's 45 days from sourcing to an accepted offer. A requirement is a duration someone needs to hold, such as Michelle Tomko's three weeks between the GM and launch, or the Counter LOI's 60 days to submit permits. A not-before rule is an estimate or requirement with a start and no end, such as at least 10 days after permits. A collision is a set of rules that cannot all hold, so some milestone has no possible date.

## Files

`offsets.yaml` holds one row per milestone, the list of rules between milestones, and four phases. Each rule says the second milestone falls within a range of days of the first, and the range can be negative, such as the GM 21 days before presale launch. A milestone reached by several rules gets the intersection of all of them, and each rule narrows both ends, so the GM requirement narrows launch given the GM and the GM given launch. Keys are stable names that vault goals and targets link to.

A not-before rule is written with `null` as the upper limit, such as `[10, null]`. `construction-start` has two, delivery and permits plus 10 days. It starts as soon as the later one allows, so its latest date is the later of their latest dates. Rent commences works the same way, 150 days after the later of delivery and permits.

A site must give every milestone marked `input: true`, such as the kickoff call, the lease range, the GM sourcing date and landlord delivery, and must record a status for each in the site's `status` block. The generator computes every other milestone. A milestone marked `site_can_fix: true`, such as `permits-submitted`, `permits-received`, `vip-start` and `presale-launch`, takes a date from the site when the site gives one. That date replaces the estimates that compute the milestone, and requirements on it still apply. Junction assumes `landlord-delivery` is 2/8, the latest date permits can be approved, so that delivery never delays construction. A date the landlord commits to replaces it with a committed status. An earlier date changes nothing, and a later one moves the earliest build dates at once and the latest ones once it passes 2/18.

A phase is a rule that also has a table row: `permit-review`, `presale-setup`, `presale-vip-booking` and `presale-membership-sales`. The last one bounds `soft-open` from launch, so the build and the sales window must agree. The generator still flags any phase whose actual span falls outside its range, which today happens when a date from the site replaces the estimate.

When the rules cannot all hold, the generator flags the collision. It names the requirement and the estimates in the loop, walks the dates around the loop, and says how many days the estimates must improve in total for the requirement to be met. It sets one rule aside to draw the dates, a requirement if the collision has one, else the estimate listed last, so list the checks last. A not-before rule is never set aside. A third table under the phase table lists each rule set aside, its kind, the rules it collides with and the days short. Today the flag says the GM-in-seat requirement collides with Fibr's estimate by 4 days, because a 12/21 launch needs the GM in seat by 11/30 and the offer accepted by 11/16, and 45 days from sourcing gives 11/20.

`sites.yaml` holds each site's inputs, such as the lease signing target and the soft-open date, plus the contract limits the generator flags against. The contract dates are copied from the vault's Contract dates table and are not computed.

`milestones.py` solves the rules as a network of date ranges, finds collisions as negative cycles, and prints three tables. The Inputs table lists every date the site gave, its status and its basis, and it comes first because the schedule below it assumes those dates. The inputs show as given, so a lease range that the permits date narrows appears in full there and narrower in the milestone table. With `--write NOTE` it rewrites the block between `<!-- milestones:SITE:start -->` and `<!-- milestones:SITE:end -->` in that note and fails if the markers are missing.

`timeline_csv.py` exports the opening timeline workbook to a CSV for a Gantt tool, one row per task with its group, category, bar start and end, and proposed predecessors from `timeline-dependencies.yaml`. With `--site` it adds the milestone key and the generator's estimate beside the bar for each row that `offsets.yaml` maps. The bars are the template's sample timeline shifted to the workbook's anchor date in B2, so the estimate columns are the Junction dates and the start and end columns are not.

## Run

```bash
cd franchise/milestones && ./.venv/bin/python milestones.py junction
```

```bash
cd franchise/milestones && ./.venv/bin/python timeline_csv.py --site junction --out "../../gdrive/private/ULC-personal/Development/Opening Timeline/ULC Los Gatos Opening Timeline.csv"
```

For TeamGantt, add `--teamgantt` to write its work-breakdown layout, with WBS numbers as predecessors. Its free plan holds 40 tasks and the workbook has 41, so `--skip 13` drops the optional DBA row; the script warns when the count exceeds 40.

Flags go to stderr: a collision between rules, a phase whose actual span is outside its planned range, a lease date after the Site Acquisition Deadline, a soft open past the Opening Deadline with the extension fee, a GM date after the hard stop before the owner's absence, and any milestone wholly inside that absence.

## Tests

```bash
cd franchise/milestones && ./.venv/bin/python -m unittest discover -s tests
```

## Not built yet

Mark's and MMP's confirmation of the template's buildout durations. A second site and the combined table with sites as columns.
