# c-settings-changelog-cast-shape（补录归档）

> 补录说明：本 change 为 PR #565 合入后（2026-09-28）的补录归档（先例：#552 补录 #550），
> 实现先于 change 目录存在。用户指令链：真机报「章纲页设定 tab 本章变化 3 个空行」→ 排查定因 →
> 修复 → 评审 → 合入 → 部署 → 归档。

## Why

「设定」页签「本章变化」按 `Array<{name, state_change}>` 读取章数据的 `outline.characters`，而后端
实际契约（`chapters/store.py`：读侧 `assemble_chapter`、写侧 `_replace_children_impl`，两侧同形）是
`characters`＝**名字 string[]**、各角色状态变化单列 `outline.character_states`（`[{name, state_change}]`，
仅非空条目）。字符串上取 `.name` 得 undefined：真库 vol-1-ch-1 三个出场角色（林野/银铎/邵青梧）名字
在库却被整体丢弃，渲染成空名字行（用户报「3 个空行」）；同型错读使 AiAssistPanel 设定页签统计
「本章变化 N 条」恒为 0。测试 mock（storylineHooksAndLore）也按错误形状造数，把 bug 钉进了门禁。

## What Changes

- **SettingsChangelogPane**：`characters` 按 string[] 取名字，`character_states` 按名字对齐出
  `state_change`；空名过滤（写入口已保证非空，纯防御）。
- **AiAssistPanel** 设定页签统计：`本章变化 N 条` 改从 `character_states` 计数。右栏「角色关系」
  页签同措辞统计数的是 `/characters/graph` 关系边（`origin_chapter`），数据源不同、语义正确，
  评审确认非同型错位、不在修复范围。
- **测试 mock 跟改**：storylineHooksAndLore 改真实契约形状，补出场角色名字上屏断言。
- **非目标**：`state_change` 全空时该节是否收起/换文案（现示「（暂无状态变化）」占位）等拍板另议；
  出场角色重名时 React key 重复为存量（改动前每行 key 恒为 `"null"` 更糟，本次严格改善）；specs 无
  漂移——chapter-data/spec.md（2026-09-28 章档归档新立）只锁 PUT presence-gate 与字段族保持，
  未钉读取形状，零 delta。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——前端按既有后端契约消费，specs 不涉及）

## Impact

- 实现：#565（squash = e427e16d，2026-09-28 合入——CI 三条 CodeQL Analyze 失败＋build 取消与
  #564 完全同签名（main 自身 CodeQL 亦红），按先例本地门禁绿合入）
- 评审：review-agent 全量过（合并基线 0d02dc9e）：API 真实形状闭环验证（workflow.engine.load_chapter
  纯委托 store.assemble_chapter；get_chapter_row 只回元数据、不含 outline 键不覆盖），
  无 qualifying findings
- 验证：vitest 3 文件 12 用例绿（storylineHooksAndLore/rewriteFlow/AiAssistPanel）＋ tsc --noEmit 干净；
  真库 sqlite 拷贝只读实勘佐证
- 部署：演示栈 client-frontend 已重建——主检出因并行会话 WIP 占 `chapter_writer.py` 不能 ff，
  从合并 commit 临时 worktree 构建（compose 带 brand 上下文）；镜像与 5174 线上 bundle 双抓指纹
  `character_states`×2 自证；仅重建前端容器，后端未动（镜像 14:23Z 本就最新）
