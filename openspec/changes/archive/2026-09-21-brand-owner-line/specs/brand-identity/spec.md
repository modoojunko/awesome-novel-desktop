# brand-identity Delta

## MODIFIED Requirements

### Requirement: 品牌单一事实源

仓库根 `brand/brand.json` SHALL 为两端品牌名与经营主体的唯一声明处，字段契约固定为五个原子字段：`name`（中文主名，现值「爱小说」）、`nameEn`（英文名，现值「AI Novel」）、`mark`（印标单字，现值「爱」）、`tagline`（一句话描述）、`company`（经营主体/版权人/发布者的法定名称，现值「星纬（海口）投资有限公司」）。派生组合 SHALL 在消费端代码拼装、MUST NOT 存入 json：组合名 = `{name} · {nameEn}`；C端版权行 = `© {当前年份} {company} · {name}`；S端页脚版权行 = `© {当前年份} {company} · {组合名}`。`company` 是法定主体名，SHALL 与法务文件的经营者署名同口径，MUST NOT 参与 S端 运行时 `brandName` 覆盖（覆盖仅作用于 `name` 及其派生组合）。json MUST NOT 声明构建/安装层产品名（exe/bundle/DMG 名）——未接线的事实不进契约。除 brand.json 与各端唯一桥接文件外，两端源码 MUST NOT 存在硬编码品牌名或主体名展示串（豁免：构建/安装层命名、`installer.iss` 的 `AppPublisher` 字面量——安装器读不了 JSON，它是主体名的唯一手写同步点，必须与 json 同批修改、引用 Finder 文件名的 FAQ 文案、docs 与原型层）。

#### Scenario: 改名单点生效

- **WHEN** 仅修改 `brand/brand.json` 的 `name` 并重建双端
- **THEN** 两端全部品牌消费点（窗口标题、splash、页面 title、字标、版权行、备份前缀、页脚）展示新名，无需改动任何源码文件

#### Scenario: 派生值不落盘

- **WHEN** 任一端渲染组合名或版权行
- **THEN** 其值由 `name`/`nameEn`/`company`/当前年份在代码中拼装得出，brand.json 中不存在对应存储字段

#### Scenario: 经营主体单源且不受运行时覆盖

- **WHEN** 静态托管上传带非空 `brandName` 的 site-config.json（运行时覆盖生效）
- **THEN** 页脚版权行中的主体名保持 brand.json 声明值不变，仅品牌名部分被覆盖值重组

#### Scenario: 主体名唯一手写同步点

- **WHEN** 经营主体依法换名，仅修改 brand.json 的 `company` 与安装脚本的 `AppPublisher` 字面量（两处同批）
- **THEN** 双端版权行与 Windows 发布者展示新主体名，其余源码零改动

### Requirement: C端品牌消费与启动兜底

C端 SHALL 在以下位置消费品牌源：系统窗口标题（= `name`，替代现值「AI Novel」）；启动 splash 品牌名；`index.html` title（构建期注入，组合式钉死为 `{nameEn} — {name}，{tagline}`，展示值与现状逐字节一致）；顶栏/登录页/落地页字标（`mark` + `name`）；书架状态条版权行（`© {当前年份} {company} · {name}`，年份取当前年份）；备份与配置包产物文件名前缀（`{name}-备份-`、`{name}-备份-配置-`，展示值与 backup-restore 既有契约一致）。python 侧读取品牌源 MUST 带内置默认值兜底：brand.json 缺失或不可读时 SHALL 使用与声明值一致的内置默认继续启动，MUST NOT 因品牌文件问题崩溃、报错弹窗或阻塞启动（`company` 不参与 python 侧运行时消费，新增键不得影响既有白名单键位）。brand.json SHALL 随打包进入安装包（PyInstaller datas 机制，release.json 同路径）。

#### Scenario: 窗口标题与产品名一致

- **WHEN** 用户启动桌面应用查看系统窗口标题
- **THEN** 标题为「爱小说」，不再是「AI Novel」

#### Scenario: 品牌文件缺失兜底

- **WHEN** 安装包遗漏 brand.json 或文件损坏
- **THEN** 应用正常启动，窗口标题、字标、备份产物前缀均使用内置默认值（与声明值一致），无报错无阻塞

#### Scenario: 备份产物名维持契约

- **WHEN** 用户导出备份与配置包
- **THEN** 产物文件名仍为「爱小说-备份-{日期}.zip」「爱小说-备份-配置-{日期}.zip」，与现状逐字节一致

#### Scenario: 版权年份动态化

- **WHEN** 跨年度后用户查看书架状态条
- **THEN** 版权行显示当前年份（如 2027 年显示「© 2027 星纬（海口）投资有限公司 · 爱小说」），而非写死年份

### Requirement: S端品牌消费与运行时覆盖

S端 SHALL 在 9 处品牌位消费品牌源：页面 title（index.html 静态兜底）、页脚版权行（`© {当前年份} {company} · {组合名}`）、控制台顶栏字标、设备授权页 title 与页内字标、收银台字标、下载弹窗标题、落地页演示窗标题、客服邮件主题前缀。构建期取 brand.json；运行时 `site-config.json` 的 `brandName` 非空时覆盖 `name` 用于全部品牌位展示（组合名与版权行随之以覆盖值重组；`company` 为主体名 MUST NOT 被覆盖），覆盖生效时应用引导段 SHALL 同步改写 `document.title`。

#### Scenario: 页脚组合名

- **WHEN** 访客打开落地页查看页脚
- **THEN** 版权行显示「© {当前年份} 星纬（海口）投资有限公司 · 爱小说 · AI Novel」（主体 + 构建期 `name · nameEn` 组合；2026 年内展示值即为此形态）

#### Scenario: 运行时改名免重建

- **WHEN** 仅上传带非空 `brandName` 的 site-config.json 到静态托管，不重建前端
- **THEN** 用户下次打开站点，页面品牌名展示为覆盖值
