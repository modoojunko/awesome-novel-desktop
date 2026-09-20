# 书架工具栏：搜索 · 状态筛选 · 排序 · 分组 · 分页（works.html v2 对齐）

## Why

`drafts/works.html` 于 2026-09-20 11:44 更新为 v2（+9.5KB）：书架从「纯卡片流」升级为可组织的作品清单——页头下新增工具栏（书名搜索＋四态筛选 chips＋四键排序），单态筛选时呈现生命周期分组视图（分组头携「去完本」常驻入口），卡片流分页（12/页＋触底自动加载），筛选/搜索空态带「清除筛选」。用户裁定以原型为准（延续 c-works-spacing-align 的同一条主线）。

## What Changes

- **工具栏 `.bk-toolbar`**（page-head 下）：书名搜索框（包含匹配、大小写不敏感）＋状态 chips（全部/设定中/写作中/待完本/已完结，`aria-pressed`，默认全部）＋排序 select（最近更新/创建时间/字数/书名）。
- **排序语义**：状态 rank 恒优先（待完本→写作中→设定中→已完结）＞所选排序键＞书名 zh tie-break；「全部」视图为单网格状态混排（待完本恒在前），单态视图为 `.bk-group` 分组（分组头＝色点＋标签＋「N 本」＋待完本组加「主线已收齐 · 去完本」按钮）。
- **待完本提示条退役（BREAKING 行为变化）**：v2 删除 `#readySlot` 提示条，其「在哪完本」职责并入 ready 分组头常驻入口与待完本卡页脚「完本」——动 works-finish-flow 既有 requirement。
- **done 卡页脚加「回看」**（secondary sm，落预览）；卡片语义 a→div role=link。
- **`.book-card .foot` 随 v2 重抄**（v1 `margin-top:18px` → v2 `margin-top:auto; padding-top:18px`）——修正上一条 change「间距已对齐」的时点：v2 这一处静默改过，属同批补抄。
- **分页**：12/页，「显示更多 · N/M」按钮＋IntersectionObserver（rootMargin 160px）触底自动加载。
- **空态两分**（判据按原型：`filtered = kind!=='all' || !!q`）：
  - **筛选/搜索无果**（filtered=true）→ v2 `bk-empty`：「没有找到符合条件的作品」＋「换个关键词或状态再试试。」＋`清除筛选`（含排序回最近更新）＋`新建作品`；
  - **零书**（filtered=false）→ **保留三步引导 first-run**（用户裁定，2026-09-20）——v2 零书简空态**不采用**，沿 ADJUSTMENTS #7 应用侧扩展口径随晋级基线保留；工具栏随有书态渲染（零书/加载/失败不渲染），登记为偏差。
- **工具栏渲染条件**（修正原「恒渲染」）：有书态渲染；零书态由 first-run 承担入口职能（一并登记）。
- **排序比较器容错**（后端评审 F1.4）：接口下发的是**无时区 ISO 字符串**（非原型数字时间戳）——比较键 SHALL 走 `Date` 解析容错（null/缺失归 0），否则排序静默退化为原序；「最近更新」语义钉死为**最后一次书级动作**（正文/章纲保存不刷新，后端事实，spec 注明）。
- 骑手修正（评审 F3.1）：FinishModal 409 toast 改透出服务端 `detail`（`errMessage`），替换硬编码「先把主线章节全部归档」——新「分组头去完本」入口使「已完结 409」成为可达路径，现状会报错误原因。
- 原型晋级：works.html v2 → `prototypes/list.html` 基线换代（**需保留 v1 的 quota/锁卡 parity 依赖块**，见决策点 5）＋ADJUSTMENTS 新章登记。

### 待用户确认的显式决策点（评审后修正）

1. ~~首启三步引导退役~~ **已裁定（2026-09-20）：保留三步引导**——v2 零书简空态不采用，晋级基线保留 first-run 块（沿 #7 先例）；工具栏随有书态渲染。
2. **待完本提示条退役**：待完本不再弹页头提示条，入口移至 ready 分组头＋待完本卡页脚；「全部」视图下靠状态 rank 置顶保证可达（后端评审 F3.3 已证可达性成立）。
3. **排序语义反转**：v2 的「状态 rank 恒优先」推翻 2026-08-29 用户裁定（书架=按 updated_at 倒排的「继续」入口）与 ADJUSTMENTS #6——完本书刚更新也沉底。按原型实施并改写 #6；若保留旧语义则本项回退。
4. ~~零书空态标题文案~~ **自动消解**：零书支改用 first-run 后，v2 的「没有找到符合条件的作品」只出现在筛选无果支（语义正确），照抄即可，无需改原型。
5. **quota/锁卡场景处置**：v2 原型完全删了免费额度墙（`lock-tile`/`ainovel.member` 零命中）——晋级时「保留 v1 块」维持 quota parity，或取消 quota 场景改由 e2e 承担（推荐前者，沿应用侧扩展先例）。

## Capabilities

### New Capabilities

- `works-toolbar`: 书架检索与组织——搜索/状态筛选/排序/分组视图/分页/两种空态的外部行为契约。

### Modified Capabilities

- `works-finish-flow`: 「待完本提示条」requirement 改为「ready 分组头常驻完本入口」（提示条退役）；「书架卡片四态徽章与分状态页脚」requirement 补 done 页脚「回看」。

## Design Impact

- **受影响端**：C端 单端，仅书架屏（/novels）；**零后端改动**——list 接口已下发全部所需字段（name/created_at/updated_at/word_count/total_archives/finished_at），过滤/排序/分页全前端。
- **受影响屏/弹层**：书架一屏；完本弹窗不动。
- **对象状态**：不新增语气词；四态语言复用（chips/分组头 dot 均按既有四态着色）。
- **是否触碰两端共享段**：否——新样式全部落业务层 `list.css`，base.css 零改动。**评审修正**：`.chip` 是**现役同名类**（`book.css:437` 设置页/工作台在用，且标准 §6.2 已判决归并 `.pill-tag`），不是「新词汇」——ADJUSTMENTS 登记的是**同名两义裁决**：本屏以 `.bk-chips .chip` 作用域化（选中实底 accent），跨屏零影响；`--radius-pill` 在 C端 不存在，实现沿现状字面 `999px`（补 token 属另一 change）。
- **是否需要原型先行**：原型已在（drafts/works.html v2 即设计真值）；任务是将它晋级为 prototypes/list.html 基线＋ADJUSTMENTS 登记。
- **设计工件产出方**：设计侧已产出（works.html v2，2026-09-20 11:44）；实现侧自查晋级。

## Impact

- 代码：`NovelListPage.tsx`（工具栏状态机＋分组渲染＋分页＋空态重构）、`list.css`（toolbar/chip/group/empty/load-more 家族）、`lib/`（排序/过滤纯函数可单测）。
- 设计线：`prototypes/list.html` 晋级 v2、ADJUSTMENTS 新章（含新词汇登记与两个决策点）、design-vocab 如有新档位（chip 30px 高/12.5px 字号、搜索 36px 高）同批登记。
- 验证：design:lint → parity 场景扩（books 混排/单态分组/空态/筛选无果）→ tsc/vitest（新增排序过滤单测）/相关 e2e。
- 不改：完本链路端点、⋯ 菜单、导入/新建、间距（上一 change 已对齐）。
