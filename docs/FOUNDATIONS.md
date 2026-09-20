# enterpriseEval：核心依据与实验边界

2026-09-20 实验状态补充：本文件保留 09-19 文献审计与当时边界；后续已新增发布/履约两个合成任务族及 AppWorld 官方纯文本子集实验，见 [夜间最终报告](OVERNIGHT_REPORT.md)。未完整复现论文，原有“下一阶段”措辞属于历史计划，不代表当前未运行。

核验日期：2026-09-19。定位为**纯文本基础模型的评测方法实验**，研究协议偏差、状态判分有效性、版本变化及重复评测成本。业务环境只是可控制的测量工具，不以交付企业应用为目标；不涉及图片、视频、GUI或多模态模型。

## 选文标准

核心依据优先选择有正式出版记录、可检查方法与代码、奖项或实际采用证据的工作；企业经验只引用官方技术文章，并与同行评审论文分开标注。近期arXiv候选不因“新”而进入核心依据。没有核查引用数，不编造引用量或“领域第一”；会议级别与团队名气也不能代替具体方法审查。

此前25篇论文与12篇技术文章是广泛检索地图，**不代表25篇都通过了同等强度的质量筛选**。当前实验不依赖TRACE、EvoBench、EvoBrowseComp、RoadmapBench及其他近期预印本的效果主张。这些只保留为待评价的线索，不作为实验或简历的权威背书。

## 核心论文与采用证据

| 文献 | 真实出版／影响证据 | 本项目采用的部分 | 未复现的部分 |
|---|---|---|---|
| **AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents** | [ACL 2024正式论文](https://aclanthology.org/2024.acl-long.850/)；[会议官方Best Resource Paper Award](https://2024.aclweb.org/program/best_papers/) | 以环境终态和附带影响判分；允许不同合法执行顺序；显式保护无关记录 | 未运行完整AppWorld，未复制其应用生态；本项目不能称AppWorld复现 |
| **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains** | [原论文](https://arxiv.org/abs/2406.12045)；[Sierra官方方法介绍](https://sierra.ai/blog/benchmarking-ai-agents)；[Anthropic使用τ-bench做工具消融](https://www.anthropic.com/engineering/claude-think-tool) | 目标数据库状态、工具及业务约束、重复运行可靠性 | 不含用户模拟器；两次重复不足以给稳定高阶可靠性估计；正式身份已核实为 ICLR 2025，见下方更正 |
| **Dynabench: Rethinking Benchmarking in NLP** | [NAACL 2021正式论文](https://aclanthology.org/2021.naacl-main.324/) | 固定静态集合饱和后需要持续构建挑战；开发反馈与验证必须分开 | 当前未实现完整人机对抗收集；参数增大本身不等于有质量的动态难题 |
| **AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents** | [NeurIPS 2024 Datasets and Benchmarks正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/877b40688e330a0e2a3fc24084208dfa-Paper-Datasets_and_Benchmarks_Track.pdf) | 将最终成功与过程诊断分开，失败不能只看单一总分 | 未复现其多环境评测或人工验证的progress metric；借鉴纯文本工具/状态分析 |
| **tinyBenchmarks: evaluating LLMs with fewer examples** | [ICML 2024正式论文与原始方法入口](https://proceedings.mlr.press/v235/maia-polo24a.html) | 小样本评测经济性必须相对于明确目标分布验证 | 本轮不拟合IRT、不声称复现tinyBenchmarks或少量样本可普遍替代全库 |

AppWorld的会议奖项和τ-bench被其他企业实际用于模型评测，是直接可检查的影响证据。其余会议论文作为方法背景，不把仅有录用记录夸大为引用量证明。已读相关方法部分不等于完成全文复现。

## 2025–2026 年正式会议补充与更正

2026-09-19 再核验：原清单并非全部是 2024 年论文，但漏标了 τ-bench 的正式会议身份，也缺少 2026 年正式会议工作。以下补充进入核心阅读路线；这是实验完成后的文献审计，不倒推声称它们已指导此前运行。

| 文献 | 核验入口与影响证据 | 下一阶段采用方式与边界 |
|---|---|---|
| **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains** | [ICLR 2025 正式论文集](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html)；上表 Sierra / Anthropic 官方使用证据 | 更正上表“未在此声称会议录用”的旧标注：已核实 ICLR 2025。阅读目标状态验证与 pass^k；区分预印本 2024 和会议 2025，不能把重复两次包装为稳定的高阶可靠性估计。 |
| **Establishing Best Practices in Building Rigorous Agentic Benchmarks (ABC)** | [NeurIPS 2025 Datasets and Benchmarks 正式论文](https://papers.nips.cc/paper_files/paper/2025/hash/f316275b44ee2de533102913828a8107-Abstract-Datasets_and_Benchmarks_Track.html)；论文对既有基准进行具体判分审计，HAL 论文亦引用该工作 | 将任务歧义、奖励缺漏、合法替代解和捷径检查纳入下一轮判分审计；先冻结规范，再独立盲审。论文报告的问题针对其审计版本，不能直接断言当前最新版仍有同样漏洞；尚未完整复现 ABC。 |
| **Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation (HAL)** | [Princeton 官方项目页明确宣布 ICLR 2026 录用](https://hal.cs.princeton.edu/)；[OpenReview 论文正文](https://openreview.net/pdf?id=vUaY1t64ZZ)。官方项目提供实际多基准运行、成本与轨迹；不据此编造高被引排名 | 参考模型 × scaffold × benchmark 的分离分析、成本记录和轨迹审计；只接入纯文本任务。下一轮先选一个因素做配对比较，报告完整 token、失败和成本缺失；不复现其大规模集群，也不将 HAL 后续可靠性面板全部当作原论文结果。 |

阅读顺序修正为：AppWorld（ACL 2024，状态与合法解）→ τ-bench（ICLR 2025，重复可靠性）→ ABC（NeurIPS 2025，判分有效性）→ HAL（ICLR 2026，可复现与成本比较）→ Harbor Continuous Benchmarks（官方工程资料，版本迁移）。2024 基础论文保留，2025–2026 工作补上评测方法前沿；会议录用、工程采用和长期学术影响是不同证据。

下一轮先产出冻结的判分规范、独立轨迹审核记录和公开纯文本任务小试，再决定扩大实验。当前结果仍是两个合成任务族上的探索性证据；这次文献更新不改变已有数字，不触发 GPU 重跑。

## 企业官方技术依据

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：区分task/trial/transcript/outcome，审查真实轨迹，隔离每次运行，维护判分与任务集合。本项目据此保留原始响应和终态，并将正常结束与任务成功分开。
- [Anthropic — The “think” tool](https://www.anthropic.com/engineering/claude-think-tool)：同一模型搭配工具及提示变化可能影响评测结果。本项目比较明确记录的协议条件，不把harness变化归因为基础模型权重提升；没有复刻该文的think机制或成绩。
- [Sierra — Benchmarking AI agents](https://sierra.ai/blog/benchmarking-ai-agents)：以数据库目标状态检查任务完成与可靠性。本项目借鉴其状态验证思路，保留工具故障是否真正触发的记录。

- [Terminal-Bench / Harbor — Continuous Benchmarks](https://www.tbench.ai/news/continuous-benchmarks)：官方维护者明确提出按变化复用、重判或重跑，并介绍任务版本管理。本项目的三分法直接参考该工程实践，补充私有grader反馈隔离、产物充分性和可重放证据检查；不宣称原创算法，也没有复现完整Harbor系统。
- [Anthropic — Quantifying infrastructure noise in agentic coding evals](https://www.anthropic.com/engineering/infrastructure-noise)：资源与执行配置会改变评测结果。本轮将输出预算作为显式诊断变量；不搬用其资源实验的提升比例。

这些官方文章提供工程方法依据，不替代独立实验，也不保证本项目得到同样结果。Terminal-Bench/Harbor属于基准维护团队的官方技术资料，与企业文章分别识别。

## 具体实验与基础模型岗位的关系

1. **协议敏感性**：固定模型权重与任务，比较native tool calling、显式恢复提示、约束JSON动作协议。三者均按自己的配置报告；提示和传输格式共同变化的比较不能称单因素因果结果。
2. **判分有效性**：同一份产物由仅检查目标状态的刻意不完整grader与完整不变量grader重判。区分真实运行上的分数变化与人工构造错误产物的检测能力。刻意不完整grader是受控方法验证，不是发现了外部基准漏洞。
3. **可靠性**：故障条件成对设置；先统计故障是否触发，再统计触发后的任务成功、重复副作用和成本。运行重复不能代替语义独立任务。
4. **版本迁移**：证明仅修改私有grader时可复用哪些产物；改变actor可见条件时实际重跑。对相同产物重判要求确定性一致，对新随机运行只比较分布与差异，不要求逐条相等。

## 必须保留的限制

当前只有两个合成业务家族。改名、金额和记录数量变体都不能当作多个独立业务根，也不能证明跨域泛化。短工作流的动作数不是人类任务时长；本轮不声称建立长程能力标尺。两个量化模型不足以做稳定的能力正交性／IRT研究。

下一阶段外部效度优先接入冻结版本的AppWorld或τ-bench纯文本子集，再讨论更长任务和难度扩展；不以追逐不确定的新预印本代替有效对照。当前三小时实验是上述方法的小型可审计验证，不是完整论文复现或论文级新颖性证明。
