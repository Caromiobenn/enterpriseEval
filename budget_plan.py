"""Post-hoc single-factor output-budget diagnostic for failed size-8 tasks."""
import argparse
import copy
import json
from pathlib import Path
from campaign import atomic_json, audit, load_plan, source_hashes
from protocols import ActorConfig, actor_signature
from workflows import digest, make_case


def build(source, output):
    original = load_plan(source)
    records, missing = audit(source, original)
    if missing or original["source_sha256"] != source_hashes():
        raise ValueError("requires complete frozen extension")
    cells, mapping = [], []
    by_id = {r["cell_id"]: r["result"] for r in records}
    for row in original["cells"]:
        if row["scale"] != 8 or row["config"]["max_output_tokens"] != 512:
            raise ValueError("unexpected source budget or scale")
        cell = copy.deepcopy(row)
        cell.pop("cell_id")
        cell["config"]["max_output_tokens"] = 2048
        cell["cell_id"] = digest(cell)[:20]
        case = make_case(cell["family"], cell["case_seed"], cell["scale"], cell["fault"])
        new_hash = actor_signature(case, ActorConfig(**cell["config"]), cell["model"], cell["model_revision"])
        if new_hash == by_id[row["cell_id"]]["actor_hash"]:
            raise ValueError("budget change must invalidate actor evidence reuse")
        cells.append(cell)
        mapping.append({"source_cell": row["cell_id"], "target_cell": cell["cell_id"],
                        "changed_field": "config.max_output_tokens", "old": 512, "new": 2048,
                        "migration_action": "rerun", "old_actor_hash": by_id[row["cell_id"]]["actor_hash"],
                        "new_actor_hash": new_hash})
    plan = {"schema": 1, "phase": "output_budget_diagnostic", "selection": original["selection"],
            "independent_business_families": 2, "source_sha256": source_hashes(),
            "source_plan_id": original["plan_id"], "cells": cells,
            "scope": "Post-hoc diagnostic chosen after observing size-8 truncation, not confirmatory evidence.",
            "server_context_limit": 16384, "total_token_budget_matched": False,
            "caution": "More output allowance can also reduce available input context; keep all failures in denominator."}
    plan["plan_id"] = digest(plan)
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "pair-mapping.json", mapping)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build(args.source, args.output)
    print(json.dumps({"plan_id": plan["plan_id"], "cells": len(plan["cells"])}))
