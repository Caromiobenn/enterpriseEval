# enterpriseEval

纯文本基础模型评测方法原型：研究判分偏差、输出预算影响及评测版本迁移。两个合成业务家族为离职交接和发票核对；不涉及多模态，不声称完整复现大型基准或证明通用长程能力。

2026-09-19 已完成本轮 **292 次真实模型 episode**（含 4 次接口 probe），另保留此前 16 次 pilot。288 份主要阶段记录通过逐步工具重放，28 项自动测试通过。运行数量不是独立任务数量。

## 最重要的观察

- **判分过度约束会改变比较方向。** 主集和新参数集各有 6 份正确终态被旧操作数规则拒绝。在固定 8 单元提示对照上，旧判分为恢复提示 6/8、最简提示 7/8；修订后分别为 8/8、7/8。修订是探索性的，不是外部专家 gold 标注或提示优劣的统计结论。
- **规模扩展的 0 分包含预算影响。** 规模 8 的 512-token 输出上限下为 0/32，23 次截断；仅改为 2048 后为 6/32，0 次截断。其余仍失败，总 token 预算不匹配，不能称模型能力提升。
- **迁移成本真实计量。** 保存产物的私有重判无需新增推理；64 次原条件重跑消耗 741,657 tokens，其成功标签与存档一致。改变提示、任务或预算的条件全部重跑。

| 条件（修订后的 v2-outcome 判分） | 7B AWQ | 14B AWQ |
|---|---:|---:|
| 主矩阵，规模 2/4 | 22/32 | 28/32 |
| 新参数验证，规模 2/4 | 23/32 | 25/32 |
| 规模 8，输出上限 512 | 0/16 | 0/16 |
| 同条件输出上限 2048 | 0/16 | 6/16 |

这是两个相关合成家族上的条件计数，不是模型总榜。旧 summary 保留历史 v1 判分；修订结果以 `final-outcome-audit.json` 和 `final-results.json` 为准，原始文件未回写。

## 阅读顺序

1. [实验报告](docs/REPORT.md)：完成范围、正负结果、成本与限制。
2. [核心依据与质量审计](docs/FOUNDATIONS.md)：AppWorld、τ-bench、Dynabench、AgentBoard、tinyBenchmarks 及官方技术文章；明确哪些没有复现。
3. [实验方法](docs/EXPERIMENT_METHODS.md)与[可重建结果表](docs/RESULTS.md)。
4. [真实轨迹案例](docs/CASE_STUDIES.md)与[面试答辩](docs/INTERVIEW_DEFENSE.md)。

版本迁移直接参考 [Terminal-Bench/Harbor Continuous Benchmarks](https://www.tbench.ai/news/continuous-benchmarks)。资源配置作为测量变量的依据包括 [Anthropic 官方文章](https://www.anthropic.com/engineering/infrastructure-noise)。近期未充分验证的预印本不作为本方案前提，不宣称原创这些已有方法。

## 离线复核

核心代码只依赖 Python 标准库；无需模型服务即可测试和重建表格：

```bash
python -m unittest -q
python results_report.py
python audit_outcomes.py --campaign artifacts/v2-main --output local-main-audit.json
```

审计输出路径应不存在，避免覆盖旧证据。完整 288 条离线审计：

```bash
python audit_outcomes.py --campaign artifacts/v2-dev --campaign artifacts/v2-main --campaign artifacts/v3-extension --campaign artifacts/v4-validation --campaign artifacts/v5-budget --migration artifacts/v3-migration --output local-full-audit.json
```

[服务器复跑说明](SERVER.md)列明模型、端口、未来截止时间和新输出目录。模型文件清单见 [model-sha256.txt](artifacts/model-sha256.txt)，运行栈见 [runtime-info.json](artifacts/runtime-info.json)。当前批次结束后已停止本轮推理服务，云实例保留。

## 实验分支

- `exp/v0-minimal-pilot`：最早 8 次工程运行。
- `exp/v0-toolcall-diagnostic`：独立 8 次接口诊断。
- `exp/v1-versioned-workflows`：两个业务环境与 4 次失败 JSON probe。
- `exp/v2-strict-action-protocol`：24 次开发比较、64 次冻结主矩阵。
- `exp/v3-evidence-migration`：72 次迁移对照、32 次规模扩展。
- `exp/v4-outcome-grader`：判分修订、64 次新参数验证。
- `exp/v5-output-budget`：32 次配对输出预算诊断与最终审计。

所有失败均保留。先扩展独立业务家族、官方纯文本子域和人工判分复核，再讨论跨域结论；更多随机 ID 不能补足外部效度。
