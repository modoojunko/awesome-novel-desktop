## ADDED Requirements

### Requirement: 执行类工具声明所需能力键

工具注册表 SHALL 为每条执行类工具（书内实体写、知识库写、页面字段写）声明所需能力键 `assistant-execute`；读类与只读检索工具 MUST NOT 要求该键。启动校验 SHALL 拒绝缺少能力键声明的执行类工具（fail loud，不静默放行）；对拍测试 SHALL 枚举注册表并双向断言：执行类工具清单与声明集合一致、读类工具不含该键。

#### Scenario: 缺声明启动失败
- **WHEN** 某执行类工具未在注册表声明 `assistant-execute`
- **THEN** 启动校验以明确错误拒绝加载，指出工具名与缺失键

#### Scenario: 注册表对拍
- **WHEN** 运行工具注册表对拍测试
- **THEN** 所有执行类工具均声明 `assistant-execute`，所有读类/只读工具均未声明，双向无遗漏

#### Scenario: 执行前判定顺序
- **WHEN** 助手调用带声明的执行类工具
- **THEN** 框架先判 `assistant-execute`（无权即回升级事件），有权后再进入既有授权梯度（授权卡/放行）流程
