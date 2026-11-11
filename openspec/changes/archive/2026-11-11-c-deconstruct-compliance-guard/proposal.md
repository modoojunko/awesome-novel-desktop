# 拆书合规保护闸门

## Why

拆书链路现在对"文本来源是否合法"零校验、源文件永久留存、建书一键继承原著人物与设定、导出无任何 AI/版权标识；法务侧的用户协议与隐私政策也未覆盖拆书场景。结果是三类可被追责的风险同时存在：用户把盗版文本带进来（帮助侵权）、应用长期持有并导出逐字内容、用户用拆书产物直接生成与原著实质相似的新书。

本次变更不加"不许拆"的限制，而是把已有能力补上最小必要的闸门：来源有登记、承诺有签署、原文有期限、建书有确认、出口有标识。让拆书从"能做"变成"有据可查、有门可挡"。

## What Changes

- **创建任务新增使用承诺前置**：未签署当前版本《拆书使用承诺》时，先弹承诺全文与一个同意勾选，签完才能创建；已签署的显示「已签署 · 版本 · 时间」与「查看承诺」，不再逐次勾选。承诺覆盖三件事：这本书我有权使用、拆出来的内容只给自己写作用、正文会发给我选的模型服务商。
- **承诺一次性签署、服务端只存签署事实**：首次拆书（或承诺版本升级后首次）签署；S端只存四个字段——谁（`user_id`）、签了哪版（`agreement_version`＋`agreement_text_sha256`）、什么时间（`server_ts`）。不存任务、书名、作者、正文、文件哈希、设备指纹。签署状态随账号走，换设备/重装不用重签；版本升级需重签。断网/服务不可达时先本机记签署，后台重试，不阻塞拆解；建书出口要求「已签署并存证」，导出为软门（可本机继续但留痕）。
- **创建任务新增来源登记**：作者（选填）＋来源类型（自己买的 / 自己写的 / 公版书 / 作者授权 / 其他，必填，默认自己买的），落库并随任务详情可见；未选来源类型时后端 400。
- **源文件限期留存**：任务进入终态后保留 7 天，到期由启动 sweep 清理目录；删除任务仍立即清理。清理后结果目录/导出/预览不受影响；失败任务续拆走既有「需重传」路径。
- **建书出口新增合规确认**：确认建书前必须勾选「发布前会改名、改写」；弹窗明示角色名、别名与世界设定会原样带入；新书书名可改，沿用原书名时给 warn 提示（不阻断）。
- **导出新增 AI 辅助生成标识**：每份产物 md 页脚与 README 顶部加声明；`导出清单.json` 写入 `ai_generated`、`generator`、`source_book`、`generated_at` 与使用提示。
- **作家 md 去除原文短例**：`examples`（原文短例）并入证据剥离集，不再随预览/导出出现；证据报告弹窗照常可见。
- **知识库原句证据收紧**：`payload.field_quotes` 单条 ≤120 字、每卡累计 ≤500 字；详情抽屉默认折叠，点开才显示；不随知识条目导出/复制/分享（本机备份可含，用于恢复）。
- **法律文本：主协议加条款、承诺做附件**：《用户服务协议》增补一条拆书条款并指向附件《拆书使用承诺》（附件构成本协议一部分），附件在首次拆书时签署；隐私政策增补签署上报字段与原文 TTL；客服页新增「侵权举报」场景（作品名、权属说明、侵权位置、联系方式，48 小时内回复）。
- **BREAKING**：首次拆书需签署《拆书使用承诺》，来源类型改为必选；存量用户下次拆书需先签一次。
- **BREAKING**：源文件 7 天后清理，超过 7 天的失败任务续拆需重新上传。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deconstruct-book`：创建任务（使用承诺、来源登记）、源文件留存与清理、建书前合规确认、拆书产物 AI 生成标识、作家 md 证据剥离范围（新增 `examples`）。
- `knowledge-base`：原句证据字段的长度与总量约束、默认折叠、出口剥离。
- `contact-support`：侵权举报场景与 48 小时响应口径。

## Design Impact

- **受影响端**：C端（主）。S端仅法律页与客服页文案同步（跨仓，本地检出由 `S_SERVER_DIR` 指定）。
- **屏/弹层**：创建任务页（上传表单＋提示区）、任务详情（任务信息、结果目录、出口弹窗）、知识库详情抽屉、S端客服页。
- **对象状态**：沿用既有 notice 的 info/warn 两级与既有 checkbox 行；不新增状态语义、不新增组件形态、不新增语气档。
- **共享段**：不触碰 `base.css` 令牌与 pill/notice/sk/panel/f-err 家族，不需要 `design-cross` 双端同改。
- **原型先行**：更新 `docs/design-c/drafts/ai-novel-c端-拆书.html`（创建页声明与来源登记）与 `docs/design-c/drafts/ai-novel-c端-拆书监控-原型.html`（建书确认与导出提示）。拆书屏不在 `prototypes/` parity 基线内，更新后在 change 目录附截图对照，`ADJUSTMENTS.md` 不新增条目。
- **设计工件**：实现侧自查（沿用既有表单与 notice 词汇），不另开设计会话。
- **文案口径**：按钮词用动词（「创建任务」「就建这本书」「收进知识库」保持不变），不出现"合规/门控/就绪度"等内部词；补救语句带可点击出口（如「重新选文件」「去重传」）。

## Impact

- **代码**：`client/backend/deconstruct/{router,service,apply,mdrender,dispatcher}.py`、`client/backend/models/deconstruct.py`、`client/backend/kb/{gates,payloads,service,router}.py`、`client/frontend/src/components/tools/{CreateTaskPage,TaskDetailPage}.tsx`、`client/frontend/src/pages/KnowledgeBasePage.tsx`、`docs/legal/*`。
- **数据**：C端 `deconstruct_jobs` 新增 `rights_basis`、`source_author`、`source_sha256`、`source_purged_at` 四列（本机台账，不上传）；新增本地表 `deconstruct_consents`（`(user_id, agreement_version)` 唯一，记签署时间、文本哈希、回执、同步状态）。S端新增 `deconstruct_consents` 表（append-only，`(user_id, agreement_version)` 唯一）。两处均沿用各自仓的迁移体系（C端 幂等 DDL、S端 alembic）。
- **接口**：`POST /api/deconstruct/tasks` 新增表单字段 `rights_basis`、`source_author`；任务详情响应新增来源与承诺信息；新增 C端→S端 `POST /api/deconstruct/consents`（请求体只有 `agreement_version` 与 `agreement_text_sha256`）与只读 `GET /api/deconstruct/consents`；`导出清单.json` 新增标识字段。
- **兼容**：存量任务无确认字段按「未登记」展示，不阻断查看/导出；存量源文件在升级后按 `finished_at` 计算 TTL 清理；存量 `field_quotes` 超限值读取侧截断显示，不做迁移；S端 签署端点未上线时 C端 按本地签署降级，不阻塞拆解。
- **跨仓**：S端 需同批立配套 change（暂名 `s-deconstruct-consent`）：Bearer 鉴权、`(user_id, agreement_version)` 幂等、版本白名单、append-only 保留 3 年、限流；C端 在 S端 未上线时按「存证未开通」降级为本地记录，不阻塞拆解、不硬门。法律页与客服页同批更新，C端 不硬编码 S端 域名（沿用 `portal_url` 体系）。
- **不在本次范围**：成稿下载（`manuscript-download`）的 AI 标识、建书自动改名/去标识化、建书文风示范段的逐字摘录收紧、产出与源文本的相似度闸、正文导入（`import-own-book`）的权利声明——各自后续独立 change。
