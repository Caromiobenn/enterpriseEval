"""A documented development-triggered size extension, retaining frozen anchors."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random

from campaign import atomic_json, audit, load_plan, source_hashes
from protocols import ActorConfig, actor_signature
from workflows import BusinessEnvironment, digest, grade_snapshot, make_case, reference_solve


def build_extension(dev, anchors, output):
    dev_plan, anchor_plan = load_plan(dev), load_plan(anchors)
    dev_rows, dev_missing = audit(dev, dev_plan)
    anchor_rows, anchor_missing = audit(anchors, anchor_plan)
    if dev_missing or anchor_missing:
        raise ValueError("development and anchor campaigns must be complete")
    if anchor_plan["source_sha256"] != source_hashes():
        raise ValueError("anchor implementation changed")
    chosen = anchor_plan["selection"]
    model_groups = {}
    for row in dev_rows:
        if row["cell"]["config_name"] == chosen:
            model_groups.setdefault(row["cell"]["model"], []).append(row["result"]["grading"]["success"])
    # Engineering proposal rule chosen after the initial development inspection.
    # This is deliberately not described as a preregistered significance test.
    trigger = any(len(values) >= 4 and all(values) for values in model_groups.values())
    if not trigger:
        raise ValueError("no development model cleared all four small conditions; do not expand")
    cells, mapping, witnesses = [], [], []
    anchor_records = {row["cell_id"]: row["result"] for row in anchor_rows}
    for old in anchor_plan["cells"]:
        if old["scale"] != 4:
            continue
        new = {k: copy.deepcopy(v) for k, v in old.items() if k != "cell_id"}
        new["scale"] = 8
        new["cell_id"] = digest(new)[:20]
        new_case = make_case(new["family"], new["case_seed"], new["scale"], new["fault"])
        new_hash = actor_signature(new_case, ActorConfig(**new["config"]), new["model"], new["model_revision"])
        old_hash = anchor_records[old["cell_id"]]["actor_hash"]
        if new_hash == old_hash:
            raise ValueError("task expansion must change the actor conditions")
        cells.append(new)
        mapping.append({"anchor_cell": old["cell_id"], "extension_cell": new["cell_id"],
                        "axis_changed": "number of business records", "old_size": 4, "new_size": 8,
                        "old_actor_hash": old_hash, "new_actor_hash": new_hash, "migration_action": "rerun"})
    unique_cases = {(c["family"], c["case_seed"], c["fault"]) for c in cells}
    for family, seed, fault in sorted(unique_cases):
        case = make_case(family, seed, 8, fault)
        for reverse in (False, True):
            env = BusinessEnvironment(case)
            reference_solve(env, reverse)
            verdict = grade_snapshot(case, env.snapshot())
            if not verdict["success"]:
                raise ValueError("extension lacks a valid reference witness")
            # Include reads and the required model finish turn in feasibility accounting.
            if len(env.events) + 1 > cells[0]["config"]["max_model_calls"]:
                raise ValueError("reference interaction exceeds the model-call budget")
            witnesses.append({"case_id": case.id, "reverse": reverse, "verdict": verdict,
                              "tool_calls": len(env.events), "fault_activated": env.fault_activated,
                              "final_state": env.snapshot()})
    random.Random(20260919).shuffle(cells)
    plan = {"schema": 1, "phase": "challenge_extension", "selection": chosen,
            "source_sha256": source_hashes(), "independent_business_families": 2,
            "scope": "same two synthetic families; expanded size is not an independent task family",
            "development_plan_id": dev_plan["plan_id"], "anchor_plan_id": anchor_plan["plan_id"],
            "trigger": "at least one development model solved all four size-2 conditions",
            "trigger_is_preregistered": False, "cells": cells}
    plan["plan_id"] = digest(plan)
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "anchor-mapping.json", mapping)
    atomic_json(output / "reference-witnesses.json", witnesses)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_extension(args.dev, args.anchors, args.output)
    print(json.dumps({"plan_id": plan["plan_id"], "cells": len(plan["cells"])}))
