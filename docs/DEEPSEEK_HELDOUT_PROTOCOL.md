# DeepSeek held-out recovery study — frozen before model validation

## Question and split

Does explicit recovery guidance change success under a lost response after a committed write? Existing offboarding is development only. New release authorization/deployment and stock reservation/dispatch families are validation only. No validation model output may be used to tune this frozen run. Environment and grader unit tests use constructed reference/mutant states, not validation model outputs. This is a prospective holdout from model-driven tuning, not blind independent task authorship or an official external benchmark.

The only environmental treatment is **one response loss after the first committed write**, versus no loss. Initial state, task, number of records, prerequisites and tool schemas are unchanged within a pair. Dependency depth and distractor count are not varied. A separate, crossed prompt factor is minimal vs explicit recovery guidance; this is not claimed to isolate an entire agent framework component.

4 development cells + 128 validation cells: 2 new semantic families × 4 variants × 2 API models × 2 prompt conditions × 2 fault conditions × 2 repeats. Variants and repeats are correlated; there are only two new semantic families, not 128 independent tasks. API aliases may change; preserve returned model identifiers and timestamps. No unsupported seed parameter is sent, and repeats are not advertised as seed-matched.

## Grader and review

Private outcome checking constructs the target state algebraically, independent of the reference action order. Legal operation-wise and record-wise schedules must pass, including an identical-ID retry after response loss. Incomplete outcomes, harmful state changes and duplicate committed operations must fail. Initial deterministic suite has 14 checks. This is necessary but not sufficient evidence of grader validity.

Do not calculate validation grades until blind review labels have been written. Select variant 0, repeat 0 from every family/model/prompt/fault stratum in advance (16 records); anonymize IDs and hide model, system prompt, fault flag and automatic labels. Reviewer sees instructions, initial state, actual tool arguments/responses, final state and committed effects. Infer outcome and instruction compliance independently and cite concrete evidence. Tool traces can reveal a timeout, so this is label/model masking, not full treatment blinding. Reviewer is the Codex assistant, not an independent human; retain that limitation. The reviewer shares knowledge of task construction and is not epistemically independent of the designer.

Save blind labels before opening the private mapping and running the deterministic grader. Report disagreements and ambiguous cases without editing the frozen grader to improve the same validation score. If a bug forces a revision, retain old results, make a new version, and treat these tasks as development thereafter.

## API execution and stopping

Server data disk, isolated Git branch `exp/v6-deepseek-heldout-recovery`. Native tool calling, thinking disabled, temperature 0.2, at most 20 model calls and 1024 output tokens per call. Two model aliases: deepseek-flash and deepseek-v4-pro. No model-generated code is executed; only allowlisted in-memory business tools run.

Sequential execution, incremental raw response/trajectory writes. Stop on uncertain billing, missing usage, HTTP/transport failure, per-request context safety cap, six-hour process deadline or conservative USD 5 usage ceiling. Reserve a conservative request allowance before sending; record actual usage with the higher listed peak rates (input USD 1.32/M, output USD 3.96/M) regardless of model/cache, so reported budget is an upper estimate rather than actual billing. Pricing verified 2026-09-19: https://api-docs.deepseek.com/quick_start/pricing/ . Never log environment variables or authentication headers. A crash with an unfinished cell requires audit, not silent rerun.

All failures remain in the denominator. Report per-family paired results and exposure rates, not a synthetic overall model ranking. Two repeats cannot establish reliable high-order pass^k. Plan hash and source hash are frozen before run. The two projects may share the infrastructure; these episodes count once.

## External validation follow-up

Inspect official AppWorld installation and license; pin the version and respect train/dev/test separation. Downloading code is not a completed reproduction. Keep official tasks/results separate from these synthetic tasks. Any model execution must isolate generated code from host credentials and private evaluators. Do not rush external benchmark setup at the cost of evaluator leakage.
