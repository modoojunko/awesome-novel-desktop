# 刀2c 架构裁定（2026-11-01 boss 已拍板：知识库是角色库/世界库/文风库等一切库的底座，各库只是知识的一部分）

**数据源切换走「后端适配器」而非前端原生改造**：

**拍板后进度**：镜像步骤已落——旧备份 character_library 段恢复后自动 migrate
进知识库（importer kb_mirrored 计数；幂等 src_key=卡 id）；**①存储切换已落
（2026-11-01，parity 全套原样跑绿）**，见下方「FK 实证修订」。

## FK 实证修订（①落地时发现，偏离原计划已按推荐方案执行）

原计划「新卡头像键=entry id 写 CharacterLibraryBlob」**不可行**：那张表
library_id 是真 FK（PRAGMA foreign_keys=ON，sqlite 实证 insert 即
FOREIGN KEY constraint failed），kb entry id 永远不在 character_library 里。
落地改为：

- 新字节住新表 **kb_entry_blobs**（entry_id/variant 复合主键，照 KbEntryTag
  先例不挂 FK；create_all 自动建，老库升级零动作）
- 迁移存量字节仍住 CharacterLibraryBlob，读经 src_key 回联（零迁移）；删卡双清
- 新卡头像字节进配置包往返（kb/entry-avatars/*.webp zip 条目＋yaml 元数据，
  parse_package 注入 data；兼容键不升 format_version）
- ③ 从「头像键迁移（entry id）」变为「旧字节一次性搬进 kb_entry_blobs ＋
  CharacterLibraryBlob 退役」（原方向不变，落点变干净）

- character-library router 各端点已委托 kb_entries 存储（读 payload_to_card ／
  写 card_to_payload＋create/update/delete_entry 闸门复用），前端 6 组件零改动；
  API 卡形状逐键不变（src/avatar 嵌套结构在 library/service._card_view 包回）
- character_library 主表停写（deprecated 落定）；备份恢复镜像除外（既有）
- 软删卡重新收录＝同键复活（unique 索引挡重插；置回 active 后走 update_entry
  整卡覆盖，tags/rev/题材同步复用）
- update_entry 扩可选参 genre（同步 concept_id）/src_novel_name——kb PATCH
  不传即不受影响
- 映射单源＝kb/migrate_library.py 的 card_to_payload / payload_to_card（已补
  aliases/role/kind＋src_novel_name 列，parity 往返测试在案）
- 替代方案（前端直调 /api/kb）被否：六组件×100% 契约全重写＋三后端面
  （头像/收录/用到新书）仍须改造，风险与工作量双高，收益只有 URL 语义

**后续顺序**：① ~~router 委托改造＋parity 测试~~ 已落 → ② ~~消费面走查~~ 已落
（snapshot 角色无落点跳过／建卡预填新卡入池／主表停写 sweep 干净）→
③ ~~旧头像字节搬 kb_entry_blobs＋退役~~ 已落（kb/blob_migration.py boot 迁移：
幂等＋孤儿保留走 union 读＋搬后删旧行；同键多用户各自补齐）→
④ 前端 URL 语义收敛（P1 可缓）
