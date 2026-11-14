## 1. 设计判定与环境

- [x] 1.1 文案级影响判定（免原型登记）：本 change 仅改既有弹层/页内的失败态与错误提示文案＋失败原因取值，不触版式、组件结构、令牌与组件词汇，不需要原型先行；登记于本条，实现侧按 design-language §13 自查（补救语句带可点击出口：弹窗「重新获取」、登录页「重新检测」）。验证：proposal「Design Impact」段与本条互为对照，design:lint/design:check 回归全绿。
- [x] 1.2 建独立 worktree＋分支 `c-proxy-fakeip-compat`（本会话独立环境，不动主检出）。验证：`git worktree list` 见新 wt；分支基于最新 main。

## 2. 后端共享守卫

- [x] 2.1 新增 `client/backend/outbound_guard.py`：`FAKEIP_NET=198.18.0.0/15`、`classify_infos(infos)→ok|fakeip|blocked`、`validate_outbound(url, trusted_hosts, *, allow_loopback_host=False)→(bool, verdict)`（https＋可信域＋getaddrinfo＋classify；kb 逃生口语义保持）。验证：新单测覆盖矩阵（全公网/全 fake-ip/混合/环回宿主/非可信域/http/DNS 失败）。
- [x] 2.2 接入 `update_check.py`：async 版改「`await loop.getaddrinfo`＋`classify_infos`」，同步版改调 `validate_outbound`；删除两份本地实现；渠道全失败日志带 verdict 摘要（用户可见行为不变，静默降级保持）。验证：既有 test_update_check 全绿；新增 fake-ip 全命中放行用例。
- [x] 2.3 接入 `prompt_pack/sync.py`：删本地 `_validate_outbound` 改调共享 util；探测站先 validate 捕 verdict；最终失败且任一候选 verdict==fakeip → `_set_state("failed", reason="proxy_fake_ip")`，否则 `cdn_unreachable` 不变。验证：既有 test_prompt_pack_sync 全绿；新增 reason 断言用例。
- [x] 2.4 接入 `kb/baseline.py`、`kb/tree_sync.py`：同 2.3 形态（`asyncio.to_thread` 保持），latest 探测失败且 verdict==fakeip → 失败 reason `proxy_fake_ip`（既有 reason 取值不变）。验证：既有 kb 单测全绿；新增 reason 断言用例。

## 3. 前端文案与提示语义

- [x] 3.1 `PromptPackModal.tsx`：`FAIL_NOTES` 增加 `proxy_fake_ip` 映射——「代理软件的 TUN 模式接管了网络：请关闭 TUN 模式，或将本站域名加入代理软件的白名单，然后重新获取。」（无内部术语；「重新获取」「复制诊断信息」出口保留）。验证：组件测试断言该 reason 呈现该文案且出口在。
- [x] 3.2 `KnowledgeSyncModal.tsx`：失败态按 reason 取文案——`proxy_fake_ip` 用同口径代理指路文案，其余维持既有文案。验证：组件测试两分支断言。
- [x] 3.3 `LoginPage.tsx`：`checkAuthorized` 网络异常返回 `"network"` 哨兵（轮询中静默）；轮询结束/手动复查呈现网络指引文案（含关 TUN 建议），「重新检测」出口保留；业务应答未授权维持既有文案。验证：组件测试三分支（网络失败/未授权/轮询中间静默）。

## 4. 回归与归档

- [x] 4.1 后端全量 pytest 通过（worktree 内、独立环境）；新增测试计入覆盖率。验证：`pytest` 全绿输出结论。
- [x] 4.2 前端 `npm run coverage`（100% 契约）＋ `npm run design:lint` ＋ `npm run design:check` 全绿；`tsc --noEmit` 过。验证：命令实际输出结论。
- [x] 4.3 相关 e2e：prompt-pack-onboard / 知识同步相关 spec 通过（存量红对拍 main 放行）。验证：playwright 结论。
- [x] 4.4 `openspec validate --change c-proxy-fakeip-compat` 过；PR（openspec sync delta＋archive 移档同 PR 带上）；PR 描述含根因（fake-ip × SSRF 守卫）与用户影响（TUN 用户四链恢复）。
