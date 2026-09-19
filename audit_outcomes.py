"""Replay saved tool events and regrade immutable artifacts without model calls."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import time

from campaign import atomic_json, audit, load_plan
from migration_study import collect
from outcome_grader import grade_outcome, outcome_grader_hash
from protocols import ActorConfig, actor_signature
from workflows import BusinessEnvironment, Case, digest


def audit_record(record, source):
    data = record["result"]
    if digest(data) != record["result_sha256"]:
        raise ValueError("result content differs from saved digest")
    case = Case(**data["case"])
    if actor_signature(case, ActorConfig(**data["config"]), data["model"], data["model_revision"]) != data["actor_hash"]:
        raise ValueError("actor signature cannot be reconstructed")
    if "job" in record:
        job = record["job"]
        if (data["case"] != job["case"] or data["seed"] != job["seed"] or data["config"] != job["config"]
                or data["model"] != job["model"] or data["model_revision"] != job["revision"]):
            raise ValueError("migration result differs from scheduled conditions")
    replay = BusinessEnvironment(case)
    for event in data["events"]:
        answer = replay.call(event["tool"], event["arguments"])
        if answer != event["result"]:
            raise ValueError("tool replay differs from observed response")
    if replay.snapshot() != data["final_state"]:
        raise ValueError("tool replay differs from final artifact")
    start = time.perf_counter()
    grade = grade_outcome(case, data["final_state"])
    elapsed = time.perf_counter() - start
    return {"source": source, "source_result_sha256": record["result_sha256"],
            "model": data["model"], "family": case.family, "case_seed": case.seed,
            "scale": case.scale, "fault": case.fault, "sampling_seed": data["seed"],
            "actor_hash": data["actor_hash"], "old_grade": data["grading"], "new_grade": grade,
            "legacy_grade": data["legacy_grading"], "replayed_exactly": True,
            "regrade_seconds": elapsed, "termination": data["termination"],
            "model_calls": data["model_calls"], "tool_calls": data["tool_calls"],
            "usage": data["usage"], "fault_activated": data["fault_activated"]}


def run(campaigns, migrations, output):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    rows = []
    for folder in campaigns:
        records, missing = audit(folder, load_plan(folder))
        if missing:
            raise ValueError("campaign is incomplete")
        rows.extend(audit_record(r, folder.name) for r in records)
    for folder in migrations:
        _, records, missing = collect(folder)
        if missing:
            raise ValueError("migration control is incomplete")
        rows.extend(audit_record(r, folder.name + "/" + r["job"]["mode"]) for r in records)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["source"], row["model"], row["family"], row["scale"], row["fault"])].append(row)
    result = {"grader_hash": outcome_grader_hash(), "records": len(rows),
              "additional_model_calls": 0, "additional_tokens": 0,
              "all_tool_replays_exact": True,
              "regrade_seconds": sum(r["regrade_seconds"] for r in rows),
              "interpretation": "Exploratory v1 correction; initial correct links are harmless but counted as inefficiency. Not external human-validated gold labels.",
              "groups": [], "rows": rows}
    for key, values in sorted(groups.items()):
        result["groups"].append({"source": key[0], "model": key[1], "family": key[2], "scale": key[3], "fault": key[4],
                                 "runs": len(values),
                                 "old_successes": sum(r["old_grade"]["success"] for r in values),
                                 "new_successes": sum(r["new_grade"]["success"] for r in values),
                                 "changed": sum(r["new_grade"]["success"] != r["old_grade"]["success"] for r in values)})
    result["audit_load_replay_regrade_wall_seconds"] = time.perf_counter() - wall_start
    result["audit_load_replay_regrade_cpu_seconds"] = time.process_time() - cpu_start
    if output.exists():
        raise ValueError("refusing to overwrite audit")
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, action="append", default=[])
    parser.add_argument("--migration", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.campaign, args.migration, args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "groups"}}, indent=2))
