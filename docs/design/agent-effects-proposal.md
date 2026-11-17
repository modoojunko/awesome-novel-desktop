# 设计提案：Agent 操作前端——对话即操作

> 提案人：AI 撰写　评审人：架构师 / 前端工程师 / 产品经理
> 状态：待评审
> 日期：2026-11-17
> 关联：c-agent-chat-memory（已有 spec）；本提案为增量设计，不改变已有 spec 契约

---

## 一、要解决什么问题

当前 agent 对话已能调用 43 个工具（读类＋写类＋产卡类）操作后端数据，但**前端页面不知道 agent 做了什么**：

```
作家（对话）：「帮我确认第七章章纲」
  ↓ agent 执行 confirm_chapter → 后端数据已变
  ↓ 对话里回一句「已确认」
  ✗ 但左侧树第七章还是灰色、章节头还是草稿态——页面没更新
  ✗ 作家要手动刷新或切页签才能看到结果
```

**目标**：agent 的每个操作结果实时反映在页面上，作家在对话里完成全流程，不用动手。

---

## 二、方案总览

### 核心机制：Effect（前端效果指令）

每个写类工具执行成功后，工具结果附带一个 **effect 对象**，声明「这个操作改变了什么、页面该怎么响应」。SSE 流将 effect 随 run_end 一起发给前端。前端 Aui2Dock 收到后调 `onEffects` 回调，NovelWorkspace 按 effect 类型执行对应的 UI 操作。

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  agent 工具   │────▶│  后端数据已变  │────▶│  effect 指令      │
│ confirm_     │     │  chapter 表   │     │  {refresh, nav,  │
│ chapter      │     │  status 变更  │     │   highlight}     │
└──────────────┘     └──────────────┘     └────────┬─────────┘
                                                    │ SSE run_end
                                                    ▼
                                          ┌──────────────────┐
                                          │  Aui2Dock         │
                                          │  onEffects(effects)│
                                          └────────┬─────────┘
                                                    ▼
                                          ┌──────────────────┐
                                          │  NovelWorkspace   │
                                          │  刷新树/导航/高亮  │
                                          └──────────────────┘
```

### 三层递进

| 阶段 | 覆盖 | 改动量 | 时机 |
|---|---|---|---|
| **Phase 1** | run 结束后按 effect 刷新数据域 | 后端：工具结果加 effect 字段；前端：回调＋按域刷新 | 本迭代 |
| **Phase 2** | agent 主动导航（「让我看看第七章」→ 页面切到第七章） | 新增 navigate 类 UI 工具 | 下一迭代 |
| **Phase 3** | 运行中实时反馈（工具执行过程中页面就刷新，不等 run_end） | SSE 事件流中插入 effect 事件 | 远期 |

**本提案只做 Phase 1**。B/C 方向明确但等 Phase 1 验证后按作家反馈决定是否继续。

---

## 三、Effect 数据模型

### 3.1 effect 对象结构

```ts
interface AgentEffect {
  /** 操作类型（决定前端怎么响应） */
  action: "refresh" | "navigate" | "highlight" | "open_panel";
  /** 受影响的数据域（决定刷新哪些数据源） */
  domain: "chapters" | "volumes" | "settings" | "characters" | "hooks" | "all";
  /** 可选：导航目标（ref/路径） */
  target?: string;
  /** 可选：高亮目标 */
  highlight?: string;
  /** 人话描述（对话里已回执，此处仅日志用） */
  description: string;
}
```

### 3.2 工具 → effect 映射

| 工具 | effect.action | effect.domain | effect.target |
|---|---|---|---|
| confirm_chapter | refresh | chapters | chapter_ref |
| unconfirm_chapter | refresh | chapters | chapter_ref |
| archive_chapter | refresh | chapters | chapter_ref |
| unarchive_chapter | refresh | chapters | chapter_ref |
| add_volume | refresh + navigate | volumes | volume_ref |
| add_chapter | refresh + navigate | chapters | chapter_ref |
| write_volume_fields | refresh | volumes | volume_ref |
| draft_character（采纳后） | refresh | characters | — |
| settings_*（采纳后） | refresh | settings | — |
| 其他写类工具 | refresh | all | — |

### 3.3 effect 的产生位置

**后端**：`_consume` 函数在处理写类工具的 `step_end` 事件时，检查工具元数据中的 `effect` 声明，追加到 `run_effects` 列表。`run_end` 事件携带 `effects: AgentEffect[]`。

**前端**：Aui2Dock 在 onEvent 的 run_end 分支中提取 `effects`，调 `onEffects(effects)` 回调。

---

## 四、前端实现

### 4.1 Aui2Dock 变更

```tsx
// 新增 prop
interface Aui2DockProps {
  // ... 已有 props
  /** agent 写操作后的前端效果回调（NovelWorkspace 实现） */
  onEffects?: (effects: AgentEffect[]) => void;
}

// run_end 分支提取 effects
if (e.type === "run_end") {
  // ... 已有收尾逻辑
  const effects = e.effects as AgentEffect[] | undefined;
  if (effects?.length && onEffects) {
    onEffects(effects);
  }
}
```

### 4.2 NovelWorkspace 变更

```tsx
// 已有的数据加载函数按域拆分，供 effect 精确刷新
const refreshDomain = useCallback((domain: string) => {
  switch (domain) {
    case "chapters":
      refreshChapters(); // 重新拉章节列表＋元数据
      break;
    case "volumes":
      refreshVolumes();
      break;
    case "characters":
      refreshCharacters();
      break;
    case "settings":
      refreshSettings();
      break;
    case "all":
      refreshAll();
      break;
  }
}, []);

// 传给 Aui2Dock
<Aui2Dock
  onEffects={(effects) => {
    // 按 domain 去重后逐域刷新
    const domains = [...new Set(effects.map(e => e.domain))];
    domains.forEach(refreshDomain);
    // 导航（如果有）
    const nav = effects.find(e => e.action === "navigate");
    if (nav?.target) navigateTo(nav.target);
  }}
/>
```

### 4.3 刷新策略

- **按域刷新**：只重拉受影响域的数据（章节列表/设定面板/角色列表），不全量刷
- **去抖**：同一域多条 effect 合并成一次刷新（用 ref 计数或 microtask 合并）
- **兜底**：如果 effect.domain 未知，降级为全量刷新（与现有「刷新」按钮同口径）

---

## 五、后端实现

### 5.1 工具结果携带 effect

每个写类工具的 `ToolResult` 增加 `effect` 字段：

```python
# 例：confirm_chapter 工具
return ToolResult(
    ok=True,
    summary=f"已确认《{ref}》的章纲。",
    effect={"action": "refresh", "domain": "chapters",
            "target": ref, "description": f"确认了 {ref} 的章纲"},
)
```

### 5.2 router._consume 收集 effects

```python
# _consume 中处理 step_end 时：
elif etype == "step_end":
    # ... 已有落库逻辑
    # 收集 effect（写类工具的结果）
    if event.get("effect"):
        run_effects.append(event["effect"])

# run_end 事件时携带
elif etype == "run_end":
    event["effects"] = run_effects  # 注入到 run_end 事件
```

### 5.3 工具注册表声明 effect

每个写类工具在注册时声明其 effect 模板（domain/target 来源），router 从工具元数据读取并填充到结果中。工具函数只需返回业务结果，effect 由注册表元数据自动生成——工具函数不需要手动构建 effect。

---

## 六、评审关注点

### 架构师

1. **effect 声明位置**：方案选择「注册表元数据自动生成」而非「工具函数手动构建」——工具函数只管业务，effect 是声明式的（domain/target 从参数自动推导）。这避免每个工具函数都手动构建 effect 的重复劳动，但要求注册表条目里声明 `effect_domain`/`effect_target_from`（从 args 里取哪个字段当 target）。
2. **race condition**：agent 在后端改数据 → 前端刷新时拉到的数据是 agent 改后的 → 不存在竞态。但如果作家同时在面板里编辑同一数据（未保存的草稿），刷新会覆盖未保存编辑——方案：刷新前检查 dirty 状态，dirty 则跳过刷新并提示。
3. **SSE 事件大小**：effects 数组随 run_end 一起发，不会显著增大事件体（每条 effect 约 100 字节，一个 run 最多 3-5 条写操作）。

### 前端工程师

1. **刷新粒度**：按域刷新 vs 全量刷新——建议按域（chapter/volume/settings/characters），NovelWorkspace 已有按域加载函数，拆开即可。
2. **dirty 保护**：如果作家正在编辑某个字段（未保存），自动刷新会覆盖。方案：刷新前检查 `onDirtyChange` 状态（已有），dirty 则跳过刷新，对话里提示「有未保存的编辑，刷新已跳过」。
3. **导航竞态**：agent 的 navigate effect 可能和作家的手动导航冲突。方案：只在作家当前无编辑焦点时才导航。
4. **Aui2Dock 不需要知道每个域的刷新细节**——它只调 `onEffects(effects)` 回调，刷新逻辑全在 NovelWorkspace。职责清晰。

### 产品经理

1. **作家体验**：agent 说「已确认」→ 页面上第七章立刻变绿。作家不需要切页签或刷新——操作和反馈在同一屏完成。
2. **安全感**：写操作走授权梯度（默认每写必确认），授权卡上看得见改什么。批量写（确认＋归档连续操作）每步都有授权卡。
3. **出错兜底**：写操作失败（网络/权限）→ 对话里出错误卡，页面不变——作家能区分「操作成功」和「操作失败」。
4. **灰度**：Phase 1 可以先只开放「确认/归档/建卷章」三个写工具的 effect，其他写类工具的 effect 后续逐步开放。

---

## 七、场景走查清单（Phase 1 验收用）

| # | 场景 | 操作 | 预期页面效果 |
|---|---|---|---|
| 1 | 确认章纲 | 作家说「确认第七章章纲」→ 授权卡→允许 | 左侧树第七章变绿（已确认态） |
| 2 | 归档章 | 作家说「归档第七章」→ 授权卡→允许 | 左侧树第七章标「已归档」＋计数更新 |
| 3 | 新增一卷 | 作家说「开第二卷」→ 授权卡→允许 | 左侧树出现第二卷＋自动展开 |
| 4 | 新增一章 | 作家说「在第一卷加一章」→ 授权卡→允许 | 左侧树第一卷下出现新章 |
| 5 | 撤回确认 | 作家说「撤回第七章的确认」→ 授权卡→允许 | 左侧树第七章回到草稿态 |
| 6 | 取消归档 | 作家说「取消第七章归档」→ 授权卡→允许 | 左侧树第七章恢复草稿态 |
| 7 | 正常对话不刷新 | 作家问「你是谁」（无写操作） | 页面不刷新（无 effects → 不触发） |
| 8 | dirty 保护 | 作家正在编辑某字段未保存 → agent 执行写操作 | 页面不刷新，对话提示「有未保存的编辑」 |

---

## 八、工作量估算

| 模块 | 工作内容 | 预估 |
|---|---|---|
| 后端 | 工具注册表加 effect 元数据＋_consume 收集＋run_end 注入 | 0.5 天 |
| 前端 Aui2Dock | onEffects 回调＋run_end 提取 | 0.5 天 |
| 前端 NovelWorkspace | refreshDomain 函数＋dirty 保护＋导航 | 1 天 |
| 测试 | 后端 effect 生成钉＋前端刷新钉＋e2e 场景钉 | 1 天 |
| 走查 | 全场景截图验收（8 个场景） | 0.5 天 |
| **合计** | | **3.5 天** |
EOF
echo "design doc written: docs/design/agent-effects-proposal.md"