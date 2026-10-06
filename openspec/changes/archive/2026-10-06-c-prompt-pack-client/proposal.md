# Proposal: c-prompt-pack-client

## Why

提示词包分发链（已拍板 2026-10-05，四方评审收口版架构）的 C端 半：**安装包硬切不含
提示词**（拍板：无双源过渡），C端 登录后按权益档位（free/standard/pro/max 四档包，跟
契约 v2 feature key 走）从 CDN 拉加密包，向 S端（`awesome-novel-server` 仓
`s-prompt-pack-keys` change 的 `/api/prompt-pack/key`）换 CEK 解密安装本地，**装完离线
自持**（S端/CDN 挂了不影响写作）。免费包＝归档＋卷体检（免门禁豁免面的现状映射）；
trial＝pro 包；lifetime＝max（S端 侧归一化）。

S端 半在 awesome-novel-server#s-prompt-pack-keys；发布链（publish.py 四档构建＋
AES-GCM＋Ed25519＋tcb hosting＋latest.json v1 schema）在 awesome-novel-prompts 仓，
随本 change 实施窗口同批落地。

## What Changes

- **同步器**（新模块 `client/backend/prompt_pack/`）：四钩子（登录成功／启动补偿／
  entitlement 快照档位变化／设置页手动「检查写作能力」）；静默 daemon 线程；流程＝
  GET latest.json→闸门（min_client_version／已最新／**版本高水位防旧版重放**，高水位
  与 receipt 分开持久化防 clear-data 连带洗掉）→按 effective_tier 档位下载
  `v{N}/{tier}.bin`＋manifest→S端 换钥（403 按档降序重试一次）→**七道校验**（App 内置
  Ed25519 信任钥集合验签〔key_id→公钥映射，manifest 带 signer key_id〕／latest↔manifest
  自洽／bundle sha256＋size／key_id 匹配／AEAD 解密／模板级 sha256＋`_SAFE_NAME_RE`
  白名单＋分层标记／版本单调）→原子安装。
- **本地布局**：`{DATA_ROOT}/prompt-pack/`（**跨版本共享**——c-db-per-version 判例，不
  随每版库轮换）：receipt.json（version/tier/key_id/min_client_version/模板 sha256，
  tmp＋os.replace 原子写）＋v{N}/＋v{N-1} 回滚位＋.staging；读时校验 `(mtime_ns,size)`
  签名失效再 sha256；损坏自愈＝回滚上一版→清 receipt 重拉；清理失败 catch＋defer
  （Windows 句柄），永不删本进程启动时 receipt 指向版。
- **loader 改造**（`prompts/__init__.py` 唯一收敛点，调用方零改动）：receipt 版本目录
  （前置闸 `receipt.min_client_version > app_version()` **拒载**回落 v{N-1}——防「旧
  App＋新包」占位符契约断裂，评审 P0）→开发/测试态包内目录→`PromptPackMissing`。
  版本比较复用 `schema_version.is_newer`（不新造比较器）。
- **枚举同批扩**（D13 双端契约）：后端 `AI_STATES`＋前端 `AiState`＋`BLOCK_TEXT` 新
  reason；`api.ts` 503 预设白名单同批（防误弹「云端服务唤醒中」）。
- **UI（原型先行）**：锁定卡四态（未登录→去登录／获取中→行内 warn「正在准备写作
  能力…」／失败→重新获取〔复触发同步＋重放原请求〕／档位不够→升级卡）；用户可见名词
  统一「**写作能力**」（提示词包/pack/manifest/loader 按 §13 禁令不进 UI，词汇表两端
  同批登记）；AcctMenu 版本行加包版本＋最近同步＋一键复制诊断串（entitlement-sync 降级
  提示同款模式）；包状态挂 `/auth/verify` 本地响应（LicenseProvider 两跳刷新消费，零
  新增轮询；已知「在装」时 startBgWatch 式 1s 短轮询；不做 SSE）；MAX 行门控走
  useFeature（tier work 已 key 化，直接消费）。
- **打包断言反转（硬切）**：`build.spec` 摘除 prompts datas；`client-package.yml` 与
  `build_release.ps1` 冒烟断言「产物树无 *.prompt」。
- **e2e**：env 钩子强制包模式＋测试签名钥夹具＋假 CDN（httpx.MockTransport 不引新依赖）；
  最小场景组（首启无模板→锁定卡→装包→重试成功／同步失败→重新获取／min_client 静默／
  存量 202 条零改动回归）。
- **依赖**：`requirements.txt` 显式声明 `cryptography>=42`（Ed25519；现状仅经
  python-jose 传递引入——评审 P3）。

## Capabilities

### New Capabilities

- `prompt-pack-delivery`（C端 侧）：提示词包（注意＝`prompts/` 模板资产，非 `prompt/`
  章级提示词 DB 链路）的获取/校验/安装/加载解析序契约与「安装包零模板」断言；S端 签发
  契约在 awesome-novel-server#prompt-pack-key-issuance，两侧互引不重复。

### Modified Capabilities

- `entitlement-sync`：快照新增「包档位」语义（effective_tier 变化触发重同步）——实施
  时按实勘定 delta 深度。
- `tier-gating`：`BLOCK_TEXT`/`AiState` 枚举扩展（D13 同批）。

## Design Impact

C端 UI 新状态（锁定卡四态＋AcctMenu 一行）——**原型先行**：design-language §5 状态总
表加「写作能力」行＋prototypes/book.html 右栏锁定卡四态变体＋ADJUSTMENTS.md 登记；
design-vocab.mjs 新词两端同批；语气词 info/warn/err 内零新增档；不触两端共享段样式。

## 非目标

- S端 发钥（s-prompt-pack-keys）；publish.py 的 CDN 上传与发布顺序机制（prompts 仓，随
  实施窗口同批但独立交付）；「写作能力」之外任何功能门禁变化（tier work 已收口）。
- 双源过渡版（已拍板硬切，明确不做）。
