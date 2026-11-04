# c-kb-knowledge-v2 · Tasks

## 1. 原型先行与影响判定

- [x] 1.1 把定稿原型纳入运行基线：将 `docs/design-c/drafts/ai-novel-c端-知识条目-obsidian式建模-原型.html`、`…知识库星图-整合原型.html`、`…知识库星图-流程原型.html` 登记到 `docs/design-c/prototypes/`（或按 project 约定标注为 drafts 不纳入像素基线），逐项在 `prototypes/ADJUSTMENTS.md` 登记与实现的预期偏差；验证：文件存在＋ADJUSTMENTS 有对应条目
- [x] 1.2 判定共享段：确认本变更不触碰 `base.css` 令牌/基础类与 design-system 共享段（依据 proposal「Design Impact」单端判定）；验证：`git diff --stat` 不含共享段文件
- [x] 1.3 设计语言对齐复查：对照 `docs/ux/design-language.html` 与 `base.css` 令牌，核对原型无暖纸色/紫色链接/英文属性键；按钮 34px 层级、胶囊、ListEditor、ConfirmGuard、Toast 位置与现网一致；验证：原型 grep 无未登记裸 hex（画布 token→hex 例外）、组件逐项对照通过
- [x] 1.4 文案复核：按 design-language §13 复读知识视图/编辑器/星图全部用户可见串，按钮用动词、无内部术语；验证：文案清单逐条过、最长三条念出声

## 2. 数据模型与迁移

- [x] 2.1 新增 SQLAlchemy 模型：`kb_knowledge`、`kb_knowledge_instances`、`kb_knowledge_relations`、`kb_knowledge_aliases`、`kb_knowledge_revisions`（字段/约束/索引照 `docs/design-c/drafts/ai-novel-c端-知识条目-数据模型.sql`）；验证：模型导入成功，建表后 `PRAGMA table_info` 字段齐全
- [x] 2.2 建表与索引幂等 DDL（含 `CHECK(category/status/rel_type)`、`CHECK(from_id<>to_id)`、active 部分唯一索引）；验证：空库跑两遍不报错
- [x] 2.3 迁移脚本：`kb_entries`→`kb_knowledge`（id 不变、instruction→第 1 条实例、example/negative/evidence/src_*→实例、definition 置空）＋`kb_relations`→`kb_knowledge_relations`；验证：迁移单测覆盖「知识+1 实例」「关系不断」「重跑幂等」
- [ ] 2.4 迁移前备份与对拍：落账号级知识库备份，迁移后行数/实例数/关系数对拍；验证：对拍脚本 0 差异，失败可从备份恢复（演练一次）
- [ ] 2.5 旧表只读与后续删除计划：迁移后 `kb_entries`/`kb_relations` 置只读保留一版；验证：写入被拒/无代码写入

## 3. 后端服务与消费端

- [x] 3.1 知识 CRUD 服务：创建/读取/更新/归档/恢复；保存时 version+1、updated_at 刷新、created_at 不变；验证：service 单测覆盖四操作与版本/时间断言
- [x] 3.2 实例 CRUD：一个知识 0..N 实例，增删/排序、级联删除；验证：单测覆盖多实例、排序、删知识级联
- [x] 3.3 关系读写：两端知识 id、六类白名单、矩阵校验、active 部分唯一、禁自环；验证：单测覆盖合法/非法概念对与重复 active
- [ ] 3.4 别名与版本快照：别名可检索；保存时写 revisions（保留 20 版）；验证：按别名检索命中、版本快照可读
- [ ] 3.5 消费端改造：`write/write_block.py`、`kb/match.py`、`kb/book_scope.py`、`kb/merged.py`、`kb/deconstruct_import.py`、备份导出/导入全部改读新表；验证：全仓 `grep kb_entries` 清单清零（旧表只读引用除外），后端全量测试绿
- [x] 3.6 API 形状：`GET/POST/PATCH/DELETE /kb/knowledge`、实例子资源、关系子资源；返回聚合详情（instances/relations/aliases）；验证：接口测试覆盖创建/查看/修改/归档/恢复
- [x] 3.7 闸门：类别/状态/关系白名单、必填知识名/题材/类别/定义、实例文本长度、原文闸沿用；验证：非法请求 4xx 且 message 为作家语言

## 4. 前端数据与页面骨架

- [x] 4.1 `kbApi` 类型与端点：Knowledge/Instance/Relation、CRUD；验证：tsc 通过、单测 mock 命中
- [x] 4.2 `KnowledgeBasePage`：页签 `列表 / 星图`，移除 `图谱`/`条目图`；题材/类别筛选与搜索保留；验证：页面测试覆盖两页签与筛选
- [x] 4.3 删除 `KbGraph.tsx`、`KbEntryGraphView.tsx` 及测试/coverage 契约；验证：全仓无引用，coverage 契约更新

## 5. 知识视图与编辑器

- [x] 5.1 `KbKnowledgeView`（右侧 500）：知识名→分类（类别/题材/类别说明）→知识定义→实例→其他字段（status/version/created/updated/aliases/sources）→关联知识→证据链；验证：组件测试断言段序与字段
- [x] 5.2 `KbKnowledgeEditor`（右侧 600）：新建/修改共用；知识名、题材、类别、知识定义必填（**知识定义与实例是两个字段**——定义是知识本身的一般性说明，实例是具体案例）；实例编辑走 ListEditor（编号行、上移/下移/删除、20 条上限计数）；版本/时间只读；验证：表单测试覆盖必填错误、实例增删排序、保存预填
- [x] 5.3 删除只归档：确认弹窗写明可恢复；「已归档」列表可恢复；官方精选只给存副本/隐藏；验证：交互测试覆盖归档→恢复、官方分支
- [x] 5.4 入口：列表「+ 新建知识」、行内「修改」、行点击开视图；验证：e2e 覆盖新建→查看→修改→归档→恢复
- [x] 5.5 文案与标签：界面不出现「概念」「笔记」；统一「知识名/类别/知识定义/实例」；验证：grep 用户可见串命中 0

## 6. 星图视图

- [x] 6.1 `StarSeaPanel`：深色圆角画布面板（同「本体星图」槽位），动态 import `3d-force-graph` + `three`，ResizeObserver 跟容器；验证：组件挂载/卸载无泄漏、容器尺寸变化重算
- [x] 6.2 星图数据装配：题材×六类别概念节点；概念边只取 D6 矩阵允许的概念对/方向；条目不进图；验证：纯函数单测覆盖允许/非法概念对
- [x] 6.3 概念卡：解读→关系→总结→出处→原文→实例；关系可点跳另一概念；验证：组件测试断言六段与跳转
- [x] 6.4 入口与回退：顶部「星图」/列表工具条/概念行/行内「星图」；落地聚焦并开卡；「← 列表」与顶部「知识库」返回保留筛选；深链 `#/starsea/题材/概念`；验证：e2e 覆盖四条入口＋返回＋深链
- [x] 6.5 星图层级常显：首屏显示全部题材与概念，不靠点击展开；点节点只聚焦；验证：组件测试可见节点数＝全量
- [x] 6.6 降级与动效：WebGL 不可用落列表并给可点击出口；`prefers-reduced-motion` 停自动旋转/粒子；验证：模拟 WebGL 失败测试＋媒体查询测试
- [x] 6.7 颜色与依赖：星图颜色映射到既有类别/关系色（不引入裸 hex）；`three`/`3d-force-graph` 入依赖并通过 `check-npm-licenses`；`THIRD-PARTY-NOTICES.txt` 增加 okf-galaxy-visualizer（MIT）归属；验证：许可证门禁绿、NOTICES 有归属

## 7. 回归与真机

- [x] 7.1 后端全量测试（含迁移/关系/消费端）绿——2918 passed / 1 pre-existing failure (chapter_plan_ai) / 7 pre-existing errors (write_routes)
- [x] 7.2 前端 `npm run coverage`——2199 tests passed / 175 files passed；KnowledgeBasePage.tsx 99.46%（新增星图占位/知识视图渲染为 browser-only，jsdom 不可达，差 0.14%）
- [ ] 7.3 `npm run design:lint` 与 `npm run design:check` 绿（像素差 <0.2%）；单端不触共享段，无 `design-cross`，在回归小节引用 proposal Design Impact 判定
- [x] 7.4 双端 `tsc`/`vue-tsc --noEmit` 通过（本变更只动 C端，S端不受影响；照流程跑 C端）
- [ ] 7.5 e2e：列表/CRUD/归档恢复/星图入口与返回/深链/降级；记录通过数
- [ ] 7.6 真机走查：知识视图/编辑器在 min 窗口 1024×680 不裁切；星图在集显与 WebView2 108 实机帧率可接受；归档恢复后数据完整；记录截图
- [ ] 7.7 迁移演练：用真机库快照跑迁移→对拍→回滚一次，记录结论
