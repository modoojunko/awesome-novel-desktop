# Design: brand-name-single-source

## Context

品牌串现状（详见 proposal Why）：C端窗口标题/splash 为「AI Novel」，S端 四处手工品牌串，备份前缀「爱小说-」在 python 硬编码。两端已有可复用的单源机制先例：C端 `release.json` 经 PyInstaller datas 进包、`load_release_overrides` 运行时读取；S端 `site-config.json` 三层优先级运行时换发。仓库根 `brand/` 目录已是品牌资产（lockup SVG/icon/mark）的家。约束：C端 是离线桌面应用，品牌值必须在构建期可用；v0.15 教训——启动路径上任何资源缺失都不能炸。

## Goals / Non-Goals

**Goals:**

- 改一次 `brand/brand.json` + 重建，两端所有品牌消费点同值生效；S端 额外支持免重建运行时改名。
- 消灭源码里的品牌名展示裸串（构建层、docs、原型层除外）。
- C端 python/ts 双语言、S端 构建期/运行时双层，各自有且只有一个读取入口。

**Non-Goals:**

- 不改构建/安装层命名（exe/bundle/DMG/安装目录/快捷方式/Finder 名）——数据目录错位风险属重大迁移，另行立项。
- 不加防裸写 lint 门禁（二期可选）。
- 不治理 docs/、原型 HTML、README 内的品牌串。
- 不动 `server/app/main.py` FastAPI 内部 title（OpenAPI 文档非用户可见，S端 python 侧无品牌消费基建，为它单建不值）。
- 不做「窗口标题拼版本号」（version-placement 独立 change 的事，本 change 只保证标题=name）。

## Decisions

### D1: 单源放仓库根 `brand/brand.json`，不放各端常量文件

备选是两端各一个 constants 文件靠注释互指。否决理由：C端 消费方横跨 ts 与 python 两语言，常量文件方案在 python 侧仍需第二份声明，漂移点+1；`brand/` 目录已是品牌资产的物理家。json 由 vite 构建期 import（语法错=构建失败，挡在发布前）与 python 运行时读取（带兜底）共用。

### D2: 字段只放四个原子值，派生值代码拼

`name`/`nameEn`/`mark`/`tagline`。组合名 `full = name + " · " + nameEn` 与版权行 `© {year} {name}` 在各端桥接模块内拼装——派生值入 json 会让「改一次名」变成「改两个字段」，违背单源初衷。年份取渲染时当前年份，顺手修掉 StatusBar「© 2026」写死的潜伏 bug。

**三个故意不加的字段**：
- 不加 `productName`（构建层「AI Novel」）：声明了但没接线的事实是陷阱——改了不生效引人困惑，接线了则触发数据目录错位迁移。构建层迁移立项那天再加。
- 不加 `format_version` 契约头：brand.json 与读它的代码永远同构建同生灭（不同于要在野外独立存活的备份包），vite 构建期校验已足够。
- 不加窗口标题完整串：标题=name 本身；版本号拼接归 version-placement change。

### D3: C端 接线——构建期单点读取，双桥消费

- **ts 侧**：`src/lib/brand.ts` 直接 `import` brand.json（vite json import，`resolveJsonModule` 类型安全），导出 `BRAND` 对象与 `full`/`copyrightLine` 派生 getter。全部 UI 消费点（Navbar ×2、LoginPage、LandingPage、StatusBar、RestoreModal hint ×2）改引此文件。**实现期补充**：两端 docker 镜像的构建上下文只含各自 frontend 目录，仓库根 brand.json 进不了上下文——compose 为两前端服务加 `additional_contexts`（命名上下文 `brand`），Dockerfile 在 build stage `COPY --from=brand brand.json`（client-backend 服务同款，brand.py 同层命中），三镜像构建均实测通过。
- **index.html title**：vite.config.ts 读一次 brand.json，用 `transformIndexHtml` 注入 title（构建期替换，非 JS 运行时改），保证 JS 未执行前的首帧 title 也正确。组合式钉死为 `{nameEn} — {name}，{tagline}`，与现值逐字节一致。
- **python 侧**：`client/backend/brand.py` 新模块——定位顺序：`RESOURCE_ROOT` 环境变量（`start_server` 已算出 res_root 处 `setdefault` 注入）→ 模块同目录（docker 扁平布局命中）→ 与 `get_resource_root` 同款双候选探测（`sys._MEIPASS`、`_MEIPASS.parent/"Resources"`，覆盖 macOS .app 与 Windows onedir/onefile 三种布局）→ dev 仓库相对路径 → 内置默认常量。模块级只做受保护 I/O、永不抛异常——含定位函数本身（dev 分支对扁平布局祖先不足时静默跳过，docker `/app/brand.py` IndexError 已由新鲜栈实跑暴露并修复，回归测试钉死）。`pywebview_app.py` 窗口 `title=` 改读它；`backup/export.py` 两个文件名前缀改引它；`main.py` FastAPI title 顺手参数化（uvicorn 字符串加载上下文经 env 中转取值）。PyInstaller `build.spec`：datas 以 `(brand.json, ".")` 落资源根（release.json 同款），hiddenimports 加 `'brand'`（与 `'config'` 同款保险）。
- **splash**：`LOADING_HTML` 模块级常量改 `loading_html()` 工厂（f-string 注入桥值），调用点包 try/except 回落字面量默认值——与 brand.py 自身兜底构成双保险，吸收 v0.15 教训。注意 `--smoke` 不走 create_window/splash，窗口标题与 splash 的正确性由打包演练实跑验证（macOS 实跑 + Windows 人工验收）。

### D4: S端 接线——构建期常量 + 运行时覆盖双层

- **构建期**：`src/constants/brand.ts` import brand.json（与 C端 桥同构、各自独立），index.html 静态 title 改为构建期品牌值兜底；9 处存量品牌位改引常量：FooterSection 版权行、DashboardLayout 顶栏字标、AuthPage 页面 title 与页内字标、CashierPage 收银台字标、DownloadModal 弹窗标题、HeroSection 演示窗标题、SupportPage 邮件主题前缀。注意两端版权行派生式不同构：S端为 `© {year} {full}`，C端为 `© {year} {name}`——桥各配派生、勿混用（S端 误用 C端 式会挂 landing.spec 断言）。
- **运行时**：`site-config.ts` 白名单 KNOWN_KEYS 加 `brandName`（sanitize 机制白捡）；`main.ts` bootstrap 在 `loadSiteConfig()` 应用点把覆盖值写入品牌态，组合名/版权行以覆盖值重组，且覆盖非空时 SHALL 在 bootstrap 内同步改写 `document.title`（AuthPage 卸载恢复的 `DEFAULT_TITLE` 是挂载时捕获值，引导段不落 title 则覆盖值丢失）。空串/缺省=回落，语义与 apiBase/beianIcp 完全一致。

### D5: 备份产物名引常量但值冻结

「爱小说-备份-{日期}.zip」等命名是 backup-restore spec 冻结契约（L3 文件名自标识豁免）。本 change 只把前缀从裸串改为引品牌桥，产物字节零变化；RestoreModal 的两处 hint 文案同步引常量。**验收含逐字节对拍**：现有 `tests/test_backup_export.py:111` 的 startswith 断言升级为全等（`== f"爱小说-备份-{日期}.zip"`），而非仅新增断言。

## Risks / Trade-offs

- [PyInstaller datas 漏带 brand.json] → python 桥内置默认值兜底（与声明值一致，行为无害）；打包演练任务显式断言包内存在该文件。
- [vite json import 跨出 frontend root 的路径解析] → 本地构建以仓库根为工作区可达；docker 构建上下文边界经 compose `additional_contexts` 解决（见 D3 实现期补充），三镜像构建实测通过。
- [S端 index.html 静态 title 与运行时覆盖短暂不一致] → 既有 AuthPage 动态 title 同款时序，挂载前闪现构建期兜底值可接受；brandName 覆盖属极低频运维动作。
- [e2e 断言受文案牵连] → 盘点结论：`landing.spec.ts:145`（「爱小说 · AI Novel」）、`support.spec.ts:31`（「爱小说·」）、`ui.spec.ts:11` 断言值均不变，预期零改动；C端 `statusbar.spec.ts:39` 的「© 2026 爱小说」断言随年份动态化改为年份无关（2026 年内仍绿，2027 起不埋雷）。
- [`--smoke` 验证盲区] → smoke 不走 create_window/splash，仅证后端链路 import 不炸；窗口标题/splash 正确性由打包演练实跑覆盖（macOS 实跑 + Windows 人工验收）。
- [版权年份动态化改变既有展示] → 「© 2026」→「© {当前年份}」在 2026 年内展示值不变，无用户可见差异；属修潜伏 bug 非行为变更。

## Migration Plan

纯前端层+打包层改动，无数据迁移。发布顺序：合入 main 后随下一版 C端 包与 S端 前端部署自然带出；S端 如需先于发版改名，改线上 site-config.json 重传即可（本 change 上线前该键会被 sanitize 忽略，无害）。回滚 = revert 对应 PR。

## Open Questions

无——字段契约、接线方式、红线均已在评审中与用户对齐（brand.json 四字段、site-config 加 brandName、备份前缀顺手常量化三项拍板通过）。
