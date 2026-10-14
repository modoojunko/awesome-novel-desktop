# c-shortfall-refill 任务

> 真立项件：全部未勾，等 #843 合入后进入 apply。

## 1. 前置与原型

- [ ] 1.1 依赖确认：#843（c-scene-density）已合 main（`plot_count_hint`/`word_target_floor`/done word_check 三件就位），本分支 rebase 最新 main
  > 现状：#843 尚未合——本分支已堆叠在 `origin/c-scene-density`（三件全部可用，全量测试即在其上跑绿）；待 #843 合入后 `git rebase origin/main` 复核再推。
- [x] 1.2 原型先行：完成卡「补足字数」动作位（既有卡式＋warn 语气）出一版原型或按完成卡既有布局自查，登记 ADJUSTMENTS；受影响屏＝正文生成完成卡（单端 C、不触共享段）
  > 自查结论：动作位复用 edit-bar 既有 `span.tool-seg`＋`btn btn-secondary btn-sm`（同款按钮已在同排、与 qc-pill 并列），无新令牌、无新语气词、不触共享段——无视觉差异可登记，ADJUSTMENTS 无新增。
  > 门禁：`node scripts/design-lint.mjs` exit 0（裸 hex/emoji 与存量持平）。design:check（像素差）依赖 5174 栈，合并部署时执行。
- [x] 1.3 apply 定形：读 `write/router.py` /write 通道与 `auxiliary` 现状，二选一（/write append 模式 vs /refill 端点）——判据＝恒定层组装与 SSE 阶段流可原样复用；结论写回 design Decision 1
  > 结论＝独立 `/write/refill` 端点：/write 携带提示词覆盖、存稿读写、替换写、按次模型四语义，append 塞入每处都要条件分支且易污染 write-prompt 存稿；独立端点原样复用 build_chapter_context/恒定层/SSE 契约与保存链，存稿零触碰。已回写 design Decision 1。

## 2. 续写补足

- [x] 2.1 续写指令行组装（append 口径：从尾接写、落点或下限先到即停、已写正文不重述）＋治理自查（无逐场配额；与收尾行 <8 公共串，扩一枚钉子）
  > 治理钉 `test_refill_line_not_verbatim_of_closing`：6 档目标×素材/收尾行公共串全 <8，且「每条约」零出现（字数只评估不投配额，拍板 2026-10-13）。
- [x] 2.2 续写端点：append 落库走既有保存链＋分段归一；独立计量 `write_chapter_refill` 族；双门控照生成
  > 事件契约照 write（phase/chunk/done/error）；失败族 `write_chapter_refill_fail`；钉 `test_refill_requires_existing_prose`（空章 422）＋`test_refill_appends_and_preserves`（旧文逐字在前、写-prompt 不脏、续写指令行进请求）。
  > 评审agent 修复（P2）：合并只归一 AI 尾段，已写正文仅去尾换行原样拼接——手动链（save_prose）留的段间空行是作者排版，钉 `test_refill_preserves_user_blank_lines`。前端中断分支同口径。
- [x] 2.3 两轮封顶收口：第三轮起动作位换成「重新生成整章」引导（复用既有重生成出口）
  > refillRounds 会话态（换章/整章生成复位）；两轮后渲染 prose-regen → startStream 原链（版本快照前置自带）。
- [x] 2.4 前端完成卡动作位＋进行中阶段呈现；达标/仍不足/两轮收口三态
  > 等待呈现复用 genStage 链；复刻钉 proseStream「续写补足复刻」两案（done 合并＋中断半截保留）。
  > 评审agent 修复（P1）：startRefill 改 async——先立守卫再 `await store.flush()`（refill 是链上唯一 read-modify-write，防抖窗口未落盘编辑会被服务端按旧稿合并覆盖；flush 失败释放守卫中止）；await 后复核章号/编辑器存活（落盘窗口内切章即放弃）。

## 3. 写链遥测

- [x] 3.1 TokenLog 加列：target/actual/below_limit/finish_reason（生成与补足两路都记）
  > StreamEvent 新增 finish_reason（openai=choices[].finish_reason、anthropic=message_delta.stop_reason；未回传＝空串 unknown 桶）；record_usage 扩参默认 None 不扰其余调用。
- [x] 3.2 档位命中现算：生成留痕时按 plot_count_hint(目标) 与实发条数记 hit 布尔（同源函数即判据）
  > 拆 `plot_count_band` 区间单源、hint＝band 渲染（钉 test_band_and_hint_single_source）；无剧情条章 tier_hit=NULL 不进命中率分母。
- [x] 3.3 聚合可查性验证：截断桶（finish_reason=length）与自愿短写桶（stop）可分离计数；命中率报表 SQL/查询口记录进本条
  > 落列钉 `test_refill_telemetry_columns`。查询口（sqlite 直算）：
  > `SELECT operation, finish_reason, count(*), avg(tier_hit) FROM token_log WHERE operation LIKE 'write_chapter%' GROUP BY 1,2;`；达标率＝`avg(actual_words >= round(target_words*0.9))` 同表直算。

## 4. 回归

- [x] 4.1 后端：pytest 全量（续写三态、免费档零调用、append 不毁稿、遥测落列、<8 治理钉）实际输出结论追加本条下
  > `2306 passed, 14 failed, 1 skipped`——14 失败与基线（git stash 对照原样复跑 14 failed/2301 passed）同集合，均为已知环境缺件族（auth_middleware_session/story_engine/version_snapshot_cap/outdated_signal）；本次 +5 枚新钉全绿。免费档门控走 @ai_feature＋require_ai_access 既有依赖（/write 同构，ai_feature_matrix 覆盖门控形态），未另造重复用例。
- [x] 4.2 前端：vitest（append 请求形状＋收尾合并/中断复刻）＋`tsc --noEmit`；`design:lint` exit 0 实际结论
  > proseStream 12 过（复刻两案＋streamChapterRefill URL/无体钉）；相邻 chapterWorkspace.plotFlow＋castReviewFlow 53 过（edit-bar 渲染无回归）；`tsc --noEmit` 净；design:lint exit 0。
  > 如实备注（评审agent 指出）：**动作位三态渲染无组件级直测**——按钮出现/计数/两轮收口仅有复刻级与挂载路过覆盖，属测试缺口；补组件级挂载测成本高（tiptap＋workbench 上下文），登记为已知缺口，真栈验收（4.3）人工核三态。
- [ ] 4.3 真栈实测（5274 独立环境纪律）：一章故意写短触发补足闭环；一本 6000 字档观察截断桶是否出数——结论回写 c-scene-density tasks 5.6 对应观察项（两仓 change 数据互认）
