## Why

真实用户反馈（2026-11-11）：「这个软件全程让我自己设计，并没有体会到 AI 的便利」——病根是 AI 入口不可见（散装在右栏固定行）、能力不成体系、AI 不主动。对话式原型（docs/design-c/drafts/ai-novel-c端-写作助手对话框-原型.html，已浏览器走查）与四角色两轮评估收敛出结论：**助手必须按「写作 agent」做**——能多步执行、能发散起草、能越用越懂作家的真 agent，而不是按钮换皮的路由器。boss 已拍板六项前提（见 design.md「已拍板决策」），本 change 在独立 worktree（ai-novel-wt-writing-agent）集中实施。

## What Changes

- **新增右栏常驻对话助手（写作 agent）**：跨三视图（初始设定/写作/预览）常驻，每书一会话；agent 循环支持多步工具调用（读书→体检→起草→改稿串联），流式输出思考与叙述。
- **能力围栏（硬边界）**：agent 工具清单物理封闭——只含书内读/写/改接口与本地知识库读/写/改接口；超范围请求助手一律回复「没能力做」。
- **发散模式**：AI 可添人添事出草案（角色组/剧情支线/命名候选），产物带「发散」标记与派生锚点，强制体检前置、过目采纳才落库。
- **授权梯度**：写类操作按档位受控——默认每写必确认（授权卡）/本书授权/全部允许；硬地板清单（删全书/批量删章/覆盖已确认设定/改授权档位）任何档位必弹卡；授权档位本身不进 agent 工具清单（结构性不可自提权）；每笔写入落回执＋可撤销。
- **助手 identity＋作家画像＋定期总结**：结构化助手身份定义（提示词包下发）；作家画像（口味/雷点/节奏）两级存储、面板手填＋对话收集、透明可编辑可清空可暂停；后台定期总结画像（越用越懂作家）。
- **免费档体验**：免费用户＝聊天 agent（多轮对话、大上下文、compact 第一期实现；无轮数闸；吃用户自配 Key）；干活工具 PRO 起、发散 MAX；未配 Key 出引导卡不打断对话流。
- **旧右栏 AI 行收编**：页面注册生效后该页旧 AI 行不再渲染；状态遥测迁对话头部状态槽；富交互弹窗保留（深度编辑场景）。
- **一期完成后续（P1/二期，不在本 change 验收线内）**：知识库外全域检索、会话回看完整 UI、自动采纳审稿人（shadow mode 灰度）、原生 function calling 按 vendor 能力位升级。

## Capabilities

### New Capabilities
- `writing-assistant`: 右栏常驻对话式写作 agent——agent 循环与工具注册表（书内＋知识库读写改的封闭清单）、能力围栏与越界拒答、发散模式纪律、授权梯度与写回撤销、助手 identity、作家画像与定期总结、会话存储与 compact、流式事件契约、档位门控、每页能力注册制与旧 AI 行收编。

### Modified Capabilities

（无——本 change 只新增能力；旧域 spec 的入口收编行为契约由 writing-assistant 承接，旧 spec 整理随归档批处理。）

## Impact

- **代码**：`client/backend/` 新增 `assistant/` 模块（router/loop/actions/tools/context/write_gate/profile/session_store）＋`models/assistant.py` 两张新表；`client/frontend/src/` 新增 `components/novel/chat/` 域＋`hooks/useChatSession.ts`＋`lib/chatApi.ts`＋`lib/chatRegistry.tsx`；`NovelWorkspace.tsx` 壳层布局改造（右栏提壳层跨三视图）；旧右栏组件（Rail/AiAssistPanel/VolumeAssistPanel/AiWriterAssistant）分批收编退役。
- **跨仓**：`awesome-novel-prompts/` 新增助手 identity/system/act/发散/命名等模板＋CURATED/TIER 清单登记＋发布（C 端加载代码零改动）。
- **数据**：本地库新增 `assistant_sessions`/`assistant_messages`/`writer_profile`/`writer_profile_events` 表（create_all 路径，零迁移代码）。
- **工作量基线**：前端 42–52 人日＋后端 ~19 人日（循环/工具/授权/画像）＋提示词包；三路并行 4–6 周历时。
- **风险对冲**：一号工程风险＝BYOK 多厂模型动作格式服从度（文本协议＋抢救＋路由式降级）；一号产品风险＝发散质量（黄金指令集离线评测先行）。
