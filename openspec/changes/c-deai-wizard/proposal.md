# Change: c-deai-wizard

## Why

朱雀检测（c-zhuque-ai-detect）已能标出「哪些段像 AI」，但**检测之后怎么改**没有产品化：作家面对标注只能手动选中→单段 polish→盲改，没有按《人味.md》第七章战法（7.6 流程／7.4 纪律／7.5 战法）组织的修稿路径，也没有格式硬伤的机器兜底（三件套/半角/嵌套引号等是统计指纹检测器的盲区）。三路评审（Prompt Engineer／Frontend Developer／Product Manager，2026-10-10，汇总见 `docs/design-c/drafts/修稿向导-三路评审汇总.md`）通过架构方向并给出落地要求；原型 v2（`docs/design-c/drafts/ai-novel-c端-修稿工作流-原型.src.html`）经用户确认定稿。

旅程定稿（用户拍板收敛）：**① AI 味检查（本地规则＋读检测存档，0 额度）→ ② 选择段落（清单勾选）→ ③ 整体修改（逐段 polish 出候选，当场取舍，0 检测额度）→ ④ 应用（一次写回）**；收口＝顶栏朱雀条重检（作家自点，向导不包复测）。

## What Changes

### 后端（client/backend）

- **新增 `write/ai_flavor_scan.py`（三合一单源）**：
  - `scan_prose(prose) -> ScanReport`：本地确定性规则扫描（判据移植资产包 `_precheck.py`＋人味二-11/12 补两条），产出 `findings[]`（rule/severity/para/excerpt/detail）＋软指标（逗句比/极短段占比/对白占比/比喻密度）。severity 分 blocking/advisory；`count_words_claim` 不自动修（事实错须人工）。
  - `RULE_LABELS`：rule_id → 作家可读一句话（直陈/疑似二分：正则确证直陈，启发式加「疑似」）。
  - `build_problem_segments(paragraphs, report, stored_result)`：合并**两路来源**（本地规则命中段＋朱雀 conf≥0.5 判定段）为去重的问题段清单（para_index 0-based 非空段序、text、source、confidence、reasons[]、suggested_fix 启发式映射——纯展示不喂模型）。
  - `quick_verdict(before, after, banned_words)`：polish 产物程序化校验——blocking（书级禁用词、**新增**结构红线（破折号/半角/尾随标签/夹层/不是A是B——区分新增 vs 存留命中）、引号奇偶、格式泄漏）＋advisory（字数带 0.80–1.65 外、数字守恒）。命中只降级不销毁。
- **新增端点 `POST /api/novels/{id}/chapters/{ref}/ai-flavor-scan`**（login 门控，0 模型 0 检测额度）：服务端读章正文＋读朱雀存档（`zhuque.service.get_stored_result`），返回 `{report, problems, detector:{stored,human_ratio}}`。无存档时 `detector.stored=false`（规则模式——不设检测前置门，PM 评审裁决）。
- **`POST …/write/polish` 响应增强**：附 `changed`（空白折叠后 diff 派生，非模型自报——「确诊零逐字原样输出」的合法无操作在向导 UI 呈现为「未查出可修的硬伤」，PE 评审 A）＋`flags`（`quick_verdict` 结果，PE 评审 E）。老客户端忽略附加字段，零破坏。

### 前端（client/frontend）

- **新增 `components/novel/workbench/polishWizard/`**：`types.ts`（PolishStep/ScanFinding/ProblemSegment/FixCandidate 等）、`PolishWizard.tsx`（Modal 壳＋步骤状态机＋四面板＋请求编排：串行＋预取 1、AbortController、关闭保护）、`applyProseSegments.ts`（写回纯函数）。
- **`ProsePane`**：`ProseHandle` 扩 `applyParagraphEdits(items)`——采纳段按文档逆序在单条 `editor.chain()` 内 `insertContentAt`（一次 ⌘Z 整批回退）＋双写 store（`lastSyncedRef`/`setProse`，对齐既有 accept 链）。
- **`AiAssistPanel`**：prose 页签新增「去 AI 味 · 修稿向导」入口行（选区单发按钮保留改名副文案）；门禁矩阵（PM 评审）：free/standard 锁＋升级；未配本书模型硬禁用＋去配置；已配模型即可进（无朱雀存档＝规则模式＋软引导；stale/检测中按状态禁用）。
- **`lib/ai.ts`**：`polishText` 补可选 `signal`；新增 `aiFlavorScan()`。

### 提示词仓（awesome-novel-prompts）

- **一期零改动**（PE 评审裁决：polish v7 复用照旧；hint 一期不喂——锚定偏误会绕过诊断门反证校准，二期按埋点触发走 OpenSpec）。「提示词设计」的本变更产出＝复用契约确认＋`lesion_hint` 二期预备措辞（存档于评审汇总）。

### 明确不做（一期）

- 向导内复测/回滚编排（应用后走顶栏朱雀条重检收口——用户拍板）；hint 喂模型；草稿暂存（fast-follow）；字级 diff 高亮（段级对照一期够用）；outline_overlap 照搬检测；机器项自动清理（②清单提示作家手动进③）。

## Capabilities

### New Capabilities

- `polish-wizard`：去 AI 味修稿向导（AI 味检查／选择段落／整体修改／应用确认四步）。

### Modified Capabilities

- `prose-writing`：polish 响应附 `changed`/`flags`（右栏老入口与向导共用，附加字段老客户端忽略）。

## Impact

- C 端：`write/{ai_flavor_scan.py,router.py}` 新增/增强；`client/frontend/src/components/novel/workbench/{polishWizard/,ProsePane.tsx,AiAssistPanel.tsx,ChapterWorkspace.tsx}`、`src/lib/ai.ts`
- 测试：后端 `tests/test_ai_flavor_scan.py` 新增＋polish 响应字段断言；前端 `src/__tests__/PolishWizard.test.tsx` 新增
- 提示词仓：零改动（一期）
- 无 schema 结构变化；新增 1 端点；门禁矩阵见 spec

## 拍板记录（评审收敛）

1. 门禁＝PM 矩阵（PRO 规则模式可进，不要求 MAX/检测存档）——用户目标「全流程落地」即按推荐执行。
2. 比喻词 severity＝advisory。
3. hint 一期不喂。
4. 机器命中段带段落定位进②清单。
