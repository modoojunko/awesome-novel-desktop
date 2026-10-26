## 1. prompts 仓（awesome-novel-prompts，分支 c-deconstruct-style-transfer）

- [x] 1.1 `deconstruct_card.prompt`＋`deconstruct_card_batch.prompt`：style 条目 quote 契约从「逐字短句 ≤60 字」扩为「逐字原文段 ≤200 字（连续 1-3 个自然段，不跨场景拼接；没有合适原文段给空串）」
- [x] 1.2 `deconstruct_style.prompt`：examples 契约从「0–6 条×≤60 字」扩为「0–8 条×≤200 字成段原文（典型对话＋叙述样本，只从卡片 quote 取，禁止自造）」
- [x] 1.3 `write_chapter.prompt`：人味写法节首最高决策理念改写（本书文风三区与示范段优先、本节补缺省、AI 指纹底线绝对）；纳管注释 style_block 描述补「示范段」（sync.py CURATED 同步）
- [x] 1.4 `python3 sync.py all`＋lint 对拍过；本仓 .venv 跑 `pytest tests/` 全绿

## 2. C端后端

- [x] 2.1 `settings/style_model.py`：`STYLE_WRITE_KEYS` 加 `style_samples`；`_MAX_SAMPLES = 6`；`put_style` cap 循环与 `normalize_style` 归一接入
- [x] 2.2 `deconstruct/settings_map.py` `style_body`：examples 截长 300→400；落地改 `body["style_samples"] = examples[:6]`（不再写 few_shot_examples）
- [x] 2.3 `write/chapter_writer.py`：`_style_samples()`（前 3 条）；`build_system_prompt` 与 `material_markdown` 示范段块（【文风示范段（本书原文摘录——句式、节奏、对话密度的最高依据，照着写）】）
- [x] 2.4 后端测试：`test_deconstruct_settings_map`（style_body 新契约）、`test_style_settings_v2`（七键 roundtrip＋截断）、`test_chapter_writer`/`test_chapter_writer_context`（注入恒定层＋素材骨架＋跳过态）、`test_deconstruct_api`（端到端导入断言改 style_samples）；全量 pytest＋ruff 绿

## 3. C端前端

- [x] 3.1 `lib/deconstructApi.ts`：DECONSTRUCT_DIMS techniques 行加 `book: true`（类型同步）
- [x] 3.2 `TaskDetailPage.tsx`：默认 bookItems＝setting||book（8/10）；「（默认不勾）」条件、弹窗说明文案同步
- [x] 3.3 `StyleSettingForm.tsx`：示范段折叠组（只读段落＋单条删除，无添加）；保存 payload 仅非空携带
- [x] 3.4 前端测试：`StyleSettingForm.fewShots.test.tsx`（键集非空七键/空六键＋示范段渲染删除）、`toolsDetail.test.tsx`（建书默认 8/10 与 items 断言）

## 4. 验证与交付

- [x] 4.1 全量验证：后端 pytest＋ruff；前端 vitest --coverage；prompts 仓 pytest；design:check（触碰 book.css 时）
- [x] 4.2 openspec validate 通过；主检出 rebase 基线确认
- [ ] 4.3 双仓 PR：prompts 仓 PR＋ai-novel PR（openspec sync delta＋归档随实现 PR）；CI 绿后合入
- [ ] 4.4 合入后发提示词包（本机 publish.py，版本按当日；min_client 不 bump）＋CDN 冒烟
- [ ] 4.5 真机验收：重拆一本书→建书（默认 8/10）→文风页示范段＋技法条目→写正文对比文风贴合→人味检测对比
