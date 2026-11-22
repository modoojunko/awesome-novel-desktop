## Context

题材有**两层**：01 题材目录（`theme`/`sub_genre`，封闭 36 类）与 02-05 题材四格（core_promise/forbidden_list/cost_ratio/battlefield）。现有助手工具只覆盖四格；模型遇到「选题材」只能拿四格顶替。前端通用兜底又把 `value` 键原样打出，卡面像程序字段而不是人话。

## Goals / Non-Goals

**Goals:**
- 作家说「根据标题选/定/判断题材」时，助手能按封闭目录给出可采纳的 01 题材卡。
- 采纳卡写回 `theme`/`sub_genre`，与题材面板手选同一条 PUT 链，其余字段不动。
- 所有设定字段卡都不再显示裸 `value` 键。

**Non-Goals:**
- 不做新的 LLM 生成端点：选题由助手模型基于目录推理，工具只校验与出卡。
- 不做多候选投票卡：一次给一个推荐（含理由）；作家要备选可继续对话。
- 不改题材目录本身、不改四格工具语义。

## Decisions

### 1. 读目录与出卡拆成两个工具

`read_genre_catalog`（read）返回全部大类/子类的解读与案例；`settings_genre_pick`（card）只接收 `theme`/`sub_genre`/`note` 并出卡。

- 理由：目录约 26KB，不适合塞进每轮系统前缀（前缀缓存/预算）；按需读一次，模型基于真值选，避免幻觉出不存在的题材。
- 备选：把目录塞进工具 description（每轮随 tools 下发，太重）；让模型凭常识选（未知 400，体验差）。

### 2. 出卡不写库

`settings_genre_pick` 只产 `kind="text"` 卡：`payload={stype:"genre", field:"catalog", value:{theme, sub_genre, note}}`。写回仍由作家点「采纳 · 写入」触发，走既有 `PUT /settings/genre`。

- 理由：与既有设定卡一致（产物一律过目，不直接落库）；授权/刷新链零新增。
- 备选：走 `write_settings_field` 授权卡（多一道批复，且四格字段白名单不含目录，需扩写面，否决）。

### 3. 前端按 `field=catalog` 特判渲染

`CardBody` 在 `stype/field` 存在时先走设定字段分支：`catalog` 渲染 题材/子类/理由 三行；其它字段用字段中文名（主要看什么/绝对禁止/吃苦指数/本小说斗什么/简介/世界各格）替代裸 `value`。对象形 `{value,note}` 拆两行。

`writeBackSettingsField` 对 `catalog` 取当前 genre 设置，写 `theme`/`sub_genre` 后整包 PUT；保留其余键。

### 4. 纪律句区分两层「题材」

`PAGE_DISCIPLINE["设定"]` 追加：作家说「选/定/判断题材」默认指 01 目录，先 `read_genre_catalog` 再 `settings_genre_pick`；说「爽点/红线/代价/斗什么」才用四格工具。静态字符串，不破坏前缀缓存。

### 5. 窄意图 prime 读目录（确定性）

`router.genre_prime_hint`：设定域内命中「根据/按标题选/定/判断/推荐题材」「这本书算什么题材」时，首步 prime `read_genre_catalog`（`{tool,args:{}}`），目录必然进当轮上下文；显式 `tool_hint` 优先、域外不触发。

- 理由：模型在长上下文/弱指令下可能跳过读目录直接猜（同 nav 走查 0/3 判例）；读类零副作用，误命中最多多读一次。
- 备选：只靠工具描述（不稳定）；把目录塞系统前缀（重、废缓存）。

## Risks / Trade-offs

- [目录读一次占上下文] → 仅选题材时触发；26KB 在 128K 窗口内，且只进当轮。
- [模型仍误用四格工具] → 工具描述＋设定纪律＋页面域校验三重约束；测试钉住新工具在 `set:` 域内。
- [旧卡 payload 兼容] → 只在 `field=catalog` 时走新分支；旧 `{value,note}` 卡改走字段中文名，形状不变。

## Migration Plan

无迁移。旧会话卡按新渲染逻辑显示更准确的中文标签；写回路径不变。

## Open Questions

（无）
