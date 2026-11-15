# c-agent-harness 任务

## 1. spike：GLM 原生 function calling 服从度

- [x] 1.1 独立 spike 脚本：GLM 原生 FC 三场景实测（单工具调用/多步串联/参数含中文与长文本）
- [x] 1.2 spike 结论进本 change design.md 附录（通过→native 全量；部分服从→记录边界进能力矩阵；不通过→text 主路径，harness 层保留待供应商修复）

## 2. ToolSpec 标准化

- [x] 2.1 Tool dataclass 增 parameters（JSON Schema dict）；risk_level 已有（复用）
- [x] 2.2 29 工具迁移出 parameters schema（读类 5＋写类＋产卡 9＋发散 2＋kb 4＋画像 2＋设定 7）
- [x] 2.3 args_hint 由 schema 派生生成（text 协议模板引用不变）
- [x] 2.4 registry 守卫测试增 schema 必填断言（每工具 parameters 为合法 JSON Schema object）

## 3. 供应商适配层

- [ ] 3.1 ai_client：chat_stream 增 tools 参数（JSON Schema 下发）＋结构化 tool_calls 返回形态（StreamEvent 增 tool_calls 字段）
- [ ] 3.2 能力矩阵 supports_native_tools(model/vendor)——glm/openai/anthropic 已知支持白名单；未知默认 text
- [ ] 3.3 非流式 chat 同步支持 tools（设定类工具核直调不受影响——纯调用面扩展）

## 4. AgentLoop native 分支

- [ ] 4.1 AgentLoop harness="native"|"text"（路由自能力矩阵；env ASSISTANT_HARNESS 可强制）
- [ ] 4.2 native 循环：结构化 tool_calls → write_gate 授权 → 执行 → tool 结果消息回填 → 循环至收口
- [ ] 4.3 两模式同构件抽公共：墙钟/停止落库（try/finally）/压缩（COMPACTING 信号＋重试＋keep 25%）/apiCalls 归集与事件/线程落盘
- [ ] 4.4 文本协议分支＝现循环原样迁移（解析器＋抢救函数保留）
- [ ] 4.5 GeneratorExit/断开收尾两分支一致（停止落库不丢半截）

## 5. 测试迁移

- [ ] 5.1 FakeClient native 形态（返回结构化 tool_calls）
- [ ] 5.2 loop 核心行为双模式参数化（多步串联/未知工具收口/压缩触发/停止落库/GeneratorExit 干净关闭）
- [ ] 5.3 golden 13 例 native 口径（stub 直返 tool_calls）＋text 口径保留
- [ ] 5.4 路由测试：能力矩阵→模式选择；降级自动切换
- [ ] 5.5 registry 守卫迁移后全绿（schema 断言＋封闭清单不变）

## 6. 走查栈真机验证

- [ ] 6.1 真 GLM native 全链：多步读写（read_progress→draft→产物卡）＋思考回看＋apiCalls 可见
- [ ] 6.2 降级路径实测（强制 text 模式复跑同指令，行为一致）
- [ ] 6.3 停止钮/断网中断：半截落库＋INTERRUPTED 语义
- [ ] 6.4 dock 全功能回归（chips/授权芯片/容量条/？帮助/线程会话零回归）
