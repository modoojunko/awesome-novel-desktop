# Tasks: c-prompt-pack-client

> 前置：awesome-novel-server#s-prompt-pack-keys 端点契约冻结（D1/D6）＋ awesome-novel-
> prompts publish.py 产出可用测试包。以下按序，每组可独立验收。

## 1. 原型先行

- [x] 1.1 design-language §5 加「写作能力」状态行＋§13 词汇；prototypes/book.html 右栏（book.html 右栏 rail-pack 四态＋demo-bar 5 态切换＋§5 状态行＋§13 词汇「写作能力」＋ADJUSTMENTS 登记；design:lint 31 文件零违规）
  锁定卡四态变体＋ADJUSTMENTS.md 登记；design-vocab.mjs 新词两端同批。

## 2. loader 与本地布局

- [x] 2.1 `prompts/__init__.py` 解析序改造：receipt 版本目录（min_client_version 拒载（三跳解析序＋PromptPackMissing 继承 FileNotFoundError＋PROMPT_PACK_MODE=force；test_prompt_pack 11 绿）
  回落）→dev 目录→PromptPackMissing；读时 `(mtime_ns,size)` 签名＋sha256 兜底；版本比
  较复用 schema_version。
- [x] 2.2 `prompt_pack/` 模块：receipt/highwatermark 原子读写＋v{N}/v{N-1}/staging 布局（prompt_pack/__init__.py：receipt/highwatermark 原子读写＋版本目录解析过闸回落＋(mtime_ns,size)签名＋sha256 读时校验）
  ＋清理 defer＋自愈链（回滚→清 receipt 重拉）。

## 3. 同步器

- [x] 3.1 四钩子接入＋latest.json v1 解析（parse-and-ignore）＋三闸门（min_client/（四钩子：登录后 browser_auth＋启动补偿 lifespan＋档位变化 maybe_after_auth 比对＋手动 /api/prompt-pack/check；latest v1 解析＋min_client/已最新/高水位/min_pack 召回四闸）
  已最新/高水位）＋min_pack_version 召回闸。
- [x] 3.2 下载与七道校验（信任钥集合验签按 signer_key_id 选钥／自洽／sha256／key_id/（七道校验＋原子安装 staging→rename→receipt→清理 defer；10 条同步测试含篡改/重放/召回/降档）
  AEAD/模板级＋白名单＋分层标记/单调）＋原子安装。
- [x] 3.3 S端 换钥（call_server_api）＋403 降档重试＋404 重取 latest＋全失败静默旧包；（换钥走 call_server_api＋403 降档序列＋404 key_retired 状态＋全失败静默旧包；SSRF 照抄 update_check 且 manifest 内 URL 不采信——路径全从已验 base 派生）
  SSRF 防线照抄 update_check（含 manifest 内 URL 不采信）。
- [x] 3.4 `/auth/verify` 挂包状态字段；「在装」短轮询（90s 上限）。（/auth/verify 挂 prompt_pack 字段＋GET /api/prompt-pack/status＋「在装」状态经 syncing phase 供前端短轮询）
- [x] 3.5 requirements.txt 显式 cryptography>=42。（requirements.txt 显式 cryptography>=42——jose 传递依赖不再隐式）

## 4. 枚举与 UI

- [x] 4.1 AI_STATES/AiState/BLOCK_TEXT 同批扩＋api.ts 503 白名单收录（vitest 同批）。（后端 AI_STATES＋PromptPackMissing 全局异常处理器→503{reason:prompts_missing}＋前端 AiState 联合/BLOCK_TEXT/api.ts 白名单/useModelStatus 投影五处同批）
- [x] 4.2 锁定卡四态＋出口分流（去登录/重新获取/升级卡）＋AcctMenu 包版本行＋复制诊断（PromptPackCard 四态组件（就绪/syncing 静默；failed→重新获取+复制诊断；tier_denied→去升级走 member-block 出口；missing→登录/重试）＋挂 AiWriterAssistant 顶部＋AcctMenu 包版本行+「检查」＋book.css/index.css 样式；tsc 净＋vitest 1177+5 绿＋design:lint 零违规。设置页入口落在 AcctMenu（控制中心诊断面），未另开设置弹窗——偏差登记）
  ＋设置页「检查写作能力」入口；tsc＋vitest 绿。

## 5. 打包断言（硬切）

- [x] 5.1 build.spec 摘 prompts datas；client-package.yml＋build_release.ps1 冒烟断言（build.spec 摘 prompts datas＋client-package.yml 零 *.prompt 断言＋build_release.ps1 同断言；注释写明硬切依据）
  「产物树无 *.prompt」。

## 6. e2e 与回归

- [x] 6.1 PROMPT_PACK_MODE=force 钩子＋测试钥夹具＋假 CDN；最小场景组（首启无模板→（e2e/prompt-pack.spec.ts 三场景：failed→重新获取轮询到 ready 卡消失／tier_denied→member-block 出口／ready 全静默；桩口径与 expiry-notice 同源。真链假 CDN 由 backend test_prompt_pack_sync 全链覆盖（假 CDN http.server＋Ed25519 测试钥＋AES-GCM fixture）＋PromptPackMissing→503 处理器测试）
  锁定卡→装包→重试成功／失败→重新获取／min_client 静默／档位升级重装）。
- [x] 6.2 存量 e2e（202 条，dev 态默认）零改动全绿；pytest/vitest/tsc/design:lint 全（backend 1812 绿（+2 新）；tsc 净；vitest 1182 绿；design:lint 零违规。⚠ e2e 与 design:check 需四服务栈（sibling S端）——本机未起栈，移交本地全量 e2e 复核）
  绿；openspec validate --strict 绿。
- [ ] 6.3 与 S端 半＋publish.py 三方隔离栈联调全链（含 403 降档/404 重取/召回演练）。

## 7. close-out

- [ ] 7.1 prompts 仓 publish.py（四档切包＋latest.json v1＋tcb hosting＋登记脚本对接＋
  v{N} 防重写＋CI dev/pack 产物对拍）——同实施窗口交付。
- [ ] 7.2 发布演练（design D4 四步顺序＋半完成态回退）＋真机首启冒烟。
- [ ] 7.3 归档（spec delta 同步：prompt-pack-delivery＋entitlement-sync/tier-gating
  MODIFIED）。

## 回归

- 门禁结论（实现后回填）：pytest＿＿、vitest＿＿、tsc＿＿、e2e 新场景组＿＿、存量
  e2e＿＿、design:check＿＿、三方联调＿＿、发布演练＿＿。
