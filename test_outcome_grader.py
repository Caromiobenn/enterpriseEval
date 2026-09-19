import copy
import unittest
from workflows import BusinessEnvironment, make_case, reference_solve
from outcome_grader import grade_outcome


class OutcomeGraderContracts(unittest.TestCase):
    def test_extra_correct_link_is_not_wrong_outcome(self):
        case = make_case("reconciliation", 77, 4, True)
        env = BusinessEnvironment(case)
        key, val = next((k, v) for k, v in case.initial["payments"].items()
                        if v["customer"] == case.request["customer"] and v["invoice_id"] is not None)
        env.call("link_payment", {"payment_id": key, "invoice_id": val["invoice_id"], "request_id": "extra"})
        reference_solve(env, True)
        grade = grade_outcome(case, env.snapshot())
        self.assertTrue(grade["success"])
        self.assertEqual(grade["diagnostics"]["harmless_extra_links"], 1)

    def test_legal_orders_and_corrupt_evidence(self):
        for family in ("offboarding", "reconciliation"):
            for seed in (77, 99):
                for reverse in (False, True):
                    case = make_case(family, seed, 4, True)
                    env = BusinessEnvironment(case)
                    reference_solve(env, reverse)
                    self.assertTrue(grade_outcome(case, env.snapshot())["success"])
                    missing = env.snapshot(); missing["effects"].pop()
                    self.assertFalse(grade_outcome(case, missing)["success"])
                    duplicate = env.snapshot(); duplicate["effects"].append(copy.deepcopy(duplicate["effects"][0]))
                    self.assertFalse(grade_outcome(case, duplicate)["success"])

    def test_extra_refund_and_protected_record_change_fail(self):
        case = make_case("reconciliation", 99, 2, False)
        env = BusinessEnvironment(case); reference_solve(env)
        protected = next(k for k in case.initial["invoices"] if k.endswith("protected"))
        corrupt = env.snapshot(); corrupt["state"]["invoices"][protected]["status"] = "closed"
        self.assertFalse(grade_outcome(case, corrupt)["success"])
        refund = next(e for e in env.effects if e["tool"] == "refund_payment")
        env.call("refund_payment", {**refund["arguments"], "request_id": "wrong-retry"})
        self.assertFalse(grade_outcome(case, env.snapshot())["success"])
