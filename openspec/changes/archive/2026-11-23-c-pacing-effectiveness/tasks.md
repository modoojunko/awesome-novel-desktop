## 1. 原型先行（C 端）

- [x] 1.1 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记拆章三方向态新增五态与文案（「本章将走：第 K 步 · 步名」/未存节奏＋「去节奏页签」/未设目标/超出目标/算不出兜底/过期批＋「重抽」）；`book.html` 拆章弹窗为隐藏空壳、不属 parity 面（ADJUSTMENTS:1155/1657 先例），SHALL NOT 补 DOM；验证：条目在案并写明「design:check 本无拆章屏用例」的理由。
- [x] 1.2 改 `docs/design-c/drafts/ai-novel-c端-卷纲节奏-原型.src.html` 查看态：来源四态文案（含「读不出来」）、条件承诺（无章数目标第三态）、主「保存到这一卷」/次「改为本卷设置」/「编辑节奏」、之前某一卷建议行；`python3 docs/design-c/drafts/build-pacing-proto.py` 重建后在 ADJUSTMENTS 按「新增块不触 parity 基线」登记；验证：`python3 docs/design-c/drafts/check-pacing-proto.py` 全绿。
- [x] 1.3 文案自查：新增文案不含「预填/生效/注入/拍位/effective」，按钮均为动词；验证：原型文本 grep 无禁用词，状态行不新增胶囊/裸 hex。

## 2. 后端：生效状态单源与只读接口

- [x] 2.1 `client/backend/volumes/pacing.py` 抽 `effective_of(config, book_default, volume_no) -> (config, source)`：volume 分支原样归一；book 分支用 `build_config(preset, steps_len, ch1_extra_on=(volume_no==1))` 补齐；空返回 `(None, None)`；`resolve_config` 复用；验证：单测覆盖三态、vol1/vol2 的 `ch1_extra_on`、`effective` 与 `resolve_config` 逐字段相等、`steps` 非空。
- [x] 2.2 `pacing_router.get_volume_pacing` 增 `effective` / `effective_source` / `config_present` / `config_invalid`；`plan.steps_len/n` 改 `effective ?? prefill`；prefs 读取异常按未设处理；验证：单测覆盖卷列/仅书默认/prev+book 不一致/两级空/坏 JSON/未知 preset/`{}`/`[]`，并断言 `prefill`/`source` 原义不变、`plan` 用 effective。
- [x] 2.3 `beat_context` 增可选 `config` 参数（已解析则不再 `resolve_config`）；`next_chapter_anchor` 用**卷内 `ch_no`** + `beat_context` 生成 `pacing_effective` / `pacing_preview{step_idx,step_name,step_task,ch1_extra}` / `pacing_reason{no_target,out_of_target,unknown,null}` / `pacing_fingerprint`；`next_no` 只留展示；验证：单测覆盖第 1/2 卷、第 2 卷第 1 章、ghost 空洞、无配置、无目标、超目标、unknown；断言无模型调用、无记账、无落库。
- [x] 2.4 `ai-directions` 响应增同一口径 `pacing_fingerprint`（与角标同源 `beat_context`）；验证：跨端点断言同章同配置下 anchor 指纹 == directions 指纹，角标步位一致。
- [ ] 2.5 钉「注入零变化＋基线口径」：`planned=false` 仍注入；仅书默认也注入；无配置素材逐字同升级前的 golden 快照；位置行/【拍位硬规则】精确计数；`mat` 键集合只多 `pacing_task`；捕获 prompt 中不得出现 `pacing_preview`/`pacing_reason`/指纹字符串；preview 与 `beat_context` 在「卷列/书默认/无/无目标/越界/第 2 卷」矩阵逐项相等；锚点调用不产生 token log；验证：`python -m pytest tests/test_volume_pacing.py tests/test_chapter_plan_ai_t*.py tests/test_plan_pacing_rules.py -q` 绿。（已加 planned=false/书默认/无 preview 泄漏/计数断言；golden 逐字快照与 mat 键集合未补）
- [x] 2.6 修正过期注释：`volumes/pacing.py` 模块头与 `prefill_chain` docstring 的「注入只认卷列」改为「注入按卷列→书默认，不看 planned；题材映射只做展示预填」；`chapters/ai_plan.py:312` 注释同步；验证：grep 无「注入只认卷列」，相关测试绿。

## 3. 前端：节奏页签与右栏

- [x] 3.1 `volumePacingApi.ts` 增 `effective`/`effective_source`/`config_present`/`config_invalid` 类型；`VolumePacingPane.tsx` 的 `shown` 与 `baseline` 都改 `effective ?? prefill`，来源四态行、条件承诺（含无章数目标第三态）、主「保存到这一卷」（PUT 预填、`planned=false`）、次「改为本卷设置」（PUT 生效书默认）、之前某一卷建议带「改用这一套」出口、读不出态、`planned` tag 取 `data.config?.planned`、tooltip 说明未排≠不会照它走；验证：单测覆盖四来源态/零改动不脏/目标为空/坏配置/两个 CTA 载荷。
- [x] 3.2 `VolumeAssistPanel.tsx` 三个节奏动作读取与写回基线改 `effective ?? prefill`；验证：单测断言书默认+上一卷预填时排段用书默认，写回后来源为 volume。
- [x] 3.3 文案断言：新增文案不含「预填/生效/注入/拍位」，按钮为动词，常态未配置无 warn/err 徽标；验证：单测 grep 断言 + `npm run design:lint`。

## 4. 前端：拆章预告与会话一致性

- [x] 4.1 `chapterPlanApi.ts` 锚点类型增 `pacing_effective?` / `pacing_preview?` / `pacing_reason?` / `pacing_fingerprint?`（optional，旧 mock 兼容）；`useChapterPlan.ts` 持久化指纹、比对内存批与 localStorage、章节抽卡用独立版本键/显式校验 `v===2`（不动卷抽卡 v1）、不一致走过期态、重抽不继承旧批 exclude；验证：单测覆盖一致恢复/从无到有/从有到无/只改任务句/改额外交代/目标清空/v1 丢弃/重抽 exclude 为空。
- [x] 4.2 `ChapterPlanModal.tsx` 三方向态五态渲染（确认+任务句 tooltip、未存、无目标、超目标、兜底）、过期批标「节奏或章数目标变了」并抑制正面预告与旧角标；忙碌态只提示不出「去节奏页签」，idle 才给；本章卡只留只读提示、不出「去节奏页签／重抽」破坏性出口；过期批本章卡换向走 fresh（不继承旧 exclude）、旧形状锚点不误报；验证：组件测试五态 + 旧字段缺失 + 过期批 + 不阻断出卡/排上。
- [ ] 4.3 「去节奏页签」接线：`ChapterPlanModal` 增 `onGoPacing`；`NovelWorkspace` 关闭弹窗并导航到 `planTargetVolRef`，`VolumeWorkspace` 加 `pacingJumpSeq`（照 `outlineSeq` 先例）在换卷重置后切到「节奏」页签；验证：单测第 2 卷弹窗切到第 2 卷节奏页签，不切错当前卷。（已实现并测 VolumeWorkspace seq 切页签；NovelWorkspace 跨卷导航未单测）

## 5. 回归与验收

- [x] 5.1 后端全量：`cd client/backend && PROMPT_PACK_DEV_DIR="$PWD/../../awesome-novel-prompts/prompts" python -m pytest tests/ -q`，记录实际通过数（不得低于本次基线）。（worktree 2930 passed / 4 baseline failed；main 同集 2918 passed / 同 4 failed——A/B 一致）
- [x] 5.2 前端类型与单测：`cd client/frontend && npx tsc --noEmit && npm run coverage`，记录实际结论（perFile 100% 契约必须 exit 0）。（1985 passed，全文件 100%，exit 0）
- [ ] 5.3 设计门禁（C 端）：`cd client/frontend && npm run design:lint && npm run design:check`，记录像素差结论；本次不触两端共享段（依据 proposal「Design Impact」），`design-cross` 不需要跑，在回归注记中写明。（design:lint exit 0；design:check 需四服务栈，未跑——本次未触 parity 屏）
- [ ] 5.4 e2e：更新 `e2e/chapter-plan.spec.ts` 的 11 处 anchor mock（补 optional 字段）；新增「未存节奏提示→保存→预告出现」「旧批过期重抽」「第 2 卷按卷内章号预告」；`e2e/volume-pacing.spec.ts` 增来源三态与两个 CTA；注意「未存节奏」用例不要先定题材（定题材会写书默认）；验证：`npx playwright test e2e/volume-pacing.spec.ts e2e/chapter-plan.spec.ts` 实际红绿。
- [ ] 5.5 真机抽检：本机 0.45 库选一本只有题材预填的书——页签来源行与「保存到这一卷」；保存后拆章弹窗出现「本章将走：第 K 步」并可悬停看任务句；用保存前旧批验证过期提示与重抽；第 2 卷验证不出现「超出目标」误报；全程不阻断出卡。（接口层真库副本只读验收已过：未存→effective null／anchor 无预告；副本保存→effective_source=volume／第 8 章预告第 2 步＋任务句；UI 真机未做）
