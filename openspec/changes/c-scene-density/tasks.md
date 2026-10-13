# c-scene-density 任务

> 补录型 change：实现已随 PR #843（本仓）落地于分支 c-scene-density（commit e3253b1d），提示词仓同批 PR #7。以下按实际完成状态回填。

## 1. 设计影响判定与口径

- [x] 1.1 双端影响判定：单端 C（章纲页签三处纯说明文案，复用既有 `field>opt`/`hint-inline` 版式），不触两端共享段、无新令牌/新语气词——原型先行豁免，判定依据登记于 proposal「Design Impact」
- [x] 1.2 四路评审（Prompt Engineer／Backend Architect／Frontend／Product）完成，阻断 3 项与建议项全部处置（见 PR #843 评审记录与 §5）

## 2. 抽卡链（chapters/ai_plot.py）

- [x] 2.1 `plot_count_hint` 档位单源（锚点四段，上限钉 PLOT_MAX_ITEMS=12；≥2000 档密度 330–500 字/条如实限定）
- [x] 2.2 素材恒带【本章字数】＋建议条数直给；取值链 body>存值>书默认，越界同落 default 注释钉死
- [x] 2.3 请求体 `PlotDrawBody.word_target`（可选，旧客户端/无 body 兼容实测）
- [x] 2.4 `_MAX_MIDDLE` 4→10（每版 4–12）；超发剪条出 warning「剪了要说」
- [x] 2.5 生成预算 8192→16384；`_is_max_tokens_rejection` 双条件判据→降 8192 重打首发一次、阶梯沿用降级值；不命中 502 直穿

## 3. 写章链（write/chapter_writer.py 等）

- [x] 3.1 「## 字数与场景分量（章级红线照守，字数照达）」独立节；红线节名改否定式仲裁「不以字数、写法为由破线」
- [x] 3.2 `scene_share_chars` 均摊行（<200 不发防超写；与守卫共用判定）
- [x] 3.3 收尾重申行扩三件语义（写足句同词不同句）；防回声钉子×2（分量行、整节，公共串<8 判据）
- [x] 3.4 `should_refresh_stored_prompt` 扩「场景分量」锚（润色资产豁免同罩）；golden 重生成
- [x] 3.5 `clamp_word_target` 迁 `settings/book_prefs_model`（消 chapters→write 跨域边；re-export 兼容）

## 4. 前端（章纲页签）

- [x] 4.1 `chapterTarget.plotCountHint` 镜像＋读源交叉对拍闸（`TestPlotCountHintParity`）
- [x] 4.2 `OgPane` 三处提示行（编辑态字数框下／剧情区标题带「现 n 条」／查看态），实时随表单生效值（越界/空→本书默认）
- [x] 4.3 `usePlotDraw` 携带表单现值；typeof 守卫＋redraw 拆开（评审阻断：MouseEvent 污染 wtRef）＋「换一批仍带 word_target」行为钉

## 5. 回归（实际输出结论）

- [x] 5.1 后端：`pytest tests/test_chapter_writer.py tests/test_chapter_writer_context.py tests/test_plot_ai.py tests/test_plot_prompt.py tests/test_shared_constants_parity.py tests/test_write_regressions.py tests/test_prose_pipeline.py tests/test_book_prefs.py -q` → **171 passed**（PR worktree 独立复跑与主检出一致；已知无关失败四文件不属本批，基线复现）
- [x] 5.2 前端：`vitest run`（plotDrawModal/plotFlow/ogWordTarget/chapterTarget）→ **51 passed**；`tsc --noEmit` → **净**
- [x] 5.3 `npm run design:lint`（node scripts/design-lint.mjs）→ **exit 0**（无新令牌：原生色板 0、裸 hex/emoji 计数与前值持平，改动仅文案与既有版式类）
- [ ] 5.4 `npm run design:check`（DESIGN_PARITY playwright e2e）——依赖 5174 dev server＋登录态，合并部署时随 PM 验收单同跑（本批不触共享段，design:cross 不适用）
- [x] 5.5 提示词仓侧配套：`sync all` 单次收敛＋`lint 通过`＋`pytest` 52 过 1 跳（其仓 tasks 登记）
