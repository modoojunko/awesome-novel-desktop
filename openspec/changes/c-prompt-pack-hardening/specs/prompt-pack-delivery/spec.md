## MODIFIED Requirements

### Requirement: 提示词包获取与安装（C端）

- C端 SHALL 在登录成功后（及启动补偿/档位变化/手动触发）以静默后台同步获取对应档位的
  提示词包：查 CDN `latest.json` → 按 effective_tier 档位下载加密 bundle（free⊂standard
  ⊂pro⊂max 累积超集；free 包＝归档＋卷体检消费面）→ 向 S端 `/api/prompt-pack/key` 换
  内容密钥 → 本地解密安装；全过程 SHALL NOT 阻塞任何用户操作。
- 同步器 SHALL 执行七道校验，任一失败即拒装并保留已装版本：内置信任钥集合按
  signer_key_id 验 manifest 签名／latest↔manifest 自洽／bundle sha256＋size／key_id
  匹配／AEAD 解密／模板级 sha256＋文件名白名单＋分层标记／版本不低于本地高水位
  （高水位与 receipt 分开持久化）。
- `latest.json` 须载 `min_pack_version` 召回底线：候选版本或已装版本低于底线 SHALL 拒装
  并停用已装坏版（回落上一版或重新拉取）。
- 安装 SHALL 原子化（staging 校验全过后 rename，receipt 原子替换），保留上一版本目录
  作回滚位；**已装包完整性 SHALL 由同步器复核（每次同步，含启动/登录钩子与手动检查
  触发）**：据 receipt 哈希复核不通过（损坏/被改）时，同版本包 SHALL 走重下重装修复；
  修复不可得（CDN/S端 不可达或校验失败）时 SHALL 按失败矩阵静默沿用现态；包存储目录
  SHALL 跨客户端版本共享。
- 装包完成后 C端 SHALL 离线自持：S端 与 CDN 不可达 SHALL NOT 影响任何已装能力；内容密
  钥仅在安装时刻使用，SHALL NOT 落盘。
- 换钥 403 SHALL 按档位序降档重试一次（S端 为档位权威）；全失败 SHALL 静默沿用已装版本。
- **落盘形态 SHALL 为密文容器**：已装版本目录 SHALL NOT 含任何模板明文（含 `.prompt`
  文件或其他可直读形态）；模板明文 SHALL 仅存在于进程内存中。
- **本地包密钥 SHALL 由操作系统级密钥保护存储保管并绑定机器与用户账户**：密钥材料
  SHALL NOT 以明文或可跨机搬运的形式随包目录存放（Windows 用 DPAPI 用户作用域、
  macOS 用 Keychain，实现见 design）；把已装包目录整体复制到另一台机器或另一用户账户
  SHALL 无法解密。
- **迁移**：检测到旧版明文包目录时，C端 SHALL 就地加密转换以保住离线能力；转换失败
  SHALL 按「未装包」处理并走既有重下路径（不得退回明文可用态）。
- **卫生**：模板文本 SHALL NOT 出现在任何日志、异常信息、回执/收据文件或临时文件中
  （含系统临时目录）。

#### Scenario: 首启登录后静默装包
- **WHEN** 新装用户首次登录成功且网络可用
- **THEN** 后台完成下载/验签/换钥/解密/安装，无阻塞无打扰性提示；完成后 AI 能力可用

#### Scenario: 装包后 S端 宕机
- **WHEN** 已装包用户在 S端 不可达时使用任意 AI 功能
- **THEN** 功能照常可用（模板读本地已装版本，无必需网络请求）

#### Scenario: 篡改包拒装
- **WHEN** bundle 或 manifest 被篡改（任一校验道失败）
- **THEN** 拒装、清理 staging、沿用已装版本并记本地告警

#### Scenario: 旧版重放被挡
- **WHEN** 攻击者以签名合法的旧版本 latest/manifest 重放
- **THEN** 版本高水位闸门拒装（版本低于高水位）

#### Scenario: 档位变化重装
- **WHEN** 用户升级套餐（如 free→pro）后触发同步
- **THEN** 按 pro 档重装（累积超集直接换目录），MAX 能力随包就绪

#### Scenario: 包目录被拷到另一台机器
- **WHEN** 用户把 `prompt-pack` 目录整体复制到另一台机器（或另一用户账户）后启动客户端
- **THEN** 包不可解密 → 按「未装包」处理：联网时走重下重装；离线时呈现既有「写作能力未就绪」态，
  且 SHALL NOT 退回任何明文可用形式

#### Scenario: 存量明文包升级
- **WHEN** 旧版本（明文落盘）用户升级到本版本后首次启动，且网络不可用
- **THEN** 既有明文包就地加密转换后照常离线可用；转换失败则按未装包处理（联网重下）

### Requirement: 模板加载解析序（C端 loader）

- `prompts.load/load_layers` SHALL 按序解析：receipt 指向的已装版本目录 → 开发/测试态
  包内目录 → 两者皆缺抛带引导语义的 `PromptPackMissing`。
- loader SHALL 拒载不满足 `receipt.min_client_version` 的已装版本并回落上一版（防「旧
  App＋新包」占位符契约断裂）；无兼容版本按未装处理并引导升级客户端。
- `PromptPackMissing` SHALL 由消费模板的 AI 端点统一转为 503＋专用 reason（前端锁定卡
  「登录后获取写作能力」，出口＝去登录/重新获取/升级卡）；手写正文等非模板功能 SHALL
  NOT 受影响。
- 后端 `AI_STATES` 与前端 `AiState`/`BLOCK_TEXT` SHALL 同批扩展该 reason；前端 fetch 层
  503 预设白名单 SHALL 同批收录（防误弹无关全局提示）。
- **读取路径 SHALL 在内存中完成解密与校验**：loader 读已装版本时 SHALL NOT 生成任何中间
  明文文件（含系统临时目录）；读时哈希校验不通过 SHALL 按既有语义视为缺失并回落。

#### Scenario: 未装包点 AI
- **WHEN** 未登录或未装包用户点击任意 AI 功能
- **THEN** 呈现锁定卡（已登录失败态含「重新获取」出口），手写正文不受影响

#### Scenario: 旧客户端拒载新包
- **WHEN** 降级安装旧版 App 且已装包 min_client_version 高于 App 版本
- **THEN** loader 拒载并回落兼容上一版；无兼容版则锁定卡引导升级客户端

#### Scenario: 存量 e2e 零改动
- **WHEN** 开发/测试态（未开强制包模式）运行既有测试与 e2e
- **THEN** loader 直读包内目录，行为与拆包前逐字节一致

#### Scenario: 读模板不落明文
- **WHEN** 任一 AI 功能读取已装包模板并组装提示词
- **THEN** 磁盘上不出现新增的模板明文文件（读前后包目录内容零变化），模板文本不进日志

## ADDED Requirements

### Requirement: 本机提取防护强度与不承诺项

- 客户端的**拼装链路 SHALL 保持在本机**（不引入云拼装依赖）：装完离线自持的语义不变。
- 「本地包密钥的解封」与「容器解密」这两个关键步骤 SHALL NOT 以可被直接反编译读取的形态
  暴露（字节码里读不到密钥材料与解密参数）——手段可为关键路径原生化或等效强度措施，
  以实现为准；客户端代码可被读取 SHALL NOT 单独构成「拿到模板明文」的充分条件。
- 防护目标是**抬高提取成本至高于提示词本身价值**，下列情形**明确不承诺**（评估防护强度与
  设计评审时以此口径为准，不再逐次讨论）：
  1. 进程内存抓取（dump/hook/调试器）；
  2. 用户在自己机器上自建代理或补丁，抓取拼装后发往模型的请求内容；
  3. 具备专业逆向能力者针对原生模块的定向逆向。
- 本能力 SHALL NOT 改变既有对外契约：S端 换钥端点、CDN 发布格式、安装包零模板断言、
  `PromptPackMissing` 四态卡语义均不变。

#### Scenario: 反编译客户端拿不到明文
- **WHEN** 攻击者反编译客户端 Python 字节码并检索模板文本与包密钥材料
- **THEN** 既检索不到任何模板明文，也拿不到可直接用于解密包目录的密钥材料（关键路径不在字节码内）

#### Scenario: 防护强度评估口径
- **WHEN** 评审或验收提出「内存里能不能拿到」这类问题
- **THEN** 以本条款的「不承诺项」为口径回答，不据此判定实现不合格

#### Scenario: 拼装仍在本地
- **WHEN** 已装包用户离线写作并触发 AI
- **THEN** 提示词在本机组装完成，行为与加固前一致（无新增网络依赖）
