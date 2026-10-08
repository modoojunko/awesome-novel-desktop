## Context

打包期 S端 地址族经 `release.json` 烘入安装包：workflow `Generate release.json` 步以 `vars.CLIENT_SERVER_API_BASE || 默认值` 注入 env，`release_json_generate.py` 落盘，PyInstaller datas 分发；运行时 `pywebview_app` 把 release.json 烘入值设为 env（恒胜），`auth_local` 的 `call_server_api` 以「主基址＋兜底基址」取值（`dict.fromkeys` 去重后逐个尝试）。该取值链的三个默认值源（workflow、`build_release.ps1`、spec 契约）自「S端 公开地址族」上线起就把主基址默认写成云托管直连域、兜底默认写成与主基址同值，而仓库 Variables 一直未配置——于是每个正式包的主/兜底实际是同一个直连 URL。

## Goals / Non-Goals

- Goals：未配置 Variables 时默认拓扑即正确（主＝自定义域名、兜底＝直连）；「同址＝无兜底」形态在构建期被判红且失败时点前移到生成步；守卫口径与运行时去重口径（归一化）一致；存量已发包行为不受影响（不带运行时迁移）。
- Non-Goals：不改运行时兜底切换链与重试语义；不动 `public_server_api`/`portal_url`/下载地址族；不给已发包做配置迁移（烘焙恒胜、手改回滚是既定契约，自救只能靠发版）；不改 `pywebview_app` 的 dev 占位（无 release.json 场景）。

## Decisions

- **默认值翻转而非只补 Variables**：Variables 已补（双保险），但 CI 默认值是「Variables 缺配」时的最后防线——保留直连域当默认会把事故形态留在仓里（fork PR、Variables 被误清都会复发）。两打包入口（workflow＋ps1）同批翻转，防三入口漂移判例（公钥默认值有先科）。
- **同址闸双闸而非单闸**：产物断言（`release_json_assert`）在 CI 里排在双平台打包之后——单靠它，同址形态要烧完全部计费分钟才红。生成侧 `generate()` 与产物侧共用同一道闸：生成步 ~2 分钟内失败，产物闸继续兜底手改产物的路径。
- **归一化单源零依赖复刻**：`call_server_api` 的去重对象是 `auth_local._normalize_server_api` 归一化后的基址（尾斜杠 rstrip＋裸域名补 `/api`）；守卫若比原始串，尾斜杠/裸域名变体直接绕过。scripts 层受「只 import 零依赖叶子」约束（Generate 步跑在 Install deps 之前），不能引 `auth_local`——故在 `release_json_assert` 落 `normalize_server_base` 纯函数（urlsplit 属 stdlib），生成/产物/测试三方共用，语义直测钉死与 `auth_local` 同口径。
- **规格入口＝`installer-release`**：release.json 烘焙契约（键集、默认值、冒烟断言）已在该 capability 的「release.json 烘焙版本与检测地址」requirement 内；默认值翻转＋新闸以 MODIFIED 收敛，不立新 capability。

## Risks / Trade-offs

- fork 构建默认改打上游自定义域名主基址（原为中性直连域）：两域名皆公开可达，开箱可用性质不变；fork 自建者显式配 Variables 即覆盖。
- 主基址换成自定义域名后，自定义域名本身的可用性成为主路径依赖：兜底（直连域）自动切换链已存在且本 change 保证其真实生效，正是该风险的缓解。
