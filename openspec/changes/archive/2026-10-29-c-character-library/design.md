# c-character-library — 设计

## Context

见 proposal.md「Why」。关键现状约束：

- `characters` 表强绑 `novel_id`（ondelete CASCADE、`UNIQUE(novel_id, seq)`/`UNIQUE(novel_id, name)`、主角部分唯一索引），角色是书级资产；账号级表先例＝`deconstruct_jobs`（user_id NOT NULL＋索引）。
- 旧库迁入引擎是全表列交集搬运（`migration/engine.py`），账号级表注册进 metadata 即被覆盖；目标 NOT NULL 无默认列会触发整表跳过——这是「加列纪律」的来源。
- 备份双包（资产包逐书＋配置包 user/api_configs/image_configs），`format_version` 演进规则「加键兼容不升版、加段升版」。
- 角色模型常量单源：后端 `settings/character_model.py`＋前端镜像 `lib/characterModel.ts`（parity 锁）；前端 UI 常量禁手抄。
- AI 链路：`settings/ai_router.py`（ai_feature 档位标注＋prompts 仓模板）＋`ai_client.get_ai_client_for_user`（无 novel 上下文的账号级调用）。
- 设计系统：单强调色、oklch token、`.pill` 四角色、`.seg`/`.chip`/`Modal` 组件族；WebView2 108 有 legacy-colors 编译，TSX 禁内联 oklch。

## Goals / Non-Goals

**Goals**：账号级角色库的完整 CRUD 与两类收录、手动同步、用到新书导出、AI 随机名龄；与设定页字段同构且共享常量单源；备份与版本迁移下角色卡不丢。

**Non-Goals**：自动同步与库→书回写；批量用到新书（v1 逐卡）；关系的跨书迁移；FTS；库内排序拖拽（按收录序/姓名即可）；素材库/世界观库的通用抽象（只立约定不建抽象层）。

## Decisions

**D1 账号级内容资产表约定（而不是通用资产抽象）**：`character_library` 表自持 uuid 主键、`user_id`（NOT NULL＋索引）、无 `novel_id`、时间戳；命名 `<域>_library`。未来域复制此约定，不建 polymorphic 资产表——抽象只省三个字段，却引入所有查询的间接层，违背简洁优先。注册进 `models/__init__.py` 即被带回引擎覆盖；加列一律 nullable/带默认（spec 已钉）。

**D2 头像库域自持 BLOB（拆独立表＋读取端点）**：`image_assets.novel_id` NOT NULL＋级联——库卡挂不进去，改 nullable 会污染书域查询与资产备份语义。方案：主表 `character_library` 只存文本与头像引用；图片字节存 `character_library_blobs(library_id, variant='full'|'thumb', data)`（照 `ImageAssetBlob` 先例，WebP，编解码与尺寸档同头像 full/thumb）。列表接口只回 `avatar: {has, thumb_url}` 引用、SHALL NOT 回传字节；新增 `GET /api/character-library/{id}/avatar?variant=full|thumb`（`get_current_user`＋按 user 归属校验；Cache-Control＋ETag，BLOB 未变不重传）。**体积控制三策**：①档位收敛——库头像 full 上限 512px、thumb 上限 128px（WebP q≈80），单图字节上限 256KB，超限素材入库时用与 ImageAsset 同一编解码工具**转码压缩一次**后落库（归档源书 full=1024 收录时按 512 重压）。**为什么不在生成时限小**：各供应商头像档位是固定契约（Ark 实测要求面积 ≥921600 px²、768×1024 都会 400；示意图 avatar 统一请求 1:1 原生档，见 `image_assets/adapters.py:_native_size`），不存在「生成 512 且更清晰」的档；正确姿势＝生成保持原生方形档、**入库一次高质量降采样**（LANCZOS 级重采样，512 在 34–64px 展示尺寸下有 8–15 倍冗余，清晰度无损）；按供应商能力另找小档会引入跨家质量不一致，不做（后续可选优化，记录不实施）；②v1 头像可选——无图卡走姓字块、不预生成，拆书卡零存储；③用到新书时以同档位写入目标书 `ImageAsset`（书内展示尺寸 32–160px，512 足够）。前端用 `LibraryAvatar` 组件消费该端点（不走书域 `ImageThumb.refreshLinks`）。拆书收录与手建先走姓字块；「用到新书」把字节写入目标书新建的 `ImageAsset`＋`ImageAssetBlob`（同一事务），书内仍走现有头像资产链。

**D3 复制语义＋provenance**：收录=复制（整卡字段），「用到新书」=复制（导出一份）。provenance＝`src_kind`（deconstruct/book/manual）＋`src_ref`（novel_id/task_id）＋`src_character_id`＋部分唯一索引 `UNIQUE(user_id, src_ref, src_character_id) WHERE src_character_id <> ''`（先例：characters 主角部分唯一索引）——收录幂等与「同步」定位都靠它。书→库同步＝PULL 覆盖书域格、库分类不动（spec 已钉），不做自动同步、不接受库→书回写。

**D4 列表一次给全（文本字段＋头像引用）、前端内存过滤**：库规模百~千卡、每卡文本几 KB（图片字节不入列表——D2）。照「角色列表一次给全」先例：`GET` 返回全部卡的文本字段与 `avatar.thumb_url`；筛选/搜索/排序/视图在前端做。备选「服务端筛选参数＋分页」：本地单用户无收益，分页反而破坏四组计数的即时性。搜索匹配在归一化文本上做（小写+NFKC），高亮按同一归一化切片——过滤与高亮必须同源，防「亮的不等于筛中的」；命中卡面不展示的字段（背景/剧情定位/势力/外貌/种族/认知格/来源书名）时，卡底显示一行「命中：背景 …」并高亮该词（回落展示，spec 已钉）。React 里高亮用 `text.split(term)` 分段渲染 `<mark>`，禁 `dangerouslySetInnerHTML`。输入防抖 250ms、过滤 `useMemo`。

**D5 AI 随机名龄**：新端点 `POST /api/character-library/random-name`（入参性别），后端组装 prompts 模板；AI 客户端走 `get_ai_client_for_user`（库无 novel 上下文）；任何失败（无 Key/超时/模板缺失 `PromptPackMissing`）→ 后端内置本地词库兜底＋随机年龄 16–55，恒 200 返回。年龄随机与名字同响应，前端一次拿全。**门控＝不挂档位门**（仅 `get_current_user`）：理由——`ai_feature` 是标注不产生门；挂 `require_ai_access` 无 Key 即 503、违反「恒 200」；挂 `require_tier_access` 违反注册表测试「LLM 类 key 只认 require_ai_access」。起名是本地兜底能力，SHALL NOT 要求已配置写作模型；`ai_feature("charlib-random-name")` 仅保留计量/审计标注（S端零改动，无新 tier key）。若日后要收紧，按拍板点另行立项（六步登记 SOP）。

**D6 落到书内：服务扩展＋撞名策略**：`create_character` 现有签名无 `cog`、不建头像资产，且 `role=主角` 会静默把目标书现有主角降级——直接复用会丢认知 30 格与头像。方案：扩 `create_character` 可选参数 `cog`（按 `COG_KEYS` 白名单逐格校验/截断）与 `avatar`（full/thumb 字节 → `ImageAsset`＋`ImageAssetBlob`，与建卡同一事务），书内基础设置仍走现有分支（书域新入口不回归旧调用）。主角冲突口径＝沿用建书惯例「每书只保留首位主角」：导入的主角卡若遇书内已有主角，落为配角并在回执留痕（SHALL NOT 静默改书内主角）。撞名：先对名字主体截断（预留后缀位）再拼「（角色库{n}）」重试 ≤5 次，回执汇报改名。批量语义按逐卡降级（v1 不做批量）。

**D7 权益**：库 CRUD/收录/用到新书全免费（`get_current_user` 即可）；仅随机起名挂 `ai_feature`（standard）。依据：收录入口上游=拆书完成页（PRO 门已在），用到新书=书内建卡同权（免费），库自身不新增售卖面。

**D8 前端落位**：路由 `/tools/characters`（App.tsx 加一条 `Authed` 路由）；ToolsMenu 加第三项；页面组件新写（`components/library/`），弹窗复用 `Modal`、切换用 `.seg`、标签用 `.chip`、定位 pill 用既有 `.pill` 组合（主角 `.pill-accent` 软底强调/配角 `.pill-tag`/反派中性弱色或 `.pill-warn`/路人 `.pill-tag` 弱化——**不新增实底胶囊**；如坚持红/实底先在 design-language §6.2/N6 登记例外）；认知 30 格直取 `characterModel.ts` 常量渲染；库卡与列表状态用 `useCharacterLibrary` hook（照 `useDeconstructTasks`）；「新建一本」走现有新建书流程后自动带入（不走 carryStore）。原型里的「真 main 让位」是静态抓取手段，真实现由路由组件直接渲染 `<main className="main">`。

## Risks / Trade-offs

- [库卡与书卡双写漂移（同名字段两处维护）] → 字段名单与格位全部来自共享常量单源；库侧只加库专属三格；parity 测试覆盖库卡序列化字段集。
- [账号级表加列触发整表跳过吞表] → spec 钉「nullable/带默认」纪律＋回归用例「旧库→新库不整表跳过」。
- [AI 起名模板在 prompts 私有仓，发布链滞后] → 后端兜底路径独立成立（无模板也能起名）；feature key 先建、模板随下一次提示词包发布。
- [搜索命中与高亮不同源导致「亮的不筛/筛的不亮」] → 过滤与高亮共用同一归一化函数，单测钉住。
- [头像 BLOB 体积膨胀库文件与备份包] → 档位收敛后单卡估 40–80KB，千卡约 40–80MB（SQLite 与 zip 打包均可接受）；v1 头像可选、多数卡零存储；若日后仍嫌大，再连同书内头像整体迁移文件存储（一次迁移，不搞双机制——已拍板继续存库，2026-10-28）。

## Migration Plan

1. 新表随 `create_all` 建出（新版本首启即建）；旧版本升级换新库后，角色卡由「迁移」流程带回（引擎零改动，注册即覆盖）。
2. 备份 format v8（`FORMAT_VERSION` 共用常量升 8，`test_backup_images.py` 的版本断言同批改）：配置包 `config.yaml` 加 `character_library` 段（文本＋头像 sha256/bytes 描述），头像字节照 images 先例以独立二进制条目 `character_library/avatars/{id}-{variant}.webp` 入 zip；旧配置包缺段跳过、头像文件缺失时卡片照常入库并 warning；导入按库卡 id 幂等。
3. 版本兼容口径：配置包当前不参与版本闸——旧应用导入 v8 配置包时**静默忽略** `character_library` 段（不报错）；资产包共用 `FORMAT_VERSION=8`，旧应用拒绝恢复新导出的资产包并提示升级（与 v6→v7 图像段同款既有取舍，接受并记录）。
4. 回滚策略：表新增无破坏性变更；回滚旧版本时新库不被旧版读取（db-per-version 天然隔离）。

## Open Questions

- 小类词表是否并档（小弟/下人）——不影响 schema（文本白名单），可随实现期反馈调整。
- 库卡头像的「头像工坊」入口形态（库内直接生成 vs 跳书内工坊）——实现期按工坊组件现状定。
