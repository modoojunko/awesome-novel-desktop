# c-char-list-order-search — 技术方案

## 关键决策（实现评审已定，含默认值）

### 后端

1. **迁移通道**：client 端不用 alembic——加列即改 schema 指纹（按表+列+类型计算），存量用户升级首启 `boot_lifecycle` 判 mismatch → 旧库改名留档 → 新空库 → 走「候选带回」整库迁移。`migration/engine.py` **零改动**：`build_plan` 列交集天然跳过源库缺失列，`sort_rank` 可空无 blocker。工程动作＝迁移缺列回归测试一条＋发车前核对同版本其他 schema 变更**合流一次迁完**。
2. **order 端点契约**：`PUT /characters/order` body `{"ids":[...]}`。校验＝ids ⊆ 本书卡集合（一次查询全覆盖）；未知/跨书 id → 400 `invalid_ids`（detail 点名，至多列 10 个）；重复 id → 400；空数组 → 400；防御性上限 2000。写入＝单事务逐 id `UPDATE ... SET sort_rank=:下标 WHERE id=:id AND novel_id=:pid`；rank 数值域＝数组下标（order 恒整组重写，稀疏 rank 无收益）；**子集提交＝未提交卡 rank 保持原值**（不能置 NULL，否则分组视图拖一组把其他组冲到末尾）；平局按 seq 破。**不 bump rev、不动 CharacterGate、不写 CharacterOp**；`Column.onupdate` 会连带更新 updated_at——无消费方依赖，接受并在 change 记录。路由静态段 `/order` 声明在 `/{character_id}` 族之前（`/graph` 先例）。
3. **读路径**：`order_by(Character.sort_rank.is_(None), Character.sort_rank, Character.seq)`；`card_to_dict` 增加 `"sort_rank"`（前端回弹竞态与拼数组依赖——spec 必补项）。
4. **提示词钉序**：list 消费方 7 处中 5 处直进提示词/AI（`chapter_writer.py` 角色锚、`ai_router.py` 主线起草、`ai_draft.py` 章纲一行卡、`ai_plan.py` 拆卷素材、`ai_cast.py` 人物盘点）。抽共用 `seq_sort_key()`（seq 升序、主角置顶的既有稳定排序保留并加 seq tiebreak）五处统一替换——**与读路径改序同一 change 原子落地**，每点钉测试。
5. **备份往返**：`character_to_export` 白名单加 `"sort_rank"`；v2 导入 `raw.get("sort_rank")` 非 int→None；v1 分支恒 NULL。**撤销快照不带 sort_rank**（`_snapshot_card`/`_overwrite_from_snapshot` 不加），delete-undo 新建行自然 NULL 落末尾＝拍板口径；测试钉死防将来"顺手补全"。

### 前端

6. **顺序唯一真源**＝全局 id 数组（`lib/characterOrder.ts` 纯函数）：分组视图＝按 ROLES 过滤的派生序；组内拖＝全局数组 splice 到目标同组成员邻近位（其他组相对序不变）；PUT 恒发全量数组。键盘 Alt+↑/↓：分组态限同类型相邻位、扁平态全局相邻。
7. **回弹治理**：`useCharacterReorder` 持 `orderRef` 永续本地全序（成功也不清空，自愈式合并：新 id 追加末尾、消失 id 滤除）；每次 reloadList 到货先按 orderRef 重排再 setList。order 提交走**独立串行队列**（只留最新数组；与单格保存队列分开——那个带 rev 语义）。失败＝orderRef 回退服务端顺序＋toast「顺序没保存上，请重试」。
8. **指针交互**：把手起拖（`aria-hidden`，不并入按钮 accessible name——防 e2e `getByRole` 失配）、6px 阈值、短按仍是选中（pointerup 后 click 需 dragRef 早退）；视觉态（dragId/overId/before/ghost）全进 React state（原型直改 DOM 的手法不照抄）；ghost 走 portal＋rAF 节流；`touch-action: none` 只挂把手。dragstart 时缓存各行 rect（避免 pointermove 每帧 O(n) 强制布局）；视口边缘自动滚动＋Alt 键兜底。
9. **分组开关**：`chars.grouped.${projectId}`（对齐 `foreshadow.snap.${projectId}` 惯例），默认 "1"；切换开关**不提交 order**（两视图共用同一全局 rank）。折叠状态维持 session 态。
10. **搜索修复**：展开＝派生态 `q ? true : groupsOpen[role]`（进搜索快照 groupsOpen、清空还原，不改本体）；搜索中禁组头折叠点击；空态＋一键清空。过滤逻辑（名字+别名）不动。
11. **覆盖率**：`characterOrder.ts` 纯函数 100%（登记 coverage-contract）；指针绑定薄壳 v8 ignore＋理由（jsdom getBoundingClientRect 全 0 不可测，仓库 17 处先例）。

## 原型迁移口径

交互基准＝drafts 原型（拖拽三态/搜索自动展开已无头验证）。实施时移植进 canonical `docs/design-c/prototypes/character-settings.html`＋`ADJUSTMENTS.md` 登记，再动 `src/`。

## E2E 环境注意

遵守会话环境隔离规则（AGENTS.md）：独立栈；order 端点未就绪期 e2e 可 `page.route` 桩过渡，落地后换真栈重钉。
