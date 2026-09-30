## Why

网文平台发布前普遍用腾讯朱雀等 AIGC 检测器把关「AI 味」，作家需要在站内自查自改。定价终拍（docs/prd/pricing-tiers-launch-promo.md §6.2/§6.4）已把朱雀检测定为 MAX 档支柱权益（feature key `ai-detect`，试用不含），现在落地整条链：配置 → 送检 → 结果展示。

## What Changes

- **模型配置页双页签**：新增「写作大模型 / 朱雀 AI 检测」页签行；「添加 API Key」按钮只属于大模型页签（切朱雀页签时隐藏）；朱雀页签内容＝介绍条 → Key 配置卡（保存并测试/掩码/更换/删除/显示开关）→「如何获取 Key」横向三步卡 → 隐私警示条，全宽布局与大模型页签同构。
- **朱雀 Key 单槽配置**：复用 `api_configs` 表、`vendor="zhuque"` 区分；加密存储/掩码/软删恢复复用既有机制；专用端点内部固定 vendor 与 base_url（用户只粘 Key）；保存＝upsert（同名软删行复活，防 409）。
- **写作模型选取路径隔离（防御）**：`ai_client` 通用选取加 `vendor != "zhuque"` 过滤，防兜底逻辑把朱雀配置当写作大模型吞用。
- **C端本地后端检测端点**：`POST /api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check`，代理腾讯 EdgeOne 网关 classify（Bearer Key）；前端零直连；段落切分由后端收口（响应给 `paragraph_index + label + confidence`，不透传 char offset）；错误映射到可展示语义（401→Key 无效、429→限流或额度耗尽、5xx/超时→可重试）；正文超上限 422；检测结果绑定送检时正文指纹（prose_hash）。
- **检测结果不落库**：仅前端内存存续（跨页签/视图切换存活、重启即弃）；归档与备份不包含任何检测数据；检测端点对章数据只读。
- **工作台三处展示**（由「在写作台显示朱雀检测」开关统一控制，默认开）：右栏正文页签末行「朱雀 AI 检测 · 查AI味」（四态：非 MAX 锁定＋MAX 专属章→统一升级出口；MAX 未配 Key→虚线引导跳「模型配置 → 朱雀」；检测中 ra-running；就绪）；章标题行右侧结果条（裸排人工/疑似/AI 三占比＋「概率参考 · 非平台判定」＋清除标注/重检；检测中/失败同位切换）；正文段落标注（TipTap Decorations：疑似/AI 段底色＋行尾置信度章，人写段灰章；正文编辑后旧标注变灰＋提示重检）。
- **门禁**：MAX 会员权益、试用不含。前端 `useFeature("ai-detect")`（快照单源，S端 entitlement 只对 MAX 发放）；C端本地后端挂会员级防御校验（与 ai-check 同源机制）；本地门禁 UX 级可绕过为 PRD §8.4 已认账口径。配置页签全档可见可配置（Key 是作家自己的腾讯资产）。
- 修改设计稿 [drafts/ai-novel-c端-朱雀检测.html](/Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/ai-novel-c端-朱雀检测.html)（v12，10 态）为本 change 的设计事实源。

## Capabilities

### New Capabilities

- `zhuque-config`: 朱雀检测的配置域——模型配置页双页签与页签级动作、Key 单槽生命周期（存/换/删/测、加密复用、软删 upsert）、显示开关（状态单源与三处消费）、配置页文案口径（MAX 权益、获取引导、隐私警示、活动额度）。
- `zhuque-detection`: 朱雀检测的执行域——C端本地后端唯一执行端点与前端零直连、写作模型选取路径的 vendor 隔离、段落切分后端收口与响应契约、错误映射、内容指纹、不落库边界、负载护栏、测试桩策略。
- `zhuque-workbench`: 朱雀检测的工作台展示域——右栏检测行四态与门禁词汇、标题区结果条三态、正文段落标注覆盖层（Decorations、变灰重检）、四消费点读同一开关。

### Modified Capabilities

- `design-system`: ADDED——「朱雀检测的组件词汇与结果呈现」：登记 zhuque 域业务词表（cfg-tabs、zq-hd 及 hd-* 行内词、zg-keyrow/zg-stats/zg-flow、zq-toggle-row、zq-mark/zq-warn/zq-err、ra-step 的 zq-guide/zq-maxlk 变体；开关对齐现役 .switch-btn 家族，不自造 .switch）；并划清「AI 结果统一出卡弹窗」条款的边界——有写回语义的 AI 产物走出卡确认，只读检测类结果（无写回）SHALL 就地呈现（标题区＋正文覆盖层），不受出卡弹窗约束（含冲突时以本条为准的优先级裁定）。
- `tier-gating`: MODIFIED——「Feature capability registry」条款的 Free-locked keys 封闭清单（SHALL be exactly）加入 `ai-detect`（MAX 专属、试用不含、快照缺失一律未授权）；全文带场景重述（features.ts 头注「加 key 先登记 specs」纪律）。

（`ai-detect` 的静态登记行为同时受 tier-gating 另一「SHALL 维护词汇表」条款约束，两条款经本次 MODIFIED 对齐，不再有封闭清单与新增 key 的矛盾。）

## Impact

- **C端前端** `client/frontend`：`pages/ApiKeyConfigPage.tsx`（双页签改造）、`components/novel/workbench/AiAssistPanel.tsx` 与 `components/novel/AiWriterAssistant.tsx`（共享组件：prose 页签新行、guide/锁定/runningHint 行变体、行级门控旁路）、`ChapterWorkspace.tsx` e-head（结果条挂点）、`ProsePane.tsx`（TipTap Decorations 扩展＋指纹失效）、`lib/features.ts`（登记 ai-detect）、`lib/prefs.ts`（显示开关持久化）、book.css / model-config.css（新业务词入册）。
- **C端本地后端** `client/backend`：新增 `zhuque/` 模块（配置路由＋classify 客户端＋段落切分）；`ai_client.py` 与 `ai_state.py` 的通用选取加 vendor 过滤、`api_configs` 列表/状态查询加同过滤（P0 防吞用与防泄漏）；`api_configs/service.py` upsert 辅助。
- **S端**：无代码改动；entitlement 快照的 `ai-detect` 发放配置归 pricing §6.5 四档改造 change（本 change 的前端判定读快照，快照未含即锁定）。
- **第三方依赖**：腾讯 EdgeOne Makers 网关（`ai-gateway.edgeone.link`，已实测可达）；每月 50 万 token 免费额度为活动口径，UI 文案一律引用式表述（「以腾讯云为准」），禁止「永久免费」表述。定价 §6.5 所指「配额」在本 change 不适用：BYOK 模式下额度与用量在作者腾讯云侧，C端仅本地留痕每次消耗（usage_tokens），平台侧配额归 pricing §6.5 四档改造。
- **测试**：pytest（切分/端点/错误映射/桩）、vitest（配置页签/开关/门禁）、e2e（配置页签切换＋添加按钮显隐、右栏行态、结果条、标注）、design:lint / design:check / design-cross（新增业务词登记后跑全门禁）。

## Design Impact

- **受影响端**：仅 C端（S端零代码改动）。
- **受影响屏/弹层**：模型配置页（页签行＋朱雀页签两态）；工作台写作视图（右栏 AI 助手卡新增行、章标题区结果条、正文编辑器标注层）；升级引导（复用既有统一升级出口，不新增弹窗）。
- **对象状态**（对照 design-language §5 状态语言总表）：检测行＝锁定（非 MAX，锁定词汇＋MAX 专属 warn 章）/引导（虚线＋可点跳转）/运行中（ra-running）/就绪；结果条＝结果（ok/warn/err 三语气占比）/检测中（prog 语义、转圈）/失败（err 红字＋按错误族可点出口「去配置」/「重试」/「关闭」）；标注＝疑似（warn 底）/AI（err 底）/过期（置灰＋可点「重检」）。语气词只用 info/ok/warn/err，无新增胶囊形态。
- **两端共享段**：不触碰 base.css 令牌与基础组件类；新增词全部落在 C端业务层（book.css / model-config.css 本地段），开关对齐现役 `.switch-btn/.sw-track/.sw-knob`（不自造 `.switch`）；登记后跑 design:lint / design:check / design-cross。
- **原型先行**：是——apply 阶段先改 `docs/design-c/prototypes/`（model-config、工作台屏）并在 ADJUSTMENTS.md 登记偏差，再动实现；`npm run design:check` 像素差 <0.2%。
- **设计工件**：设计侧会话已产出终版设计稿 [drafts/ai-novel-c端-朱雀检测.html](/Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/ai-novel-c端-朱雀检测.html)（v12，10 态，含 v1→v12 决策日志与四路评审结论）；实现侧按稿自查。
