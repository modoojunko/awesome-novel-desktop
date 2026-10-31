# Tasks · 写作知识库批1（c-knowledge-base · Phase 1 ①）

## 后端

- [ ] 1.1 `models/kb.py`：11 张模型注册；全列 nullable/server_default；entry_tags 冗余 user_id
- [ ] 1.2 `kb/concepts.py`：六概念注册表＋场面/情绪词表＋别名＋关系元数据；前后端一致性测试
- [ ] 1.3 `kb/payloads.py`：六概念 Pydantic（extra=forbid、槽位闸、when 白名单）
- [ ] 1.4 入库闸门：概念推断＝作家输入文本与 `kb/infer.py` 的 aliases 表做关键词匹配（不跑模型）；推断不出预选"手法"；长度/原文/幂等 partial index；**手录按概念动态字段＋概念推断**（POST /api/kb/entries，校验失败逐字段错误码）
- [ ] 1.5 标签物化（同事务重建）＋重建端点
- [ ] 1.6 题材归一 normalize_theme；空态契约；题材栏含「跨题材通用」
- [ ] 1.7 默认库自动生成（同事务＋partial unique index）；停用不删条目
- [ ] 1.8 API 契约：GET genres / GET entries（筛选+搜索+游标）/ GET entries/{id} / POST entries / GET concepts / POST tags/rebuild；分页「加载更多」
- [ ] 1.9 kb_prefs (user_id, entry_id) 账号级
- [ ] 1.10 import 断言：kb SHALL NOT import write/deconstruct

## 前端

- [ ] 1.11 知识库页：路由 /tools/kb 深链；ToolsMenu 入口；题材栏（只显有内容+全部+跨题材通用+更多折叠）；概念页签带白话说明；条目按题材×概念**分组标题行**组织（不做独立库卡）；条目列表＋抽屉（Esc＋焦点管理）
- [ ] 1.11b 窄窗：题材栏横滚/折叠＋无横向溢出断言
- [ ] 1.12 手录表单：必填=写什么+选题材；概念系统推断可改；适用条件可选后补；标题自动截取；校验错误逐字段 inline＋剩余字数；**全部文案用作家日常用语**
- [ ] 1.13 数据获取：lib/kbApi.ts＋queryKeys.kb；useInfiniteQuery；手录后失效 key 清单

## 测试

- [ ] 1.14 单测：闸门/槽位/默认库并发/标签重建/normalize_theme parity/import 断言
- [ ] 1.15 e2e：批1 范围断言（题材栏折叠/分组标题行/手录推断概念/Esc 抽屉/搜索/空态/加载更多）；原型 verify 脚本 ① 约 15 项直译
- [ ] 1.16 性能：10 万级列表＋搜索回归
- [ ] 1.17 design:check 收编：知识库屏入 strictSrcGlobs

## 角色库迁移（⑥ c-kb-character-migration）

- [ ] 6.1 扩 `kb/payloads.py` CharacterPayload 到角色库全量字段（dossier 8 格：gender/age/race/faction/look/speech/background/plot；cog 11 格：w1/w5/s1/s5/v1/p2/p6/p3/p4/b1/e3；persona/relation_slot/arc）
- [ ] 6.2 迁移脚本：读 `character_library` 全量 → 创建 kb_entry（concept="角色设定"，src_kind="character_library_migration"，src_ref="character_library"，src_key=原 id，幂等）
- [ ] 6.3 角色关系迁移：character_relations → kb_relations（rel_type="related_to"）
- [ ] 6.4 角色库 UI 数据源切换：列表页读 kb_entries（concept="角色设定"）、编辑器读写 payload、关系读 kb_relations
- [ ] 6.5 头像：kb_entry 加 avatar_url 字段引用独立存储；legacy 原文不迁移
- [ ] 6.6 `character_library` 表标 deprecated
- [ ] 6.7 单测：迁移前后字段映射 parity＋幂等（重复迁移不产生副本）

## 子变更草案已存

drafts/c-kb-write-block/（写法块选择器+注入+prose-writing delta）
drafts/c-kb-import/（拆书入库+deconstruct-book delta）
drafts/c-kb-snapshot/（快照启用+库卡亮相）
drafts/c-kb-character/（角色原型）
drafts/c-kb-organize/（AI 整理+全局图上线）
drafts/c-kb-backup/（备份+backup-restore delta）
