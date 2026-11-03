# c-kb-baseline · 全题材基线知识包（分发与同步）

## Why

写法块（c-kb-write-block，已合 #996）的取数源是账号级知识库——**新用户库空＝写法块交付为零**（冷启动缺口）。解法：由我们维护一套**全题材基线知识**（各题材代表作拆书代产＋人工筛选改写，持续版本化维护），随 CDN 分发，客户端启动同步幂等 merge 进账号库（来源标签「官方精选」），开书复制/写法块从此开箱有货。

内容源仓已建：`modoojunko/awesome-novel-knowledge`（私有；schema＋validate/build/publish 工具＋玄幻/都市打样 13 条，CI 绿）。

## What Changes

- **条目来源**：新增 src_kind="baseline"（工程标识）；作家可见来源标签「官方精选」（与用户拆书 deconstruct、手录 manual 区分）
- **同步管线**：启动补偿拉 `download/knowledge/baseline/latest.json` → 按 manifest sha256 校验下载 entries.jsonl/tombstones → 幂等 merge 进账号库（只增不改：用户改过/删过/标过的同 key 不覆盖）
- **下架**：tombstones 清单驱动物理清理（用户标记过的转隐藏而非删除）
- **AI 整理边界**：整理/合并/纠偏对 baseline 条目跳过（官方内容客户端不改写，修订走基线包版本）
- **知识库页**：来源筛选取值加「官方精选」；条目卡来源标签同

## Capabilities

### New Capabilities

- `knowledge-baseline`: 基线包分发与同步（latest 指针/manifest 校验/幂等 merge/tombstone 下架/同步状态面）

### Modified Capabilities

- `knowledge-base`: 数据模型新增 src_kind="baseline"（AI 整理跳过边界）；浏览页与条目卡来源标签「官方精选」

## Design Impact

- 受影响端：**C端 only**（S端零接触；分发走既有 CDN，与提示词包同域不同目录）
- 受影响屏/弹层：知识库页（来源筛选项＋条目卡标签「官方精选」）；**无新增弹窗**——同步静默，失败进知识库页状态行（可重试），零确认
- 对象状态：无新增全局状态；条目新增来源枚举值
- 共享段：不触碰
- 原型先行：否（知识库页既有模式的枚举扩展）
- 设计工件：实现侧自查

## Gazette

- 内容源仓 `awesome-novel-knowledge`（私有）：validate/build/publish 工具＋CI（PR 必过 validate；publish 手动触发）
- CDN 凭据接入（KNOWLEDGE_CDN_BUCKET secret＋真实上传实现）为发布前置，boss 侧配置
- 与 c-deconstruct-knowledge（拆书双模式，进行中）的关系：基线内容生产复用拆书管线，本变更不依赖其合入（打样条目人工产出）
