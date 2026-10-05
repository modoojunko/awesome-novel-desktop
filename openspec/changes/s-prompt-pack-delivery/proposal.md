# s-prompt-pack-delivery（C端 半）

> **拆仓与拆半注记（s-server-repo-split，2026-10-05）**：本 change 原为双端混合设计
> （S端 zip 直发＋不分档），经四方评审（架构/后端/前端/产品，2026-10-05）三处方向反转
> （分档已拍板 free/PRO/MAX、CDN＋CEK 取代 S端 直发、Ed25519 验签），现拆为两半：
> **S端 半**（发钥端点＋prompt_pack_keys 表＋pg_schema 三件套＋SENSITIVE_PATHS 登记）
> 在 `awesome-novel-server` 仓同名 change；本仓只做 C端 半。
> **Design freeze 门槛＝用户拍板 5 项产品决策**（免费包口径含卷体检/MAX v1 按 PRO 超集
> /trial 映射/lifetime→max/存量迁移双源过渡一个版本）——拍板前 tasks 实现段不动。

## Why

提示词模板（`client/backend/prompts/*.prompt`，61 个约 280KB）是产品核心资产，当前经
build.spec 明文打进安装包——解包即拷走。已拍板架构（2026-10-05）：**安装包不含提示词**；
C端 登录后按权益从 CDN 静态托管拉取加密分档包（free⊂PRO⊂MAX 累积超集），Ed25519 验签
＋S端 按档发内容密钥（CEK）＋本地解密安装，**装完离线自持**（S端/CDN 挂了不影响写作，
CEK 只在装包时刻用一次）。本仓实现 C端 拉包安装链与 loader 改造。

## What Changes

- **C端 同步器**（新模块）：登录成功＋启动补偿两钩子触发，静默后台线程——GET
  `latest.json`（CDN）→闸门（min_client_version／已最新／版本高水位防旧版重放）→按本地
  entitlement 档位下载 `{tier}.bin`＋manifest→S端 `POST /api/prompt-pack/key` 换 CEK
  （403 按档降档重试）→七道校验（App 内置 Ed25519 公钥验签／latest↔manifest 自洽／
  bundle sha256＋size／key_id 匹配／AEAD 解密／模板级 sha256＋名字白名单＋分层标记／
  版本单调）→原子安装（staging→rename→receipt 原子写，保留上一版回滚）。
- **loader 解析序改造**（`client/backend/prompts/__init__.py`，唯一收敛点，61 调用方不动）：
  receipt 指向版本目录→包内目录（仅开发/测试态）→`PromptPackMissing`（AI 链路统一兜
  「登录后获取写作能力」锁定卡，手写正文不受影响）。receipt 带 min_client_version，
  loader 拒载不兼容已装包（回落上一版）——防「旧 App＋新包」占位符契约断裂。
- **双端共享枚举同批扩**（D13 先例）：后端 `AI_STATES`＋前端 `AiState`＋`BLOCK_TEXT`
  新值；`api.ts` 503 预设白名单同步收录（防误弹「云端服务唤醒中」）。
- **打包断言反转**：build.spec 摘除 prompts datas；client-package.yml 与本地打包脚本
  冒烟断言新增「安装包内不存在 .prompt 文件」（存量迁移若走双源过渡版，断言反转随移除
  版本到位——待拍板 5）。
- **失败矩阵**（验收基线）：已装包时 CDN/S端 任一挂→照常用；未装→AI 锁定卡＋登录/重试
  出口；验签/解密失败→拒装用旧包＋本地告警；损坏读时发现→回滚上一版或清 receipt 自愈。

## Capabilities

### New Capabilities

- `prompt-pack-delivery`（C端 侧）：提示词包（注意：是 `prompts/` 模板资产，不是
  `prompt/` 章级提示词 DB 链路）的获取/校验/安装/加载解析序契约与「安装包零模板」断言。
  S端 发钥契约在 awesome-novel-server 仓立 spec，两侧互相引用不重复。

### Modified Capabilities

（待 design freeze 后按拍板定——如免费口径改动触及卷体检消费面，登记对应 spec delta。）

## Design Impact

C端 UI 新增状态：锁定卡四态（未登录→去登录／获取中→行内 warn／失败→重新获取／档位
不够→升级卡）。按硬性流程**原型先行**：§5 状态总表加行＋prototypes/book.html 右栏锁定卡
补状态变体＋ADJUSTMENTS.md 登记；用户可见名词统一「写作能力」（提示词包/pack/manifest/
loader 按 §13 禁令不进 UI）；不触两端共享段样式。

## Impact

- C端 后端：prompts loader、新 pack 同步模块（httpx 超时 6s 口径、update_check 式
  SSRF 防线：https＋烘焙域＋DNS 公网校验、manifest 内 URL 不采信路径从已验 base 派生）。
- C端 前端：锁定卡、AcctMenu 包版本行＋诊断串、`/auth/verify` 挂包状态（LicenseProvider
  两跳刷新消费，零新增轮询）。
- 打包链：build.spec／build_release.ps1／client-package.yml 冒烟断言。
- e2e：隔离栈假 CDN＋测试签名钥夹具；强制包模式 env 钩子（存量 205 条零改动回归）。
