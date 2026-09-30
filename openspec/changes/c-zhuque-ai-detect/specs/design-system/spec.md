## ADDED Requirements

### Requirement: 朱雀检测的组件词汇与结果呈现

- 模型配置页页签行 SHALL 使用 `.cfg-tabs/.cfg-tab` 词汇（C端 model-config 作用域，business 层），页签激活态沿 seg 口径（surface 提亮＋fg）；「添加 API Key」按钮的页签级显隐归 zhuque-config 域约束。
- 朱雀检测结果在章标题行的呈现 SHALL 裸排（`.zq-hd` 及 `.hd-top/.hd-bar/.hd-ratio/.hd-act/.hd-errline/.hd-run` 行内词），SHALL NOT 套卡片壳；正文段落标注 SHALL 使用 `.zq-warn/.zq-err/.zq-mark`（m-ok/m-warn/m-err 三语气档＋`.zq-mark.stale` 过期置灰档），挂编辑器作用域（`.editor`），SHALL NOT 挂通用 `.prose` 名。
- 右栏检测行的引导态 SHALL 用 `.ra-step.zq-guide`（虚线变体）、锁定态 SHALL 用 `.ra-step.zq-maxlk`（复用既有锁定视觉：降透明＋cursor not-allowed＋MAX 专属 warn 徽章），SHALL NOT 新发明第四种行形态；徽章 SHALL 用既有 `.pill` warn 语气档。配置面板的 Key 行/统计行/步骤条 SHALL 使用 `.zg-keyrow/.zg-stats/.zg-flow`，显示开关行 SHALL 使用 `.zq-toggle-row`（开关本体复用现役 `.switch-btn` 家族）。
- 「AI 结果统一出卡确认弹窗」条款（见 Requirement: AI 写作助手卡片与结果区组件词汇）的适用域 SHALL 为**有写回语义的 AI 产物**（生成文本、候选、补缺建议等确认后才落库的结果）；朱雀检测是只读测量、无写回动作，其结果 SHALL 就地呈现（章标题区结果条＋正文装饰层），SHALL NOT 强制走出卡弹窗，清除即弃（无确认语义）。本条为该条款适用域的裁定：只读测量类结果与「结果进弹窗」字面冲突时，以本条为准。
- 本条新增词全部为 C端 business 层（book.css / model-config.css 本地段），SHALL 只复用共享令牌，不新增全局 token、不新增状态档位/胶囊形态/字号档位；开关 SHALL 复用现役 `.switch-btn/.sw-track/.sw-knob`，SHALL NOT 另造 `.switch` 样式。

#### Scenario: 检测结果不走卡弹窗

- Given MAX 作者点击右栏检测行且检测成功
- When 查看结果呈现位置
- Then 结果在章标题行右侧与正文标注中就地展示，无弹窗、无确认键；「清除标注」即弃

#### Scenario: 新词通过设计门禁

- Given zhuque 域新词已登记入 book.css / model-config.css 本地段
- When 跑 npm run design:lint 与 design:check
- Then 无禁令违规、基线场景像素差 <0.2%
