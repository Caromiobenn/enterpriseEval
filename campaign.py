"""Frozen schedules, resumable cells, explicit missingness, and raw evidence."""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import asdict
from datetime import datetime
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import statistics
import threading
import time

from protocols import ActorConfig, run_actor
from workflows import digest, make_case

MODELS = {"qwen2.5-7b-instruct-awq": 8001, "qwen2.5-14b-instruct-awq": 8000}
SOURCE_FILES = ["workflows.py", "protocols.py", "campaign.py"]


def source_hashes():
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def revisions(inventory):
    grouped = {model: {} for model in MODELS}
    for line in Path(inventory).read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        if len(sha) != 64:
            raise ValueError("invalid model inventory")
        for model in grouped:
            if model.replace("qwen", "Qwen").replace("-instruct-awq", "-Instruct-AWQ").replace("7b", "7B").replace("14b", "14B") in name:
                grouped[model][Path(name).name] = sha
    if any(not value or not any(k.endswith(".safetensors") for k in value) for value in grouped.values()):
        raise ValueError("both model weight inventories required")
    return {model: digest(files) for model, files in grouped.items()}


def make_plan(phase, model_revisions, selected="json-recovery"):
    if phase not in {"probe", "dev", "main"}:
        raise ValueError("unknown phase")
    configs = [selected] if phase == "main" else (["json-recovery"] if phase == "probe" else
                                                ["native-minimal", "native-recovery", "json-recovery"])
    seeds = [11, 22] if phase == "main" else [0]
    scales = [2, 4] if phase == "main" else [2]
    cells = []
    for family, seed, scale, fault, model, config_name, repeat in itertools.product(
            ("offboarding", "reconciliation"), seeds, scales,
            [True] if phase == "probe" else [False, True], MODELS, configs,
            range(2 if phase == "main" else 1)):
        transport, strategy = config_name.split("-")
        config = asdict(ActorConfig(transport=transport, strategy=strategy))
        cell = {"family": family, "case_seed": seed, "scale": scale,
                "fault": fault, "model": model, "model_revision": model_revisions[model],
                "config_name": config_name, "config": config, "repeat": repeat,
                "sampling_seed": 20260919 + repeat}
        cell["cell_id"] = digest(cell)[:20]
        cells.append(cell)
    random.Random(20260919).shuffle(cells)
    plan = {"schema": 1, "phase": phase, "independent_business_families": 2,
            "scope": "synthetic family-conditional experiment; parameter seeds are not semantic roots",
            "selection": selected if phase == "main" else "development_only",
            "source_sha256": source_hashes(), "cells": cells}
    plan["plan_id"] = digest(plan)
    return plan


def load_plan(folder):
    plan = json.loads((folder / "plan.json").read_text())
    payload = {k: v for k, v in plan.items() if k != "plan_id"}
    if digest(payload) != plan["plan_id"]:
        raise ValueError("plan hash mismatch")
    ids = [cell["cell_id"] for cell in plan["cells"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate planned cell")
    return plan


def audit(folder, plan):
    expected = {cell["cell_id"]: cell for cell in plan["cells"]}
    records, seen = [], set()
    for path in sorted((folder / "results").glob("*.json")):
        record = json.loads(path.read_text())
        cid = record["cell_id"]
        if cid in seen or cid not in expected or record["plan_id"] != plan["plan_id"]:
            raise ValueError("duplicate, unexpected, or incompatible result")
        if record["cell"] != expected[cid] or cid != path.stem:
            raise ValueError("cell metadata mismatch")
        if digest(record["result"]) != record["result_sha256"]:
            raise ValueError("result hash mismatch")
        if record.get("journal_sha256"):
            journal = folder / "journals" / record["journal"]
            if Path(record["journal"]).name != record["journal"] or not journal.is_file():
                raise ValueError("missing or invalid response journal")
            if hashlib.sha256(journal.read_bytes()).hexdigest() != record["journal_sha256"]:
                raise ValueError("journal hash mismatch")
            responses = [json.loads(line) for line in journal.read_text().splitlines() if line]
            if responses != record["result"]["provider_responses"]:
                raise ValueError("response journal differs from final artifact")
        result, cell = record["result"], expected[cid]
        expected_case = make_case(cell["family"], cell["case_seed"], cell["scale"], cell["fault"])
        if (result["case"] != asdict(expected_case) or result["model"] != cell["model"] or
            result["model_revision"] != cell["model_revision"] or result["config"] != cell["config"] or
            result["seed"] != cell["sampling_seed"]):
            raise ValueError("result does not match planned actor or case")
        records.append(record)
        seen.add(cid)
    return records, sorted(set(expected) - seen)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def summarize(folder):
    plan = load_plan(folder)
    records, missing = audit(folder, plan)
    groups = {}
    for record in records:
        result, cell = record["result"], record["cell"]
        key = f"{cell['model']}|{cell['config_name']}|{cell['family']}"
        groups.setdefault(key, []).append(result)
    metrics = {}
    for key, results in groups.items():
        times = sorted(r["seconds"] for r in results)
        metrics[key] = {"runs": len(results), "successes": sum(r["grading"]["success"] for r in results),
                        "faults_planned": sum(r["fault_planned"] for r in results),
                        "faults_activated": sum(r["fault_activated"] for r in results),
                        "activated_and_successful": sum(r["fault_activated"] and r["grading"]["success"] for r in results),
                        "protocol_failures": sum(r["termination"] in {"protocol_error", "unparsed_tool_text", "output_truncated"} for r in results),
                        "http_errors": sum(r["termination"] in {"http_error", "transport_error"} for r in results),
                        "mean_seconds": statistics.mean(times), "max_seconds": max(times),
                        "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in results),
                        "completion_tokens": sum(r["usage"]["completion_tokens"] for r in results),
                        "usage_complete_runs": sum(r["usage_complete"] for r in results)}
    summary = {"plan_id": plan["plan_id"], "phase": plan["phase"], "planned": len(plan["cells"]),
               "observed": len(records), "missing": missing, "complete": not missing, "groups": metrics,
               "scope": plan["scope"], "artifact_sha256": {
                   path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((folder / "results").glob("*.json"))}}
    atomic_json(folder / "summary.json", summary)
    return summary


def execute(folder, deadline_epoch):
    plan = load_plan(folder)
    if plan["source_sha256"] != source_hashes():
        raise ValueError("source changed after plan freeze")
    lockfile = folder / "runner.lock"
    if lockfile.exists():
        old_pid = int(lockfile.read_text())
        try:
            os.kill(old_pid, 0)
        except ProcessLookupError:
            lockfile.unlink()
        else:
            raise RuntimeError(f"runner PID {old_pid} may still be active")
    with lockfile.open("x") as handle:
        handle.write(str(os.getpid()))
    ledger_lock = threading.Lock()
    def log(event):
        with ledger_lock, (folder / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.time(), **event}) + "\n")
            handle.flush()
    try:
        _, missing = audit(folder, plan)
        pending = [c for c in plan["cells"] if c["cell_id"] in missing]
        def worker(model):
            for cell in [c for c in pending if c["model"] == model]:
                if time.time() >= deadline_epoch - 5:
                    break
                case = make_case(cell["family"], cell["case_seed"], cell["scale"], cell["fault"])
                journal = folder / "journals" / f"{cell['cell_id']}-{time.time_ns()}.jsonl"
                journal.parent.mkdir(exist_ok=True)
                def checkpoint(response):
                    with journal.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(response) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                log({"event": "started", "cell_id": cell["cell_id"], "journal": journal.name})
                result = run_actor(case, ActorConfig(**cell["config"]), f"http://127.0.0.1:{MODELS[model]}/v1",
                                   model, cell["model_revision"], cell["sampling_seed"], deadline_epoch, checkpoint)
                record = {"plan_id": plan["plan_id"], "cell_id": cell["cell_id"], "cell": cell,
                          "result": result, "result_sha256": digest(result), "journal": journal.name,
                          "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest() if journal.exists() else None}
                destination = folder / "results" / f"{cell['cell_id']}.json"
                if destination.exists():
                    raise RuntimeError("refusing to overwrite completed evidence")
                atomic_json(destination, record)
                log({"event": "finished", "cell_id": cell["cell_id"], "success": result["grading"]["success"],
                     "termination": result["termination"], "seconds": result["seconds"]})
                print(json.dumps({"cell": cell["cell_id"], "model": model, "family": case.family,
                                  "protocol": cell["config_name"], "success": result["grading"]["success"],
                                  "termination": result["termination"], "seconds": result["seconds"]}), flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, model) for model in MODELS]
            for future in futures:
                future.result()
    finally:
        lockfile.unlink(missing_ok=True)
        summarize(folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "run", "summarize"])
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--phase", choices=["probe", "dev", "main"], default="dev")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--selected", default="json-recovery")
    parser.add_argument("--deadline", default="2026-09-19T12:15:00+00:00")
    args = parser.parse_args()
    if args.command == "plan":
        if not args.inventory:
            parser.error("--inventory required")
        args.folder.mkdir(parents=True, exist_ok=False)
        (args.folder / "results").mkdir()
        plan = make_plan(args.phase, revisions(args.inventory), args.selected)
        atomic_json(args.folder / "plan.json", plan)
        print(json.dumps({"plan_id": plan["plan_id"], "cells": len(plan["cells"])}))
    elif args.command == "run":
        execute(args.folder, datetime.fromisoformat(args.deadline).timestamp())
    else:
        print(json.dumps(summarize(args.folder), indent=2))
