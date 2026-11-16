# c-tool-flow 任务

## 1. 批1 基座

- [x] 1.1 Tool 执行契约：执行函数返回 dict（成功 `{"<内容键>":…}`／失败 `{"error", "error_type"}`），loop 统一兜异常转 error 结果；`_display` 侧车键规范成文（模型不可见、只给人看）
- [x] 1.2 caps 目录骨架：assistant/caps/__init__.py＋域划分注释；样板域 chapter 三工具（拆下一章/本章剧情/体检）迁 caps/chapter.py
- [x] 1.3 样板域测试：caps 纯函数直测（不再 HTTP 路径构造）

## 2. 批2 chips 结构化触发

- [x] 2.1 chatRegistry chip 增 tool/args 字段（label 保留为人话意图句）
- [x] 2.2 dock 发消息带 tool_hint={tool, args}；chatApi/body 类型同步
- [x] 2.3 router→loop：tool_hint 首步确定性执行（域校验/授权/去重照走），结果回填后模型接管
- [x] 2.4 e2e：点 chip＝首步直执行（不看模型猜话术）＋自由输入回归

## 3. 批3 能力核抽取·章纲域

- [ ] 3.1 plot_simulate 核抽 caps/chapter.py（入参 dataclass：章 ref；出参：推演 rounds）
- [ ] 3.2 chapter_directions/chapter_plot/consistency 核同批抽取；端点改为调 caps
- [ ] 3.3 fleet 三工具改调 caps（不再伪造面板表单/不再直调 handler）
- [ ] 3.4 端点回归 e2e（面板 UI 与对话双皮同核）

## 4. 批4 能力核抽取·设定/卷纲域

- [ ] 4.1 generate_field/run_hooks_ai/intro_ai 核入 caps/settings.py；volume_options/expand/arc 核入 caps/volume.py
- [ ] 4.2 对应七工具迁 caps；端点同调
- [ ] 4.3 设定/卷纲面板回归 e2e

## 5. 批5 自含 AI 提示词工具统一

- [ ] 5.1 统一 AI 调用帮手（建 client/系统提示词/JSON 裁剪/异常归一一套），12 个手搓工具迁移
- [ ] 5.2 契约测试迁移（33 工具×dict 契约＋人话卡面断言）

## 6. 收口

- [ ] 6.1 流程规则四条（去重/域外引导/人话 draft/收口话术）固化进基座＋契约测试
- [ ] 6.2 chips 全页签点击走查＋自由输入回归
- [ ] 6.3 openspec 归档随实现 PR
