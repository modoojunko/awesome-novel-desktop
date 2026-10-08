# c-chapter-dead-subtables — 三个无消费方章纲子表退役（knowledge_states / downtime_functions / key_choices）

## Why

c-og-slim-v2 用「不填这一条，正文会不会写坏」的判据清了章纲页面字段，但保留了三张同类历史子表未动（当时明确列为非目标）：`chapter_knowledge_states`、`chapter_downtime_functions`、`chapter_key_choices`。本次按同一判据复核，结论一致——**三者均为零消费方**：

- 页面无任何控件（章纲页从未渲染过它们）；
- 正文两条提示词路径（粗组/素材包）、AI 体检、文风建议、剧情推演、拆章素材全部不读；
- 前端 `src/` 零读取点；装配/拆装只做存储往返。
- 历史佐证（叙事更正）：`useOutline.saveChapter` 是 `\{...existing, ...data\}` 整体合并 PUT——三键随装配输出**被原样回传**（回显而非「表单发送空数组」）；含历史内容的章回传的是已填充数组。结论不变（零产生零读取），且「停发即清空」正是预期退役路径，专项测试 SHALL 覆盖「含历史内容的章保存一次 → 三键清空、留存字段逐字不变」。

零用户（2026-09-18 确认）口径下，按 c-og-slim-v2 先例干净拆除。本 change 是 c-og-slim-v2 的姊妹篇，机制完全复用（模型摘列、拆装收口、备份升版、旧包忽略）。

## What Changes

- **BREAKING** 三张子表随模型摘除：`chapter_knowledge_states`、`chapter_downtime_functions`、`chapter_key_choices`（类＋relationship＋装配/拆装＋`_CHILD_ATTRS`）；`_split_labeled` helper **保留**（`required_changes` 留存子表仍用它做「场景：功能」拆分）。
- **BREAKING** 备份包 FORMAT_VERSION 5→6（删键＝升版）；v5 及更早包照常导入，三个键按忽略处理并在导入报告计数（复用 c-og-slim-v2 的 retired-key 计数机制）。
- 章装配（assemble_chapter）不再输出 `memo.downtime_functions`/`memo.key_choices`/`knowledge_states`；导出、登录态导出（loginless YAML）同源收缩。
- 旧库迁入仍走列交集（三张表不搬），无 DDL。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-data`: 三张子表退役（持久化 requirement 收窄到留存子表：出场角色/伏笔项/必须完成的变化/禁止事项/读者获得）；导出不再输出三键；备份包升 v6 与旧包读窗。

## Impact

- `client/backend/models/chapter.py`、`models/__init__.py`、`chapters/store.py`、`backup/format.py`、`backup/importer.py`、`chapters/versions.py`（旧快照忽略）、`scripts/seed-demo.py`（已不含，核对即可）。
- 测试：`test_volume_chapter_crud`／`test_backup_roundtrip`／`test_workflow_api`／`test_export_db_zip` 中三子表的种子与断言随退役收缩；`test_og_slim_v2_retire` 的 retired 集合扩容。
- 前端零改动（无读取点、无控件）。
