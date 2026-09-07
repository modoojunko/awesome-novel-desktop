# Tasks: brand-name-single-source

## 1. 单源落盘与 C端 ts 桥

- [x] 1.1 新增 `brand/brand.json`（name=爱小说 / nameEn=AI Novel / mark=爱 / tagline=AI 辅助长篇小说写作），确认 JSON 合法（`python3 -m json.tool` 通过）
- [x] 1.2 新增 `client/frontend/src/lib/brand.ts`：import brand.json，导出 `BRAND` 与派生 `full`（`{name} · {nameEn}`）、`copyrightLine`（`© {当前年份} {name}`）；`npx tsc --noEmit` 过

## 2. C端 前端消费点替换（值不变的引常量）

- [x] 2.1 Navbar（2 处字标 `mark`+`name`）、LoginPage h1、LandingPage 字标改引 brand.ts，渲染值与改前一致
- [x] 2.2 StatusBar 版权行改 `copyrightLine`（2026 年内展示值不变，年份不再写死）；RestoreModal 两处 hint 改引 `name` 拼装；`e2e/statusbar.spec.ts:39` 的「© 2026 爱小说」断言同步改为年份无关（如 `© \d{4} 爱小说` 正则）
- [x] 2.3 vite.config.ts 读 brand.json 经 `transformIndexHtml` 注入 index.html title（组合式钉死 `{nameEn} — {name}，{tagline}`）；`npm run build` 产物 HTML title 与现值逐字节一致
- [x] 2.4 `npm run design:lint` 绿（未触共享段，无需 cross 校验）；本地 vitest 相关面通过

## 3. C端 python 桥与打包层

- [x] 3.1 新增 `client/backend/brand.py`：定位顺序 RESOURCE_ROOT env（start_server res_root 处 setdefault 注入）→ get_resource_root 同款双候选 → dev 仓库路径 → 内置默认；模块级只做受保护 I/O 永不抛；新增 dev pytest 断言内置默认值 == brand.json 声明值（防兜底漂移）；`venv python -c` 冒烟三种路径取值一致
- [x] 3.2 `pywebview_app.py`：create_window `title=` 改品牌桥取值（「AI Novel」→「爱小说」）；LOADING_HTML 改 `loading_html()` 工厂注入桥值、调用点 try/except 回落字面量；`--smoke` 通过（口径：仅证后端链路 import 不炸，GUI 正确性由 3.3 实跑覆盖）
- [x] 3.3 PyInstaller `build.spec`：datas 加 brand.json（落资源根 `"."`，release.json 同款）、hiddenimports 加 `'brand'`；打包演练 macOS 实跑断言包内含 brand.json 且窗口标题实测「爱小说」；Windows 窗口标题人工验收
- [x] 3.4 `backup/export.py` 两个产物名前缀改引 brand.py；现有 `tests/test_backup_export.py:111` startswith 断言升级为全等对拍（`爱小说-备份-{日期}.zip` 等，逐字节）；`main.py` FastAPI title 顺手参数化（经 RESOURCE_ROOT env 取值）

## 4. S端 构建期常量与消费点

- [ ] 4.1 新增 `server/frontend/src/constants/brand.ts`（import 同一 brand.json；派生 `full` 与 S端版权行 `© {当前年份} {full}`——注意与 C端 `© {年} {name}` 不同构，勿混用）；`vue-tsc --noEmit` 过
- [ ] 4.2 存量 9 处品牌位全量收编：index.html title、FooterSection 版权行（年份动态化）、DashboardLayout 顶栏字标、AuthPage document.title 与页内字标、CashierPage 收银台字标、DownloadModal 弹窗标题、HeroSection 演示窗标题、SupportPage 邮件主题前缀；渲染值与改前一致（2026 年内）

## 5. S端 运行时覆盖

- [x] 5.1 `site-config.ts` KNOWN_KEYS 加 `brandName`（sanitize 白名单自动生效）；`public/site-config.json` 加 `"brandName": ""` 空值键
- [x] 5.2 `main.ts` bootstrap 应用点接入 brandName 覆盖：覆盖 name 重组组合名/版权行，覆盖非空时在 bootstrap 内同步改写 `document.title`（保证 AuthPage 卸载恢复的 DEFAULT_TITLE 拿到覆盖值）；空值回落构建期值；单测覆盖 sanitize 与回落语义
- [x] 5.3 本地 e2e：`landing.spec`（页脚「爱小说 · AI Novel」）、`support.spec`（主题前缀）、`ui.spec` 全绿，断言零改动

## 6. 全量验证与收尾

- [x] 6.1 裸串清点：`rg "爱小说|AI Novel"` 于 client/frontend/src、client/backend、server/frontend/src 仅剩桥接文件与豁免层（Finder 文件名 FAQ 文案、注释）命中
- [ ] 6.2 C端 本机全量 e2e（docker 栈）通过；S端 e2e 全量通过；双端 `tsc`/`vue-tsc --noEmit` 过
- [x] 6.3 改名演练：临时改 brand.json 的 name → 按核对单逐项验证双端同值生效（OS 窗口标题 GUI 实跑、splash、双端 index.html title、双端字标、版权行、备份产物前缀、S端 9 处品牌位）→ 还原；演练期备份产物名临时偏离 backup-restore 冻结契约，演练产物不得用于备份兼容性结论、演练后立即还原
