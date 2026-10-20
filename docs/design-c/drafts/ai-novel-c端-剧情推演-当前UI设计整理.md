# 剧情推演（plot-sim）当前 UI 设计整理 · 现状快照

> 2026-10-13 整理。目的：用户反馈「用得不爽」，先把现行界面完整摸底，为重设计讨论提供底稿。
> 对应能力规格：`openspec/specs/plot-sim/spec.md`； redesign 提案背景见 2026-10-11 讨论记录（待拍板未立项）。

## 0. 一句话定位

「以上一章结尾为起点，用本章章纲的剧情条目与出场角色，一回合一步推到本章结尾」——
AI 一次生成全章 2–4 个回合，作者在弹窗里逐回合替角色选走法（顺 / 拗），最后把走法
收进章纲。MAX 档功能（feature key `ai-plot`），界面是 storyline.html 四期尾原型的复刻。

## 1. 入口与门禁

| 环节 | 现状 |
|---|---|
| 入口位置 | 写作页右栏「AI 助手」面板 · **章纲页签**动作列表，条目「剧情推演 · 按回合走一遍」，副文案「先定走法再逐步推演；走法可收进本章剧情条目」（`AiAssistPanel.tsx:414`，testid `og-simulate`） |
| 中栏章纲面板 | 不设按钮——2026-09-20 拍板 AI 起草/剧情推演入口收口右栏（`OgPane.tsx:583` 注释留痕） |
| 禁用条件 | 本章已归档 →「本章已归档」；非 MAX 档 → `upgradeHintOf("ai-plot")` 升级提示 |
| 后端门禁 | 端点挂 `@ai_feature("ai-plot")`（仅 MAX）＋本书模型就绪双门控；403 拦截时不发生任何模型调用 |
| 挂载链 | `ChapterWorkspace.tsx:1163` `onSimulate: () => setShowSim(true)` → `:1623` 渲染 `<SimModal>`，注入 projectId / chapterRef / chapterLabel / planWords（章目标字数）/ onAdopt |

## 2. 弹窗结构（Modal 560px · wbStyle）

`SimModal.tsx` · 样式类 `.sim-*` 在 `book.css:1447-1458`（纵向 flex 12px 间距、描边卡片、12.5px muted 说明行）。自上而下：

1. **标题**：「剧情推演 · 按回合走一遍」。
2. **章题行**（`.sim-ch`）：完整章标题「第X章 · 名称」。
3. **导语**（`.sim-lead`）：解释玩法——每一回合先替角色做一次选择，再推到本章结尾。
4. **等待态**：两行文案「正在推演……」＋「AI 推演中，请勿关闭弹窗」。**无进度条、无取消、无倒计时**；弹窗此时并未 `locked`（只有关闭前的字面劝阻）。
5. **错误态**：一行 `error.message` ＋［重试］按钮。
6. **统计条**（`.sim-stats` 四格）：起点（「第 N 章结尾」或「开书」）· 终点（本章标题）· 回合（N 回合）· 出场角色（N 人）。
7. **「推演的起与收」卡**：承接上一章 `entry`（上一章正文末 60 字或概要）· 收束到本章 `exit`（必须完成的变化首条，缺省回落概要）· 计划篇幅（千分位字数或「未定」）。
8. **回合卡列表**（2–4 张，随 step 逐张展开）：
   - 未走到：占位卡，文案「还没走到——推到这里才会展开」（防剧透式呈现）；
   - 当前回合：题「回合 N · 待你定」；正文 = 起点说明 `at` ＋三行明细（**关键事件** beat／**在场** who·place·time／**这一回合落下** shift）；
   - 走法按钮恰两个：「顺 · {角色}顺着当前节奏动手」「拗 · {角色}先被外力打断一下」（label 由后端 `_moves()` 定形）；
   - 选定后追加结果行：「走法已定 · 顺/拗 ＋ 结果句 out」；**已定回合的按钮仍可点击换选**。
9. **剩余提示卡**（未走完时）：「还剩 N 回合 · 每定一步，推演就更贴近本章结尾；走法只作参考，不会自动改动章纲」。
10. **页脚四按钮**：［关闭］［重新推演］＋［推演下一个回合］／末回合时替换为［按这条走法收进章纲］（在途显示「收进章纲…」并 `locked`）。

## 3. 交互流程（前端行为逻辑）

```
打开弹窗 → 立即 POST simulate（一发式，AI 已写完全部回合）
  ├─ 加载中：文案劝阻勿关（实际可关，请求继续，再开重取）
  ├─ 失败：一行错误 ＋ 重试
  └─ 成功：展示统计/起收/回合1，其余回合折叠为占位卡
逐步「推演下一个回合」＝纯前端展开下一张已生成回合
  └─ 当前回合未选走法 → info toast「先替这一回合选一个走法，再往下推」（软校验，按钮不 disabled）
末回合 →「按这条走法收进章纲」
  └─ strategyLineOf(picks)：全回合任一「拗」→「推演走法 · 中途先接一次意外，再拉回主线」
     否则→「推演走法 · 顺着章纲节奏推进，不多加波折」（二选一固定话术，仅此两句）
  └─ handleSimAdopt（ChapterWorkspace.tsx:814）：该句追加为 ogForm.plots 末尾一条
     → ogFormIssues 校验 → 走既有 saveChapter 链；成功 toast「已按推演走法加了一条剧情」＋关窗
「重新推演」：整单重发请求，清空全部已选走法、step 回 1
推演产物本身不落库；重开弹窗从零再推
```

## 4. 后端与数据契约

- **端点**：`POST /api/novels/{pid}/chapters/{ref}/simulate`，无 body（`write/plot_sim.py:198`）。
- **响应**：`{ok, source: "ai"|"fallback", entry, exit, prev_label, cast, rounds[]}`；回合含
  `n/beat/who/place/time/at/shift/moves`，`moves` 恰两条（tone=ok/warn）。
- **素材**（`_material()`）：本章章纲（概要／剧情条目≤12／出场角色／挑战／卷内阶段／主情绪／
  必须维持悬念／必须完成的变化）＋上一章结尾（正文末 120 字摘录、末 60 字做 entry；
  无上一章用「开书第一章」固定句）。退役字段（关键事件/场景/预期策略等）不入素材（c-og-slim-v2）。
- **AI 调用**：**一次** haiku 调用生成全部回合，`max_tokens=1600`——这是全应用最长的单发阻塞
  POST（几十秒暴露窗，10-11 曾据此定诊 HTTP 502）。
- **清洗**：beat/ok/warn 缺一丢整回合，上限 4 回合。
- **兜底**：调用失败/产物不合格 → 确定性模板推演（剧情条目环＋模板走法句），`source=fallback`，
  端点永不向用户报错；**UI 不区分来源，兜底与 AI 产物同口径展示**。
- **记账**：调用已发生（成功/失败）均记 usage（失败记 `plot_sim_fail`）；模型未就绪不记账。
- **提示词**：`awesome-novel-prompts/prompts/plot_sim.prompt` v2 分层——system＝长篇策划角色＋
  推演标准＋JSON 输出契约；user＝素材包。走法口径写死为 ok＝顺节奏推进／warn＝外力打断再拉回。

## 5. 已知痛点（10-13 摸底汇总，含 10-11 三层设计诊断）

| # | 痛点 | 出处 |
|---|---|---|
| P1 | **推进感是假的**：全部回合在作者点第一个按钮前就已一次写完，顺/拗选择不影响任何后续内容；「一回合一步往下推」只是逐张展开的呈现效果 | plot_sim.py 单发调用 / SimModal step 只翻卡 |
| P2 | **参与口只有二选一**：走法是两个固定原型（prompt 与 `_moves()` 都写死），不能自提走法、不能改写回合落点、不能增删回合 | plot_sim.prompt；plot_sim.py:41 |
| P3 | **收进章纲零信息**：`strategyLineOf` 只产两句固定话术，AI 的具体结果句与作者逐回合选择全部丢失 | SimModal.tsx:27；ChapterWorkspace.tsx:814 |
| P4 | **长等待＋502**：整章推演一发阻塞几十秒，「请勿关闭弹窗」窗口撞上换包/重启即 502（10-11 日志实锤）；无进度、无取消 | plot_sim.py:262；demo 栈判例 |
| P5 | **无回退**：「重新推演」清空全部已选；回合已定仍可换选但旧选择不留痕；弹窗可关但劝阻文案与实际不锁相悖 | SimModal.tsx:49-66,104 |
| P6 | **兜底不告知**：fallback 模板句与 AI 结果同口径展示，作者看不出拿到的是保底填充 | spec「弹窗永远可用」的副作用 |
| P7 | 小项：追加剧情条目 `slice(0, PLOT_MAX_ITEMS)` 超限静默丢尾；软校验靠 toast 而按钮不禁用 | ChapterWorkspace.tsx:818 |

## 6. 重设计方向备忘（未拍板，勿当结论）

10-11 提案：翻转为**真回合制**——每回合一次 AI 调用（只生成下一回合局势＋2-3 候选走法），
三个参与口＝选候选／自由输入走法／直接改写回合落点；每回合定完可单独收进章纲（落实际内容句，
`strategyLineOf` 退役）；单回合 ≤15s 顺带收窄 502 暴露窗；「快速一次生成」倾向砍掉。
成本＝一章 1 次调用变 2–4 次（MAX 档可接受）。落地＝openspec change，端点 step 式＋SimModal
重做＋plot_sim.prompt 重写三处联动。

## 7. 文件索引

| 层 | 文件 |
|---|---|
| 弹窗 UI | `client/frontend/src/components/novel/workbench/SimModal.tsx`（269 行，含 strategyLineOf） |
| 入口面板 | `client/frontend/src/components/novel/workbench/AiAssistPanel.tsx:414` |
| 挂载/收进章纲 | `client/frontend/src/components/novel/workbench/ChapterWorkspace.tsx:811-840, 1163, 1623-1631` |
| API 客户端 | `client/frontend/src/lib/plotSim.ts` |
| 样式 | `client/frontend/src/design/book.css:1447-1458` |
| 后端端点 | `client/backend/write/plot_sim.py`（348 行） |
| 提示词 | `awesome-novel-prompts/prompts/plot_sim.prompt` |
| 能力规格 | `openspec/specs/plot-sim/spec.md` |
| 测试 | `client/backend/tests/test_plot_sim_api.py`（302 行）· `client/frontend/src/__tests__/plotSimAndPromptSources.test.tsx`（122 行） |
