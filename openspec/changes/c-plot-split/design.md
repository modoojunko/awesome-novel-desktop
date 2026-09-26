# c-plot-split 设计

## Context

动机与范围见 proposal.md；行为契约见 specs/（新能力 chapter-plot-items ＋ 4 个 delta）。要点：章纲表单已有整表回传保存链（`ogToPartial`／浅合并 PUT `useOutline.ts:246-252`／3s 自动保存 `ChapterWorkspace.tsx:295-317`）、拆章已有三方向抽卡与名次→字母评分先例（`chapter-plan-ai`）、素材包已有两路组装（`material_markdown`／`to_prompt`）。五路评审实勘结论与证据（file:line）全录 `docs/design-c/drafts/review-plot-0925/五路评审-v3.md`，八条拍板见 `docs/design-c/drafts/章内剧情拆分-设计要点.md`（v3.4）。

## Goals / Non-Goals

**Goals:**

- 用最小改动面把 plot_items 落进既有链路：列、表单、保存、素材包、AI 端点全部搭现有骨架（style_shadow 列先例、ogToPartial 整表回传、ai_plan 生成骨架、pick-* 弹窗词汇）。
- 把评审六条 P0 在实现层一次钉死（结尾单源、常驻撤销、块名与两路同源、润色不丢块、生成预算、落库纪律）。

**Non-Goals:**

- 不做结构化剧情字段、不做链↔正文校验、不动场景卡/段落规划/gate 口径（拍板留档）。
- 不做服务端回滚历史（撤销只活在前端会话内）；不为剧情建子表或排序列。
- 不引入新组件形态或语气档位（复用 pick-*/locked/toast 既有词汇）。

## Decisions

1. **建模走 `string[]` 直传**：OgForm 增 `plots: string[]`（照 segs/scenes 数组先例），`ogToPartial` 直出 `plot_items: string[]`。
   - 备选 keys/chars「\n 拼串」（chapterForm.ts:170-171 先例）——**弃**：含换行长文本 round-trip 会被切成多条。
2. **落库缺键语义＝presence-gate＋恒带双保险**：服务端缺键保留现值、显式 `[]` 清空（style_shadow 先例 store.py:292-303）；前端 `ogToPartial` 恒带键（空存 `[]`）。
   - 备选 clear-on-missing（拆章五段先例 store.py:288-290）——**弃**：旁路部分写入（service.py:115-128）会成丢数据入口；测试契约在本 change 内按新口径钉。
3. **列落地照 style_shadow**：`models/chapter.py` 增 `plot_items` Text 列（`default="[]"`、`server_default="[]"`），随版本换代自动建出（无 DDL）；读侧 `json.loads(row.plot_items or "[]")` 损坏按空（migration/engine.py 空串回填坑）。
4. **生成端点复用 ai_plan 骨架，一次出 3 版**：单次调用产出 3 版（temperature 0.7），响应 `{ok, versions:[{items}], grades, warnings}`；`_generate` 加 `max_tokens` 关键字参数（默认 4096 不动），本端点传 8192（volumes/ai_plan.py:44,51-58 现状写死）。
   - 备选三次串行生成——**弃**：2ccbbf39 教训（串行重试烧 tokens）；备选 2 版照出——**弃**：拍板「必须凑满 3 版」。
   - 重试阶梯只认「0 可用版本」；越界按句读截断（clip_story_arc 先例 chapter_writer.py:45-55）不重试；grades＝模型给 1–3 名次、服务端映射字母（对位 keep_map，ai_plan.py:299-356 口径），缺名次不出角标。
5. **素材包块单源渲染**：新增 `_plot_block(items)` 之类的单一渲染函数，`material_markdown` 与 `to_prompt` 都调用（两路已存量漂移，禁再两处手写）；插入位在【场景原材料】之前，块名【本章剧情走向（分条）】＋定位句。润色骨架补第 10 要素（逐条保留不改写）＋`validate_polished_prompt` 条件锚（照场景原材料条件锚先例 chapter_writer.py:109-110）。
   - 备选各自拼接＋文档约定——**弃**：parity 无机器保障。
6. **前端弹窗与撤销**：抽卡弹窗复用 `pick-grid/pick-card/pk-corner/pick-foot`＋`Modal`（常驻挂载保 200ms 退场与焦点还原）；代际守卫照 `useChapterPlan.ts:185-189,334-339`（换一批清上一批选中、关窗丢晚到响应）。采纳前快照 `plots`，回执常驻（不挂 toast 超时），撤销走函数式 `setOgForm` 只回滚 `plots`（借 3s 自动保存回写）；「自己写」退回原列表。
   - 备选 UndoToast 8s 装饰器——**弃**：超时即丢手写内容（P0-2）。
7. **预算校验只在输入侧**：`maxLength=200`＋满 12 禁加；**不进 `ogFormIssues`**（issues 非空整表自动保存冻结，ChapterWorkspace.tsx:301）。备选入 issues 就地报错——**弃**：连坐冻结是数据丢失路径。
8. **已润色章软提示**：前端判定（该章有润色提示词且剧情被编辑）→ 软提示「可重新润色」，不自动重算。备选自动失效重算——**弃**：拍板⑥＋不新增保存链。

## Risks / Trade-offs

- [3 版输出仍可能超 token] → 生成预算写死进提示词（每版 2–6 条×≤200 字、合计 ≤4000 字）＋max_tokens 8192＋句读截断兜底；截断只丢长度不丢结尾句（截到最后一个句读点）。
- [两路素材包漂移复发] → 共享 helper＋parity 回归进 CI；golden 回归钉「空剧情逐字不变」。
- [条件锚误伤存量] → 校验只在润色动作时执行，不回溯存量 write-prompt；存量提示词优先级不变。
- [常驻回执与自动保存赛跑] → 撤销以函数式回滚为准、回执在下次编辑即收；自动保存失败时走既有 saveState=failed/retry 口径，不另造提示。
- [presence-gate 与拆章五段口径并存] → 在 chapter-data delta 注明与 style_shadow 同口径；拆章五段行为不动（避免顺手改契约），差异在本 change 登记。

## Migration Plan

- 无显式迁移：列随版本换代自动建出；旧库旧书读出 `[]`、不回溯补填。回滚＝代码回滚，多余列无害（读侧兜底）。
- 发布顺序：原型＋门禁 → 后端列/端点 → 前端表单/弹窗 → 提示词层（可同批）；每步独立可验证（pytest/vitest/e2e 分层）。

## Open Questions

- 无（口径已由八条拍板与五路评审收口）。
