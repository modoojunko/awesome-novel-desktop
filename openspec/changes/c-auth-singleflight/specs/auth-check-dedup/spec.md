## Purpose

check-auth（本地端点向 S端 的静默登录态探测）是「可能 30~60 秒的慢路径」：S端 CloudBase MinNum=0 缩零后首请求需冷启动。本能力约束其出网去重契约——短窗口内重复探测复用同一份成功快照与同一个在途请求，冷启动与发布窗口的等待至多付一次，且不破坏启动自愈重试与重新授权等待的即时性。

## ADDED Requirements

### Requirement: check-auth 成功快照缓存

本地 `GET /auth/check-auth` SHALL 对 S端 静默探测的成功结果（envelope code 0）保留 60 秒缓存：缓存窗口内的后续调用 SHALL 直接返回该快照且 SHALL NOT 触发新的出网请求。缓存 SHALL 只保存成功快照：code -1（S端不可达/冷启动）与其它非零 code SHALL NOT 进入缓存——失败后的下一次调用必须重新出网（启动自愈依赖此语义探测实例唤醒）。

#### Scenario: 缓存窗口内重复调用
- **WHEN** 60 秒内第二次 `GET /auth/check-auth` 到达，且此前有一次 code 0 成功结果
- **THEN** 返回缓存快照，该请求对应零次出网

#### Scenario: 失败不缓存
- **WHEN** check-auth 出网返回 code -1（S端冷启动/网络错误）后紧接着再次调用
- **THEN** 第二次调用重新出网，不受上次失败影响

### Requirement: check-auth 出网单飞

同一时刻并发的多个 `/auth/check-auth` 请求 SHALL 共享同一个在途 S端 静默探测（单飞）：后端 SHALL NOT 同时发起多个相同的静默探测出网。

#### Scenario: 并发去重
- **WHEN** 缓存未命中期间 3 个 `/auth/check-auth` 并发到达
- **THEN** 后端只发起 1 次出网，3 个请求以同一结果返回，总耗时等于单次出网耗时

### Requirement: fresh 旁路

`GET /auth/check-auth` SHALL 支持 `fresh=1` 查询参数：跳过缓存读取并绕过在途共享直接活调 S端；活调取得的 code 0 结果 SHALL 回填缓存。需要「当下真实登录态」的消费方（如重新授权等待轮询）SHALL 使用该旁路，防止旧快照造成误判。

#### Scenario: 授权等待轮询不受旧快照污染
- **WHEN** 缓存中存有 30 秒前的 code 0 快照，用户在提示词包弹窗发起重新授权并以 fresh=1 轮询登录态
- **THEN** 轮询返回活调结果（旧快照不参与判定），授权完成可被即时感知

### Requirement: 登录动作后缓存失效

非静默登录流程（`POST /auth/browser-auth`）发起后 SHALL 失效既有 check-auth 缓存：其后的首次 check-auth（不带 fresh）为活调。

#### Scenario: 登录后首查活调
- **WHEN** 缓存中存在快照，用户完成一次浏览器登录流程后调用 `/auth/check-auth`
- **THEN** 该调用重新出网，不返回登录前的旧快照
