## 根因机制

#766 把 `statusNote={...}` 写在 `<AiWriterAssistant ...>` 开标签 `>` 之后。JSX 中开标签结束后的位置是 children——这一行不是 prop，是一段裸文本节点，值为字面量源码 `statusNote={tab === "prose" && !zqShow ? "朱雀检测已关闭 · 其余可用" : undefined}`。它：

- **编译期全绿**：裸文本是合法 JSX 子节点，tsc／esbuild／运行时都不报错；
- **视觉上是小字注记**：落在卡面尾部，字号小、似说明文案，肉眼易当作有意文案放过（10-08 合入后两天无人报，直至 10-09 用户截图）；
- **无测试咬住**：既有用例只断言「该出现的」，没钉「不该出现的」。

## 裁决

- **归位而非删除**：zhuque-workbench spec 既有 Requirement SHALL 要求开关关时功能性副行注明「朱雀检测已关闭 · 其余可用」，删除即违反 spec；正解＝挪回 props 列表（`data-od-id` 前），走 `AiWriterAssistant` 既有副行优先级（功能性状态 > 调用方注记 > 不显示）。
- **防回归钉「否定断言」**：三例中两例是 `queryByText(/statusNote/)` 形态的字面量否定断言——对「不该出现的东西」钉存在性检查，才咬得住这类静默渲染回归；只钉「该出现的」永远防不住。

## 判据（供后续同类问题）

- 排查法：`grep -rn "propName=" --include="*.tsx"` 逐处看缩进上下文——在 `>` 之前是 prop、在 `>` 之后即 children 文本。
- 高危面：卡头/卡尾的注记槽、`footNote`／`targetLine` 这类字符串 prop 家族——它们最容易被后续重构整段平移时越过 `>`。
