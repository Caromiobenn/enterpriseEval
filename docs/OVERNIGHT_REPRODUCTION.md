# 夜间评测实验复现教程（最终版）

2026-09-20 已收尾。新增 2,405 次正式验证，详见同目录《整夜实验最终报告》。以下步骤区分历史结果复核与新实验；不要覆盖冻结证据。

## 研究问题与数据划分

已有 offboarding 任务只用于开发和接口检查。新增 release（双重审批、部署、激活）与 fulfillment（库存预留、发货、库存守恒）为前瞻验证任务族。冻结后不得根据验证模型输出修改提示、工具或判分；如发现必须修复的缺陷，应保留旧版，把已观察任务降为开发用途，另建验证集。

验证来自两个合成语义任务族。参数变体、采样重复和模型条件不是独立任务族；还需要官方外部任务验证。

## 对照与复杂度

每个配对保持初始状态、记录数、依赖结构、工具定义和预算一致，只改变是否在第一次写入成功后丢失响应。工具返回超时但状态已变，模型需要查询或使用原 request_id 重试。不能重新使用新的请求 ID 重复提交。

提示因素独立交叉设置为 minimal / recovery。它检验显式恢复提示的效果，不能直接解释为某个复杂框架的总体效果。当前不同时改变深度、干扰数量或任务规模。

## 版本与运行

- API 分支：`exp/v6-deepseek-heldout-recovery`；`deepseek_study.py`。4 个开发单元，128 个验证单元，2 次重复；API 模型别名及返回标识保存，不承诺服务端版本永久固定。
- 本地分支：`exp/v7-local-heldout-recovery`；`local_heldout_study.py`。4 个开发单元，512 个验证单元，8 次重复；两张卡各运行一个 Qwen2.5 AWQ 模型。
- 两批共用冻结业务工具及判分源码；模型权重和服务实现不同，因此跨服务分数差不视为单因素因果效应。

创建计划与执行应使用新的输出目录。例如：

```bash
python deepseek_study.py test
python deepseek_study.py plan --folder artifacts/new-api-study
python deepseek_study.py run --folder artifacts/new-api-study
```

API key 只从环境变量读取，不能写进计划或 Git。该脚本设置 5 美元保守预算上限，保留每次响应和 usage；请求中断时不假定零费用，也不静默重试。请求进行中 ledger 的 uncertain=true 是预留状态；进程已终止仍为 true 才需要核对不确定计费。

本地服务分别绑定 127.0.0.1:8066 和 8067。运行本地计划前确认这两个端口的 model ID 正确。`local_heldout_study.py` 的截止时间是此次实验冻结值，复跑必须创建新版本、设置未来截止时间并重新生成计划，不能直接拿过期计划运行。

## 判分可信度与盲审

确定性测试覆盖两种合法调度顺序、超时同 ID 重试、未完成任务、错误副作用和重复提交。通过这些测试不等于判分绝对正确。

验证模型轨迹的自动标签延后生成。按预先规则选取每个条件分层的 variant=0、repeat=0，共每批 16 条。先读取匿名轨迹，根据任务要求和状态变化写出独立判断、证据和不确定项；保存标签后才能读取映射及自动判分，记录一致和不一致的原因。

审核者为 Codex 模型，不能写成“独立人工标注”或外部专家 gold。审核者知道任务设计，轨迹中的超时也可能暴露故障条件，因此只能声称隐藏模型身份、系统提示和自动标签，不能声称完全双盲。

主判分仅覆盖终态和唯一提交，不覆盖读取与最终验证义务。`audit_observations.py` 是解盲后加入的辅助审计，将义务操作化为首次成功写入前观察初始状态、最后成功写入后观察最终状态；保留主成绩不变。DeepSeek 128 条均满足，但这不能证明主判分完备。本地 409/512 满足两项辅助条件，58 条主成功中 56 条满足；不能把它冒充预注册主指标。

## 报告规范

分别报告每个任务族、模型、提示及故障条件的成功数/运行数、故障实际触发率、终止原因、token 与耗时。失败、截断和 HTTP 错误不得从分母删除。计划但未运行的单元列为缺失，不计成失败或成功。API 成本记录区分保守估计和账户真实扣费。

区分最终状态正确与指令遵循；例如结果正确但重复提交仍可能违反明确任务合同。不要事后放宽合同来提高同一验证集成绩。两任务族无法支撑广泛的总体模型排名或跨领域显著性主张。

## 公开基准

AppWorld 实际运行包为 **0.1.3.post1，Python 3.12.8，官方 data-0.1.0**。参考源码克隆固定 commit `42b5bcf3cd334fee33f0c37c02070a9f5807add5`，但它不是实际安装版本；不能混写。官方加密数据包 SHA256 为 `fd9f9608c2ec71ed0ac25c3633a738b9129a318a129e31230425b9188e508250`。服务器安装依赖已冻结，`pip check` 通过。

数据选择先于模型结果：官方 train 选 2 个开发任务，test_normal 选 16 个不同任务前缀。按 `SHA256(20260920:task_id)` 排序选择，不按成功率挑任务。开发失败全部保留：初始 API 运行输出截断，第二次触发上下文上限；本地 7B 重复生成截断，14B 提前结束且任务未完成。开发记录不能混进独立验证成绩。

本项目采用结构化 API actor：模型只能列出公开 API、读取参数文档、提交 JSON 参数；桥接器检查公开 API 白名单，使用固定表达式执行调用，不接受模型任意 Python。模型不能访问私有判分、参考解或宿主凭据。此配置与 AppWorld 官方代码生成 agent 不同，结果不能直接和官方排行榜比较；也不能称为完整操作系统沙箱。

冻结 actor 为最多 40 次模型请求、每次最多 1024 输出 tokens、temperature=0.2。提示要求一次最多两次工具调用（模型可能不遵守，不能误写为服务端强制限制）。完整历史保存到记录；请求达到上下文预算时，优先移除较早且较大的工具观察，保留最近两轮，显式提示观察已省略。每次真实请求视图另存，不能用完整历史冒充模型实际看见的上下文。超出硬预算仍终止并保留失败。

v8 正式计划：16 个任务 × 2 个 AWQ 模型 × 最多 8 次重复，共 256 次，已全部完成。先覆盖任务再做重复，同任务同 repeat 配对。截止时尚未运行列为缺失，超时或判分异常单列。计划数不能写作已完成数。

```bash
python appworld_plan.py --output selection.json
python appworld_batch.py plan --selection selection.json --root /path/to/appworld-root --output /path/to/new-batch
python appworld_batch.py run --root /path/to/appworld-root --output /path/to/new-batch
python analyze_appworld.py --folder /path/to/new-batch
```

复跑前必须把 `appworld_batch.py` 的本次固定截止时间修改为未来时间，再创建新计划；不要更改已冻结批次代码。AppWorld 需在其独立环境中安装应用并解包官方数据后才能运行。Windows 上仅运行分析器时使用 `python -X utf8`。

统计先在同任务相同 repeat 上配对，再计算任务内平均差和任务间宏平均。按任务重采样的区间只描述这个固定子集的组成敏感性；不是把 256 次当作 256 个独立任务，也不支持总体模型排名。原始任务、解密应用与衍生轨迹保持服务器私有；公开时只导出不含题目、工具内容、私有测试细节的汇总。

## 安装与本地推理服务

AppWorld 使用独立的 Python 3.12 环境；缓存与数据放到数据盘。以下是新环境示例，已有环境无需重复安装：

```bash
python3.12 -m venv /mnt/enterprise-eval/appworld-new-venv
source /mnt/enterprise-eval/appworld-new-venv/bin/activate
export PIP_CACHE_DIR=/mnt/enterprise-eval/pip-cache
pip install 'appworld==0.1.3.post1'
export APPWORLD_ROOT=/mnt/enterprise-eval/appworld-new-data
mkdir -p "$APPWORLD_ROOT"
cd "$APPWORLD_ROOT"
appworld install
appworld download data
pip check
pip freeze > installed-requirements.txt
```

本轮因官方下载超时，实际使用从官方源取得的 81 个 Linux wheels 离线安装，并用包自带工具解包已校验 SHA256 的官方 bundle；不是换用未知数据镜像。安装锁定清单以服务器实际环境为准。

vLLM 服务用独立推理环境，两卡分别执行以下命令。端口须与计划一致；当前旧服务已停止，启动新服务前确认 GPU 未被其他任务使用：

```bash
CUDA_VISIBLE_DEVICES=0 /home/ubuntu/miniforge3/bin/python -m vllm.entrypoints.openai.api_server \
  --host 127.0.0.1 --port 8066 \
  --model /mnt/harnesslab-data/models/Qwen2.5-14B-Instruct-AWQ \
  --served-model-name qwen2.5-14b-instruct-awq --quantization awq --dtype half \
  --max-model-len 16384 --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice --tool-call-parser hermes
```

第二张卡将 `CUDA_VISIBLE_DEVICES` 改为 1、端口改为 8067、模型路径和 served-model-name 改为对应 7B、显存比例改为 0.85。实际 vLLM 为 0.7.3，支持本轮使用的 `guided_json`。

## 按分支选择实验，而不是从最新版误跑旧矩阵

| 版本 | 分支 | 冻结 actor / 批次依据 | 实际验证 |
|---|---|---|---:|
| v6 | exp/v6-deepseek-heldout-recovery | 2e7a4dc；以 plan 内哈希为准 | 128 |
| v7 | exp/v7-local-heldout-recovery | 1ab1e49；以 plan 内哈希为准 | 512 |
| v8 | exp/v8-appworld-external | actor 8ed425a、批次 4569b88；后续提交为分析/审核 | 256 |
| v9 | exp/v9-appworld-discovery-guidance | 冻结 plan 的三个源码哈希；后续 f03610a 含正控制/分析 | 1,280 |
| v10 | exp/v10-appworld-constrained-protocol | actor 6067903；9836f06 更新分析器 | 229 |

各分支末端可能包含后续报告或分析提交，**逐文件哈希比把整个分支末端当成 actor 版本更精确**。新实验先创建独立 checkout，修改固定截止日期并生成新 plan；新代码哈希必须与新计划一致。冻结后修改 actor 应另建版本，而不是绕过断言。

v9 用 `appworld_plan.py --validation-count 40 --exclude-selection /path/to/v8-selection.json --output /path/to/v9-selection.json`，排除 v8 所有前缀。v10 用 `--split test_challenge --validation-count 24`，另核验与前两批前缀不重叠。开发只用 train，先完成接口检查再冻结验证。原 batch 默认日期已经过期，**直接运行不会产生新实验**。

v10 最多 768 单元，已运行 229、539 未启动。完成 24 任务覆盖后继续重复，截止时间与模型速度导致重复数不齐；分析器只比较完整匹配对。constrained JSON 同时改变语法、提示与观察消息表示，不是单独解码算法的因果试验。

## 复核已完成证据

在本地项目根目录执行，不需要 API key 或 GPU：

```bash
python -X utf8 enterpriseEval/deepseek_study.py test
python -X utf8 enterpriseEval/analyze_heldout.py --folder deliverables/2026-09-20-overnight/deepseek-heldout-authfixed-20260919 --blind-labels enterpriseEval/reviews/deepseek-blind-20260920.json
python -X utf8 enterpriseEval/analyze_heldout.py --folder deliverables/2026-09-20-overnight/local-heldout-20260919 --blind-labels enterpriseEval/reviews/local-blind-20260920.json
python -X utf8 enterpriseEval/summarize_overnight.py --root deliverables/2026-09-20-overnight
```

预期：14 项检查通过，128 与 512 条回放一致，各 16 条匿名审核；总新增验证 2,405、外部前缀 80。`status.json` 中历史 `blind_review_pending=true` 是 runner 完成时的快照，最终审查状态看 reviews 文件与 postreview-analysis，不回写旧快照。

AppWorld 原始记录只在服务器：

- v8：`/mnt/enterprise-eval/appworld-pilot-20260920/frozen-validation`
- v9：`/mnt/enterprise-eval/appworld-v9-20260920/validation`
- v10：`/mnt/enterprise-eval/appworld-v10-20260920/validation`

使用最新版 `analyze_appworld.py --folder <批次目录>`，它核对任务/模型/条件/actor 哈希、显式列出缺失，并只输出不含任务正文的 aggregate-analysis。不能把原始 record、参考解、判分测试详情上传到公共仓库。官方数据许可与使用条款仍适用。

两个官方 train 参考解的直接执行控制均通过；经桥接器回放为 1/2 通过，另一个 145 调用参考序列触发 100 次环境上限。控制不计为模型运行，也不将参考解用于测试任务。

## 长任务监控与收尾

本轮按用户要求每小时检查，监控不发送常规通知；后台队列自主接续，09:00 停止启动新单元，09:30 仅按 PID 和创建时间停止本轮服务。09:48 已核验进程退出，停止记录在 final-audit/deadline-stop.json。

本次 GPU CSV 仅保留到 01:01，是监控缺陷。今后采样器应作为独立持久服务运行，每次小时检查同时验证文件最后更新时间；进程存在不能代替采样新鲜度。对已发生的缺失不插值补造利用率。批次启动/结束记录证明约 9 小时 24 分执行跨度，不能证明连续满载十小时。

API 主批次费用上界 $2.4466398，外部开发试跑 $0.2760846，总上界 $2.7227244，不是实际账单。未购买新资源，云实例保留。
