# 四档改造 · 三视角评审（前端/后端/架构）点位清单

日期：2026-09-30 ｜ 上游方案：[pricing-tiers-launch-promo.md §6](pricing-tiers-launch-promo.md) ｜ 性质：工程评审底稿（openspec propose 的直接输入）

## 0. TL;DR

- **工程主体**：把 C端 49 处二元会员门重排为按 feature key 门禁；机制地基（快照契约、useFeature、数据驱动目录）全部现成。**后端 3.5–5 人日＋前端（含 S端门户与 e2e）6–8 人日 ≈ 合计 10–14 人日**（单人约两周，两人一周余）。
- **三个推翻 PRD 假设的实锤**：① 朱雀检测已合入主干且现挂 PRO（不是"在途"），四档要真上收 MAX（后端门，非前端判定）；② 新增 key 是 **5 个**不是 4 个（style-quant 漏算）；③ 三处档位枚举是隐藏雷：C端 `FALLBACK_MEMBER_TIERS` 是**准入闸**（在快照判定之前，缺 standard 则标准用户即使快照完整也判免费）、S端 `_TIER_RANK` 缺 standard 会把 standard 码算成 none（买了不生效）、C端无快照第 4 分支只给 is_member 不给 features（feature 门会全锁死）。
- **红线一条**：standard SKU 开卖之前，新版 C端 必须已全量发布——旧版 C端 只判会员白名单，standard 用户会被当免费（付费即残废）。
- **发布编排**：B1 契约→B2 S端配置（SKU 不上架）→B3 C端守门 key 化（真拦截）→B4 SKU 上架（翻转点）→B5 前端多态→B6 收银台/法律/e2e 基线。B3 不得早于 B2。零用户期不做灰度（配置级分步已等效）。

## 1. 端点 × key 全量盘点（49 处声明点）

改法推荐：**单符号守门＋路由装饰器标注 key**（`fn.__ai_feature__`，守门函数从路由元数据读）——不要用工厂函数，否则 26 个测试文件约 35 处 `dependency_overrides[require_ai_access]` 静默失配（100+ 用例连锁红）。403 语义分两层：非会员保留 `member_required`（前端零改）；会员但档位不够新增 `feature_required`（带 `feature`/`tier_required`，前端按档出文案）。

| key（档位） | 端点 | 位置 |
|---|---|---|
| **ai-generate**（PRO+）6 处 | 正文生成/续写/润色(去AI味)/压缩/扩写/提示词润色 | client/backend/write/router.py:314,384,420,483,546,205 |
| **prompt-panel**（PRO+）5 处 | 章提示词四端点＋GET /write/prompt | client/backend/prompt/router.py:31,58,86,117；write/router.py:156 |
| **ai-plan**（标准+）10 处 | 卷三套走法/铺空缺/**卷体检(现状免费,收标准)**/拆章三方向/帮写剧情三选一/章纲补缺/起草/**人物盘点抽卡**/**盘点只读(现状免费,收标准)**/建书元信息建议 | volumes/ai_plan.py:554,698,820；chapters/ai_plan.py:522；chapters/ai_plot.py:126；chapters/ai_draft.py:193,321；chapters/ai_cast.py:715,597；novels/router.py:146 |
| **chapter-review**（标准+）1 处 | **章自检 AI 短评(现状免费,收标准)** | chapters/ai_plan.py:688 |
| **settings-ai-fields**（标准+）10 处 | 设定域全家（简介/世界×3/主线/伏笔/字段生成/角色×3） | settings/ai_router.py:416,608,711,871,1073,1384,2047；settings/characters_ai.py:122,274,458 |
| **style-quant**（标准+，新 key）3 处 | 文风蒸馏/文风建议/章内文风建议 | settings/ai_router.py:1824,1950；write/style_shadow.py:116 |
| **ai-plot**（仅 MAX，新 key）9 处 | **剧情推演/六类冲突检测（整端点上收，见待拍板#1）**/story 推演七端点 | write/plot_sim.py:203；write/ai_check.py:132；story/router.py:29,75,91,107,123,141,161 |
| **ai-detect**（仅 MAX；**现状挂 PRO，上收**）4 处 | 朱雀执行＋config 增删/test | client/backend/zhuque/router.py:128,82,100,109 |
| **撤门→归档AI免费** 4 处 | reconcile accept/reject/run＋dossier 收尾闸（ai_access_granted 短路删） | archive/reconcile_router.py:106,133,148；archive/dossier.py:325 |
| **撤门→本地免费** 1 处 | quality-check（纯本地规则零 AI，却挂会员门） | write/router.py:33 |
| 确认无门（不动） | 四域提取/next-chapter-anchor/plan-card/文风基线存取 | archive/dossier_router.py:240,269,293；chapters/ai_plan.py:492,635；settings/style_quant_router.py:36,48,71 |

## 2. 判定链与兜底（三处枚举雷，必须同批改）

| # | 位置 | 动什么 |
|---|---|---|
| A | client/backend/auth_local/service.py:652 | **分支结构改造**：`FALLBACK_MEMBER_TIERS` 名单当准入闸用在快照之前——改为「none/free 走免费基线，其余档位一律进快照判定」，名单补 standard |
| B | server/app/domain/payments/pricing.py:59-65 | `_TIER_RANK` 插 standard=15，否则 standard 码被 `resolve_effective_tier` 算成 none（check-auth 下发 tier=none，权益不生效） |
| C | client/backend/auth_local/service.py:687-689 | 无快照第 4 分支（is_member=true 但无 features）按档位标准表**合成 features**，否则 feature 门全锁死 |
| D | service.py:119-133 | STANDARD_FALLBACK 补 standard 行；pro 行摘 ai-detect；max 行补 ai-plot/ai-detect |
| E | service.py:466-467 | 离线沿用旧快照：旧 PRO 快照含 ai-detect，四档后离线窗内 PRO 仍可用朱雀（偏宽），刷新自愈，记录接受 |
| F | auth_local/deps.py:168-170 | 建书满额文案硬编码「免费用户最多 N 个」→ 按 tier 出双文案 |

S端配置批：config.py:219-250（TIER_POLICY 插 standard＋ENTITLEMENT_DEFAULTS 五处）、pricing.py rank、tiers/skus 种子 SQL（standard/max 转live；SKU 先不上架）、docs/contracts/entitlement-defaults.json 升 v2（trial 行=pro 减 ai-plot/ai-detect，**现状 trial 含 ai-detect 必须移除**）。注册试用判定零改动（trial 行内容改即可）。

## 3. 前端点位（C端 React＋S端 Vue）

机制层先行：features.ts 注册表 `memberOnly:boolean`→`minTier:"standard"|"pro"|"max"`＋新增 4 key＋ai-detect 注释改回 MAX（:45-48 现有"下放 PRO"过渡语要删）；LicenseProvider.tsx:191 `isPro: isMember` 改 `tier∈{pro,max}`——**最大语义坑，不改则标准用户 UI 全量白嫖**（后端拦但 UI 不锁）；lib/tier.ts 档位文案单源（standard 会裸显英文 "standard"，BookPrefsModal.tsx:151 现状就是）；api.ts:191-206 双 reason 兼容；MemberBlockPrompt/UpgradeModal 按 tier_required 出三版。

主要点位（量级 S≤0.5h/M≤0.5d/L≥1d）：

| 块 | 要点 | 量级 |
|---|---|---|
| AiAssistPanel（最大单点） | :315 整卡门禁按页签拆 key；og 行级映射：simulate(:369)/conflict(:400)→ai-plot，draft/fill/plot-draw→ai-plan，cast-review(:388)→ai-plan（**免费从可点变锁**）；prose→ai-generate；朱雀行文案 :468/:475/:501 改 MAX | L |
| 卷/章规划 | VolumeAssistPanel :232 拆章锁 isPro→ai-plan；**:213 卷体检 aiState="ready" 硬编码→新锁点**；VolumePlanModal :149 铺空缺→ai-plan；useVolumePlan.open 的 isPro 参数语义改 hasAiPlan；ChapterPlanModal :202「AI 看一眼」免费→chapter-review 新加锁 | M×4 |
| 盘点 | useCastReview startDraw 门→ai-plan；**drawSession.ts:131 `trimCastSessionForTier(s,isPro)` 传参不改则标准用户恢复抽卡会话丢卡面（功能 bug）** | M |
| 设定域/文风 | AiWriterAssistant 锁卡文案分档；5 处表单「升级 PRO」文案走单源 helper；StyleShadowPane→style-quant | M |
| 归档收尾放开 | ReconcilePane.tsx 删三处 `!isPro`（免费渲染＋5s 轮询）；Rail 传参；modals.tsx :305「归档收尾（PRO）」改全档口径 | S |
| 书架/建书 | 上限五处硬编码（NovelListPage.tsx:243,542,707、CreateProjectModal.tsx:93,135）→ `limits.max_projects` 单源；三条账号横幅＋「试用内可用全部 AI 功能」文案与 trial=pro 矛盾要改 | M |
| S端门户 | CashierPage.vue:599 `repeat(3,1fr)`→4；FALLBACK_FEATS 四档化（现 max 卖点「更强模型·多章连写」与真实权益不符要重写）；MAX planned→live **前端零逻辑**（数据驱动自动转可选卡）；试用口径五处统一「PRO 同权（不含 MAX 件）」 | S×n |

**e2e 估红**（约 8-10 spec）：reconcile.spec 免费不渲染断言**必红（行为反转）**；plot-sim trial 会话失权（trial 不含 ai-plot）；story-arc 403 桩 reason 判等断崖；design-parity-book 像素基线（原型 book.html 同批改＋重录）；zhuque 种子权益；**11 个 spec 各自复制的 writeOAuthSession(tier) 需要一个「按档种子」helper**（注入 features）——一次投入全档场景受益。

## 4. spec delta 底稿（openspec change 输入）

| spec | 动作 | 要点 |
|---|---|---|
| tier-gating | MODIFIED | Feature registry 重构（minTier 分级，判定权仍在快照——"vocabulary not authority"不破）；锁定指示档位感知多态；ai-detect 场景改「仅 MAX（trial 也不含）」；isPro/isMember 等价拆开补场景；ADDED 归档收尾免费放开 |
| tier-access | MODIFIED+ADDED | **bypass predicate 最尖锐修正**：名单 SHALL NOT 出现在快照存在的主判定路径（现状违反，见 §2-A）；ADDED 按 feature key 的 AI 门禁总则（49 声明点契约归宿＋403 feature_required 契约）；Archive is free 撤门 |
| entitlement-sync | MODIFIED | 默认表枚举扩五档；trial 行语义显式化（pro 减 ai-plot/ai-detect）；无快照兜底名单＋镜像补 standard；features 纯增 key 属兼容变更注记 |
| s-payments | MODIFIED+ADDED | ADDED tier_rank 等级序 Requirement（standard=15，License.merge/tier 归属依赖）；目录三档矩阵场景补 standard/max 转 live；订单/退款零冲击 |
| s-pay-cashier | MODIFIED | 四档对比列；换档引导补 standard→PRO 场景；agreement_version 换版触发 |
| s-landing-pricing | MODIFIED | 四档；MAX 预告卡双分支（朱雀赶上→live；赶不上→planned 且文案不承诺含检测）；免费列 CTA 与试用时长联动 |

## 5. key 词汇表治理（五处散布＋SOP）

一个 key 的存在散在五处：features.ts（词汇表）／entitlement-defaults.json（对拍基准）／C端 49 处端点声明（**门卫映射，本次新增，无机械保护**）／S端 ENTITLEMENT_DEFAULTS（兜底）／DB tiers 行（运行时唯一发放事实源）。**不收拢单源**（DB 发放事实源原则不破），治理靠两件：① 「加新功能 key」SOP 六步（openspec 登记→features.ts→contract v+1→S端 DEFAULTS→**端点装饰器＋对拍测试同批**→DB 插行），写入 contract 文件注释；② **端点 key ∈ 词汇表的对拍测试**（扫描路由表断言）——唯一新增机械件，把第 3 处漂移从无保护变 CI 保护。顺序强制：装饰器与 features.ts 必须同批（否则「快照发了 key、端点没挂门」静默空窗）。

## 6. 发布编排（翻转点 = SKU on_sale）

| 批 | 内容 | 门禁 |
|---|---|---|
| B1 契约先行 | openspec change（六 spec）＋contract v2＋features.ts＋require_feature 原语与对拍测试 | vitest＋pytest 全量不红 |
| B2 S端配置 | DEFAULTS/rank/TIER_POLICY＋DB tiers/skus 插行（**SKU 全部不上架**） | server pytest＋对拍＋/pay/skus 目检（standard 预告卡态） |
| B3 C端守门 key 化 | 49 声明点真拦截＋撤门 5 处＋三枚举雷同批修 | pytest 全量＋e2e 现有 44 spec 零红（等价性证明） |
| B4 翻转（业务） | standard/max SKU 上架＋rehearsal 各走一单 | 支付演练台账＋目检 |
| B5 前端多态 | 锁定 UI/文案分档/归档放开 | vitest＋e2e 补 standard/max 视角 |
| B6 收尾 | 收银台四列/法律换版/e2e 基线重录 | 全量绿 |

B3 不得早于 B2（唯一会出线上事故的排序）。前端多态（B5）晚于 B4 可容忍（方向偏保守）。

## 7. 反逆向裁剪（本次做/不做）

做：守门 key 化（判定面 49 处散点收敛为 1 个可替换点——未来一切服务端仲裁的结构前提）；wrapped_key 接口约束写进 spec（SHALL 走 features 非空语义，MUST NOT 写 tier 白名单）。不做：快照验签（等任务一 ed25519 烘包顺带）、Nuitka 编译加固（**建议首发引流前完成，独立排期**）、提示词分区钥/wrapped_key 实现（依赖任务一；四档上线后的白嫖取证反哺它）、S端 AI 代理（09-28 已拍不做）。分区钥按 free/paid 二分，不随四档扩四分区。

## 8. 评审新增的待拍板（合并进产品底稿 §7）

| # | 决策点 | 建议 |
|---|---|---|
| 10 | ai_check 六类冲突检测是一个端点带 kind 参数 | **整端点挂 ai-plot（MAX）**，不拆 kind 级门（不值复杂度） |
| 11 | quality-check 纯本地规则却挂会员门 | 撤门归免费（顺手修正） |
| 12 | workflow/ai-backfill 两端点无门但真调 AI（裸奔） | 挂 ai-plan 或明确设计为免费导入辅助（二选一） |
| 13 | 建书元信息建议 suggest-meta | 归 ai-plan（顺带核对其 require_project_limit 依赖语义） |
| 14 | ProContainer（PRO 阶段催促卡）是否对标准档放开 | 默认维持 PRO 起（isFree 判定不动），PM 定 |
| 15 | 收银台 popular_sku 默认指向 | standard live 后是否改指 standard（产品定） |

## 9. 零代码运营目标（用户拍板 09-30：销售侧一切变化不得改代码）

原 §2 方案留了两处档位枚举在代码（S端 `_TIER_RANK`、C端 `STANDARD_FALLBACK` 按档名写死）——新增第五档仍要碰代码。按拍板升级设计：

| 原方案 | 零代码方案 |
|---|---|
| S端 `_TIER_RANK` 代码常量（pricing.py:59-65） | rank 改从 **DB `tiers.rank` 列**读（列已存在）；代码常量退役为 DB 不可用时的已知档兜底 |
| C端 `STANDARD_FALLBACK` 五档写死（service.py:119-133） | 改为**档位目录缓存**：S端 check-auth/verify 响应附带 tier→features 目录（tiers 表投影），C端缓存之；无快照时按目录兜底。新档位＝S端插行，C端自动认识 |
| `FALLBACK_MEMBER_TIERS` 名单（本次本就要改） | 分支改造为**通用规则**：「none/free → 免费基线；其余任何档名 → 进快照/目录判定」——永不因新档名改代码 |
| 前端 tier.ts 档位文案写死「标准会员/PRO 会员」 | `display_name` 随快照下发（tiers.display_name 列已有），前端只渲染 |
| TIER_POLICY 代码表（config.py:219-230，含 device_limit/duration_days） | **整体退役**：device_limit、duration_days（trial 时长）升为 tiers 表列（一次性 DDL），代码只留兜底；§7-5 试用延长从此也是改库 |

**有意保留在代码的（不是欠账）**：① 端点→key 声明（门牌）——新功能上线时随功能代码写一次；门禁是安全面，端点→key 放 DB 意味着配置错字＝静默开洞且无编译期保护，§5 的对拍测试就是为它设的。② none/free 免费基线——产品常量，不是销售配置。

**结果矩阵**：

| 运营动作 | 改代码？ |
|---|---|
| 调价/折扣/上下架 SKU | 零（现状已支持） |
| 档位权益调整（key 分配/max_projects/设备数/试用时长） | 零（改 tiers 行即生效） |
| 新增/退役档位 | 零（DB 插行，rank/display_name/entitlement 同行配置） |
| 上线全新功能 | 功能代码本身要发版（不可免）；key 声明随功能写一次（一行），**之后分给哪档零代码** |

对改造量的影响：后端 +0.5–1 人日（DDL＋rank/limits 改读 DB＋目录下发＋C端目录缓存），前端 tier.ts 文案改读 display_name（含在原 M 档内）。评审红线不变：standard SKU 开卖前新版 C端 必须全量发布。
