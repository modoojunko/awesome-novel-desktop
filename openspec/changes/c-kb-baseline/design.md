# c-kb-baseline · Design

设计权威＝整体方案 §7/§8（四来源/书级副本方向）。本文件记实现决策。

## D1 分发形状（与提示词包的三点不同）

不加密（基线在知识库页对作者可见，加密无意义）；无档位门（冷启动底座人人有）；消费＝
同步期幂等 merge 进 kb_entries（数据行），非运行时模板读取。

## D2 同步管线（挂既有启动补偿点）

- 拉 `{CDN}/download/knowledge/baseline/latest.json`（薄指针 version+manifest_sha256）
- 本地记录（app_meta key="kb_baseline_version"）相同即静默返回（O(1) 探测）
- 拉 v< N >/manifest.json 校验指针哈希 → 逐文件 sha256 校验 → merge → 记版本
- 失败：知识库页状态行可重试；不弹窗；不阻断写法块（未就绪＝不出现，同级降级）

## D3 merge 规则（用户资产优先）

逐条按 src_key：
- 库内缺失 → 插入（src_kind="baseline"，来源标签官方精选）
- 库内已有且 src_kind=baseline：
  - 本地 tombstone（用户删除）→ 保持删除，仅刷新内容快照
  - 用户改过（rev>1 或 rev 与包版本记录不一致）→ 保持用户版
  - 未触碰 → 用包版本刷新（修订下发通道）
- 逻辑删除条目（status=archived 且非用户删）→ 按包恢复

「用户触碰」判定：merge 时比对条目内容与上一已同步包版本的 text_snapshot——不依赖
运行时标记。首版无历史记录时，除 key 缺失外一律按「已同步过」跳过（保守首装口径）。

## D4 tombstone 下架

tombstones.removed 里的 src_key：用户未触碰 → 物理移除；触碰过 → status=archived（隐藏，
可手动清）。下架不回写内容仓（单向下架）。

## D5 AI 整理边界（与 #998 交互）

c-kb-organize 的整理/合并/纠偏/关系提案对 src_kind="baseline" 条目跳过——官方内容修订
只走基线包版本。跳过实现＝整理候选查询统一过滤 src_kind<>'baseline'。

## D6 明确不做

不做统一 resources.json 收敛（阶段2 独立变更：拆提示词包弹窗）；不做档位门；不做书级
副本复制（书级副本为独立方向变更，本变更的账号库基线条目是其复制源）；不做条目加密。
