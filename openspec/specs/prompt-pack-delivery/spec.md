# prompt-pack-delivery Specification

## Purpose

定义提示词包分发链的 **C端 侧**契约：安装包硬切不含 `.prompt` 模板（产物零模板断言），
登录后按权益档位从 CDN 拉取加密包（free⊂standard⊂pro⊂max 累积超集），经内置信任钥
验签、向 S端 换内容密钥、本地解密安装；装完离线自持（S端/CDN 不可达不影响已装能力）。
loader 与同步器、四态卡 UI、打包冒烟均为本 capability 的落点。S端 按档发钥契约见
awesome-novel-server 仓 prompt-pack-key-issuance；发布链（切包/加密/签名/上 CDN）见
awesome-novel-prompts 仓 publish.py。

## Requirements

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
  模板目录 → 两者皆缺抛带引导语义的 `PromptPackMissing`。
- 开发/测试态模板目录 SHALL 由环境变量 `PROMPT_PACK_DEV_DIR` 显式指定（本地＝sibling
  提示词仓检出，见「提示词模板源与内容闸门归属」）；未设该变量时回退「包内目录」
  （`prompts/__init__.py` 同目录，兼容历史测试夹具；发布包内恒无该目录）。开发态模板源
  SHALL 允许携带纳管注释块（`## ` 行），**loader SHALL 在一切读取路径（含不经
  `load_layers` 的直读调用）上剥除文件头注释块**，SHALL NOT 把注释行喂给模型。
- 模块状态判定 SHALL 与模板目录解析同源：开发/测试态来源可用时包状态 SHALL 判 ready，
  SHALL NOT 出现「四态卡未就绪而 AI 能力可用」的不一致。
- **发布态（frozen 打包应用）SHALL NOT 启用开发态模板目录跳**：用户自设
  `PROMPT_PACK_DEV_DIR` 亦不生效；发布态唯一来源仍为已装包，未装按既有 503 语义。
- loader SHALL 拒载不满足 `receipt.min_client_version` 的已装版本并回落上一版（防「旧
  App＋新包」占位符契约断裂）；无兼容版本按未装处理并引导升级客户端。
- `PromptPackMissing` SHALL 由消费模板的 AI 端点统一转为 503＋专用 reason（前端锁定卡
  「登录后获取写作能力」，出口＝去登录/重新获取/升级卡）；手写正文等非模板功能 SHALL
  NOT 受影响。开发/测试态既无已装包、开发态模板目录也不可用时，SHALL 走同一 503 语义
  （不新增第二形态）。
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
- **THEN** loader 经 `PROMPT_PACK_DEV_DIR`（或回退包内目录）直读模板源，行为与拆包前逐字节一致（纳管注释行在一切读取路径上被剥除，不进提示词）

#### Scenario: 读模板不落明文
- **WHEN** 任一 AI 功能读取已装包模板并组装提示词
- **THEN** 磁盘上不出现新增的模板明文文件（读前后包目录内容零变化），模板文本不进日志

#### Scenario: 开发态经提示词检出加载
- **WHEN** 本地开发或容器栈以 `PROMPT_PACK_DEV_DIR` 指向 sibling 提示词仓检出（文件带纳管注释）
- **THEN** AI 功能正常取到模板且注释行不进入提示词，包状态判 ready（不呈现未就绪卡）；未指认且包内目录为空时按未装包 503 语义呈现

#### Scenario: 发布态不启开发跳
- **WHEN** 打包应用（frozen）运行且环境被设置 `PROMPT_PACK_DEV_DIR` 指向含模板的目录
- **THEN** 该跳不生效：未装包按既有 503 语义呈现；已装包按已装版本加载，不读明文目录

### Requirement: 安装包零提示词断言（硬切）

- C端 安装包产物 SHALL NOT 包含任何 `.prompt` 模板文件（拍板硬切，无双源过渡）；打包
  流水线（client-package.yml 与本地打包脚本） SHALL 以冒烟断言钉住「产物树无
  *.prompt」，断言失败即中止发布。
- 传输面 SHALL 复用 update_check 纪律：仅 https＋烘焙可信域＋DNS 拒非公网；manifest
  内出现的下载 URL 一律不采信，路径从已验基址派生。

#### Scenario: 打包冒烟拦截模板泄漏
- **WHEN** 打包产物意外包含 .prompt 文件
- **THEN** 冒烟断言失败、发布中止

### Requirement: 验签公钥随包烘焙与校验（发布链）

- 发布构建 SHALL 在 `release.json` 烘入**必选键** `pack_pubkeys`：内容为
  `{"<signer_key_id>": "<base64(32 字节 Ed25519 公钥)>"}` 的 JSON 字符串（与
  release.json 各键统一为字符串值的既有形态一致）。签名私钥 SHALL NOT 出现在任何
  仓库、产物或构建日志中；仅公钥随包分发。
- 生成期（`release_json_generate`）SHALL 硬要求 `RELEASE_PACK_PUBKEYS` env 并做形态
  校验：缺失或形态非法即构建失败，SHALL NOT 产出缺键/坏键产物。
- 产物侧冒烟断言（`release_json_assert`）SHALL 将 `pack_pubkeys` 列为必选键并严格
  校验：合法 JSON 映射／非空／每个值合法 base64／恰 32 字节；任一不满足断言失败、
  流水线转红。形态校验实现 SHALL 单源（生成侧与产物侧复用同一实现）。
- 打包应用启动后端时 SHALL 经 release.json 注入 `CLIENT_PACK_PUBKEYS`（键名与同步器
  读取一致）；release.json 缺该键（如本地直打）时 SHALL 回落生产发布公钥常量——
  SHALL NOT 以空钥集运行（空钥集＝恒拒装）。
- 三条打包路径（CI workflow 内联兜底 / Windows 本地 ps1 默认 / pywebview 常量）
  的默认公钥 SHALL 逐字一致，且 SHALL 由测试钉死（漂移＝某条路径烘出验不了包的钥）。
- 轮换签名钥 SHALL 支持多 kid 并存：`pack_pubkeys` 允许同时携带新旧公钥；新包用新
  kid 签发、旧包按已装版本继续可验——SHALL NOT 一对一替换式轮换（会致已装包验签
  失败）。

#### Scenario: 发布构建烘入公钥
- **WHEN** tag／PR 构建执行 `release.json` 生成步骤
- **THEN** 产物内 `pack_pubkeys` 存在且为合法 `{kid: base64(32B Ed25519)}` 映射，
  冒烟断言通过

#### Scenario: 缺烘或坏形态在构建期拦截
- **WHEN** 生成期缺 `RELEASE_PACK_PUBKEYS` env，或产物的 `pack_pubkeys` 为空/非 JSON/
  非映射/坏 base64/非 32 字节
- **THEN** 生成或冒烟断言失败、流水线转红，坏产物 SHALL NOT 发布

#### Scenario: 运行时注入与回落
- **WHEN** 打包应用启动后端
- **THEN** `CLIENT_PACK_PUBKEYS` 等于 release.json 的 `pack_pubkeys` 值；release.json
  缺该键时等于生产发布公钥常量（恒非空）

#### Scenario: 跨入口默认一致
- **WHEN** 检查三条打包路径的默认公钥
- **THEN** 三者逐字一致且形态合法（测试守卫；漂移即红）

#### Scenario: 多 kid 轮换不破已装包
- **WHEN** 发布方轮换签名钥并在 `pack_pubkeys` 中同时保留新旧公钥
- **THEN** 旧版本已装包继续可验（按旧 kid），新包按新 kid 验签，用户无感

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

### Requirement: 提示词模板源与内容闸门归属

- 主库 SHALL NOT 跟踪任何 `.prompt` 模板文件——提示词唯一编辑源为私有仓
  awesome-novel-prompts 的 `prompts/`（单源；loader 代码与提示词包同步器不在此列）。
- 开发/测试态的模板来源 SHALL 为该仓的 sibling 检出：本地与 docker 开发栈以
  `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}` 只读挂载并以 `PROMPT_PACK_DEV_DIR`
  注入，本地 e2e 同批；SHALL NOT 以子模块或复制品形态在主库重新引入第二份模板。
- 模板内容闸门（分层协议、注释↔占位符对拍、正文断言）SHALL 住提示词仓 CI；主库 CI
  SHALL NOT 依赖提示词仓内容（不引入跨仓 token），`client/backend/prompts/` 相关回归以
  桩夹具覆盖 loader 行为。
- 提示词仓 SHALL 以「元数据单源渲染注释头＋正文可直改」维护模板：注释头由生成器幂等
  重渲染、对拍校验元数据↔正文，SHALL NOT 让注释与元数据形成两份可各自漂移的文本。
- 发布链 SHALL 保持既有契约不变（安装包零 `.prompt` 断言、CDN 包格式、验签与换钥、
  `prompt_pack` 同步器七道校验）；提示词仓 `publish.py` 以其本仓 `prompts/` 为输入。

#### Scenario: 主库零模板
- **WHEN** 检查主库检出与打包产物
- **THEN** 不存在任何 `.prompt` 模板文件（loader 与同步器代码除外）；新增模板只落提示词仓

#### Scenario: 开发栈经 sibling 取模板
- **WHEN** 本地 `docker compose` 起 client-backend 且 sibling 提示词检出在位
- **THEN** AI 端点取到模板（注释剥除）且不依赖任何网络包；检出不在位时呈现既有未装包语义

#### Scenario: 内容闸门随源走
- **WHEN** 修改提示词仓任一模板（占位符或分层标记）不合规
- **THEN** 提示词仓 CI 闸门拦截；主库 CI 不因模板内容变化而红
