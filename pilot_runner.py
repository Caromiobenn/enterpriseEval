"""Predeclared engineering pilot; all tasks are dev. No statistical quality claims."""
import concurrent.futures
import hashlib
import json
import random
from pathlib import Path

from enterprise_eval import make_task, run_live

OUT = Path("artifacts/live-pilot-20260919")


def one_model(model, port):
    cases = [(4, False), (4, True), (8, False), (8, True)]
    random.Random(20260919).shuffle(cases)
    results = []
    for depth, fault in cases:
        task = make_task(0, depth, fault)
        result = run_live(task, f"http://127.0.0.1:{port}/v1", model, 20260919, max_calls=40)
        path = OUT / f"{model}-{task.id}.json"
        with path.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        row = {"model": model, "task_id": task.id, "depth": depth, "fault": fault,
               "success": result["grading"]["success"], "checks": result["grading"]["checks"],
               "termination": result["termination"], "error": result["error"],
               "usage": result["usage"], "usage_complete": result["usage_complete"],
               "seconds": result["duration_seconds"], "tool_calls": len(result["events"]),
               "model_calls": len(result["provider_responses"]),
               "artifact": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        results.append(row)
        print(json.dumps(row), flush=True)
    return results


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=False)
    protocol = {"purpose": "engineering_feasibility_only", "template_count": 1,
                "parameter_seed_count": 1, "split": "dev", "depths": [4, 8],
                "faults": [False, True], "repeats": 1, "model_count": 2,
                "temperature": .6, "top_p": .9, "max_tokens_per_call": 1024,
                "max_model_calls": 40, "seed": 20260919,
                "source_sha256": hashlib.sha256(Path("enterprise_eval.py").read_bytes()).hexdigest()}
    (OUT / "protocol.json").write_text(json.dumps(protocol, indent=2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one_model, model, port) for model, port in
                   [("qwen2.5-7b-instruct-awq", 8001), ("qwen2.5-14b-instruct-awq", 8000)]]
        rows = [row for future in futures for row in future.result()]
    (OUT / "summary.json").write_text(json.dumps({"status": "engineering_pilot", "rows": rows}, indent=2))
