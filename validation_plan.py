"""Freeze new parameter seeds after correcting the private outcome grader."""
import argparse
import json
from pathlib import Path
from campaign import atomic_json, load_plan, source_hashes
from outcome_grader import outcome_grader_hash
from workflows import digest


def build(source, output):
    original = load_plan(source)
    if original["source_sha256"] != source_hashes():
        raise ValueError("frozen actor files changed")
    cells = []
    for row in original["cells"]:
        cell = {k: v for k, v in row.items() if k != "cell_id"}
        cell["case_seed"] = {11: 77, 22: 99}[cell["case_seed"]]
        cell["cell_id"] = digest(cell)[:20]
        cells.append(cell)
    plan = {**original, "phase": "new_parameter_validation", "cells": cells,
            "source_plan_id": original["plan_id"], "private_outcome_grader_hash": outcome_grader_hash(),
            "purpose": "New entity/amount seeds after exploratory grader correction; not new business families.",
            "selection": original["selection"]}
    plan.pop("plan_id")
    plan["plan_id"] = digest(plan)
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    atomic_json(output / "plan.json", plan)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build(args.source, args.output)
    print(json.dumps({"plan_id": plan["plan_id"], "cells": len(plan["cells"])}))
