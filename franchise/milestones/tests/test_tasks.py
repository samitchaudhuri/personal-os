import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import tasks

D = dt.date
DATES = {"bid-complete": (D(2026, 12, 8), D(2026, 12, 22)), "vip-start": (D(2026, 10, 23), D(2026, 10, 26))}

NOTE = "\n".join([
    "- [ ] #task **Collect bids** — text [milestone:: bid-complete] #task/outreach 🆔 gc-bids ⏫ 📅 2026-11-06",
    "- [ ] #task **Start VIP** [milestone:: vip-start, earliest] #task/admin 🆔 vip 📅 2026-10-23",
    "- [ ] #task **Hand-dated** #task/admin 🆔 plain 📅 2026-01-01",
    "- [x] #task **Done** [milestone:: bid-complete] #task/admin 🆔 done 📅 2026-01-01 ✅ 2026-01-02",
    "\t- 2026-10-19: a note line [milestone:: bid-complete]",
])


class TestTasks(unittest.TestCase):
    def test_only_open_tagged_tasks_are_read(self):
        self.assertEqual([t[1] for t in tasks.tagged(NOTE)], ["gc-bids", "vip"])

    def test_the_default_end_is_the_latest(self):
        self.assertEqual(tasks.target(DATES, "bid-complete", tasks.DEFAULT_END), D(2026, 12, 22))
        self.assertEqual(tasks.target(DATES, "bid-complete", "earliest"), D(2026, 12, 8))

    def test_lists_a_task_off_its_date_and_skips_one_on_it(self):
        found = tasks.drifts(NOTE, DATES)
        self.assertEqual([(d.task, d.target) for d in found], [("gc-bids", "2026-12-22")])
        self.assertIn("due 2026-11-06", tasks.describe(found[0]))

    def test_sync_rewrites_only_the_drifted_due_date(self):
        out = tasks.sync(NOTE, DATES)
        self.assertIn("🆔 gc-bids ⏫ 📅 2026-12-22", out)
        self.assertEqual(out.replace("2026-12-22", "2026-11-06"), NOTE)
        self.assertEqual(tasks.drifts(out, DATES), [])

    def test_sync_adds_a_due_date_when_a_task_has_none(self):
        note = "- [ ] #task **A** [milestone:: vip-start] #task/admin 🆔 a"
        self.assertEqual(tasks.sync(note, DATES), note + " 📅 2026-10-26")

    def test_sync_note_moves_the_dates_in_the_sites_tasks_note(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tasks.md"
            path.write_text(NOTE, encoding="utf-8")
            with mock.patch.object(tasks.ramp, "outputs", return_value={"tasks": path}):
                self.assertEqual(tasks.sync_note("junction", DATES), 1)
                self.assertEqual(tasks.sync_note("junction", DATES), 0)
            self.assertIn("📅 2026-12-22", path.read_text(encoding="utf-8"))

    def test_sync_note_does_nothing_without_an_outputs_tasks_path(self):
        with mock.patch.object(tasks.ramp, "outputs", return_value={}):
            self.assertEqual(tasks.sync_note("junction", DATES), 0)

    def test_an_unknown_key_fails(self):
        with self.assertRaises(ValueError):
            tasks.drifts("- [ ] #task **A** [milestone:: nope] 🆔 a 📅 2026-01-01", DATES)


SITES = """sites:
  owner: x
  junction:
    title: Junction
    inputs:
      presale-kickoff: 2026-10-09      # scheduled by Elise
      bid-complete: 2026-12-22 # Vision Track
    status:
      presale-kickoff: committed
      bid-complete: committed
    outputs:
      tasks: x
"""
DURATIONS = {"milestones": [{"key": "presale-kickoff", "input": True}, {"key": "bid-complete", "input": True},
                            {"key": "vip-start", "site_can_fix": True}, {"key": "permits-received"}]}
DONE = NOTE + "\n- [x] #task **Kit** [milestone:: vip-start] #task/admin 🆔 kit 📅 2026-10-26 ✅ 2026-10-21"


class TestActuals(unittest.TestCase):
    def test_reads_only_checked_tagged_tasks_with_a_stamp(self):
        self.assertEqual(tasks.completed(DONE), [("done", "bid-complete", D(2026, 1, 2)), ("kit", "vip-start", D(2026, 10, 21))])

    def test_only_inputs_and_site_fixable_milestones_are_settable(self):
        self.assertEqual(tasks.settable(DURATIONS), {"presale-kickoff", "bid-complete", "vip-start"})

    def test_a_finished_task_replaces_an_input_and_keeps_the_other_lines(self):
        out, changes = tasks.apply_actuals(SITES, "junction", DURATIONS, [("bids", "bid-complete", D(2026, 12, 10))])
        self.assertIn("      bid-complete: 2026-12-10  # finished, task bids", out)
        self.assertIn("      presale-kickoff: 2026-10-09      # scheduled by Elise", out)
        self.assertEqual(len(changes), 1)
        self.assertEqual(yaml.safe_load(out)["sites"]["junction"]["status"]["bid-complete"], "committed")

    def test_a_site_fixable_milestone_not_yet_given_is_added_to_inputs_and_status(self):
        out, _ = tasks.apply_actuals(SITES, "junction", DURATIONS, [("kit", "vip-start", D(2026, 10, 21))])
        conf = yaml.safe_load(out)["sites"]["junction"]
        self.assertEqual(conf["inputs"]["vip-start"], D(2026, 10, 21))
        self.assertEqual(conf["status"]["vip-start"], "committed")
        self.assertEqual(conf["outputs"], {"tasks": "x"})

    def test_a_computed_milestone_and_an_unchanged_date_change_nothing(self):
        out, changes = tasks.apply_actuals(SITES, "junction", DURATIONS,
                                           [("p", "permits-received", D(2027, 1, 1)), ("b", "bid-complete", D(2026, 12, 22))])
        self.assertEqual((out, changes), (SITES, []))


if __name__ == "__main__":
    unittest.main()
