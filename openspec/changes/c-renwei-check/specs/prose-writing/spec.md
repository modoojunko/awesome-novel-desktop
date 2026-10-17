# prose-writing Specification（delta）

## REMOVED Requirements

### Requirement: 选区变换（去AI味）

**Reason**：去AI味改写已拍板退役（2026-10-17）。`/write/polish` 端点、其去AI味口径（信息轮次化/场景换场/极简化/换骨架四策略与完成判定）、`quick_verdict` 快扫与右栏 `ai-polish` 按钮行随整链退役——人味检测（renwei-check）成为唯一检测引擎，人工边注改稿成为唯一改稿路径。场景扩写与压缩啰嗦段落已先期退役（c-retire-selection-transforms），本需求移除后选区变换不再保留任何端点。

**System Impact**：后端删除 `/write/polish` 端点、polish 提示词装配与 `quick_verdict`；`operation=polish` 记账随之终止；前端删除选区去AI味按钮与向导调用链（向导退役见 polish-wizard delta）。**不变**：润色等其余路径（若后续单独立项）、生成侧反AI结构红线注入与人味写法（本 capability 的生成时预防需求原样保留）、文风禁用词单源。prompts 私有仓的 `polish_text.prompt` 退役随跨仓 PR 同批执行（见 change design/tasks）。c-polish-v5-diagnostic-gate（未归档挂账，改写口径 v4.4→v5）随之撤销，不再实施。
