"""Two small synthetic business environments; neither is a production benchmark."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import random
from dataclasses import asdict, dataclass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Case:
    family: str
    seed: int
    scale: int
    fault: bool
    initial: dict
    request: dict

    @property
    def id(self):
        return f"{self.family}-s{self.seed}-n{self.scale}-f{int(self.fault)}"

    def public(self):
        return {"case_id": self.id, **self.request}


def make_case(family, seed, scale=2, fault=False):
    if family not in {"offboarding", "reconciliation"} or scale < 1:
        raise ValueError("unknown family or invalid scale")
    rng = random.Random(seed)
    suffix = rng.randrange(10000, 99999)
    if family == "offboarding":
        target, successor, other = [f"user-{suffix}-{x}" for x in ("leaving", "successor", "other")]
        assets = {f"asset-{suffix}-{i}": {"owner": target, "archived": False} for i in range(scale)}
        assets[f"asset-{suffix}-protected"] = {"owner": other, "archived": False}
        access = {f"access-{suffix}-{i}": {"user": target, "app": f"app-{i}", "enabled": True}
                  for i in range(scale)}
        access[f"access-{suffix}-protected"] = {"user": other, "app": "shared", "enabled": True}
        state = {"users": {u: {"active": True} for u in (target, successor, other)},
                 "assets": assets, "access": access}
        request = {"target_user": target, "successor": successor,
                   "instruction": "Offboard the target user: transfer every asset they own to the successor, "
                   "revoke every access grant belonging to them, then disable their account. "
                   "Preserve all other users, assets and grants. Read state before deciding actions. "
                   "Writes can time out after committing: inspect state or retry with the SAME request_id. "
                   "Each write has an audit side effect; do not repeat successful writes with new IDs. "
                   "Verify the resulting state before finishing."}
    else:
        customer, other = f"customer-{suffix}", f"customer-{suffix}-other"
        invoices, payments = {}, {}
        seq = 0
        for i in range(scale):
            inv, amount = f"invoice-{suffix}-{i}", rng.choice([50, 100, 150, 200])
            invoices[inv] = {"customer": customer, "amount": amount, "status": "open"}
            payments[f"payment-{suffix}-{seq}"] = {
                "customer": customer, "amount": amount, "invoice_reference": inv,
                "invoice_id": inv if i % 2 == 0 else None, "bank_reference": f"bank-{suffix}-{i}",
                "sequence": seq, "refunded": False}
            seq += 1
            if i % 2 == 0:
                payments[f"payment-{suffix}-{seq}"] = {
                    "customer": customer, "amount": amount, "invoice_reference": inv,
                    "invoice_id": inv, "bank_reference": f"bank-{suffix}-{i}",
                    "sequence": seq, "refunded": False}
                seq += 1
        protected = f"invoice-{suffix}-protected"
        invoices[protected] = {"customer": other, "amount": 75, "status": "open"}
        payments[f"payment-{suffix}-protected"] = {
            "customer": other, "amount": 75, "invoice_reference": protected, "invoice_id": protected,
            "bank_reference": "bank-protected", "sequence": 999, "refunded": False}
        state = {"invoices": invoices, "payments": payments, "refunds": [], "cash": 5000}
        request = {"customer": customer,
                   "instruction": "Reconcile only the requested customer's invoices and payments. "
                   "Link unlinked payments using invoice_reference. Payments sharing a bank_reference "
                   "are duplicates: keep the smallest-sequence payment and refund each later one exactly once. "
                   "Close every invoice of this customer when its active linked payments equal its amount. "
                   "Preserve all other customers' records. Read state before acting and verify before finishing. "
                   "A write can time out after committing; inspect state or retry with the SAME request_id. "
                   "A refund repeated with a different request_id debits cash again."}
    return Case(family, seed, scale, fault, state, request)


def tool_specs(case):
    sections = list(case.initial) + ["all"]
    signatures = [("read_state", "Read current business state, including committed changes.",
                   {"section": {"type": "string", "enum": sections}})]
    string = {"type": "string"}
    if case.family == "offboarding":
        signatures += [
            ("transfer_asset", "Transfer ownership. Source and destination users must be active.",
             {"asset_id": string, "new_owner": string, "request_id": string}),
            ("revoke_access", "Revoke one access grant by its ID.", {"access_id": string, "request_id": string}),
            ("disable_user", "Disable only after all assets and access are cleared.",
             {"user_id": string, "request_id": string})]
    else:
        signatures += [
            ("link_payment", "Link a payment to an invoice; changes matching, not cash.",
             {"payment_id": string, "invoice_id": string, "request_id": string}),
            ("refund_payment", "Refund one payment; each distinct request ID debits cash.",
             {"payment_id": string, "request_id": string}),
            ("close_invoice", "Close invoice only when its active linked payments equal amount due.",
             {"invoice_id": string, "request_id": string})]
    return [{"type": "function", "function": {"name": n, "description": d,
             "parameters": {"type": "object", "properties": p, "required": list(p),
                            "additionalProperties": False}}} for n, d, p in signatures]


class BusinessEnvironment:
    def __init__(self, case):
        self.case = case
        self.state = copy.deepcopy(case.initial)
        self.effects, self.events, self.requests = [], [], {}
        self.fault_activated = False

    def snapshot(self):
        return {"state": copy.deepcopy(self.state), "effects": copy.deepcopy(self.effects)}

    def call(self, name, args):
        before = digest(self.snapshot())
        try:
            spec = next(t["function"]["parameters"] for t in tool_specs(self.case)
                        if t["function"]["name"] == name)
            if not isinstance(args, dict) or set(args) != set(spec["required"]):
                raise ValueError("exact tool argument names required")
            if any(not isinstance(v, str) or not v for v in args.values()):
                raise ValueError("arguments must be nonempty strings")
            result = self._call(name, args)
        except (KeyError, ValueError, TypeError, StopIteration) as exc:
            result = {"error": type(exc).__name__, "message": str(exc) or "unknown tool"}
        self.events.append({"tool": name, "arguments": copy.deepcopy(args), "result": result,
                            "before": before, "after": digest(self.snapshot())})
        return result

    def _call(self, name, args):
        if name == "read_state":
            return copy.deepcopy(self.state if args["section"] == "all" else self.state[args["section"]])
        key = args["request_id"]
        operation = {"tool": name, "arguments": {k: v for k, v in args.items() if k != "request_id"}}
        if key in self.requests:
            if self.requests[key] != operation:
                raise ValueError("request_id belongs to a different operation")
            return {"ok": True, "replayed": True}
        s = self.state
        if name == "transfer_asset":
            asset = s["assets"][args["asset_id"]]
            if not s["users"][asset["owner"]]["active"] or not s["users"][args["new_owner"]]["active"]:
                raise ValueError("both owner accounts must be active")
            asset["owner"] = args["new_owner"]
        elif name == "revoke_access":
            s["access"][args["access_id"]]["enabled"] = False
        elif name == "disable_user":
            user = args["user_id"]
            if any(a["owner"] == user for a in s["assets"].values()) or any(
                    a["user"] == user and a["enabled"] for a in s["access"].values()):
                raise ValueError("transfer assets and revoke access first")
            s["users"][user]["active"] = False
        elif name == "link_payment":
            payment, invoice = s["payments"][args["payment_id"]], s["invoices"][args["invoice_id"]]
            if payment["customer"] != invoice["customer"]:
                raise ValueError("customer mismatch")
            payment["invoice_id"] = args["invoice_id"]
        elif name == "refund_payment":
            payment = s["payments"][args["payment_id"]]
            payment["refunded"] = True
            s["cash"] -= payment["amount"]
            s["refunds"].append({"payment_id": args["payment_id"], "amount": payment["amount"]})
        elif name == "close_invoice":
            invoice = s["invoices"][args["invoice_id"]]
            paid = sum(p["amount"] for p in s["payments"].values()
                       if p["invoice_id"] == args["invoice_id"] and not p["refunded"])
            if paid != invoice["amount"]:
                raise ValueError(f"active payment total {paid} differs from amount due")
            invoice["status"] = "closed"
        else:
            raise ValueError("unknown write")
        self.requests[key] = operation
        self.effects.append(operation)
        if self.case.fault and not self.fault_activated and len(self.effects) == 2:
            self.fault_activated = True
            return {"error": "timeout_after_commit", "message": "Response unavailable; commit status unknown."}
        return {"ok": True, "replayed": False}


def grade_snapshot(case, snapshot, version="v1"):
    """Independent expected-state construction; v0 intentionally omits invariants."""
    if version not in {"v0", "v1"}:
        raise ValueError("unknown grader")
    s, initial = snapshot["state"], case.initial
    expected = copy.deepcopy(initial)
    if case.family == "offboarding":
        target = case.request["target_user"]
        expected["users"][target]["active"] = False
        for value in expected["assets"].values():
            if value["owner"] == target:
                value["owner"] = case.request["successor"]
        for value in expected["access"].values():
            if value["user"] == target:
                value["enabled"] = False
        goal = not s["users"][target]["active"]
        state_ok = s == expected
        required_effects = 1 + sum(a["owner"] == target for a in initial["assets"].values()) + sum(
            a["user"] == target and a["enabled"] for a in initial["access"].values())
    else:
        customer = case.request["customer"]
        payments = [(key, val) for key, val in initial["payments"].items() if val["customer"] == customer]
        seen, refunds = set(), []
        for key, val in sorted(payments, key=lambda kv: kv[1]["sequence"]):
            if val["bank_reference"] in seen:
                expected["payments"][key]["refunded"] = True
                refunds.append({"payment_id": key, "amount": val["amount"]})
            seen.add(val["bank_reference"])
            if val["invoice_id"] is None:
                expected["payments"][key]["invoice_id"] = val["invoice_reference"]
        target_invoices = [k for k, v in initial["invoices"].items() if v["customer"] == customer]
        for key in target_invoices:
            expected["invoices"][key]["status"] = "closed"
        expected["refunds"] = sorted(refunds, key=lambda x: x["payment_id"])
        expected["cash"] -= sum(r["amount"] for r in refunds)
        candidate = copy.deepcopy(s)
        candidate["refunds"] = sorted(candidate["refunds"], key=lambda x: x["payment_id"])
        state_ok = candidate == expected
        goal = all(s["invoices"][key]["status"] == "closed" for key in target_invoices)
        required_effects = len(refunds) + len(target_invoices) + sum(v["invoice_id"] is None for _, v in payments)
    effects = snapshot["effects"]
    no_duplicates = len(effects) == len({digest(e) for e in effects})
    checks = {"requested_goal": goal}
    if version == "v1":
        checks.update({"full_business_state": state_ok, "no_duplicate_effects": no_duplicates,
                       "effect_count": len(effects) == required_effects})
    return {"success": all(checks.values()), "checks": checks, "grader_version": version}


def reference_solve(env, reverse=False):
    """Uses public request and read_state output, never the grader's expected state."""
    s = env.call("read_state", {"section": "all"})
    operations = []
    if env.case.family == "offboarding":
        target = env.case.request["target_user"]
        operations += [("transfer_asset", {"asset_id": k, "new_owner": env.case.request["successor"]})
                       for k, v in s["assets"].items() if v["owner"] == target]
        operations += [("revoke_access", {"access_id": k}) for k, v in s["access"].items()
                       if v["user"] == target and v["enabled"]]
        if reverse:
            operations.reverse()
        operations.append(("disable_user", {"user_id": target}))
    else:
        customer = env.case.request["customer"]
        records = [(k, v) for k, v in s["payments"].items() if v["customer"] == customer]
        grouped = {}
        for key, value in records:
            grouped.setdefault(value["bank_reference"], []).append((key, value))
            if value["invoice_id"] is None:
                operations.append(("link_payment", {"payment_id": key, "invoice_id": value["invoice_reference"]}))
        for group in grouped.values():
            for key, value in sorted(group, key=lambda pair: pair[1]["sequence"])[1:]:
                operations.append(("refund_payment", {"payment_id": key}))
        if reverse:
            operations.reverse()
        operations += [("close_invoice", {"invoice_id": k}) for k, v in s["invoices"].items()
                       if v["customer"] == customer]
    for i, (name, args) in enumerate(operations):
        args["request_id"] = f"reference-{i}"
        result = env.call(name, args)
        if result.get("error") == "timeout_after_commit":
            result = env.call(name, args)
        if "error" in result:
            raise RuntimeError(result)
    env.call("read_state", {"section": "all"})


def actor_environment_hash(case):
    return digest({"case": asdict(case), "tools": tool_specs(case),
                   "environment_code": inspect.getsource(BusinessEnvironment),
                   "tool_schema_code": inspect.getsource(tool_specs)})


def grader_hash(version):
    return digest({"version": version, "code": inspect.getsource(grade_snapshot)})
