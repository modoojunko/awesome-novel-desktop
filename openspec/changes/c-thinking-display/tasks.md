## 1. 原型先行（C端 硬性流程）

- [x] 1.1 思考呈现原型已完成并获作者认可（2026-10-20）：`docs/design-c/drafts/ai-novel-c端-思考呈现-原型.html`（真界面基线 HEAD@933cd 实抓＋假 MiniMax 流式服务驱动真实生成链路；六态可交互；自检全过）。已拍板口径：占位行让位、思考框相对列宽（width:100% max 680，与思考字数无关）、四态形态与文案。设计事实源＝认可稿；`prototypes/workbench.html` 的生成区同步与 ADJUSTMENTS.md 登记随本任务收尾时一并执行（apply 首任务）

## 2. 客户端层思考事件通道

- [x] 2.1 `StreamEvent` 增思考类别字段；openai 剥离状态机 STRIPPING 态滑窗外增量以思考事件透出（守卫撤点仍只认正文）；用测试钉「思考事件与正文事件零混入、守卫不因思考事件撤销」
- [x] 2.2 openai 分支读取 `reasoning_content` 增量转思考事件；用测试钉「与 content 并行时两通道无重复」
- [x] 2.3 anthropic 分支 `thinking_delta` 转思考事件；用测试钉「thinking/text delta 分流完整」；三来源共用工况下 tokens 记账口径不变钉
- [x] 2.4 think→prose→think 交错形态（M2 系交错思考）零串道钉
- [x] 2.5 ai_call 行补思考元数据账：`thinking_ms`（流开始至首个正文片段）、`first_char_ms`（生成确认至首字，含拒参重试）、`thinking_chars`；思考全文 SHALL NOT 落日志；测试钉三字段口径（含零思考生成时字段语义）
- [x] 2.6 MiniMax anthropic 用量解析修复：`message_delta.usage.output_tokens` 取到 tokens_out（2026-10-20 实测 0 失真）；测试钉 MiniMax 形态流 tokens 进出齐账

## 3. SSE 转发与前端四态呈现

- [x] 3.1 生成正文链路 SSE 增思考事件形态（正文/阶段/完成/失败事件名不变）；失败/停止事件携带思考缓冲可用性标记（前端超时卡据此保留）；后端转发钉
- [x] 3.2 前端思考期：首个思考增量即切换思考面板（占位行整体让位）——模型名＋已思考秒数（延续等待计时）＋弱化全文（~100ms 节流合批、限高滚动锚尾、全量保留不截断）＋「不进正文」说明；宽度相对正文列、与内容量无关；无思考增量维持既有阶段行（vitest 钉：让位/秒数连续/面板宽度与字数无关/空思考不出现/非文档）
- [x] 3.3 前端收起条与回看：首字到达面板收起为收起条（账目行：思考 N 秒 · 生成 N 秒 · 正文 N 字），可展开回看抽屉（限高滚动）；编辑会话内常驻＋阅读视图保留（vitest 钉：转场/账目/回看/阅读态保留/非文档）
- [x] 3.4 前端超时终局：守卫判死失败转超时卡（正文保持原样＋已到达思考保留可回看＋重新生成入口＋顶条生成指示退场）（vitest 钉：判死转卡/思考保留/指示退场）
- [x] 3.5 e2e 全链一条：思考增量可见（占位行让位）→首字到达转收起条→回看抽屉可开→正文零思考残留→字数不含思考（隔离栈拓扑按 e2e-iso-stack-traps 配置）

## 4. 回归与收尾

- [x] 4.1 后端全量 pytest＋ruff、前端 vitest＋tsc、design:check 全绿；openspec validate 通过
- [ ] 4.2 真机抽检：MiniMax M3.1（anthropic thinking_delta＋面板让位＋回看）、DeepSeek（reasoning_content）、GLM（强制思考形态）各生成一章目验；llm.log 单行账核对 thinking_ms/first_char_ms/thinking_chars 与 tokens 齐账
