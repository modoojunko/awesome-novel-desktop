## ADDED Requirements

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

#### Scenario: 未装包点 AI
- **WHEN** 未登录或未装包用户点击任意 AI 功能
- **THEN** 呈现锁定卡（已登录失败态含「重新获取」出口），手写正文不受影响

#### Scenario: 旧客户端拒载新包
- **WHEN** 降级安装旧版 App 且已装包 min_client_version 高于 App 版本
- **THEN** loader 拒载并回落兼容上一版；无兼容版则锁定卡引导升级客户端

#### Scenario: 存量 e2e 零改动
- **WHEN** 开发/测试态（未开强制包模式）运行既有测试与 e2e
- **THEN** loader 直读包内目录，行为与拆包前逐字节一致

### Requirement: 安装包零提示词断言（硬切）

- C端 安装包产物 SHALL NOT 包含任何 `.prompt` 模板文件（拍板硬切，无双源过渡）；打包
  流水线（client-package.yml 与本地打包脚本） SHALL 以冒烟断言钉住「产物树无
  *.prompt」，断言失败即中止发布。
- 传输面 SHALL 复用 update_check 纪律：仅 https＋烘焙可信域＋DNS 拒非公网；manifest
  内出现的下载 URL 一律不采信，路径从已验基址派生。

#### Scenario: 打包冒烟拦截模板泄漏
- **WHEN** 打包产物意外包含 .prompt 文件
- **THEN** 冒烟断言失败、发布中止
