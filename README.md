# enterpriseEval — v2 strict action protocol

Pure-text foundation-model evaluation: tool protocol sensitivity, state-based grading, reliable evidence reuse, and versioned challenge sets. [Research foundations and scope](docs/FOUNDATIONS.md) document ACL/NeurIPS/ICML publications, AppWorld's ACL award, and Sierra/Anthropic sources. Recent unvetted preprints are not prerequisites for this design.

## Development experiment

The two synthetic families are offboarding (assets/access) and invoice reconciliation (matching/refunds/cash). This version separates each tool's JSON argument schema and documents unique per-operation request IDs. It preserves v1's failed probe and does not silently repair malformed model text.

| Frozen development protocol | Success | Transport/format errors |
|---|---:|---:|
| Native minimal | 6/8 | 0/8 |
| Native recovery prompt | 7/8 | 0/8 |
| Constrained JSON recovery | 6/8 | 0/8 |

[Raw development evidence](artifacts/v2-dev/summary.json) and [selection record](artifacts/v2-dev/selection.json) are saved. One seed, two families, clean/fault, two models, one sample per cell. This is engineering selection, not a significant superiority claim. A shared native-recovery protocol was selected before running the parameter-holdout matrix.

## Frozen matrix

64 cells: 2 families × 2 entity seeds × 2 sizes × 2 fault conditions × 2 models × 2 repeats. Size varies within seed, avoiding a seed/size confound. These are two business families, not 64 independent tasks. Qwen2.5-7B/14B-Instruct-AWQ run on separate RTX4090 GPUs. All runs retain original responses, per-response journals, state and usage. Missing, incompatible and duplicate cells are explicitly audited.

The matrix completed 64/64 planned cells. Strict success: 14B offboarding 16/16, reconciliation 12/16; 7B offboarding 10/16, reconciliation 6/16. Total 44/64. [Audited summary](artifacts/v2-main/summary.json). This is a small, correlated synthetic workload, not a broad model ranking. No long-horizon capability or cross-domain generalization is claimed.

`python -m unittest -v` checks contracts. `campaign.py plan`, `run`, and `summarize` freeze and execute schedules. Keep source hashes fixed within a batch. A completed or failed cell is not silently overwritten; interruptions remain visible in the attempt ledger.
