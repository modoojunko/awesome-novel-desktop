# c-rail-tier-badge — 任务清单

## 1. 卡头收口（角标随套餐＋套餐文案退役）

- [x] 1.1 档位角标：`hooks/useTier.usePlanBadge()` 复用 `lib/tier.tierShort`（单源），色调 `accent/muted/warn`；档位未知不标。验证＝`AiWriterAssistant.test.tsx` 角标钉子（pro→「PRO 会员」／free→「免费版」／无快照→不标）
- [x] 1.2 卡头副行只留功能性状态（no_key/missing_model/invalid/prompts_missing）；删「你的 PRO 已包含…」「你的套餐已包含…」「未解锁 · 开通后…」与 `subTitle` 插槽。验证＝NovelWorkspace／AiAssistPanel／AiWriterAssistant 三处负断言
- [x] 1.3 章纲页签说明文案三处删除（副行／页脚／出口块）；行级出口判据改 `!ai-generate` 并把按钮移回能力行下方（不带说明文案）。验证＝`castReviewRail.test.tsx` 免费档出口＋真 PRO 快照（无出口、推演锁「需 MAX」）＋e2e `plot.spec.ts`

## 2. 同族错档文案（文案与门禁 key 同源）

- [x] 2.0 **锁文案单源**：章纲页签四行/卷页签拆章行/抽人锁卡/规划台/文风量化的档位 hint 改走 `upgradeHintOf(featureKey)`（helper 出「需开通（标准档起）／PRO 专属／MAX 专属」），测试与 e2e 钉子同批更新
- [x] 2.1 卷页签：拆章行 hint「需 PRO」→ 单源 helper（「需开通（标准档起）」）、出口按钮「升级套餐」、页脚「生成、改写与归档需开通（标准档起）」（门禁＝`ai-plan`）
- [x] 2.2 抽人：锁卡「AI 抽人需开通（标准档起）」＋标签「标准」＋出口按钮「升级套餐」，toast 同步（门禁＝`ai-plan`）
- [x] 2.3 蒸馏两处标签 `PRO`→`MAX`（`StylePasteModal` 标题旁／`StyleSettingForm` 量化页签；门禁＝`style-quant`）
- [x] 2.4 升级弹窗目标档随档位（已有 `ai-generate`→MAX 三行权益；否则→PRO 原三行）；`MemberBlockPrompt` 标题改与档位无关的「升级套餐解锁」
- [x] 2.5 免费态两处提示去 PRO（`ModelSettingForm`「开通套餐后本书 AI 即可用」／`SettingsView`「开通套餐后解锁」）；`BookPrefsModal` 出口按钮统一「升级套餐」
- [x] 2.6 规划台门禁对齐：`VolumePlanModal.isPro` → `hasAiPlan`（`NovelWorkspace` 传 `useFeature("ai-plan")`），锁文案「需开通（标准档起）」＋徽标「标准」。验证＝`volumePlan.test.tsx` 46 例绿（含锁定态断言改写）
- [x] 2.7 全量验证：`npx vitest run` 110 files 全绿、`npx tsc --noEmit` 0 error、`vitest --coverage`（契约文件 100%）、`design:lint` 净

## 3. 设计资产同步（原型）

- [x] 3.1 `book.html` 章纲/正文两卡头改「角标随档位（free-mode→免费版）＋只留标题」；页脚两态同文收成一句；补免费态「升级套餐」出口（`#btnUpgrade3`，被 `design-parity-book` 的 `modal-upgrade` 例引用）；rh-t 两态 CSS 退役。验证＝Playwright 打开零 console 错误（本地目检）
- [ ] 3.2 `DESIGN_PARITY=1` 重跑 `design-parity-book.spec.ts` 四例并重录 `docs/design-c/baselines/book.*`（parity 为本地工具、不进 CI；未随本 change 执行）

## 4. 规格与应用侧回归

- [x] 4.1 specs delta：`workbench`／`storyline-settings`／`intro-genre-settings` 三处（`chapter-plan-ai`／`chapter-cast-review` 已由 #769 sync 写入口径，不再出 delta；rebase 到 #769 后按新主 spec 文本重导）（要点：角标随套餐、副行只留功能状态、行级出口只给未到 `ai-generate`、行级 hint 与 key 同源、弹窗目标档随档位）。验证＝`openspec validate c-rail-tier-badge --strict` 通过
- [x] 4.2 e2e 断言同步：`plot`（免费档出口）／`style-quant`（免费态卡头角标）／`story-arc`（拦截弹窗标题）／`prompt-pack`（同上）／`world-settings`（stub 文案）／`modals-pr5`（出口按钮与弹窗标题注记）
- [ ] 4.3 真机验收：PRO 账号看章纲页签＝角标「PRO 会员」＋无升级出口＋推演锁定标「需 MAX」；标准账号＝出口「升级套餐」可见、弹窗目标 PRO；免费账号＝整卡锁定＋点击出「升级套餐解锁」弹窗
- [x] 4.4 弹窗目标档按 `tier_required`：出口透传 feature key（`onUpgrade(required?)`）＋弹窗出标准/PRO/MAX 三套口径，全局入口回退「下一档」。验证＝`UpgradeModal.test.tsx` 四例（ai-plan→标准／ai-detect→PRO／无 key→PRO 与 PRO→MAX／非登记 key 防御）＋e2e `plot.spec.ts` 免费档点出口出「升级标准」
- [x] 4.5 评审整改（自查 findings 闭环）：档位短名单源 `tierLabel`＋四处徽标取值；弹窗 ownRank 认试用档（不重复喊已含的档，`UpgradeModal.test.tsx` 补例）；`statusNote` 功能性副行（朱雀开关关注记，`AiWriterAssistant.test.tsx` 补例）；注释/死字段回正；原型 ra-hint 五处同步；`ADJUSTMENTS.md` 登记卡头/出口/弹窗偏差；补 `design-system`／`zhuque-workbench`／简介右栏三条 delta
- [ ] 4.6 归档：`openspec archive c-rail-tier-badge` 并 sync 主 spec（归档前复核 3.2 基线重录是否随批）
