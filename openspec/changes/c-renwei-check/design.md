# Design: c-renwei-check

## Context

原型已定稿并经用户拍板：`docs/design-c/drafts/ai-novel-c端-人味检测-原型.html`（真机抓取底座 v3）＋《ai-novel-c端-人味检测-设计说明.md》（用户故事地图循环版＋8 项拍板）。算法参考实现已存在：`docs/design-c/drafts/check-renwei-demo.py`（19 项指标＋人味率＋优先级的完整纯 Python 实现，约 300 行，原型所有数字由它实算）。本 design 只记录实现决策，交互细节以原型与设计说明为准。

## Goals / Non-Goals

- Goals：本地检测引擎（19 项＋人味率＋定位 findings）与端点；四拍报告弹窗；左右分边注＋逐段重扫消卡；章头徽章；右栏入口行；去AI味改写链退役。
- Non-Goals：语义层检测（归章节体检）；本地小模型/分类器（不做——透明统计已是方案核心）；权重反校准（长期项，只留数据口子）；报告落档与趋势（v1 不落库，随时免费重算）；朱雀检测的任何改动。

## Decisions

### D1 引擎放后端，纯 Python 移植
- 新模块 `client/backend/write/renwei_check.py`：以 `check-renwei-demo.py` 为底移植——`renwei_lexicon.py`（词表：虚词/抽象名词/具体名词/转场词/感官分类，从资产包 `_人味指纹.py` **全量**移植）＋ `renwei_baseline.py`（基线冻结常量表：19 项 mean±SD＋P25–P75＋权重，来源 320 章实测表）＋ 纯函数 `check_prose(text) -> {score, priorities, metrics[], findings[]}`。
- 参考实现的对拍测试保留：`tests/test_renwei_check.py` 用「像人段/机器味段」逐指标钉方向（省略号少=扣分等，防写反）、基线表完整性、豁免规则；`docs/design-c/drafts/check-renwei-demo.py` 升级为对拍工具（同一输入分别喂参考实现与生产引擎，指标差超容差即红）。
- 阈值方向钉死：省略号/虚词是下限型（少=差）、句号/抽象名词是上限型（多=差）——演示阶段已发生过方向写反，逐项断言。
- 已知校准点（不阻塞，实现时处理）：MTLD/Hapax 2,000 字收敛门槛、资产包全量词表落地的密度类复测、资产包 `_人味指纹.py` 若有现成实现则逐函数对拍。

### D2 端点与记账
- `POST /api/novels/{project_id}/chapters/{chapter_ref}/renwei-check`：只挂登录；无请求体读盘正文；同步返回；**不进 TokenLog**（非模型调用，backend-logging 的 llm.log 不涉及；常规 app.log 一条 debug 即可）。
- 编辑防抖重扫复用同一端点（整章重算毫秒级，前端只更新受影响段）——SHALL NOT 做单段专用端点（避免两套口径）。
- 退役端点：`/ai-flavor-scan`（向导①步，唯一调用方是向导）与 `/write/polish`（选区去AI味）随 tasks 阶段三下线，连同其测试与 schema。

### D3 词表与基线的演示→生产换装
- 演示最小词表（26 虚词字/20 抽象词/10 具体字…）SHALL NOT 上生产；移植时以资产包全量词表替换，并用资产包 `_人味指纹.py` 对同一段文本做实现对拍（演示口径与资产包口径的差异项——叙述文本口径、2,000 字收敛门槛——已在设计说明 §4 登记，移植时以此复核）。
- 题材敏感项（具体名词等）按总表原注不入计分、仅观察。

### D4 前端结构与标注机制
- 入口行：章右栏 ra-* 检测区，朱雀行之下（`renwei-check` 行，无门控分支——不走 tier 门）。
- 四拍弹窗：新组件 `RenweiCheckModal`（intro/running/result 三态体＋脚部按钮随态），文案全部取自设计说明的作家口径（禁实现词汇）。
- **标注用 TipTap Decoration**（沿用 zhuqueMarks 先例，独立 PluginKey/独立 storage）：段色＝node decoration；边注＝段尾 widget decoration（React 渲染，内嵌「标为已改/跳过」按钮可交互）。遵守 zhuqueMarks 文件头两条实测坑（DecorationSet 住 plugin state 保身份稳定、widget 用函数形态 toDOM＋稳定 key）。
- 边注布局按原型：正文锁死居中（覆盖层/decoration 均不占布局流），边注右贴边、宽度自适应剩余空白（放不下换行）、详情卡向左展开；窄窗回退（<约 950px 中栏）退化为「段角胶囊＋浮层」——实现期以最小窗宽断点处理。
- 逐段重扫：编辑防抖 0.7s → 调 renwei-check 端点 → 前端 diff 新旧 findings：该段命中清空＝消卡（其余段不动）；该段仍有命中＝更新边注计数。跳过项本地记录（会话内，不落库）。朱雀 stale 语义照旧（正文变更→置灰），人味检测不读写朱雀数据。
- 章头徽章：e-head 内「人味改稿 n/10」，随 findings 处理状态实时更新；清零转绿＋朱雀重检提示光圈。

### D5 退役装配
- 前端：`PolishWizard.tsx` 及其调用链（`ai-polish` 卡、openPolishWizard、usePolish*）、polish 相关 vitest/e2e 用例删除或改写。
- 后端：`/write/polish`、`/ai-flavor-scan` 端点与 schema、`quick_verdict`、ai-flavor-scan 规则（其正则类规则由 renwei 引擎收编——**收编清单在移植时逐条对**：罐装反应句/比喻词/嵌套引号/段首同词等 renwei 未列项并入 findings 规则集）。
- prompts 私有仓：`polish_text.prompt` 退役（独立 PR，先合 C 端退役、后发 prompts 包下架——顺序钉死避免新包引用旧端点）。
- 挂账 change：删除 `openspec/changes/c-polish-v5-diagnostic-gate/` 与 `openspec/changes/c-deai-wizard-keep-advance/`（撤销记录写入本 change design；v5 的六类病灶诊断知识由 renwei findings 规则与生成侧红线承接）。
- spec 卫生：本 change 的 6 份 delta 之外，workbench/prose-writing 正文中的**纯历史提法**（如「去AI味采纳后的持久化」列举）不逐条回改——退役语义以 delta 为准；归档时由 archive 流程合并进主 spec。

### D6 权衡记录
- 检测不用 AI：数得出的是规则强项；循环体验依赖零成本；语义层由章节体检/朱雀分工（详见会话评估记录）。若未来规则穷尽仍有残留误差，出路是朱雀级模型训练，不是本功能范围。
- 报告不落档：免费即时重算使落档无必要；「同书对照/趋势」若立项再引入轻量表。
- 边注不用朱雀式段落胶囊：左右分边注已拍板（用户 2026-10-17 二次迭代定稿）。

## Risks / Trade-offs

- 词表移植后的密度类指标与原型演示值会有偏移（词表规模不同）——以实现对拍钉住方向，绝对值差异在报告语义内可接受（分数带自校准空间）。
- 基线来自网文拆文库，题材偏移已在算法文档警示——报告在题材敏感项标注「题材敏感」。
- 退役涉及跨仓（prompts），发版顺序必须 C 端先合、prompts 包后下架，反向会出现端点 404。

## Migration Plan

纯新增＋纯下线，无数据迁移。次序：后端 renwei 引擎与端点 → 前端新 UI → 前端退役向导 → 后端下线 polish/ai-flavor-scan → prompts 仓退役 PR。每步独立可回滚（退役步骤的最后一步前，旧链路保持完整可回）。


## Implementation Notes (2026-10-18)

- **词表来源偏差**：资产包未携带 `_人味指纹.py`，`renwei_lexicon.py` 按方法论口径重建并按基线校准（虚词窄集对齐 208±14）；单文件可替换，扩表须真人样本重校。
- **规则收编取舍**：不收编 `ellipsis_misuse`（与基线相悖）与 `simile_word`（基線不惩罚）；其余规则全收编。
- **标注机制**：段落色＝TipTap node decoration（独立 PluginKey）；边注＝React 覆盖层（spec 要求「独立覆盖层、不锁死正文」，覆盖层＋滚动重算直接满足）。
- **徽章位置**：编辑工具行（`.ol-top edit-bar`）而非章头——避免跨组件传态。
- **连带清理**：`ai-polish` entitlement、升级弹窗权益文案、`write/auxiliary.polish_text`、前端 polish API 同批下线。

## Open Questions

- 边注会话态是否随章留存（当前：不落库、会话内有效）——实现期如需持久化再立项。
- 权重反校准的数据口子（真检结果记录）——长期项，不进一期。
