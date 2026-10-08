## Context

- 门控现状（`client/backend/auth_local/deps.py`）：`require_ai_access` 单函数承担三段——会员（403 `member_required`）→ 档位（403 `feature_required`，按 `ai_feature` 标注的 key 判）→ **写作大模型 Key 已配**（503「AI 服务未配置 — 请先在设置中填写 API Key」，判据链 ApiConfig active 行 → 旧 `User.api_key` → config.json 兜底）。第三段对「用作者自持 Key 的端点」是错判据。
- 触发源：`tier-plan-four-tiers`（#679）B3.2「41 声明点挂门」把朱雀配置域三端点（PUT/DELETE config、POST test）一并挂上 `require_ai_access`；同 PR 的 e2e 侧以「先种一条模型配置」绕行（`zhuque.spec.ts` 注释原文即「无写作 Key 时 503，须先有一条模型配置」），产品侧没有绕行路径——首配作者点「保存并测试」必吃 503。
- 该 change 自述拦截范围（tasks 3.2「=免费/标准」）只有档位门，判据复用越界；其未归档 spec delta 却把「配置端点挂 `ai-detect` 门＋非会员保存 403」写成了目标契约——与主 spec 现行文本（配置页 SHALL NOT 阻挡配置动作）及其前端实现（页签无锁定态）都不一致。
- 2026-10-08 用户拍板三条：①**配置不区分套餐权益，操作入口区分**（配置全档可配，权益门禁落使用口）②使用口（检测）同换键自持门——「任何 Key 都没有」不再被通用 503 盖过 ③**两个 Key 世界互不顶替**——没配大模型时，用到大模型的功能就要提示去配大模型；朱雀配不配不影响大模型功能（反向同理，使用朱雀功能没配朱雀就提示配朱雀）。
- 口径③暴露的第二处缺陷：门控的「已配写作大模型 Key」判据是**自建查询**（`ApiConfig.api_key != ""`，不看 vendor、不解密），而判定层 `user_has_ai_key` 早已按「可解密＋排除 `vendor="zhuque"`」判——两处不同源：只配朱雀的用户会被当成「已配大模型 Key」放过门，随后在更深处吃不明错误（既有其余判据如 `compute_ai_state`/novel 绑定早已排除朱雀行）。
- 口径④（同日追加拍板）：**提示词面板看/改不依赖写作大模型**——买了 PRO、还没配模型 Key 的作者，打开面板/生成弹窗看与编辑已存提示词 SHALL NOT 被拦，「去配大模型」的引导落在**点生成**时；面板仍是 PRO 专属（档位门不动）。
- 口径④把 `prompt-panel` 五端点纳入后，「键自持门」消费者变成两组（`ai-detect`／`prompt-panel`）——守卫需要白名单，否则「任何 key 都能挂键自持门」会让「生成类端点错挂门」这类误配静默通过。
- e2e 善后（带栈复跑时完成）：`zhuque.spec.ts` 的历史绕行种子（先种一条写作模型配置）已删，该 spec 现即「零大模型配置＋朱雀 Key」的回归网；`workbench-features.spec.ts` ④b 按口径④重写。
- 测试基建：既有 `test_zhuque.py` 的 `_client()` 以 `dependency_overrides[require_ai_access] = lambda: True` 整段绕门，**配置域的门从未被真实执行**（本缺陷漏网直接原因）；`test_ai_feature_matrix.py` 直调真门、`test_ai_feature_registry.py` 扫路由断言「挂 key 必有门」。

## Goals / Non-Goals

**Goals:**

- 朱雀 Key 的保存/更换/删除/连接测试**不分套餐档位、不依赖写作大模型配置**：免费到 MAX 全档可完成；PRO/试用且零写作模型配置亦然。
- `ai-detect` 权益门禁落在使用口：检测端点＝会员＋档位真门（`require_tier_access`），前端 `useFeature` 锁定为第二层；未配朱雀 Key 时返回精确的 503 `zhuque_not_configured`。
- 写作链路端点门与文案零变化（`require_ai_access` 对外行为逐字不变）。
- 提示词面板（`prompt-panel`）取数与编辑不依赖写作大模型 Key：PRO/试用可看/可改/可存，未配 Key 的引导落在生成动作上（口径④）。
- 用走真实门依赖的回归用例＋三向变异检查钉死「配置域无门、使用口键自持门、Key 判据单源」；守卫按 key 分型校验（键自持门白名单），白名单外错挂门型即红。

**Non-Goals:**

- 不改写作链路任何端点的**门**（档位/会员判据不动）；但按拍板③精修其第三段判据的**实现与引导文案**（收归判定层＋指名配置口）。
- 不动前端：朱雀页签本就无门禁代码，工作台检测行的档位锁定（「PRO 专属」＋升级出口）已在，与拍板①同口径。
- 不给免费/标准档做「检测可用」的任何放行（使用口档位门照拦）。
- 不给 `prompt-panel`／`ai-detect` 之外的 key 开键自持门（守卫白名单固化；新增键自持端点须同步白名单与本 change 的 `tier-access` delta）。
- 无 UI 改动、无 schema/依赖变更。

## Decisions

1. **配置域撤门到「只挂登录」，而非保留档位门。**
   - 依据拍板①（配置不分套餐权益）与 BYOK 语义：朱雀 Key 是作者自备的腾讯资产，配置动作本身不消耗任何平台能力；档位门在该处无收益，只制造「配了也不能用」与「首配被拦」两类摩擦。
   - 该拍板同时修正 `tier-plan-four-tiers` 未归档 delta 中的相反契约（见第 4 条）。
2. **使用口用新门 `require_tier_access`（会员＋档位，不查写作模型 Key）。**
   - 抽 `_require_member_and_tier(user, request)`，`require_ai_access` 与 `require_tier_access` 共用；Key 判据抽成 `_check_writing_model_configured(user, db)` 只由前者调用 → `require_ai_access` 签名/行为/文案逐字不变（写作链路 40+ 端点零影响）。
   - 不参数化（如 `ai_feature(key, own_key=True)`）：两种门是两种语义，独立依赖自查即明；守卫只需认两个 `__name__`。
3. **回归钉必须走真实依赖**：新用例只 override `get_current_user`，档位用隔离 config.json 设定（`local_tier` fixture，用完还原路径＋清缓存）；不动 `_client()` 既有语义（那批用例测端点自身行为），只给它补 `require_tier_access` 覆盖位——否则新门在旧用例里被真跑，且因测试库 config.json 为空而 403（实现期实测：漏补即 2 用例红）。
4. **在途 spec 就地修正**：`tier-plan-four-tiers` 未归档（自 #707 起未再改动、无在途归档 PR），其 zhuque-config delta 的「配置端点挂门／非会员 403」段与 zhuque-detection delta 的「通用 503 先行」注若原样归档，会把刚拍板否掉的契约写回主 spec——故两处就地改正为本次口径（改动限于这两段／一注，其余文本不动）。
5. **Key 判据收归判定层 `user_has_ai_key`（口径③）**：删除门控内联查询，改为延迟导入 `ai_state.user_has_ai_key`（deps 内已有同款延迟导入先例 `ensure_novel_model_ready`，防循环依赖）。收益＝单源（可解密口径＋排除朱雀行）＋修掉「朱雀顶大模型」漏判；成本＝未配时文案统一为门控引导语（死文态细分文案仍由 `ai_state.no_key_message` 在 `/ai-model` 路径给）。503 文案同时改为指名配置口：`尚未配置写作大模型 API Key — 去「模型配置 → 写作大模型」添加`（保留「API Key」「未配置」子串，前端既有 `useChapterPlan` 兜底匹配与 e2e `/API Key/` 断言不受影响）。
6. **提示词面板＝看/改不判 Key、生成才提示（口径④）**：`prompt-panel` 五端点（书目总览／章级列表／内容读取／内容保存／生成弹窗预览 `GET .../write/prompt`）换 `require_tier_access`，`ai_feature("prompt-panel")` 保留（PRO 专属不放松）。判据：面板取数与编辑不调大模型（纯存储读写＋本地组装），「未配模型」的引导落在生成动作（正文生成端点按 Key 判据 503）——与拍板③「用到大模型的功能才提示」一致；e2e `workbench-features` ④b 由「弹窗即报错＋生成键置灰」改为「弹窗照常展示提示词 → 点生成就地提示」。
7. **守卫按 key 分型（白名单）而非「任一 AI 门」**：`KEYLESS_GATE_KEYS = {ai-detect, prompt-panel}`；LLM 类 key 仍只认 `require_ai_access`，错挂键自持门即判失败（否则「未配模型的作者被放行到业务深处」这类误配会静默通过——正是本次修的 bug 类），并补「白名单自身为空／含词汇表外 key」的自检场景。
8. **变异检查作为钉子验收**（都实测）：配置端点加回 `require_ai_access` → `test_config_domain_open_for_all_tiers` 红；检测端点门回 `require_ai_access` → `test_detect_endpoint_missing_zhuque_key_is_not_generic_503` 红（通用 503 复现）；Key 判据换回旧宽松查询 → `test_zhuque_key_is_not_a_writing_model_key` 红。

## Risks / Trade-offs

- [配置域无门后，免费/标准用户能存朱雀 Key 却用不了检测] → 正是拍板①的取舍（配置不分套餐、入口区分）：Key 是自备资产，配好等升级即可用；使用口由档位门＋前端锁定双重拦，不会白烧额度。
- [检测端点换门后，「任何 Key 都没有」的 503 文案从通用「AI 服务未配置」变为 `zhuque_not_configured`] → 更精确（指向朱雀页签），且前端在该情形走引导态、不依赖该响应区分；旧顺序的 spec 文本（zhuque-detection 注）同步退役。
- [抽函数改动门控核心文件，波及所有 AI 端点] → `require_ai_access` 逐字保留原逻辑（只改位置），全量套件对拍基线零新增红；matrix 门禁矩阵继续对真门直调。
- [修改在途 change 的 spec 文本可能与那份 change 的归档动作抢行] → 改动仅两段／一注且方向与主 spec 一致；若对方归档时从旧文本同步，收敛结果仍是本次口径（本次 delta 亦为同向修正）。
- [守卫白名单是手工名单] → 新增键自持端点时须同步白名单＋`tier-access` delta，否则守卫会红（宁可红不可静默放水）；自检场景已覆盖「白名单为空／含未知 key」。
- [e2e 种子删除是否安全] → 已在本会话自建隔离栈（`zqgate-e2e`，跑本分支构建）复跑验证：`zhuque.spec.ts` 2 passed（零大模型配置）、`workbench-features` ④b 1 passed（tasks 4.12）。

## Migration Plan

纯后端行为修复，无 schema/依赖/数据迁移，随下个 C端 发版带走。回滚即还原 `deps.py`／`zhuque/router.py` 两处（测试、文档与在途 spec 修正同批回滚），无用户数据影响。

## Open Questions

（无）

- `prompt-panel` 的档位口径维持 PRO（`features.ts` `minTier: "pro"`，不是 PRO 就不能用）；本 change 只撤其中「已配写作大模型 Key」的判据（口径④），档位门未动，端点级钉子见 `test_ai_feature_http`／`test_ai_feature_matrix`。
