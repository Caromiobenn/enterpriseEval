# 当前复跑入口（版本化实验）

建议先在本机 `python -m unittest -q`，再按 README 的离线审计命令复算现有证据。`campaign.py` 为保持原始实验可重建，运行输出仍包含历史 v1 grader；最终业务判分通过 `audit_outcomes.py` 单独生成，不能混淆两者。

双卡服务启动参数仍见下文。本轮新证据分别存于 `/mnt/enterprise-eval/enterpriseEval-auto-20260919/code-v2` 至 `code-v5`，旧 pilot 目录独立保留。新运行务必创建不存在的输出目录并显式传入未来截止时间；脚本内默认日期属于原实验冻结配置。

例如在包含冻结源码的独立新工作目录执行：

```bash
python campaign.py plan --folder artifacts/recheck-main --phase main --selected native-recovery \
  --inventory /mnt/enterprise-eval/enterpriseEval-20260919/model-sha256.txt
python campaign.py run --folder artifacts/recheck-main \
  --deadline "$(date -u -d '+1 hour' +%FT%T+00:00)"
python audit_outcomes.py --campaign artifacts/recheck-main --output artifacts/recheck-outcome-audit.json
```

先确认模型路径与清单一致、两个端口对应正确模型；每个模型串行，不同时启动多个批次争用同一 GPU。新批次与原批次分别报告，不覆盖失败。使用 Python 推理环境时将 `python` 换成下文的完整路径。

---

以下保留早期 pilot 的历史入口；它不等于后续版本化主矩阵。

# 服务器复跑入口

工作目录：`/mnt/enterprise-eval/enterpriseEval-20260919`。模型仍在原盘，推理环境为`/home/ubuntu/miniforge3/bin/python`；harnesslab自己的`.venv`不包含vLLM。Python3.12.8、vLLM0.7.3、torch2.5.1、transformers4.49.0为今天核验版本。完整文件哈希与启动参数已归档。

下面两个服务需各自占用一个终端。启动前确认8000/8001没有已有服务、对应GPU没有其他实验。保持仅监听回环地址，评测脚本在服务器本机访问。

```bash
CUDA_VISIBLE_DEVICES=0 /home/ubuntu/miniforge3/bin/python -m vllm.entrypoints.openai.api_server \
  --host 127.0.0.1 --port 8000 \
  --model /mnt/harnesslab-data/models/Qwen2.5-14B-Instruct-AWQ \
  --served-model-name qwen2.5-14b-instruct-awq \
  --quantization awq --dtype half --max-model-len 16384 \
  --gpu-memory-utilization 0.90 --enable-auto-tool-choice --tool-call-parser hermes
```

```bash
CUDA_VISIBLE_DEVICES=1 /home/ubuntu/miniforge3/bin/python -m vllm.entrypoints.openai.api_server \
  --host 127.0.0.1 --port 8001 \
  --model /mnt/harnesslab-data/models/Qwen2.5-7B-Instruct-AWQ \
  --served-model-name qwen2.5-7b-instruct-awq \
  --quantization awq --dtype half --max-model-len 16384 \
  --gpu-memory-utilization 0.85 --enable-auto-tool-choice --tool-call-parser hermes
```

等服务就绪后，在第三个终端创建**新的、不存在的**运行目录，只复制源码；不能删除旧产物来“重跑”。示例目录已存在时换名：

```bash
mkdir /mnt/enterprise-eval/recheck-001
cp /mnt/enterprise-eval/enterpriseEval-20260919/enterprise_eval.py /mnt/enterprise-eval/recheck-001/
cp /mnt/enterprise-eval/enterpriseEval-20260919/pilot_runner.py /mnt/enterprise-eval/recheck-001/
cd /mnt/enterprise-eval/recheck-001
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
ENTERPRISE_DIAGNOSTIC=1 /home/ubuntu/miniforge3/bin/python pilot_runner.py
```

脚本内的日期、seed和文件夹名是冻结协议标识；重复执行不代表发生在标识日期。外层新目录用于区分执行批次。诊断协议复跑并不保证确定性：温度0.6、服务并行与底层执行可能带来差异。

当前源码默认最简提示已增加终止分类与actor配置摘要，故不等于首轮原始代码。严格复现首轮实现应从`enterprise-pilot-evidence.tar.gz`取源码。诊断轮对应`enterprise-diagnostic-evidence.tar.gz`。两份归档均存于本机交付目录，服务器也保留各次产物。

正式实验前必须另行冻结模型文件、prompt、工具schema、判分代码、预算、任务划分、planned schedule和运行环境。此入口只供工程复查。
