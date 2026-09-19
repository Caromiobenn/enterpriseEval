"""Rebuild descriptive result tables; no significance claim across two families."""
from collections import Counter
import json
from pathlib import Path

from campaign import atomic_json, audit, load_plan
from migration_study import collect
from outcome_grader import grade_outcome, outcome_grader_hash
from workflows import Case

ROOT = Path(__file__).resolve().parent


def build():
    phases = {}
    for name in ("v2-dev", "v2-main", "v3-extension", "v4-validation", "v5-budget"):
        folder = ROOT / "artifacts" / name
        plan = load_plan(folder)
        if "private_outcome_grader_hash" in plan and plan["private_outcome_grader_hash"] != outcome_grader_hash():
            raise ValueError("validation grader differs from the frozen pre-run revision")
        records, missing = audit(folder, plan)
        if missing:
            raise ValueError(f"incomplete {name}")
        phases[name] = records
    _, migrations, missing = collect(ROOT / "artifacts/v3-migration")
    if missing:
        raise ValueError("incomplete migration")
    for mode in ("full_rerun_control", "actor_change_requires_rerun"):
        phases[mode] = [r for r in migrations if r["job"]["mode"] == mode]

    tables = []
    for phase, records in phases.items():
        models = sorted({r["result"]["model"] for r in records})
        for model in models:
            data = [r["result"] for r in records if r["result"]["model"] == model]
            new = [grade_outcome(Case(**d["case"]), d["final_state"]) for d in data]
            tables.append({"phase": phase, "model": model, "runs": len(data),
                           "v0_goal_success": sum(d["legacy_grading"]["success"] for d in data),
                           "v1_exact_count_success": sum(d["grading"]["success"] for d in data),
                           "v2_outcome_success": sum(g["success"] for g in new),
                           "terminations": dict(Counter(d["termination"] for d in data)),
                           "fault_planned": sum(d["fault_planned"] for d in data),
                           "fault_activated": sum(d["fault_activated"] for d in data),
                           "activated_and_successful": sum(d["fault_activated"] and g["success"] for d, g in zip(data, new)),
                           "usage_complete_runs": sum(d["usage_complete"] for d in data),
                           "reported_prompt_tokens": sum(d["usage"]["prompt_tokens"] for d in data),
                           "reported_completion_tokens": sum(d["usage"]["completion_tokens"] for d in data),
                           "sum_episode_seconds_not_wall_time": sum(d["seconds"] for d in data)})

    main = {r["cell_id"]: r for r in phases["v2-main"]}
    pairs = []
    for record in phases["actor_change_requires_rerun"]:
        source = main[record["job"]["source_cell"]]["result"]
        target = record["result"]
        pairs.append({"source_cell": record["job"]["source_cell"], "job_id": record["job"]["job_id"],
                      "model": target["model"],
                      "source_historical_v1": source["grading"]["success"],
                      "target_historical_v1": target["grading"]["success"],
                      "source_outcome": grade_outcome(Case(**source["case"]), source["final_state"])["success"],
                      "target_outcome": grade_outcome(Case(**target["case"]), target["final_state"])["success"]})

    extension = {r["cell_id"]: r for r in phases["v3-extension"]}
    budget = {r["cell_id"]: r for r in phases["v5-budget"]}
    mapping = json.loads((ROOT / "artifacts/v5-budget/pair-mapping.json").read_text())
    budget_pairs = []
    for pair in mapping:
        old, new = extension[pair["source_cell"]], budget[pair["target_cell"]]
        expected = json.loads(json.dumps(old["cell"]))
        expected["config"]["max_output_tokens"] = 2048
        expected["cell_id"] = new["cell_id"]
        if expected != new["cell"]:
            raise ValueError("budget comparison changed another factor")
        budget_pairs.append({**pair, "model": new["result"]["model"],
                             "old_termination": old["result"]["termination"],
                             "new_termination": new["result"]["termination"],
                             "old_success": grade_outcome(Case(**old["result"]["case"]), old["result"]["final_state"])["success"],
                             "new_success": grade_outcome(Case(**new["result"]["case"]), new["result"]["final_state"])["success"]})
    result = {"grader_hash": outcome_grader_hash(), "tables": tables,
              "actor_change_pairs": pairs, "output_budget_pairs": budget_pairs,
              "audited_v2plus_model_runs": sum(len(records) for records in phases.values()),
              "independent_business_families": 2,
              "note": "Descriptive correlated synthetic conditions; post-hoc diagnostic comparisons, no cross-domain significance claim."}
    atomic_json(ROOT / "artifacts/final-results.json", result)
    lines = ["# 可重建结果表", "", "下表由 `python results_report.py` 从完整计划与原始产物重建。v0只看目标，v1含过严操作数约束，v2-outcome区分无害冗余与业务错误。", "",
             "| 批次 | 模型 | 运行数 | v0目标 | v1历史 | v2-outcome | usage完整 |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in tables:
        model = "14B" if "14b" in row["model"] else "7B"
        lines.append(f"| {row['phase']} | {model} | {row['runs']} | {row['v0_goal_success']} | {row['v1_exact_count_success']} | {row['v2_outcome_success']} | {row['usage_complete_runs']} |")
    lines += ["", "所有分数仅对应这两个合成业务家族。开发、锚点、新参数验证、规模扩展和预算诊断分别解释，不合成模型总榜。usage不完整的运行不能当作零成本。",
              "", "完整分层信息、终止类型、故障触发与配对核对见 [final-results.json](../artifacts/final-results.json)。"]
    (ROOT / "docs/RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = build()
    print(json.dumps({"audited_v2plus_model_runs": result["audited_v2plus_model_runs"],
                      "output_budget_pairs": len(result["output_budget_pairs"])}))
