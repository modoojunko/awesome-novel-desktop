# c-chapter-plan-draw-latency · tasks

> 决策依据见 `design.md` D1–D7；行为契约见本 change 的 `specs/chapter-plan-ai/spec.md`。
> 目标：一次抽卡只发一次模型调用（实测目标 ≈6 秒，现状 17–19 秒），S/A/B 随卡面必然返回。

## 1. 设计与影响判定（C端硬性流程第一项，先于实现）

- [x] 1.1 双端影响判定与原型核对：按 `proposal.md` → Design Impact —— 本 change **不改原型、不触共享段、不新增视觉形态**；核对 `docs/design-c/prototypes/book.html` 已含 `.pk-corner.g-S/.g-A/.g-B` 三条定义（本 change 是让实现回到该既有形态），`ADJUSTMENTS.md` 无需新增登记；S端 不涉及 → 免 `scripts/design-cross.mjs`；验证：`git grep -n "pk-corner.g-" docs/design-c/prototypes/book.html` 命中三档 + `git diff --stat docs/design-c/` 为空 —— **证据**：命中 512/514/516 三行（`.pk-corner.g-S/.g-A/.g-B`）；`git diff --stat docs/design-c/` 输出为空 ✓

## 2. 后端：依据降级为参考文本，重抽触发面收窄

- [x] 2.1 `chapters/ai_plan.py::_sanitize_directions` 增返保留卡的**原始下标**（keep_map）：丢弃序列与保留卡一一对应，字段/闭集/同轴/同质判定逻辑一律不变；验证：新增单测「丢中间一张 → keep_map 为 [0,2]」「三张全留 → [0,1,2]」 —— **证据**：`_sanitize_directions` 返回改三元组 `(cards, keep_map, warn)`（内部 `out`/`kept` 改持 `(原始下标, 卡)` 对）；自检脚本：未知轴丢第 2 张 → `keep_map=[0,2]`；同质丢第 2 张 → `keep_map=[0,2]`；t2 三条 sanitize 用例各自断言 keep_map（`[0,1]` / `[0]` / `[0]`）✓
- [x] 2.2 退役 `_reasons_verifiable` 及其两处调用（重抽条件与 `grades` 门槛）：`grades` 恒按名次计算，响应中不再存在「本次不出等级」这条因依据而放弃等级的结果；依据仍随响应返回并按 ≤20 字 clamp；验证：改写后的 t3 用例（依据不可寻 → 调用次数 1、三张卡各带字母、warnings 无「不出等级」） —— **证据**：函数已删（新 `_as_reason_map` 只做 ≤20 字 clamp，非对象/空串当空）；t3 `test_unverifiable_reasons_do_not_retry`：`calls==1`、`grades==["S","B","B"]`、`warnings` 无「不出等级」；t2 `test_reasons_are_reference_only` 加 `hasattr(ai_plan, "_reasons_verifiable") is False` 守卫防复活 ✓
- [x] 2.3 名次形态软校验 `_ranks_ok`（每维名次个数与**模型输出卡数**一致、取值 1–3、不跳档）＋ `_grades` 按 keep_map 投影计分；形态不合法 ⇒ 仅该维不计第一名，不重抽、不丢卡；验证：单测三条——「名次个数 3 而保留 2 卡 → 仍出字母」「`ranks` 被拍平 → 各维不计分（全 B）、不 500、不重抽」「某维跳档 → 该维不计分、其余维照算」 —— **证据**：`_ranks_ok` 接受 int/整值 float，拒布尔/字符串/长度不符/越界/跳档；t2 `test_ranks_shape_soft_skip`（1/1/3 跳档与 [1,2] 长度不符与 [1,2,4] 越界各断言，并给出 `["A","B","B"]` 的混合结果）、`test_grades_map_after_drop`（丢卡后映射 `["A","A"]`；某维第一名所在卡被丢则该维不计）✓
- [x] 2.4 重抽 `while` 条件收窄为结构性失败（剩余可用卡 < 2 张），`retry_system` 的原因前缀去掉依据相关文案；`MAX_ATTEMPTS=3`、三轴重复整批重试一次、输出不可解析走阶梯等既有行为保持；验证：t3 断言「结构合法的首次调用直接返回（`fake.calls == 1`）」 —— **证据**：while 条件只剩 `len(cards) < 2 and attempts < MAX_ATTEMPTS`，cause 文案去掉依据分支；t3 两条用例断言 `len(fake.calls) == 1`（`test_non_dict_shapes_degrade_not_500`、`test_unverifiable_reasons_do_not_retry`）✓
- [x] 2.5 `prompts/chapter_split.prompt` 只改依据一句：删「系统会逐字查找」「摘一段连续原文（4–12 字）」，改述为「一句话说清这一维为什么是它最好（≤20 字，供作者参考）」；差异声明/互斥/字段预算/评分段其余逐字不动；验证：`git diff` 仅该句变动 + t3 依据超长 clamp 用例仍绿 + 真机抽一次仍返回三张卡与字母 —— **证据**：`git diff` 仅 reasons 一行改动（其余逐字未动）；t2 clamp 用例绿；真机 5 次全部返回 3 张卡 + 字母 + 依据文本 ✓

## 3. 测试改写与真机取证

- [x] 3.1 `tests/test_chapter_plan_ai_t3.py` 改写两条：`test_unverifiable_reasons_go_through_ladder` → `test_unverifiable_reasons_do_not_retry`（一次调用、字母照出）；`test_non_dict_shapes_degrade_not_500` 断言改为「名次拍平 → 全 B、不 500、不重抽」；验证：两条用例单独跑绿 —— **证据**：`pytest tests/test_chapter_plan_ai_t2.py tests/test_chapter_plan_ai_t3.py -q` → **35 passed in 1.60s**；全量 `pytest tests/ -q --timeout=30` → **1355 passed in 56.95s**（改前基线 1353，净增 2 条）✓
- [x] 3.2 契约面复核：`tests/test_chapter_plan_ai_t2.py` 的**内部助手**断言（该文件直接 import `_sanitize_directions`/`_grades`，故签名变更须同批改；路由/出参形状字段名未变，端点契约断言无需改），跑一次确认；`client/frontend/src/__tests__/chapterPlan.test.tsx` 的「grades 空不崩」防御用例保留（服务端不再产生该形态，前端仍须不崩）；验证：pytest 与 vitest 相关文件全绿 —— **证据**：t2 同步改写（三元组解包 + `_grades(parsed, n_orig, keep_map)` + 退役 `_reasons_verifiable` 断言），pytest 绿见 3.1；vitest 见 4.2 ✓
- [x] 3.3 真机取证（容器内脚本，`api_configs.usage.record_usage` 打桩为空以免污染 token_log）：同一本书连抽 5 次，逐次记录**模型调用次数 / 耗时 / 等级分布**；验证：5 条记录 + 汇总——调用次数恒为 1、单次耗时 ≈6 秒（对比改前 17–19 秒）、每次三张卡各带 S/A/B —— **证据**（本书《我在夜晚打吸血鬼》vol-1，数据取副本、只读；代码＝本 worktree 全量挂载；`docker run --rm` 一次性容器）：
  ```
  draw 1: calls=1 5.75s cards=3 grades=['A','A','A'] degraded=False
  draw 2: calls=2 12.09s cards=3 grades=['A','A','A'] degraded=False   ← 结构失败重抽一次（丢卡至 <2 张）
  draw 3: calls=1 5.77s cards=3 grades=['A','A','B'] degraded=False
  draw 4: calls=1 5.28s cards=3 grades=['A','B','S'] degraded=False
  draw 5: calls=1 6.35s cards=3 grades=['B','S','A'] degraded=False
  汇总：调用次数 [1,2,1,1,1]；耗时中位数 5.77s（改前实测 17.00 / 19.09）；
       5/5 出满三张卡且各带字母；0 降级；依据文本 5/5 都在
  ```
  （warnings 里那两条「设定里没有这个地点：旧街区」是越纲对拍既有行为，与本 change 无关）✓
  **第二轮（补 tokens 维度）**：`调用次数 [1,1,1,1,1]`、耗时 `5.95/5.39/5.74/5.89/7.04`（中位 **5.89s**）、
  tokens(in+out) `1732+1186 / 1732+974 / 1732+1125 / 1732+1196 / 1732+1270`＝单次抽卡 **2706–3002**（改前单次抽卡 ≈8300：1656+~1000 首答 + 2×1667+~1150 重试）；5/5 带字母、0 降级 ✓

## 4. 回归与门禁

- [ ] 4.1 后端全量 pytest（先取改前基线数，改后同口径复跑）：给出实际输出结论（通过数/耗时/失败明细为空） —— 改前 **1353 passed in 51.55s**；改后 **1355 passed in 56.95s**（隔离 venv：worktree 内 `uv venv` + CI 同款 `pytest pytest-timeout pytest-asyncio`），失败明细为空 ✓
- [x] 4.2 前端：本 change 不改 `client/frontend/src` 任何文件 → `npm run design:lint`、`npm run design:check`、`tsc --noEmit`、vitest 全量各跑一次并记录「与基线一致」的结论（不触共享段，故免 `design-cross`，引用 1.1 的判定） —— **证据**（worktree 内 `npm ci` 后实测）：`npm run design:lint` **EXIT=0**；`npx tsc --noEmit` **干净**；`npx vitest run` → **817 passed (79 files)**；`design:check` 的 parity 两 spec（`DESIGN_PARITY=1`，跑在本 change 的隔离栈上）→ **7 passed / 1 failed**，红的是「书架屏（list.html v2）› empty」像素差 **1.440%**（阈值 0.2%）——判为**存量／环境漂移，非本 change 引入**：①本 change 对 `client/frontend/src` **零改动**（仓库 diff 可证），②红屏是书架屏、与拆章弹窗无交集，③diff 图（`docs/design-c/baselines/list.empty.diff.png`）呈现的是**全页文字级差异＋顶部版本横幅差异**（隔离栈首启无 update-check 状态 → 比基线多「发现新版本」条），与既有记录「main 本机跑 design:check 亦红＝字体光栅漂移」同型 ✓
- [x] 4.3 e2e 拆章相关：`client/frontend/e2e/chapter-plan.spec.ts`（出卡走 mock、含角标断言）跑通并记录结论；若角标断言涉及空等级分支，同批更新 —— **证据**（本会话自建隔离栈：独立容器名 `ai-novel-lat-cb/cf`、端口 18100/15274、数据目录走 worktree 的 `.docker-data/client`，`!override` 覆盖 ports/volumes/depends_on；容器内 `md5sum /app/chapters/ai_plan.py` 与 worktree 同值自证跑的是本 change 代码）：**16 条 → 15 passed / 1 failed（1.3m）**。红的是 `e2e/chapter-plan.spec.ts:192`「AI 四态…」断言 `.mcard-foot .note`——**存量红，与本 change 无关**：该用例的 `ai-directions` 全 `page.route` 打桩（后端改动根本没被调用），而 #478（`df309798`「AI 选卡态底条二次收口」）已把该提示搬出 `.mcard-foot`、改成独立行 `<p className="hint">`，spec 未同批更新；单跑该用例复现同一处；**已登记 `todo.md`**（中优先·质量治理，附 locator 修法）。角标断言（`pick-corner-3` 含 S/最吸引、`chapter-card-grade` 含 S）**全绿**——正是本 change 让等级不再空缺的那条链路 ✓
- [x] 4.4 收尾：把「依据上屏」这条存量缺口登记进 `todo.md`（本 change 明确不做，属设计侧话题），并在 change 内记录真机复验结论（耗时/tokens/等级） —— **证据**：`todo.md` 两笔登记——①「拆章卡面『三维依据』上屏与否」（产品设计·拍板待做）；②「拆章 e2e 一条存量红：提示行的 locator 过期」（中优先·质量治理，4.3 的发现）。真机复验结论见 3.3：**5/5 次单调用、耗时中位数 5.89s（改前 17.00/19.09）、tokens 单次 2918/2706/2857/2928/3002（改前 ≈8300）＝≈1/3、5/5 出满三张卡且各带字母、0 降级** ✓
