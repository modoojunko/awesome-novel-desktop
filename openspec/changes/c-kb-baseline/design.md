# c-kb-baseline · Design

设计核心＝**overlay 双层存储**（boss 定案）：官方基线＝只读 lower 层（不可变、整层替换式
更新），用户知识＝可写 upper 层；一切「修改/删除基线」都是 upper 层的写时复制（CoW），
基线原件永不改变。

## D1 双层模型

- **lower 只读层**：`kb_baseline_entries`（src_key 主键＋pack_version＋条目内容 JSON）。
  基线包同步＝**整层事务替换**（删旧插新，单事务）；客户端任何路径 SHALL NOT 更新单条。
- **upper 可写层**：
  - 用户自有条目（kb_entries 现状，零改动）
  - `kb_baseline_overlays`（user_id＋src_key＋action∈{hide,edit}＋content＋updated_at）：
    hide＝whiteout（隐藏）；edit＝写时复制的私有副本（merged view 以副本遮蔽原件）
- **merged view**（选择器与知识库页统一查询口径）：
  基线（排除 hidden，edit 命中套用户副本）∪ 用户自有条目；来源标签「官方精选」随层走。

## D2 升级语义（整层替换）

- 同步＝拉 latest → manifest 哈希校验 → 事务内：清空 kb_baseline_entries → 按包全量插入
  → 记 pack_version（app_meta）。overlays 表 SHALL NOT 触碰。
- 版本相同 → O(1) 静默返回；失败 → 状态行可重试，旧层继续服务（同步是替换不是增删，
  无半套状态）。
- 官方修订了被用户 edit 的条目 → 用户副本继续生效；知识库页该条目提示「官方有新版」
  （不自动覆盖，用户主动「恢复官方版」＝删 edit 记录）。

## D3 merged 查询口径

- 写法块选择器候选：`基线（src_key NOT IN hidden，instruction 取 COALESCE(overlay.content, 原文)）∪ 用户条目`
  ——两段查询 UNION 后进既有打分/配额链（c-kb-write-block 结构零改动，只是候选域换源）。
- 知识库页：同口径分页；来源筛选「官方精选/我的」；基线条目操作面＝隐藏/恢复默认/
  （有副本时）恢复官方版，SHALL NOT 出现编辑/删除。

## D4 反馈与推演

- prefs（有用/没用）挂 overlay（对官方条目的反馈＝用户层注解；恢复默认不删反馈）。
- 反馈聚合（没用率）随遥测/备份上抛，作为**我们修订基线包**的数据依据（内容维护闭环）；
  书级副本（独立方向）从 merged view 复制，书内演化与本层互不影响。

## D5 明确不做

merge 判定（快照比对/rev 推断）；基线条目加密/档位门；统一 resources.json 收敛（阶段2
独立变更）；AI 整理写入本层（#998 的整理对基线跳过，见 knowledge-base delta）。
