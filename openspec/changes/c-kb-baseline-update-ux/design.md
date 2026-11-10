# Design: c-kb-baseline-update-ux

抄写蓝本＝提示词包更新链（c-prompt-pack-client / c-prompt-pack-onboard-modal /
c-pack-modal-dismiss），逐件映射到知识基线；关键取舍在 proposal Non-Goals。

## 后端

### `kb/baseline.py` · `maybe_sync()`

照 `prompt_pack/sync.py:755 maybe_after_auth` 的语义：

- 早退**纯本地、零外呼**：app_meta 有 `kb_baseline_version` 且 `kb_baseline_entries`
  非空 → return。与提示词包「已装+档位一致+完好 → return」同构（基线无档位）。
- 需要补装 → `loop.create_task(_sync_with_logging())`（复用既有 `_syncing` 单飞锁
  与静默失败语义）。无运行循环＝静默跳过（同 `schedule_sync`）。
- 受 `KB_BASELINE_SYNC=0` 闸管——与 `schedule_sync` 共用同一检查，conftest 已设，
  防 TestClient 真联网抢 SQLite 写锁（CI `database is locked` 判例）。
- 启动 `schedule_sync` 保持不动（首启首查必发）。

### `auth_local/service.py` · browser_auth 成功段挂点

`maybe_after_auth`（:656）之后并排：

```python
try:
    from kb.baseline import maybe_sync
    maybe_sync()
except Exception:  # noqa: S110 —— 基线补装绝不阻塞登录
    pass
```

路由切换/focus/登录都会走 check-auth（LicenseProvider 两跳节流），钩子随之继承，
无需另做周期轮询。

### `kb/router.py` · `GET /api/kb/baseline/probe`

- async httpx 拉主域/兜底域 `latest.json`（复用 `_cdn_bases`/`_fetch_json`/
  `verify_manifest`），读 `version` 与本地 `kb_baseline_version` 比对。
- 成功：`{installed, latest, update_available}`；失败：`{update_available: false,
  reason}`（latest_invalid / unsafe_url 等，复用 sync 的 reason 词汇）。
- DNS 解析丢 `asyncio.to_thread`（照 `_sync_impl` 同款防线）；httpx 超时 8s。
- 不需要登录门（基线公开），但保持 GET 幂等只读。

## 前端

### `lib/kbProbe.ts`（新，照 `lib/packProbe.ts` 剪裁）

- `lastProbe` 内存缓存＋`claim/release` 在途槽（StrictMode 双挂载去重）
  ＋登出/换号复位（resetPackProbeState 同款）。
- 「暂不更新」锚：`localStorage["kb-sync-dismissed"]`，单键 `{updateVersion}`——
  同版不重弹、版本变化自动重臂（照 pack-modal-dismiss）。
- 弹窗开启走 `enqueueDialog("kb-sync", 2, …)` 壳层队列（带回流程先例）。

### `components/kb/KnowledgeSyncModal.tsx`（新）

两模式（无 install 模式）：

- `update`：自动弹。标题「官方知识有更新」；行「当前 v3 → 最新 v4」；
  动作「立即更新」（动词按钮）／「暂不更新」（记锚）。
- `manual`：页头入口点开。显示当前版本；有新版→「可更新到 v4」＋「立即更新」；
  无新版→「已是最新」。
- 更新动作：`await kbApi.baselineSync()`（既有 POST /kb/baseline/sync，幂等直回）
  →成功 `toast.success("官方知识已更新到 v4")`；失败 `toast.info("更新没有完成，稍后可再试")`
  并保留弹窗可重试。不做 1s 轮询（同步秒级、await 直回）。

### `pages/KnowledgeBasePage.tsx`

- 挂载 effect：claim 探测槽 → `kbApi.baselineProbe()` → setLastProbe →
  `update_available` 且 `readKbDismissal().updateVersion !== String(latest)` →
  `openKbSyncModal({mode:"update", from, to})`。
- 页头小字入口：`官方知识 v{installed}`（probe 缓存有值时显示）→
  `openKbSyncModal({mode:"manual"})`。
- 同版/就绪＝零渲染（照 PromptPackCard「就绪全静默」口径）。

### `lib/kbApi.ts`

复用既有 `baselineStatus`/`baselineSync`（:490-496），新增 `baselineProbe()`。

## 文案（design-language §13 口径，已默读）

- 弹窗标题：「官方知识有更新」（update）／「官方知识」（manual）
- 版本行：「当前 v3 → 最新 v4」（update）／「当前 v3，已是最新」（manual 无新版）
- 按钮：「立即更新」「暂不更新」——动词、无内部术语
- toast：「官方知识已更新到 v4」（ok）／「更新没有完成，稍后可再试」（info，弹窗内可重试＝可点击出口）

## 风险与判例

- **CI 联网锁**：maybe_sync 必须吃 KB_BASELINE_SYNC=0 闸（conftest:237 已设）。
- **弹窗队列**：经 enqueueDialog 不与带回流程抢面（legacy-migrate:open 先例）。
- **探测频率**：页面挂载级（进页一次）＋会话内存缓存；CDN 故障时单次 8s×2 域上限，
  不在渲染关键路径（effect 内 async）。
- **降级拉取**：现有 sync 的版本比对是 `!=` 而非 `>`，CDN latest 回退旧版会被当
  「新版」拉回——发布纪律（版本单调＋latest 最后翻）已覆盖，本 change 不改此语义。
