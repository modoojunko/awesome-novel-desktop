## Context

C 端当前档位代码仍是四档（`free`/`standard`/`pro`/`max`）：`standard` 为付费入门档，`free` 展示“免费版”，PRO/MAX 的助理能力与官方库/人味/图像/拆书边界分散在 `features.ts`、`STANDARD_FALLBACK`、工具注册表、KB 路由、图像/拆书/人味端点与升级弹窗里。S 端套餐目录/价格/落地页在同批 S change 中改；本设计只解决 C 端如何消费新快照、如何拦截、如何展示。

## Goals / Non-Goals

**Goals:**

- 三档会员在 C 端一致落地：标准（免费）/PRO/MAX；旧 `standard` 仅存量兼容。
- 把“标准＝头脑风暴、PRO＝AI 写手、MAX＝写作秘书”变成可执行的 feature key / 工具 / 端点 / UI 边界。
- 官方库与本地库分层；人味/图像/拆书建书/自动执行按 MAX 收口。
- 旧快照、旧 standard 用户、试用用户都有确定的兼容路径。

**Non-Goals:**

- 不改 S 端支付/订单/退款逻辑；不改落地页视觉；不改知识库数据模型/基线内容。
- 不新增 AI 生成能力；只重排现有能力的档位归属与文案。
- 不把旧 standard 用户追溯降级；不强制迁移其本地数据。

## Decisions

### 1. 内部档位键与展示名

- `free` 继续作为内部键，展示名改“标准”；`pro`/`max` 不变；`standard` 只保留为存量付费档（grandfather），不再新售。
- `tierLabel("free") = "标准"`；存量 `standard` 显示“标准会员（旧）”；`upgradeHintOf` 不再输出“标准档起”，统一 PRO/MAX 专属。
- 理由：避免大规模数据迁移；旧 standard 快照/订单/设备记录仍可按原键读取。替代方案（把 free 重命名为 standard、删除 standard 键）需要迁移所有快照/订单/设备/测试，风险高。

### 2. 权益重排

- PRO 权益 = 旧 standard AI keys + 旧 pro keys + `assistant-execute` + `kb-official`：
  `ai-plan`、`chapter-review`、`settings-ai-fields`、`style-suggest`、`outline-advanced-fields`、`assistant-execute`、`ai-generate`、`prompt-panel`、`ai-detect`、`deconstruct`、`kb-official`、`ai-model`。
- MAX 权益 = PRO + `image-generate`、`human-taste`、`assistant-diverge`、`ai-plot`、`style-quant`、`deconstruct-import`。
- 标准（免费）权益 = 仅 free keys（`tree-crud`/`prose-edit`/`version-history`/`archive`/`volume-chapter-config`/`advanced-config-entry`/`settings-7-items`/`ai-model`）；本地库/助理只读工具不挂 key。
- `trial` = PRO（不含 MAX keys）。
- 理由：PRO 是唯一付费 AI 写手档，必须包含全部“写”能力；MAX 用质量/图像/建书/自动化做增量。替代方案（保留付费 standard 当入门）与“标准免费”拍板冲突。

### 3. 知识库分层

- 本地层（本书/用户条目/决策/拆书产物入库）不挂 key，标准（免费）可读写；助理 `kb_search`/`kb_read` 不挂 key。
- 官方层（官方基线/写法条目/知识树/图谱官方节点/按题材取文风）挂新 key `kb-official`（PRO）。
- `kb_search_craft`、`/settings/style/kb-draft`、官方库查询/树/图谱端点挂 `kb-official`；`kb_create_entry`/`kb_update_entry` 写本地层但属写类工具，挂 `assistant-execute`。
- **不采用**整段 `/api/kb/*` 挂一个 `kb-access`：那会把标准（免费）自己的库一起封死。基线同步/探针保持系统内部，不挂会员门；消费层才挂 `kb-official`。
- 理由：官方库是 PRO 的主要付费理由；本地库是“书稿归你”的信任底座，不能锁。

### 4. 人味/图像/拆书/导入

- `human-taste`（MAX）：`/write/renwei-check` 与助理 `read_prose_checks` 挂 MAX；`AiWriterAssistant` 人味行取消 `ungated`，改 MAX 锁定/升级出口。
- `image-generate` 从 PRO 改 MAX：AI 封面/头像/试画/批量头像/封面画面提取全挂 MAX；手动上传不挂 key。
- `deconstruct` = PRO（拆/看/导出/收进本地库）；`deconstruct-import` = MAX（一键建书）；`collect-to-kb` 补 `deconstruct`；取消/删除保持无门。
- `import-own-book`：直接导入（只带正文）标准（免费）；AI 拆书 PRO。两条路文案分开，不再叫同一个“导入”。
- 理由：与最终三档叙事一致；止损动作（取消/删除）不设门，避免降档用户被卡。

### 5. 授权梯度

- `confirm_each`：标准（免费）无写类工具；PRO 可用但每写必确认；MAX 可用。
- `allow_book`：仅 MAX 可选择；标准/PRO 选择器显示 MAX 锁定，后端 `setPermissionTier`/`evaluate` 拒绝非 MAX 的 `allow_book`。
- `allow_all`：仅存量兼容映射到 `allow_book`，不新增选项。
- 硬地板（删全书/批量删章/覆盖已确认设定/改授权档位）任何档位都弹卡。
- 理由：这是 MAX“更多方便和效率”的最大体感差异；现成能力，只做档位发放，不新造。

### 6. 升级弹窗与文案

- `UpgradeModal` 收成两跳：标准（免费）→ PRO（AI 写手：官方库/规划/正文/拆书/朱雀/提示词）；PRO → MAX（写作秘书：人味+改法/图像/拆书建书/发散/推演/蒸馏/自动执行）。
- 删除 `TIER_PITCH.standard` 的“升级标准”话术；`TIER_PITCH.free` 出 PRO；`TIER_PITCH.pro` 出 MAX。
- 所有 `upgradeHintOf`/锁定行文案统一 PRO/MAX 专属；不再出现“标准档起”。
- 理由：避免标准（免费）用户被“升级标准”误导；两跳与三档模型一致。

### 7. 兼容与迁移

- 旧快照：`_LEGACY_IMPLICIT_FEATURES` 更新为 `kb-official`→pro、`human-taste`→max、`image-generate`→max、`deconstruct`→pro、`deconstruct-import`→max、`assistant-execute`→pro；标准（免费）/过期不隐式放行。
- 存量 `standard`：C 端保留其快照权益到到期；UI 显示“标准会员（旧）”；S 端停售 SKU；到期后按 PRO 升级券或回标准（由 S 运营执行）。
- 试用：`trial` 权益改为 PRO 快照（含 `kb-official`/`deconstruct`/`assistant-execute`，不含 MAX keys）。
- 回滚：C 端回滚到旧版本时，新 key 不识别按旧快照兜底；S 端恢复旧 entitlement/价格即可；无本地数据迁移。

## Risks / Trade-offs

- [标准（免费）已能 AI 头脑风暴 + 自有库，PRO 付费理由偏薄] → PRO 必须让“AI 写手 + 官方库 + 拆书”在产出上可感知（正文/章纲/官方写法引用）；上线后用免费→PRO 转化与 PRO 7 日留存验证，低于阈值再调 PRO 价格或权益。
- [官方/本地库当前是 merged 视图，分层闸可能漏] → 在 KB 查询/树/图谱/草稿端点统一按 layer 过滤；增加“标准看不到官方条目、PRO 看得到”的端点测试与 e2e。
- [`allow_book` 自动执行误伤] → 硬地板不变；自动执行落回执+撤销；MAX 默认仍 `confirm_each`，需用户主动切换。
- [存量 standard 显示名与免费“标准”冲突] → UI 明确“标准会员（旧）”；销售目录不再出现；到期前不追溯降级。
- [两仓发布顺序] → S 端先发 entitlement/价格/套餐目录，C 端后发；旧 C 端忽略新 key，标准（免费）不受影响；新 C 端在旧 S 快照下按 `_LEGACY_IMPLICIT_FEATURES` 保守放行。
- [测试夹具大量假设 standard 付费] → 同批更新 `e2e/tier-features.ts`、features/UpgradeModal/Aui2Dock/AiWriterAssistant 单测；新增“标准免费无 AI 写手/官方库/人味/图像”负向钉。

## Migration Plan

1. S 端：tiers/skus/entitlement 改三档；PRO 49.9/MAX 89.9；旧 standard SKU 下架；生产库走 tier-catalog SOP；旧 standard 用户保留到期。
2. C 端：合入本 change；旧快照按 `_LEGACY_IMPLICIT_FEATURES` 兼容；试用快照改 PRO；存量 standard 快照保留。
3. 灰度/回滚：C 端先发；如出现比例异常，回滚 C 端版本（旧版本忽略新 key）；S 端恢复旧 entitlement/价格；无数据迁移。

## Open Questions

- 无阻塞项。PRO 年付具体扣率/价格由 S 端 SKU 运营按 49.9 月底价重算；C 端只展示目录下发值。
