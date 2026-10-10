# c-char-list-order-search — 任务

## 1. 原型先行（C端 硬性流程）

- [ ] 1.1 `docs/design-c/prototypes/character-settings.html` 补：行拖拽把手与三态（源行半透明/拖影/落位线）、「按角色类型分组」开关（关=扁平＋行内类型标签）、搜索命中自动展开与空态一键清空；`ADJUSTMENTS.md` 登记偏差
- [ ] 1.2 `npm run design:lint` + `design:check` 过

## 2. 后端（同一 change 原子落地，读路径与钉序不分批）

- [ ] 2.1 `models/character.py` 加 `sort_rank` 可空整型列；迁移缺列回归测试（`build_plan` 无 blocker、行不丢、目标 rank=NULL）
- [ ] 2.2 `characters_router.py` 加 `PUT /order`（静态段前置）；`character_service.set_characters_order`：ids ⊆ 本书校验（未知/跨书/重复/空 → 400 `invalid_ids` 点名）、单事务 UPDATE、不 bump rev、不作废门禁
- [ ] 2.3 `list_characters` 读路径改 `ORDER BY sort_rank IS NULL, sort_rank, seq`；`card_to_dict` 加 `sort_rank`
- [ ] 2.4 抽 `seq_sort_key()` 并替换 5 个提示词消费点排序：`chapter_writer.py`／`ai_router.py`／`ai_draft.py`／`ai_plan.py`／`ai_cast.py`
- [ ] 2.5 备份往返：`character_to_export` 加 sort_rank；v2 导入 `raw.get`（非 int→NULL）；撤销快照不带 sort_rank
- [ ] 2.6 pytest：order 持久化/幂等/子集保原值/未知与跨书与重复与空 400/不 bump rev/不作废门禁/新卡与撤销恢复落末尾/路由不遮蔽（照 `/graph` 先例）；writer 等 5 点「order 后仍 seq 序」各一条；备份 `sort_rank_survives_roundtrip`＋老包缺键 NULL；迁移缺列回归

## 3. 前端

- [ ] 3.1 `lib/characterOrder.ts` 纯函数（全局数组唯一真源、组内拖=全局 splice、键盘移动池、派生分组序）
- [ ] 3.2 `useCharacterReorder`：独立串行队列只留最新数组、orderRef 本地真源解 reloadList 回弹（新 id 追加/消失 id 滤除）、失败回退＋toast
- [ ] 3.3 列表面板：把手（aria-hidden、`touch-action:none`、rect 缓存）、6px 阈值短按选中、ghost portal+rAF、搜索中置灰、Alt+↑/↓、分组开关（`chars.grouped.${projectId}`）
- [ ] 3.4 搜索修复：命中分组自动展开（快照还原）、搜索中禁组头折叠、零结果空态＋一键清空
- [ ] 3.5 `CharacterManager` 拆分（ListPanel/BatchAddModal 接口对齐 c-char-batch-import）；登记 coverage-contract；薄壳 v8 ignore
- [ ] 3.6 vitest：characterOrder（move/组内约束/键盘池/派生序/orderRef 合并/失败回退）；搜索三态；开关持久化；存量 CharacterManager 测试零改跑绿

## 4. e2e（独立栈）

- [ ] 4.1 拖拽换序→断言 PUT 载荷全量→刷新后顺序保持
- [ ] 4.2 分组开关两态拖拽（关=扁平跨组、开=组内不跨组）
- [ ] 4.3 搜索别名命中自动展开（折叠的路人组）＋空态清空＋搜索中不可拖
- [ ] 4.4 Alt+↑/↓ 移动；存量角色 e2e 原样跑绿

## 5. 收尾

- [ ] 5.1 `tsc --noEmit`、`design:check`、pytest、vitest 全绿
- [ ] 5.2 真机冒烟：旧书（无 rank）打开＝原创建序；拖拽后重启保序；写一章确认角色锚顺序未变
