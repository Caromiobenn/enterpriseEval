# 真人复核表（尚未进行）

本表未由真人填写。已有 model-adjudications.json 是 Codex 模型裁决，不能转换成人工标签。

复核时先阅读任务要求与证据，写出个人判断及理由，再对照模型裁决；保留分歧，不以“与代码一致”为目标。

| 边界案例（两任务族均需查看） | 真人判断 pass/fail/invalid/needs_review | 理由或规则修订 | 审核人 / 日期 |
|---|---|---|---|
| duplicate_commit：终态未变但新编号重复提交 | 未审核 | 待填写 | 待填写 |
| missing_final_read：业务已完成但未读最终状态 | 未审核 | 待填写 | 待填写 |
| ambiguous_task：要求只写“适当处理” | 未审核 | 待填写 | 待填写 |
| clarified_task：明确合同后的参考解 | 未审核 | 待填写 | 待填写 |
| uncertain_prose：状态正确但文字表示不确定 | 未审核 | 待填写 | 待填写 |

同时建议复核 reference、alternative、surface_only、input_edit 各一例，检查评分器是否有共同设计偏差。若修订规则，应创建新版本并保留本轮标签与报告。
