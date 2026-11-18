# writing-assistant Delta

## MODIFIED Requirements

### Requirement: 助手以右栏常驻对话形态存在且跨视图连续

右栏 SHALL 整栏渲染为对话助手（对话前端以 @agentscope-ai/chat 定版，见 assistant-chat-ui 能力），跨初始设定/写作/预览三视图常驻不卸载；每本书一个会话，切换页面/视图 SHALL 保留对话流，并在流内落页面切换分隔标记。窄屏（≤840px）SHALL 降级为悬浮球＋抽屉形态。生成进行中切换页签/点结构树 SHALL 走与正文流式一致的确认守卫。

#### Scenario: 切换页面对话保留
- **WHEN** 作家在卷纲页与助手对话后切换到设定·角色页
- **THEN** 对话流原样保留并出现页面切换标记，能力盘 chips、上下文徽标、输入框占位文案随之切换为角色页配置

#### Scenario: 流式中切换页签
- **WHEN** agent 正在多步执行且作家点击其他页签
- **THEN** 弹出与正文流式同口径的确认守卫，取消则留在当前页
