# model-api-config Specification

## Purpose

模型配置屏的接口格式能力：让每条 API 配置显式声明 OpenAI 或 Anthropic 接口格式，系统按该格式调用大模型、探测连接，并保证存量配置与备份包平滑兼容。

## Requirements

### Requirement: 接口格式为配置的一级字段

每条模型配置 SHALL 持久化一个接口格式字段 `api_format`，取值仅为 `openai` 或 `anthropic`，默认 `openai`。接口格式与供应商正交：同一供应商的配置可分别声明两种格式。

#### Scenario: 新建配置默认 OpenAI 格式
- **WHEN** 用户添加配置且未显式选择接口格式
- **THEN** 该配置保存后 `api_format` 为 `openai`

#### Scenario: 厂商锁定矩阵
- **WHEN** 用户在添加弹窗选择 OpenAI、Anthropic 或 Ollama 供应商
- **THEN** 接口格式控件呈置灰锁定态，分别固定为 OpenAI 格式、Anthropic 格式、OpenAI 格式，不可切换
- **WHEN** 用户选择 GLM、Kimi、DeepSeek、Qwen 或 OpenAI 兼容供应商
- **THEN** 接口格式控件可在 OpenAI 格式 / Anthropic 格式间切换

### Requirement: Base URL 不自动预填

选择供应商或切换接口格式 SHALL NOT 改动 Base URL 输入框的内容，且界面 SHALL NOT 提供任何接口地址引导文案（含厂商双地址小字与点击填入）；用户照抄厂商文档自填，placeholder 随格式给示例域名。

#### Scenario: 选供应商与切格式不动 URL
- **WHEN** 用户先选某供应商、再切换接口格式
- **THEN** Base URL 输入框内容保持不变（含为空），仅 placeholder 随格式给出示例域名

### Requirement: 编辑态可改接口格式

编辑已有配置时供应商保持锁定，接口格式 SHALL 允许修改且不弹二次确认；修改后该配置已拉取的模型列表与最近测试结果 SHALL 立即失效，需重新测试。

#### Scenario: 改格式后模型缓存失效
- **WHEN** 用户编辑一条已有模型列表的配置并切换接口格式后保存
- **THEN** 该配置的模型列表与测试状态被清空，配置卡提示需重新测试

### Requirement: 按接口格式调用大模型

大模型调用 SHALL 依据配置的 `api_format` 选择对应契约：`openai` 走 chat/completions 报文，`anthropic` 走 Anthropic messages 报文。显式 `api_format` SHALL 优先于任何基于 URL 字符串的格式推断；仅当配置无格式信息（旧数据回退路径）时才按「URL 含 anthropic 即 anthropic」推断。

#### Scenario: 显式格式压过 URL 猜测
- **WHEN** 一条 `api_format=anthropic` 的配置，其 base_url 不含 "anthropic" 字样
- **THEN** 调用走 Anthropic messages 契约且正常收到回复
- **WHEN** 一条 `api_format=openai` 的配置，其 base_url 含 "anthropic" 字样
- **THEN** 调用走 OpenAI chat/completions 契约

#### Scenario: 两种格式全链路可用
- **WHEN** 分别以 GLM 的 OpenAI 格式地址与 Anthropic 格式地址（`https://open.bigmodel.cn/api/anthropic`）各建一条配置并触发生成
- **THEN** 非流式与流式生成均正常返回，token 用量正常计入

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models` + Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。anthropic 格式下 models 端点返回 404 时 SHALL 自动降级为一条 max_tokens=1 的最小请求验证鉴权，成功即报连接正常。

#### Scenario: Anthropic 格式探测用户地址
- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: models 端点缺失时降级探活
- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发最小验证请求，鉴权通过即报「连接正常」且不报错误

### Requirement: 存量配置迁移等价

本地库升级 SHALL 幂等新增接口格式字段并回填存量行：base_url 含 "anthropic" 或供应商为 anthropic 的配置回填为 `anthropic`，其余为 `openai`，与升级前的运行时格式推断严格等价；重复启动 SHALL NOT 重复迁移或改变结果。

#### Scenario: 升级零行为变化
- **WHEN** 存量用户升级到新版并照常使用任一旧配置生成
- **THEN** 走的接口格式与升级前一致

### Requirement: 备份包接口格式前向兼容

配置包导出 SHALL 在每条 api_config 中包含 `api_format` 键（加键兼容契约内，不升 format_version）；导入 SHALL 接受缺失该键的旧包并默认 `openai`，接受含该键的新包并逐条还原。

#### Scenario: 新旧包互导
- **WHEN** 新版导出的配置包导入新版，或旧版导出（无 api_format 键）的配置包导入新版
- **THEN** 前者接口格式逐条一致还原，后者全部落 `openai` 且不报错

### Requirement: 配置域请求失败语义统一

模型配置域的请求（配置列表、连接探测、模型候选、用量统计、切换历史、设备激活）SHALL 经统一请求出口发起，失败时呈现与其他域一致的可读语义：认证失效回登录页、服务不可用给统一提示、会员门控给出升级出口；SHALL NOT 把原始状态码（如「HTTP 401」「HTTP 503」）直接呈现给用户。

#### Scenario: 配置列表失败不露原始状态码

- **WHEN** 配置列表请求失败（服务不可用）
- **THEN** 呈现统一的服务不可用提示与重试出口，不出现「HTTP 503」

#### Scenario: 模型就绪态失败可见

- **WHEN** 模型状态探测失败（非 ok 响应或网络错误）
- **THEN** 就绪态呈现失败/未知语义（不静默停留在旧值），并提供重试入口

#### Scenario: 会员门控出口

- **WHEN** 配置域请求收到会员门控拒绝（member_required）
- **THEN** 呈现升级引导出口，与主栈口径一致

### Requirement: Key 静态加密与钥匙同库自包含

- API Key 静态加密的 Fernet 钥匙 SHALL 存储**在数据库内**（应用级元数据 KV 表的一行）；**稳态运行** SHALL NOT 依赖数据目录中的独立钥匙文件（仅首启迁移期一次性读取，见下）。库（含钥匙行）SHALL 成为自包含单元——凡库整体移动/备份/恢复之处，钥匙随行，密文保持可解。
- 钥匙生命周期 SHALL 与库绑定：不存在钥匙行时，启动期 SHALL 按以下顺序初始化——①若数据目录存在旧钥匙文件且内容**合法**（可通过 Fernet 构造校验），SHALL 将其内容**原样**迁入库（零重加密，存量密文保持可解，迁移对用户无感）；②文件不存在或内容**非法**（空/截断/非 Fernet 格式）时 SHALL 生成新钥匙入库并记 warning（非法文件原样保留不删，库内既有密文按「密文无法解密」引导重填）。迁移成功后旧文件 SHALL **保留**（退役为只读遗留，不再参与任何逻辑）——同机新旧版本混跑/回滚时旧版读文件、新版读库行，两者内容一致，密文保持可解。
- 启动期钥匙初始化 SHALL 在数据库结构就绪（建表/补列/指纹戳）之后、任何需要加解密的启动步骤（含 `config.json`→User、User→ApiConfig 迁移中的 Key 加密）与任何 AI 加解密调用之前完成；并发首启同时写入钥匙行时 SHALL 以「先落库者胜、后到者重读装载」消解（迁移来源相同则内容一致，零分叉）；初始化失败 SHALL 快速失败（明确报错），SHALL NOT 静默退化为「全部密文不可解」且无提示。
- **安全取舍 SHALL 显式化**：钥匙入库后「库文件单独流出时 Key 不可读」的保护视为放弃（db 流出即钥匙流出；现状钥匙文件与库同目录，该保护本已名存实亡）。备份链路行为不变：导出包内 Key 保持明文、导入时以本地钥匙重加密，包内既无密文也无钥匙材料（包内 `api_key` 本身为明文，既有行为）。
- 密文无法解密（钥匙更换/丢失致旧密文成死文） SHALL 属可恢复状态：设置页重新保存 Key 即以当前钥匙重加密，**无需删除配置或重建绑定**。
- **库间迁入链路的死文提示**：通过库迁移/恢复端点把旧库数据（含 `api_configs` 密文列）迁入当前库时，SHALL 在迁入报告中对「按当前钥匙不可解」的密文配置给出明确提示（需重填）；该状态的运行期表现由「密文无法解密」的 503 引导承接。

#### Scenario: 旧钥匙文件存在时迁移零感

- Given 库内无钥匙行，数据目录存在旧 `.fernet_key` 文件（内容合法），且库内有以该钥匙加密的 `enc:` 密文
- When 应用启动完成
- Then 钥匙行内容等于旧文件内容，存量配置的 Key 保持可解（用户无需重填）；旧文件保留且内容不变

#### Scenario: 旧钥匙文件非法时按不存在处理

- Given 库内无钥匙行，数据目录存在 `.fernet_key` 文件但内容为空或截断（Fernet 构造失败）
- When 应用启动完成
- Then 生成新钥匙入库（记 warning），非法文件原样保留；库内既有 `enc:` 密文按「密文无法解密」引导重填，SHALL NOT 因非法钥匙内容在加解密时抛未处理异常

#### Scenario: 旧钥匙文件不存在时生成新钥匙

- Given 库内无钥匙行，数据目录不存在旧钥匙文件
- When 应用启动完成
- Then 生成新钥匙入库；库内既有 `enc:` 密文解不开，相关配置按「密文无法解密」引导重填（不 500）

#### Scenario: 库整体迁移带钥匙

- Given 应用已初始化钥匙行的数据目录
- When 将该数据目录的库文件整体移动到另一环境并启动
- Then 钥匙随库行生效，库内全部密文保持可解（SHALL NOT 再出现「库在钥匙丢」的死文状态）

#### Scenario: 库间迁入带死文密文时报告提示

- Given 新库（新钥匙或文件不在生成的钥匙）通过库迁移端点迁入旧库数据，旧库 `api_configs` 含旧钥匙加密的密文（迁移引擎按表搬运 `api_configs`，`app_meta` 不随行）
- When 迁入完成
- Then 迁入报告 SHALL 提示「N 条配置的 Key 按当前钥匙不可解，迁入后需重填」；运行期这些配置按「密文无法解密」引导（503 `no_key`），SHALL NOT 500

#### Scenario: 备份包不含钥匙材料

- Given 用户导出备份包并导入另一台库（钥匙行不同）的实例
- When 导入完成
- Then 导入的配置 Key 以本地钥匙重加密后可用（既有明文导出/重加密导入行为不变，包内 `api_key` 本身为明文），备份包内不存在钥匙材料
