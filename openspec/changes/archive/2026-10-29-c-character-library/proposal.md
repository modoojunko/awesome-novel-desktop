# c-character-library — 跨书角色库（全局档案柜）

## Why

老万需求：角色设定要跨书共用——拆书拆出的角色和作家自设角色归纳进同一个库，分类组织，性格与说话方式随卡，开新书时换个名字和年龄就能接着用，不用重新设计角色。现状 `characters` 表强绑 `novel_id`（随书级联删除），角色是「书的资产」；跨书复用等于每本书重建设定。boss 拍板：功能挂全局「写作工具」菜单（任务清单/拆书之后的第三项）、支持拆书后收录、库内增删改查全字段且与设定页角色卡逐字一致、头像随卡、版式按 OpenDesign 档案柜产出；书里的角色可按作家操作**手动同步**回库（评审「再同步 YAGNI」据此作废）。

## What Changes

- **新账号级表 `character_library`**（不挂 novel_id，跟作家走）：全字段与书内角色卡同构——名字/别名·称呼/一句话人设/基础档案八格（性别·年龄·种族·势力·身份·外貌标签·语言特征·背景·剧情定位）/认知内核 30 格/头像 BLOB（full/thumb 两档，库域自持，不挂书级 image_assets）；库专属三个分类格：题材、定位（主角/配角/反派/路人，与书内共享常量同源）、小类（亲人/朋友/挚友/小弟/下人/长辈/敌人/其他）。
- **九操作 API**（前缀 `/api/character-library`，全部 `get_current_user`）：列表一次给全（文本字段＋头像引用；筛选/搜索/排序在前端内存完成）／手建空卡／详情／整卡保存／删卡（复制语义）／头像读取（`GET /{id}/avatar?variant=full|thumb`，鉴权＋归属校验＋缓存头）／收录（书内卡整卡复制，provenance 幂等）／书→库手动同步／用到新书（复制落卡）／AI 随机起名（不挂档位门，本地兜底恒 200）。
- **provenance 三列**（src_kind=deconstruct/book/manual＋src_ref＋src_character_id）＋部分唯一索引：重复收录返回已有卡；「同步」凭 provenance 拉源书卡最新格与头像（只手动触发，无自动同步；库分类不动）。
- **用到新书**：选书弹窗（现存书单选＋「新建一本」入口）；设定照原卡复制一份，可选导入时换名换龄；撞名自动「（角色库{n}）」后缀＋回执留痕（沿用建书撞名惯例）；导出后库→书方向不回写。
- **AI 随机改名换龄**：按性别 AI 起名＋年龄 16–55 一次返回；无 Key/调用失败/模板缺失一律本地词库兜底恒 200；只碰名字与年龄，其余格不动。
- **权益**：库 CRUD、收录、用到新书全免费（收录入口上游自带拆书档位门）；唯一挂 `ai_feature` 的是随机起名（standard 档）。
- **前端**：写作工具菜单第三项「角色库」＋ `/tools/characters` 路由；档案柜版式（大页头统计＋四组左栏＋卡片/列表双视图＋悬停浮现动作＋空态双入口）；角色卡编辑弹窗（全字段，认知 30 格直取共享常量禁手抄）＋「从《书》同步最新设定」钮；书内角色页「从角色库导入」（v1 逐张）。
- **备份**：配置包新增 `character_library` 段（角色卡＋头像随备份往返），格式升 v8，旧包缺段跳过。
- **版本存活**：库表注册进 Base.metadata 即被带回引擎列交集搬运覆盖；加列一律 nullable 或带 server_default（否则整表跳过吞表）；迁移告知卡加「角色卡 N 张」一份。
- 明确不做：自动同步、库→书回写、FTS 全文索引、批量用到新书（逐卡，后补）、关系的跨书迁移（关系边不入库）。

## Capabilities

### New Capabilities

- `character-library`: 跨书角色库（全局档案柜）——账号级角色资产的字段同构契约、四组分类与双视图检索、书内/拆书两条收录、书→库手动同步、用到新书导出、AI 随机改名换龄、全字段 CRUD、空态与删除语义。

### Modified Capabilities

- `deconstruct-book`: 「写作工具入口」由两项扩充为三项（新增「角色库」，`/tools/characters` 路由入口）。
- `backup-restore`: 配置包新增 `character_library` 段随包往返（v8 加段；旧包缺段跳过）。
- `db-generation`: 「旧库迁入引擎」补账号级内容资产表的注册与加列纪律（注册即带回、加列须 nullable/带默认）；「迁移告知卡」清单加「角色卡 N 张」。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：顶栏写作工具下拉（加第三项）；角色库页（新路由 `/tools/characters`，档案柜版式）；角色库编辑弹窗（全字段＋同步钮＋删除两段确认）；「用到新书」选书弹窗；书内角色页按钮行（「从角色库导入」「收入角色库/同步到角色库」）。
- **对象状态**：定位 pill 四档用既有 `.pill` 组合（主角＝`.pill-accent` 软底强调 / 配角＝`.pill-tag` / 反派＝中性弱色或 `.pill-warn` / 路人＝`.pill-tag` 弱化；**不新增实底胶囊**；如坚持红色/实底需先在 design-language §6.2/N6 登记例外并同批改两端 design-vocab）；悬停浮现动作三态（hover / focus-within / pointer:coarse 常显）；空态两分；toast。不新增提示语气词。
- **共享段**：不触碰（`base.css` 令牌与基础组件类零改动；`design-system` 无 delta）。
- **原型先行**：已完成——`docs/design-c/drafts/ai-novel-c端-角色库-原型.src.html`（build/check 脚本＋五场景真界面实抓 v3，自检全绿）；实现按原型落，偏差登记 `docs/design-c/prototypes/ADJUSTMENTS.md`。
- **设计工件产出**：设计会话已产出（前置原型五场景＋设计说明＋OpenDesign MCP 档案柜版式评审定稿）；实现侧照原型与设计说明自查门禁。

## Impact

- `client/backend/models/character_library.py`（新）：账号级库表（uuid 主键／user_id 索引／role/genre/kind/name/aliases/persona/dossier_json/cog_json/src_kind/src_ref/src_character_id/src_novel_name/rev/created_at/updated_at）＋部分唯一索引 `UNIQUE(user_id, src_ref, src_character_id) WHERE src_character_id <> ''`（先例：characters 主角部分唯一索引）；**头像字节独立表 `character_library_blobs`**（library_id/variant/data，照 ImageAssetBlob），列表不回传字节。
- `client/backend/models/__init__.py`：注册新表（带回引擎覆盖的唯一条件）。
- `client/backend/library/`（新域）：`service.py`（CRUD/收录/同步/用到新书/随机起名为纯逻辑）、`router.py`（七个端点；静态段声明在 `/{id}` 族之前防路由遮蔽——`/graph` 先例）。
- `client/backend/settings/character_service.py`：**扩 `create_character` 可选 `cog`（COG_KEYS 白名单）与 `avatar`（→ImageAsset＋Blob 同事务）**——现签名无 cog 且 role=主角会静默降级书内主角，直接复用会丢认知格与头像；用到新书走扩展签名，撞名主体截断留后缀位再拼「（角色库{n）」重试；新增库侧读卡投影白名单（禁 model_dump 直出）。
- `client/backend/settings/ai_router.py`＋prompts 私有仓：随机起名新 feature key（standard 档）＋模板（跨仓发布链，兜底不依赖模板）；AI 客户端走 `get_ai_client_for_user`（无 novel 上下文）。
- `client/backend/backup/`：配置包导出/导入加 `character_library` 段（含头像 BLOB）；format v8 ；旧包缺段跳过。
- `client/backend/db_lifecycle.py`：候选告知卡载荷加角色卡计数。
- `client/frontend/src/lib/libraryApi.ts`（新，照 charactersApi 信封）＋ `useCharacterLibrary` hook（照 useDeconstructTasks 模式）。
- `client/frontend/src/components/tools/`：`CharacterLibraryPage`（新）＋ `ToolsMenu.tsx` 第三项；`App.tsx` 加 `/tools/characters` 路由。
- `client/frontend/src/components/library/`（新）：档案卡/行、四组筛选栏、双视图切换、编辑弹窗（Modal 复用、认知 30 格直取 `characterModel.ts` 常量）、两张清单弹窗、选书弹窗。
- `client/frontend/src/components/novel/settings/CharacterManager.tsx`：按钮行加「从角色库导入」；卡操作加「收入角色库/同步到角色库」。
- 测试：后端库 CRUD/收录幂等/同步/撞名后缀/随机名兜底/备份往返/迁移带回（账号级表）＋前端库页筛选搜索/双视图/CRUD/空态/e2e 菜单入口→收录→用到新书全链。
- 依赖：AI 起名模板在 prompts 私有仓（跨仓发布链）；无模板时兜底路径独立成立。
