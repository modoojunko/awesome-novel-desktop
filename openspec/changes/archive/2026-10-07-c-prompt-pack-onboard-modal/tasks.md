# Tasks: c-prompt-pack-onboard-modal

> 顺序：原型 → 后端（探测/进度/触发修复）→ 前端（弹窗/挂载点/菜单）→ e2e/回归。
> 每组可独立验收；前置约束：用户可见名词统一「写作能力」。

## 1. 原型先行（design-system 前置）

- [x] 1.1 书架原型（prototypes list.html 同源位）登记弹窗三模式变体（首装 running/
  更新 confirm/手动 manual + done/failed 行）＋进度分步行样式；ADJUSTMENTS.md 登记留档。
- [x] 1.2 design-language §5 状态总表加「写作能力弹窗」行；design-vocab.mjs 新词两端
  同批登记（弹窗标题/进度行/完成行/失败行/菜单项三态 hint）；design:lint 绿。

## 2. 后端：探测端点＋进度面

- [x] 2.1 `sync.py` 新增 `probe_latest()`：复用候选 URL/验签/min_client 闸，比较 receipt
  版本返回 `{installed_version, latest_version, update_available}`；不下载不装不调 S端
  不改 `_state.phase`；dev 态（非 force 且包内目录可用）恒 false；router 挂 GET
  `/api/prompt-pack/probe`；pytest 单测覆盖（有更新/无更新/验签失败/旧客户端跳过/dev 态）。
- [x] 2.2 `sync_once` 关键节点写 `step`（probe/download/install，完成清空），`get_status()`
  快照带出；pytest 钉住各 step 观测点与完成清空。

## 3. 后端：触发可靠性（定诊修复）

- [x] 3.1 `trigger_sync` pending 重跑：在途时记 `_pending_tier`，线程收尾按其重跑一次
  （仅一级）；pytest 钉「在途触发→结束后按新档位重跑」与「不无限重排」。
- [x] 3.2 `maybe_after_auth` 无 token 早退；pytest 钉「未登录不发起同步」（无外呼断言）。

## 4. 前端：弹窗与挂载点

- [x] 4.1 `licenseCache` PackStatus 扩 `step`；`PromptPackModal` 新组件（mode×stage 状态机
  见 design D7，复用 design/Modal；1s 轮询 `/prompt-pack/status` 上限 180s；tier_denied
  走升级出口；失败态含重新获取＋复制诊断）挂壳层单点，CustomEvent `pack-modal:open`
  开启；vitest 覆盖状态机各迁移。
- [x] 4.2 `NovelListPage` 挂载 effect：status 为 missing/failed → 开弹窗 install 模式并
  POST `/prompt-pack/check`；否则 probe，有更新 → 开弹窗 update 模式；in-flight 去重＋
  StrictMode 双挂载保护；vitest 钉三分支与静默分支。
- [x] 4.3 `AiWriterAssistant` BLOCK_TEXT `prompts_missing` 文案按已登录失败口径调整
  （指向菜单「写作能力」重新获取）；`PromptPackCard` 失败文案同步对齐；vitest 更新。

## 5. 前端：账号菜单入口

- [x] 5.1 AcctMenu：「数据」组「模型配置 · API Key」后加 `am-item`「写作能力」（hint
  三态：已就绪 vX/未就绪/有新版本），点击 close＋CustomEvent 开弹窗；删除 foot `am-pack`
  行与 `am-pack-check` 及其样式；AcctMenu 测试更新（旧 pack 行用例改菜单项断言）。

## 6. e2e 与回归

- [x] 6.1 新 spec `prompt-pack-onboard.spec.ts` 四场景：首装弹窗全程（开窗即下载→进度
  →完成可关）／更新确认（探测→confirm→进度→完成）＋暂不更新（关窗不装，再进再提示）／
  **进度期弹窗锁定**（X disabled、无退出出口，完成才提示可关闭——用户 10-07 二次
  拍板，推翻初版「中途可关窗」）／菜单手动入口（无更新「已是最新」）。实施口径＝桩模式（与既有
  prompt-pack.spec 同源；真链假 CDN 已由 pytest test_prompt_pack_sync 覆盖）；隔离栈
  （本地 vite 5199＋后端 8100＋假 S端 19100）新旧两 spec 7/7 绿；存量 prompt-pack.spec
  补 localStorage 登录态种子（此前 AuthGuard 判据缺口）＋独立目录首建容错。
- [x] 6.2 存量回归：pytest 1989/1 skip、vitest 1222、tsc、design:lint、validate --strict
  全绿；design:parity 7/8 过，quota 2.693% 红＝存量光栅漂移（PR #711 在途时同值）；
  书架探测收敛为单请求（probe 端点带 source=dev 静默，请求预算零扰动）；list parity
  原型侧移除 demo-bar（非基线 chrome）。

## 7. close-out

- [ ] 7.1 真机首装冒烟（Windows/macOS 各一）：全新安装→登录→弹窗引导→就绪→AI 可用；
  菜单入口三态可见。
- [x] 7.2 归档（spec delta 同步：prompt-pack-delivery MODIFIED+ADDED、design-system
  ADDED；Purpose 无需改）。

## 回归

- 门禁结论（实现后回填）：pytest 1990 绿（含原子换版钉 test_update_keeps_old_set_until_
  atomic_swap）、vitest 1222 绿、tsc 绿、design:check 绿（parity quota 2.693%＝存量
  红）、e2e 新场景组 4/4＋存量 pack e2e 3/3（隔离栈；含「不能关闭此窗口＋预计 1 分钟
  左右」文案断言）、真机冒烟＿＿（待做）。
- 10-07 三次拍板追加：进度与更新确认文案明说「期间不能关闭此窗口＋预计耗时」；原子
  换版契约入 spec（不能边升级边换提示词——staging 全验后原子切换，pytest 钉）。
- **开发评审轮（原型定稿后）**：3 P1 全修——①probe 端点 asyncio.to_thread（同步
  httpx 不得阻塞事件循环）；②min_client 跳过分支落终态 missing+reason（防 180s 锁定
  死弹窗）＋前端 reason 静默（书架不弹窗/手动提示先更新客户端）；③弹窗 onOpen running
  守卫＋轮询 run-token（防锁定降级/双链）。P2 五条全修：pending 消费到空（重跑期触发
  不丢）、proposal 改锁定口径、done 刷探测缓存＋登出清、失败原因映射人话、补 5 测
  （重入/180s 超时/失败原因/manual min_client/书架 min_client）。终验：pytest 1992、
  vitest 1227、tsc、validate 全绿；e2e「tier_denied 超时」定诊＝**环境非产品**——
  收环境 lsof 逗号多端口假零→僵尸旧进程跨轮存活（bind 全败但 nohup 静默），后端
  404/超时全来自僵尸＋失效库句柄；修复＝逐口杀＋bind 自检＋spec 网络步骤 fail-fast
  （mustOk）；干净环境连跑三轮 7/7×18s 证稳。
- **review-agent 轮（PR #714 后）**：P2＝trigger_sync 退出与 finally 清空非原子（排队
  触发窄窗口被丢，违背「在途触发不吞」）→ 退出判定与 _syncing 复位合并同一临界区、
  异常路径独立收尾；P3＝design-system delta 的 design-vocab.mjs 登记承诺与该文件机制
  不符 → 措辞对齐（类名/文案不入其白名单）。
