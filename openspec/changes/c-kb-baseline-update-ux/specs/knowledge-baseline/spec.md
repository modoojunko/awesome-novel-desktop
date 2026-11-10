# Delta: knowledge-baseline · 新增「更新探测与触达」

## ADDED Requirements

### Requirement: 更新探测与触达

用户已同步某版官方知识后，官方发布了新版本时，用户**无需重启 app** 即可在知识库页
获知有更新，并可一键更新；层缺失时登录/校验成功自动补装。

#### Scenario: 探测端点同版
- **WHEN** GET /api/kb/baseline/probe 且 CDN latest 版本与本地已装版本相同
- **THEN** 返回 `{installed: N, latest: N, update_available: false}`

#### Scenario: 探测端点发现新版
- **WHEN** CDN latest 版本号与本地已装版本不同
- **THEN** 返回 `{installed: N, latest: M, update_available: true}`

#### Scenario: 探测端点失败不打扰
- **WHEN** CDN 不可达或 latest 验签失败
- **THEN** 返回 `{update_available: false, reason: "<原因>"}`，不抛错、不触发同步

#### Scenario: 层缺失时登录/校验钩子补装
- **WHEN** 登录或 check-auth 成功且本地从未同步过基线（或层为空）
- **THEN** 后台静默触发一次同步，失败不阻塞登录、下次钩子再试

#### Scenario: 已装用户钩子零外呼
- **WHEN** 登录或 check-auth 成功且本地已有基线版本且层非空
- **THEN** 不发起任何网络请求（纯本地早退）

#### Scenario: 知识库页自动弹更新窗
- **WHEN** 知识库页挂载探测到 update_available 且该 CDN 版本未被用户「暂不更新」锚压制
- **THEN** 自动弹出更新窗：显示「当前 vN → 最新 vM」＋「立即更新」「暂不更新」两个动作

#### Scenario: 暂不更新同版不重弹
- **WHEN** 用户点了「暂不更新」后再次进入知识库页且 CDN 仍为同一版本
- **THEN** 不再自动弹窗；CDN 版本号变化后恢复自动弹

#### Scenario: 立即更新落层
- **WHEN** 用户在弹窗点「立即更新」
- **THEN** 调用同步端点（幂等），完成后本地基线层为新版、提示「官方知识已更新到 vM」；
  失败则提示「更新没有完成，稍后可再试」且可重试

#### Scenario: 手动检查入口
- **WHEN** 用户点击知识库页头部「官方知识 vN」入口
- **THEN** 打开手动弹窗：显示当前版本；有新版时提供「立即更新」，无新版时显示已是最新

#### Scenario: 测试闸不受影响
- **WHEN** 环境变量 KB_BASELINE_SYNC=0（测试/诊断态）
- **THEN** 补装钩子不发起同步；既有启动同步闸语义不变
