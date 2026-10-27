## 1. prompts 仓（分支 c-style-distill-full）

- [ ] 1.1 新模板 `style_learn_extract.prompt`：system＝拆书编辑角色＋逐字铁律＋JSON 契约（role ≤40 字／rules ≤10 条 how ≤60 字／craft ≤8 条／taboo→rules 提示／examples 0–6 条逐字原文段 ≤200 字，对话＋叙述各至少一条，禁止自造改写）；user＝{sample_text}；纳管注释经 sync.py CURATED 登记（TIER max）
- [ ] 1.2 `python3 sync.py all`＋lint 对拍；本仓 .venv `pytest tests/` 全绿（新增模板 pin 测试：逐字契约锚点）

## 2. C端后端

- [ ] 2.1 `settings/ai_router.py`：step4 端点（member 门控＋模型就绪依赖同三步）；样本由请求重供（body.text 或文件/章节，复用 `_assemble_distill_samples`；**text 在 step4 只作供给、MUST NOT 触发清空重启**；无 step1 产物→400）；调用 `style_learn_extract` 模板解析 JSON，产物写 `style-quant.draft.step4`（role/rules/craft/taboo→rules 行/examples）
- [ ] 2.1b `PromptPackMissing` 降级：包缺模板→结构化错误（非 500）＋更新提示词包文案；step4 force 重提（保留 step1–3）
- [ ] 2.2 draft 兼容：存量 draft 无 step4 产物→续跑补跑；粘贴重启清空含 step4；「不像，再学一次」只重跑 step3 不动 step4 产物
- [ ] 2.3 后端测试：step4 契约钉（member 403/模型未就绪/502 可重试/解析坏 JSON 502/**text 不清空 draft**/无 step1 400/**旧包缺模板降级**/force 重提）、draft 续跑四态（存量补跑/粘贴清空/重学不清 step4/独立重试）、样例形状收敛（超限截断）

## 3. C端前端

- [ ] 3.1 蒸馏流 UI：进度步数三→四（复位/续跑/在飞语义沿既有钉子；distillStep union 扩位）；确认卡新增文字层两段——三区草稿编辑器（身份一句＋规则 ListEditor＋手法 ListEditor，taboo 已转「避免…」行）＋示范段只读列表（可删条目）＋「重新提取」入口＋旧包降级文案
- [ ] 3.2 分段落卡交互：基线「落卡」照旧；文字层「采纳到文风设定」（三区/示范段各自勾选采纳或弃采）→ 采纳前回读文风 KV 合并（D4 同款）→ put_style 白名单 PUT（三区替换＋style_samples ≤6 替换）→ ChangeReceipt 回执撤销；未采纳段零写回；**采纳后表单态同步＋脏快照重基线**（防后续保存回踩/误报脏）
- [ ] 3.3 前端测试：进度四步钉（存量补跑/粘贴复位）、分段采纳三态（全采纳/只采纳示范段/全弃零写回）、回执撤销恢复、防丢词（未保存禁用词＋采纳合并）、**采纳后脏基线重置（后续保存不回踩）**、无来源标记差异（style-samples 组呈现同形态）
- [ ] 3.4 原型 style-settings.html 确认卡补文字层两段演示＋ADJUSTMENTS 登记；design:lint 过（不触共享段）

## 4. 验证与交付

- [ ] 4.1 全量验证：后端 pytest＋ruff；前端 vitest --coverage＋tsc；prompts 仓 pytest
- [ ] 4.2 openspec validate；rebase 基线确认（main 在 e330e8f2 之后可能再动，动手前 fetch）
- [ ] 4.3 双仓 PR（prompts #新＋C端 #新），openspec sync delta＋归档随实现 PR；CI 绿后合入
- [ ] 4.4 发提示词包（max 77→78；min_client 0.39 不 bump）＋五步链＋双冒烟＋tag/Release 台账
- [ ] 4.5 真机验收：粘贴参考书文本学全三层→逐段采纳/弃采→示范段入文风页→写正文看贴库；撤销链回放
- [ ] 4.6 挂账转立项：量化段提示词效果 A/B 实证（同书同章纲开关对比：程序统计收敛度＋盲评）
