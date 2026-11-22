## Why

作家说「根据标题，帮我选定题材」时，助手只有题材四格工具（爽点/红线/代价/战场），没有「选 01 题材目录（大类＋子类）」的能力：模型只好拿 `settings_genre_core_promise` 顶替，产出 `{value, note}` 的爽点卡。卡面还把字段名 `value` 原样打出，采纳后写的也是「主要看什么」，不是题材本身。

## What Changes

- 新增只读工具 `read_genre_catalog`：返回封闭题材目录（36 大类＋子类，含解读/案例），供模型按标题判断。
- 新增产卡工具 `settings_genre_pick`：模型给出 `theme`/`sub_genre`/`note`，后端按目录校验，产出 `stype=genre, field=catalog, value={theme, sub_genre, note}` 的采纳卡（不直接写库）。
- 前端新增「题材采纳卡」渲染：行标签为题材/子类/理由，不再出现裸 `value`；「采纳 · 写入」走既有 `PUT /settings/genre`，只改 `theme`/`sub_genre`，其余字段保持。
- 设定字段卡（core_promise 等）统一按字段映射中文标签，`value` 不再原样上屏。
- 设定域纪律补一句：作家说「选/定/判断题材」默认指 01 题材目录；「爽点/红线/代价/斗什么」才用题材四问。
- 设定域窄意图 prime：命中「根据标题选/定/判断题材」时首步确定性调用 `read_genre_catalog`，先把封闭目录放进当轮上下文（显式 chip tool_hint 优先；纯读零副作用）。
- 修 prime 与模型首步共用 stepId 的老问题：prime 步与模型工具步 SHALL 各用独立 stepId，否则前端同 id 工具卡合并、目录步在过程区消失（真机 smoke 实锤）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-tools`: 新增「题材目录选择工具」要求（读目录＋选题材卡＋目录校验）。
- `assistant-chat-ui`: 新增「题材采纳卡」要求（中文标签、写回 01 题材、字段卡去裸 `value`）。

## Impact

- 后端：`assistant/tools_settings.py`、`assistant/scopes.py`；测试 `test_page_scopes.py` / 新增工具测试。
- 前端：`components/novel/chat/CardBody.tsx`、`lib/dockWriteBack.ts`；测试 `cardBody.test.tsx`、`dockWriteBack.test.ts`。
- 无 DB/schema/API 迁移；卡 payload 为新增形态，旧卡不受影响。
