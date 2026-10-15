## 1. 原型先行（C端 硬性流程）

- [ ] 1.1 `prototypes/workbench.html` 生成区增加「模型思考中」思考流式呈现样式（弱化行内＋滚动窗口＋计时同 行），ADJUSTMENTS.md 登记偏差；design:check 矩阵复跑通过

## 2. 客户端层思考事件通道

- [ ] 2.1 `StreamEvent` 增思考类别字段；openai 剥离状态机 STRIPPING 态滑窗外增量以思考事件透出（守卫撤点仍只认正文）；用测试钉「思考事件与正文事件零混入、守卫不因思考事件撤销」
- [ ] 2.2 openai 分支读取 `reasoning_content` 增量转思考事件；用测试钉「与 content 并行时两通道无重复」
- [ ] 2.3 anthropic 分支 `thinking_delta` 转思考事件；用测试钉「thinking/text delta 分流完整」；三来源共用工况下 tokens 记账口径不变钉
- [ ] 2.4 think→prose→think 交错形态（M2 系交错思考）零串道钉

## 3. SSE 转发与前端呈现

- [ ] 3.1 生成正文链路 SSE 增思考事件形态（正文/阶段/完成/失败事件名不变）；后端转发钉
- [ ] 3.2 前端按事件名分流：思考缓冲＋~100ms 节流渲染＋滚动窗口上限（先 2000 字符），「模型思考中」阶段弱化行内呈现；无思考增量维持既有阶段文案（vitest 钉：流式可见/退场即销毁/不进文档不计数/空思考区不出现）
- [ ] 3.3 e2e：思考增量可见→首字到达退场→正文零思考残留全链一条（隔离栈拓扑按 e2e-iso-stack-traps 配置）

## 4. 回归与收尾

- [ ] 4.1 后端全量 pytest＋ruff、前端 vitest＋tsc、design:check 全绿；openspec validate 通过
- [ ] 4.2 真机抽检：MiniMax M3（内联）、DeepSeek（reasoning_content）、GLM（anthropic thinking_delta）三形态各生成一章目验
