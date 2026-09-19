"""Private grader revision: separate correct outcomes from redundant operations.

This is an exploratory correction after inspecting v2-main, not a preregistered
metric. Frozen actor/environment files and historical grades remain unchanged.
"""
from collections import Counter
import inspect

from workflows import digest, grade_snapshot


def required_operations(case):
    s, req = case.initial, case.request
    operations = []
    def add(tool, **arguments):
        operations.append({"tool": tool, "arguments": arguments})
    if case.family == "offboarding":
        target = req["target_user"]
        for key, val in s["assets"].items():
            if val["owner"] == target:
                add("transfer_asset", asset_id=key, new_owner=req["successor"])
        for key, val in s["access"].items():
            if val["user"] == target and val["enabled"]:
                add("revoke_access", access_id=key)
        add("disable_user", user_id=target)
    else:
        seen = set()
        payments = sorted(s["payments"].items(), key=lambda item: item[1]["sequence"])
        for key, val in payments:
            if val["customer"] != req["customer"]:
                continue
            if val["invoice_id"] is None:
                add("link_payment", payment_id=key, invoice_id=val["invoice_reference"])
            if val["bank_reference"] in seen:
                add("refund_payment", payment_id=key)
            seen.add(val["bank_reference"])
        for key, val in s["invoices"].items():
            if val["customer"] == req["customer"]:
                add("close_invoice", invoice_id=key)
    return operations


def grade_outcome(case, snapshot):
    previous = grade_snapshot(case, snapshot, "v1")
    required = Counter(digest(op) for op in required_operations(case))
    observed = Counter(digest(op) for op in snapshot["effects"])
    # Only an already-correct initial link can be extra without an actual state
    # change. Repeated required writes remain explicit instruction violations.
    harmless = set()
    if case.family == "reconciliation":
        for key, val in case.initial["payments"].items():
            if val["customer"] == case.request["customer"] and val["invoice_id"] == val["invoice_reference"]:
                harmless.add(digest({"tool": "link_payment", "arguments": {
                    "payment_id": key, "invoice_id": val["invoice_reference"]}}))
    surplus = observed - required
    checks = {
        "full_business_state": previous["checks"]["full_business_state"],
        "required_operation_evidence": all(observed[k] >= n for k, n in required.items()),
        "no_repeated_committed_operation": all(n == 1 for n in observed.values()),
        "extra_operations_are_initially_correct_links": all(k in harmless for k in surplus),
    }
    return {"success": all(checks.values()), "checks": checks, "grader_version": "v2-outcome",
            "diagnostics": {"harmless_extra_links": sum(n for k, n in surplus.items() if k in harmless),
                            "operation_count": sum(observed.values()),
                            "minimum_required_operations": sum(required.values())}}


def outcome_grader_hash():
    return digest({"version": "v2-outcome", "state_oracle": inspect.getsource(grade_snapshot),
                   "required": inspect.getsource(required_operations), "grader": inspect.getsource(grade_outcome)})
