## ADDED Requirements

### Requirement: 提示词包获取与安装（C端）

- C端 SHALL 在登录成功后（及启动补偿/档位变化/手动触发）以静默后台同步获取对应档位的
  提示词包：查 CDN `latest.json` → 按 entitlement 档位下载加密 bundle → 向 S端
  `/api/prompt-pack/key` 换内容密钥 → 本地解密安装；全过程 SHALL NOT 阻塞任何用户操作。
- 同步器 SHALL 执行七道校验，任一失败即拒装并保留已装版本：App 内置 Ed25519 公钥验
  manifest 签名／latest↔manifest 自洽／bundle sha256＋size／key_id 匹配／AEAD 解密／
  模板级 sha256＋文件名白名单＋分层标记／版本不低于本地高水位。
- 安装 SHALL 原子化（staging 校验全过后 rename，receipt 临时文件＋原子替换），并保留
  上一版本目录作为回滚位；已装包读时校验失败 SHALL 回滚上一版，无可用上一版 SHALL 清
  receipt 回到未装态并允许重拉。
- 装包完成后 C端 SHALL 离线自持：S端 与 CDN 不可达 SHALL NOT 影响任何已装能力；内容
  密钥仅在安装时刻使用一次，SHALL NOT 落盘。
- 换钥 403（档位不足）SHALL 按档位序降档重试一次；全部失败 SHALL 静默沿用已装版本。

#### Scenario: 首启登录后静默装包
- **WHEN** 新装用户首次登录成功且网络可用
- **THEN** 后台完成下载/验签/换钥/解密/安装，无任何阻塞或打扰性提示；完成后 AI 能力可用

#### Scenario: 装包后 S端 宕机
- **WHEN** 已装包用户在 S端 不可达时使用任意 AI 功能
- **THEN** 功能照常可用（模板读本地已装版本，不发起任何必需的网络请求）

#### Scenario: 篡改包拒装
- **WHEN** 下载的 bundle 或 manifest 被篡改（任一校验道失败）
- **THEN** 拒绝安装、清理 staging、沿用已装版本，并记录本地告警日志

### Requirement: 模板加载解析序（C端 loader）

- `prompts.load/load_layers` SHALL 按序解析：receipt 指向的已装版本目录 → 开发/测试态
  的包内目录 → 两者皆缺抛带引导语义的 `PromptPackMissing`。
- loader SHALL 拒载不满足 `receipt.min_client_version` 的已装版本并回落上一版（防
  「旧 App＋新包」占位符契约断裂）；无兼容版本时按未装处理。
- `PromptPackMissing` SHALL 由消费模板的 AI 端点统一转为 503＋专用 reason（前端锁定卡
  「登录后获取写作能力」）；手写正文等非模板功能 SHALL NOT 受影响。
- 后端 `AI_STATES` 与前端 `AiState`/`BLOCK_TEXT` 枚举 SHALL 同批扩展新 reason；前端
  fetch 层 503 预设白名单 SHALL 同批收录（防误弹无关全局提示）。

#### Scenario: 未装包点 AI
- **WHEN** 未登录或未装包用户点击任意 AI 功能
- **THEN** 呈现「登录后获取写作能力」锁定卡（出口=去登录/重新获取），手写正文不受影响

#### Scenario: 旧客户端装新包拒载
- **WHEN** 用户降级安装旧版 App 且本地已装包的 min_client_version 高于 App 版本
- **THEN** loader 拒载该包并回落兼容的上一版；无兼容版则锁定卡引导升级客户端

### Requirement: 安装包零提示词断言

- C端 安装包产物 SHALL NOT 包含任何 `.prompt` 模板文件；打包流水线（client-package.yml
  与本地打包脚本） SHALL 以冒烟断言钉住「产物树无 *.prompt」（双源过渡期断言随移除版
  到位）。
- 包存储目录 SHALL 跨客户端版本共享（SHALL NOT 随每版独立库文件轮换）。

#### Scenario: 打包冒烟拦截模板泄漏
- **WHEN** 打包产物中意外包含 .prompt 文件
- **THEN** 冒烟断言失败、发布流程中止
