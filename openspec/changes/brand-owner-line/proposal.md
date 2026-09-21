# 版权行加经营主体（© 主体口径统一）

## Why

产品的版权与发布者口径目前散落且互不一致：法务四件套的经营者、EULA 署名（relicense-proprietary 已定稿）与备案主体都是「星纬（海口）投资有限公司」，但 S端 主站页脚是「© 2026 爱小说 · AI Novel」、C端 状态条是「© 2026 爱小说」、Windows 发布者字段此前完全缺失（exe 属性页显示「发布者: 未知」）。「爱小说」是产品名、「modoojunko」是开发者网名，都不是能主张权利的法律主体——版权行是权利归属声明，维权、软著署名、《电子商务法》第 15 条的经营者公示（s-payment-user-notices 已列为待补占位）以及将来的代码签名证书主体，全部只能落在法定主体名上。主体拍板为公司口径后，需要一次把全部展示面收拢到单一声明处。

## What Changes

- `brand/brand.json` 新增第 5 个原子字段 `company`（经营主体/版权人/发布者，现值「星纬（海口）投资有限公司」），成为该名称的全仓唯一声明处
- 两端版权行派生公式统一前置主体名：
  - S端 页脚 `brandCopyright()`：`© {年} {company} · {组合名}`
  - C端 状态条 `copyrightLine`：`© {年} {company} · {name}`
  - 主体名不参与 S端 运行时 `brandName` 覆盖（法定名称属备案信息类事实，改名须整体换发）
- Windows 发布者对齐同源：`build.spec` 读同一 `company` 键生成 Windows 版本资源（`CompanyName`/`LegalCopyright`=主体；`ProductName`/`FileDescription` 一并改从 json 取，缺 `company` 键拒绝构建）；`installer.iss` 的 `MyAppPublisher` 设为公司名（Inno 读不了 JSON 的唯一手写字面量副本，文件保持 UTF-8 无 BOM——Inno ≥6.3 官方推荐）
- C端 原型 6 处 © 行同步（list/book/model-config/preview 状态条、backup-restore 旧版 pagefoot、home 落地页脚），ADJUSTMENTS.md 登记；index.html 的设计稿 meta 落款不改
- e2e 断言升级为钉住主体名：`statusbar.spec`（C端）与 `landing.spec`（S端）
- 实现已随口径拍板预置在工作区（未提交），apply 阶段为门禁核对与提交

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `brand-identity`：「品牌单一事实源」的字段契约由四字段扩为五字段（新增 `company`），两条版权行派生公式前置主体名；「C端品牌消费与启动兜底」「S端品牌消费与运行时覆盖」中版权行的展示值随之更新，并明确主体名不受运行时 brandName 覆盖
- `installer-release`：新增「Windows 发布者元数据」Requirement——exe 版本资源与安装器 `AppPublisher` 必须署名经营主体，取值与 brand.json `company` 同源

## Impact

- 代码：`brand/brand.json`、`client/frontend/src/lib/brand.ts`、`server/frontend/src/constants/brand.ts`、`client/packaging/build/build.spec`、`client/packaging/build/installer.iss`、`.github/workflows/client-package.yml`（Build app 步骤注入 `APP_VERSION`，版本资源口径与安装包同源）、`.gitignore`（排除生成的 `version_info.txt`）
- 测试：`client/frontend/e2e/statusbar.spec.ts`、`server/frontend/e2e/tests/landing.spec.ts`
- 设计资产：`docs/design-c/prototypes/{list,book,model-config,preview,backup-restore,home}.html`、`ADJUSTMENTS.md`
- 兼容性：brand.py 白名单逐键取值，新增 json 键对其无影响（防漂移断言只锁原四键）；老 brand.json（无 `company`）会使 build.spec 显式失败——仓库内文件恒有该键，不构成发布风险
- 不触碰两端共享段（base.css 令牌与组件类零改动）；无 API/依赖变化

## Design Impact

- 受影响端：**双端**（C端 状态条＋S端 落地页页脚），另有打包层元数据（非界面）
- 受影响屏/弹层清单：C端 状态条常驻的全部应用态屏（书架/工作台/设定等，落地页 `/` 豁免不受影响）；S端 营销落地页页脚
- 对象状态：无新增交互状态——纯展示文案变化，不引入 notice/pill/toast，语气词表不涉及
- 两端共享段：不触碰（无 base.css 改动，`design-cross` 无需重跑）
- 原型先行：已先行——6 处原型 © 行与实现同批改齐，偏差与豁免（index.html meta 落款）已登记 ADJUSTMENTS.md「版权行加经营主体」节
- 设计工件：实现侧自查（文案变更，无版式/组件改动）；design:lint 已过，像素 parity 4 spec 已跑（9 过；5 个失败经 diff 图归因为并行在途工作的中栏版式漂移，状态条区域在本改动容差内）
