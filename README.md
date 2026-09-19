# enterpriseEval — v4 outcome-aware regrading

Pure-text foundation-model evaluation: tool protocol sensitivity, state-based grading, reliable evidence reuse, and versioned challenge sets. [Research foundations and scope](docs/FOUNDATIONS.md) document ACL/NeurIPS/ICML publications, AppWorld's ACL award, and Sierra/Anthropic sources. Recent unvetted preprints are not prerequisites for this design.

Current status: v4 corrects an overly restrictive operation-count check discovered in the main matrix. Historical v1 grades remain unchanged; all 256 v2–v4 records have been replayed exactly and audited. New parameter validation is complete. Read [methods and limitations](docs/EXPERIMENT_METHODS.md), [trace case studies](docs/CASE_STUDIES.md), and [interview questions](docs/INTERVIEW_DEFENSE.md).

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

The matrix completed 64/64 planned cells. Historical v1-grader success: 14B offboarding 16/16, reconciliation 12/16; 7B offboarding 10/16, reconciliation 6/16. Total 44/64. [Audited summary](artifacts/v2-main/summary.json). This is a small, correlated synthetic workload, not a broad model ranking. No long-horizon capability or cross-domain generalization is claimed.

`python -m unittest -v` checks contracts. `campaign.py plan`, `run`, and `summarize` freeze and execute schedules. Keep source hashes fixed within a batch. A completed or failed cell is not silently overwritten; interruptions remain visible in the attempt ledger.

## Grader correction and new-parameter validation

The revised private v2-outcome grader separates harmless initial-correct linking from outcome failure. Main matrix: 7B 22/32 and 14B 28/32, versus historical v1 16/32 and 28/32. New entity seeds 77/99: 7B 23/32 and 14B 25/32, versus historical v1 17/32 and 25/32. The six changed 7B verdicts in each set are correct final states rejected by the exact operation-count rule. This correction is exploratory and not independently human-adjudicated gold. New seeds are not new business families.

[Audited replay and grades](artifacts/outcome-audit.json) cover 256 records with zero additional model calls. Raw new-parameter records and the frozen private-grader hash are under [v4-validation](artifacts/v4-validation/plan.json). All historical verdicts remain in their original files.
