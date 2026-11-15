# c-agent-fleet 任务

> 实施前提：c-agent-harness 已合入（委派走 native tool_calls；文本协议降级路径下 fleet 退化为总调度自答＋转域指引）。

## 1. AgentSpec 与域注册表

- [ ] 1.1 AgentSpec dataclass（name/title/persona/domain_hint/tool_scope）＋启动校验（tool_scope ⊆ registry；orchestrator 无域写工具；每域至少一写工具）
- [ ] 1.2 五域起步：orchestrator/settings/volume/outline/prose——persona 自身份定义派生（单源拼接）＋域纪律段；domain_hint 委派判据文案
- [ ] 1.3 域写工具归属表（generate_field 等设定写类→settings；写回/草稿类→volume/outline/prose 对应域）；读类工具全域共享清单
- [ ] 1.4 registry 守卫测试扩展（舰队校验断言：越域工具/总调度持写工具即报错）

## 2. 总调度路由

- [ ] 2.1 总调度系统提示词：身份定义＋路由纪律（先分类；tab 为先验不锁死；域外自答不空委派）
- [ ] 2.2 delegate_agent 工具（native tool_calls 形态：agent/task/context 三参）；文本协议降级下不可用→总调度自答＋转域指引
- [ ] 2.3 委派召回：域 agent 返回 not-my-domain 时总调度换域重派或自答
- [ ] 2.4 路由测试（域内委派/跨页先验不锁死/域外自答三场景，fake native client）

## 3. 委派执行与纪律继承

- [ ] 3.1 AgentLoop 委派分支：内嵌域循环（同 harness native 分支）；域循环转写独立用后即弃（不写线程）
- [ ] 3.2 墙钟预算切分：总调度持有单回合墙钟；委派前剩余预算检查，不足拒派收口
- [ ] 3.3 停止穿透：域循环 GeneratorExit 干净关闭＋半截落库语义不变；总调度循环同步退出
- [ ] 3.4 write_gate 透传：域循环 gate 事件原样入流（标域身份）；授权梯度语义零改动
- [ ] 3.5 域 agent 禁止再委派（delegate_agent 不在任何域 tool_scope）
- [ ] 3.6 测试：嵌套循环/预算拒派/停止穿透/gate 透传/再委派拒绝

## 4. 事件契约增项与 dock 呈现

- [ ] 4.1 step_start/step_end/TraceFolded 增 agent 字段（orchestrator 缺省省略；向后兼容）
- [ ] 4.2 dock 轨迹组标域身份（「设定助手 · N 步」）；气泡署名保持「AI 助手」不拆对话
- [ ] 4.3 事件契约测试（缺 agent 字段旧客户端/旧测试零回归）

## 5. 走查栈真机验证

- [ ] 5.1 真 GLM 全链：设定页问章纲任务（跨页委派）＋轨迹域标签＋产物卡同流
- [ ] 5.2 授权透传实测（域内写工具 gate 弹出→批准→继续）
- [ ] 5.3 停止穿透实测（域循环中停止，半截落库）
- [ ] 5.4 文本协议降级复跑（强制 text 模式：总调度自答＋转域指引话术）
- [ ] 5.5 dock 回归（线程/压缩/授权芯片/容量条零回归）
