## Context

三步蒸馏管线已完整存在（`client/backend/settings/ai_router.py:1718` 起的 `/ai/style-distill/{step1,step2,step3,commit}`，产物落 `style-quant.draft` 可续跑），样本装配 `_assemble_distill_samples`（同文件 L1631）只认 `files`/`chapter_ids` 两路。前端量化页签（`StyleSettingForm.tsx`，915 行）的蒸馏流程是面板内联三视图（samples→steps→portrait），无任何粘贴 UI；弹窗底座 `Modal.tsx`（wbStyle 版式）与 AiModal（大 textarea 弹窗先例）可直接复用。基线「服务端只写」纪律：前端唯一写路径是 `putLocks`，落卡只能走 commit。设计事实源与硬性流程见 openspec config（原型先行＋ADJUSTMENTS 登记＋design:check 门禁）。

## Goals / Non-Goals

**Goals:**
- 作家能把 ≤10,000 字（去空白）的文本直接贴进弹窗跑完整蒸馏链，结果经确认卡落卡进量化参数界面。
- 粘贴路与文件/章节两路在区间校验、门控、计量、提示词模板上完全同口径。
- 确认卡升级为「画像＋六行基线预览」，两路蒸馏流共享。

**Non-Goals:**
- 不做新端点/新提示词模板/新存储形状（style-quant KV 结构不动）。
- 不做弹窗内进度/确认（进度与确认沿既有面板视图，弹窗只管输入）。
- 不动 3,000 字下限、门控规则、基线写边界；不触 S端 与两端共享段。

## Decisions

1. **粘贴＝显式重启（本 change 最关键裁定）**：step1 现有守卫「`draft.step1` 存在即返回 resumed」会无条件短路——若粘贴不重启，新样本永远到不了 LLM。因此 `text` 非空 ⇒ 清空 draft 再装配重跑。判定式：`paste = str(body.get("text") or "").strip()`，非空才重启；`text` 键存在但非字符串 SHALL 返回 400（不静默 `str()` 强转，防数字/列表被当成样本）。**清 draft 仅内存态**：沿用现行 save-at-end——校验通过且 LLM 产出后才落盘，超限 400 时持久层旧 draft 零写入（与 spec 场景一致）。备选「前端先调一个清 draft 端点」被否：多一次往返且两端可能不一致，后端单点语义最可靠。`text` 缺省或为空时空行为零变化。
2. **无新端点、body 加字段**：`step1` body 增 `text`，粘贴分支**置于续跑短路判断之前**——先判 `text` 非空、再判 resumed（顺序反了粘贴就会被 resumed 吞掉，即决策 1 点名的坑）；粘贴路不查文件/章节（`chapter_count=0`、`samples_used=["粘贴文本"]`）。备选「独立 /distill-paste 端点」被否：step2/3/commit、续跑、门控全要重挂一遍，纯重复。
3. **六行预览由后端单源构建，落 draft；锁定行预览说真话**：step3 落盘时以 `build_baseline` 构建**新值行**存 `draft.step3.rows`，构建时注入 `confidence = confidence_for(draft.sample_chars, draft.chapter_count)`（缺省 0 会全员落 ±30%——「一致地错」且预览＝落卡断言照样绿，必须显式注入）；构建位于 step3 共享落盘块（force「再学一次」整体重写 step3 时同样重建）。`commit_draft` 复用 rows 后**仍执行既有锁定行覆盖环**（按落卡时点正式区锁定态取上一版值＋记 mixture）——锁定语义保持落卡时点新解，杜绝「step3 之后、落卡之前锁被改」的陈旧窗口。前端预览对锁定行按当前正式区锁定态显示「保留上一版：旧值」标记（只读 `draft.step3.rows` 与 `quant.baseline` 两个服务端字段做展示规则，不复制业务算法）——预览与落卡逐行一致，宁可如实告知锁定行不会更新，不做场景豁免。备选「前端镜像 build_baseline 本地算」被否：rhythm 拼接/归一不值得抄第二份，两处实现必然漂移。
4. **弹窗形态照 AiModal 先例**：`Modal wbStyle width=560`＋`afterTitle` PRO 标＋大 textarea＋footer 取消/开始蒸馏；字数用去空白口径，抽 `countSampleChars` 放 `styleApi.ts` 单源——实现用码点迭代（`[...text.replace(/\s/g,"")].length`）贴近 Python `len`，docblock 写明已知残差清单（JS `\s` 含 U+FEFF 而 Python 不含；Python 空白含 `\x1c-\x1f`/`\x85` 而 JS 不含；代理对 JS 记 2 码元 Python 记 1 码点），接受「前端预判、后端为准」。区间外禁用提交＋就地补救文案（不足报还差多少字）。不做硬 maxLength 截断（静默截断＝数据丢失陷阱），但加廉价 fast-path：原始长度已超上限时直接显示超限提示并跳过精确计数，防整本数 MB 粘贴时受控 textarea 每键 O(n) 卡顿。
5. **重启起跑的竞态修复＋重试不丢样本**：`runSteps` 现从 state `distillStep` 起步——粘贴提交时 `setDistillStep(0)` 后闭包仍是旧值，会跳过 step1 拿旧产物跑 step3。改造为 `runSteps(from, force, opts?)` 显式带 `startStep` 与 `text`，粘贴路径强制从 step1 起跑。**粘贴文本存组件态**：重试的 step1 body 持续携带同一 `text`，直至本次粘贴链成功或用户取消——否则 step1 一次 502 后点重试会按空文件/章节路装配，报「样本合计 0 字」的误导错误（粘贴直开弹窗路径 `samples` 为 null，用户无从补救）。后端重启语义幂等，重试再清 draft 重跑无副作用。e2e 用「预置旧 draft＋粘贴」用例锁死此回归。
6. **入口布局**：空态主按钮改「粘贴文本蒸馏」（直开弹窗），次按钮「从文件/章节选样本」**沿用既有 `btn-open-distill` id 与行为**（开样本选择页——存量 e2e 按此 id 断言）；样本选择页顶部加「直接粘贴文本」text-btn。右栏 AI 蒸馏行维持开样本选择页不变，但 desc 文案「输入：novel-samples 或已归档章节」补第三路（`SettingsView.tsx` 与原型同批改，防文案失真）。画像确认挂起态（旧 draft 的 portrait 视图）顺手补 ghost「取消，稍后再说」（`setDistillView("closed")`、draft 保留）——粘贴成为第一入口后「换样本重来」诉求变多，不能把用户锁死在旧确认卡里。
7. **原型先行＋ADJUSTMENTS 登记**：`style-settings.html` 蒸馏空态双入口、样本页粘贴入口、弹窗层（mcard 复用）、确认卡基线预览段（含锁定行「保留上一版」标记口径）、右栏 desc 第三路，`ADJUSTMENTS.md` 逐条登记。style-settings 屏无像素 parity 基线场景（parity CASE 仅 list 屏），但原型在 design-lint 严格名单内（全文禁裸 hex/emoji）——登记如实陈述口径，不攀 parity 先例。

## Risks / Trade-offs

- [粘贴重启误伤：作家在旧蒸馏中途贴新文本，旧进度丢失] → 弹窗提交前不静默：粘贴入口文案标明「重新开始一次蒸馏」；旧产物本就无法与新样本混算，丢失是语义必然，且 draft 只在 commit 后才影响正式区。
- [前端字数口径与后端漂移] → `countSampleChars` 单源＋码点迭代贴近 Python `len`，docblock 记录已知残差；后端强校验兜底，接受「前端预判、后端为准」。
- [超长粘贴卡 UI] → 10,000 字量级 textarea 无渲染压力；不做 maxLength，超限由 fast-path 提示＋提交禁用兜住（见决策 4）。
- [旧 draft 无 rows 时确认卡预览缺行] → 预览段条件渲染（rows 缺失整段隐藏，沿 quant-baseline `if (!row) return null` 同款容错）；`commit_draft` 回落路径保留（从 step3 现算），跨部署边界不炸；真实存量为零（产品未上线）。
- [busy 中「取消」不中止管线，跑完把视图拽回 portrait] → 存量行为，登记**不改**：本 change 不引 abort 机制（与 step2/3 无锁现状同水位）；粘贴重启场景下取消后 draft 被重跑覆盖，由弹窗「提交中禁关」＋后续版本再评估。
- [并发双击粘贴 step1 无锁，双计量] → 与既有蒸馏端点同水位，last-write-wins 无腐损；不引锁，登记即可。

## Migration Plan

单端功能增量，无数据迁移：style-quant KV 形状不变，`draft.step3.rows` 为新增可选键，旧文档经 `quant_doc` 读边界自然兼容。回滚＝还原前端与 step1 分支即可，落卡产物不受影响。顺手修 `quant_doc` 浅拷贝地雷（`dict(_EMPTY)` 改 `deepcopy`）：已实证无 history 键的文档经 commit 后会让第二个新项目串到第一个项目的 history 快照——本 change 正在改 `commit_draft`，同函数边上不留雷。

## Open Questions

（无——区间口径、下限保留、入口布局均已在方案审定时拍板。）
