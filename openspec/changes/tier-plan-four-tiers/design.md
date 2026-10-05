# Design: tier-plan-four-tiers

上游：[产品底稿](../../../docs/prd/pricing-tiers-launch-promo.md) §6、[三视角评审](../../../docs/prd/four-tier-gating-review.md)（含全部 file:line 证据）。本文件只记拍板与取舍，证据以评审报告为准。

## 1. 四档权益矩阵（拍板）

| 档 | features（entitlement） | max_projects | device_limit |
|---|---|---|---|
| free | [] | 1 | 1 |
| standard | ai-plan, chapter-review, settings-ai-fields, style-suggest, outline-advanced-fields, ai-model | 3 | 1 |
| pro | standard 全量 + ai-generate, prompt-panel, ai-detect | null | 3 |
| max | pro 全量 + ai-plot, ai-polish, style-quant | null | 10 |
| trial | = pro 行（trial 同权含朱雀） | null | 1 |

- 分层轴（2026-10-05 终拍）：免费=全流程人工＋归档 AI（收尾提案撤门归免费）；标准=AI 管流程＋设定域 AI＋人物盘点＋文风建议，正文自己写；PRO=正文 AI＋朱雀检测（**留 PRO，trial 同权**——撤销早前「上收 MAX」草案）；MAX=剧情推演＋去AI味（ai-polish）＋文风蒸馏（style-quant——与文风建议**拆 key**：style-suggest 归标准）。月价 29.9/59.9/89.9，季/年未拍首发只插月付行。
- `ai-model`（模型配置）随 standard 行下发仅为快照完整性；免费档该能力不设门（现状口径不变）。
- 设备数按档固定（PRO 月/季 3、年 5 的分时长差异取消，统一 3）。

## 2. 守门改造（后端核心）

- **单符号＋路由装饰器**：`require_ai_access` 保持模块级唯一函数（签名加 `request: Request`，**默认 None＋getattr 防御**——兼容 test_ai_member_gate.py:246 的直调点），feature 从 `request.scope["route"].endpoint.__ai_feature__` 读（FastAPI ≥0.115 起 `APIRoute.matches` 写入 `scope["route"]`，本仓 0.128 实证）。新增 `ai_feature(key)` 装饰器：**setattr 后返回原函数**（不做 functools.wraps 包装，保证 route.endpoint 即标注对象），加在 `@router.post` 之下。**否决工厂函数**：每个调用点生成新 callable 会令 17 个测试文件 21 处 `dependency_overrides[require_ai_access]` 静默失配。
- 44 处 `Depends(require_ai_access)` 声明点逐点标 key（归类表见评审报告 §1；对拍测试兜底防漏挂）；**撤门 3 处**（reconcile/run、dossier 收尾闸、quality-check——accept/reject 现状无门勿动）；**zhuque config 增删/test 3 处为新增门**（现状只挂登录，按 ai-detect 拦截——ai-detect 留 PRO 且 trial 同权，拦截范围=免费/标准，403 契约与 e2e 按新行为写）。
- 403 双 reason：`member_required`（非会员，兼容保留，前端现有升级引导零改动）＋`feature_required`（会员但档位不够，带 `feature`/`tier_required`）。**tier_required 推导**：按 tier_catalog 的 rank 升序找首个含该 key 的档位；目录缺失退 features.ts 词汇表 minTier。
- `ai_access_granted(feature=None)`：传 feature 按 key 判，None 保持二元语义（ai_state 消费点保持 None）。
- `require_novel_model` 不动——归档 AI 全家转免费后它就是免费档的模型就绪门。
- **端点 key ∈ 词汇表对拍测试**（新机械件）：扫描路由表断言每个挂 AI 门的端点 key 已登记——把「端点→key」这处无保护漂移变成 CI 保护。

## 3. 判定链改造（三处枚举雷＋零代码目标）

| # | 位置 | 改法 |
|---|---|---|
| A | client/backend/auth_local/service.py:652 准入闸 | 分支重构为通用规则：none/free → 免费基线；**其余任何档名 → 进快照/目录判定**（FALLBACK_MEMBER_TIERS 补 standard 后退役为目录皆无时的已知档兜底） |
| B | server/app/domain/payments/pricing.py | rank 改读 DB tiers.rank 列：**rank map 走 TierRepo 同款类级 60s TTL 缓存**（payments_repo.py:472 先例），由应用/接口层注入 merge/tier_rank——pricing.py 是领域纯函数模块，SHALL NOT 直连 infrastructure；`resolve_effective_tier:88` 与 `tier_rank()` **两份 rank 逻辑收敛单源**；缺行 `logger.warning(event=...)`＋启动告警通道，不静默清零 |
| C | service.py:687-689 无快照分支 | 按档位目录缓存行合成 features（tier_catalog 由 check-auth/pair 共用装配点 build_license_snapshot 下发，**投影加同类级 TTL 缓存**——现 find_all 无缓存）；**C端 通道**：verify_session 与 /auth/check-auth 响应透出 tier_catalog，licenseCache 类型扩展＋Provider 接收，登出/换号清目录（与快照同链） |
| D | service.py:119-133 STANDARD_FALLBACK | **五行全量重写**对齐 v2 默认表：standard 新增；pro=standard 全量＋ai-generate/prompt-panel/**ai-detect**；max=pro 全量＋ai-plot/ai-polish/style-quant；trial=pro（同权含朱雀）——与 entitlement-defaults.json 对拍锁定 |
| E | server/app/config.py TIER_POLICY | 整体退役：device_limit/duration_days 升 tiers 表列（DDL），代码只留兜底；**消费方全量迁移**（见 tasks 2.1：tier_policy 归一先查、设备限额×3、legacy 码激活、admin 发码、注册试用时长） |

保守方向拍板：快照异常降级一律收紧（按档位标准表/目录缓存行），误伤靠 60s 重同步自愈；漏权是真金白银损失，偏宽不可取。

## 4. 前端多态

- 机制层：features.ts `memberOnly` → `minTier`（兼容派生 `isMemberFeature`，生产零调用点、仅测试）；LicenseProvider 拆 `isStandard/isPro/isMax`（**isPro≠isMember**，功能门控一律走 useFeature）；tierLabel/文案单源 helper（输入 minTier 出「需开通/PRO 专属/MAX 专属」，display_name **兜底映射表**进 tier.test.ts）；api.ts 403 双 reason 兼容（503 isAiPrecondition 白名单无需扩）；MemberBlockPrompt/UpgradeModal 按 tier_required 三版；**display_name/tier_catalog 管道**：licenseCache 类型扩展＋Provider 接收（tasks 5.1）。
- 逐文件点位（AiAssistPanel 行级映射/卷体检新锁点/drawSession 裁剪参数/建书上限 limits 化/ReconcilePane 放开/CastReviewModal 内部 isPro 分支/ChapterWorkspace canAiDraft 源头等）见评审报告 §3，不再复述。
- S端 门户四列数据驱动（仅断点 3→4 与兜底卖点文案）；MAX planned→live 前端零逻辑。**BookPrefsModal 证据勘误**：现状 standard 用户会被错标「PRO 会员」（tier.ts is_member 判定），非「裸显 standard 字面量」——修复方向不变（display_name 单源），验收断言写成「standard 显示 display_name」。
- e2e 基建：新建「按档会话种子」helper（落 e2e/helpers.ts），收敛 **19 个 spec** 各自复制的 writeOAuthSession（config-page 无 tier 参）；统一 atomic 写＋稳定复写、expires_at 按 tier 策略参数化、返回统一 `{restore}`；**注入机制拍板**：helper 在浏览器侧桩 `/auth/verify` 返回带 `entitlement:{v,features,limits}` 的响应（design-parity-book.spec.ts:815 先例）——不依赖 C端兜底常量，档位场景与兜底实现解耦。

## 5. 不做什么（裁剪）

- 不做快照本地验签/Nuitka 加固/提示词分区钥实现（反逆向三任务独立排期，本 change 只留 spec 接口约束：未来 wrapped_key 判定 SHALL 走 features 语义、MUST NOT 写 tier 白名单）。
- 不做用户级灰度（零真实用户；B2「tiers 先 live、SKU 不上架」＋B4 rehearsal 已等效）。
- 不做升级补差价（维持「先退再买」＋收银台换档引导；重启另立 change）。
- 促销体系（券/码/时间窗）不在本 change。

## 6. 发布编排（翻转点 = SKU on_sale）

B1 契约（本 change specs＋entitlement-defaults.json v2＋features.ts＋require_feature 原语＋对拍测试）→ B2 S端 配置（DEFAULTS/rank 读 DB/DDL/tiers 插 standard/max 行——**B2 期间两行保持 status='planned'（预告卡态，规避「live 无在售 SKU」的未定义呈现），SKU 不上架**）→ B3 C端 守门 key 化真拦截（等价性门禁：现有 e2e 零红；trial/pro 兜底行补新 key 后 19 个 trial 会话 spec 的锁点按新矩阵走）→ B4 翻转（standard/max tiers 转 live＋SKU on_sale＋rehearsal 各走一单；**红线：standard 开卖前新版 C端 必须全量发布；B3 不得早于 B2**）→ B5 前端多态＋e2e 补档位视角 → B6 收银台四列/法律换版（agreement_version 升版）/design-parity 基线重录（原型 book.html 行集＋文案同步——盘点行免费变锁、推演/去AI味/蒸馏变 MAX 锁、设定域/文风建议变标准锁、朱雀锁定行「MAX 专属」改「PRO 专属」）。

## 7. 风险与已知接受的偏宽

- ~~旧 PRO 快照含 ai-detect~~（2026-10-05 朱雀留 PRO 后失效——快照本就应含，非风险）。
- 旧版 C端 遇 standard 用户按免费判（B4 编排规避；零用户期无存量暴露）。
- legacy 档名（monthly 等）alias→pro 全量放行窗口维持现状。
- C端 本地判定可篡改面不变（门禁定位 UX 级非 DRM）；key 化把 49 散点收敛为单判定原语，是未来服务端仲裁的结构前提。

## 8. 开发量（评审估计）

后端＋S端 4–6 人日（含零代码目标增量 0.5–1）；前端含 S端 门户与 e2e 6–8 人日；合计 10–14 人日。
