# Tasks: tier-plan-four-tiers

编排约束（design §6）：B1→B2→B3→B4→B5→B6；**B3 不得早于 B2**；standard SKU 上架（4.x）前新版 C端 必须全量发布；B2 期间 standard/max tiers 保持 planned。每节内自上而下。

## 1. B1 契约先行（词汇表＋原语＋对拍）

- [x] 1.1 `client/frontend/src/lib/features.ts`：注册表 `memberOnly` → `minTier`（free/standard/pro/max），保留 `isMemberFeature` 兼容派生（生产零调用点、仅测试）；新增 key：ai-plan/chapter-review/style-suggest/style-quant/ai-plot/ai-polish；ai-detect 留 pro（trial 同权——删「下放 PRO」过渡注释改「PRO 起」）；style-suggest（文风建议，标准）/style-quant（文风蒸馏，MAX）拆 key；同步 features.test.ts
- [x] 1.2 `docs/contracts/entitlement-defaults.json` 升 v2：五档行（free/standard/pro/max/trial=pro 同权含 ai-detect），四端 key 全量（新增 ai-plan/chapter-review/style-suggest/style-quant/ai-plot/ai-polish）；契约文件头注释替换为「加新 key 六步 SOP」
- [x] 1.3 `server/app/config.py` ENTITLEMENT_DEFAULTS 同批对齐五档（**补 standard 行**；trial=pro 同权含 ai-detect——架构评估：缺 standard 键时快照兜底落到 none 全空，标准用户权益清零）；两端对拍测试（client test_entitlement_sync.py / server test_check_auth_extension.py、contract 对拍）随 v2 重写先红后绿
- [x] 1.4 C端 `ai_feature(key)` 路由装饰器（**setattr 后返回原函数，不做 wraps**）＋`require_ai_access` 读 `request.scope["route"].endpoint.__ai_feature__`（签名 `request: Request = None`＋getattr 防御，兼容 test_ai_member_gate.py:246 直调；依据 fastapi≥0.115 的 scope["route"]，本仓 0.128）；403 双 reason（member_required 保留＋feature_required 带 feature/tier_required；tier_required 按 tier_catalog rank 升序首个含 key 的档推导，目录缺失退 minTierOf）
- [x] 1.5 端点 key ∈ 词汇表对拍测试（扫描路由表 44 处挂点断言；新机械件）
- [x] 1.6 门禁单测：五档 × 各新 key 放行/拒绝矩阵（**必须走真实依赖＋config/快照种子，禁用 dependency_overrides**——override 会整段绕过 key 判定测不到 feature_required）

## 2. B2 S端 配置与数据（standard/max 保持 planned；SKU 不上架）

- [x] 2.1 DDL 四步：① TierORM 加 device_limit/duration_days 列（server_default 回填）② alembic 新 revision 线性挂尾 ③ **`pg_schema.REQUIRED["tiers"]`/COLUMN_DEFAULTS 同批**（漏列即红对拍）④ gen_missing_ddl.py 产出→MCP 带外应用→启动探针 run_schema_check 目检
- [x] 2.2 **TIER_POLICY 退役的消费方全量迁移**（改读 tiers 行，先 `_TIER_ALIASES` 归一再查）：`domain/licensing/tier_policy.py`、设备限额三处（application/devices/verify_license.py:75、list_devices.py:14、get_device_status.py:24）、legacy 码激活 `application/licensing/activate_code.py:25`（改 codes.duration_days，防 monthly 码激活即过期；redeem 行内 ✓ 无需动）、~~admin 发码校验 `admin_api/codes.py`~~（实勘不存在，跳过）、注册试用时长 `identity/register_user.py:56`（改读 trial 行 duration_days ✓，含 trial code duration_days 同步）；TIER_POLICY 降为 DB 不可用兜底（注意 lifetime 在 config.py:230 被加载期改写为 99，勿照抄注释值）
- [x] 2.3 **rank 读 DB**：rank map 走 TierRepo 类级 60s TTL 缓存（payments_repo.py:472 先例）、由调用方注入 merge/tier_rank（pricing.py 保持领域纯函数不直连 infrastructure）；`resolve_effective_tier` 与 `tier_rank()` 两份逻辑收敛单源；缺行 `logger.warning(event=tier_rank_missing)`＋启动告警
- [x] 2.4 tiers 数据：插 standard 行（rank=15、**status=planned**、entitlement JSON=ai-plan/chapter-review/settings-ai-fields/style-suggest/outline-advanced-fields/ai-model＋max_projects=3）；max 行 entitlement=pro+ai-plot+ai-polish+style-quant（仍 planned）；**pro 行不动**（ai-detect 留 PRO，2026-10-05 拍板）；display_name 全行核对；**插行前 SELECT 生产 tiers 核对 rank/sort 现值**（架构评估未核实项）
- [x] 2.5 skus 数据：首发只插月付 3 行（standard_monthly=2990 分/pro_monthly 维持 5990/max_monthly=8990，on_sale=false）；**sort 排 pro 现有行之后（建议 4-6，禁用默认 0）**——popular_sku 机制取第一个年付 SKU，sort 撞序会静默换档（架构评估 §四-3）；季/年卡未拍不插；PRO 年卡 device_limit 5→3（按档固定，仅展示列——实际限额走 TIER_POLICY 迁移 2.2）
- [x] 2.6 tier_catalog 下发：build_license_snapshot 共用装配点加投影（活跃档 key/rank/display_name/features）；**投影加类级 TTL 缓存**（现 find_all 无缓存）；`GET /api/pay/skus` 目检四档出列（standard/max呈预告卡态）；server pytest 全量＋对拍绿

## 3. B3 C端 守门 key 化（真拦截）

- [x] 3.1 判定链：service.py 准入闸分支重构（none/free→免费基线，其余任何档名进快照/目录判定）；**STANDARD_FALLBACK 五行全量重写**对齐 v2 默认表（standard 新增；pro=standard＋ai-generate/prompt-panel/ai-detect；max=pro＋ai-plot/ai-polish/style-quant；trial=pro 同权；与 entitlement-defaults.json 对拍）；**FALLBACK_MEMBER_TIERS 补 standard**（退役为目录皆无时的兜底）；无快照分支按目录缓存合成 features；**tier_catalog 通道**：service.py:462-470 落盘＋:513-526 code-1 清除＋verify_session（:574-589）与 /auth/check-auth（:472-482）响应透出目录
- [x] 3.2 声明点 41 处逐点挂 key（合并 main 后按退役后代码重盘点：续写/扩写/压缩退役出局）：ai-generate×6、prompt-panel×5、ai-plan×8（卷规划×2/拆章/章纲起草/剧情抽卡/建书建议/盘点抽卡/补缺）、chapter-review×1、settings-ai-fields×12（设定域 9＋角色档案 3）、style-suggest×2＋style-quant×1（文风建议/蒸馏拆 key）、ai-plot×8（story 推演七端点＋plot_sim）、ai-polish×1（去AI味 /polish）、卷纲冲突检测挂 ai-generate（ai-check 族）、ai-detect×4（zhuque 执行端点换真门）；**zhuque config 增删/test 3 处为新增门**（现状只挂登录，拦截范围=免费/标准），403 契约按新行为
- [x] 3.3 撤门×3：reconcile/run（:154）、dossier 收尾闸（archive/dossier.py:325，ai_access_granted 删）、quality-check（write/router.py:33，纯本地规则）；**accept/reject 现状无门勿动**
- [x] 3.4 `ai_access_granted(feature=None)` 扩参；ai_state 透传 features；建书满额文案按 tier 双口径（deps.py:168）
- [x] 3.5 pytest：存量语义翻转 8–12 文件（reconcile 免费放行、zhuque PRO→403 feature_required＋config/test 新增门、卷体检/盘点/自检免费→403 等）＋新增矩阵用例；client pytest 全量绿
- [x] 3.6 e2e 现有 spec 零红（等价性门禁：trial/pro 会话经 3.1 重写后的兜底行拿到正确 features；19 个 trial 会话 spec 的锁点按新矩阵走——流程 AI 对 trial 仍全开、推演/朱雀转锁）

## 4. B4 翻转（业务动作，前置：新版 C端 全量发布）

- [ ] 4.1 standard/max tiers 行 status planned→live；SKU on_sale 上架；rehearsal 模式各走一单（下单-激活-退款）＋台账
  - 进度（10-05）：tiers 四档 live＋九 SKU on_sale＋季/年回架（月×3 九折/月×12 八折）已上线；rehearsal 三档各下一单 code:0＋支付码生成。**余**：激活-退款全链（需真实微信支付回调）＋台账归档——待真实支付走单后勾
- [x] 4.2 pay-ops 改价操作手册落档（首发折扣上下线双人复核；无时间窗引擎的补偿流程）
  - 落档：awesome-novel-server docs/ops/pay-ops-runbook.md（PR #5=54b5069）

## 5. B5 前端多态

- [x] 5.1 机制层：LicenseProvider 拆 isStandard/isPro/isMax（isPro≠isMember，功能门控走 useFeature）；**licenseCache 类型扩展（display_name/tier_catalog）＋Provider 接收存储＋resetLicenseCache 清目录**（auth.ts:29/licenseCache.ts:44）；useTier.ts 兜底改 minTierOf＋目录缓存消费；lib/tier.ts 档位文案走 display_name（兜底映射表进 tier.test.ts；standard 现状错标「PRO 会员」随此修复）；api.ts 双 reason 广播（quiet 豁免覆盖新 reason）；MemberBlockPrompt/UpgradeModal 按 tier_required 三版
- [x] 5.2 AiAssistPanel：整卡门禁按页签拆 key；og 行级映射（simulate/conflict→ai-plot、draft/fill/plot-draw/cast-review→ai-plan）；prose→ai-generate（**源头 ChapterWorkspace.tsx:1071 canAiDraft 与 :630 polishHint 同批**）；:900/:1525 手写 member-block 事件随 ai-plan 分档；朱雀行文案维持 PRO 口径（AiAssistPanel :466-476/:501 不变；**ZhuquePanel.tsx:147「PRO 会员权益」保留**——ai-detect 留 PRO 2026-10-05 拍板）；footNote 分档
- [x] 5.3 卷/章规划：VolumeAssistPanel 拆章锁与卷体检（aiState 硬编码修复）→ai-plan；VolumePlanModal 铺空缺→ai-plan；useVolumePlan 参数语义；ChapterPlanModal「AI 看一眼」→chapter-review 新锁
- [x] 5.4 盘点：useCastReview 门→ai-plan；**CastReviewModal 内部 isPro 分支（:772-778 抽卡门/:835-849 锁卡/:120-123 footNote）改 useFeature("ai-plan")**；drawSession.trimCastSessionForTier 参数改 hasAiPlan（修恢复丢卡 bug）
- [x] 5.5 设定域/文风：AiWriterAssistant 锁卡与 toast 分档；5 处表单文案＋StyleSettingForm.tsx:783＋SettingsView.tsx:242 走单源 helper；StyleShadowPane→style-suggest（文风建议归标准；style-quant 仅蒸馏）
- [x] 5.6 归档收尾放开：ReconcilePane 删三处 `!isPro`（:132/:144/:163）；Rail 传参；modals.tsx「归档收尾（PRO）」改全档口径
- [x] 5.7 书架/建书：上限五处硬编码（NovelListPage :243/:542/:707＋CreateProjectModal :93/:135）→limits.max_projects 单源；三条账号横幅＋试用口径（「PRO 同权（不含 MAX 件）」）；AcctMenu/徽章五态
- [x] 5.8 埋点：plan_entry_open/pick_drawn payload 的 tier 标签从二元改真实档位（NovelWorkspace :550-562）；vitest 全量＋组件测试更新（ReconcilePane.test、novelListPage.test trial→isMember 口径翻转等）

## 6. B6 收银台/落地页/法律/e2e 基线

- [x] 6.1 S端 门户：CashierPage/PricingSection 四列断点（repeat(3,1fr)→4＋中断点防挤压）；FALLBACK_FEATS 四档重写（max 旧卖点「更强模型·多章连写」与真实权益不符一并修）；「当前方案」按登录态 license.tier 标注；试用口径五处统一（HeroSection/FaqSection/ActivationGuideSection/RegisterPage/CashierPage）
- [x] 6.2 e2e 基建：按档会话种子 helper（落 e2e/helpers.ts），收敛 **19 个 spec** 各自复制的 writeOAuthSession（config-page 无 tier 参）；统一 atomic 写＋稳定复写、expires_at 按 tier 参数化、返回统一 `{restore}`；注入机制＝浏览器侧桩 `/auth/verify` 返回带 entitlement 的响应（design-parity-book.spec.ts:815 先例）
- [x] 6.3 **e2e 桩承重短语 grep 归位**（先例：c-hooks-plot-exclusion）——已实勘承重桩：plot.spec:239「需 PRO」、statusbar.spec:119「PRO 会员」、modals-pr5.spec:386「升级 PRO · 解锁 AI 能力」、foreshadow-ai.spec:321/genre-ai-settings.spec:239 桩「AI 是会员功能」、free-writing-flow.spec:134「免费版」徽章；逐个改断言或保留短语；再补 reconcile 行为反转、plot-sim/story-arc 换 max 会话（zhuque 种子改 pro——ai-detect 留 PRO）、story-arc 双 reason 断言、style-quant/world-settings/modals 分档断言、standard/max 视角新 spec 2–3 个
- [x] 6.4 design-parity：原型 book.html 免费锁卡**行集＋文案**同步（抽卡/补缺/盘点→需开通·ai-plan；推演→需 MAX；冲突留需 PRO；副行与 footNote 新口径）＋基线重录（baselines 21 张刷新）；design-vocab.mjs 无档位词登记需求（hint 词非 lint 词表域）
  - 登记：book parity 余红 4 例＝存量漂移（modal-delete/prefs/upgrade 三 modal 屏不含 og 右栏与档位文案零交集；free·workbench 11.7% 大头为 #666-672 密度/归档只读/退役链时代原型未同步的树/菜单区），原型全量重同步另立
- [ ] 6.5 法律换版：付费须知/退款政策（agreement_version 升版）；存量文案 grep 清零（「试用可用全部 AI」「PRO 会员权益」含 ZhuquePanel、readiness:136「蒸馏是 PRO 功能」、world-settings:133、character-settings:256、outline-ai-draft「PRO 作者」、frontend-auth-heal:88 等陈旧档位词逐个归位或登记豁免）
- [x] 6.6 全量门禁（10-05 收口）：C端 pytest 1789＋S端 pytest 480＋vitest 1177＋C端 e2e 202/202 全绿；design:lint 绿＋parity 基线重录（余红登记存量）；openspec validate ✓（余 INFO＝拆仓后 S端 五 spec 归属，归档时跨仓同步——server 仓 openspec 同批）

## 归档注记（2026-10-08）

- **C端 半批已 sync**（PR「chore(openspec): tier-plan-four-tiers C端 半批 sync」）：17 个本仓 capability 的 32 处 delta 已进主 spec（含 3 条新增：design-system「档位徽标与档位名词表」／tier-access「按 feature key 的 AI 门禁」／tier-gating「档位显示名单源渲染」），并新建 `tier-catalog`（只收 C端 侧「档位目录缓存兜底」一条）。
- **手改五处**（含 delta 自身两处内部矛盾）：tier-gating 注册表去重 `ai-plot` 重复条＋检测行升级出口由「MAX」改正为「PRO」（与同块「ai-detect 留 PRO」自洽）；workbench 右栏块四处四档口径（体检归 ai-plan×2／整卡锁定按 feature key／剧情推演 MAX／头部副行档位感知，措辞按实现 `AiAssistPanel.tsx` 仲裁）；zhuque-config 试用口径「不含→同权」。
- **按主 spec 更新跳过 1 处**：zhuque-detection「检测门禁与额度口径」——主 spec 现行（键自持门＋精确 503，c-zhuque-config-keyless 2026-10-08 归档）比本 delta 新，SHALL NOT 回灌。
- **余 S端 半批（须在 awesome-novel-server 仓同步）**：`tiers` 表事实源／档位等级序以 DB 为源／s-payments「档位等级序（tier rank）」／check-auth 目录投影下发／account-control-center／entitlement-sync／s-landing-pricing／s-pay-cashier 等 capability 的 delta。**S端 半批落地前本 change 不归档**（移目录留待两边齐后一次做）。
