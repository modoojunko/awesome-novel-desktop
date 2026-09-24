## Context

见 proposal.md 的 Why。落地相关现状（实勘）：

- 保存链：`lib/chapterPlanApi.ts:114-121` 的 `saveEdit` 只发 `{outline:{summary}, challenge, ladder_exit, chapter_acts, plot_stage}`；后端 `chapters/store.py:506-510`（`prose = data.get("prose") or ""`）、`:273-292`（`word_target` 按缺省清）、`:606-609`（子表 `clear()` 后按 data 重建）。前端 `__tests__/chapterPlan.test.tsx:512-521` 用「缺字段按空写」把该契约钉死。
- 读卡：`hooks/useChapterPlan.ts:107-138` openEdit 不清 draft、catch 只置 error；`ChapterPlanModal.tsx:285-294` 保存钮不看装载状态。
- 竞态：`useChapterPlan.ts:150-165` 进场锚 catch 比 `tokenRef.current` 而非 `anchorTokenRef.current`；`openManual/openAi` 不重置 `entry`；`runSelfcheck`（`:221-252`）无 token 守卫。
- 回执：`NovelWorkspace.tsx:573-582` 恒提示「已排上」；`useChapterPlan.ts:275-279` editing 分支返回 `{ok:true}` 无动作标识。
- 对照正例：章纲保存链（`useOutline.saveChapter`）走「读全量→合并→PUT」；拆章弹窗已有 `client_token` 幂等与 `Modal locked`。

## Goals / Non-Goals

**Goals:**

- 保存动作在任何入口、任何章状态下都不丢内容（正文/子表/字数）。
- 卡面状态（草稿/进场/自检）与当前目标章严格对应，不出现跨章残留。

**Non-Goals:**

- 不改后端写语义（显式全量 PUT 的「缺键即空」保留——它服务显式清空；改由前端发全量）。
- 不重构拆章弹窗状态机为 reducer（本次只加守卫与清理，最小改动）。
- 服务端幂等（`client_token`）不在本次扩展（排上已有；回改保存不涉及创建）。

## Decisions

**D1：`saveEdit` 改「读全量 → 合并五段 → 全量 PUT」。**
沿 `useOutline.saveChapter` 同路：先 GET 章全量，覆盖五段字段后整发。备选（已弃）后端对缺 `prose` 视为保留——会剥夺显式清空能力，且与「显式全量 PUT」契约矛盾。

**D2：前端契约测试改口径，而非保留旧断言。**
`chapterPlan.test.tsx` 的「缺字段按空写」改为「saveEdit 发出全量字段（含未编辑字段）」——测试是契约的守卫，契约变了守卫要同批改。

**D3：读卡失败 = 空草稿 + 禁用保存（与 C2 主线卡同型口径）。**
统一「未成功装载不得提交」的守卫范式，后续新卡面照此办理。

**D4：竞态守卫统一用「请求代际 token + 开卡重置」。**
进场锚修正为比 `anchorTokenRef.current`；`open*` 三入口统一重置 `entry`；自检加 token 守卫与按钮 busy。不做更大重构。

**D5：回执按动作分流。**
`adopt` 返回动作标识（`adopt` / `edit`），handler 据此给「已排上」/「已保存」；文案遵循 design-language §13（动词、无内部术语）。

## Risks / Trade-offs

- [读全量 + 全量 PUT 多一次请求] → 本地单用户、单章数据量小；正确性优先。
- [改契约测试可能掩盖真实回归] → 反向验证：先在旧实现上跑新断言应红（证明新断言能抓住清空行为）。
- [派生视图行（含归档章）入口放开写] → 本 change 保证写入安全；是否限制入口（只读归档章）属产品口径，登记为 Open Question 不阻塞。
- [搬运 409 判定改动与 c-db-version-hardening 同文件] → 两 change 同批实施，先落 C5 的 409 判定再叠加 C4 的清理门。

## Open Questions

- 已归档章/仅派生视图行是否应开放「改这一章」入口（当前可达且写入安全后无数据风险，但语义上是否允许改动归档章内容）——可在实施后由产品口径确认，不影响本 change 规格与任务。
