# 任务：拆书合规保护闸门

## 1. 原型先行（C端）

- [x] 1.1 更新 `docs/design-c/drafts/ai-novel-c端-拆书.html`：创建页加承诺状态行（已签署 · 版本 · 时间／未签署）、「阅读并签署」入口、签署弹窗（承诺全文＋一个同意勾选）、来源类型/作者行；截图存 `openspec/changes/c-deconstruct-compliance-guard/prototypes/`，验收＝原型可打开、签署前后两态可见
- [x] 1.2 更新 `docs/design-c/drafts/ai-novel-c端-拆书监控-原型.html`：任务详情加签署状态行（已签署/待同步/待登录/本机签署）、建书弹窗加确认勾选与书名 warn、导出摘要加软门提示；截图同目录，验收＝四个状态与两个弹窗可见
- [x] 1.3 判定并记录：拆书屏不在 `docs/design-c/prototypes/` parity 基线内，`ADJUSTMENTS.md` 不新增条目；验收＝在 design.md 或 change 目录写明判定依据

## 2. 跨仓：S端签署端点（在 S端私有仓执行，本仓只记录契约）

- [x] 2.1 在 S端 仓立配套 change `s-deconstruct-consent`，写入本 change 的接口契约（字段、幂等、401、限流、保留期）；验收＝S端 `openspec validate --strict` 通过
- [x] 2.2 S端 新增 `deconstruct_consents` 表与 alembic 迁移：`(user_id, agreement_version)` 唯一、append-only；字段只有记录 id、`user_id`、`agreement_version`、`agreement_text_sha256`、`server_ts`；验收＝迁移在测试库 up/down 成功，表内无任务/作品/设备/IP 字段
- [x] 2.3 S端 实现 `POST /api/deconstruct/consents` 与 `GET /api/deconstruct/consents`：Bearer 身份服务端解析、版本白名单、`agreement_text_sha256` 64 hex、限流、同用户同版本幂等返回同一记录；验收＝接口测试覆盖 200/400/401/重复签署
- [ ] 2.4 部署测试环境（阻塞：需测试环境 TCB 凭据；本地已用 SQLite 全链验证），用真实 C端 token 签署与重签；验收＝返回 `code:0`、同一记录、服务端时间落库，请求体只有版本与文本哈希

## 3. C端 数据与后端

- [x] 3.1 启动期幂等 DDL：`deconstruct_jobs` 增 `rights_basis`、`source_author`、`source_sha256`、`source_purged_at`、`build_ack_at`、`build_ack_version`；新建本地 `deconstruct_consents`（用户×版本：签署时间、文本哈希、回执、同步状态、重试账）；验收＝老库升级后字段齐全、重复启动不报错
- [x] 3.2 承诺单一事实源：新增附件 `docs/legal/拆书使用承诺-v1.md` 与内置 `agreement_text_sha256` 常量（构建期从文本计算），C端 校验哈希与版本；验收＝单测断言常量与文本一致，改文本不改常量会红
- [x] 3.3 创建任务接口：接收并校验 `rights_basis`（枚举，默认 owned）、`source_author`（选填）；创建前校验本地承诺为当前版本已签署，否则 400；流式落盘时同步算 `source_sha256`；任务落库承诺版本/签署时间/来源；验收＝接口测试覆盖未签署 400、来源缺失 400、成功落库
- [x] 3.4 签署上报器：复用 `call_server_api(..., with_token=True)`；首次签署与版本升级时上报 `agreement_version`＋`agreement_text_sha256`；签署后立即、启动时、每 10 分钟、手动重试；401→待登录，404→本机签署，网络错误→待同步并退避；按用户×版本幂等写回执；验收＝单测覆盖五种结果与重复上报不新增记录
- [x] 3.5 原文 TTL：终态后 7 天（`finished_at` 兜底 `created_at`），启动 sweep 删目录并写 `source_purged_at`；删除任务立即删；续拆遇缺源走 `need_reupload`；验收＝单测用假时钟覆盖到期/未到期/存量任务/续拆
- [x] 3.6 建书硬门：承诺未「已签署」时拒绝受理并返回可区分错误码，前端据此禁用；建书确认时间与版本落库；验收＝接口测试覆盖已签署/待同步/本机签署三种前置
- [x] 3.7 导出标识与证据剥离：`apply.export_products` 在每份 md 末尾与 README 顶部加声明、清单写五个标识字段、重复导出不叠加；`mdrender` 把 `examples` 并入证据剥离集；验收＝导出快照断言声明只出现一次、预览无原文短例
- [x] 3.8 原句证据约束：`field_quotes` 校验单条 ≤120、每卡累计 ≤500（超限截断）；建书投影与提示词不含 `field_quotes`；验收＝校验单测＋建书产物断言无该字段
- [x] 3.9 任务详情响应下发来源类型/作者/承诺版本/签署时间/建书确认；验收＝接口测试断言字段齐全、存量任务显示未登记

## 4. C端 前端

- [x] 4.1 创建任务页：未签署时显示「阅读并签署」与禁用态；签署弹窗展示承诺全文＋一个同意勾选；已签署显示「已签署 · 版本 · 时间」与「查看承诺」；来源类型下拉＋作者输入；验收＝vitest 覆盖未签署/签署中/已签署三态与来源缺失禁用
- [x] 4.2 任务详情：签署状态行（已签署 ok / 待同步 info + 重试 / 待登录 warn + 重新登录 / 本机签署 info）；建书弹窗加「发布前会改名、改写」勾选（不勾禁用「就建这本书」）＋可编辑书名＋同名 warn；导出摘要未签署存证时显示软门提示；验收＝vitest 覆盖四种状态与建书禁用/解禁
- [x] 4.3 知识库详情：原句证据默认折叠，加「看原句」「收起」；列表行与星图不显示；验收＝vitest 覆盖折叠/展开与列表不带原句
- [x] 4.4 文案走查：按 `design-language.html` §13 核对新增文案（动词按钮、无内部词、补救语句带可点击出口）；验收＝新增文案逐条走查；design:lint 唯一红为未改文件的存量 ⚠

## 5. 法律与客服

- [x] 5.1 S端 线上《用户服务协议》升 v2026.12：增补拆书条款（指向附件《拆书使用承诺》、附件构成本协议一部分、合法来源承诺、仅个人学习创作、禁止再发布侵权产物）与侵权投诉 48 小时条款；验收＝条款可在协议中定位、与客服页时限一致
- [x] 5.2 S端 线上《隐私政策》升 v2026.13：披露签署存证只上报账号标识、承诺版本、承诺文本哈希、服务端时间，用途与 3 年保留期；披露原文 7 天清理、本机来源登记不上传；验收＝字段清单与实际请求体逐项对齐
- [x] 5.3 S端 法律页与客服页同批更新（跨仓）：新增 `/legal/deconstruct-consent.html` 附件页；客服页加「侵权举报」场景与 48 小时口径；验收＝页面可打开、时限与 5.1 一致
- [x] 5.4 `docs/legal/README.md` 版本表与待办同步：登记附件《拆书使用承诺》v1，并注明 C端 docs/legal 为历史快照、S端 线上页已迭代；验收＝README 登记附件、指向线上真源

## 6. 测试

- [x] 6.1 后端单测：承诺版本/哈希校验、签署五态、幂等、401/404、TTL、建书硬门、导出标识、`field_quotes` 截断；验收＝3042 passed；2 条基线红为内容仓工作树被清空（`test_kb_baseline_fullchain`/`test_kb_baseline_gate_parity`），与本 change 无关
- [x] 6.2 前端单测：创建页三态、签署状态行、建书确认、知识库折叠；验收＝`cd client/frontend && npx vitest run --coverage` 四项 100% 阈值通过
- [ ] 6.3 e2e：签署（未签→签→待同步→重试→已签署）、已签署跨设备复用、未签署建书被挡、导出 md 带标识；验收＝相关 Playwright 用例通过
- [x] 6.4 覆盖率契约：把新增分支登记进 `src/coverage-contract.ts`（若为页面级新文件）；验收＝coverage 门禁绿

## 7. 回归

- [x] 7.1 `cd client/frontend && npm run design:lint`；验收＝本 change 文件零违规；唯一红为 `docs/design-c/prototypes/preview.html:1` 的存量 ⚠（未改该文件）
- [ ] 7.2 `cd client/frontend && npm run design:check`；验收＝parity 屏像素差 <0.2%（拆书屏不在基线，记录实际输出）
- [x] 7.3 `cd client/frontend && npx tsc --noEmit` 与 `npm run build`；验收＝零错误（仅 chunk >500KB 提示）
- [x] 7.4 `cd client/backend && python -m pytest tests/ -q -m "not perf"`；验收＝3042 passed / 2 基线红（内容仓空，见 6.1）
- [x] 7.5 触共享段判定：本 change 不触碰 `base.css` 令牌与 pill/notice/sk/panel/f-err 家族，不跑 `design-cross`；验收＝在回归记录引用 proposal Design Impact 的判定依据
- [ ] 7.6 e2e 相关套件重跑；验收＝无新增红、无残留测试数据（`npm run e2e:sweep:dry` 干净）

## 8. 归档

- [ ] 8.1 实现 PR 内用 `openspec-sync-specs` 同步 3 个 delta 到主 spec，再 `openspec archive c-deconstruct-compliance-guard`；验收＝主 spec 含新 Requirement、`openspec validate --all` 无新增红
- [x] 8.2 变更记录：在 change 目录留 S端 配套 change 名、灰度观察项（签署成功率/404 比例/建书门触发数）；验收＝交接文档可查
