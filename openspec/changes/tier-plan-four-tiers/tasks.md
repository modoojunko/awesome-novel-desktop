# Tasks: tier-plan-four-tiers

编排约束（design §6）：B1→B2→B3→B4→B5→B6；**B3 不得早于 B2**；standard SKU 上架（4.x）前新版 C端 必须全量发布；B2 期间 standard/max tiers 保持 planned。每节内自上而下。

## 1. B1 契约先行（词汇表＋原语＋对拍）

- [ ] 1.1 `client/frontend/src/lib/features.ts`：注册表 `memberOnly` → `minTier`（free/standard/pro/max），保留 `isMemberFeature` 兼容派生（生产零调用点、仅测试）；新增 key：ai-plan/chapter-review/style-suggest/style-quant/ai-plot/ai-polish；ai-detect 留 pro（trial 同权——删「下放 PRO」过渡注释改「PRO 起」）；style-suggest（文风建议，标准）/style-quant（文风蒸馏，MAX）拆 key；同步 features.test.ts
- [ ] 1.2 `docs/contracts/entitlement-defaults.json` 升 v2：五档行（free/standard/pro/max/trial=pro 同权含 ai-detect），四端 key 全量（新增 ai-plan/chapter-review/style-suggest/style-quant/ai-plot/ai-polish）；契约文件头注释替换为「加新 key 六步 SOP」
- [ ] 1.3 `server/app/config.py` ENTITLEMENT_DEFAULTS 同批对齐五档（**补 standard 行**；trial=pro 同权含 ai-detect——架构评估：缺 standard 键时快照兜底落到 none 全空，标准用户权益清零）；两端对拍测试（client test_entitlement_sync.py / server test_check_auth_extension.py、contract 对拍）随 v2 重写先红后绿
- [ ] 1.4 C端 `ai_feature(key)` 路由装饰器（**setattr 后返回原函数，不做 wraps**）＋`require_ai_access` 读 `request.scope["route"].endpoint.__ai_feature__`（签名 `request: Request = None`＋getattr 防御，兼容 test_ai_member_gate.py:246 直调；依据 fastapi≥0.115 的 scope["route"]，本仓 0.128）；403 双 reason（member_required 保留＋feature_required 带 feature/tier_required；tier_required 按 tier_catalog rank 升序首个含 key 的档推导，目录缺失退 minTierOf）
- [ ] 1.5 端点 key ∈ 词汇表对拍测试（扫描路由表 44 处挂点断言；新机械件）
- [ ] 1.6 门禁单测：五档 × 各新 key 放行/拒绝矩阵（**必须走真实依赖＋config/快照种子，禁用 dependency_overrides**——override 会整段绕过 key 判定测不到 feature_required）

## 2. B2 S端 配置与数据（standard/max 保持 planned；SKU 不上架）

- [ ] 2.1 DDL 四步：① TierORM 加 device_limit/duration_days 列（server_default 回填）② alembic 新 revision 线性挂尾 ③ **`pg_schema.REQUIRED["tiers"]`/COLUMN_DEFAULTS 同批**（漏列即红对拍）④ gen_missing_ddl.py 产出→MCP 带外应用→启动探针 run_schema_check 目检
- [ ] 2.2 **TIER_POLICY 退役的消费方全量迁移**（改读 tiers 行，先 `_TIER_ALIASES` 归一再查）：`domain/licensing/tier_policy.py`、设备限额三处（application/devices/verify_license.py:75、list_devices.py:14、get_device_status.py:24）、legacy 码激活 `application/licensing/activate_code.py:25`（改 codes.duration_days，防 monthly 码激活即过期）、admin 发码校验 `admin_api/codes.py`、注册试用时长 `identity/register_user.py:60`（改读 trial 行 duration_days）；TIER_POLICY 降为 DB 不可用兜底（注意 lifetime 在 config.py:230 被加载期改写为 99，勿照抄注释值）
- [ ] 2.3 **rank 读 DB**：rank map 走 TierRepo 类级 60s TTL 缓存（payments_repo.py:472 先例）、由调用方注入 merge/tier_rank（pricing.py 保持领域纯函数不直连 infrastructure）；`resolve_effective_tier` 与 `tier_rank()` 两份逻辑收敛单源；缺行 `logger.warning(event=tier_rank_missing)`＋启动告警
- [ ] 2.4 tiers 数据：插 standard 行（rank=15、**status=planned**、entitlement JSON=ai-plan/chapter-review/settings-ai-fields/style-suggest/outline-advanced-fields/ai-model＋max_projects=3）；max 行 entitlement=pro+ai-plot+ai-polish+style-quant（仍 planned）；**pro 行不动**（ai-detect 留 PRO，2026-10-05 拍板）；display_name 全行核对；**插行前 SELECT 生产 tiers 核对 rank/sort 现值**（架构评估未核实项）
- [ ] 2.5 skus 数据：首发只插月付 3 行（standard_monthly=2990 分/pro_monthly 维持 5990/max_monthly=8990，on_sale=false）；**sort 排 pro 现有行之后（建议 4-6，禁用默认 0）**——popular_sku 机制取第一个年付 SKU，sort 撞序会静默换档（架构评估 §四-3）；季/年卡未拍不插；PRO 年卡 device_limit 5→3（按档固定，仅展示列——实际限额走 TIER_POLICY 迁移 2.2）
- [ ] 2.6 tier_catalog 下发：build_license_snapshot 共用装配点加投影（活跃档 key/rank/display_name/features）；**投影加类级 TTL 缓存**（现 find_all 无缓存）；`GET /api/pay/skus` 目检四档出列（standard/max呈预告卡态）；server pytest 全量＋对拍绿

## 3. B3 C端 守门 key 化（真拦截）

- [ ] 3.1 判定链：service.py 准入闸分支重构（none/free→免费基线，其余任何档名进快照/目录判定）；**STANDARD_FALLBACK 五行全量重写**对齐 v2 默认表（standard 新增；pro=standard＋ai-generate/prompt-panel/ai-detect；max=pro＋ai-plot/ai-polish/style-quant；trial=pro 同权；与 entitlement-defaults.json 对拍）；**FALLBACK_MEMBER_TIERS 补 standard**（退役为目录皆无时的兜底）；无快照分支按目录缓存合成 features；**tier_catalog 通道**：service.py:462-470 落盘＋:513-526 code-1 清除＋verify_session（:574-589）与 /auth/check-auth（:472-482）响应透出目录
- [ ] 3.2 44 声明点逐点挂 key（归类表见评审报告 §1）：ai-generate×6、prompt-panel×5、ai-plan×10、chapter-review×1、settings-ai-fields×10、style-suggest×2＋style-quant×1（文风建议/蒸馏拆 key）、ai-plot×4（剧情推演——卷纲冲突检测留 ai-check 族挂 ai-generate 门）、ai-polish×1（去AI味）、ai-detect×4（zhuque 执行端点换真门）；**zhuque config 增删/test 3 处为新增门**（现状只挂登录，拦截范围=免费/标准），403 契约按新行为
- [ ] 3.3 撤门×3：reconcile/run（:154）、dossier 收尾闸（archive/dossier.py:325，ai_access_granted 删）、quality-check（write/router.py:33，纯本地规则）；**accept/reject 现状无门勿动**
- [ ] 3.4 `ai_access_granted(feature=None)` 扩参；ai_state 透传 features；建书满额文案按 tier 双口径（deps.py:168）
- [ ] 3.5 pytest：存量语义翻转 8–12 文件（reconcile 免费放行、zhuque PRO→403 feature_required＋config/test 新增门、卷体检/盘点/自检免费→403 等）＋新增矩阵用例；client pytest 全量绿
- [ ] 3.6 e2e 现有 spec 零红（等价性门禁：trial/pro 会话经 3.1 重写后的兜底行拿到正确 features；19 个 trial 会话 spec 的锁点按新矩阵走——流程 AI 对 trial 仍全开、推演/朱雀转锁）

## 4. B4 翻转（业务动作，前置：新版 C端 全量发布）

- [ ] 4.1 standard/max tiers 行 status planned→live；SKU on_sale 上架；rehearsal 模式各走一单（下单-激活-退款）＋台账
- [ ] 4.2 pay-ops 改价操作手册落档（首发折扣上下线双人复核；无时间窗引擎的补偿流程）

## 5. B5 前端多态

- [ ] 5.1 机制层：LicenseProvider 拆 isStandard/isPro/isMax（isPro≠isMember，功能门控走 useFeature）；**licenseCache 类型扩展（display_name/tier_catalog）＋Provider 接收存储＋resetLicenseCache 清目录**（auth.ts:29/licenseCache.ts:44）；useTier.ts 兜底改 minTierOf＋目录缓存消费；lib/tier.ts 档位文案走 display_name（兜底映射表进 tier.test.ts；standard 现状错标「PRO 会员」随此修复）；api.ts 双 reason 广播（quiet 豁免覆盖新 reason）；MemberBlockPrompt/UpgradeModal 按 tier_required 三版
- [ ] 5.2 AiAssistPanel：整卡门禁按页签拆 key；og 行级映射（simulate/conflict→ai-plot、draft/fill/plot-draw/cast-review→ai-plan）；prose→ai-generate（**源头 ChapterWorkspace.tsx:1071 canAiDraft 与 :630 polishHint 同批**）；:900/:1525 手写 member-block 事件随 ai-plan 分档；朱雀行文案维持 PRO 口径（AiAssistPanel :466-476/:501 不变；**ZhuquePanel.tsx:147「PRO 会员权益」保留**——ai-detect 留 PRO 2026-10-05 拍板）；footNote 分档
- [ ] 5.3 卷/章规划：VolumeAssistPanel 拆章锁与卷体检（aiState 硬编码修复）→ai-plan；VolumePlanModal 铺空缺→ai-plan；useVolumePlan 参数语义；ChapterPlanModal「AI 看一眼」→chapter-review 新锁
- [ ] 5.4 盘点：useCastReview 门→ai-plan；**CastReviewModal 内部 isPro 分支（:772-778 抽卡门/:835-849 锁卡/:120-123 footNote）改 useFeature("ai-plan")**；drawSession.trimCastSessionForTier 参数改 hasAiPlan（修恢复丢卡 bug）
- [ ] 5.5 设定域/文风：AiWriterAssistant 锁卡与 toast 分档；5 处表单文案＋StyleSettingForm.tsx:783＋SettingsView.tsx:242 走单源 helper；StyleShadowPane→style-suggest（文风建议归标准；style-quant 仅蒸馏）
- [ ] 5.6 归档收尾放开：ReconcilePane 删三处 `!isPro`（:132/:144/:163）；Rail 传参；modals.tsx「归档收尾（PRO）」改全档口径
- [ ] 5.7 书架/建书：上限五处硬编码（NovelListPage :243/:542/:707＋CreateProjectModal :93/:135）→limits.max_projects 单源；三条账号横幅＋试用口径（「PRO 同权（不含 MAX 件）」）；AcctMenu/徽章五态
- [ ] 5.8 埋点：plan_entry_open/pick_drawn payload 的 tier 标签从二元改真实档位（NovelWorkspace :550-562）；vitest 全量＋组件测试更新（ReconcilePane.test、novelListPage.test trial→isMember 口径翻转等）

## 6. B6 收银台/落地页/法律/e2e 基线

- [ ] 6.1 S端 门户：CashierPage/PricingSection 四列断点（repeat(3,1fr)→4＋中断点防挤压）；FALLBACK_FEATS 四档重写（max 旧卖点「更强模型·多章连写」与真实权益不符一并修）；「当前方案」按登录态 license.tier 标注；试用口径五处统一（HeroSection/FaqSection/ActivationGuideSection/RegisterPage/CashierPage）
- [ ] 6.2 e2e 基建：按档会话种子 helper（落 e2e/helpers.ts），收敛 **19 个 spec** 各自复制的 writeOAuthSession（config-page 无 tier 参）；统一 atomic 写＋稳定复写、expires_at 按 tier 参数化、返回统一 `{restore}`；注入机制＝浏览器侧桩 `/auth/verify` 返回带 entitlement 的响应（design-parity-book.spec.ts:815 先例）
- [ ] 6.3 **e2e 桩承重短语 grep 归位**（先例：c-hooks-plot-exclusion）——已实勘承重桩：plot.spec:239「需 PRO」、statusbar.spec:119「PRO 会员」、modals-pr5.spec:386「升级 PRO · 解锁 AI 能力」、foreshadow-ai.spec:321/genre-ai-settings.spec:239 桩「AI 是会员功能」、free-writing-flow.spec:134「免费版」徽章；逐个改断言或保留短语；再补 reconcile 行为反转、plot-sim/story-arc 换 max 会话（zhuque 种子改 pro——ai-detect 留 PRO）、story-arc 双 reason 断言、style-quant/world-settings/modals 分档断言、standard/max 视角新 spec 2–3 个
- [ ] 6.4 design-parity：原型 book.html 免费锁卡**行集＋文案**同步（book.html:1043-1079 五行「需 PRO」＋盘点行免费变 ai-plan 锁＋footNote）＋基线重录；design-vocab.mjs 若涉档位词两端同批
- [ ] 6.5 法律换版：付费须知/退款政策（agreement_version 升版）；存量文案 grep 清零（「试用可用全部 AI」「PRO 会员权益」含 ZhuquePanel、readiness:136「蒸馏是 PRO 功能」、world-settings:133、character-settings:256、outline-ai-draft「PRO 作者」、frontend-auth-heal:88 等陈旧档位词逐个归位或登记豁免）
- [ ] 6.6 全量门禁：pytest（两端）＋vitest＋e2e 全绿；openspec validate
