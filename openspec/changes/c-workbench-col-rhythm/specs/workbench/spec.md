## ADDED Requirements

### Requirement: 中栏节奏单源（内容衬垫与版心）

书内三栏页的中栏内容节奏 SHALL 以单源变量定义一次（`.wb .view.on.three-col` 作用域）：内容衬垫 `--col-pad-t/-x/-b`（26px / clamp(20px,4vw,48px) / 60px，book.html 口径）与表单版心 `--col-measure`（76ch）；卷/章编辑区节奏 SHALL 以 `--col-pad-editor`（18px 22px 24px，storyline `.e-pad` 口径）单列。全部**内容型面板** SHALL 继承单源衬垫而非各自声明：

- 章页签：`.og-pane`/`.prompt-pane`/`.settings-pane`/`.style-pane`/`.relations-pane`/`.actions-pane`/`.hooks-wrap` 左右内容衬垫 SHALL 一致（同值同源）；
- 设定视图（settings-v）各面板 SHALL 具备列级内容衬垫；行级内容（文风表单行/操作卡等）SHALL 不超过 `--col-measure`；（写作空态由并行 change `c-0vol0ch-empty-state` 按新原型处理，不在本条范围）
- **通栏构件**（e-head／页签条／设定页 panel-head 与 panel-foot）SHALL 保持左右出血（不因内容衬垫而缩进），文字与内容对齐；
- **版心**：面板默认版心 660px（book.html `.panel`）；豁免清单 SHALL 显式声明且仅此三处——设定页 1180 上限（贴 AI 栏的既有决策）、`sub-fill` 双栏（角色/伏笔满栏）、卷壳面板（其字段自带 76ch 约束）。
- 实现 SHALL NOT 再以「先整列归零 `.col-panel`/`.panel`、再逐面板补衬垫」的模式维护节奏；新增面板 SHALL 自动继承单源。

#### Scenario: 设定页不再贴边

- **WHEN** 打开设定视图任一面板（简介/题材/世界/角色/主线/文风/伏笔）
- **THEN** 中栏内容左右具备列级衬垫（1440 视口下 48px），面板版心不超过声明上限（设定域 1180 / 其余 660），底部保存条保持通栏

#### Scenario: 章页签节奏一致

- **WHEN** 在章视图依次切换章纲/正文/提示词/设定/文风/角色关系/伏笔/操作页签
- **THEN** 各页签内容左右衬垫一致（同源变量），表单内容宽度不超过版心；正文阅读区（独立排版 680 居中）与卷视图（e-pad 18/22/24）节奏不回归

#### Scenario: 通栏条保持出血

- **WHEN** 查看章头部（e-head）、页签条（ch-tabs）或设定页底部保存条
- **THEN** 其底边线/顶边线仍横跨整栏（不因面板衬垫而缩进），条内文字与内容区左对齐
