# c-agent-nav Design

## Context

Phase 1 effect 系统（c-agent-effects 已上线）：写类工具声明 effect_domain → router
收集成功写步 → run_end 注入 effects 数组 → NovelWorkspace 按域 refreshCharStale。
缺口：只有 refresh，没有 navigate——agent 描述切页纯靠话术（幻觉执行实锤截图）。

页面模型（NovelWorkspace 实勘）：
- `view`: workbench | advanced-settings | archives（写作/设定/预览三页签）
- `chapterRef`: 树选中章；ChapterWorkspace 仅在 chapterRef 非空时渲染
- `chTab`: ChapterWorkspace 内部 state，七值 og/prose/settings/relations/hooks/actions/style；
  外部驱动的既有先例＝aiWriteSignal 计数器信号（生成启动→切正文页签＋聚焦）
- dock 线程键＝`ch:{tab}`（fleet 每页签一线程）；切页签后 dock 随 scope.chapterTab
  自动重绑（既有机制）

方案论证与开源调研全文见 docs/design/agent-nav-design.md（boss 已拍板方案 A：
声明式前端动作；方案 B 真·前端执行停车等待＝过重，方案 C 整体上 AG-UI＝换血，均否）。

## Goals / Non-Goals

- Goals：agent 说切就真切（中途翻页体感）；模型不撒谎（校验＋回喂）；域外不可见；
  回放安全；增量最小（不动协议/loop 架构/dock）
- Non-Goals：跨视图导航（写作↔设定↔预览，涉 guardedLeave 脏守卫链，挂账）；
  跨章跳转（树选中态＋resumeSignal 链，挂账）；写操作中途实时刷新（Phase 3 挂账）；
  AG-UI 适配器（词汇已对齐，等外部集成需求）

## Decisions

### D1：effect 契约 v2——新增 navigate action（对齐 AG-UI 词汇）

```ts
interface AgentEffect {
  action: "refresh" | "navigate";          // 未来可扩 open_panel/render（AG-UI Custom 同位）
  domain: "chapters" | "volumes" | "ui";   // ui＝纯前端状态，不触发数据刷新
  target?: string;                          // navigate＝页签键
  description: string;
}
```

### D2：工具元数据声明式生成 effect（工具函数零感知）

Tool dataclass 增 `effect_action: str = "refresh"`、`effect_target_from: str = ""`。
router._consume 按 `ok + effect_domain` 生成 effect：action 取 effect_action，
target 从 step_end.args[effect_target_from] 取。switch_tab 声明
`effect_action="navigate", effect_domain="ui", effect_target_from="tab"`。
既有六写工具默认值不变（refresh），零回归面。

### D3：step_end 携带 args

_emit_step 的 step_end 增加 `args` 字段（工具入参原样，模型生成的小 JSON）。
effect target 的来源；SSE 体积影响可忽略（单步 args ≈ 数百字节）。

### D4：navigate 即时下发（step_end 时刻），refresh 维持 run_end 批量

router._consume 生成 navigate effect 时**立即**向队列发独立 SSE 事件
`{type:"effect", action:"navigate", domain:"ui", target, description}`——作家在
agent 说话中途就看到翻页。**不入库**（导航是活体事件，历史回放不 teleport——
assistant_messages 不落 effect 行）。refresh 维持 Phase 1 口径（run_end 汇总批量），
因为写操作常连发、批量刷省抖动。effect SSE 事件对 useChatSession 是即弃事件
（转发 onEffect 单条回调），不进镜像/落库分支。

### D5：前端应用链——计数器信号（aiWriteSignal 同款）

- Aui2Dock 新 prop `onEffect?: (effect) => void`（单条即时；run_end 的 onEffects 保持）
- NovelWorkspace：`view==="workbench" && chapterRef` 守卫 → bump
  `chatNavSeq`＋记录 `chatNavTab`（七值）→ props 传 ChapterWorkspace
- ChapterWorkspace：useEffect on chatNavSeq → `setChTab(chatNavTab)`；
  无 dirty 拦截（与手点页签同语义）；dock 线程重绑由 scope.chapterTab 变化自动发生
- 守卫不满足（作家已切走）→ 静默忽略（窄竞态，设计接受——server 不知道前端视口）

### D6：域可见性——七域工具集各加一行，共享集不动

scopes.py `_DOMAIN_TOOLS`：ch:og/ch:prose/ch:settings/ch:relations/ch:hooks/
ch:actions/ch:style 七域的 tools frozenset 各加 `"switch_tab"`。
`_SHARED_TOOLS` **不加**（否则卷纲/设定/预览/默认域全可见，破坏域封闭）。
`tool_domain()` 归属映射自动随域清单更新（轨迹标签显示「章纲」等域）。

### D7：话术契约进工具描述（模型唯一可读面）

description 写死三句：①用途＝作家要看某个页签/说「切到/给我看」时调用；
②调用前话术用进行时（「我切过去」），SHALL NOT 预告「已切」；③仅限当前章节
页签间切换，跨章/跨视图做不到就直说。文本协议目录（tool_catalog_text）运行时
从注册表渲染，新工具自动进清单——**无需发提示词包**。

### D8：读类免授权＋启动校验链

kind=read：_gate_fn 恒放行；test_assistant_registry 既有围栏钉
（read free/write fenced）覆盖新工具自动通过；注册表唯一性/fn 存在钉同活。

## Risks / Trade-offs

- **窄竞态说谎**：thread 是 ch:prose 但作家已手动切走 → 前端忽略，模型被告知成功。
  接受（概率低代价一句话）；后续可做前端回执升级为 CopilotKit 式双向（挂账）
- **effect 事件与 useChatSession 事件幂等面**：新事件类型进 SSE 流，镜像/落库分支
  必须显式不匹配（设计即如此），走查盯镜像不受染
- **ch:actions 域**（tools 现为空集）加入 switch_tab 后该页签助手获得第一个域内
  工具——意图内行为（操作页签的助手理应能切页签）

## Migration Plan

零迁移：新工具＋新事件类型均为增量；老客户端（不发 effect 事件的包）不受影响；
前端旧包收到未知 SSE 类型按既有「非 JSON 行跳过/未知类型忽略」口径安全降级。

### D9：页签真值注入（走查实锤补刀 2026-11-18 复测）

thread 后缀即当前页签，服务端是唯一真值源——不注入，flash 就信被污染的历史
（「页签已经在正文了」幻觉，复测 0/3 服从）。_stream_chat 在 note 里追加
「［当前页签：X］」。

### D10：导航意图 prime（走查实锤补刀）

纪律口号治不动 flash（补刀后仍 0/3）。窄正则命中「切/换/跳到 X」「看看 X」→
prime switch_tab 首步（chips tool_hint 同款确定性机制，模型只管事后叙述）。
守卫：显式 tool_hint 优先／域外 None／同页签 None（真值注入兜住）／意图外
None。读类零风险，误命中代价＝一次无副作用翻页。纯函数 nav_prime_hint 可钉。

## Open Questions

<!-- 无：boss 已拍板方案 A＋中途翻页＋工具名 switch_tab（2026-11-18） -->
