"""Execute evidence reuse, private regrading, and model reruns as separate operations."""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import time

from campaign import MODELS, atomic_json, audit, load_plan
from protocols import ActorConfig, actor_signature, run_actor
from workflows import BusinessEnvironment, Case, digest, grade_snapshot, grader_hash, make_case, reference_solve


def migration_decision(old, target, artifact_complete=True):
    if not artifact_complete or old is None or old["actor_hash"] != target["actor_hash"]:
        return "rerun"
    if old.get("sampling_seed") != target.get("sampling_seed"):
        return "rerun"
    if bool(old.get("grader_feedback_to_actor")) != bool(target.get("grader_feedback_to_actor")):
        return "rerun"
    if old["grader_hash"] != target["grader_hash"]:
        if old.get("grader_feedback_to_actor") or target.get("grader_feedback_to_actor"):
            return "rerun"
        return "regrade"
    return "reuse"


def seeded_grader_audit():
    rows = []
    for family in ("offboarding", "reconciliation"):
        for seed in (0, 11, 22):
            case = make_case(family, seed, 2, True)
            for reverse in (False, True):
                env = BusinessEnvironment(case)
                reference_solve(env, reverse)
                legal = env.snapshot()
                rows.append({"family": family, "seed": seed, "kind": "legal_alternative", "expected": True,
                             "v0": grade_snapshot(case, legal, "v0")["success"],
                             "v1": grade_snapshot(case, legal, "v1")["success"]})
            variants = {}
            duplicate = env.snapshot()
            duplicate["effects"].append(duplicate["effects"][0])
            variants["duplicate_audit_effect"] = duplicate
            missing = env.snapshot()
            missing["effects"].pop()
            variants["missing_effect_evidence"] = missing
            collateral = env.snapshot()
            if family == "offboarding":
                other = next(k for k in collateral["state"]["users"] if k.endswith("other"))
                collateral["state"]["users"][other]["active"] = False
            else:
                collateral["state"]["cash"] -= 1
            variants["collateral_or_cash_corruption"] = collateral
            for kind, snapshot in variants.items():
                rows.append({"family": family, "seed": seed, "kind": kind, "expected": False,
                             "v0": grade_snapshot(case, snapshot, "v0")["success"],
                             "v1": grade_snapshot(case, snapshot, "v1")["success"]})
    return {"scope": "deliberately seeded grader weakness; not an external benchmark vulnerability",
            "legal_cases": sum(row["expected"] for row in rows),
            "invalid_cases": sum(not row["expected"] for row in rows),
            "v0_false_accepts": sum(not r["expected"] and r["v0"] for r in rows),
            "v1_false_accepts": sum(not r["expected"] and r["v1"] for r in rows),
            "v1_false_rejects": sum(r["expected"] and not r["v1"] for r in rows), "rows": rows}


def prepare(source, output, full_rerun=True):
    source_plan = load_plan(source)
    records, missing = audit(source, source_plan)
    if missing or not records:
        raise ValueError("source campaign must be complete")
    output.mkdir(parents=True, exist_ok=False)
    (output / "reruns").mkdir()
    migrations, jobs = [], []
    grade_cpu_total, grade_wall_total = 0.0, 0.0
    start_cpu, start_wall = time.process_time(), time.perf_counter()
    for record in records:
        data, cell = record["result"], record["cell"]
        case = Case(**data["case"])
        config = ActorConfig(**data["config"])
        old = {"actor_hash": data["actor_hash"], "grader_hash": grader_hash("v0"),
               "sampling_seed": data["seed"], "grader_feedback_to_actor": False}
        new = {**old, "grader_hash": grader_hash("v1")}
        current_actor = actor_signature(case, config, data["model"], data["model_revision"])
        if current_actor != old["actor_hash"]:
            raise ValueError("source actor implementation differs; use the frozen source")
        assert migration_decision(old, {**old, "note": "documentation only"}) == "reuse"
        assert migration_decision(old, new) == "regrade"
        grade_cpu_start, grade_wall_start = time.process_time(), time.perf_counter()
        new_grade = grade_snapshot(case, data["final_state"], "v1")
        grade_cpu_total += time.process_time() - grade_cpu_start
        grade_wall_total += time.perf_counter() - grade_wall_start
        if new_grade != data["grading"] or grade_snapshot(case, data["final_state"], "v0") != data["legacy_grading"]:
            raise ValueError("saved grading cannot be reconstructed")
        migrations.append({"source_cell": cell["cell_id"], "source_result_sha256": record["result_sha256"],
                           "old": old, "target": new, "metadata_action": "reuse", "grader_action": "regrade",
                           "old_grade": data["legacy_grading"], "new_grade": new_grade,
                           "matches_saved_strict_verdict": True, "additional_model_calls": 0,
                           "additional_prompt_tokens": 0, "additional_completion_tokens": 0})
        bridge = cell["case_seed"] == 11 and cell["scale"] == 2 and cell["repeat"] == 0
        if full_rerun or bridge:
            jobs.append({"source_cell": cell["cell_id"], "mode": "full_rerun_control", "config": asdict(config),
                         "case": data["case"], "model": data["model"], "revision": data["model_revision"],
                         "seed": data["seed"], "target_actor_hash": old["actor_hash"]})
        if bridge:
            changed = replace(config, strategy="minimal" if config.strategy == "recovery" else "recovery")
            changed_hash = actor_signature(case, changed, data["model"], data["model_revision"])
            assert migration_decision(old, {**new, "actor_hash": changed_hash}) == "rerun"
            jobs.append({"source_cell": cell["cell_id"], "mode": "actor_change_requires_rerun", "config": asdict(changed),
                         "case": data["case"], "model": data["model"], "revision": data["model_revision"],
                         "seed": data["seed"], "target_actor_hash": changed_hash})
    cpu = {"records": len(migrations), "regrade_cpu_seconds": grade_cpu_total,
           "regrade_wall_seconds": grade_wall_total,
           "migration_preparation_cpu_seconds": time.process_time() - start_cpu,
           "migration_preparation_wall_seconds": time.perf_counter() - start_wall,
           "natural_verdict_flips": sum(m["old_grade"]["success"] != m["new_grade"]["success"] for m in migrations),
           "all_same_artifact_strict_verdicts_match": True, "additional_model_calls": 0,
           "scope": "v0 was deliberately incomplete; stored v1 result is the deterministic reference"}
    for job in jobs:
        job["job_id"] = digest(job)[:20]
    random.Random(20260919).shuffle(jobs)
    plan = {"source_plan_id": source_plan["plan_id"], "full_rerun": full_rerun,
            "source_actor_files": source_plan["source_sha256"],
            "study_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "target_grader_hash": grader_hash("v1"), "jobs": jobs}
    plan["plan_id"] = digest(plan)
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "migrations.json", migrations)
    atomic_json(output / "regrade-summary.json", cpu)
    atomic_json(output / "seeded-grader-audit.json", seeded_grader_audit())
    return plan


def checked_plan(output):
    plan = json.loads((output / "plan.json").read_text())
    if digest({k: v for k, v in plan.items() if k != "plan_id"}) != plan["plan_id"]:
        raise ValueError("migration plan changed")
    return plan


def collect(output):
    plan = checked_plan(output)
    jobs = {j["job_id"]: j for j in plan["jobs"]}
    seen, rows = set(), []
    for path in sorted((output / "reruns").glob("*.json")):
        row = json.loads(path.read_text())
        job_id = row["job"]["job_id"]
        if job_id in seen or job_id not in jobs or row["job"] != jobs[job_id] or row["plan_id"] != plan["plan_id"]:
            raise ValueError("duplicate/incompatible migration result")
        if digest(row["result"]) != row["result_sha256"] or row["result"]["actor_hash"] != jobs[job_id]["target_actor_hash"]:
            raise ValueError("migration result hash/actor mismatch")
        if row.get("journal_sha256"):
            journal = output / "journals" / row["journal"]
            if Path(row["journal"]).name != row["journal"] or hashlib.sha256(journal.read_bytes()).hexdigest() != row["journal_sha256"]:
                raise ValueError("migration journal mismatch")
            if [json.loads(s) for s in journal.read_text().splitlines() if s] != row["result"]["provider_responses"]:
                raise ValueError("migration response journal differs")
        seen.add(job_id)
        rows.append(row)
    return plan, rows, sorted(set(jobs) - seen)


def summary(output):
    plan, rows, missing = collect(output)
    migrations = {m["source_cell"]: m for m in json.loads((output / "migrations.json").read_text())}
    groups = {}
    for mode in ("full_rerun_control", "actor_change_requires_rerun"):
        selected = [row for row in rows if row["job"]["mode"] == mode]
        groups[mode] = {"runs": len(selected), "successes": sum(r["result"]["grading"]["success"] for r in selected),
                        "prompt_tokens": sum(r["result"]["usage"]["prompt_tokens"] for r in selected),
                        "completion_tokens": sum(r["result"]["usage"]["completion_tokens"] for r in selected),
                        "sum_episode_seconds": sum(r["result"]["seconds"] for r in selected),
                        "usage_complete_runs": sum(r["result"]["usage_complete"] for r in selected),
                        "changed_success_from_archived_strict": sum(r["result"]["grading"]["success"] !=
                            migrations[r["job"]["source_cell"]]["new_grade"]["success"] for r in selected)}
    result = {"plan_id": plan["plan_id"], "planned_model_runs": len(plan["jobs"]), "observed": len(rows),
              "missing": missing, "complete": not missing, "groups": groups,
              "regrade": json.loads((output / "regrade-summary.json").read_text()),
              "note": "Regrading compares identical artifacts. Fresh reruns are stochastic and need not match itemwise."}
    atomic_json(output / "summary.json", result)
    return result


def _execute(output, deadline):
    plan, rows, missing = collect(output)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != plan["study_sha256"]:
        raise ValueError("study source changed after freeze")
    if any(hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() != sha
           for n, sha in plan["source_actor_files"].items()):
        raise ValueError("actor source changed after freeze")
    def worker(model):
        for job in [j for j in plan["jobs"] if j["model"] == model and j["job_id"] in missing]:
            if time.time() >= deadline - 5:
                break
            journal = output / "journals" / f"{job['job_id']}-{time.time_ns()}.jsonl"
            journal.parent.mkdir(exist_ok=True)
            def checkpoint(response):
                with journal.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(response) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            result = run_actor(Case(**job["case"]), ActorConfig(**job["config"]),
                               f"http://127.0.0.1:{MODELS[model]}/v1", model, job["revision"], job["seed"], deadline, checkpoint)
            target = output / "reruns" / f"{job['job_id']}.json"
            if target.exists():
                raise RuntimeError("would overwrite migration evidence")
            atomic_json(target, {"plan_id": plan["plan_id"], "job": job, "result": result,
                                 "result_sha256": digest(result), "journal": journal.name,
                                 "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest() if journal.exists() else None})
            print(json.dumps({"job": job["job_id"], "mode": job["mode"], "model": model,
                              "success": result["grading"]["success"], "seconds": result["seconds"]}), flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, model) for model in MODELS]
            for future in futures:
                future.result()
    finally:
        summary(output)


def execute(output, deadline):
    lockfile = output / "runner.lock"
    if lockfile.exists():
        try:
            os.kill(int(lockfile.read_text()), 0)
        except ProcessLookupError:
            lockfile.unlink()
        else:
            raise RuntimeError("migration runner may still be active")
    with lockfile.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        _execute(output, deadline)
    finally:
        lockfile.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run", "summarize"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bridge-only", action="store_true")
    parser.add_argument("--deadline", default="2026-09-19T12:15:00+00:00")
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.source:
            parser.error("--source required")
        plan = prepare(args.source, args.output, not args.bridge_only)
        print(json.dumps({"plan_id": plan["plan_id"], "jobs": len(plan["jobs"])}))
    elif args.command == "run":
        execute(args.output, datetime.fromisoformat(args.deadline).timestamp())
    else:
        print(json.dumps(summary(args.output), indent=2))
