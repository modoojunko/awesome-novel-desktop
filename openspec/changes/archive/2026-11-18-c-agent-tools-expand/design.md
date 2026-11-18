# c-agent-tools-expand 设计

## 1. 结构动作三件（写类）

**能力核**：复用既有 service——确认/撤回走 chapters 路由同款 service 函数（caps/chapter.py 增 confirm_chapter/unconfirm_chapter/archive_chapter/unarchive_chapter 薄包装）；建卷/建章走 volumes/service.create_volume＋chapters 建章（章号 MAX+1 同源）。工具层（tools.py）Depends 占位按位传（批4 同款）。

**工具清单**（写类，kind="write"，走授权梯度）：
- confirm_chapter(chapter_ref) / unconfirm_chapter(chapter_ref)
- archive_chapter(chapter_ref) / unarchive_chapter(chapter_ref)
- add_volume(title) / add_chapter(volume_ref, title)

**授权卡预览**：write_gate._preview 补映射（confirm→「确认章纲：第 N 章」、archive→「归档：第 N 章」、add→「新建卷/章：标题」），作家批前看得见。

## 2. 世界观三件（读/产卡类，不写回）

**能力核**：settings ai_router 的 world draft/check/lore-suggest 同一后端函数——caps/world.py 薄包装（Depends 占位同款）。工具：draft_worldbuilding（产卡）/ check_worldbuilding（report）/ lore_suggest（候选列表）。产物过目采纳，不自动写回设定。

## 3. 域挂账

- 结构动作：全域共享（书级操作，任意页签可命中）
- 世界观三件：设定域（set: 前缀）
- 启动校验自动覆盖（registry ⊆ 域∪共享）

## 4. 非目标

- 正文写流收编（终态链路）、版本回退（硬地板候选）、key 管理
