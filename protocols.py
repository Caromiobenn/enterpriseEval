"""Budgeted local-model actors. Native tools and constrained JSON stay distinct."""
from __future__ import annotations

import inspect
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from workflows import BusinessEnvironment, actor_environment_hash, digest, grade_snapshot, grader_hash, tool_specs


@dataclass(frozen=True)
class ActorConfig:
    transport: str = "native"
    strategy: str = "minimal"
    max_model_calls: int = 24
    max_tool_calls: int = 40
    max_output_tokens: int = 512
    max_seconds: float = 240
    temperature: float = 0.2
    top_p: float = 0.9


def system_prompt(case, config):
    text = "Complete the user's business task using the available tools. Finish only after checking the state."
    if config.strategy == "recovery":
        text += (" First inspect current records and identify exactly which records are in scope. "
                 "Track necessary actions and their prerequisites. Execute one action at a time. "
                 "After any write timeout, read the affected state or retry the identical operation with "
                 "the same request_id. Do not repeat already successful writes. A tool error is an observation; "
                 "correct the problem and continue when possible. Preserve unrelated records.")
    elif config.strategy != "minimal":
        raise ValueError("unknown strategy")
    if config.transport == "json":
        text += (" Respond only as a JSON object with keys tool and arguments. Choose one available tool; "
                 "use tool=finish and arguments={} when done. No markdown, prose or invented observations. "
                 "Tool contracts: " + json.dumps(tool_specs(case)))
    elif config.transport == "native":
        text += " Use the structured tool-call interface for actions; do not print calls in ordinary text."
    else:
        raise ValueError("unknown transport")
    return text


def action_schema(case):
    specs = [tool["function"] for tool in tool_specs(case)]
    properties = {key: value for spec in specs for key, value in spec["parameters"]["properties"].items()}
    return {"type": "object", "properties": {
        "tool": {"type": "string", "enum": [s["name"] for s in specs] + ["finish"]},
        "arguments": {"type": "object", "properties": properties, "additionalProperties": False}},
        "required": ["tool", "arguments"], "additionalProperties": False}


def actor_signature(case, config, model, model_revision):
    return digest({"environment": actor_environment_hash(case), "config": asdict(config),
                   "prompt": system_prompt(case, config), "model": model, "revision": model_revision,
                   "loop": inspect.getsource(run_actor), "json_schema": action_schema(case)})


def run_actor(case, config, base_url, model, model_revision, seed, deadline_epoch=None, response_checkpoint=None):
    env = BusinessEnvironment(case)
    messages = [{"role": "system", "content": system_prompt(case, config)},
                {"role": "user", "content": json.dumps(case.public())}]
    responses, usage = [], {"prompt_tokens": 0, "completion_tokens": 0}
    started, usage_complete = time.monotonic(), True
    limit = min(config.max_seconds, max(0, deadline_epoch - time.time())) if deadline_epoch else config.max_seconds
    termination, error, tool_calls = "model_budget", None, 0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for turn in range(config.max_model_calls):
        remaining = limit - (time.monotonic() - started)
        if remaining <= 0:
            termination = "time_budget"
            break
        payload = {"model": model, "messages": messages, "stream": False,
                   "temperature": config.temperature, "top_p": config.top_p,
                   "seed": seed, "max_tokens": config.max_output_tokens}
        if config.transport == "native":
            payload.update({"tools": tool_specs(case), "tool_choice": "auto", "parallel_tool_calls": False})
        else:
            payload.update({"guided_json": action_schema(case), "guided_decoding_backend": "outlines"})
        try:
            request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                             json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with opener.open(request, timeout=min(60, remaining)) as response:
                raw = json.load(response)
            responses.append(raw)
            if response_checkpoint:
                response_checkpoint(raw)
            measured = raw.get("usage") or {}
            for key in usage:
                if not isinstance(measured.get(key), int):
                    usage_complete = False
                else:
                    usage[key] += measured[key]
            choice, message = raw["choices"][0], raw["choices"][0]["message"]
            messages.append(message)
            if choice.get("finish_reason") == "length":
                termination = "output_truncated"
                break  # Never execute a partially emitted action.
            if config.transport == "native":
                calls = message.get("tool_calls") or []
                if not calls:
                    content = message.get("content") or ""
                    termination = "unparsed_tool_text" if ("<tool_call>" in content or
                        ('"name"' in content and '"arguments"' in content)) else "actor_finished"
                    break
                actions = [(call["function"]["name"], json.loads(call["function"]["arguments"]), call["id"])
                           for call in calls]
            else:
                action = json.loads(message.get("content") or "")
                if set(action) != {"tool", "arguments"} or not isinstance(action["arguments"], dict):
                    raise ValueError("invalid action envelope")
                if action["tool"] == "finish":
                    if action["arguments"]:
                        raise ValueError("finish accepts no arguments")
                    termination = "actor_finished"
                    break
                actions = [(action["tool"], action["arguments"], None)]
            if tool_calls + len(actions) > config.max_tool_calls:
                termination = "tool_budget"
                break
            for name, arguments, call_id in actions:
                observation = env.call(name, arguments)
                tool_calls += 1
                if config.transport == "native":
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(observation)})
                else:
                    messages.append({"role": "user", "content": json.dumps({"tool": name, "observation": observation})})
        except urllib.error.HTTPError as exc:
            termination, error, usage_complete = "http_error", f"HTTP {exc.code}: {exc.read().decode()[:1000]}", False
            break
        except (ValueError, KeyError, TypeError) as exc:
            termination, error = "protocol_error", f"{type(exc).__name__}: {exc}"
            break
        except Exception as exc:
            termination, error, usage_complete = "transport_error", f"{type(exc).__name__}: {exc}", False
            break
    snapshot = env.snapshot()
    return {"case": asdict(case), "case_id": case.id, "family": case.family,
            "model": model, "model_revision": model_revision, "seed": seed, "config": asdict(config),
            "actor_hash": actor_signature(case, config, model, model_revision), "grader_hash": grader_hash("v1"),
            "grader_version": "v1", "grading": grade_snapshot(case, snapshot, "v1"),
            "legacy_grading": grade_snapshot(case, snapshot, "v0"),
            "termination": termination, "error": error, "model_calls": len(responses), "tool_calls": tool_calls,
            "usage": usage, "usage_complete": usage_complete, "seconds": time.monotonic() - started,
            "effective_time_budget_seconds": limit,
            "fault_planned": case.fault, "fault_activated": env.fault_activated,
            "messages": messages, "provider_responses": responses, "events": env.events, "final_state": snapshot}
