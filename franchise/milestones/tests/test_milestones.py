"""Hermetic tests for the milestone generator (milestones.py).

Golden values are the Junction inputs in sites.yaml. Nothing here touches the
vault, Google Drive or Excel; the rewrite test works on a temp file.
"""
import datetime
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import milestones as ms  # noqa: E402

D = datetime.date
DURATIONS = ms.load_yaml("durations.yaml")
SITES = ms.load_yaml("sites.yaml")
# The rule tests read the derived chain, so they leave out the VIP start date the site holds while the launch date is open.
JUNCTION = dict(SITES["sites"]["junction"], inputs={k: v for k, v in SITES["sites"]["junction"]["inputs"].items() if k != "vip-start"})
AWAY = SITES["owner"]["away"]


def junction():
    return ms.resolve(DURATIONS, JUNCTION["inputs"])


def synthetic(constraints, events, **fixed):
    """Offsets with the named events; `fixed` marks which are inputs."""
    return {"milestones": [dict(key=e, label=e, basis="", **({"input": True} if e in fixed else {}))
                           for e in events],
            "constraints": constraints}


def c(frm, to, lo, hi, kind="estimate"):
    """A rule; hi None writes the duration as [lo,] with no maximum, and lo None as [,hi] with no minimum."""
    return {"from": frm, "to": to, "duration_days": [lo] if hi is None else [lo, hi], "kind": kind}


class TestNotBeforeStart(unittest.TestCase):
    def solve(self, *extra):
        d = synthetic([c("s", "a", 0, 5), c("a", "b", 14, None, "requirement"), *extra], ["s", "a", "b"], s=1)
        return ms.solve(d, {"s": D(2026, 1, 1)})

    def test_a_not_before_rule_starts_its_target_as_soon_as_it_allows(self):
        self.assertEqual(self.solve().ranges["b"], (D(2026, 1, 15), D(2026, 1, 20)))

    def test_another_rule_with_a_latest_date_stops_the_start(self):
        s = self.solve(c("s", "b", 30, 40))
        self.assertEqual(s.ranges["b"], (D(2026, 1, 31), D(2026, 2, 10)))
        self.assertEqual(s.conflicts, [])

    def test_an_open_minimum_bounds_the_latest_date_and_stops_the_start(self):
        # b is at least 14 days before g, so it ends 14 days before g's latest date, and it never starts at once.
        s = ms.solve(synthetic([c("s", "b", 0, None), c("g", "b", None, -14), c("s", "g", 30, 40)],
                               ["s", "g", "b"], s=1), {"s": D(2026, 1, 1)})
        self.assertEqual(s.ranges["b"], (D(2026, 1, 1), D(2026, 1, 27)))
        self.assertEqual(s.ranges["g"], (D(2026, 1, 31), D(2026, 2, 10)))


class TestResolve(unittest.TestCase):
    def test_inputs_pass_through(self):
        r = junction()
        self.assertEqual(r["lease-signed"], (D(2026, 11, 30), D(2026, 12, 15)))
        self.assertEqual(r["presale-kickoff"], (D(2026, 10, 9), D(2026, 10, 9)))

    def test_sourcing_is_a_site_input(self):
        self.assertEqual(junction()["gm-sourcing"], (D(2026, 10, 6), D(2026, 10, 6)))

    def test_offer_accepted_is_45_days_after_sourcing(self):
        self.assertEqual(junction()["gm-offer-accepted"], (D(2026, 11, 20), D(2026, 11, 20)))

    def test_gm_in_seat_is_two_to_four_weeks_after_the_offer(self):
        self.assertEqual(junction()["gm-in-seat"], (D(2026, 12, 4), D(2026, 12, 18)))

    def test_forward_chain_uses_template_durations(self):
        r = junction()
        rg = lambda a, b: (D(*a), D(*b))
        self.assertEqual(r["construction-start"], rg((2027, 2, 8), (2027, 2, 18)))
        self.assertEqual(r["lighting-flooring-delivered"], rg((2027, 3, 22), (2027, 4, 1)))
        self.assertEqual(r["equipment-installed"], rg((2027, 5, 10), (2027, 5, 20)))
        self.assertEqual(r["av-ordered"], rg((2027, 2, 15), (2027, 2, 25)))
        self.assertEqual(r["equipment-ordered"], rg((2027, 3, 11), (2027, 4, 19)))
        self.assertEqual(r["build-complete"], rg((2027, 5, 3), (2027, 5, 27)))
        self.assertEqual(r["soft-open"], rg((2027, 5, 10), (2027, 6, 3)))

    def test_equipment_is_ordered_and_paid_45_to_60_days_before_soft_open(self):
        r = junction()
        soft_lo, soft_hi = r["soft-open"]
        ord_lo, ord_hi = r["equipment-ordered"]
        self.assertEqual((soft_lo - ord_lo).days, 60)
        self.assertEqual((soft_hi - ord_hi).days, 45)
        self.assertNotIn("equipment-paid", r)

    def test_av_is_ordered_84_days_before_install_whatever_the_payment_date(self):
        r = junction()
        self.assertEqual((r["equipment-installed"][0] - r["av-ordered"][0]).days, 84)
        self.assertLess(r["av-ordered"][1], r["equipment-ordered"][0])

    def test_av_lead_time_and_equipment_timing_are_estimates(self):
        rules = {(x.frm, x.to): x for x in ms.constraints_of(DURATIONS)}
        self.assertEqual(rules[("equipment-installed", "av-ordered")].kind, "estimate")
        self.assertEqual(rules[("soft-open", "equipment-ordered")].kind, "estimate")

    def test_new_equipment_milestones_add_no_flags_or_collisions(self):
        sol = ms.solve(DURATIONS, JUNCTION["inputs"])
        self.assertEqual([k.set_aside.name for k in sol.conflicts], ["presale-launch to gm-in-seat"])

    def test_permit_review_follows_submission(self):
        r = junction()
        self.assertEqual(r["permits-submitted"], (D(2026, 12, 14), D(2026, 12, 14)))
        self.assertEqual(r["permits-received"], (D(2027, 1, 29), D(2027, 2, 8)))

    def test_delivery_is_the_planning_assumption(self):
        self.assertEqual(junction()["landlord-delivery"], (D(2027, 2, 8), D(2027, 2, 8)))

    def test_delivery_is_an_input_every_site_must_give(self):
        inputs = {k: v for k, v in JUNCTION["inputs"].items() if k != "landlord-delivery"}
        with self.assertRaises(ValueError):
            ms.resolve(DURATIONS, inputs)

    def test_earlier_delivery_changes_nothing_and_later_delivery_moves_the_build(self):
        early = ms.resolve(DURATIONS, dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 1, 15)}))
        self.assertEqual(early["construction-start"], junction()["construction-start"])
        self.assertEqual(early["soft-open"], junction()["soft-open"])
        late = ms.resolve(DURATIONS, dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 2, 12)}))
        self.assertEqual(late["construction-start"], (D(2027, 2, 12), D(2027, 2, 18)))

    def test_construction_waits_for_the_later_of_delivery_and_permits(self):
        late = dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 3, 1)})
        self.assertEqual(ms.resolve(DURATIONS, late)["construction-start"], (D(2027, 3, 1), D(2027, 3, 1)))
        self.assertEqual(junction()["construction-start"][0], D(2027, 2, 8))

    def test_template_gaps_from_construction_start(self):
        # Template: construction 11/18, lighting 12/30, install 2/17. Jason Park: CO 12 to 14 weeks in, open a week later.
        start = D(2026, 11, 18)
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": start,
                                             "permits-received": D(2026, 10, 1)})
        r = ms.resolve(DURATIONS, inputs)
        self.assertEqual(r["lighting-flooring-delivered"][0], D(2026, 12, 30))
        self.assertEqual(r["equipment-installed"][0], D(2027, 2, 17))
        self.assertEqual(r["build-complete"][0], D(2027, 2, 10))
        self.assertEqual(r["soft-open"][0], D(2027, 2, 17))

    def test_rent_starts_150_days_after_the_later_not_before_rule(self):
        # Delivery 2/8 plus 150 days is 7/8, later than the earliest permits plus 150 days, 6/28.
        self.assertEqual(junction()["rent-commences"], (D(2027, 7, 8), D(2027, 7, 8)))

    def test_permits_submitted_within_60_days_of_lease(self):
        inputs = {k: v for k, v in JUNCTION["inputs"].items() if k != "permits-submitted"}
        # 60 days after the latest lease is 2/13, and no rule points back at the submission to pull it earlier.
        self.assertEqual(ms.resolve(DURATIONS, inputs)["permits-submitted"], (D(2026, 11, 30), D(2027, 2, 13)))

    def test_site_fixed_submission_leaves_the_lease_range_alone(self):
        # The rule runs from the lease to the submission, so a submission fixed on 12/14 does not narrow the lease.
        self.assertEqual(junction()["lease-signed"], (D(2026, 11, 30), D(2026, 12, 15)))

    def test_forward_chain_from_presale_kickoff(self):
        r = junction()
        self.assertEqual(r["vip-start"], (D(2026, 10, 23), D(2026, 10, 26)))
        self.assertEqual(r["presale-launch"], (D(2026, 12, 4), D(2026, 12, 21)))
        self.assertEqual(r["grand-opening"], (D(2027, 6, 21), D(2027, 7, 29)))

    def test_presale_prerequisites_fall_between_kickoff_and_vip_start(self):
        r = junction()
        for key in ("digital-partner-selected", "membership-agreement-finalized"):
            self.assertEqual(r[key], (D(2026, 10, 9), D(2026, 10, 26)), key)

    def test_the_kit_order_runs_from_kickoff_to_the_latest_the_gm_and_launch_checks_allow(self):
        self.assertEqual(junction()["presale-kit-ordered"], (D(2026, 10, 9), D(2026, 12, 4)))

    def test_a_prerequisite_the_site_dates_after_vip_start_collides(self):
        for key in ("digital-partner-selected", "membership-agreement-finalized"):
            inputs = dict(JUNCTION["inputs"], **{key: D(2026, 10, 30)})
            s = ms.solve(DURATIONS, inputs)
            self.assertIn("requirement", [k.set_aside.kind for k in s.conflicts], key)

    def test_a_kit_order_after_vip_start_is_fine_but_inside_14_days_of_launch_collides(self):
        key = "presale-kit-ordered"
        late = ms.solve(DURATIONS, dict(JUNCTION["inputs"], **{key: D(2026, 10, 30)}))
        self.assertEqual([k for k in late.conflicts if not k.soft], [])
        too_late = ms.solve(DURATIONS, dict(JUNCTION["inputs"], **{key: D(2026, 12, 10)}))
        self.assertIn("requirement", [k.set_aside.kind for k in too_late.conflicts])

    def test_a_prerequisite_the_site_dates_inside_the_window_leaves_vip_start_alone(self):
        inputs = dict(JUNCTION["inputs"], **{"membership-agreement-finalized": D(2026, 10, 24)})
        s = ms.solve(DURATIONS, inputs)
        self.assertEqual([k for k in s.conflicts if not k.soft], [])
        self.assertEqual(s.ranges["vip-start"], (D(2026, 10, 23), D(2026, 10, 26)))
        self.assertEqual(s.ranges["membership-agreement-finalized"], (D(2026, 10, 24), D(2026, 10, 24)))

    def test_kickoff_slip_moves_vip_and_launch_and_the_gm_target_follows_launch(self):
        # Kickoff 10/14 gives VIP 10/28 to 10/31 and launch 12/09 to 12/26 from the durations alone.
        # The GM preference runs from launch to the GM, so it leaves both ranges alone and dates the GM back from launch.
        inputs = dict(JUNCTION["inputs"], **{"presale-kickoff": D(2026, 10, 14)})
        s = ms.solve(DURATIONS, inputs)
        self.assertEqual(s.ranges["vip-start"], (D(2026, 10, 28), D(2026, 10, 31)))
        self.assertEqual(s.ranges["presale-launch"], (D(2026, 12, 9), D(2026, 12, 26)))
        self.assertEqual(s.conflicts, [])

    def test_site_fixed_date_replaces_the_estimates(self):
        inputs = dict(JUNCTION["inputs"], **{"presale-launch": D(2026, 12, 14)})
        r = ms.resolve(DURATIONS, inputs)
        self.assertEqual(r["presale-launch"], (D(2026, 12, 14), D(2026, 12, 14)))

    def test_input_for_a_computed_row_is_ignored(self):
        inputs = dict(JUNCTION["inputs"], **{"soft-open": D(2027, 1, 1)})
        self.assertEqual(ms.resolve(DURATIONS, inputs)["soft-open"], junction()["soft-open"])

    def test_delivery_slip_moves_soft_open(self):
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 5, 1)})
        self.assertEqual(ms.resolve(DURATIONS, inputs)["soft-open"][0], D(2027, 7, 31))

    def test_slipping_sourcing_moves_the_gm(self):
        inputs = dict(JUNCTION["inputs"], **{"gm-sourcing": D(2026, 10, 12)})
        self.assertEqual(ms.resolve(DURATIONS, inputs)["gm-in-seat"][0], D(2026, 12, 10))

    def test_missing_input_is_an_error(self):
        inputs = {k: v for k, v in JUNCTION["inputs"].items() if k != "presale-kickoff"}
        with self.assertRaises(ValueError):
            ms.resolve(DURATIONS, inputs)

    def test_unbounded_event_is_an_error(self):
        lone = synthetic([c("a", "b", 1, 2)], ["a", "b", "orphan"], a=1)
        with self.assertRaises(ValueError):
            ms.resolve(lone, {"a": D(2026, 1, 1)})

    def test_unknown_kind_is_an_error(self):
        bad = synthetic([c("a", "b", 1, 2, kind="hope")], ["a", "b"], a=1)
        with self.assertRaises(ValueError):
            ms.resolve(bad, {"a": D(2026, 1, 1)})


class TestConstraintModel(unittest.TestCase):
    def test_range_is_the_intersection_of_every_constraint(self):
        # b is 1/11 to 1/21 from a and 1/15 to 1/22 from z, so both fit only from 1/15 to 1/21.
        off = synthetic([c("a", "b", 10, 20), c("z", "b", 5, 8)], ["a", "z", "b"], a=1, z=1)
        r = ms.resolve(off, {"a": D(2026, 1, 1), "z": [D(2026, 1, 10), D(2026, 1, 14)]})
        self.assertEqual(r["b"], (D(2026, 1, 15), D(2026, 1, 21)))

    def test_a_rule_narrows_its_target_and_never_its_source(self):
        # b is fixed 1/20 to 1/25 and sits 10 to 15 days after a, which still allows every date a was given.
        off = synthetic([c("a", "b", 10, 15)], ["a", "b"], a=1, b=1)
        r = ms.resolve(off, {"a": [D(2026, 1, 1), D(2026, 1, 31)], "b": [D(2026, 1, 20), D(2026, 1, 25)]})
        self.assertEqual(r["a"], (D(2026, 1, 1), D(2026, 1, 31)))
        self.assertEqual(r["b"], (D(2026, 1, 20), D(2026, 1, 25)))

    def test_negative_range_puts_the_event_before(self):
        off = synthetic([c("launch", "gm", -21, -21)], ["launch", "gm"], launch=1)
        r = ms.resolve(off, {"launch": D(2026, 12, 21)})
        self.assertEqual(r["gm"], (D(2026, 11, 30), D(2026, 11, 30)))

    def test_a_requirement_dates_launch_from_the_gm_and_leaves_the_gm_alone(self):
        off = synthetic([c("gm", "launch", 21, 21, "requirement")], ["gm", "launch"], gm=1, launch=1)
        r = ms.resolve(off, {"gm": [D(2026, 12, 4), D(2026, 12, 18)], "launch": [D(2026, 12, 1), D(2027, 1, 31)]})
        self.assertEqual(r["launch"], (D(2026, 12, 25), D(2027, 1, 8)))
        self.assertEqual(r["gm"], (D(2026, 12, 4), D(2026, 12, 18)))

    def test_not_before_takes_the_latest_lower_bound_and_starts_as_soon_as_allowed(self):
        off = synthetic([c("a", "x", 0, None), c("b", "x", 10, None)], ["a", "b", "x"], a=1, b=1)
        r = ms.resolve(off, {"a": [D(2026, 3, 1), D(2026, 3, 5)], "b": [D(2026, 2, 20), D(2026, 3, 1)]})
        self.assertEqual(r["x"], (D(2026, 3, 2), D(2026, 3, 11)))

    def test_not_before_alone_leaves_no_upper_limit_so_a_later_bound_conflicts(self):
        off = synthetic([c("a", "x", 0, None), c("x", "y", 5, 5), c("z", "y", 0, 0)],
                        ["a", "x", "y", "z"], a=1, z=1)
        s = ms.solve(off, {"a": D(2026, 3, 1), "z": D(2026, 3, 1)})
        self.assertEqual(len(s.conflicts), 1)

    def test_junction_gm_preference_misses_its_ideal_because_of_the_fibr_estimate(self):
        s = ms.solve(DURATIONS, JUNCTION["inputs"])
        self.assertEqual(len(s.conflicts), 1)
        k = s.conflicts[0]
        self.assertEqual(k.short, 4)
        self.assertEqual(k.set_aside.name, "presale-launch to gm-in-seat")
        names = {x.name for x in k.constraints}
        self.assertIn("presale-launch to gm-in-seat", names)
        self.assertIn("gm-sourcing to gm-offer-accepted", names)
        self.assertTrue(k.soft)
        self.assertIn("Ideal missed by 4 days: the preference presale-launch to gm-in-seat", k.message)
        self.assertIn("improved by 4 days in total", k.message)
        for date in ("2026-11-30", "2026-11-20", "2026-12-04", "2026-12-21"):
            self.assertIn(date, k.message)

    def test_conflict_shows_the_estimates_without_the_requirement(self):
        s = ms.solve(DURATIONS, JUNCTION["inputs"])
        self.assertEqual(s.ranges["presale-launch"], (D(2026, 12, 4), D(2026, 12, 21)))
        self.assertEqual(s.ranges["gm-in-seat"], (D(2026, 12, 4), D(2026, 12, 18)))

    def test_a_preference_gives_before_an_estimate_and_a_requirement_is_not_soft(self):
        off = synthetic([c("a", "b", 10, 10), c("a", "b", 20, 20, "preference")], ["a", "b"], a=1)
        s = ms.solve(off, {"a": D(2026, 1, 1)})
        self.assertEqual([(k.set_aside.kind, k.soft) for k in s.conflicts], [("preference", True)])
        hard = synthetic([c("a", "b", 10, 10), c("a", "b", 20, 20, "requirement")], ["a", "b"], a=1)
        self.assertFalse(ms.solve(hard, {"a": D(2026, 1, 1)}).conflicts[0].soft)

    def test_a_preference_that_holds_dates_like_a_requirement_and_raises_no_warning(self):
        off = synthetic([c("gm", "launch", 21, 21, "preference")], ["gm", "launch"], gm=1)
        s = ms.solve(off, {"gm": D(2026, 1, 1)})
        self.assertEqual(s.conflicts, [])
        self.assertEqual(s.ranges["launch"], (D(2026, 1, 22), D(2026, 1, 22)))

    def test_a_negative_preference_dates_its_target_back_from_its_source_and_never_moves_the_source(self):
        # b is 10 to 20 days after a, and the GM-style preference wants c 3 days before b.
        off = synthetic([c("a", "b", 10, 20), c("a", "c", 0, 60), c("b", "c", -3, -3, "preference")],
                        ["a", "b", "c"], a=1)
        s = ms.solve(off, {"a": D(2026, 1, 1)})
        self.assertEqual(s.conflicts, [])
        self.assertEqual(s.ranges["b"], (D(2026, 1, 11), D(2026, 1, 21)))
        self.assertEqual(s.ranges["c"], (D(2026, 1, 8), D(2026, 1, 18)))

    def test_a_late_target_cannot_push_the_source_later(self):
        # c cannot be before 1/20, but the preference wants it 3 days before b, which is no later than 1/21, so the
        # preference is the rule that gives and b keeps its dates.
        off = synthetic([c("a", "b", 10, 20), c("a", "c", 19, 40), c("b", "c", -3, -3, "preference")],
                        ["a", "b", "c"], a=1)
        s = ms.solve(off, {"a": D(2026, 1, 1)})
        self.assertEqual(s.ranges["b"], (D(2026, 1, 11), D(2026, 1, 21)))
        self.assertEqual(s.ranges["c"][0], D(2026, 1, 20))
        self.assertEqual([(k.set_aside.name, k.soft) for k in s.conflicts], [("b to c", True)])

    def test_a_duration_with_no_maximum_is_written_with_a_trailing_comma(self):
        rule = ms.constraints_of(synthetic([c("a", "b", 14, None)], ["a", "b"]))[0]
        self.assertEqual((rule.lo, rule.hi, rule.pins), (14, None, True))

    def test_a_duration_with_null_is_an_error(self):
        bad = synthetic([dict(c("a", "b", 14, 20), duration_days=[14, None])], ["a", "b"])
        with self.assertRaises(ValueError):
            ms.constraints_of(bad)

    def test_a_duration_with_no_minimum_is_written_with_a_leading_comma(self):
        loaded = ms.parse_yaml("constraints:\n  - {from: g, to: k, duration_days: [,-14], kind: requirement}\n")
        self.assertEqual(loaded["constraints"][0]["duration_days"], [None, -14])
        rule = ms.constraints_of(synthetic(loaded["constraints"], ["g", "k"]))[0]
        self.assertEqual((rule.lo, rule.hi, rule.pins), (None, -14, False))

    def test_a_duration_with_no_limits_is_an_error(self):
        bad = synthetic([dict(c("a", "b", 1, 2), duration_days=[None])], ["a", "b"])
        with self.assertRaises(ValueError):
            ms.constraints_of(bad)

    def test_requirement_met_means_no_conflict(self):
        inputs = dict(JUNCTION["inputs"], **{"gm-sourcing": D(2026, 10, 2)})
        self.assertEqual(ms.solve(DURATIONS, inputs).conflicts, [])

    def test_two_estimates_collide_and_the_one_listed_last_gives(self):
        off = synthetic([c("a", "b", 10, 10), c("a", "b", 20, 20)], ["a", "b"], a=1)
        s = ms.solve(off, {"a": D(2026, 1, 1)})
        self.assertEqual(len(s.conflicts), 1)
        self.assertIn("The estimates a to b and a to b cannot all hold and are 10 days apart", s.conflicts[0].message)
        self.assertEqual(s.ranges["b"], (D(2026, 1, 11), D(2026, 1, 11)))

    def test_loop_without_dates_names_the_constraints(self):
        off = synthetic([c("a", "b", 5, 5, "requirement"), c("b", "a", 0, 0), c("a", "b", 0, 100)], ["a", "b"])
        off["milestones"][0]["input"] = True
        s = ms.solve(off, {"a": D(2026, 1, 1)})
        self.assertEqual(len(s.conflicts), 1)

    def test_delivery_slip_collides_with_the_sales_window(self):
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 5, 1)})
        s = ms.solve(DURATIONS, inputs)
        self.assertIn("presale-membership-sales", [k.set_aside.name for k in s.conflicts])
        self.assertEqual(s.ranges["presale-launch"], junction()["presale-launch"])
        self.assertIn("presale-membership-sales", s.set_aside_phases)


class TestBasisText(unittest.TestCase):
    def test_a_basis_names_a_phase_and_never_copies_its_length(self):
        # The length lives in the phase's duration_days, so a copy in a basis would drift when it changes.
        copies = [m["key"] for m in DURATIONS["milestones"] if re.search(r"phase of \d", m["basis"])]
        self.assertEqual(copies, [])


class TestMonthsOver(unittest.TestCase):
    def test_part_of_a_month_counts_as_a_month(self):
        self.assertEqual(ms.months_over(D(2027, 5, 12), D(2027, 7, 15)), 3)

    def test_exact_months(self):
        self.assertEqual(ms.months_over(D(2027, 5, 12), D(2027, 7, 12)), 2)

    def test_end_of_month_clamps(self):
        self.assertEqual(ms.months_over(D(2027, 1, 31), D(2027, 2, 28)), 1)


class TestFlags(unittest.TestCase):
    def messages(self, resolved):
        return dict(ms.flags(resolved, JUNCTION["limits"], AWAY))

    def test_junction_flags_extension_and_opening_fee(self):
        m = self.messages(junction())
        self.assertIn("one-time 90-day extension", m["lease-signed"])
        self.assertIn("1 months past", m["soft-open"])
        self.assertIn("$2,500", m["soft-open"])
        self.assertIn("hard stop", m["gm-in-seat"])

    def test_lease_before_deadline_is_clean(self):
        r = dict(junction(), **{"lease-signed": (D(2026, 11, 2), D(2026, 11, 2))})
        self.assertNotIn("lease-signed", self.messages(r))

    def test_lease_past_extended_deadline(self):
        r = dict(junction(), **{"lease-signed": (D(2027, 3, 1), D(2027, 3, 1))})
        self.assertIn("extended", self.messages(r)["lease-signed"])

    def test_gm_after_hard_stop(self):
        r = dict(junction(), **{"gm-in-seat": (D(2027, 1, 15), D(2027, 1, 15))})
        self.assertIn("hard stop", self.messages(r)["gm-in-seat"])

    def test_absence_flag_needs_whole_range_inside(self):
        r = dict(junction(), **{"gm-in-seat": (D(2026, 12, 20), D(2026, 12, 22))})
        self.assertIn("absence", self.messages(r)["gm-in-seat"])


class TestConflictFlags(unittest.TestCase):
    def test_flag_names_both_constraints_and_the_days(self):
        s = ms.solve(DURATIONS, JUNCTION["inputs"])
        key, msg = s.conflicts[0].key, s.conflicts[0].message
        self.assertEqual(key, "gm-in-seat")
        self.assertIn("presale-launch to gm-in-seat", msg)
        self.assertIn("gm-sourcing to gm-offer-accepted", msg)
        self.assertIn("4 days", msg)


class TestInputRows(unittest.TestCase):
    def rows(self, site=JUNCTION):
        return ms.input_rows(DURATIONS, site)

    def test_lists_every_date_the_site_gives_with_its_status(self):
        rows = self.rows()
        self.assertEqual(len(rows), len(JUNCTION["inputs"]))
        by_key = {r[0]: r for r in rows}
        self.assertEqual(by_key["landlord-delivery"][2:4], ((D(2027, 2, 8), D(2027, 2, 8)), "assumed"))
        self.assertEqual(by_key["presale-kickoff"][3], "committed")
        self.assertEqual(by_key["lease-signed"][2:4], ((D(2026, 11, 30), D(2026, 12, 15)), "estimated"))

    def test_rows_follow_milestone_order(self):
        keys = [r[0] for r in self.rows()]
        order = [m["key"] for m in DURATIONS["milestones"]]
        self.assertEqual(keys, sorted(keys, key=order.index))

    def test_site_basis_replaces_the_default(self):
        by_key = {r[0]: r for r in self.rows()}
        self.assertIn("planning assumption", by_key["landlord-delivery"][4])

    def test_a_date_without_a_status_is_an_error(self):
        site = dict(JUNCTION, status={k: v for k, v in JUNCTION["status"].items() if k != "landlord-delivery"})
        with self.assertRaises(ValueError):
            ms.input_rows(DURATIONS, site)

    def test_unknown_status_is_an_error(self):
        site = dict(JUNCTION, status=dict(JUNCTION["status"], **{"lease-signed": "hoped"}))
        with self.assertRaises(ValueError):
            ms.input_rows(DURATIONS, site)


class TestSetAsideRows(unittest.TestCase):
    def test_lists_the_preference_set_aside_and_what_it_collides_with(self):
        rule, kind, others, short = ms.set_aside_rows(ms.solve(DURATIONS, JUNCTION["inputs"]).conflicts)[0]
        self.assertEqual((rule, kind, short), ("presale-launch to gm-in-seat", "preference", 4))
        self.assertIn("gm-sourcing to gm-offer-accepted", others)
        self.assertNotIn("presale-launch to gm-in-seat", others)

    def test_rows_follow_the_order_ignored(self):
        inputs = dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 5, 1)})
        rows = ms.set_aside_rows(ms.solve(DURATIONS, inputs).conflicts)
        self.assertEqual(len(rows), 2)
        self.assertIn("presale-membership-sales", rows[0][0])


class TestPhaseFlags(unittest.TestCase):
    def messages(self, inputs=None):
        s = ms.solve(DURATIONS, dict(JUNCTION["inputs"], **(inputs or {})))
        return dict(ms.phase_flags(DURATIONS, s.ranges, s.set_aside_phases)), s.ranges

    def test_junction_sales_window_is_inside_four_to_six_months(self):
        m, _ = self.messages()
        self.assertNotIn("soft-open", m)

    def test_soft_open_too_long_after_launch_is_a_conflict_not_a_phase_flag(self):
        s = ms.solve(DURATIONS, dict(JUNCTION["inputs"], **{"landlord-delivery": D(2027, 6, 1)}))
        messages = [k.message for k in s.conflicts if k.set_aside.phase == "presale-membership-sales"]
        self.assertEqual(len(messages), 1)
        self.assertIn("improve by 73 days in total", messages[0])
        self.assertIn("landlord-delivery to construction-start", messages[0])
        self.assertNotIn("soft-open", dict(ms.phase_flags(DURATIONS, s.ranges, s.set_aside_phases)))

    def test_derived_phases_are_clean(self):
        m, _ = self.messages()
        self.assertNotIn("vip-start", m)
        self.assertNotIn("presale-launch", m)

    def test_soft_open_inside_the_bound_is_clean(self):
        # Early permits and delivery 12/14 give soft open 4/16 to 4/26, inside 90 to 150 days.
        m, _ = self.messages({"permits-submitted": D(2026, 10, 30), "landlord-delivery": D(2026, 12, 14)})
        self.assertNotIn("soft-open", m)

    def test_soft_open_too_soon_after_launch_is_a_conflict(self):
        s = ms.solve(DURATIONS, dict(JUNCTION["inputs"], **{"presale-launch": D(2027, 6, 1)}))
        self.assertIn("presale-membership-sales", [k.set_aside.name for k in s.conflicts])

    def test_site_fixed_launch_outside_the_range_is_flagged(self):
        m, _ = self.messages({"presale-launch": D(2027, 1, 20)})
        self.assertIn("presale-vip-booking", m["presale-launch"])
        self.assertIn("over its planned", m["presale-launch"])

    def test_phase_rows_list_every_phase(self):
        _, r = self.messages()
        rows = ms.phase_rows(DURATIONS, r)
        self.assertEqual([p[0] for p in rows], [p["key"] for p in DURATIONS["phases"]])
        self.assertEqual(dict((p[0], p[4]) for p in rows)["presale-membership-sales"], (157, 164))


class TestRender(unittest.TestCase):
    def test_table_keeps_keys_and_order(self):
        table = ms.render_table(DURATIONS, junction(), JUNCTION)
        keys = [line.split("`")[1] for line in table.splitlines()[2:]]
        self.assertEqual(keys, [m["key"] for m in DURATIONS["milestones"]])

    def test_site_basis_overrides_default(self):
        table = ms.render_table(DURATIONS, junction(), JUNCTION)
        self.assertIn("45 to 60 days", table)

    def test_status_column_marks_inputs_and_computed_dates(self):
        rows = {r[0]: r for r in ms.milestone_rows(DURATIONS, junction(), JUNCTION)}
        self.assertEqual(rows["presale-kickoff"][3], "committed")
        self.assertEqual(rows["soft-open"][3], "computed")

    def test_a_narrowed_input_also_shows_the_range_the_site_gave(self):
        narrowed = dict(junction(), **{"lease-signed": (D(2026, 11, 30), D(2026, 12, 14))})
        rows = {r[0]: r for r in ms.milestone_rows(DURATIONS, narrowed, JUNCTION)}
        self.assertEqual(rows["lease-signed"][3], "estimated, given 2026-11-30 to 2026-12-15")

    def test_point_and_range_formats(self):
        self.assertEqual(ms.fmt((D(2026, 11, 30), D(2026, 11, 30))), "2026-11-30")
        self.assertEqual(ms.fmt((D(2026, 10, 8), D(2026, 10, 15))), "2026-10-08 to 2026-10-15")


class TestSections(unittest.TestCase):
    def test_flags_follow_the_milestone_table_when_something_is_off(self):
        text = ms.render_sections(DURATIONS, JUNCTION, ms.solve(DURATIONS, JUNCTION["inputs"]))
        heads = [l for l in text.splitlines() if l.startswith("#### ")]
        self.assertEqual(heads, ["#### Milestones", "#### Flags"])
        self.assertIn("- `presale-launch to gm-in-seat` (preference) was set aside, 4 days short", text)

    def test_flags_heading_is_left_out_when_nothing_is_off(self):
        text = ms.render_sections(DURATIONS, JUNCTION, ms.Solution(junction(), [], set()))
        self.assertNotIn("#### Flags", text)
        self.assertNotIn("#### Inputs", text)


class TestRewrite(unittest.TestCase):
    def test_replaces_only_the_marked_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("before\n<!-- milestones:junction:start -->\nold\n<!-- milestones:junction:end -->\nafter\n")
            ms.rewrite_note(path, "junction", "NEW TABLE")
            with open(path, encoding="utf-8") as f:
                text = f.read()
        self.assertEqual(text, "before\n<!-- milestones:junction:start -->\nNEW TABLE\n<!-- milestones:junction:end -->\nafter\n")

    def test_missing_markers_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("no markers\n")
            with self.assertRaises(SystemExit):
                ms.rewrite_note(path, "junction", "x")


if __name__ == "__main__":
    unittest.main()
