# enterpriseEval — v0 minimal pilot

Research prototype for verifiable multi-step tool tasks and evaluation version migration.

This branch freezes the original 2026-09-19 minimal actor implementation and its 8 development runs. One dependency-chain template, one entity seed, depths 4/8, clean/fault, one run per condition and model. Qwen2.5-7B-Instruct-AWQ: 2/4 successful; Qwen2.5-14B-Instruct-AWQ: 0/4. These are engineering observations, not model rankings or independent-task generalization results.

- `artifacts/live-pilot-20260919/`: protocol, summary, full responses, tool events and final states.
- `artifacts/cpu-smoke-20260919/`: 72 parameter variants; 72 reference passes, 72 no-op rejections, 216 mutant rejections. Scripted tests are not model-quality results.
- `enterprise_eval.py`: environment, independent final-state grader, migration decision prototype, HTTP actor loop.
- `test_enterprise_eval.py`: 10 contract tests. Run `python -m unittest -v`.

The original actor-stop label also includes unparsed tool-shaped text and truncation; inspect raw provider responses. Migration is a decision function, not a complete execution pipeline. Object boundaries are not a process sandbox. Different identifier seeds are not independent business tasks.

Later protocols live on separate experiment branches. The `exp/v0-toolcall-diagnostic` branch changes prompting and records another 8 development runs; do not pool the protocols. A negative result remains part of the evidence.
