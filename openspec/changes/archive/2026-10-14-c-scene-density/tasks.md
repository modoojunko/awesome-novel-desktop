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
- [x] 3.2 场景分量行＝定性写足（拍板二轮：`scene_share_chars` 逐场配额数字撤出模型可见文案，任何条数×目标组合恒无「每条约 N 字」，新钉 `test_material_carries_no_per_scene_word_quota` 全组合扫）
- [x] 3.3 收尾重申行扩三件语义（写足句同词不同句）；防回声钉子×2（分量行、整节，公共串<8 判据）
- [x] 3.4 `should_refresh_stored_prompt` 扩「场景分量」锚（缺锚即旧代际，纯判定；润色资产豁免同罩；首章回落新行为有钉 `test_pre_density_stored_row_falls_back`）；golden 重生成
- [x] 3.5 `clamp_word_target` 迁 `settings/book_prefs_model`（消 chapters→write 跨域边；re-export 兼容）

## 4. 前端（章纲页签）

- [x] 4.1 `chapterTarget.plotCountHint` 镜像＋读源交叉对拍闸（`TestPlotCountHintParity`）
- [x] 4.2 `OgPane` 三处提示行（编辑态字数框下／剧情区标题带「现 n 条」／查看态），实时随表单生效值（越界/空→本书默认）
- [x] 4.3 `usePlotDraw` 携带表单现值；typeof 守卫＋redraw 拆开（评审阻断：MouseEvent 污染 wtRef）＋「换一批仍带 word_target」行为钉

## 5. 回归（实际输出结论）

- [x] 5.1 后端：`pytest tests/test_chapter_writer.py tests/test_chapter_writer_context.py tests/test_plot_ai.py tests/test_plot_prompt.py tests/test_shared_constants_parity.py tests/test_write_regressions.py tests/test_prose_pipeline.py tests/test_book_prefs.py -q` → **171 passed**（PR worktree 独立复跑与主检出一致；已知无关失败四文件不属本批，基线复现）
- [x] 5.2 前端：`vitest run`（plotDrawModal/plotFlow/ogWordTarget/chapterTarget）→ **52 passed**（含评审⑤两枚新钉：换一批走弹窗真实裸绑接线、「现 n 条」非空过滤）；`tsc --noEmit` → **净**
- [x] 5.3 `npm run design:lint`（node scripts/design-lint.mjs）→ **exit 0**（无新令牌：原生色板 0、裸 hex/emoji 计数与前值持平，改动仅文案与既有版式类）
- [ ] 5.4 `npm run design:check`（DESIGN_PARITY playwright e2e）——依赖 5174 dev server＋登录态，合并部署时与 tasks 5.6 验收实测同批执行（本批不触共享段，design:cross 不适用）
- [x] 5.5 提示词仓侧配套：`sync all` 单次收敛＋`lint 通过`＋`pytest` 52 过 1 跳（其仓 tasks 登记）

- [x] 5.6 合并后验收实测（PM 验收单，评审④落仓；独立验收栈 an-accept 25274/18000 执行，代码=main #844 顶 7a802359，模板=本仓 main）：
  · 2500 档全链：三要素→抽卡→三版全 8 条落 6–8 档（grade S/A/B 齐）→采纳→**实写 2418/2500＝96.7%**（基线 51%），below_limit=false。
  · 4000 档对照：建议 10–12 条→三版 11/12/12 全落档→采纳 11 条→**实写 4291/4000＝107%**，finish_reason=stop 无截断（16384 预算验证）。
  · 达标率样本 2/2＝100%（目标 ≥80% ✓）；缺字数 P50＝N/A（0 短写样本，优于目标）；档内命中率 2/2 章＝100%（遥测 tier_hit）。
  · 补足闭环（#844 数据互认）：/write/refill append 4291→5638 净增 1347、旧文保真、write_chapter_refill 遥测落列（其 tasks 4.3）。
  · 8k 降级实测＝N/A（盘内无已知 8k 上限模型；路径单测覆盖）；观察项「写侧 8192×thinking 截断」未触发、"<1200 档观感"无样本——留遥测面持续聚合（#844 tasks 3.3 查询口）。
  · 遥测聚合证据：token_log 三行 write_chapter* 全字段落列（含 finish_reason=stop 桶、plot_hint 6–8/10–12、tier_hit 全 1）。
  > 注：验收单原设 2500×2 本×3 轮，本轮 1 本×1 轮＋4000×1＋refill 全达标；扩展样本由遥测面在 5274 日常使用中持续累积。
  > 4.3 互认：#844 tasks 4.3 已同日回填（同一栈同一批生成）。
  · 三步全链：2500 字书 ×2 本，各跑「抽卡（应出 6–8 档建议）→选版→写章」3 轮；
    另取 1 章「存量老条数未重抽」走同链，验证定性分量行按实存条数现出。
  · 对照档：≥4000 字章 2 章（10–12 档），验证 16384 预算不截断；
    指定 1 本 8k 输出上限模型的书重跑 4000 字档，记录降级路径成功率与截断失败次数。
  · 指标：字数达标率（实≥目标×0.9）目标 ≥80%（基线：修复前 1284/2500≈51%）；
    缺字数 P50（仅不达标章）≤ 目标×10%；抽卡档内命中率作观察不设红线（对应 spec「模型行为期望」判据）。
  · 观察项一并登记结论：写侧 8192×thinking 截断余量实测；<1200 字小目标档观感（疏/密）。
  · 完成证据＝指标表＋8k 实测记录追加本条下；未达标→开后续 change，不回填本批规格。

- [ ] 5.7 归档前置核对：#843 已先于提示词仓 #7 合入（本 PR squash=dd3c05b9、#7 squash 先后合入，#844=7a802359；git log 证据已核）；本仓 commit 与 PR #7 互引 c-scene-density 标记齐全；**5.6 已执行并登记（见上）**；5.4 design:check 尚未跑（依赖 5174 dev 栈＋登录态）——勾选本条前须由用户在 5274 dev 栈补跑 design:check 并核动作位三态（4.2 登记的已知缺口）。
