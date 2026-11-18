# c-agent-chat-memory 设计

## 1. 前端架构定版

### 1.1 现状与目标

本分支（c-agent-fleet）已实装：Aui2Dock 默认＋`?aui=0` 遗留开关＋AuiErrorBoundary 常驻。本 change 收口三件事：退役旧链、卡面真卡化、text 协议流式。

**退役清单**（删码不删能力）：

| 文件 | 处置 |
|---|---|
| `chat/ChatDock.tsx` | 删（`?aui=0` 分支随 NovelWorkspace 一并移除） |
| `chat/AuiDock.tsx` | 删（assistant-ui spike，选型已定 ChatAnywhere） |
| `chat/SseChatAdapter.ts` | 删（assistant-ui 专用桥） |
| `hooks/useChatSession.ts` | 删（自研状态机；Aui2Dock 走 ref 直控＋SSE 桥） |
| `chat/ChatMarkdown.tsx`、`chatApi.ts` 遗留导出 | grep 引用后删净（判例：删码先 grep 同名引用） |
| `@assistant-ui/react` 依赖 | package.json 移除 |

E2E 中引用 ChatDock testid 的用例随新前端改写（保留行为断言、换选择器）。

### 1.2 卡面体系（customCards）

ChatAnywhere `cardConfig` 注册自定义卡；Aui2Dock 的 SSE 桥把后端事件翻译为结构化消息：

- `artifact` 事件 → 卡消息（kind＋payload 原样透传）→ customCards 按 kind 渲染**既有 CardBody**（复用 ChatDock 时代的卡面组件，零新设计）
- `gate` 事件 → 授权卡消息（gateId/preview/humanOnly）→ customCards 渲染预览＋「允许」「拒绝」按钮 → 点击调既有 `approveGate` 端点 → 卡面状态翻转为已授权/已拒绝（updateMessage 替换）
- `step_start/step_end` → 保持轻量轨迹行（● 工具名 ✓）——ChatAnywhere 内嵌文本即可，不做卡（轨迹是过程信息，卡是交付物，形态分离）

风险项：ChatAnywhere customCards 的注册 API 形状（按 name 匹配消息 data）需小 spike 验证一次再批量挂卡——排在 tasks 第一批。

### 1.3 全模型逐字流式：哨兵分节协议

**问题**：text 协议模型每步输出单个 JSON（`{"thought","action","tool","args","reply"}`），`reply` 是字符串值——从残缺 JSON 里增量抽字符串易碎（转义/嵌套引号），裸流曾泄协议 JSON 到前端（已修回归）。

**方案**：text 模型协议改「叙述先行＋哨兵收尾」，把正文与协议物理分开：

```
（叙述正文——普通文本，逐字显示）
===ACT===
{"action": "final"|"tool", "tool": "工具名", "args": {}}
```

- 后端流式循环按哨兵 `===ACT===` 切分：哨兵前的增量**原样 yield `narration_delta`**（零解析零改写，字节直通）；哨兵后攒全量解析动作 JSON
- 缺哨兵＝整段视为 final narration（action=final 兜底）——模型忘带哨兵不炸流程
- 哨兵行本身 SHALL NOT 出现在任何交付给前端的文本里（切分即剥除）
- 原生 FC 模型（glm/openai vendor）不动——已有 per-chunk narration_delta
- `reply` 字段退役：叙述即正文，不再有两处话术

**连带**：ACT_PROTOCOL 兜底稿改写＋提示词包 `assistant_act` 模板同步（发包走既有提示词包管线，本 change 只改内置兜底稿＋发布挂账）；prompt-pack 冒烟用例补哨兵形状。

**回归钉**：text 分支单测——哨兵前增量逐条 yield / 哨兵后 JSON 正确解析 / 缺哨兵兜底 final / 裸 JSON 永不出现在 narration_delta（deepseek 回归钉保留）。

## 2. 分层记忆

### 2.1 数据模型（两新表，零迁移既有表）

```python
class BookAgentMemory(Base):
    __tablename__ = "book_agent_memory"
    id: int PK
    novel_id: str FK(novels.id, ondelete=CASCADE) + index
    content: Text          # 一条写作规矩/特化知识
    created_at / updated_at

class BookDecision(Base):
    __tablename__ = "book_decisions"
    id: int PK
    novel_id: str FK(novels.id, ondelete=CASCADE) + index
    decision: Text         # 方向性结论（否了什么/定了什么）
    reason: Text | None    # 理由（可空）
    created_at
```

- ~~alembic 迁移两表~~ → **实施修正（勘察发现）**：assistant 模块全部走 create_all 零迁移路径（models/assistant.py 头注释明示「代内 DDL 已退役」），两表随启动自建；novel_id 按本模块惯例为裸列＋索引（无 DB 级 FK），级联走应用层（删书路由显式清理，image_assets 先例同款）——原「FK ondelete 双保险」随之修正为「应用层级联＋测试钉零孤儿」

### 2.2 注入链（L1 拼装序）

`prompts.py` L1 前缀拼装序固化为：**身份 → 作家人格覆盖 → 书级 agent 记忆＋最近决策 → 围栏 → 动作协议 → 页面域纪律**（记忆段插人格之后、围栏之前——身份与围栏是安全段，记忆是数据段，数据段永不挤安全段）。

- 新模块 `assistant/memory.py`：`load_book_memory_section(novel_id) -> str`——agent 记忆全量＋决策按时间倒序；空书返回空串（段整体省略，前缀缓存友好）
- 容量护栏：记忆段字符上限常量（记忆 ~800 字＋决策 ~1200 字，超限决策从最旧截断）；护栏超限只截断不报错
- 前缀缓存：记忆变更频率低，段插在稳定区（身份后）；本轮会话内不重复查库（run 级装载一次）

### 2.3 自维护工具（四工具，封闭注册）

| 工具 | 签名 | 说明 |
|---|---|---|
| `recall_book_memory` | `()` | 返回 {memories:[{id,content,updated_at}], decisions:[{decision,reason,created_at}]} |
| `remember_book_memory` | `(content, memory_id?)` | 增/改（带 id 即改）；透明告知一句 |
| `forget_book_memory` | `(memory_id)` | 删单条 |
| `remember_decision` | `(decision, reason?)` | 追加决策留痕 |

- 注册进封闭工具注册表＋`scopes.py` 全域共享组（所有页签域都可持——记忆是书级跨页签资产）；启动校验覆盖
- **免授权**：四个工具只写记忆表，不碰书稿数据，不进写回授权梯度（与「查设定」同级的低危写）；write_gate 白名单登记
- 注入与工具读同源（`memory.py` 单一实现），避免两套口径漂移（判例：改字段必须全层同改）

### 2.4 与 c-agent-fleet 的关系

fleet（域 agent 委派）是后续 change，本 change 不实现委派；但 scope 分层与注入链是 fleet 的地基——fleet 的域 agent 复用同一 L1 拼装（域 persona 拼在域纪律位），记忆段不动。两 change 无代码冲突面（fleet 尚未开工，0/22）。

## 3. 非目标

- 作家手动编辑书级记忆的 UI 面板（助手工具话术自证已覆盖；UI 挂账后续按需求立项）
- 跨书记忆（「我所有书都……」类偏好）——归作家画像层既有链，不在本 change
- 记忆的向量检索/语义召回——条目量级小（每书十来条），全量注入足够
- assistant-ui spike 复活、ChatDock 兼容层
