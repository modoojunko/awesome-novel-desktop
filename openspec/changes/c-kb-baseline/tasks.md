# c-kb-baseline · Tasks

## 批A 只读层与同步（后端）

- [ ] A1 `kb_baseline_entries` 表（src_key 主键＋pack_version＋内容 JSON）＋`kb_baseline_overlays` 表（user_id＋src_key＋action＋content）
- [ ] A2 `kb/baseline.py` 同步：latest 指针→manifest 哈希校验→整层事务替换→记 pack_version；版本相同 O(1) 返回；失败静默可重试
- [ ] A3 启动补偿挂接（照 prompt-pack sync 先例）；pack_version 记 app_meta
- [ ] A4 merged 查询口径：基线（排除 hidden、套用 edit 副本）∪ 用户条目——选择器候选域换源（c-kb-write_block 链零改动）
- [ ] A5 单测：整层替换/升级保 overlays/同版本 O(1)/失败旧层继续服务/merged 口径（隐藏过滤＋副本遮蔽）

## 批B 用户层操作面（后端＋前端）

- [ ] B1 覆盖/隐藏/恢复端点（写时复制：edit 物化副本；恢复＝删 overlay 记录）
- [ ] B2 知识库页：基线条目只读操作面（隐藏/恢复默认/恢复官方版）＋来源筛选「官方精选」＋「官方有新版」提示
- [ ] B3 AI 整理跳过基线层（候选过滤＋单测）
- [ ] B4 prefs 挂 overlay（恢复默认不删反馈）
- [ ] B5 前端入约＋组件测试（只读操作面断言：无编辑无删除）

## 批C 内容与发布（内容仓 awesome-novel-knowledge）

- [ ] C1 打样扩量：玄幻/都市补齐＋新增 1-3 题材（每类手法＋场景写法 10-15 条过 validate）
- [ ] C2 publish 真实上传实现＋KNOWLEDGE_CDN_BUCKET secrets（boss 侧配）
- [ ] C3 基线包 v1 发布＋真机同步走查（含升级整层替换＋用户副本保留两态）
