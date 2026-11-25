# Tasks: c-kb-server-gated-sync

## 1. C 端后端

- [x] 1.1 `kb/server_api.py`：`sign(scope, version, path, genre)`（`call_server_api("kb/sign")`
  ＋token 空早退 `code=-2`）；`fetch_signed(url, max_bytes) -> (bytes|None, verdict)` 出站
  守卫（`KB_STORAGE_HOSTS` 精确主机＋fake-ip 逃生）＋ `build_async_client`；无公开 CDN。
- [x] 1.2 `kb/baseline.py`：按题材同步 `sync_genre(genre)`；`_load_release` 走 pointer→
  manifest（免费）；`_replace_genre_layer` 只替换该题材层（overlay/carry/提升按题材作用域）；
  `AppMeta["kb_baseline_genres"]`、按题材高水位、全局版本兼容；`resume_baseline` 清撤回；
  启动/登录/周期复查 `sync_baseline` 只 probe（`probed/skipped/failed`）。
- [x] 1.3 `kb/tree_sync.py`：S 端 `tree_pointer`/`tree_data` 签名 URL；树免费；
  `maybe_sync()` 登录钩子自动更新；保留缓存/回执/高水位/结构闸/`KB_TREE_SYNC=0`。
- [x] 1.4 `auth_local/service.py`：登录成功段基线只 probe（不下载）＋知识树 `maybe_sync`。
- [x] 1.5 `kb/router.py`：`POST /baseline/sync` 收 `{genre}` 调 `sync_genre`；`status` 透出
  `genres`；probe 端点不变（只读）。
- [x] 1.6 `write/write_block.py`：冷启动 fingerprint 按书的题材取该题材 version/sha。
- [x] 1.7 `kb/revocation.py`：撤回时一并清空 `kb_baseline_genres`。
- [x] 1.8 `outbound_guard` 复用；`server_api` 默认 COS 桶域
  `ai-novel-knowledge-1468883265.cos.ap-shanghai.myqcloud.com`（预检确认后如有变化改常量）。

## 2. C 端前端

- [x] 2.1 `lib/kbProbe.ts`：`KbProbe`（genres/installed_genres/updates/quota/resume）、
  `KbSyncModalDetail`（probe/focusGenre）；dismiss 锚沿用。
- [x] 2.2 `lib/kbApi.ts`：`baselineProbe` 返回 `KbProbe`；`baselineSync(genre)` POST
  `{genre}`；`baselineStatus` 带 `genres`。
- [x] 2.3 `KnowledgeSyncModal.tsx`：题材清单（已同步/可更新/未同步＋每行同步＋今日剩余/
  重置）＋失败/跳过原因诚实提示＋`focusGenre` 高亮＋同步完成事件；running 单飞。
- [x] 2.4 `KnowledgeBasePage.tsx`：进页 probe 携快照开弹窗；当前题材未同步给「去同步」
  入口；页头入口携缓存快照。
- [x] 2.5 `NovelWorkspace.tsx`：写作工作台 appbar 在书的题材未同步时给「去同步本题材」
  提示（免费 probe；携 `focusGenre` 开弹窗；`kb-sync-completed` 后重算）。
- [x] 2.6 `ADJUSTMENTS.md` 登记「知识库按题材同步/写作提示」口径（Design Impact 见 proposal）。

## 3. 测试与门禁

- [x] 3.1 后端：`tests/test_kb_baseline_sync.py`（按题材替换/幂等/坏哈希保旧层/格式闸/
  carry/overlay/双账号/配额/失败原因）31 passed；`test_kb_tree_sync.py` 20 passed；
  `test_kb_baseline_sync_ui.py` 16 passed（登录/周期只探测不下载）；`test_kb_baseline_fullchain.py`
  2 passed（本地 HTTP 真实下载＋真实验签＋出块）。
- [x] 3.2 后端全量：`PYTHONPATH=. .venv-kb/bin/python -m pytest tests/ -q --timeout=30 -m "not perf"`
  → **3360 passed**（4:46，327 skipped/2 deselected；2026-11-21 本 worktree 独立 venv）。
- [x] 3.3 前端：`tsc --noEmit` 绿；`vitest run` 全量 **182 files / 2283 passed（1 skipped）**；
  `npm run coverage` 阈值全绿（KnowledgeBasePage ≥99/95）。
- [x] 3.4 `ruff check` 改动文件全绿；`npm run check:inline-colors` 绿；
  `npm run design:lint` 唯一红项＝`docs/design-c/prototypes/preview.html` 存量 emoji
  （与本变更无关，记忆已登记）。
- [x] 3.5 OpenSpec：`openspec validate c-kb-server-gated-sync --strict` 绿。

## 4. 跨仓/上线（待执行）

- [ ] 4.1 S 端 `s-kb-signed-delivery` 合并/部署：`kb_sync_events` DDL 带外＋`pg_gate`；
  注入 `COS_BUCKET/COS_REGION`；探活 `/api/user/me`。
- [ ] 4.2 第 0 步 COS 预检：`server/scripts/cos_preflight.py`（列桶/建私有桶/put/presign/
  GET/delete；免费额度控制台核对）；失败处置按 S 端 design D7。
- [ ] 4.3 内容仓：v5 基线（8197 条/36 题材/4.6MB，`resume_baseline=true`）上传 COS →
  翻 `latest.json`；知识树 v2 上传 → 翻 `tree/latest.json`；S 端测试账号走 pointer/
  manifest/genre/tree 下载验签。
- [ ] 4.4 发 C 端新版本：真机登录→知识库页题材清单→同步 A→只装 A→同步 B→A 保留→
  免费第 3 个 429→次日重置；写作工作台提示出现/消失；旧客户端公开树仍可拉。
- [ ] 4.5 一个版本周期后：静态托管删 `knowledge/tree` 及 baseline 残留，`tcb hosting list`
  复核。
- [ ] 4.6 归档 `c-kb-server-gated-sync` + 同步主 specs；README 更新。
