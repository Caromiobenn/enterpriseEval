# enterpriseEval — v0 tool-call diagnostic

This branch preserves the second 8-run development protocol: an explicit tool-use/recovery prompt and `parallel_tool_calls=false`. Full source, protocol, model responses, state and usage are retained.

| Protocol | 7B AWQ | 14B AWQ |
|---|---:|---:|
| Initial minimal actor | 2/4 | 0/4 |
| Diagnostic actor | 0/4 | 2/4 |

These results are from one workflow template, one entity seed, depths 4/8, clean/fault, one sample per cell. They demonstrate protocol sensitivity, not a model ranking. The diagnostic service sometimes still returned multiple calls. Fault recovery claims require an actually activated fault.

- `artifacts/live-diagnostic-20260919/`: second protocol and full evidence.
- `artifacts/live-pilot-20260919/`: historical first-protocol evidence; its original source is on `exp/v0-minimal-pilot`.
- `artifacts/cpu-smoke-20260919/`: 72 parameter variants and 216 invalid-state rejections, not independent business tasks.
- Run `python -m unittest -v` for 10 contract tests.

The actor records truncation and unparsed tool-shaped text separately. Migration remains a decision function; actual multi-workflow migration experiments are on later branches. No process sandbox, formal generalization claim or cost-reduction result is implied.
