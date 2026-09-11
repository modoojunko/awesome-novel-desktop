# Proposal: brand-name-single-source

## Why

品牌名以裸字符串散落两端 20+ 处，且已发生分叉：C端系统窗口标题、启动 splash、index.html title 仍是「AI Novel」，与产品名「爱小说」对不上（V4 评审旁注观察项）；S端 页脚/FAQ 也是手工拼的品牌串。当前改一次品牌名等于全仓翻找替换，且无法保证两端一致。需要一处声明、各端引用的单一事实源。

## What Changes

- 新增仓库根 `brand/brand.json` 作为品牌单一事实源：仅 4 个原子字段（`name`=爱小说、`nameEn`=AI Novel、`mark`=爱、`tagline`=AI 辅助长篇小说写作）。
- C端 构建期接入：vite 读取 brand.json 注入 index.html title；前端新增薄桥 `src/lib/brand.ts`；python 侧新增品牌桥模块（读 json，读不到回落内置默认值，启动路径零风险）。
- C端 消费点替换：pywebview 窗口标题「AI Novel」→「爱小说」；启动 splash 文案改读品牌桥；`index.html` title 改品牌驱动；Navbar/Login/Landing/StatusBar 字标与版权行引常量（**展示值不变**）；版权行年份由写死 2026 改为当前年份（顺手修潜伏 bug）；备份产物名前缀「爱小说-」引同一常量（**值不变**，`backup-restore` spec 契约不动）。
- S端 消费点替换（存量 9 处全量收编）：新增 `constants/brand.ts` 引同一 json；index.html title、FooterSection 版权行、DashboardLayout 顶栏字标、AuthPage 页面 title 与页内字标、CashierPage 收银台字标、DownloadModal 弹窗标题、HeroSection 演示窗标题、SupportPage 邮件主题前缀引常量（**展示值不变**；页脚年份同步动态化，2026 年内无可见差异）。
- S端 运行时覆盖：`site-config.json` 新增可选键 `brandName`（空串或缺省=回落构建期值，沿用现有三层优先级契约），改一个 JSON 重新上传即全站改名、无需重建前端。
- 红线（非目标）：构建/安装层命名一律不动——exe/bundle/DMG/安装目录/快捷方式/Finder 名保持「AI Novel」（改名属老用户数据目录错位的重大迁移，另行立项；S端 FAQ「右键 AI Novel」引用的正是 Finder 文件名，现状是对的）；「爱」字标取值不变；文档/原型 HTML 内的品牌串不治理；不新增防裸写 lint 门禁（二期）。

## Capabilities

### New Capabilities

- `brand-identity`: 品牌单一事实源与两端消费——brand.json 字段契约、派生组合规则（组合名/版权行）、C端（窗口标题/splash/字标/备份前缀，python 兜底纪律）、S端（标题/页脚/邮件前缀）。

### Modified Capabilities

- `site-config`: 已知字段白名单四→五（新增 `brandName`），字段级覆盖优先级与空串回落语义沿用既有契约，`brandName` 覆盖品牌显示名并可独立换发。

## Impact

- **C端**：`client/packaging/build/pywebview_app.py`（窗口标题+splash+PyInstaller datas 带入 brand.json，release.json 同机制）、`client/backend/`（新品牌桥 + `backup/export.py` 前缀 + FastAPI 内部 title 顺手参数化）、`client/frontend/`（vite.config、index.html、`src/lib/brand.ts` 新增、Navbar/LoginPage/LandingPage/StatusBar/RestoreModal 替换）。
- **S端**：`server/frontend/`（`src/constants/brand.ts` 新增、index.html、FooterSection、AuthPage、SupportPage、`src/lib/site-config.ts` 白名单、`public/site-config.json` 加键、main.ts 应用点）。
- **e2e**：S端 `landing.spec.ts:145`（页脚「爱小说 · AI Novel」）、`support.spec.ts:31`（主题含「爱小说·」）、`ui.spec.ts:11` 断言值均不变，预期零改动；C端 `statusbar.spec.ts:39` 现断言「© 2026 爱小说」，版权年份动态化后 MUST 同步改为年份无关断言（唯一需动的既有断言）。窗口标题在 e2e/DOM 快照测不到的 OS 层，用打包演练实跑验证（`--smoke` 不走 GUI 路径，仅证后端链路）。
- 无后端 API 契约变化、无数据库变化、无新增依赖。

## Design Impact

- **受影响端**：双端。
- **受影响屏/弹层**：C端 无 in-app 屏视觉变化（全部是同值字符串引常量）；变化发生在 parity 与 DOM 快照均测不到的三处——OS 窗口标题、启动 splash、index.html title。S端 页脚/标题展示值不变，仅改为引用常量。
- **对象状态**：无新增状态，不触状态语言总表。
- **两端共享段**：不触碰（base.css 令牌与组件类零改动，无需 cross 校验）。
- **原型先行**：免——改动不在原型/parity 覆盖层内，无 in-app 视觉差异。
- **设计工件**：实现侧自查；无新按钮词与提示条，窗口标题「爱小说」为品牌名词非操作词，符合 §13 口径。
