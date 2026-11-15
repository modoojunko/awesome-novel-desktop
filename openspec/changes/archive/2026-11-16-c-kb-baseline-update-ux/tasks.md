# Tasks: c-kb-baseline-update-ux

## 1. 后端

- [x] 1.1 `kb/baseline.py`：新增 `maybe_sync()`——KB_BASELINE_SYNC=0 闸＋纯本地早退
      （app_meta 有版本且层非空）＋`create_task(_sync_with_logging())`；复用 `_syncing` 锁
- [x] 1.2 `auth_local/service.py`：browser_auth 成功段 `maybe_after_auth` 后并排挂
      `maybe_sync()`，try/except S110
- [x] 1.3 `kb/router.py`：新增 `GET /baseline/probe`——latest 验签＋版本比对，失败
      update_available:false＋reason；DNS 丢 to_thread
- [x] 1.4 后端测试 `tests/test_kb_baseline_sync_ui.py`：
  - probe 同版 false／新版 true／CDN 失败 false+reason（mock `_fetch_json`）
  - maybe_sync：层空触发／已装早退零外呼／KB_BASELINE_SYNC=0 短路
  - browser_auth 钩子挂载断言（mock maybe_sync）

## 2. 前端

- [x] 2.1 `lib/kbApi.ts`：新增 `baselineProbe()`；确认 `baselineStatus/baselineSync` 可复用
- [x] 2.2 `lib/kbProbe.ts`：lastProbe 缓存＋在途槽＋登出复位＋暂不锚（localStorage）＋
      `openKbSyncModal`（enqueueDialog 队列）
- [x] 2.3 `components/kb/KnowledgeSyncModal.tsx`：update/manual 两模式＋更新动作
      （await sync→toast）＋暂不记锚
- [x] 2.4 `pages/KnowledgeBasePage.tsx`：挂载探测→自动弹 update；页头「官方知识 vN」
      manual 入口；同版零渲染
- [x] 2.5 前端测试：`__tests__/KnowledgeSyncModal.test.tsx`（两模式/更新/toast/暂不锚）
      ＋KnowledgeBasePage 既有测试补 probe/sync mock；`npm run coverage` 过页面契约

## 3. 验证

- [x] 3.1 E2E 演练（独立环境）：本地 http.server 服知识仓 dist/baseline＋
      `KNOWLEDGE_CDN_BASE` 指本地＋独立 DATA_ROOT/端口起 backend——首启同步 v3→
      手造 v4（复制 v3＋manifest version=4＋`manifest_crypto` 重签＋latest 重签）→
      probe 弹 update 窗→更新落 v4＋toast；暂不锚同版不重弹、造 v5 重臂
- [x] 3.2 `KB_BASELINE_SYNC=0` 全量测试不联网（conftest 闸验证）＋后端全量 pytest 绿
- [x] 3.3 收环境（杀服务/清临时目录）＋openspec validate

## 4. 收尾

- [ ] 4.1 boss 真机走查（下版装机后：知识库页自动弹更新窗＋手动入口）
