# 可重建结果表

下表由 `python results_report.py` 从完整计划与原始产物重建。v0只看目标，v1含过严操作数约束，v2-outcome区分无害冗余与业务错误。

| 批次 | 模型 | 运行数 | v0目标 | v1历史 | v2-outcome | usage完整 |
|---|---|---:|---:|---:|---:|---:|
| v2-dev | 14B | 12 | 10 | 10 | 10 | 12 |
| v2-dev | 7B | 12 | 12 | 9 | 10 | 12 |
| v2-main | 14B | 32 | 28 | 28 | 28 | 32 |
| v2-main | 7B | 32 | 23 | 16 | 22 | 32 |
| v3-extension | 14B | 16 | 0 | 0 | 0 | 16 |
| v3-extension | 7B | 16 | 0 | 0 | 0 | 15 |
| v4-validation | 14B | 32 | 25 | 25 | 25 | 32 |
| v4-validation | 7B | 32 | 23 | 17 | 23 | 32 |
| v5-budget | 14B | 16 | 6 | 6 | 6 | 16 |
| v5-budget | 7B | 16 | 0 | 0 | 0 | 15 |
| full_rerun_control | 14B | 32 | 28 | 28 | 28 | 32 |
| full_rerun_control | 7B | 32 | 23 | 16 | 22 | 32 |
| actor_change_requires_rerun | 14B | 4 | 4 | 4 | 4 | 4 |
| actor_change_requires_rerun | 7B | 4 | 4 | 3 | 3 | 4 |

所有分数仅对应这两个合成业务家族。开发、锚点、新参数验证、规模扩展和预算诊断分别解释，不合成模型总榜。usage不完整的运行不能当作零成本。

完整分层信息、终止类型、故障触发与配对核对见 [final-results.json](../artifacts/final-results.json)。
