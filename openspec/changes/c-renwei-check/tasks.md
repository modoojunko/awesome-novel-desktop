# Tasks: c-renwei-check

## 1. 后端检测引擎

- [x] 1.1 移植词表：新建 `client/backend/write/renwei_lexicon.py`，从资产包 `_人味指纹.py` 全量移植虚词/抽象名词/具体名词/转场词/感官分类词表（对照 `docs/design-c/drafts/check-renwei-demo.py` 的最小演示词表逐组扩容）
- [x] 1.2 冻结基线常量表：`renwei_baseline.py`——19 项 mean±SD＋P25–P75＋权重（3/2/1/不计分），来源《人类样本指标参考_320章》《可量化标准总表》
- [x] 1.3 检测引擎 `client/backend/write/renwei_check.py`：以 check-renwei-demo.py 为底移植纯函数 `check_prose(text)`——19 项指纹、人味率（≥1,500 字门槛＋MTLD/Hapax 2,000 字收敛门槛）、修稿优先级（权重×|z| top3）、定位 findings（正则类到词/窗口类到段/整章类不定位）
- [x] 1.4 收编清单对齐：ai-flavor-scan 的规则逐条并入 findings 规则集（罐装反应句/比喻词/嵌套引号/相邻段首同词等），逐条核对不遗漏
- [x] 1.5 `tests/test_renwei_check.py`：人造「像人段/机器味段」逐指标方向钉（防写反）；基线表完整性；豁免规则（专名/口头禅）；≥1,500/2,000 字门槛语义；优先级排序
- [x] 1.6 对拍工具：check-renwei-demo.py 升级为参考实现 vs 生产引擎的同输入对拍（指标差超容差即红），进 CI 或留本地验收钉

## 2. 检测端点

- [x] 2.1 `POST /api/novels/{id}/chapters/{ref}/renwei-check`：只挂登录；读盘正文；调引擎同步返回（人味率/优先级/指纹表/findings/字数）；不进 TokenLog
- [x] 2.2 短章语义：<1,500 字返回「打不了分」标记（score=null），findings/不计分项照常
- [x] 2.3 端点测试：登录门、404 章、空正文、契约钉（响应形状）

## 3. 前端：入口与四拍报告弹窗

- [x] 3.1 右栏检测区「人味检测」行（朱雀行之下）：「本地 · 免费」标注、无门控分支、文案按设计说明作家口径
- [x] 3.2 `RenweiCheckModal` 四拍状态机：说明页（流程图：验→查→改→再验＋循环回线）→ 运行态 → 结果页 → 标记到正文；脚部按钮随态切换
- [x] 3.3 结果页渲染：人味率头卡（档位胶囊 ok/warn/err）＋先改这几处（<70% 时）＋定位问题清单（段号/摘录高亮/为什么/改法）＋整章对照表（真人常见范围＋分量 高中低）
- [x] 3.4 文案审查：全界面零实现词汇（指纹/基线/权重/额度/P25），对照设计说明 §3.0
- [x] 3.5 vitest：弹窗三态、结果渲染、空结果文案、短章「打不了分」

## 4. 前端：左右分边注与逐段重扫

- [x] 4.1 TipTap 标注 Extension（独立 PluginKey）：段色 node decoration＋边注 widget decoration；遵守 zhuqueMarks 两条实测坑（DecorationSet 住 plugin state、widget 函数形态 toDOM＋稳定 key）
- [x] 4.2 左右分边注布局：朱雀胶囊左移（margin 态）、人味边注右贴边自适应空白换行、正文锁死（无横向滚动、位置与阅读态一致）——窄窗（中栏 <950px）回退为段角胶囊＋浮层
- [x] 4.3 悬停详情卡（为什么/改法/标为已改/跳过）＋「标记到正文」上屏动作（结果页触发）
- [x] 4.4 逐段重扫：编辑防抖 0.7s → 整章重算 → 精准消卡（带标注段通过即消，其余保留）；无标注段修改＝全部失效提示重测；跳过语义
- [x] 4.5 章头「人味改稿 n/10」徽章：实时进度、清零转绿＋朱雀重检提示光圈＋引导 toast
- [x] 4.6 vitest：边注上屏/消卡/跳过/徽章/朱雀置灰不受人味检测影响的独立性钉

## 5. 退役：去AI味改写链

- [x] 5.1 前端：删 PolishWizard 及调用链、右栏 ai-polish 卡、openPolishWizard；相关 vitest 用例删除或改写
- [x] 5.2 后端：删 `/write/polish`、`/ai-flavor-scan` 端点与 schema、`quick_verdict`、ai-flavor-scan 规则（先完成 1.4 收编核对再删）
- [x] 5.3 e2e：删除/改写涉 polish 用例；free-writing-flow 全量回归
- [ ] 5.4 prompts 私有仓：`polish_text.prompt` 退役 PR（sync/manifest 同批）；**发版顺序＝C 端先合，prompts 包后下架**（跨仓，须在 prompts 仓单独开工单；本仓已下线端点，旧包模板成为死资源，等 prompts PR 合入后随下次发包清出）
- [x] 5.5 挂账 change 处置：删除 `openspec/changes/c-polish-v5-diagnostic-gate/` 与 `c-deai-wizard-keep-advance/`，处置记录留本 change design.md
- [x] 5.6 spec 卫生巡检：全仓代码/文案残留「去AI味」入口类提法清点（历史提法不强制回改，入口类必须清）

## 6. 门禁与验收

- [x] 6.1 后端：pytest 全绿＋覆盖率门（新增模块 coverage 达标）
- [x] 6.2 前端：vitest＋tsc＋build 绿
- [x] 6.3 `openspec validate c-renwei-check` 通过
- [ ] 6.4 手工验收：按用户故事地图走全循环——验（朱雀）→查（检测报告）→改（边注逐条＋逐段重扫）→再验；短章/干净章/机器味章三态核对（需独立栈起真机；原型四屏与交互已逐条截图验收，见设计说明 §6）
- [ ] 6.5 设计对照：实现与原型（ai-novel-c端-人味检测-原型.html）逐屏对拍；文案对照设计说明 §3.0 基调（文案与结构已按原型落成，逐屏像素对拍随 6.4 真机验收一并联调）


## 实施偏差登记（2026-10-18）

- **1.1 词表来源**：资产包 zip 未携带作者原 `_人味指纹.py`（包内仅 `_precheck.py`）——词表按三份方法论文档口径＋标准汉语功能字集重建，并以「与 208±14 基线同量级」校准（宽表实测虚词 300+、具体名词 87/千，会系统性高估）。单文件 `renwei_lexicon.py` 可整体替换：拿到作者全量词表后只改此文件。**扩表须用真人样本重校，不得凭感觉加词**。
- **1.4 规则收编取舍**：`ellipsis_misuse`（叙述句省略号）**不收编**——作者自有书规「省略号只留独立成段与引号内」与 320 章人味基线（真人叙述省略号 17.3/千）相悖，收编会在干净章刷 26 条误报。`simile_word`（单比喻词）不收编（基线不惩罚比喻），只留 `simile_chain`（同句两个比喻词）。其余规则全收编。
- **4.1 标注机制**：段落标色用 TipTap node decoration（独立 PluginKey，照 zhuqueMarks 两条实测坑）；**边注用 React 覆盖层**（而非 widget decoration）——spec 的要求是「独立覆盖层、不占布局流、正文锁死」，覆盖层＋滚动重算直接满足，且交互按钮无需在 ProseMirror 内造 React 根。
- **4.5 徽章位置**：回落到编辑工具行（`.ol-top edit-bar` 右侧「人味改稿 n/N」）而非章头 `.e-head`——e-head 由 ChapterWorkspace 持有（朱雀结果条同处），跨组件传状态成本高；编辑工具行与「正在编辑正文」同行，作家改稿时始终可见。
- **退役超出 delta 枚举的部分**：`write/auxiliary.polish_text`、`lib/ai.ts` 的 polishText/polishTextDetail/aiFlavorScan、`ai-polish` entitlement（`auth_local/service.py` + `docs/contracts/entitlement-defaults.json`）、升级弹窗/提示词包文案中的「去AI味」权益行——均属退役链的连带清理，随本 change 同批。
- **测试替换**：`PolishWizard.test.tsx`、`test_ai_flavor_scan.py`、`test_write_transform_modes.py` 随功能删除；`test_write_routes_contract.py` 增加 `/write/polish` 防回潮钉；门禁矩阵/注册表/entitlement 测试同步去 `ai-polish`。
