# Design: c-prompt-pack-client

> 双钥匙信任模型（签名钥集合防伪＋CEK 控权益）与全链时序沿用 2026-10-05 定稿设计；
> 本文件只记 C端 实现决策，评审 P0/P1 修正全部内化。

## D1 本地布局与安装原子性

```
{DATA_ROOT}/prompt-pack/          ← 跨版本共享（c-db-per-version 判例：库每版独立，包不能跟）
  receipt.json    {version, tier, key_id, min_client_version, installed_at,
  │                templates:{名:sha256}}（tmp＋os.replace，save_local_config 同款）
  highwatermark   ← 与 receipt 分开存（config.json 侧），防 clear-data 连带洗掉防重放记忆
  v{N}/           当前版本模板平铺（不可变）＋已验签 manifest 副本
  v{N-1}/         保留上一版（回滚位）；损坏自愈实作＝同步器完整性复核 →
                  同版本重装修复（读路径只拒绝读取，修复触发器挂在同步侧）
  .staging-v{N}/  安装中转（七道校验全过才 rename；失败整目录删除）
```

- 清理失败 catch＋defer（Windows 句柄竞态：升级切换瞬间正有 AI 调用读旧版）；保留集＝
  当前＋前一版；**永不删本进程启动时 receipt 指向的版本**；loader 打开失败重试一次
  （重读 receipt）再判损坏。
- 同步对 clear-data/路径类 OSError 容错，失败静默留待下轮。

## D2 loader 解析序（`prompts/__init__.py` 唯一收敛点，61→58 调用方零改动）

1. receipt 指向版本目录——前置闸：`receipt.min_client_version > app_version()`（复用
   schema_version 比较器）拒载→回落 v{N-1}（同样过闸）→都不兼容＝PromptPackMissing
   引导升级（复用 UpgradeGate 文案族，不发明第四种提示面）；
2. 开发/测试态包内目录（e2e 存量 202 条零改动的关键：**默认 dev 态直读仓库单源**，仅
   强制包模式 env 钩子（`PROMPT_PACK_MODE=force`）下走包链）；
3. `PromptPackMissing`——AI 端点统一 503＋专用 reason；手写正文等非模板功能不受影响。

## D3 同步器与状态通道

- 钩子：登录成功（browser_auth silent 分支 save_local_config 后）＋启动补偿（lifespan
  末尾 dossier-sweep 同款 try/except）＋entitlement 快照档位变化＋设置页手动入口。
- 出站：独立 daemon 线程＋同步 httpx.Client；CDN 6s 超时（update_check._FETCH_TIMEOUT
  口径，不用 call_server_api 的 60s）；S端 换钥走 call_server_api；**SSRF 防线照抄
  update_check**（https＋烘焙可信域＋DNS 全公网＋异步 getaddrinfo）；manifest 内 URL
  一律不采信，路径从已验 base 派生（_derived_urls 先例）。
- 换钥 403→按档序降档重试一次（听 S端 权威，本地 config.json tier 不一致时以 S端 为
  准）；404→重取 latest.json；全失败静默沿用旧包。
- 状态出口：包状态字段挂 `/auth/verify` 本地响应；前端 LicenseProvider 路由/focus 两跳
  刷新消费；「在装」窗口 startBgWatch 式 1s 短轮询（90s 上限）；**不做 SSE**（C端 无先
  例）；登录成功链已有两连 toast，解锁瞬间用**卡片原位刷新**不加第三个 toast。
- 流式无感：模板只在组装端点被读（AiModal 打开/刷新提示词时），流式链路不再读模板
  ——实施时核一句后端确认此架构事实后落档。

## D4 打包断言（硬切）与 e2e

- build.spec 摘 prompts datas；client-package.yml 冒烟＋build_release.ps1 各加「产物树
  无 *.prompt」断言（历史上冒烟漏过 prompts——client-package.yml:162 注释自认，这次反
  转成门禁）。
- e2e：`PROMPT_PACK_MODE=force` 钩子＋测试签名钥夹具（进 fixtures，不进产物）＋假 CDN
  （monkeypatch 模块函数＋httpx.MockTransport，test_update_check 先例）；场景组见
  proposal；存量 202 条默认 dev 态零改动回归。

## D5 UI（原型先行，评审前端 P0/P1 内化）

- §5 状态总表加「写作能力」行；prototypes/book.html 右栏锁定卡四态＋ADJUSTMENTS 登记；
  design-vocab.mjs「写作能力」两端同批；§13:378 tier 行 MAX 臂已随 tier work 落地
  （`max: "MAX 会员"` 已在），不重复做。
- 状态×界面矩阵：已最新/换版完成/min_client 静默/自愈中＝**全静默**；未装+点了 AI＝
  行内 warn；失败＝锁定卡＋「重新获取」；档位不够＝升级卡（出口分流：未登录→去登录，
  已登录失败→重新获取——照抄会员锁卡形态但出口语义换，P1-4）。
- AcctMenu 版本行 title 加包版本＋最近同步＋复制诊断串；多书/多章界面不感知包版本
  （app 级资源，不进书架/工作台数据面——防 scope 膨胀）；未登录可进的 /config 页无登录
  上下文，不露包状态。
- min_client 不满足＝完全静默（旧包服役 AI 无损）；仅 S端 判死（不再兼容）才升级为锁定
  卡＋「去下载新版」。

## D6 与另两方的接口冻结点

- S端 `/api/prompt-pack/key` 契约（s-prompt-pack-keys D1）——本 change 实施前置。
- latest.json **v1 schema 一次定全**（评审 P0：召回字段事后补无效）：`{schema_version,
  version, min_client_version, min_pack_version(召回底线), published_at, tiers:{free/
  standard/pro/max:{sha256,size,key_id,template_count}}, signer_key_id}`；客户端 parse-
  and-ignore 未知字段；`min_pack_version` 闸门：candidate 与已装版 < 底线→拒装且已装
  坏版停用（回落 v{N-1} 或重拉）。
- publish.py（prompts 仓）：四档切包映射表＝模板→feature key→tier（CURATED 加 tier 字
  段单源）；publish_clean() 剥纳管注释（与 loader strip 语义逐字节一致——10-05 已对
  齐）；CI 加「dev 加载产物==pack 加载产物」哈希对拍。
