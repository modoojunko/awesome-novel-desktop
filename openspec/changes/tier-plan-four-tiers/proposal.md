# Proposal: tier-plan-four-tiers

## Why

产品拍板套餐从「免费/PRO」二元制升级为**免费/标准/PRO/MAX 四档**（免费=体验流程＋归档 AI；标准=AI 帮搞流程、正文自己写；PRO=正文都 AI 写；MAX=剧情规划＋朱雀检测），第一波宣传在即。但 C端 守门现状是「会员/非会员」二元拦截——标准档一上线就会被全量放行 AI；同时三处档位枚举散在代码里（C端 兜底名单/兜底表、S端 rank 表），每加一档都要发版，与「销售侧变化零代码」的运营目标冲突。

## What Changes

- **C端 守门 key 化**：`require_ai_access` 从二元会员门升级为按 feature key 门禁（49 处声明点逐点标 key；单符号＋路由装饰器方案，不做工厂函数）；403 语义分层——非会员保留 `member_required`，会员但档位不够新增 `feature_required`（携带 `feature`/`tier_required`）。
- **feature key 词汇表扩容**（2026-10-05 拍板口径）：新增 `ai-plan`（卷规划/拆章/章纲起草/卷体检/人物盘点，标准）/`chapter-review`（章自检短评，标准）/`style-suggest`（文风建议，标准）/`style-quant`（文风蒸馏——与建议拆 key，MAX）/`ai-polish`（去AI味加工，MAX）/`ai-plot`（剧情推演，MAX）；`ai-detect`（朱雀检测）**留 PRO**（trial 同权，不上收）；归档 AI 全家（收尾提案）撤门归免费。
- **四档权益矩阵落地**（月价 29.9/59.9/89.9，季/年未拍首发只插月付行）：免费（全流程人工＋归档 AI，1 本）/标准（流程 AI＋设定域 AI＋人物盘点＋文风建议，3 本）/PRO（＋正文 AI＋朱雀检测＋提示词页签，不限书 3 设备）/MAX（＋剧情推演＋去AI味＋文风蒸馏＋拆书＋人工客服＋内测，10 设备）；trial=同 PRO（含朱雀）。
- **零代码运营目标（用户拍板）**：销售侧一切变化（调价/折扣/上下架/档位权益调整/新增退役档位/试用时长/设备数）改库即生效——S端 rank 改读 DB `tiers.rank` 列、C端 `STANDARD_FALLBACK` 改为「档位目录缓存」（S端 响应附带 tier→features 目录）、`FALLBACK_MEMBER_TIERS` 分支改通用规则、`display_name` 随快照下发、TIER_POLICY 的 device_limit/duration_days 升 tiers 表列后整体退役。
- **C端 前端多态化**：`isPro===isMember` 拆开（tier 判定）、锁定 UI 从二态改「需开通/PRO 专属/MAX 专属」多态、文案分档单源 helper、归档收尾面板对免费档放开、建书上限改 `limits.max_projects` 单源。
- **S端**：tiers/skus 插行（standard rank=15；MAX 转 live）、entitlement-defaults.json 升 v2、收银台/落地页四档列（数据驱动，前端仅断点与兜底卖点文案）。
- 判定链三处枚举雷同批修（C端 准入闸分支结构、S端 rank 缺 standard、C端 无快照分支合成 features）。

**BREAKING**：卷体检/章自检短评/人物盘点从免费收进标准档（现状免费的 AI 只读例外收走）；设定域 AI（settings-ai-fields）从 PRO 下放标准（放宽非破坏）。朱雀检测留 PRO（2026-10-05 拍板，撤销早前「上收 MAX」草案）。

## Capabilities

### New Capabilities

- `tier-catalog`: 档位目录数据驱动——tiers 表为档位唯一事实源（rank/entitlement/display_name/device_limit/duration_days），S端 下发档位目录投影，C端 缓存兜底；新增/调整/退役档位零代码（运营改库即生效）。

### Modified Capabilities

- `tier-gating`: Feature registry 从布尔分级为 minTier（useFeature/useTier 兜底改目录缓存口径）；锁定指示档位感知多态；ai-detect 场景改「PRO 起（trial 同权）」；isPro/isMember 等价拆开；ADDED 档位显示名单源渲染。
- `tier-access`: bypass predicate 修正（档位名单 SHALL NOT 出现在快照存在的主判定路径＋通用分支规则）；ADDED 按 feature key 的 AI 门禁总则（44 声明点契约归宿＋feature_required 403 契约）；归档收尾撤 ai_access_granted 门。
- `entitlement-sync`: 默认表/兜底镜像扩四档；trial 行语义显式化（=pro 减 ai-plot/ai-detect）；快照异常三段式兜底源改档位目录缓存；无快照兜底补 standard。
- `tier-catalog` 之外的判定链：`s-payments` ADDED tier rank 消费行为（等级序机制归 tier-catalog）＋商品目录四档矩阵场景。
- `s-pay-cashier`: 三档对比列→四档（数据驱动出列）；「当前方案」标注按登录态实际档位。
- `s-landing-pricing`: 三档→四档；免费列卖点口径改「人工写作免费＋归档 AI 免费」；注册导流文案去试用天数硬编码。
- `design-system`: 档位徽标五态与档位感知锁文案（minTier 单源 helper、display_name 渲染）。
- **功能 spec 档位口径同步（BREAKING 落点）**：`archive-reconcile`/`chapter-dossier`（收尾提案撤门归免费）、`volume-plan-ai`（生成类/体检归 ai-plan）、`chapter-plan-ai`（拆章 AI 归 ai-plan、章自检归 chapter-review）、`chapter-cast-review`（盘点/抽卡归 ai-plan）、`zhuque-detection`/`zhuque-config`/`zhuque-workbench`（ai-detect 留 PRO＋trial 同权、后端真门维持、锁定文案「PRO 专属」、试用可见可用）、`plot-sim`（推演归 ai-plot）、`workbench`（推演/文风建议/帮写剧情/归档预览/ra-head 副行五处口径）、`account-control-center`（徽章五态＋display_name 单源）、`intro-genre-settings`/`storyline-settings`（统一升级提示改档位感知单源 helper）、`chapter-data`（质量检查撤门后入口全档可见）。
- 判定链三处枚举雷同批修（C端 准入闸分支结构、S端 rank 缺 standard、C端 无快照分支合成 features）。

## Impact

- **代码**：client/backend（auth_local deps/service、44 处 AI 端点声明点装饰器＋撤门 3 处、tier_catalog 透出与前端通道）、client/frontend（features.ts/LicenseProvider/useTier/AiAssistPanel 等锁定面、ReconcilePane 放开、文案单源 helper）、server/app（config DEFAULTS/TIER_POLICY 退役＋消费方迁移、rank 读 DB＋TTL 缓存、目录下发）、server/frontend（收银台/落地页四列）。
- **数据**：tiers 表 DDL（+device_limit/duration_days 列）＋standard/max 插行（B2 期间保持 planned，B4 转 live；standard rank=15）；skus 首发插月付 3 行（29.9/59.9/89.9 分，**sort 排 pro 之后防 popular 抢占**；季/年未拍后续插行）；entitlement-defaults.json v2。**popular_sku 显式留 PRO**（用户拍板；机制上取第一个年付 SKU，插行须防 sort 撞出换档）。
- **测试**：pytest 语义翻转 8–12 文件＋新增约 20 门禁单测＋端点 key∈词汇表对拍测试（新机械件）；e2e 约 8–10 spec 修复（reconcile 行为反转/plot-sim trial 失权/story-arc 403 断崖/design-parity 基线重录＋原型行集同步）＋按档会话种子 helper（19 个 spec 副本收敛）。
- **法务/文案**：付费须知、退款政策换版（agreement_version 升版）；「试用可用全部 AI」等既有文案与新权益矩阵对齐。
- **红线**：standard SKU 开卖（B4）前新版 C端 必须全量发布；B3 守门 key 化不得早于 B2 S端 配置。
- **工作底稿**：[docs/prd/pricing-tiers-launch-promo.md](../../../docs/prd/pricing-tiers-launch-promo.md)（产品，§6.2/§6.3/§6.4 需按 10-05 拍板刷 v3）、[docs/prd/four-tier-gating-review.md](../../../docs/prd/four-tier-gating-review.md)（三视角评审）、S端上线架构评估（2026-10-05 会话：`_TIER_RANK` 缺 standard=付费用户全设备停用／C端 fail-closed 实证／popular sort 暗雷——B1 三件代码与上线步骤以此为准）。

## Design Impact

- **受影响端**：双端。C端：书架（横幅/档位徽章/满额文案/建书上限）、工作台右栏 AiAssistPanel（锁定行多态）、卷规划台/拆章/盘点（锁点重排：卷体检与盘点从免费变锁标准、推演/冲突变锁 MAX）、设定域（锁卡文案分档）、归档弹窗与收尾面板（免费放开）、升级弹窗（三版）、账号菜单/偏好弹窗（档位名）。S端：收银台四列、落地页套餐区四列、免费列卖点文案。
- **对象状态**：新增「档位锁定」多态——同一锁定行对免费/标准/PRO 分别呈现「需开通/PRO 专属/MAX 专属」（对照状态语言总表 locked 族扩展）；归档收尾从 PRO-only 状态转全档可用（状态语言无新增，入口态变化）。
- **共享段**：不触碰两端共享的令牌/基础类逐字段（L1）；档位徽标（pill）扩展两档属 L2 语义类同义变更，两端同批；design-vocab.mjs 若涉及 pill 文案词表需两端同源改。
- **原型先行**：不需要新原型——锁定多态沿用现有锁定卡形态，仅文案分档；收银台四列由数据驱动自动出列，断点微调（3→4 列）按现有栅格推导。design-parity 像素基线涉及的 book.html 免费锁卡文案需同步改并重录基线。
- **设计工件产出**：实现侧自查（分档文案矩阵见三视角评审报告 §3，docs/prd/four-tier-gating-review.md；若评审时发现锁定多态需要新形态再回设计侧会话）。
