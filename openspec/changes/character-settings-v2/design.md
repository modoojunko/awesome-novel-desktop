# Design — character-settings-v2

## Context

现状与约束（详见 `proposal.md` 与二轮评审结论）：

- 现役角色是 `project_settings` 的 KV 行，键为派生字符串 `character:{名字}.yaml`（`client/backend/filesystem/paths.py:19-41`），卡内 `name` 可独立编辑 → **键名与卡名可分离**；章纲按显示名引用（`client/backend/chapters/store.py:130,281`），有 4 处按显示名读卡（`write/chapter_writer.py:609-626`、`write/auxiliary.py:84-104`、`archive/service.py:168-193`、`story/engine.py:62-86`），另有 `readiness.py:82-85` 与 `chapters/ai_draft.py:246` 两处。
- 写章提示词的「角色初始状态」**今天恒空**：段级 `characters` 没有生产者、写读键名不一致（`change` vs `state`）、兜底键 `personality` 不存在。
- 启动期 schema 指纹检查（`client/backend/legacy_archive.py:19-33` + `main.py:47-67`）：**任何新表 / 改列都会让存量库三件套留档、以空库启动**；兼容责任在资产包 `format_version`（`openspec/specs/backup-restore`）。
- 导出只遍历 `PATH_TO_KEY` + `THREADS_PATH` + `CHARACTER_DIR`（`client/backend/backup/export.py:95-118`）；导入的设定分支走 `route_relative_path`（`backup/importer.py:181-191`）。
- `backup-restore` 承诺的八层 roundtrip 断言在仓库里**缺失**（该 change 的 4.3 未勾选），必须先补。

## Goals / Non-Goals

**Goals**：角色与关系的真表化；章节出场引用按 id；删 / 合并 / 撤销可依赖；AI 四能力有可实施的提示词与后处理契约；导入导出跨版本可用；写章「角色初始状态」换供给源。

**Non-Goals**：不动世界页 / 主线页的 AI 信封与响应形状；不动 `chapter-data`；本批不 id 化 `volume_character_voices` 与 `chapter_knowledge_states`（登记债务）；不做体检结果缓存；不做服务端请求幂等键；不改动画布 / 工作台其它视图。

## Decisions

### D1 角色进真表，认知与档案用 JSON 列

`characters`（id / novel_id / seq / name / aliases / role / persona / dossier / cog / legacy / rev / created_at / updated_at），`character_relations`（id / novel_id / owner_id / other_id / rel_type / stance / note / ch_ref / rev / 时间戳）。

- **id 用 uuid（String(36)）**：与仓库既有业务表一致（`models/project.py:13-15` 等），且导入时允许"原 id 直接落库"，省掉全局 id 映射表。显示编号 `#C-0001` 由**每书单调的 `seq`** 派生（不回收）。
- **`dossier` / `cog` 用 JSON 文本列**（理由）：schema 指纹按"表 + 列 + 类型"计算 ⇒ 拆成 38 列意味着**以后每加一格都再触发一次全量留档**；JSON 列把加格降为纯代码变更。**代价**：单格写入必须服务端按键路径读-改-写（不接受整卡回传），且无法用 SQL 直接按格检索（本批判据都在 Python 侧算，43 行量级无压力）。
- **约束**：`UNIQUE(novel_id, seq)`；`UNIQUE(novel_id, name)`（同名两卡会让 AI 指代无从选择）；`UNIQUE(owner_id, other_id)`（"同一对端一条"由 DB 保证）；**部分唯一索引** `UNIQUE(novel_id) WHERE role='主角'`（每书一位主角）。
- **主角换人**：服务层在**同一事务**里"先降原主角、再升新主角"，且**两条 UPDATE 之间必须显式 `flush()`**、升级语句带 `WHERE novel_id=? AND role='主角'` 的条件写——已实测：靠 ORM 赋值顺序会在后续某次 autoflush 时抛 `UNIQUE constraint failed: characters.novel_id`，而报错栈里看不到"设主角"这个动作，排查成本极高。导入时若包内 ≥2 主角，按 `seq` 最小者保留、其余降级并告警。
- **`seq` 取号用单调计数器，不用 `MAX+1`**：`MAX+1` 在"删掉最大号的那张卡后再建卡"时会复用编号，直接违反"编号不回收"；计数器可给 `novels` 加一列（本批 schema 反正要变），并在同事务内读改写、撞唯一键重试一次。
- **单格写入必须是条件 UPDATE（CAS）**：SQLite 没有 `SELECT … FOR UPDATE`，`读 → 比较 rev → ORM 赋值` 的写法在并发下必然丢字。落地为 `UPDATE characters SET <col>=:new, rev=rev+1 WHERE id=:id AND rev=:rev`，`rowcount==0` 才回 409。merge / delete / 设主角 / 关系 upsert 也都要 bump `rev`，否则合并后客户端拿旧 rev 仍能 PATCH 成功。
- **`character_gate` 与 `character_ops` 的列清单**（tasks 2.1 要按它写断言）：`character_gate{novel_id 唯一, protagonist_id(FK SET NULL), fingerprint, confirmed_at, rev}`；`character_ops{novel_id, kind(delete|merge|rel_delete), before(JSON 前像), undo_token, expires_at, undone_at}`。
- **JSON 列另外三条代价**（除"必须服务端读-改-写""无法 SQL 按格检索"之外）：① 撤销/合并前像是整卡 JSON（数十格），TTL 一长就无界增长；② `aliases` 是 JSON，**业务唯一性无法下沉到 DB**——别名与别人本名撞车是合法状态，"别名冲突"只能告警不能报错；③ `legacy` 列没有列级读白名单，响应组装必须显式白名单，**禁止 `model_dump()` 直出**。
- 备选：KV 键改成稳定 id（改动小但仍是 JSON 大块、无法 SQL 聚合，归档 change 还得再改一次）——否；DB 唯一索引保主角（`role` 在 JSON 里没有列可建索引，且老数据可能 0/2 个主角）——否，改用部分唯一索引 + 服务层事务。

### D2 章节出场引用改存 id，API 契约保持"名字数组"

> **修正（后端审核）**：解析点**不能**放在 `_replace_children`（`chapters/store.py:257` 无 session、无 async、拿不到 novel_id，按原稿字面根本写不出来）。落到 **`apply_chapter_data(session, row, data)`（`:450`，有 session 与 `row.project_id`）**；导入路径完全绕开 `save_chapter`，要在 `chapters` 循环之前**单独做一步显式 id 绑定**（`characters` 必须先于 `chapters` 落库），否则导入的章全 `character_id=NULL` 而测试仍全绿。

- `chapter_characters` 增加 `character_id`（可空，`ON DELETE SET NULL`），**保留 `character_name` 作原文快照**（未命中/卡已删的活路）。刻意不重命名该列：语义上它就是快照，重命名只增 diff。
- **解析只放在存储层的两个点**：写入时 `名字 → id`（`chapters/store.py:281-285`），读取时 `id → 现名`（`chapters/store.py:130`）。因此 `outline.characters: string[]` 的 JSON 契约不变 ⇒ 写章、辅助、归档、版本快照、前端表单**全部零改动**，而"改名后章纲自动跟随"自然成立。
- 未命中名字：保存成功 + 响应 `warnings[]` + 落快照；**不自动建卡**（会污染列表）。
- **写入口共 10 条**（`chapters/store.py` ×2、`chapters/router.py` ×3、`chapters/ai_draft.py`、`chapters/versions.py`、`write/router.py`+`write/auxiliary.py`+`prompt/router.py`、`novels/router.py`、`backup/importer.py`）——关键是"读全章 → 回写"的 5 条路径不得把 id 洗回名字，测试要逐条断言。
- **出场角色的输入控件必须同批换**（现在是自由文本 textarea），否则作者手打名字会持续产生未命中。

### D3 老包映射：9 个内容格 + 2 个身份格，5 个无归宿字段只留原文

> 身份格映射：`name→characters.name`；`role` 需**枚举表** `protagonist→主角 / antagonist→反派 / supporting→配角`（老库只有三值，新表四值，"路人"无老值）。

`appearance→dossier.look`、`background→dossier.background`、`speech→dossier.speech`、`world_view→cog.w3`、`self_image→cog.s2`、`values→cog.v2`、`abilities→cog.p2`、`skills→cog.p6`、`environment→cog.e1`；`possessions` / `experiences` / `relationships` / `state_history` / `personality` → `characters.legacy`（原文留存、不上界面、不进 AI）。映射函数放独立纯函数模块（照 `settings/world_model.py` 的 `_from_v1` 分层），可被逐行单测。

导入后门禁必然报缺口（老包没有 `persona` / `剧情定位` / `p3` / `p4`）——这是诚实行为，导入回执要说明。

### D4 导入改道（顺序是硬约束）

`backup/importer.py` 的设定分支今天会把角色写进 `character:` 前缀的 KV ⇒ **真表上线后就是"导入成功、角色全空"**。落地顺序必须是：

1. 先迁**读卡消费方**（4 + 2 处）到新表；
2. 再给 `_import_single_book` 加角色段分支（v1 走映射、v2 直读）；
3. **最后**把 `route_relative_path` 的 `character:` 前缀改为显式报错（兜底，不是第一步——否则上述消费方会 500）。

同时补：**单书包分支也要读 `format_version`**（现在只有资产包读，版本上限形同不存在）；`FORMAT_VERSION` 三处常量收敛到一处并升到 2；导出角色段改走新布局（不再写 `settings/character-setting/`）。

### D5 撤销落表

合并的"按对端去重"会**删掉关系行**，被删行的前像不在任何表的当前状态里 ⇒ 前端快照只能做同屏回滚，跨请求的一步撤销必须服务端留底。新增 `character_ops`（单行前像 + `expires_at`），删除 / 合并 / 删关系各写一行，撤销按前像在同一事务里重放（合并的逆 = 重建源卡 + 关系改回 + 恢复被去重删除的行 + 恢复主角位），`undone_at` 标记单次可用。**窗口用具体秒数**（`expires_at = now + 600`；"继续编辑"由前端主动作废），三态响应钉死：二次撤销 409 `already_undone` / 过期 409 `undo_expired` / 无 token 404；**过期不删行**（保留审计，且让 409 与 404 可区分）。设计稿文案按"会话内 + 明确窗口"写。

### D6 AI 四能力的契约

- 端点：`POST /api/novels/{id}/settings/ai/characters/{character_id}/draft`（`target ∈ persona|dossier|cog`）与 `.../check`；**`act`（insert / replace）由服务端按 target 决定**，不接受客户端传（它是写入判据，能传就能绕过）。
- **只补空格的基准＝服务端此刻的空值**（不信客户端提交的清单；简介页那套"前端传 missing"是引导性输入，性质不同）。响应回带 `targets`，前端只渲染它。
- 脏返回处置：已填格 → 丢弃并 `skipped: already_filled`；未知键（含 `gender`/`age`/`personality`）→ 丢弃且不进 `skipped` 之外的任何地方；超长 → clamp；非 JSON → 502 可重试。**逐格 best-effort，不做整批 400**；全部目标被丢弃才 502。
- **性别 / 年龄三层挡**：不进 `targets`、不进白名单、采纳时再挡一次；SHALL NOT 做成 400（是"永不代填"不是"错误输入"）。
- 人设是唯一覆盖型（`act=replace`）：豁免非空检查，但写入前存旧值支持一步撤销；空值不许覆盖。
- 零空格时免调用（先算 targets，空则直接回"已齐"）。
- 提示词模板 4 个新文件（`settings_characters_persona|dossier|cog|check.prompt`），同批删除死模板 `settings_characters.prompt`、`_STYPE_PROMPTS['characters']`、`FIELD_GENERATABLE` 里的 `characters`（顺序敏感，漏删会 KeyError）、孤儿 `CharacterCreateModal.tsx`。格名与项名由领域常量渲染进模板，模板不手抄。
- **领域单源** `client/backend/settings/character_model.py`：六层格表、档案格表（含 `author_only` 标记 gender/age）、补全键清单、写章状态键清单、体检项表（力量向 / 现实向两套）、体检四态常量。前端留渲染副本 + parity 测试。

### D7 体检四态与不拦确认

`ok / warn / conflict / miss`：`miss` = 缺输入判不了，`conflict` = 判为矛盾（**新增元组，绝不扩世界页白名单**——`ai_router.py:741` 用它接受 world 出参，扩了会把"矛盾"在世界页显示成"缺失"）。项名 / 顺序 / `goto` 全部服务端常量出（模型只填 status 与依据句，长度 clamp）；输入缺失走降级（`degraded` + 该行 `miss` + 提示去补），四项设定全空 / 卡片全空 / 路人卡 → 免调用或短路；**体检无副作用**，readiness 与门禁不消费它；不承诺结论稳定、不做指纹缓存。生成温度：人设 0.6 / 档案与认知 0.4 / 体检 0.3（spec 冻结）。

### D8 写章「角色初始状态」换供给源

不再修那条恒空的 `state_history` 链；改由**六层主格（w1/s1/v1/p2/b1/e3）+ `dossier.speech`** 供给：格序固定、每格 ≤40 字、每人 ≤120 字、块 ≤5 人（主角优先装箱，放不下整人不注入并声明）；全空者不渲染成「- 名字：」；读不到卡渲染显式标注。同批改 `prompts/prompt_crafting.prompt` 里"起点→转折→落点"的旧口径，并把「角色初始状态」纳入校验的条件锚词。

### D9 关系单向

存储 `owner_id → other_id`；"对方卡自动镜像"与"同一对端一条"的旧口径作废；合并时"自己写的并入目标、别人写给他的改指目标"，自环直接消解。写章提示词只注入"在场者之间、以当前视角"的关系（≤3 条 / 人，总预算受限）；体检**不用对端卡的事实校验本卡的关系**（否则故意的认知差会被判矛盾）。

## Risks / Trade-offs

- [老库留档重建不可逆，用户若从未导出则角色不可自助找回] → 升级引导前置"先导出备份"；全链演练用旧版造的真库；保留留档库的人工恢复路径（需补只读消费手段）。
- [导入静默丢角色] → D4 的改道顺序 + `character:%` 计数断言 + `route_relative_path` 显式报错。
- [id 化期间引用被洗回名字] → 只收 id 的写边界 + 5 条"读全章→回写"路径逐条测试 + 未命中一律快照 + 告警。
- [读-改-写并发覆盖作者的字] → 单格 PATCH + `rev` 409；归档不再回写角色卡（改由章侧数据承担）；合并 / 删除走单事务。
- [查询放大（43 人 = 44 请求）] → 列表聚合端点一次给全，"首次出场"由一次 `GROUP BY` 求 min（不逐角色查）。
- [体检结论漂移被当成 bug] → 只承诺结构稳定（项名/顺序/取值集合/长度上限），并把它当度量对象（同内容两次的取值翻转率）。
- [`AIClient` 无 timeout + 502 路径记零账] → 单开 change，但顺序上必须在角色四行之前。

## Migration Plan

1. **先合**（不动 schema、不动角色行为）：原型归位 `docs/design-c/prototypes/` + `ADJUSTMENTS.md` 登记 + `design-vocab.mjs` 白名单与两处 lint 违规修正；补建 roundtrip 八层断言底座；零行为重构（抽 `apply_chapter_data`、删死代码与死提示词、`_check_characters` 加 `novel_id` 参数）。
2. **一次发布列车**（所有 schema 变更必须同批，分两次 = 留档两次）：新表 + 角色/关系/删除合并撤销端点 + `chapter_characters` id 化 + 导入导出升版 + 前端面板重写 + AI 两能力 + 门禁两档与第三态。
3. **发布门禁**：全链演练（用旧版造真库 → 导出双包 → 装新版 → 断言留档 → 导入 → 九层 roundtrip 全绿 → 再断言 v1 包在新版下角色段无损）+ 各端 design 门禁 + 双端 tsc + 相关 e2e。
4. **回滚**：不支持降级（旧版读不了 v2 包、且会触发留档）；唯一回退路径是"重装新版 + 从导出包恢复"，因此升级引导必须前置备份。

## 附：id 稳定性矩阵（1.2 往返断言的依据）

- **不稳定（只比语义）**：`Novel.id/name/slug/root_path/created_at`、`Chapter.id`、`Volume.id`、`version`（时间戳）——导入会改名、改 slug、新生成章 id。
- **必须字节级稳定**：`ChapterVersion.snapshot`、`ChapterPrompt.content`、`Archive.content`。
- **本 change 新增的稳定项**：`characters.id`、`character_relations.id`（与 `Novel.id` 不稳定正好相反，同一 fixture 要区别对待，否则实现者会写"整体深比"而永远写不出这条断言）。

## 附：死提示词判定方法（tasks 1.6 用）

只按 `load_prompt("x")` 字面量 grep 会同时产生假阴性与假阳性——本仓构造 prompt 名共有 **4 条机制**，必须全查：① 字面量 `load_prompt/load`；② 三张映射表 `settings/ai_router.py:40 _INTRO_PROMPTS`、`:45 _GENRE_PROMPTS`、`:51 _STYPE_PROMPTS`；③ `novels/ai_backfill.py:54` 的 f-string 拼装（取值只有 `synopsis_world/style/characters/outlines`）；④ `novels/ai_backfill.py:16-23` 的自定义 loader。

按此判定：**真死 5 个**（`settings_anti_ai`、`backfill_step1_system`、`backfill_step2_system`、`archive_summary`、`perspective`）；**看着像死但活着 4 个**（`backfill_characters`、`backfill_outlines`、`backfill_style`、`backfill_synopsis_world`——走 f-string 机制，**不要删**）。

## Open Questions

- 生成温度的具体数字（已给建议值，spec 里冻结前可微调）。
- 人设 5 稿是否落库（当前按"不落库、会话内"实现）。
- `volume_character_voices` 与本批的关系（当前按"登记债务、不改"实现）。
