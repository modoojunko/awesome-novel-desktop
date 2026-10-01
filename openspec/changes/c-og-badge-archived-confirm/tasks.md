# c-og-badge-archived-confirm · Tasks

## 1. 原型先行（硬流程）

- [x] 1.1 `docs/design-c/prototypes/book.html`：徽标计数（~L1836）、树 dot（~L1899）、删除盘点 chips（~L2025）、firstPending（~L2266）四处判定补「或已归档」，与实现新口径一致（种子数据下像素零差）。验证：肉眼对照四处 + `git diff` 只含判定行。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记条目（规则对齐原因＋像素零差说明）。验证：条目落在书工作台小节。

## 2. 前端主修

- [x] 2.1 `client/frontend/src/hooks/useOutline.ts` `deriveOutlineStatus` 首分支加 `|| meta.status === "archived"`，置于 chapterData 判定之前；注释标明投影语义与 c-og-confirm-gates 时点。验证：`npx tsc --noEmit` 零新增错误。
- [x] 2.2 vitest 钉（`src/__tests__/useOutline.test.tsx` 或新文件）：①树含 archived 章 → chapterStatuses="confirmed" 且 confirmedCount 含它、全归档时 allConfirmed=true；②loadChapterData 后（chapterData 带 summary）归档章仍 confirmed（分支顺序钉）；③draft+概要 → in_progress（unarchive 回落钉，经 refetchTree 不清 chaptersMap 路径）；④负钉：meta.status="draft" 的桩不因任何 outline_status 判 confirmed。验证：`npx vitest run` 全绿。
- [x] 2.3 vitest 徽标钉（`src/__tests__/NovelWorkspace.test.tsx`）：全归档树 → modnav 出现「4/4 章纲」。验证：同上。

## 3. 后端守卫（与 c-og-confirm-gates 逐字同形）

- [x] 3.1 `client/backend/chapters/router.py` confirm 端点：`_validate_ref` 之后、`load_chapter` 之前加归档章 409 守卫（逐字抄 bc0a4380 hunk，含注释与文案；`chapter_repo` import 同步上移）。验证：`git -C /Users/modoojunko/Desktop/coding/ai-novel-og-gates show bc0a4380 -- client/backend/chapters/router.py` 与本地 diff 逐字对拍。
- [x] 3.2 pytest 四例（`tests/test_write_archive_meta_sync.py`，复用既有夹具与 HTTP POST /archive 触发模式）：①免费档 confirm×archived → 409，且 status/archived_at/total_archives/Archive 行不变式断言；②PRO 档（`_set_tier("monthly", _future_iso())`）同场景 → 409 非 400（守卫先于 tier/gate 的排序钉）；③归档→unarchive→confirm→重归档全环 → total_archives 恒 1、终态 archived、树 `archived is True`；④409 后 GET /volumes 树契约 `archived is True`。验证：`pytest tests/test_write_archive_meta_sync.py` 绿。

## 4. e2e 桩修真

- [x] 4.1 `client/frontend/e2e/design-parity-book.spec.ts`（~L85 ch2）、`design-parity-preview.spec.ts`（chapter 工厂＋~L113 chapterDetail）、`manuscript-download.spec.ts`（~L54-55）：`archived:true` 的桩统一改 `status:"archived"`，断言一律不动。验证：`grep -n '"confirmed"'` 三文件无 archived:true＋status:"confirmed" 组合残留。

## 5. 门禁与交付

- [x] 5.1 后端：`ruff check app tests scripts`（client/backend ruff.toml 口径）＋`pytest` 全量绿。验证：两命令零红（存量红逐条对照 main 基线）。
- [x] 5.2 前端：`npx tsc --noEmit`＋`npx vitest run` 全量绿。验证：零新增红。
- [x] 5.3 `openspec validate c-og-badge-archived-confirm` 通过。验证：CLI 零 error。
- [ ] 5.4 提交（ Proposal 与实现分开或同批均可）＋推送＋PR：标题带 change 名；描述注明①与 c-og-confirm-gates 的 router.py hunk 逐字同形（先合方为准，后合方 rebase 即 no-op）、②409 的 spec delta 归 c-og-confirm-gates、③parity 不作为本修验证手段（不进 CI）。验证：PR 创建成功且描述含去重说明。
