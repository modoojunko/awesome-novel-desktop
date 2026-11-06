# c-kb-relations-view · Design

## Context

关系读取链路**早已存在**（评审后修正立项时的误判）：`GET /kb/entries/{id}/relations`（kb/router.py）→ `organize.entry_relations`（kb/organize.py，带 user_id 隔离、REL_TYPES 白名单、批量 IN 取对端 title 兜底、输出含 id/rel_type/status/direction/other_id/other_title/note/evidence）→ 前端 `kbApi.entryRelations` + `kbApi.organize.relationFeedback` → `KbEntryRelations.tsx` 完整组件（含「这条不对」反馈、merged 追溯、空态不渲染）。缺口＝`KnowledgeBasePage.tsx` 导入组件却从未渲染（死导入），且组件是 organize 批D 旧形态（rel_type 英文裸键、无点跳、无 active 过滤、无对端归档剔除）。另：知识视图抽屉渲染的是列表行对象（页面不调详情接口），但本组件自带取数（按 entryId 拉关系），不依赖详情聚合——正因此取数通路天然可用。

约束：`get_entry` 只放行 active/merged——对端 status=archived 时点跳必 404；基线代理条目（kb_baseline_entries）在 kb_relations 永无行，`entry_relations` 对其返回 not_found/空。

## Goals / Non-Goals

**Goals:**
- 接通现成链路：抽屉渲染 `KbEntryRelations`，视图即见 active 关系
- 组件升到 v2 口径：中文标签、按类句式、点跳、active 过滤、死链剔除
- 标签词表单一来源（整理面板与视图同源）

**Non-Goals:**
- 不做手动新建/删除关系（另行立项）
- 不改整理产关系/采纳/否决链路；不动 `get_entry` 可达性口径
- 不做点跳深链（`?knowledge=` URL 同步，挂账）；不动段序（导航段上移挂账到证据链落地时一并）
- 不在视图段展示 pending（pending 清单仍在「知识整理」面板）

## Decisions

### D1 复用既有 relations 端点，不新增聚合

不新增 REST 面也不新写查询函数：`entry_relations` 服务加 `status` 入参（`"active"` 只回生效行；默认 `"all"` 保持现行为兼容），router 透传 query 参数；前端取数显式传 `active` 并保留一行防御过滤。理由：该端点与服务已带 user_id 隔离、白名单、批量 title 兜底，新写 `list_active_relations` 会成为第二套同义形状（漂移风险正是 D2 要防的那类）。

### D2 死链剔除在服务侧，一行口径

`entry_relations` 构造行时剔除「对端缺失或对端 `status=archived`」的关系行（对端 `archived_at` 非空但 status=active 的 v2 归档行可达，保留）。点跳永不落 404，前端零特判；基线代理条目查无行 → 空 → 段不渲染，同样零特判。

### D3 标签与句式收敛到 `src/lib/kbRelations.ts`

六类中文标签（**refines 沿用现网「细化」**，不改词）＋按类出入向句式模板（出向「适用于 B／源自 B／属于 B／依赖 B／与 B 相冲／细化 B」；入向「B 适用于本知识／B 源自本知识／B 属于本知识／B 依赖本知识／与 B 相冲／B 细化本知识」）从组件内联抽到 lib；`KbOrganizePanel` 与 `KbEntryRelations` 同源 import。lib/ 有同型先例（kbFieldLabels.ts 等），命名合惯例。

### D4 点跳走页面回调，组件保持无页面依赖

`KbEntryRelations` 加可选 prop `onOpenKnowledge?(id)`：传入时对端名渲染为可点（点即切 `selected`，Esc 关抽屉回列表——页面既有行为，无需新栈）；不传时保持纯文本（向后兼容旧用法）。深链与返回栈不做（Non-Goals）。

### D5 「这条不对」保留（现成出口，非禁区）

反馈端点 `POST /relations/{id}/feedback` 已存在且组件已接——保留按钮不动；它不是建/删关系，与「手动关联另行立项」的禁区不冲突。段落提示语口径「来自知识整理」（存量 active 行未经逐条采纳）。

## Risks / Trade-offs

- **单知识 active 关系行数**：整理侧「active ≤ 条目数五倍」上限兜底；列表一次渲染不分页
- **对端 v2 归档（archived_at）可达但无归档标识**：详情照开；「已归档」标识属于归档视图范畴，挂账不在本 change
- **组件改造的测试迁移**：`kbEntryRelations.test.tsx` 现断言基于旧形态（英文键/箭头/「待确认」），随改造同步改写；coverage-contract 条目保留（组件不删除，只是行为升级）

## Migration Plan

无数据迁移。后端 `status` 入参默认不变（兼容）；前端同包同发（桌面单工件），前后端形状同步交付（tasks 1 与 2 同 change）。
