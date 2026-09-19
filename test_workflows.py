import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign import MODELS, atomic_json, audit, load_plan, make_plan
from protocols import ActorConfig, action_schema, actor_signature, run_actor
from workflows import BusinessEnvironment, digest, grade_snapshot, grader_hash, make_case, reference_solve


class WorkflowContracts(unittest.TestCase):
    def test_action_schema_keeps_tool_argument_sets_separate(self):
        schema = action_schema(make_case("offboarding", 0))
        branches = {b["properties"]["tool"]["enum"][0]: b["properties"]["arguments"] for b in schema["anyOf"]}
        self.assertEqual(set(branches["revoke_access"]["required"]), {"access_id", "request_id"})
        self.assertNotIn("user_id", branches["revoke_access"]["properties"])
        self.assertEqual(branches["finish"]["properties"], {})

    def test_reference_alternative_orders_and_noop(self):
        for family in ("offboarding", "reconciliation"):
            for seed in (0, 11, 22, 33):
                for scale in (1, 2, 4):
                    for fault in (False, True):
                        for reverse in (False, True):
                            case = make_case(family, seed, scale, fault)
                            env = BusinessEnvironment(case)
                            self.assertFalse(grade_snapshot(case, env.snapshot())["success"])
                            reference_solve(env, reverse=reverse)
                            self.assertTrue(grade_snapshot(case, env.snapshot())["success"], (case.id, reverse))
                            self.assertEqual(env.fault_activated, fault)

    def test_strict_grader_rejects_collateral_and_missing_evidence(self):
        for family in ("offboarding", "reconciliation"):
            case = make_case(family, 0)
            env = BusinessEnvironment(case)
            reference_solve(env)
            bad = env.snapshot()
            if family == "offboarding":
                other = next(k for k in bad["state"]["users"] if k.endswith("other"))
                bad["state"]["users"][other]["active"] = False
            else:
                bad["state"]["cash"] -= 1
            self.assertTrue(grade_snapshot(case, bad, "v0")["success"])
            self.assertFalse(grade_snapshot(case, bad, "v1")["success"])
            missing = env.snapshot()
            missing["effects"] = []
            self.assertFalse(grade_snapshot(case, missing)["success"])

    def test_timeout_retry_is_idempotent_new_key_duplicates_fail(self):
        for family in ("offboarding", "reconciliation"):
            case = make_case(family, 0, 2, True)
            env = BusinessEnvironment(case)
            reference_solve(env)
            event = next(e for e in env.events if isinstance(e["result"], dict) and
                         e["result"].get("error") == "timeout_after_commit")
            before = env.snapshot()
            self.assertTrue(env.call(event["tool"], event["arguments"])["replayed"])
            self.assertEqual(before, env.snapshot())
            repeated = {**event["arguments"], "request_id": "new-key"}
            env.call(event["tool"], repeated)
            self.assertFalse(grade_snapshot(case, env.snapshot())["success"])

    def test_disable_requires_both_assets_and_access_cleared(self):
        case = make_case("offboarding", 0)
        env = BusinessEnvironment(case)
        before = env.snapshot()
        result = env.call("disable_user", {"user_id": case.request["target_user"], "request_id": "x"})
        self.assertIn("error", result)
        self.assertEqual(before, env.snapshot())

    def test_invoice_cannot_close_with_duplicate_payments(self):
        case = make_case("reconciliation", 0)
        env = BusinessEnvironment(case)
        inv = next(iter(case.initial["invoices"]))
        self.assertIn("error", env.call("close_invoice", {"invoice_id": inv, "request_id": "x"}))

    def test_unknown_or_extra_arguments_do_not_mutate(self):
        env = BusinessEnvironment(make_case("reconciliation", 0))
        before = env.snapshot()
        for name, args in [("bad", {}), ("refund_payment", {"payment_id": "bad", "request_id": "x"}),
                           ("read_state", {"section": "all", "extra": "x"})]:
            self.assertIn("error", env.call(name, args))
            self.assertEqual(before, env.snapshot())

    def test_version_separation_and_actor_configuration_hash(self):
        case, config = make_case("offboarding", 0), ActorConfig()
        sig = actor_signature(case, config, "model", "revision")
        self.assertNotEqual(grader_hash("v0"), grader_hash("v1"))
        self.assertEqual(sig, actor_signature(case, config, "model", "revision"))
        self.assertNotEqual(sig, actor_signature(case, replace(config, max_model_calls=12), "model", "revision"))
        self.assertNotEqual(sig, actor_signature(case, config, "model", "new-revision"))

    def test_both_actor_protocols_execute_scripted_public_tool_trace(self):
        case = make_case("reconciliation", 0, 2, True)
        ref = BusinessEnvironment(case)
        reference_solve(ref)
        for transport in ("native", "json"):
            actions = list(ref.events)
            class Reply:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def read(self):
                    if actions:
                        event = actions.pop(0)
                        if transport == "native":
                            msg = {"role": "assistant", "content": None, "tool_calls": [
                                {"id": f"call-{len(actions)}", "type": "function", "function": {
                                    "name": event["tool"], "arguments": json.dumps(event["arguments"])}}]}
                        else:
                            msg = {"role": "assistant", "content": json.dumps({"tool": event["tool"], "arguments": event["arguments"]})}
                    else:
                        msg = {"role": "assistant", "content": "Done" if transport == "native" else '{"tool":"finish","arguments":{}}'}
                    return json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}],
                                       "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
            class Opener:
                def open(self, *args, **kwargs):
                    return Reply()
            with patch("urllib.request.build_opener", return_value=Opener()):
                result = run_actor(case, ActorConfig(transport=transport), "http://localhost", "scripted", "test", 1)
            self.assertTrue(result["grading"]["success"], result)
            self.assertTrue(result["fault_activated"])
            self.assertTrue(result["usage_complete"])


class ScheduleContracts(unittest.TestCase):
    def plan(self):
        return make_plan("dev", {m: "fixture" for m in MODELS})

    def record(self, plan, cell):
        case = make_case(cell["family"], cell["case_seed"], cell["scale"], cell["fault"])
        result = {"case": asdict(case), "model": cell["model"], "model_revision": cell["model_revision"],
                  "config": cell["config"], "seed": cell["sampling_seed"]}
        return {"plan_id": plan["plan_id"], "cell_id": cell["cell_id"], "cell": cell,
                "result": result, "result_sha256": digest(result)}

    def test_whole_model_missing_is_detected(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "results").mkdir()
            for cell in plan["cells"]:
                if "7b" in cell["model"]:
                    atomic_json(folder / "results" / f"{cell['cell_id']}.json", self.record(plan, cell))
            rows, missing = audit(folder, plan)
            self.assertEqual(len(rows), 12)
            self.assertEqual(len(missing), 12)

    def test_duplicate_or_incompatible_results_rejected(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "results").mkdir()
            record = self.record(plan, plan["cells"][0])
            path = folder / "results" / f"{record['cell_id']}.json"
            atomic_json(path, record)
            atomic_json(folder / "results" / "duplicate.json", record)
            with self.assertRaises(ValueError):
                audit(folder, plan)
            (folder / "results" / "duplicate.json").unlink()
            record["plan_id"] = "different"
            atomic_json(path, record)
            with self.assertRaises(ValueError):
                audit(folder, plan)

    def test_modified_plan_and_modified_result_rejected(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "results").mkdir()
            atomic_json(folder / "plan.json", plan)
            self.assertEqual(load_plan(folder)["plan_id"], plan["plan_id"])
            plan["cells"].pop()
            atomic_json(folder / "plan.json", plan)
            with self.assertRaises(ValueError):
                load_plan(folder)
            record = self.record(plan, plan["cells"][0])
            record["result"]["model"] = "wrong"
            atomic_json(folder / "results" / f"{record['cell_id']}.json", record)
            with self.assertRaises(ValueError):
                audit(folder, plan)


if __name__ == "__main__":
    unittest.main()
