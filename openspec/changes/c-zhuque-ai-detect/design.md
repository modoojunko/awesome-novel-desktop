## Context

设计事实源：[drafts/ai-novel-c端-朱雀检测.html v12](/Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/ai-novel-c端-朱雀检测.html)（10 态，含 v1→v12 决策日志与四路评审结论）。约束：

- C端是 BYOK 双层架构：`client/frontend`（React 19 + TipTap）→ `client/backend`（本地 FastAPI + SQLite）→ 上游。写作大模型 Key 已有 `api_configs` 表（加密 `api_configs/crypto.py`、软删恢复 `service.py`、连接测试 `connection.py`）。
- 朱雀上游：`POST https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify`（Bearer Key，`{"text", "is_merge": true}`），返回 `softmax_confidence / labels_ratio{0人工,1AI,2疑似} / segment_labels[{text,label,conf,order,position}] / makers_models_usage.total_tokens`；错误 401/403/429/5xx；已实测可达，网关响应头无 CORS 限制问题（前端也不直连）。
- 定价终拍：朱雀检测＝MAX 权益、试用不含（pricing-tiers-launch-promo.md §6.2/§6.4，feature key `ai-detect`）。当前代码只有 member 二元（`features.ts` memberOnly），MAX 精确发放靠 S端 entitlement 快照。
- 既有门控机制：`auth_local/deps.py` 的 `require_ai_access()`（会员校验，ai-check 同款）；前端 `useFeature(key)` 读快照。

## Goals / Non-Goals

**Goals:**

- 整条链可用：配置（双页签单 Key 槽）→ 送检（本地后端代理）→ 展示（标题区结果条＋正文 Decorations 标注）。
- 四处消费点（配置开关、右栏行、标题区、正文标注）读同一状态单源，行为与设计稿 10 态一一对应。
- 防御三件套落地：写作模型选取路径 vendor 过滤（P0）、Key 加密复用、检测结果零落库。

**Non-Goals:**

- 不做 S端 代理/计费/配额体系（pricing §6.5 四档改造的范围；本 change 的端点收拢即为其预留）。
- 不做异步检测模式（同步 read=90s 足够，上游异步 Work-Mode 仅在同步 p95 超 30s 时再引入）。
- 不做检测结果持久化、不做「检测历史」列表、不做月度额度统计面板。
- 不改既有「AI 出卡确认弹窗」对写回类产物的约束（design-system 只加边界条款）。

## Decisions

### D1. Key 存储：复用 api_configs 表 + vendor="zhuque"（用户拍板）

- 复用表白得：加密存储（`crypto.py` fernet）、掩码、软删/恢复、last_test_status 持久化。专用端点 `GET/PUT/DELETE /api/v1/zhuque/config` 内部固定 `name="朱雀 AI 检测"`、`vendor="zhuque"`（同时写 `vendor_display_name="朱雀 AI 检测"`，避开 resolve 落 "zhuque" 裸名）、`base_url=网关地址`（不接用户输入）。
- **upsert 语义**：查重键为 `(user_id, name)`（与表唯一约束 `uq_api_configs_user_name` 一致，**不含 vendor**）；active→更新密钥；deleted→复活该行（恢复 active＋新密钥，保 id 稳定）。绕开 `service.py:38-42` 名称唯一检查不含 status 过滤的软删 409。作者的大模型配置撞固定名→409 明确提示。并发双保存：捕获 IntegrityError 回滚后重查转 update（幂等兜底）。
- **空串守卫**：PUT 的 api_key 空串＝未提供（保留已存密文），复用 `api_configs/router.py:206-209` 既有守卫口径与回归用例模板（`test_update_with_blank_api_key_preserves_stored_key`）。
- **P0 隔离（判据方向逐一钉死）**：
  - `ai_client.py` 的 `get_ai_client_for_user / get_ai_client`（401-446，按 created_at 倒序取任意 active 有 Key 配置）加 `ApiConfig.vendor != "zhuque"` 过滤；
  - `ai_state.py` 的 `user_has_ai_key` 同加过滤（只配朱雀时应呈「未配置 Key」引导语义，而非「先选模型」）；
  - `auth_local/deps.py` 的 `require_ai_access` Key 存在性前置检查 **SHALL NOT 过滤**——朱雀-only 的 MAX 作者须靠朱雀行通过它到达检测端点自身门禁。
- **数据面隔离**：`get_user_api_configs` / `get_batch_status` 加 `vendor != "zhuque"`——朱雀卡 SHALL NOT 出现在大模型页签列表，且不可经通用编辑/测试路径破坏固定 name/vendor/base_url（update 路径同样无 vendor 防护，靠列表不可达兜住）。
- **绑定侧防注入**（生成选取第三条路 `get_ai_client_for_novel` 按本书绑定直取、无过滤，防护靠「绑不进去」）：备份导入的唯一 active 自动挂接跳过 zhuque 行；「应用到全部书」类批量绑定校验目标配置 vendor；`get_ai_client_for_novel` 对 vendor==zhuque 直接拒绝（一条 if 兜住直调面）。
- `vendor.py` 不为 EdgeOne 域名新增 pattern（创建走显式固定 vendor，不落 resolve 推断）。
- 否案：独立新表（架构评审曾提）——用户拍板复用表；语义差异（单槽 vs 多配置）由专用端点吸收，不暴露通用 CRUD。

### D2. 检测端点与契约

```
POST /api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check
  auth: get_current_user + require_ai_access（会员级防御；MAX 精确判定在前端快照）
  前置（前端保证）：前端调用方 POST 前 await 本章 store.flush()（chapter-rewrite 同款先例）；后端读落盘正文原样送检
  200 {ok, prose_hash,
       summary: {human_ratio, suspect_ratio, ai_ratio, softmax_confidence},
       segments: [{paragraph_index, label(0|1|2), confidence}],
       usage_tokens}
  400 空正文/全空白 | 401 Key 无效(上游401/403) | 404 章/项目不存在
  422 超上限(30000字) | 429 限流或额度耗尽(透传上游 code/message)
  502 上游5xx/分段数不符 | 503 zhuque_not_configured（会员但 Key 缺失/刚删）
  504 网络/超时
GET/PUT/DELETE /api/v1/zhuque/config；POST /api/v1/zhuque/test
  test 响应沿用 connection.py 全部状态枚举（ok/auth_error/rate_limited/timeout/network_error/unknown）
  （持久化 last_test_status/last_tested_at，供配置卡「上次测试时间」显示）
```

- httpx.AsyncClient 直连（同 `connection.py` 惯例，不进 AIClient/SDK——httpx2 拒收 httpx.Timeout 的坑只在 SDK 路径）；`httpx.Timeout(connect=10, read=90, write=30)`。超时/5xx 的失败文案与 429 区分为「上游响应慢/异常」。
- **上游对齐规则**：请求 `is_merge: true` 一次送全文；响应 `segment_labels` 按其 `order` 序与本地非空段一一对应；上游分段数 ≠ 本地非空段数时返回 502「检测结果与段落不一致，请重试」，不做静默 best-effort。
- **403 文案错位**（`require_ai_access` 现文案承诺「开通 PRO 或 7 天试用」，对本权益是错误承诺）不在本 change 修——归 pricing §6.5 四档改造重写 feature-key 门禁时统一收口，本 change 在 Risks 登记。
- 前端零直连 ⇒ 无 CORS 议题；`ZHUQUE_API_BASE` 环境变量供测试/e2e 桩替换。
- 检测连通性测试（test）＝一次最小 classify（几个 token），UI 披露消耗。
- **作话/作者注剔除**：经核不适用——C端章正文数据结构为纯 `\n` 分段文本（`chapters/store.py` store.prose），无作话/作者注块可剔；送检范围＝全部非空段。设计稿 v12 的该拍板以此口径落地并记录于此。

### D3. 段落切分后端收口与指纹管道

- 切分规则（前后端唯一口径）：换行归一 `\r\n|\r` → `\n`；「段落」谓词＝**trim 后非空**的行；`paragraph_index` 按非空段 0 起编号。前端映射＝`doc.content.forEach` 遍历 paragraph 节点取「第 k 个非空节点」（`textContent.trim() !== ""`）——与 `ProsePane.textOffsetToPmPos` 的全节点遍历口径**刻意不同**（编辑器空段保留为节点：`proseDoc.ts` 空行保留为空段落，且用户手敲双 Enter 的空段会真实入库；`normalizeStreamedProse` 的折叠只作用于 AI 流式落库），实现者 MUST NOT 复用 textOffsetToPmPos 计索引。编辑器 hardBreak 已禁用（ProsePane.tsx:194），段内硬换行不构成漂移源；真正的漂移源是**全空白行**（后端 strip 后跳过、编辑器 textContent 非空计数）——两侧谓词统一为 trim 后非空即消除。
- `prose_hash` 规范化管道（前后端共用，钉死）：换行归一 → 按非空段切分 → 各段 trim → `\n` join → sha256。前端 stale 判定对编辑器当前文档按同一管道重算；NBSP 归一不进管道（后端拿 DB 原文，不含编辑器侧 NBSP→空格转换——送检文本以落盘 DB 文本为准，编辑器保存链落盘后两者一致）。
- golden 样本（前后端同环）：连续空行、全空白行、首尾空白段、单段、6 段标准样本。

### D4. 正文标注：TipTap Decorations（前端最大不确定项）

- 封成 TipTap Extension（`zhuque-marks`）：插件状态持有 `{segments, proseHash}`；
  - node decoration：paragraph 节点加 `zq-warn`/`zq-err` 类（label 2→warn、1→err）；
  - widget decoration：段落尾插 `contenteditable=false` 的 `.zq-mark m-*` 置信度章。
- **失效**：`editor.on("transaction")` 监听 doc 变更（`tr.docChanged`），按 D3 管道重算当前文档指纹（输入＝docToProse(editor 文档) 的保存链同款文本——含 NBSP 归一，防粘贴章「检完即 stale」；随后遍历非空段 trim join sha256）≠ proseHash → 插件状态转「过期」：全部装饰换置灰变体（`.zq-mark.stale`＋段落底色移除），标题区结果条同步灰化＋「正文已修改，结果可能过期」＋重检。流式写入/整档替换（`replaceDocNoHistory` 的 preventUpdate 不拦 transaction 事件）/撤销天然走同一路径。装饰注入后需 dispatch 一个 meta 事务触发 decorations 重算（ProseMirror 插件状态变更的标准动作）。
- 标注状态存 React 层（`useZhuqueCheck` hook）经 extension storage 注入，编辑器实例单例长驻（既有纪律），卸载组件不清编辑器。

### D5. 状态单源与消费链

- **挂载层级**：`useZhuqueCheck` 与其 `(chapterRef, proseHash)` 内存缓存 SHALL 挂在路由边界之上（App 级 provider/context 或模块级单例 store）——三消费点分属不同子树（右栏 Rail、ChapterWorkspace 的 e-head 与 ProsePane），且 `/config` 是独立路由，跳配置页会卸载整个写作视图树；挂低了「拨回开恢复展示」场景必假。存续语义＝**应用会话级**（跨路由/页签存活，应用重启即弃）。
- running/status 下发右栏 SHALL 走 Rail 直连 props（沿用 `aiState` 先例），SHALL NOT 进 `onRailData` effect 包（状态高频翻转会撞渲染死循环纪律，见 09-26 事故）。
- `useZhuqueCheck(projectId, chapterRef)`：持有 `{status: idle|running|ok|error, result, proseHash, stale}`；`AbortController` 挂切章/重复点击；结果按 `(chapterRef, proseHash)` 缓存。README 语义：不进 localStorage、不进 DB。
- 显示开关：`lib/prefs.ts` 扩展 `zhuqueShow: boolean`（默认 true）——应用级本地偏好；三消费点经 props/hook 同源读取；配置页开关写 prefs（跨路由同步经 CustomEvent/事件先例）。
- 四态行判定（右栏）：`useFeature("ai-detect")`（快照精确 MAX；快照缺失/降级一律未授权）→ 非 MAX 锁定；MAX×未配 Key→引导；MAX×已配×开关开→就绪/运行；开关关→不渲染。
- **整卡锁定调和**：免费档 prose 页签的锁定由既有整卡机制承载（`AiAssistPanel.tsx:292` state="member_required"→`.rail-assist.locked`，guard 拦点击走升级出口）——行为恰符合锁定行 spec，不为非 MAX 改行级判定；行级 `zq-maxlk` 仅在卡为 ready 时生效（PRO 档）。锁定行 SHALL NOT 用 disabled 实现（`AiWriterAssistant.tsx:150` disabled 吞 onClick，无法走升级出口）。检测运行期整卡其余行禁用为既有行为，认领不改。

### D6. CSS 词汇入册（对齐四路评审）

- 新增 business 词（book.css 本地段 + model-config.css）：`.cfg-tabs/.cfg-tab`、`.zg-keyrow/.zg-stats/.zg-flow`、`.zq-hd/.hd-top/.hd-bar/.hd-ratio/.hd-act/.hd-errline/.hd-run`、`.zq-mark(.m-ok/.m-warn/.m-err/.stale)`、`.ra-step.zq-guide/.zq-maxlk`、`.zq-toggle-row`。
- 开关复用现役 `.switch-btn/.sw-track/.sw-knob`（评审抓的自造 `.switch` 已废）；`.zrc-*` 遗骸不入册；设计稿里 `.prose p` 选择器实装挂 `.editor` 作用域。
- 原型先行：apply 第一步改 `prototypes/`（model-config、工作台屏）＋ ADJUSTMENTS.md 登记新词映射与偏差——含「设计稿 demo 类 `.zq-new`/`.pill-new` → 实装 `zq-guide`/`zq-maxlk`＋`.pill-warn`」映射、`.prose p`→`.editor` 作用域、`.switch`→现役 `.switch-btn`、stale 过期态示意（设计稿十态未含该屏，按 design-language 状态语言总表出原型）。随后 design:lint → design:check → tsc → e2e。

### D7. 门禁分层

- 前端：`features.ts` 登记 `"ai-detect": { memberOnly: true }`（注释：MAX 专属、试用不含、快照单源）；右栏行 `useFeature("ai-detect")`；快照缺失/权益降级一律按未授权（锁定）。
- 后端：检测端点挂 `get_current_user + require_ai_access`（会员级防御底，与 ai-check 同款）；MAX 精确性由快照发放保证（S端只对 MAX 发 ai-detect）——本地后端不做 MAX 级二次判定（tier 信息在前端快照，PRD §8.4 认账本地门禁 UX 级）。`require_ai_access` 的 Key 存在性前置检查不过滤 vendor（朱雀-only MAX 作者须能到达检测端点；其 403 文案「开通 PRO 或 7 天试用」对本权益的措辞错位归 pricing §6.5 四档改造统一收口）。
- 配置端点只挂登录（配置页签全档可见可配）。

## Risks / Trade-offs

- **TipTap Decorations 复杂度**（评审评 2-3 天、高风险）：流式写入/整档替换/撤销都会打断指纹 → 标注频繁进「过期」态。接受：过期即变灰提示重检，不做局部增量重映射（成本高且易错位）。重检走作者手动。
- **段落映射漂移**：后端切分与 PM 节点遍历若规则漂移（如段内硬换行）会错位。缓解：切分规则在后端单点＋golden 用例钉「硬换行/连续空行/首尾空白」样本；前端映射单测对齐同一 golden。
- **上游变动/额度收紧**（活动口径）：适配隔离在 `zhuque/client.py` 单文件（schema 变动只改它）；文案全部引用式（「以腾讯云为准」）；额度耗尽走 429 同口径。
- **免费档误配**：非 MAX 配了 Key 但工作台锁定——配置页签保持可配（Key 是作者腾讯资产），锁定文案指明升级后即用；接受「配了暂时用不上」的轻微落差（保留作者已完成的高门槛动作）。
- **旧库兼容**：朱雀配置行进 api_configs 表（vendor 新值）无 DDL；老代码读到 zhuque 行的风险只存在于旧版客户端同库场景（单机单版本，不适用）。
- **require_ai_access 403 文案错位**（现文案承诺「开通 PRO 或 7 天试用」，对 MAX 专属的 ai-detect 是错误承诺）：本 change 不修，归 pricing §6.5 四档改造重写 feature-key 门禁时统一收口；暴露面仅 UI 直调旁路（PRD §8.4 已认账 UX 级门禁）。
