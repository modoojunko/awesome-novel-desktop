# Design: brand-owner-line

## Context

见 proposal.md「Why」。与实现直接相关的现状事实（实勘）：

- Windows 的「发布者」来自三层，修法互不相同：① exe 版本资源（属性页/任务管理器）＝打包时烘入，`build.spec` 此前**完全没有** `version` 元数据，故显示「未知」；② 「设置 → 应用」/卸载列表＝Inno `AppPublisher`，原值「AI Novel」；③ UAC 与 SmartScreen 弹窗＝只认 Authenticode 证书主体，元数据改不动（自签 `cert.pfx` 仅限先装证书的机器；证书主体只能是法定名称，网名上不了证书）。
- 口径漂移全景：法务四件套「经营者」、relicense-proprietary 已定稿的 `MyAppPublisher=星纬（海口）投资有限公司`、备案主体均为公司；主站页脚与 C端 状态条为品牌名；Windows 为缺失。`server/frontend/public/legal/*.html` 页脚已有「© 星纬（海口）投资有限公司 · 爱小说 awesome-novel.com」的在库先例。
- `brand/brand.json` 现为四原子字段；`client/backend/brand.py` 白名单逐键取值（`_KEYS` 锁四键），`tests/test_brand.py` 防漂移断言逐键比对——新增 json 键对 python 侧零影响（新增键无运行时消费点）。
- `installer.iss` 现为 UTF-8 无 BOM 且已含中文（快捷方式描述等），随 v0.23 及近期 PR 包一直正常编译。Inno Setup 6.3.0 changelog 原文：*“Added support for UTF-8 encoded files without a BOM for `.iss` script files…”* 且 *“Using a BOM in UTF-8 encoded files is not needed and not recommended since Inno Setup 6.3.0”*；7.0.2 起「`.iss` 含文件码页内非法字节」从静默 U+FFFD 改为**编译失败**。
- PyInstaller（6.22.3 实勘）加载版本文件走 `load_version_info_from_text_file`＝`decode`（容忍 BOM/PEP263 编码声明）＋`eval()`——**单表达式**，前导注释合法但不能含赋值语句；`EXE(version=…)` 非 Windows 平台仅告警不生效。真加载器依赖 `PyInstaller.compat.win32api`，本机（macOS）验证须打桩。
- C端 像素 parity 以原型为基线逐像素比对（阈值 0.2%），状态条在 list/book/model-config/preview 四基线内——文案变更必须原型同批，否则 design:check 红。
- e2e 断言现状：`statusbar.spec` 钉 `/© \d{4} 爱小说/`，`landing.spec` 钉页脚含「爱小说 · AI Novel」。

## Goals / Non-Goals

**Goals:**

- 经营主体名全仓单源（brand.json），双端版权行与 Windows 发布者全部派生或显式同步自它
- Windows exe 与安装器不再出现「发布者: 未知」/「AI Novel」主体口径；版本号与安装包同源
- 主站页脚与 C端 状态条版权行具备权利归属效力（法定主体名前置），顺手补《电商法》15 条的页脚主体公示位
- 原型与实现同批（parity 不红）、断言钉住主体名（改名强制同批）

**Non-Goals:**

- 不做 Authenticode 证书采购与签名接入（UAC/SmartScreen 的「未知发布者」在买到证书前依旧存在——已向用户单列拍板项）
- 不给主体名做 site-config 运行时覆盖（法定名称属备案信息类事实，改名须整体换发，与备案号同一换发点逻辑但走重建通道）
- 不动法务页（已是正确口径）、不动 index.html 的设计稿 meta 落款
- 不在 python 后端消费 `company`（无运行时消费点，白名单不扩，避免死代码）

## Decisions

- **D1 — 主体名进 brand.json 作第 5 原子字段**，而非独立 `company.json` 或两端各自常量。理由：与品牌同域（版权行＝主体＋品牌的组合展示）、两端桥与打包层都已在读这个文件；替代方案（独立文件）为一根字符串建第二声明处，违背 brand-name-single-source 既有收敛方向。
- **D2 — 版权行公式＝「© 年 主体 · 品牌」**（S端尾随组合名、C端尾随单名，保留既有「两端派生不同构」约定）。主体前置与法务页「公司 · 品牌」同构；替代方案「纯公司名」丢品牌识别、「纯品牌名」无权利归属效力，均否决。年份保持动态取（现契约），法务页无年份不冲突（法务件求稳定、营销页求新鲜）。
- **D3 — Windows 版本资源由 build.spec 在 win32 分支生成 `version_info.txt` 并传 `EXE(version=…)`**，而非提交静态版本文件：文件含动态版本号（`APP_VERSION` > `git describe` > `0.0.0`，tag 去 v、非法字符清洗成 `-`；数字版本位只取首个点分数字前缀并逐段 clamp 0–65535——哈希/PR 号等尾巴不进位；模板值一律 `!r` 生成合法字面量，值含引号/反斜杠不炸加载器 eval，字段读取过 `isinstance(str)` 门禁），静态文件必漂移。生成物 gitignore。缺 `company` 键 `SystemExit` 拒构建——「静默出未知发布者的包」正是本 change 要消灭的故障类。`CompanyName`/`LegalCopyright` 取 `company`，`ProductName`/`FileDescription` 顺带改从 json 取（同一次读取，消除既有字面量）；`InternalName`/`OriginalFilename` 维持 exe 文件名字面量（改名属多点位联动，不在本次）。版本资源用简中码页 `'080404b0'`＋`Translation [2052, 1200]`，与产品语言一致。
- **D4 — `installer.iss` 的 `AppPublisher` 用字面量**（文件内注释标注「唯一手写同步点」），不从 CI 以 `/DMyAppPublisher=…` 注入：中文经 Git Bash(MSYS2)→iscc 命令行传递有编码风险，且 `MyAppName` 已有字面量先例。换名成本＝json＋iss 两处同批（spec 场景已钉）；`client-package.yml` 增加「Assert installer publisher matches brand.json」步骤逐字比对两侧，漂移即红——字面量方案保留但不再裸奔人肉纪律。
- **D5 — `installer.iss` 保持 UTF-8 无 BOM**：6.3.0 官方 changelog 明文“not needed and not recommended”，7.0.2 的非法字节编译失败反而把编码错误从静默乱码变成硬失败（更好）。文件内加编码约束注释，防后续编辑器存成 ANSI。替代方案（补 BOM）被否——与官方推荐相悖且无收益。
- **D6 — 原型 6 处 © 行与实现同批改**（四个 parity 基线状态条＋backup-restore 旧版式 pagefoot＋home 落地页脚），`index.html` 的「© 爱小说 · 界面重设计 v2」为设计稿 meta 落款（非产品 UI）不改；条目入 ADJUSTMENTS.md。e2e 断言升级为字面量钉全名（宽松正则会放过主体名被悄悄去掉的回归）。
- **D7 — CI 的 PyInstaller 步骤注入 `APP_VERSION: ${{ github.ref_name }}`**：版本资源 FileVersion 与 iscc 安装包文件名版本同源（同 tag 去 v 清洗逻辑放 build.spec 单点）。

## Risks / Trade-offs

- **真实 Windows 渲染只能由 CI 证实**：本机 macOS 无法跑 PyInstaller Windows 构建与 Inno 编译；已用 6.22.3 真加载器（打桩 win32api）验证版本文件解析＋`toRaw()`，端到端结论挂靠下个触 `client/**` 的 PR 打包产物（任何编码/字段错误都会让该流水线红或产物属性页可查）。
- **parity 阈值余量**：状态条文案变长的像素增量与全图抗锯齿噪声同量级（阈值 0.2%）。实证：带新文案的 9 个 parity 场景全过；5 个失败经 diff 图归因为并行在途工作的中栏版式漂移（红块集中空态卡/工作台，状态条仅底噪）——该归因随在途 change 合并自然消解。
- **主体将来变更**是四点联动（brand.json → installer.iss → 两 e2e 断言 → 重建前端镜像），已全部写进对应文件注释与 spec 场景，靠断言强制同批。
- **老 brand.json（无 `company`）** 会使打包显式失败：仓库内文件恒有该键，仅影响脱离仓库的构造场景——拒绝服务优于静默出「未知发布者」的包。
- Windows 7 等老系统对简中码页版本资源的展示差异未测（目标系统 MinVersion 10.0+，无影响面）。
