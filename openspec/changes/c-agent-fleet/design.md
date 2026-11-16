# c-agent-fleet 设计：总调度＋域 agent 舰队

## Context

一期单体 agent（一份身份定义＋30 工具全量＋按页注入）已走查可用。boss 拍板升级为舰队：AI 助手＝总调度 agent（唯一对话入口），每个 tab 对应一个域 agent（设定/卷纲/章纲/正文…），会话形态＝**全部先进总调度**（每条消息先分类再委派，作家感知单对话）。实施次序＝c-agent-harness（native FC）先落地，fleet 在原生 tool_calls 上叠加。

## Goals / Non-Goals

- Goals：总调度路由（分类→委派→收口）；AgentSpec 封闭注册（persona＋工具子域）；委派嵌套循环与纪律继承；事件带 agent 身份标签
- Non-Goals：不做作家可见的域 agent 独立会话（单对话感知）；不做域间自由对话（域 agent 互不直连，经总调度）；不增删能力围栏清单；不改线程模型与授权梯度语义

## 架构决策

### D1：总调度＝路由器＋承接者，无域写工具
总调度持有：全域**读**工具＋委派工具（delegate_agent，native tool_calls）＋画像/人格工具。**域写工具（generate_field/写回/建卡执行类）不出现在总调度 tool_scope**——写操作物理上只能经委派到域 agent 执行。分类错域可召回：总调度对委派结果不满意时（域 agent 返回 not-my-domain），换域重派或自答。

### D2：AgentSpec 封闭注册表
```python
@dataclass
class AgentSpec:
    name: str            # orchestrator / settings / volume / outline / prose
    title: str           # 总调度 / 设定助手 / 卷纲助手 / 章纲助手 / 正文助手
    persona: str         # 域 persona（自身份定义派生段＋域专属纪律段）
    domain_hint: str     # 给总调度的委派判据（管什么/不管什么）
    tool_scope: set[str] # 全量注册表的子集（读工具共享＋域写工具本域）
```
- 注册表封闭校验：tool_scope ⊆ registry、orchestrator.tool_scope 不含任何域写工具、每域至少一写工具（否则域无意义）
- 域 persona 自身份定义派生：身份定义（提示词包）仍是单源，域 persona = 身份定义＋域纪律段；身份定义更新时域 persona 自动跟随（不做两份独立维护）

### D3：委派＝原生 tool_calls＋内嵌循环
总调度循环里 `delegate_agent(agent, task, context)` 为一工具步：内嵌跑域 agent 循环（同 AgentLoop，harness=native 分支），域循环的步事件加 `agent` 标签原样流入 SSE；域循环结束返回结构化结果（summary＋cards）给总调度。纪律继承：
- **墙钟**：单回合墙钟由总调度持有（600→1800s 不变），委派消耗共享预算；委派前检查剩余预算，不足直接拒派并收口
- **停止**：作家停止穿透域循环（GeneratorExit 干净关闭，半截落库语义不变）
- **授权梯度**：域循环内写工具照常过 write_gate，gate 事件透传（作家看到的是域 agent 在请求授权）
- **压缩**：域循环转写独立、用后即弃（不写线程）；线程压缩仍按现有总调度会话口径

### D4：事件契约增项（向后兼容）
step_start/step_end/TraceFolded 增 `agent` 字段（orchestrator 缺省省略）；dock 轨迹组标域身份（「设定助手 · 2 步」），气泡署名保持「AI 助手」不拆对话。文本协议降级路径下 fleet 退化为总调度自答＋转域指引（委派不可用），事件不带 agent 标签——dock 对缺省字段零依赖。

### D5：tab 上下文＝路由先验，不是路由器
当前 tab（threadKey 的 scope）作为强先验注入总调度（「作家正在设定页」），但分类仍由总调度做——设定页问正文，委派正文域而非硬拒。线程仍按 tab 分（现有模型不动），跨 tab 的任务上下文经委派参数（context）传递。

## Risks / Trade-offs

- 委派嵌套一层就够（域 agent SHALL NOT 再委派——总调度唯一）；预算切分错了表现是「域 agent 干一半被墙钟掐」，靠委派前预算检查兜底
- 分类错误率靠域 domain_hint 判据＋召回重派兜底；一期域少（4 域）分类风险低
- 文本协议降级下 fleet 能力退化（无委派）——走查场景覆盖指引话术

## Migration Plan

1. AgentSpec＋域注册表落地（orchestrator/settings/volume/outline/prose 五域起步）
2. 总调度提示词＋delegate_agent 工具（native tool_calls 形态）
3. AgentLoop 委派分支（内嵌循环＋事件标签＋纪律继承）
4. 事件契约增项＋dock 身份标签呈现
5. 测试（路由/委派/越域写拒绝/预算切分/停止穿透）
6. 走查栈真 GLM 验证（跨域接力/授权透传/轨迹标签）

## Open Questions

- 拆书/知识/画像等是否单独成域（一期先并入总调度直答，域多了再拆）
- 委派任务的进度可见粒度（域循环内步骤全透传 vs 只报里程碑）——走查定
