# 设计：dev 哨兵分流件纳入迁入候选

## Context

实勘（origin/main @ 51076a42）：

- `schema_version.parse_db_filename` 的形状枚举：`_DISPOSED_RE = ^novel-v([A-Za-z0-9._-]+)\.db\.(mismatch|corrupt)-[0-9TZ:._-]+$`——只认 `novel-v{X}` 前缀的分流件。
- dev 构建本机版本为 `dev`（无 `{X}`），首启状态机分流产出 **`novel-dev.db.mismatch-<stamp>`**——`parse_db_filename` 判 `DBName(None)`，`is_candidate=False`。
- `scan_migration_candidates` 只按 `is_candidate`＋空壳过滤，无形状逻辑；`candidate_rank` 对 `kind='mismatch'` 走 `version_sort_key(parsed.version)`，`version=None` → `((-1,),0,())` 全域垫底，不抛异常。
- 迁移引擎（precheck/preview/start）与清理端点的路径校验全部经 `parse_db_filename` 白名单——单源形状枚举修复后全链自动受益。
- 前端 `LegacyMigrateModal` 不消费 `version` 字段（展示文件名/书数/时间），无展示面风险。

## Goals / Non-Goals

**Goals**

- `parse_db_filename` 认取 `novel-dev.db.mismatch-<stamp>`（候选）与 `novel-dev.db.corrupt-<stamp>`（隔离件，对称认取不进候选）。
- dev→dev 换代后书库在找回向导可见、可一键带回；全链（候选/预览/搬运/清理）零额外改动走通。

**Non-Goals**

- 不改首启状态机的分流行为（改名形状维持现状——它是既定产物，补的是**下游识别**）。
- 不动版本构建路径（`novel-v{X}.db.mismatch-*` 旧行为逐字回归）。
- 不给 dev 哨兵发明版本语义（version 保持 None，不伪造 `dev` 串参与版本比较）。
- 不做 UI 变更。

## Decisions

1. **形状枚举落点在 `parse_db_filename` 单源**（新增一条 `SENTINEL_DISPOSED_RE = ^novel-dev\.db\.(mismatch|corrupt)-[0-9TZ:._-]+$`，插在 gen0 判断之后、`_DISPOSED_RE` 之前）：mismatch → `DBName("mismatch")`（version/generation 均 None），corrupt → `DBName("corrupt")`。与 #464 的白名单形状枚举纪律一致（不得 `novel*` 前缀通配——本正则是精确哨兵名前缀，非通配）。
2. **version=None 而非 'dev'**：`_VERSION_RE` 不收纯字母串，`_versioned('dev')` 会判 None；且 version 参与排序/推荐比较，None 走 `version_sort_key` 的非法串降级分支（垫底、不抛）——语义与「dev 哨兵垫底」既有口径一致。`candidates` API 的 `version` 字段对哨兵件返回 null，前端不消费，无展示面。
3. **`candidate_rank` 不改**：mismatch 分支已存在，`version_sort_key(None)` 天然垫底——哨兵件排全部具名候选之后，推荐位（「第一个不新于当前版本的候选」）逻辑不受影响。
4. **测试三钉**（`tests/test_db_lifecycle.py`）：parse 新形状三例（dev mismatch→mismatch 候选、dev corrupt→corrupt 非候选、`novel.db.e2e-*` 等残件回归 None）；scan 集成用例（tmp 目录造含 1 书的 dev 分流件 → `scan_migration_candidates` 命中、book_count=1；空壳哨兵分流件不进候选）；既有 `novel-v{X}` 用例回归（`test_v4_unreadable_quarantined_not_candidate` 等）。

## Risks / Trade-offs

- 哨兵分流件排序垫底：多候选时排在具名版本之后——可接受，dev 件本就是最低优先级，推荐位不受影响。
- 借形状手工恢复的存量件（如 09-24 案例中已改名 `novel-v0.0.db.mismatch-*` 的库）本形状已合法，修复后无行为变化；若盘上还留有未恢复的 `novel-dev.db.mismatch-*` 原始件，修复后自动变为可见候选——正是本 change 的目的。
