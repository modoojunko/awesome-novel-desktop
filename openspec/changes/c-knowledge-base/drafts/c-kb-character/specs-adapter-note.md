# 刀2c 架构裁定（2026-10-31，待 boss 拍板可推翻）

**数据源切换走「后端适配器」而非前端原生改造**：

- character-library router 各端点改为委托 kb_entries 存储（读 payload_to_card /
  写 card_to_payload＋update_entry 闸门复用），前端 6 组件零改动零风险
- character_library 主表停写（deprecated 落定）；CharacterLibraryBlob 保留作
  头像独立存储（6.5 口径），键改 kb 条目 id；迁移过的存量卡头像经 src_key 回联
- 映射单源＝kb/migrate_library.py 的 card_to_payload / payload_to_card（已补
  aliases/role/kind＋src_novel_name 列，parity 往返测试在案）
- 替代方案（前端直调 /api/kb）被否：六组件×100% 契约全重写＋三后端面
  （头像/收录/用到新书）仍须改造，风险与工作量双高，收益只有 URL 语义

**后续顺序**：① router 委托改造＋parity 测试 → ② 收录/同步/用到新书端点
跟随 → ③ 头像键迁移（entry id）→ ④ 前端 URL 语义收敛（P1 可缓）
