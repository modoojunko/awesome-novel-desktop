## MODIFIED Requirements

### Requirement: 模板加载解析序（C端 loader）

- `prompts.load/load_layers` SHALL 按序解析：receipt 指向的已装版本目录 → 开发/测试态
  模板目录 → 两者皆缺抛带引导语义的 `PromptPackMissing`。
- 开发/测试态模板目录 SHALL 由环境变量 `PROMPT_PACK_DEV_DIR` 显式指定（本地＝sibling
  提示词仓检出，见「提示词模板源与内容闸门归属」）；未设该变量时回退「包内目录」
  （`prompts/__init__.py` 同目录，兼容历史测试夹具；发布包内恒无该目录）。开发态模板源
  SHALL 允许携带纳管注释块（`## ` 行），loader 在分层/片段加载时 SHALL 剥除，SHALL NOT
  把注释行喂给模型。
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
- **THEN** loader 经 `PROMPT_PACK_DEV_DIR`（或回退包内目录）直读模板源，行为与拆包前逐字节一致（纳管注释行被剥除，不进提示词）

#### Scenario: 读模板不落明文
- **WHEN** 任一 AI 功能读取已装包模板并组装提示词
- **THEN** 磁盘上不出现新增的模板明文文件（读前后包目录内容零变化），模板文本不进日志

#### Scenario: 开发态经提示词检出加载
- **WHEN** 本地开发或容器栈以 `PROMPT_PACK_DEV_DIR` 指向 sibling 提示词仓检出（文件带纳管注释）
- **THEN** AI 功能正常取到模板且注释行不进入提示词；未指认且包内目录为空时按未装包 503 语义呈现

## ADDED Requirements

### Requirement: 提示词模板源与内容闸门归属

- 主库 SHALL NOT 跟踪任何 `.prompt` 模板文件——提示词唯一编辑源为私有仓
  awesome-novel-prompts 的 `prompts/`（单源；loader 代码与提示词包同步器不在此列）。
- 开发/测试态的模板来源 SHALL 为该仓的 sibling 检出：本地与 docker 开发栈以
  `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}` 只读挂载并以 `PROMPT_PACK_DEV_DIR`
  注入，本地 e2e 同批；SHALL NOT 以子模块或复制品形态在主库重新引入第二份模板。
- 模板内容闸门（分层协议、注释↔占位符对拍、正文断言）SHALL 住提示词仓 CI；主库 CI
  SHALL NOT 依赖提示词仓内容（不引入跨仓 token），`client/backend/prompts/` 相关回归以
  桩夹具覆盖 loader 行为。
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
