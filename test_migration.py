from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from campaign import MODELS, atomic_json, make_plan
from migration_study import collect, migration_decision, prepare, seeded_grader_audit
from protocols import ActorConfig, actor_signature
from workflows import BusinessEnvironment, digest, grade_snapshot, grader_hash, make_case, reference_solve


class MigrationContracts(unittest.TestCase):
    def test_visibility_and_artifact_sufficiency(self):
        old = {"actor_hash": "a", "grader_hash": "g0"}
        self.assertEqual(migration_decision(old, {**old, "note": "new docs"}), "reuse")
        self.assertEqual(migration_decision(old, {**old, "grader_hash": "g1"}), "regrade")
        self.assertEqual(migration_decision(old, {**old, "actor_hash": "b"}), "rerun")
        self.assertEqual(migration_decision(old, old, False), "rerun")
        self.assertEqual(migration_decision(None, old), "rerun")
        self.assertEqual(migration_decision({**old, "sampling_seed": 1}, {**old, "sampling_seed": 2}), "rerun")
        self.assertEqual(migration_decision(old, {**old, "grader_feedback_to_actor": True}), "rerun")
        self.assertEqual(migration_decision({**old, "grader_feedback_to_actor": True},
                                           {**old, "grader_hash": "g1"}), "rerun")

    def test_seeded_weakness_and_legal_alternatives(self):
        audit = seeded_grader_audit()
        self.assertEqual(audit["legal_cases"], 12)
        self.assertEqual(audit["invalid_cases"], 18)
        self.assertEqual(audit["v0_false_accepts"], 18)
        self.assertEqual(audit["v1_false_accepts"], 0)
        self.assertEqual(audit["v1_false_rejects"], 0)

    def test_prepare_regrades_without_inference_and_declares_missing_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source", Path(directory) / "migration"
            (source / "results").mkdir(parents=True)
            plan = make_plan("main", {model: "scripted-fixture" for model in MODELS}, "native-recovery")
            atomic_json(source / "plan.json", plan)
            for cell in plan["cells"]:
                case = make_case(cell["family"], cell["case_seed"], cell["scale"], cell["fault"])
                env = BusinessEnvironment(case)
                reference_solve(env)
                result = {"case": asdict(case), "model": cell["model"], "model_revision": cell["model_revision"],
                          "config": cell["config"], "seed": cell["sampling_seed"], "final_state": env.snapshot(),
                          "actor_hash": actor_signature(case, ActorConfig(**cell["config"]), cell["model"], cell["model_revision"]),
                          "grading": grade_snapshot(case, env.snapshot(), "v1"),
                          "legacy_grading": grade_snapshot(case, env.snapshot(), "v0")}
                atomic_json(source / "results" / f"{cell['cell_id']}.json", {
                    "plan_id": plan["plan_id"], "cell_id": cell["cell_id"], "cell": cell,
                    "result": result, "result_sha256": digest(result)})
            with patch("migration_study.run_actor", side_effect=AssertionError("must not infer during regrading")):
                new_plan = prepare(source, output)
            regrade = json.loads((output / "regrade-summary.json").read_text())
            self.assertEqual(regrade["records"], 64)
            self.assertEqual(regrade["additional_model_calls"], 0)
            self.assertEqual(regrade["natural_verdict_flips"], 0)
            self.assertEqual(len(new_plan["jobs"]), 72)
            _, rows, missing = collect(output)
            self.assertEqual(len(rows), 0)
            self.assertEqual(len(missing), 72)


if __name__ == "__main__":
    unittest.main()
