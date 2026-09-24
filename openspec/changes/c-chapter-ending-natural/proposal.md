# 拆章抽卡章尾自然断点——去掉伪伏笔钩子诱导

## Why

拆章抽卡生成的章尾清一色是「伪伏笔」：神秘人现身、信物露角、异象乍起——模型在硬造悬念感。作者 2026-09-24 拍板：章怎么开头、本章困难是什么、章结束时剧情处在什么局面，**自然断开本章就好，悬念留给读者**（读者想知道"然后呢"），而不是故意写一个感觉有伏笔悬念的结尾。

根因在模板明文：`chapter_split.prompt` 硬规则 4＝「本章结尾停在"还没完"的地方：谁或什么变了、但没被解决，让读者想立刻看下一章」——「谁或什么变了、但没被解决」正是钩子配方；评分四维「拉力」（只看 ending）的现行解释「停在'还没完'的地方」又在排名时二次奖励同一习惯。`chapter_selfcheck.prompt` 的拉力问句与 spec 的四维定义同口径，若不同批对齐，自检会继续按钩子口径给章尾加分，两头漂移。

## What Changes

- **`chapter_split.prompt` 硬规则 4 改写**：结尾停在**剧情自然断点**——写清章结束时事件到哪一步、谁在什么局面，断在事件半途即可；SHALL NOT 刻意制造悬念道具（凭空冒出的新谜团、神秘登场、异象信物）来装「留伏笔」。末章例外（硬规则 5 收卷落预期结局）原样不动。
- **`chapter_selfcheck.prompt` 拉力问句同批对齐**：从「停没停在'还没完'的地方」改为按自然断点判定，防自检与生成两头口径漂移。
- **spec `chapter-plan-ai`「结尾拉力」四维定义 MODIFIED**：`openspec/specs/chapter-plan-ai/spec.md:94`「停在'还没完'的地方」→「停在剧情自然断点（局面未定），而非刻意悬念钩」。spec:104 的 S 级判定（三维均列第一）只引用维度名，不动。
- **刻意不动（划界）**：四维键名「拉力」保留——前端评分条、sanitizer、十余处测试都钉在该键名上，且「拉力」与自然断点不矛盾（断点本身就是"还没完"）；改口径不改名字，前端与既有测试零改动。`ending` 字段定义里 #484 已落的「停在场面状态上——下一章才接得住」方向正确，保留并在规则 4 新文中呼应。
- **模板对拍测试**：新增两条断言钉住新口径（chapter_split 禁悬念道具句、chapter_selfcheck 自然断点句），防回归回退。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：评分四维「结尾拉力」的定义口径从「停在'还没完'的地方」改为「停在剧情自然断点（局面未定），而非刻意悬念钩」。

## Impact

- `client/backend/prompts/chapter_split.prompt`（硬规则 4 一条）
- `client/backend/prompts/chapter_selfcheck.prompt`（拉力问句一行）
- `openspec/specs/chapter-plan-ai/spec.md`（归档 sync 时生效，1 处定义）
- `client/backend/tests/`（模板对拍测试 +2 条）
- 前端、sanitizer、e2e：零改动（键名与 JSON 契约不变）
- 与在途 `c-plan-pacing-rules`（PR #488）无冲突：该 change 对 `chapter_split.prompt` 只加一行 `<<position_rules>>` 占位符（素材块后、硬规则前），明文「主体十条硬规则逐字零改动」，hunk 不重叠，先后合并仅需 trivial rebase。
