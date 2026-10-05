# Design: s-prompt-pack-delivery（C端 半）

> 双钥匙信任模型与全链时序见 2026-10-05 对话定稿设计（本文件只记 C端 实现决策）。
> Design freeze 门槛＝5 项产品拍板；未拍板项在文中标 ⏳。

## D1 本地布局与安装原子性

```
{DATA_ROOT}/prompt-pack/
  receipt.json     {version, tier, key_id, min_client_version, installed_at, templates:{名:sha256}}
  v{N}/            当前版本模板平铺（不可变）＋已验签 manifest 副本
  v{N-1}/          上一版（回滚位；读时校验连续失败 1 次即回落，再坏则清 receipt 重拉）
  .staging-v{N}/   安装中转（七道校验全过才 rename；失败整目录删除）
```

- receipt 临时文件＋`os.replace` 原子写（`save_local_config` 同款范式）；清理失败
  catch＋defer（Windows 句柄竞态），保留集＝当前＋前一版，永不删本进程启动时 receipt
  指向版。
- 包存储跨版本共享（c-db-per-version 判例：库每版独立，包不能跟着走）。

## D2 loader 解析序（`prompts/__init__.py` 唯一收敛点）

1. receipt 指向版本目录——前置闸：`receipt.min_client_version > app_version()` 拒载回落
   v{N-1}（都不兼容→PromptPackMissing 引导升级）；读时轻量校验 `(mtime_ns,size)` 签名
   失效再 sha256（config.json 缓存同款口径）。
2. 包内目录（仅开发/测试态；发布包经 D4 断言不含模板）。
3. `PromptPackMissing`（异常带引导语义）——AI 链路统一 503＋新 reason，前端锁定卡。

## D3 同步器与状态通道

- 钩子：登录成功（browser_auth silent 分支 save_local_config 后）＋启动补偿（lifespan
  末尾，dossier sweep 同款 try/except 不挡启动）＋entitlement 快照档位变化＋设置页手动
  「检查写作能力」。
- 出站：httpx 同步 Client 独立 daemon 线程；CDN 6s 超时、S端 复用 call_server_api 口径；
  SSRF 防线照抄 update_check（https＋烘焙可信域＋DNS 全公网＋异步 getaddrinfo），manifest
  内 URL 一律不采信、路径从已验 base 派生。
- 状态出口：包状态挂 `/auth/verify` 本地响应（LicenseProvider 路由/focus 两跳刷新消费；
  已知「在装」时 startBgWatch 式 1s 短轮询；不做 SSE）。
- 换钥 403→按 latest.json 档序降档重试一次；全失败用旧包静默。

## D4 打包断言与 e2e

- build.spec 摘 prompts datas；client-package.yml 冒烟加「产物树无 *.prompt」（⏳ 若走
  双源过渡版：首发保留包内模板兜底、在线包可覆盖，断言随移除版到位）。
- e2e：env 钩子强制包模式＋测试签名钥夹具＋假 CDN（httpx.MockTransport，不引新依赖）；
  最小场景：首启无模板→锁定卡→装包→重试成功；min_client 静默；存量 parity 零改动。

## D5 UI（原型先行）

- §5 总表加「写作能力包」状态行；prototypes/book.html 右栏锁定卡四态变体＋ADJUSTMENTS
  登记；AcctMenu 版本行加包版本＋最近同步＋复制诊断串（entitlement-sync 降级提示同款）。
- 文案：用户可见名词统一「写作能力」；按钮全动词（去登录/重新获取/重试/去下载新版）；
  语气词 info/warn/err 内，无新增档。MAX 行级门控走 useFeature＋新 FeatureKey（⏳ 随
  拍板 2/3 定），tier.ts 扩 MAX 臂与 §13:378 同批。
