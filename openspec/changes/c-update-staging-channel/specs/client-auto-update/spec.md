## ADDED Requirements

### Requirement: 灰度渠道本地覆盖

C端 SHALL 支持数据目录下的可选渠道覆盖文件 `update-channel.yaml`（路径＝`DATA_ROOT/update-channel.yaml`；客户端对它**只读不写**；文件缺失时 MUST 完全保持生产行为，普通用户零感知）。文件形态：`channel: staging`（检测地址切灰度清单主/兜底两址）、`channel: prod`（显式回生产，等价删文件）、`update_url: <完整清单地址>`（自定义单候选，高级用法）；自定义清单内各平台包 URL MUST 与该候选域同源——信任域集合仅从候选地址推导，跨源平台包会在自动下载出站闸被拒绝（自动下载不启动，手动链照旧）。`channel` 与 `update_url` 同时存在时 `channel` MUST 优先。解析 MUST 容错：`utf-8-sig` 读取（BOM 不致命）、剥标量值两侧空白与全角/智能引号；解析失败、空文件、未知取值 MUST 一律回退生产候选链并留 warning 日志，MUST NOT 使更新检查失败或抛错。覆盖文件的优先级 MUST 高于环境变量与烘焙地址；信任域集合、更新说明页派生地址 MUST 随生效候选自动跟随；https＋公网解析出站闸 MUST 保持不变。检测载荷（GET /update-check）与手动检查响应（POST /update-check/refresh）SHALL 带 `channel` 字段（`prod`/`staging`/`custom`，仅反映覆盖文件，env 覆盖不改标签）；前端手动「检查更新」的结果提示在非生产渠道 MUST 附渠道后缀（〔灰度渠道〕/〔自定义渠道〕），使「开关未生效」可被当场识别。

#### Scenario: 无文件保持生产行为

- **WHEN** 数据目录不存在 `update-channel.yaml`
- **THEN** 候选地址、检测结果与历史行为完全一致，`channel` 字段为 `prod`

#### Scenario: staging 切换生效

- **WHEN** 覆盖文件写 `channel: staging` 且用户点「检查更新」
- **THEN** 真实外呼灰度清单地址（主域失败自动切兜底域），响应 `channel` 为 `staging`，结果提示附〔灰度渠道〕后缀

#### Scenario: 坏文件不炸不误导

- **WHEN** 覆盖文件为非法 YAML、全注释空文件或未知取值（如 `channel: beta`）
- **THEN** 回生产候选链并留 warning 日志，更新检查正常工作，`channel` 为 `prod`

#### Scenario: 覆盖文件压过环境变量

- **WHEN** 覆盖文件（`channel: staging`）与环境变量 `CLIENT_UPDATE_URL` 同时存在
- **THEN** 检测地址以覆盖文件为准（环境变量仅在无覆盖文件时生效）

#### Scenario: 信任域与派生地址跟随

- **WHEN** `channel: staging` 生效
- **THEN** 灰度清单两域进入信任域集合，更新说明页链接按灰度基址派生（`{基址}/v<VER>/notes.html`），下载地址仍为清单内版本化实物直链
