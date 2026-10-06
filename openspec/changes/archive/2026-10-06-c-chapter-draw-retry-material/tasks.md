## 1. 原型先行（用户可见：busy 态阶段列表）

- [x] 1.1 原型处置（2026-10-05 用户拍板「照先例登记偏差」，替代原「改 book.html」方案——该弹窗原型只有空壳 `#split-body`、design:check 无拆章屏用例，照 c-chapter-plan-guards 先例不补 DOM）：`prototypes/ADJUSTMENTS.md` 追加 `## c-chapter-draw-retry-material（2026-10-05）` 节，登记 busy 阶段列表为产品超出原型项、复用 `.ex-steps` 词汇、不触共享段，阶段文案终稿＝「读卷纲与设定／推演 3 个方向／自查与评分」——验证：ADJUSTMENTS 条目在册（文件尾部可查）

## 2. 后端：结构性重试带全素材（跑偏与慢的同源修复）

- [x] 2.1 `client/backend/chapters/ai_plan.py` 端点内把首调用 user 消息组装抽为可复用局部构建（`material_blocks`＋`position_rules`＋「请给出第 N 章…」引导句一次算好），首调用行为逐字不变——验证：既有 t1/t2/t3 用例 52 passed（首调用逐字不变：`user_msg` 本就先于循环算好，直接复用即同源）
- [x] 2.2 重试循环改发与首调用同源的完整 user 消息（素材包＋位置片段＋目标章引导句＋`_exclude_block(exclude)`），system 仍追加「（上一次{cause}。）」；降温阶梯（0.7/0.3）、`MAX_ATTEMPTS=3`、降级出口原样——验证：新增 `test_retry_carries_full_material_and_logs_cause` 断言第 2 次调用 user 与首调用逐字相同且含素材标记；t1/t2/t3 全绿 52 passed
- [x] 2.3 触发重试时以模块 logger（INFO）落 `attempt/cause/novel/vol/ch` 一行日志，不进 API 响应——验证：caplog 断言 `attempt=2/3 cause=…` 行在案（钉子用例内）
- [x] 2.4 回归钉子：`test_retry_carries_full_material_and_logs_cause` 独立用例（首调用喂结构性失败桩 → 捕获第 2 次请求 → 断言与首调用同文＋素材标记在场、system 含失败原因、日志 attempt=2/3）——验证：红绿翻转已实证——临时改回裸重试该用例 FAILED（1 failed），恢复后 1 passed

## 3. 前端：busy 态阶段进度（感知层）

- [x] 3.1 `ChapterPlanModal.tsx` busy 态加阶段列表：`CH_STEPS`（读卷纲与设定／推演 3 个方向／自查与评分）＋`STEP_DONE_MS` 5s/10s/15s 计时推进，进 busy 归零、出卡停表；渲染复用 `.ex-steps`＋`ra-spin`＋`data-testid="split-steps"`，宽度内联复用 genbox 的 66ch 档（零新增 CSS 规则、零裸 hex、零新语气词）——验证：`chapterPlan.test.tsx` 新用例（fake timers 推进、完成段 em.ok、15s 全完成 busy 仍不退出、响应回来才出卡）81 passed；`npx tsc --noEmit` 0 错
- [x] 3.2 核对 e2e 与桩：grep 索取语短语（「请给出 2 到 3 个剧情方向」）在 e2e/桩脚本**零命中**（桩全是 page.route 网络层拦截，不看提示词）；`chapter-plan.spec.ts` AI 四态用例补 `split-steps` 在场＋首段文案断言——验证：隔离栈 chapter-plan.spec **16/16 passed**（1.3m）

## 4. 回归门禁（记录实际输出结论）

- [x] 4.1 后端（主检出 .venv 解释器＋worktree cwd）：t1/t2/t3 = **52 passed**；全量 pytest = **1790 passed, 0 failed**（67.11s）——零新增红；`ruff check --extend-select F811,F821,F841`（CI 同款选择）两改动文件 **All checks passed**
- [x] 4.2 C端前端：`design:lint` **0 违规 exit 0**；`npx tsc --noEmit` **0 错**；`vitest chapterPlan.test.tsx` **81 passed**；全量 `vitest run` **102 files/1178 tests 全 passed**；`design:check` 7 过 1 红——红＝书架屏 list.empty **0.291%**，系存量光栅漂移（ai-modal-no-close-tip 期即 0.29% 红，见记忆）：本改只动 ChapterPlanModal，不触 list 屏，拆章屏无 parity 用例（ADJUSTMENTS 收编实况在案），与本改无因果
- [x] 4.3 e2e 隔离栈（per-session 配方）：`-p an-cdrm`＋自写 override（container e2e-cdrm-*，端口 5178/8004/19001，共享 S端 19000 实测未发布→自带 S端 retag 镜像）；镜像特征串自证＝前端 bundle「读卷纲与设定」1 命中＋后端「chapter_directions retry attempt」1 命中；`chapter-plan.spec.ts` **16/16 passed**；`E2E_CLIENT_BACKEND_CONTAINER=e2e-cdrm-client-backend` 已设（teardown 不打共享栈）
- [x] 4.4 触共享段判定：`git diff --name-only` 六文件（ai_plan.py／t3 测试／ChapterPlanModal／chapterPlan 测试／e2e spec／ADJUSTMENTS）——**未触 base.css 与 icons**（共享段零触碰）；`.ex-steps` 仅 C端 `src/design/book.css`；按 proposal Design Impact 判定依据，无需 `design-cross.mjs`
