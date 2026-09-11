# site-config Delta

## MODIFIED Requirements

### Requirement: 字段级覆盖与优先级

配置 SHALL 只承认五个已知字段：`apiBase`、`beianIcp`、`beianPolice`、`beianPoliceLink`、`brandName`，均为可选字符串；未知字段 MUST 被忽略。生效优先级为字段级判断：运行时非空值 > 构建期环境变量烘焙值 > 内置安全默认（apiBase=`/api`、备案号为空、brandName 空=用构建期品牌值）。JSON 中某字段为空串或缺省 MUST 表示「回落到构建期值」而非清空。`apiBase` SHALL 复用既有基址规范化规则：裸域名自动补 `/api` 尾巴、已带自定义路径的原样保留、绝不出现 `/api/api`。`brandName` 非空时 SHALL 覆盖品牌显示名 `name`（组合名与版权行随之以覆盖值重组），仅影响品牌展示，MUST NOT 影响 API 基址与备案号等任何非品牌展示行为。

#### Scenario: 仅覆盖部分字段

- **WHEN** 配置文件只写了 `beianIcp`，未写 `apiBase`
- **THEN** 备案号按运行时值展示，API 基址仍为构建期烘焙值

#### Scenario: 裸域名自动补前缀

- **WHEN** 配置 `apiBase` 为 `https://www.example.com`
- **THEN** 实际请求基址为 `https://www.example.com/api`

#### Scenario: 已带路径原样保留

- **WHEN** 配置 `apiBase` 为 `https://www.example.com/api`
- **THEN** 实际请求基址保持 `https://www.example.com/api`，不重复追加

#### Scenario: brandName 空串回落

- **WHEN** 配置中 `brandName` 为空串或缺省
- **THEN** 页面品牌名使用构建期烘焙值（brand.json 声明值），行为与无此字段时代码一致

#### Scenario: brandName 覆盖展示名

- **WHEN** 配置 `brandName` 为非空值
- **THEN** 页面 title、页脚版权行等品牌展示位以该值作为显示名重组，API 基址与备案号展示不受影响

### Requirement: 配置可独立换发

在不重新构建前端的前提下，仅替换静态托管上的 `site-config.json` SHALL 即可使后续页面加载应用新配置（API 基址、备案号展示与品牌名展示随之生效）；浏览器 MUST NOT 因缓存读到过期配置（对该文件的读取按不使用本地缓存语义发起）。随构建发布的仓库内 `site-config.json` SHALL 承载当前生产真实值（`brandName` 留空=随包品牌值），使不经 CI 的本机部署同样自带正确配置。

#### Scenario: 免重建切换 API 基址

- **WHEN** 运维仅上传新的 `site-config.json`（新 `apiBase`）到静态托管根目录，不做任何前端构建
- **THEN** 用户下次打开站点后，页面 API 请求发往新基址

#### Scenario: 免重建切换品牌名

- **WHEN** 运维仅上传带非空 `brandName` 的 `site-config.json`，不做任何前端构建
- **THEN** 用户下次打开站点后，页面品牌展示名为新值

#### Scenario: 本机部署自带生产配置

- **WHEN** 从本机执行前端构建与部署（无 GitHub Secrets 参与）
- **THEN** 发布产物包含带生产真实值的 `site-config.json`，线上基址、备案号与品牌展示均正确
