# 执行协议干预与 Judge 证据压力实验（2026-10-16—17）

这是已完成实验的公开代码与证据子集。执行器是自写工具调用循环，未使用 Deep Agents，未修改模型权重。

## 阅读顺序

1. [报告](REPORT.md)：正式批 1,536 条与新增参数批 9,216 条分别报告，另有 768 次 Judge 评测。
2. [真实案例](案例解读.md)：修复、退化和剩余失败。三个案例为事后解释性选择，不能代替总体统计。
3. [冻结执行源码](evidence/recovery-study-20261016/code/recovery_study.py)：`make_case → RequestPolicy.transform → run_episode → Environment.call → replay`。
4. [Judge 源码](evidence/recovery-study-20261016/code/judge_stress_study.py)：证据视图、输出解析与错误分解。
5. [已核验统计](verified-analysis.json)：全量本地重放核验与分层统计的保存结果。

## 无 GPU 复现（从仓库根目录执行）

```bash
python -m unittest -v test_recovery_study test_judge_stress_study
python recovery_study.py selftest
python studies/recovery-20261016/offline_demo.py
python studies/recovery-20261016/replay_case.py --case rescue --arm raw
python studies/recovery-20261016/replay_case.py --case rescue --arm namespace
```

还可将 `--case` 改为 `regression` 或 `remaining_failure`，`--arm` 改为 `semantic`。这些命令不调用模型；重放检查保存的工具动作与环境状态，不能验证模型输出可被再次生成。

## 结果与边界

新增参数批 7B raw / namespace 为 74/1536 与 1512/1536；14B 为 248/1536 与 521/1536。semantic 未显示稳定额外收益。固定48条源轨迹的 Judge 评测中，7B direct 从完整证据改为精简证据时，误拒绝由2/29增至9/29。

操作命名空间解决合成环境全局请求ID缓存的跨操作冲突；语义去重依赖每项业务操作只允许一次的任务合同。这是执行层条件收益，不是模型能力提升。重复运行不是独立任务；环境判分不是人类金标。只涉及两类合成环境和一个 AWQ 模型家族，不代表生产部署或通用故障恢复能力。

## 证据发布范围

公开：冻结源码、正式Agent及扩展计划、统计结果、图、三个案例（各含三种执行条件，共9条轨迹）、本目录逐文件SHA256清单。

未公开：完整10,752条Agent记录、768条Judge记录、服务日志与模型权重。完整归档在本地交付时核验了11,647个文件，归档SHA256为 `2cc36b790e0280f01d8e67cb5b4f71c1b26e4afa3e0b171084f88d88e13dd47f`。这是历史核验结果；仅凭公开子集无法独立重算总体统计。

冻结计划包含历史截止时间与当时的源码哈希，不应直接启动为新实验。新推理需要独立输出目录、可用模型服务、新的时间预算和重新冻结的计划；不覆盖旧结果。根目录脚本便于开发，冻结快照用于证据重放。
