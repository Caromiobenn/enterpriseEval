# enterpriseEval：核心依据与实验边界

核验日期：2026-09-19。定位为**纯文本基础模型的评测方法实验**，研究协议偏差、状态判分有效性、版本变化及重复评测成本。业务环境只是可控制的测量工具，不以交付企业应用为目标；不涉及图片、视频、GUI或多模态模型。

## 选文标准

核心依据优先选择有正式出版记录、可检查方法与代码、奖项或实际采用证据的工作；企业经验只引用官方技术文章，并与同行评审论文分开标注。近期arXiv候选不因“新”而进入核心依据。没有核查引用数，不编造引用量或“领域第一”；会议级别与团队名气也不能代替具体方法审查。

此前25篇论文与12篇技术文章是广泛检索地图，**不代表25篇都通过了同等强度的质量筛选**。当前实验不依赖TRACE、EvoBench、EvoBrowseComp、RoadmapBench及其他近期预印本的效果主张。这些只保留为待评价的线索，不作为实验或简历的权威背书。

## 核心论文与采用证据

| 文献 | 真实出版／影响证据 | 本项目采用的部分 | 未复现的部分 |
|---|---|---|---|
| **AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents** | [ACL 2024正式论文](https://aclanthology.org/2024.acl-long.850/)；[会议官方Best Resource Paper Award](https://2024.aclweb.org/program/best_papers/) | 以环境终态和附带影响判分；允许不同合法执行顺序；显式保护无关记录 | 未运行完整AppWorld，未复制其应用生态；本项目不能称AppWorld复现 |
| **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains** | [原论文](https://arxiv.org/abs/2406.12045)；[Sierra官方方法介绍](https://sierra.ai/blog/benchmarking-ai-agents)；[Anthropic使用τ-bench做工具消融](https://www.anthropic.com/engineering/claude-think-tool) | 目标数据库状态、工具及业务约束、重复运行可靠性 | 不含用户模拟器；两次重复不足以给稳定高阶可靠性估计；未在此声称会议录用 |
| **Dynabench: Rethinking Benchmarking in NLP** | [NAACL 2021正式论文](https://aclanthology.org/2021.naacl-main.324/) | 固定静态集合饱和后需要持续构建挑战；开发反馈与验证必须分开 | 当前未实现完整人机对抗收集；参数增大本身不等于有质量的动态难题 |
| **AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents** | [NeurIPS 2024 Datasets and Benchmarks正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/877b40688e330a0e2a3fc24084208dfa-Paper-Datasets_and_Benchmarks_Track.pdf) | 将最终成功与过程诊断分开，失败不能只看单一总分 | 未复现其多环境评测或人工验证的progress metric；借鉴纯文本工具/状态分析 |
| **tinyBenchmarks: evaluating LLMs with fewer examples** | [ICML 2024正式论文与原始方法入口](https://proceedings.mlr.press/v235/maia-polo24a.html) | 小样本评测经济性必须相对于明确目标分布验证 | 本轮不拟合IRT、不声称复现tinyBenchmarks或少量样本可普遍替代全库 |

AppWorld的会议奖项和τ-bench被其他企业实际用于模型评测，是直接可检查的影响证据。其余会议论文作为方法背景，不把仅有录用记录夸大为引用量证明。已读相关方法部分不等于完成全文复现。

## 企业官方技术依据

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：区分task/trial/transcript/outcome，审查真实轨迹，隔离每次运行，维护判分与任务集合。本项目据此保留原始响应和终态，并将正常结束与任务成功分开。
- [Anthropic — The “think” tool](https://www.anthropic.com/engineering/claude-think-tool)：同一模型搭配工具及提示变化可能影响评测结果。本项目比较明确记录的协议条件，不把harness变化归因为基础模型权重提升；没有复刻该文的think机制或成绩。
- [Sierra — Benchmarking AI agents](https://sierra.ai/blog/benchmarking-ai-agents)：以数据库目标状态检查任务完成与可靠性。本项目借鉴其状态验证思路，保留工具故障是否真正触发的记录。

这些博客提供工程方法依据，不替代正式实验，也不保证本项目得到同样结果。有关版本迁移的reuse/regrade/rerun划分是本项目对可复用证据条件的工程化设计，不冒充上述论文的原始算法。

## 具体实验与基础模型岗位的关系

1. **协议敏感性**：固定模型权重与任务，比较native tool calling、显式恢复提示、约束JSON动作协议。三者均按自己的配置报告；提示和传输格式共同变化的比较不能称单因素因果结果。
2. **判分有效性**：同一份产物由仅检查目标状态的刻意不完整grader与完整不变量grader重判。区分真实运行上的分数变化与人工构造错误产物的检测能力。刻意不完整grader是受控方法验证，不是发现了外部基准漏洞。
3. **可靠性**：故障条件成对设置；先统计故障是否触发，再统计触发后的任务成功、重复副作用和成本。运行重复不能代替语义独立任务。
4. **版本迁移**：证明仅修改私有grader时可复用哪些产物；改变actor可见条件时实际重跑。对相同产物重判要求确定性一致，对新随机运行只比较分布与差异，不要求逐条相等。

## 必须保留的限制

当前只有两个合成业务家族。改名、金额和记录数量变体都不能当作多个独立业务根，也不能证明跨域泛化。短工作流的动作数不是人类任务时长；本轮不声称建立长程能力标尺。两个量化模型不足以做稳定的能力正交性／IRT研究。

下一阶段外部效度优先接入冻结版本的AppWorld或τ-bench纯文本子集，再讨论更长任务和难度扩展；不以追逐不确定的新预印本代替有效对照。当前三小时实验是上述方法的小型可审计验证，不是完整论文复现或论文级新颖性证明。
