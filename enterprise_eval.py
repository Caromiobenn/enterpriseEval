"""CPU research prototype. Scripted checks are NOT model evaluation results."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Task:
    id: str
    root_id: str
    split: str
    depth: int
    fault: bool
    goal: str
    nodes: dict[str, list[str]]

    def public_request(self) -> dict:
        return {
            "task_id": self.id,
            "instruction": f"Complete workflow goal {self.goal}. Discover prerequisites with inspect. "
            "Do not complete unrelated work. Each completion has a side effect; avoid duplicates. "
            "A timeout may occur after a write commits. Reuse request_id to retry a write safely. "
            "Use status to verify the state before declaring completion.",
            "goal": self.goal,
            "available_nodes": sorted(self.nodes),
        }


def make_task(root: int, depth: int, fault: bool) -> Task:
    if root < 0 or depth < 2:
        raise ValueError("root >= 0 and depth >= 2 required")
    rng = random.Random(root)
    names = rng.sample(range(1000, 9999), depth + 2)
    ids = [f"ticket-{n}" for n in names]
    nodes = {node: ([] if i == 0 else [ids[i - 1]]) for i, node in enumerate(ids[:depth])}
    # Distractors are real work items, not necessary for this request.
    nodes.update({node: [] for node in ids[depth:]})
    return Task(f"workflow-r{root}-d{depth}-f{int(fault)}", f"r{root}",
                "dev" if root < 6 else "heldout", depth, fault, ids[depth - 1], nodes)


class Environment:
    """In-memory tool boundary; no filesystem or shell tools exposed to the actor."""

    def __init__(self, task: Task):
        self.task = task
        self.done: set[str] = set()
        self.effects: list[str] = []
        self.requests: dict[str, str] = {}
        self.fault_triggered = False
        self.events: list[dict] = []

    def call(self, name: str, arguments: dict) -> dict:
        before = self.snapshot()
        try:
            result = self._call(name, arguments)
        except (ValueError, KeyError, TypeError) as exc:
            result = {"error": type(exc).__name__, "message": str(exc)}
        self.events.append({"tool": name, "arguments": copy.deepcopy(arguments),
                            "result": result, "before": digest(before),
                            "after": digest(self.snapshot())})
        return result

    def _call(self, name: str, arguments: dict) -> dict:
        if name not in {"inspect", "complete", "status"}:
            raise ValueError("unknown tool")
        if name == "status":
            if arguments:
                raise ValueError("status accepts no arguments")
            return {"done": sorted(self.done)}
        allowed = {"node"} if name == "inspect" else {"node", "request_id"}
        if set(arguments) != allowed:
            raise ValueError("wrong tool arguments")
        node = arguments["node"]
        if node not in self.task.nodes:
            raise ValueError("unknown node")
        if name == "inspect":
            return {"node": node, "prerequisites": self.task.nodes[node], "done": node in self.done}
        key = arguments["request_id"]
        if not isinstance(key, str) or not key:
            raise ValueError("nonempty request_id required")
        if key in self.requests:
            if self.requests[key] != node:
                raise ValueError("request_id reused for a different operation")
            return {"done": node, "replayed": True}
        if not all(dep in self.done for dep in self.task.nodes[node]):
            raise ValueError("prerequisites incomplete")
        self.requests[key] = node
        self.done.add(node)
        self.effects.append(node)
        if self.task.fault and not self.fault_triggered and len(self.effects) == max(1, self.task.depth // 2):
            self.fault_triggered = True
            return {"error": "timeout", "message": "Response unavailable; commit status unknown."}
        return {"done": node, "replayed": False}

    def snapshot(self) -> dict:
        return {"done": sorted(self.done), "effects": list(self.effects)}


def grade(task: Task, snapshot: dict) -> dict:
    """Evaluator computes acceptance from dependency closure, not reference trace."""
    required: set[str] = set()
    frontier = [task.goal]
    while frontier:
        node = frontier.pop()
        if node not in required:
            required.add(node)
            frontier.extend(task.nodes[node])
    done = set(snapshot["done"])
    effects = snapshot["effects"]
    checks = {
        "goal_and_dependencies": required <= done,
        "no_unrelated_changes": done <= required and set(effects) <= required,
        "no_duplicate_effects": len(effects) == len(set(effects)),
        "state_ledger_agreement": set(effects) == done,
    }
    return {"success": all(checks.values()), "checks": checks,
            "progress": len(required & done) / len(required)}


def reference_solve(env: Environment) -> None:
    """Scripted recursive solver using public tool responses only."""
    def visit(node: str) -> None:
        obs = env.call("inspect", {"node": node})
        if obs["done"]:
            return
        for dep in obs["prerequisites"]:
            visit(dep)
        args = {"node": node, "request_id": f"reference-{node}"}
        reply = env.call("complete", args)
        if reply.get("error") == "timeout":
            env.call("complete", args)
    visit(env.task.public_request()["goal"])


def task_manifest(task: Task, verifier_version: str = "1", note: str = "") -> dict:
    return {"task_id": task.id, "root_id": task.root_id, "split": task.split,
            "actor_hash": digest({"task": asdict(task), "tool_contract": "1", "budget": 80}),
            "verifier_hash": digest(verifier_version), "note": note}


def migration(old: dict | None, new: dict, artifact_complete: bool = True) -> str:
    if old is None or old["actor_hash"] != new["actor_hash"] or not artifact_complete:
        return "rerun"
    if old["verifier_hash"] != new["verifier_hash"]:
        return "regrade"
    return "reuse"


def paired_root_bootstrap(rows: list[dict], draws: int = 2000, seed: int = 19) -> dict:
    """Conditional on this workflow family; resample independent task roots."""
    if draws < 100:
        raise ValueError("at least 100 draws required")
    pairs: dict[tuple, dict] = {}
    for row in rows:
        if row["system"] not in {"a", "b"} or row["success"] not in {0, 1}:
            raise ValueError("binary outcomes for systems a and b required")
        key = (row["root_id"], row["task_id"], row["repeat"])
        if row["system"] in pairs.setdefault(key, {}):
            raise ValueError("duplicate cell")
        pairs[key][row["system"]] = row["success"]
    roots: dict[str, list[float]] = {}
    for key, cells in pairs.items():
        if set(cells) != {"a", "b"}:
            raise ValueError("incomplete pair")
        roots.setdefault(key[0], []).append(cells["b"] - cells["a"])
    if len(roots) < 2:
        raise ValueError("need at least two independent roots")
    means = [sum(values) / len(values) for values in roots.values()]
    rng = random.Random(seed)
    samples = sorted(sum(rng.choices(means, k=len(means))) / len(means) for _ in range(draws))
    return {"difference_b_minus_a": sum(means) / len(means),
            "ci95_percentile": [samples[int(.025 * (draws - 1))], samples[int(.975 * (draws - 1))]],
            "independent_roots": len(roots), "paired_cells": len(pairs),
            "scope": "root-macro average; conditional on task family; small-root CI is exploratory"}


TOOLS = [{"type": "function", "function": {"name": name, "description": description,
          "parameters": {"type": "object", "properties": properties,
                         "required": list(properties), "additionalProperties": False}}}
         for name, description, properties in [
             ("inspect", "Read prerequisite IDs and status for one workflow node.", {"node": {"type": "string"}}),
             ("complete", "Complete node after prerequisites; use stable request_id for retries.",
              {"node": {"type": "string"}, "request_id": {"type": "string"}}),
             ("status", "Read all completed workflow nodes.", {})]]


def run_live(task: Task, base_url: str, model: str, seed: int, max_calls: int = 40,
             api_key: str | None = None, single_call: bool = False) -> dict:
    """OpenAI-compatible local endpoint; no private grader information in messages."""
    import time
    env = Environment(task)
    actor_instruction = "Use tools to complete the public workflow task."
    if single_call:
        actor_instruction += (
            " Issue exactly one structured tool call per turn, using the supplied tool-call format. "
            "Do not describe intended calls or print raw JSON in ordinary prose. "
            "Inspect unmet prerequisites before trying to complete a node. "
            "Continue after recoverable tool errors; inspect state rather than assuming success. "
            "Check status before your final response."
        )
    messages = [{"role": "system", "content": actor_instruction},
                {"role": "user", "content": json.dumps(task.public_request())}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    usage_complete = True
    trace = []
    error = None
    termination = "budget_exhausted"
    started = time.monotonic()
    for call in range(max_calls):
        if time.monotonic() - started > 600:
            termination = "wall_budget_exhausted"
            break
        payload = {"model": model, "messages": messages, "tools": TOOLS,
                   "temperature": .6, "top_p": .9, "seed": seed, "max_tokens": 1024,
                   "stream": False}
        if single_call:
            payload["parallel_tool_calls"] = False
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                             json.dumps(payload).encode(), headers)
            with urllib.request.urlopen(request, timeout=min(60, max(1, 600 - (time.monotonic() - started)))) as response:
                result = json.load(response)
            trace.append(result)
            if not result.get("usage"):
                usage_complete = False
            for key in usage:
                usage[key] += result.get("usage", {}).get(key, 0)
            message = result["choices"][0]["message"]
            messages.append(message)
            calls = message.get("tool_calls", [])
            if not calls:
                content = message.get("content") or ""
                if result["choices"][0].get("finish_reason") == "length":
                    termination = "output_truncated"
                elif "<tool_call>" in content or ('"name"' in content and '"arguments"' in content):
                    termination = "unparsed_tool_text"
                else:
                    termination = "actor_stopped"
                break
            if len(calls) > 16:
                raise ValueError("too many tool calls in one response")
            for tool_call in calls:
                function = tool_call["function"]
                try:
                    args = json.loads(function["arguments"])
                    if not isinstance(args, dict):
                        raise ValueError("tool arguments must be an object")
                    observation = env.call(function["name"], args)
                except (ValueError, TypeError) as exc:
                    observation = {"error": "invalid_arguments", "message": str(exc)}
                messages.append({"role": "tool", "tool_call_id": tool_call["id"],
                                 "content": json.dumps(observation)})
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            termination = "execution_error"
            usage_complete = False
            break
    manifest = task_manifest(task)
    manifest["actor_hash"] = digest({"task_actor_hash": manifest["actor_hash"],
                                     "system_prompt": actor_instruction, "single_call": single_call,
                                     "max_calls": max_calls, "temperature": .6, "top_p": .9,
                                     "max_tokens": 1024, "model": model})
    return {"mode": "live", "task_id": task.id, "root_id": task.root_id,
            "seed": seed, "model": model, "manifest": manifest,
            "actor_protocol": "single_call_diagnostic" if single_call else "minimal",
            "grading": grade(task, env.snapshot()), "termination": termination, "error": error,
            "usage": usage, "usage_complete": usage_complete,
            "duration_seconds": time.monotonic() - started, "events": env.events,
            "messages": messages, "provider_responses": trace, "final_state": env.snapshot()}


def smoke(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    manifests = []
    for root in range(12):
        for depth in (4, 8, 16):
            for fault in (False, True):
                task = make_task(root, depth, fault)
                env = Environment(task)
                reference_solve(env)
                verdict = grade(task, env.snapshot())
                no_op = grade(task, {"done": [], "effects": []})
                missing = env.snapshot()
                missing["done"].remove(task.goal)
                duplicate = env.snapshot()
                duplicate["effects"].append(task.goal)
                unrelated = env.snapshot()
                other = next(node for node in task.nodes if node not in env.done)
                unrelated["done"].append(other)
                unrelated["effects"].append(other)
                rejected = [not grade(task, candidate)["success"] for candidate in (missing, duplicate, unrelated)]
                rows.append({"mode": "scripted_reference", "task_id": task.id,
                             "root_id": task.root_id, "split": task.split,
                             "reference_pass": verdict["success"],
                             "no_op_rejected": not no_op["success"],
                             "mutations_rejected": sum(rejected), "fault_activated": env.fault_triggered})
                manifests.append(task_manifest(task))
    (output / "contracts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    summary = {"mode": "CPU_CONTRACT_ONLY_NOT_MODEL_RESULTS", "tasks": len(rows), "roots": 12,
               "task_families": 1, "dev_roots": 6, "heldout_roots": 6,
               "reference_passes": sum(row["reference_pass"] for row in rows),
               "no_op_rejections": sum(row["no_op_rejected"] for row in rows),
               "mutant_rejections": sum(row["mutations_rejected"] for row in rows),
               "fault_activations": sum(row["fault_activated"] for row in rows)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["smoke", "live"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model")
    parser.add_argument("--root", type=int, default=0)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--seed", type=int, default=19)
    args = parser.parse_args()
    if args.command == "smoke":
        print(json.dumps(smoke(args.output), indent=2))
    else:
        if not args.model:
            parser.error("--model required for live")
        import os
        result = run_live(make_task(args.root, args.depth, True), args.base_url, args.model,
                          args.seed, api_key=os.environ.get("ENTERPRISE_EVAL_API_KEY"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(json.dumps({"grading": result["grading"], "termination": result["termination"]}))
