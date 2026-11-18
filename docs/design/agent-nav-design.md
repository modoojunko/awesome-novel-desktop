# 设计提案：Agent 导航——agent 说的翻页必须真翻（Phase 2）

> 提案人：AI 撰写　评审人：boss 拍板
> 状态：待拍板（先设计＋开源调研，未动代码）
> 日期：2026-11-18
> 关联：docs/design/agent-effects-proposal.md（Phase 1 已上线：refresh 域刷新）；本篇是其 Phase 2「navigate」的落地设计＋开源对照结论

---

## 一、要解决什么问题

**走查实锤（2026-11-18 截图）**：作家对助手说「把页面切到正文」，助手回「页面切到
正文了，聚焦 vol-1-ch-7。」——**中栏一动不动，还停在章纲页签**。模型没有切页能力，
纯靠话术假装切了（幻觉执行）。这比不回应更糟：作家信了。

Phase 1 的 effect 只覆盖 `refresh`（数据变了刷新面板）；「agent 主动改变作家看到的
页面」没有落点。boss 总纲：**AI 助手的操作如果涉及翻页、编辑、保存，要在页面上看
到操作效果**——翻页是其中缺失的一环。

---

## 二、开源调研：这类问题业界怎么做

| 项目 | 许可 | 是什么 | 对本问题的映射 | 结论 |
|---|---|---|---|---|
| **AG-UI 协议**（ag-ui-protocol/ag-ui） | MIT | agent↔前端的事件协议：生命周期/文本流/工具调用/状态快照＋JSON Patch 增量，`Custom` 事件是应用自定义扩展点 | **没有专门的"导航"事件**——社区实践是 agent 发 Custom 事件或前端工具调用，前端订阅后自己 `navigate()` | **借鉴词汇与概念**：前端工具（schema 在服务端、执行在前端）＝行业标准名；effect 的 action 动词对齐它，留未来换装门 |
| **CopilotKit**（CopilotKit/CopilotKit） | MIT | `useCopilotAction` 在浏览器注册前端动作 → 后端中间件把 schema 转发给 LLM → 模型照常调用 → **浏览器 handler 执行 → 结果回喂模型** | 和我们要的完全同构：模型调 `navigateToPage(path)`，前端真的 `router.push`，模型知道成败（不说谎） | **借鉴契约**：①工具清单里可见 ②前端真执行 ③结果回喂。不引入运行时（它绑定 LangGraph/create_agent 系） |
| **assistant-ui** | MIT | React 聊天组件＋tool-ui 渲染层 | 渲染层方案；我们已有 cardConfig 卡面体系 | 不引入 |
| **Vercel AI SDK Generative UI** | Apache-2.0 | 工具结果→React 组件（工具选择 UI） | 我们的产物卡已是同概念 | 不引入 |
| **@agentscope-ai/chat@1.1.72**（现 dock） | 开源 | 聊天渲染壳（ChatAnywhere＋cardConfig）——**本地实勘：无前端工具/自定义事件 API 可消费**；上游 AgentScope×AG-UI 集成（issue #912）尚有映射缺口 | 无免费午餐；我们自驱的 SSE 链已经是传输层 | 留观察，不动 |
| **AWS Bedrock AgentCore×AG-UI 等实践** | — | 「前端持有动作、agent 请求执行」＝共识范式 | 印证方案 A 方向 | — |

**整体评估**：AG-UI/CopilotKit 都假设可替换的 agent 运行时与前端栈。我们的 loop 是
自研 asyncio 双模式 harness（sentinel 分节流式是为 deepseek-flash 合规性刚打磨过的）、
dock 是 Spark Chat 壳＋自研卡面。**为「切页签」一个能力换血，不成比例**。
正确姿势：**借设计不借代码**——effect 契约按它们的词汇演进，留 AG-UI 适配器门。

---

## 三、方案空间

| 方案 | 做法 | 代价 | 判定 |
|---|---|---|---|
| **A. 声明式前端动作**（推荐） | 新增 `switch_tab` 服务端工具（kind=read 免授权）：服务端只做**域校验＋生成 navigate effect**，前端收到 effect 后真实切页签；工具 summary 回喂模型 | 与 Phase 1 同构，后端 ~4 处小改＋前端 ~3 处 | ✅ 最小增量，链路已验过 |
| B. 真前端执行（CopilotKit 式） | loop **停车**等前端执行工具并回传结果（write_gate PARKING 同款机制） | 每次切页多一个往返；停车/超时/取消三条边界全要处理；文本协议下模型端到端延迟翻倍 | 过重，导航不需要 |
| C. 整体上 AG-UI/CopilotKit | 换协议＋换 dock＋换 loop | 换血；sentinel 流式（deepseek 合规）要重做 | 否 |

**推荐 A，外加一个关键决定：navigate 在 step_end 时立即应用（中途翻页），不等 run_end。**
理由：作家说「切到正文」，页面在 agent 还在说话时就翻过去——这是体感的核心；
refresh 仍按 Phase 1 在 run_end 批量刷（写操作常连发，批量刷省抖动）。

---

## 四、推荐设计（方案 A）

### 4.1 Effect 契约 v2（词汇对齐 AG-UI）

```ts
interface AgentEffect {
  action: "refresh" | "navigate";   // 未来可扩 open_panel / render（AG-UI Custom 事件同位）
  domain: "chapters" | "volumes" | "ui";  // ui＝纯前端状态，不触发数据刷新
  target?: string;                   // navigate＝页签键（og|prose|settings|relations|hooks|actions|style）
  description: string;               // 人话（日志用）
}
```

### 4.2 新工具 `switch_tab`

- 注册：kind=read（免授权，读类恒放行）；入参 `tab`（七值白名单，见 4.4）
- 域可见性（fleet 封闭集）：只进 `ch:*` 七个页签域——**卷纲/设定/书主页的助手根本
  看不到这个工具**，从源头杜绝域外乱切；共享读集合不动
- 服务端行为：校验 tab 白名单（坏值→ok=False，模型如实转告）→ summary「已切到
  {中文页签名}。」回喂 → effect 由 router 生成（工具零感知 effect 存在，声明式）
- **话术契约（写进工具描述）**：调用前的话术不许预告「已切」——只能说「我切过去」
  「你看一下正文」；切没切成由系统做，模型不背书

### 4.3 链路（哪里改）

```
模型调 switch_tab(tab="prose")
  → loop._emit_step：step_end（新增 args 字段——effect target 从这取）
  → router._consume：ok 且注册表声明 effect_action=navigate
      → 立即发 SSE 新事件 {type:"effect", action:"navigate", domain:"ui", target:"prose"}
      （不入库——导航是活体事件，回放历史不 teleport）
  → Aui2Dock：effect 事件 → onEffect 单条回调（新增 prop；run_end 的 onEffects 汇总保持 Phase 1 口径）
  → NovelWorkspace：navigate 守卫（view==="workbench" 且 chapterRef 在）→ chatNav 计数器信号
  → ChapterWorkspace：chatNavSeq/chatNavTab → setChTab(target)（aiWriteSignal 同款模式）
  → 页签真实切换，dock 线程随 scope.chapterTab 重绑（fleet 每页签一线程，现有机制自动接手）
```

后端落点：tools.py（Tool 元数据＋effect_action/effect_target_from＋switch_tab 注册）、
loop.py（step_end 带 args）、router.py（_consume 生成＋即时下发 effect 事件）。
前端落点：chatApi.ts（effect 事件类型）、Aui2Dock.tsx（onEffect 单条回调）、
NovelWorkspace.tsx（守卫＋信号）、ChapterWorkspace.tsx（信号→setChTab）。

### 4.4 页面模型映射（工具枚举＝既有页签键，不自造词）

| tab 值 | 页签 | 说明 |
|---|---|---|
| og | 章纲 | |
| prose | 正文 | 归档章有既有 banner，不受影响 |
| settings | 设定 | |
| relations | 角色关系 | |
| hooks | 伏笔 | |
| actions | 操作 | |
| style | 文风 | |

### 4.5 守卫与边界

- **流式中**：navigate 恰恰发生在流式中（中途翻页是卖点）；树锁定守卫只锁作家手动
  切页，agent 导航不受影响
- **脏表单**：chTab 页签间切换与作家手点页签同语义（现状无脏拦截），不加守卫；
  跨视图（写作↔设定）才碰 guardedLeave——本期不做跨视图
- **窄竞态**：thread 是 ch:prose 但作家已手动切走（如去了设定页）→ 前端守卫不切，
  模型被告知成功——概率低、代价小（一句话误差），设计上如实接受；后续可加前端
  回执（方案 B 的轻量版）再收
- **effect 不落库**：导航不进 assistant_messages，历史回放不重放导航（作家重开书
  不被 teleport）；refresh 汇总也只在活体 run 有效

### 4.6 明确不做（挂账）

- 跨视图导航（写作↔设定↔预览）：涉及 guardedLeave 脏守卫链，另立
- 跨章跳转（「打开第七章」）：涉及章节树选中态＋resumeSignal 链，另立
- 写操作中途实时刷新（Phase 3）：等 Phase 2 体感反馈
- AG-UI 适配器：effect 词汇已对齐，等有外部集成需求再评估

---

## 五、验收清单（走查用）

| # | 场景 | 预期 |
|---|---|---|
| 1 | 正文页签说「切到章纲」 | agent 调 switch_tab，页面立即翻到章纲，轨迹卡可见工具步 |
| 2 | 章纲页签说「看正文」 | 同上翻到正文；随后消息落 ch:prose 新线程（fleet 既有语义） |
| 3 | 说「切到设定」 | 翻到章节设定页签 |
| 4 | 卷纲页签说「切到正文」 | 工具不可见，模型直说「这里切不了，打开一章后我再帮你切」 |
| 5 | 说个不存在的页签 | 工具校验失败，模型如实说切不了＋列可选页签 |
| 6 | 切页后对话连续性 | dock 重绑新页签线程，历史/容量条正确；原线程内容不丢 |
| 7 | 话术纪律 | agent 不再出现「已切」假话术（截图实锤场景回归） |
| 8 | 回放安全 | 重开书/切页签回来，页面不被旧导航事件 teleport |

---

## 六、工作量

| 模块 | 内容 | 估 |
|---|---|---|
| 后端 | 工具＋元数据＋step_end args＋effect 生成/下发 | 0.5 天 |
| 前端 | onEffect 回调＋守卫＋chatNav 信号 | 0.5 天 |
| 测试 | route 钉（effect 即时下发/白名单/域不可见）＋前端信号钉 | 0.5 天 |
| 走查 | 五场景截图验收 | 0.5 天 |
| **合计** | | **2 天** |

---

## 七、待拍板

1. **方案 A**（声明式前端动作＋中途翻页）是否照此立项（openspec c-agent-nav）？
2. 工具名 `switch_tab`／话术契约口径有无要调的？
3. 跨视图＋跨章跳转挂账口径确认（本期不做）。
