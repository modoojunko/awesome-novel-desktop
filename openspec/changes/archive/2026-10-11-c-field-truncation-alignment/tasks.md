# Tasks: c-field-truncation-alignment

## 1. 生成侧钳位（终版：内容字段完整直通）

- [x] 1.1 `chapters/ai_plan._fit`：plot/obstacle/ending 直通（limit=None）；title/why/gap 保列宽
- [x] 1.2 `chapters/ai_plot._sanitize_versions`：条目不截断，「已截到最后一个句号」告警退役；计数预算保留
- [x] 1.3 `chapters/schemas.normalize_plot_items`：单条不截（只保 12 条）；`clip_sentence`/`clip_plot_item` 转可选工具（生产链零调用）
- [x] 1.4 `volumes/ai_plan`：`_sanitize_plans`（spine/conflict/ending/antagonist_line）与 `_sanitize_expand`（summary/conflict/ending/antagonist_line）直通；expand 卡面带入值直通；伏笔台账 description、人物 persona brief 直通
- [x] 1.5 `chapters/ai_cast` 人物 persona brief 直通

## 2. 存储/装配侧夹删除

- [x] 2.1 `chapters/store`：章纲 summary 列宽夹（300）与角色状态 state_change（200）退役
- [x] 2.2 `chapters/ai_draft`：fills `[:300]` 退役
- [x] 2.3 `write/chapter_writer`：角色状态逐格 40 字封顶退役（完整直通）；clip import 清理

## 3. 验证上限放宽（完整内容可保存）

- [x] 3.1 `volumes/schemas`：summary 300→2000、core_conflict 150→1000、ending 300→2000、antagonist_line 150→1000

## 4. 测试

- [x] 4.1 旧契约钉子改写：`test_plot_ai` 超长条目（截断+告警 → 完整直通）、`test_plot_items_save` ×3（预算夹 → 直通）
- [x] 4.2 新增防回归钉子：`test_chapter_writer` 角色状态直通、`test_volume_plan_ai` 卷纲 sanitize 直通
- [x] 4.3 受影响套件 200/200 绿；全量 2156 passed（15 存量环境失败不变，原版对照实证；批量跑 volume_crud 的 database-locked 为环境问题）

## 5. 合入与生效

- [ ] 5.1 ai-novel 提交（本 change 追加拍板）
- [ ] 5.2 5274 compose 重建 client-backend，容器内冒烟（直通行为验证）
- [ ] 5.3 prompts 仓预算声明（前批 3b0ebec 已提交；终版下为「目标值」——无需再改）
- [x] 5.4 specs delta 补齐：`specs/chapter-plan-ai/spec.md`（拆章素材包与输出契约＋章卡写法提示词约束）、`specs/volume-plan-ai/spec.md`（两条并行入口＋生成时自查＋存储与数据；含随行提交 c-vol-options-prev-ending 的目标卷号口径）；`openspec validate` 过
- [ ] 5.5 发包顺序随 c-cast-split-user-layer 3.4：本仓先合 → 提示词仓同批 PR 后合 → 重发包（本 change 模板侧只是预算声明文案，无占位符硬依赖，随同批走）

## 6. 验收（真机/演示栈）

- [ ] 6.1 重新出一版拆章卡与卷走法卡：超长内容完整保留（不腰斩）
- [ ] 6.2 生成一版正文素材：角色状态/剧情条目/卷纲块完整（可对照旧 dump）
- [ ] 6.3 存量断句数据作者手工：卷纲「同时应对/独自走」、ch-5/ch-6 章纲概要（或重跑出卡）
