# enterpriseEval — v1 business workflow probe

Pure-text evaluation methods for foundation models: protocol sensitivity, business-state grading, fault recovery and evaluation version migration. See [verified research foundations](docs/FOUNDATIONS.md).

This version adds two synthetic families: employee offboarding (ownership and access invariants) and invoice reconciliation (duplicate payments, matching and cash conservation). 21 contract tests pass, including alternate valid action orders and seeded invalid states. These are small controlled environments, not a reproduction of AppWorld or tau-bench.

The four constrained-JSON preflight runs in `artifacts/v1-probe` all failed. Traces show two concrete problems: the action-envelope schema allowed the argument sets of different tools to mix, and both models reused a task ID across distinct write operations. One response was truncated. Raw evidence is retained; no bad text is silently repaired into an action.

The next version tests a discriminated action schema and an explicit per-operation request-ID contract. This v1 branch remains the original failed probe. Historical v0 pilots remain in their own branches and artifact directories. No broad model ranking or long-horizon capability claim follows from these probes.

Run `python -m unittest -v`. `campaign.py` freezes planned cells, records per-response journals, rejects incompatible/duplicate results and reports wholly missing conditions. CPU tests are not model success rates.
