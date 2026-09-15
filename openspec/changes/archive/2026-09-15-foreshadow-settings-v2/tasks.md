# foreshadow-settings-v2 · Tasks

> 三批切片（用户拍板）：§1-§5＝批1 免费基座（表＋迁移＋CRUD＋面板＋门禁）；§6-§7＝批2 体检＋起草；§8＝批3 拟收束＋一致性；§9-§10 收尾与退役。每批独立可交付，迁移在批1 独立暴露。

## 1. 词表与表结构（批1）

- [x] 1.1 新建 `client/backend/settings/hooks_model.py` 词表单源：9 type slug、3 status、长度常量（description/payoff_note 300）、priority 归一函数（int/str/high→1/2/3）；前端镜像常量＋parity 测试（沿 test_shared_constants_parity 先例），pytest 通过
- [x] 1.2 新建 `models/hook.py` NovelHook：id UUID PK、novel_id FK CASCADE、seq、description、type、priority Integer、status、introduced/planned/resolved/mentioned_chapter_id（FK SET NULL＋index）、payoff_note、时间戳；novels.hook_seq_high 计数器；索引 ix_hook_novel_status；lifespan create_all 自动建表，空库启动验证表存在
- [x] 1.3 卷章树 API 补 chapter id：`volumes/service.py` list_volumes 与 `novels/service.py` build_project_tree 的章条目加 `id` 字段；curl 验证 `GET /volumes`、`GET /tree` 章条目含 id 且等于 chapters.id；新增断言用例

## 2. CRUD 与门禁（批1）

- [x] 2.1 新建 `settings/hooks_router.py`：GET 列表（含 #H-#### 展示号）/POST/PATCH/DELETE/POST restore（ops token，原 id 原样恢复；token 到下次操作/刷新失效）；seq 同事务取号不复用；路由注册先于 `/settings/{type}` 兜底；单测覆盖必填/枚举/长度/跨书章引用拒绝/seq 不复用/restore 幂等
- [x] 2.2 章节删除级联验证：删章/删卷后 hook 行保留、四列章引用 SET NULL；`chLabel` 悬挂口径前端显示「章节已删」（PR 阶段先以后端用例钉住）
- [x] 2.3 `_check_hooks` 换真表数据源（≥1 条 trim 后非空描述、任意状态）；`test_readiness.py::test_confirm_hooks` 等种数据从旧 PUT 换新 API；新增「全 resolved 可确认」「空表 400」「全空格 400」「resolved 无留痕可确认」四用例
- [x] 2.4 消费方切换：`prompt/context.py`（status==active＋chapter id 排除本章＋优先级 高/中/低 标注）、`write/chapter_writer.py`、`write/auxiliary.py`、`chapters/ai_draft.py`；`archive/service.py` 归档改单条 UPDATE mentioned_in_chapter_id；`_canonical_chapter_ref` 两处副本退役；test_hooks_consumers 重写为真表语义（注入过滤/本章排除/归档幂等）
- [x] 2.5 摘除旧 KV 通道：`filesystem/paths.py` PATH_TO_KEY 去 hooks、`filesystem/init.py` SETTINGS_TEMPLATES 去种子并删 hooks.yaml.template、`settings/router.py` hooks 分支下线；test_db_storage 键集合断言更新

## 3. 备份 v3 与升级链（批1）

- [x] 3.1 `backup/format.py` FORMAT_VERSION=3；导出端新增 hooks 段（章引用 id→ref，解析不了置空）；导入端 hooks 段直读＋章循环落库后 ref→id 重绑（显式注释落库顺序）；test_backup_roundtrip 第十层（hooks 计数/章 ref 对拍/status 逐条相等）
- [x] 3.2 导入器 v1 hooks 读窗：三数组→行、mentioned→active＋mentioned 列、introduced_in 归一绑 ref（绑不上 NULL＋warning 不丢行）、priority/type 混形归一、project_settings 无 hooks 残留；单测覆盖每种混形样例
- [x] 3.3 升级演练扩阶段（沿 upgrade_drill 六阶段）：seed-old 混形种子→boot-new 留档断言→import-v1 逐条对拍→export-v2（无 settings/hooks.yaml）→roundtrip-v2（删库救回＋引用跟随）→downgrade 拒绝；幂等重跑断言；`--all` 全绿
- [x] 3.4 发布说明文案：预告「升级整库留档＋从备份恢复」路径与伏笔段新格式（交付物＝文案草稿入 change 目录）

## 4. 前端 API 层与面板重写（批1）

- [x] 4.1 原型转正：`docs/design-c/drafts/ai-novel-c端-伏笔设定.html`（v3）→ `docs/design-c/prototypes/`，ADJUSTMENTS 登记 hk-* 词表映射表（.kv→作用域化、data-aiact、保存四态、状态点三色）与「空态 AI 旁路=零 AI 按钮唯一例外」；design:lint 通过
- [x] 4.2 新建 `lib/hooksApi.ts`（对齐 charactersApi 形态：列表/新增/PATCH/删除/restore、unwrap、类型）；卷章树消费点（useOutline/useWorkbench）适配章条目新 id 字段；tsc 通过
- [x] 4.3 重写 `HooksSettingForm.tsx` 为伏笔台账＋伏笔卡：三分组（状态点三色、空组不渲染）、搜索、添加置顶、伏笔卡 kv 档案表（描述/引入/计划收束/类型/优先级 seg/状态三态切换挪组选中跟随/收束记录软引导）、章节选择器（卷 optgroup、存 chapter id、悬挂「章节已删」、未建章留空 hint）；data-od-id 全量对齐原型
- [x] 4.4 自动保存：字段级防抖 PATCH＋串行队列＋409/失败回同步；save()=flush；「存草稿」对伏笔隐藏（SettingsView 显隐条件扩展）；面板脚保存四态（保存中…/已自动保存）＋确认前 flush 接 gap3；删除走 DELETE＋ops token 撤销（原 id 恢复），回执面板内自管（最近一条、8 秒自清）
- [x] 4.5 确认门禁与徽标：空表提示性预检（按钮恒可点，后端兜底）、确认即 flush＋confirm 快照；徽标五态（还没有伏笔/N 条待收束/已确认 · N 条待收束/全部收束/内容有变 · 待重新确认）+ settingsStatus reload 后一致；SettingsView 面板脚槽位接线
- [x] 4.6 样式收编：book.css settings-v 段落 hk-* 家族＋保存态；parity 场景开 settings-foreshadow（hooks stub：列表/单条/status/ai_state）；design:check 全绿＜0.2%
- [x] 4.7 e2e（批1 范围）：creation-flow hooks 段改真表流（选择器 input-hook-desc、保存等待换新端点、确认前进断言保留）；新增 CRUD 刷新回读/搜索过滤/状态挪组选中跟随/章节选择存 id/删除撤销原 id 恢复/空表确认指引/内容有变徽标，共 7 例；本地 docker 栈全量绿

## 5. 批1 验收

- [x] 5.1 批1 全量回归：容器 pytest 全量绿、e2e 本地栈全量绿、design:check 绿、tsc 绿；升级演练 `--all` 绿；手测「老库升级→伏笔零丢失→确认门禁→自动保存」全链

## 6. AI 端点与起草伏笔（批2）

- [x] 6.1 新建 `POST /ai/hooks/{action}` 白名单端点（require_ai_access＋require_novel_model、_judge_chat 记账全套、注册先于通配路由）：draft（简介＋题材锚＋世界＋主线→3 候选，出参 slug/priority 归一）、audit（活跃×已写章纲；章纲上下文构建器＋无章纲/无活跃降级免调用；判定常量服务端出）；mock 测试（降级/门控 403/超时记账/出参归一/audit 白名单）
- [x] 6.2 SettingsView 右栏 foreshadow 分支＋runHooksAi 分发（沿 runGenreAi 模式、aiState 一次分派 D13）；起草行：勾选采纳（乐观 temp id→POST 真 id）、采纳后聚焦引入章节、最近 5 次历史 chips、回执精确撤销；AiSink 落卡底
- [x] 6.3 埋坑体检交互：结果行可点跳转（选中＋聚焦字段＋滚动可见）、四类点名（超期/在期/未定期/无留痕）、降级文案；免费态四行可见＋锁定走统一升级出口、空态旁路同门控；e2e 4 例（AI 桩：候选采纳/体检跳转/免费锁定零请求/降级）

## 7. 批2 验收

- [x] 7.1 批2 回归：pytest＋e2e＋design:check 全绿；手测「起草→采纳→自动保存→体检点名→跳转补填」全链

## 8. 拟收束与查一致性（批3）

- [x] 8.1 payoff 端点（按选中 hook id 作用域，body 传当前编辑值，出 resolved ref 建议＋怎么收的）与 check 端点（选中×简介/题材/世界，缺输入 D7 降级）；mock 测试
- [x] 8.2 拟收束方案交互：结果落收束记录区 sink、覆盖已有记录时「覆盖并收束」明示警示、采纳=patch＋flush＋回执精确撤销；无选中置灰＋hint（h2/h4）；查一致性结果行跳转；e2e 3 例（覆盖明示/置灰指路/一致性跳转）

## 9. 退役与清理（收尾）

- [x] 9.1 旧 `/ai/hooks/description` 退役：FIELD_GENERATABLE 摘 hooks、_STYPE_PROMPTS 摘 hooks、删 `prompts/settings_hooks.prompt`；旧端点返回 400 退役文案；test_workflow_api 对应用例更新；全仓 grep 零残留
- [x] 9.2 提示词注入回归：`render_hooks_block` 展示号＋优先级标注用例；test_chapter_writer_context 预算数学不动、fixture 补 id 字段

## 10. 归档验收（收尾）

- [x] 10.1 全量验收：容器 pytest 全量绿；e2e 本地 docker 栈全量绿（新增约 14 例＋存量改造）；design:check 全绿＜0.2%；`upgrade_drill.py --all` 六阶段绿＋幂等重跑；roundtrip 第十层入套件
- [x] 10.2 规格同步：creation-flow（伏笔移出无 AI 清单）、readiness（任意状态＋真表数据源）、prompt-crafting（注入口径）、write-archive-meta-sync（mentioned UPDATE）、backup-restore（FORMAT_VERSION 3＋hooks 段＋v1 读窗）、volume-chapter-service（树补 id）、design-system（hk-* 词表）七处 capability sync；README 表清单更新
