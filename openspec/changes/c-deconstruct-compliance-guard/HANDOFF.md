# 交接：c-deconstruct-compliance-guard

## 本次落地

### C端（本仓）

- **原型**：`docs/design-c/drafts/ai-novel-c端-拆书.html`（承诺卡/签署弹窗/来源登记/四态状态行/建书确认/导出软门）、`拆书监控-原型.html`（运行态承诺胶囊）；截图与 parity 判定见 `prototypes/`。
- **后端**
  - `models/deconstruct.py`：`deconstruct_jobs` 增 `rights_basis/source_author/source_sha256/consent_version/consent_signed_at/source_purged_at/build_ack_at/build_ack_version`；新增 `DeconstructConsent`（用户×版本、同步状态、重试账）。
  - `deconstruct/consent.py`：承诺文本/哈希单一事实源、签署、五种上报结果、`sync_pending`、10 分钟补偿循环。
  - `deconstruct/router.py`：`GET/POST /api/deconstruct/consent`、`POST /api/deconstruct/consent/retry`；创建任务校验来源类型与已签署、流式算 SHA-256；建书硬门（`build_ack`＋`can_build`）与可编辑书名。
  - `deconstruct/pipeline.py`：`purge_expired_sources`（终态 7 天，删目录写 `source_purged_at`），并入 `startup_sweep`。
  - `deconstruct/mdrender.py`：`examples` 并入证据剥离集；`AI_NOTICE` 与 `with_ai_notice`（预览/导出同口径）。
  - `deconstruct/apply.py`：README 顶部声明、`导出清单.json` 五个标识字段。
  - `kb/payloads.py`（＋ vendor_sdk 同源副本）：`field_quotes` 单条 120/卡累计 500 截断。
- **前端**
  - `CreateTaskPage`：承诺状态卡/签署弹窗/来源类型/作者；未签署禁用创建。
  - `TaskDetailPage`：签署状态行（四态＋重试/登录）、建书确认勾选、可编辑书名与同名 warn、导出软门提示。
  - `KnowledgeBasePage`：原句证据默认折叠（看原句/收起，换实例复位）。
  - `deconstructApi`：consent 三端点、创建参数、`importBookFromTask` 的 `buildAck/bookName`。
- **法律**
  - `docs/legal/拆书使用承诺-v1.md`（与代码 `CONSENT_TEXT` 同文）。
  - `docs/legal/README.md`：登记附件；注明 C端 docs/legal 为历史快照、S端 线上页为真源。

### S端（独立仓 worktree：`/tmp/s-consent-wt`，分支 `s-deconstruct-consent`）

- OpenSpec change `s-deconstruct-consent`（proposal/spec/design/tasks，validate 通过）。
- 新表 `deconstruct_consents`（五业务列、`(user_id, agreement_version)` 唯一、append-only）＋ alembic `e9f0a1b2c3d4` ＋ `pg_schema` 登记。
- `POST/GET /api/deconstruct/consents`：`get_bound_identity`（含 token_version）、body 只收两字段、未知字段 400、版本白名单、哈希 64 hex、幂等、审计日志。
- `SENSITIVE_PATHS` 登记；SQL/PG 双仓储与 factory。
- 法律页：`user-agreement.html` 升 v2026.12（拆书条款＋侵权通知）、`privacy-policy.html` 升 v2026.13（签署记录字段/3 年/原文 7 天）、新增 `legal/deconstruct-consent.html`；客服页加「侵权举报」场景（48 小时）。

## 验证结果

| 项 | 结果 |
|---|---|
| C端后端 `pytest tests/ -q -m "not perf"` | 3037 passed / 2 failed；2 条为内容仓工作树被清空导致的 `test_kb_baseline_fullchain` 与 `test_kb_baseline_gate_parity`（与本 change 无关）；本次新增 consent 5 条、建书门 3 条、SDK 上限 1 条、mdrender 2 条均通过 |
| C端前端 `npx vitest run --coverage` | 175 文件 / 2210 通过 / 1 跳过；四项覆盖率阈值通过 |
| C端 `npx tsc --noEmit` | 通过 |
| C端 `npm run build` | 通过（仅 chunk >500KB 提示） |
| C端 `npm run design:lint` | **基线红**：`docs/design-c/prototypes/preview.html:1` 的 ⚠（本 change 未改该文件） |
| C端 parity `design:check` | 被 design:lint 基线红挡住；直接跑 parity 需 :5174 dev server（本次未起），且拆书屏不在 parity 基线、未改 parity 屏 |
| S端 `ruff check app/ tests/ scripts/` | 通过 |
| S端 `pytest tests/ -q` | 717 passed，1 条 `test_short_period_refund` 为 main 基线红（main 同红，与本 change 无关） |
| S端 `vue-tsc --noEmit` | 通过 |

## 未完成 / 待办

1. **S端 部署测试环境**（C端 tasks 2.4）：需 TCB 凭据；本地 SQLite 全链已验证，PG HTTP 路径需在测试环境用真 token 跑一次签署/幂等。
2. **e2e**（C端 6.3）：签署三态、未签署建书被挡、导出标识的 Playwright 用例待补；本机未起 e2e 栈。
3. **design:check**：需先清 `preview.html` 的存量 emoji 红（本 change 范围外）并起 :5174 dev server；拆书屏不在 parity 基线。
4. **C端 docs/legal 快照**：本地 v2026.08 已落后 S端 线上 v2026.11/v2026.12；后续应从 S端 回灌一次，避免双源漂移。

## 灰度观察

- 签署成功率（`event=deconstruct_consent.sync state=*`）
- 404 比例（S端 未上线时的降级量）
- 建书门触发数（`build_ack`/`can_build` 409）
- 原文清理量（`event=deconstruct_source_purged`）
