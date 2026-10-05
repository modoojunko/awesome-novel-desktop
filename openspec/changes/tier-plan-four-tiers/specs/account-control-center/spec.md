## MODIFIED Requirements

### Requirement: 触发钮套餐徽章四态与失联变色保持档位

触发钮徽章 SHALL 按「免费/试用/三档会员」五态短档展示当前套餐，判定优先级与既有文案单源一致：expired 优先 → 试用（tier=trial）→ 会员（is_member，standard/pro/max 分档）→ 免费版。短档展示：会员三档 SHALL 各按服务端下发的 display_name 单源渲染（底色沿用 accent；文案如「标准会员/PRO 会员/MAX 会员」——以 tiers.display_name 为准，SHALL NOT 前端写死档位中文名，standard 用户 SHALL NOT 被错标为「PRO 会员」或「免费版」）/ 试用 · 剩 N 天（充裕 muted；剩余 ≤3 天（含 0 天）转 warn）/ 免费版（含已过期，muted 合并单档）。徽章判定 SHALL 复用既有会话校验数据（tier/is_member/expired/trial_remaining_days），MUST NOT 新增请求点位与轮询。**S端无响应或本地断网（权益同步刷新失败）时，档位判定 SHALL 完全基于本地会话与本地权益快照：徽章文案照常显示既有档位、仅整体转 warn 色（触发钮与面板头同步），网络恢复同步成功后自动回常规色。** 网络失败 MUST NOT 触发清缓存、MUST NOT 把已登录用户的会员/试用档位降级展示（含书架横幅口径一致，修掉既有「刷新失败清缓存降免费」行为，失联信号取自前端同步失败状态而非后端字段）。`entitlement_degraded`（快照不完整防御态）MUST NOT 作为徽章信号消费。完整套餐档 SHALL 保留在面板账号区头展示（如「套餐已过期 · 免费待遇」），短档合并细节 MUST NOT 丢失档位信息。展示文案 MUST 统一自共享文案单源派生（短档为同一判定数据的投影、允许缩短措辞），MUST NOT 出现第二套分叉文案表。

#### Scenario: PRO 用户首屏可见身份

- **WHEN** 已登录的 PRO 会员进入书架
- **THEN** 顶栏触发钮徽章显示「PRO 会员」（accent 色），无需打开任何弹层

#### Scenario: 标准会员按 display_name 展示

- **WHEN** 已登录的 standard 会员进入书架
- **THEN** 顶栏触发钮徽章按 tiers.display_name 展示标准档短档（accent 色），SHALL NOT 显示「PRO 会员」或「免费版」

#### Scenario: 试用临期转警示色

- **WHEN** 试用用户剩余天数 ≤3 天（含 0 天）
- **THEN** 触发钮与面板头徽章同步显示 warn 色短档（如「试用 · 剩 2 天」）

#### Scenario: 过期与免费在触发钮层同为免费版

- **WHEN** 用户套餐已过期或从未付费
- **THEN** 触发钮短档统一显示「免费版」（muted）；打开面板后账号区头区分展示完整档「套餐已过期 · 免费待遇」或「免费版 · 单机使用」

#### Scenario: S端失联变色且档位不变

- **WHEN** 已登录的 PRO 会员使用期间 S端无响应或本地断网（权益同步刷新失败）
- **THEN** 触发钮与面板头徽章仍显示「PRO 会员」文案、整体转 warn 色；MUST NOT 降级为免费/试用展示、MUST NOT 清缓存

#### Scenario: 网络恢复自动回常规色

- **WHEN** S端恢复可达且权益同步成功
- **THEN** 徽章回常规色（accent），文案按最新判定值展示
