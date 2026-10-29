# c-charlib-deconstruct-exit — 拆书第三出口「收进角色库」

## Why

拆书产物里的角色维度（角色卡全字段＋关系边）现在只有两个去向：建书（写进某本书、关系与章卷留在任务资料）或导出文件（离库的静态产物）。跨书角色库（c-character-library）落地后，拆出来的角色应该能**直接收进库**——这是老万「拆书拆出来的角色归纳进库」的核心场景；也是 boss 拍板的第三出口。本 change 把角色库接到拆书完成页，作为与建书/存文件夹并列的第三个「选择去向」。

## What Changes

- **拆书完成页「选择去向」弹层第三张卡「收进角色库」**：点开收录清单——列出 characters 维度经**与建书同一套投影清洗**后的角色（证据剥离、人设兜底、角色定位白名单归一、跨批同名去重、路人不入清单），逐角色勾选（默认全选、已收录行灰态），可选「收进来时换个新名字和年龄」；确认后收进角色库，**这本书本身不受影响**（不建书、不动书内任何东西）。
- **候选端点**：`GET /tasks/{id}/library-candidates` 返回投影后的候选角色（身份键/名字/定位/人设/性别年龄/是否已收录）与 `can_import/reason`——前端清单、灰态与禁用原因只消费它，**禁止解析 md**。
- **投影单源**：`deconstruct/apply.py` 的 `_cards`（分析稿→操作稿投影）**连同 `card_to_book_payload`（扁平格→书内 payload/dossier 组装）**一并提为 deconstruct 域公共模块（`deconstruct/cards.py`），建书与收录共用；`apply.py` 保留 re-export，`scripts/deconstruct_product_check.py` 与既有测试的 import 同批改；SHALL NOT 出现第二套清洗口径。
- **幂等**：同任务同一源角色重复收录返回库中已有的卡（provenance＝src_kind=deconstruct＋src_ref=task_id＋src_character_id；身份键＝trim 后非空主名，空名兜底「未命名#序号」；插入 `ON CONFLICT DO NOTHING` 后回查，双击/并发不 500），不产生重复卡；`picks` 为空 400 且不置 exported_at。
- **已取结果语义**：`to-library` 成功后置 `exported_at`（建书出口靠 `book_id`、导出出口靠 `exported_at` 的既有双信号口径不动）；任一出口消费后任务徽标不再计入。
- **门禁**：收录入口上游＝拆书完成页（拆书=PRO 门已在），收录本身不新增档位门。
- 明确不做：关系边入角色库（关系不入库已拍板）、收录时选分类（入类后可编辑）、从角色库反查任务并回写。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`: 「结果目录与出口勾选」由出口二选一扩为三选一（新增「收进角色库」），明确该出口按 characters 维度产物消费、不受结果目录文件勾选集约束，以及三出口统一的「已取结果」语义。
- `character-library`: 新增「拆书收录」要求（角色清单=投影后的 characters 维度、逐角色勾选、可选换名换龄、幂等、不动书内）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：拆书完成详情「选择去向」弹层（加第三张卡）；新增「收进角色库」勾选清单弹窗。
- **对象状态**：第三卡与既有两张 `.ex-fmt` 卡同形（选中/悬停）；清单行勾选态；成功 toast。不新增提示语气、不触碰共享段。
- **原型先行**：已包含在角色库原型场景④（`docs/design-c/drafts/ai-novel-c端-角色库-原型.src.html`，真弹窗实抓＋第三卡运行时挂载）；实现期偏差登记 `ADJUSTMENTS.md`。
- **设计工件产出**：设计会话已产出（同上原型场景④＋设计说明 §3 收录流）。

## Impact

- `client/backend/deconstruct/apply.py`：`_cards` 提为域公共函数（`deconstruct/cards.py` 或 apply 模块导出），建书与收录共用；收录服务调用角色库域 `import_from_deconstruct(db, task, picks, rename)`。
- `client/backend/library/service.py`：新增 `import_from_deconstruct`（走投影、provenance 幂等、可选随机名龄）。
- `client/backend/deconstruct/router.py`：新增 `GET /tasks/{id}/library-candidates`（投影候选＋已收录集合＋can_import/reason）与 `POST /tasks/{id}/to-library`（仅 completed→否则 409；characters 产物缺失→422 可读错误；picks 空→400）。
- `client/backend/deconstruct/service.py`：任一出口成功后置 `exported_at`（消费统计与徽标口径扩三出口）。
- `client/frontend/src/components/tools/TaskDetailPage.tsx`：出口弹层加第三张 `.ex-fmt` 卡＋收录清单弹窗（复用 Modal）。
- 测试：投影单源一致性（收录与建书同输入同输出）、幂等、勾选与计数、换名换龄、三出口 exported_at 语义、六类状态回归（非 completed 不可收录）。
- 依赖：本 change 应用在 `c-character-library` 之后（依赖其库表与端点）。
