## ADDED Requirements

### Requirement: 题材目录选择工具

助手 SHALL 具备「按标题选 01 题材目录」的能力，与题材四格（爽点/红线/代价/战场）区分：

- 只读工具 `read_genre_catalog` SHALL 返回封闭题材目录（`genres/theme_catalog.py` 的全部大类与子类，含解读与案例），供模型按书名/简介判断；SHALL NOT 允许模型自造目录外题材。
- 产卡工具 `settings_genre_pick` SHALL 接收 `theme`（必填）、`sub_genre`（可空）、`note`（理由，可空），并按目录校验：大类不存在或子类不属于该大类时 SHALL 返回可读的可选清单（不抛裸异常、不落库）。
- 合法调用 SHALL 产出采纳卡，payload 为 `{stype:"genre", field:"catalog", value:{theme, sub_genre, note}}`；工具 SHALL NOT 直接写设定（写回只在作家点采纳后发生）。
- 助手在作家说「选/定/判断/推荐题材」「这本书算什么题材」时 SHALL 优先使用上述两工具；SHALL NOT 用 `settings_genre_core_promise` 等四格工具顶替「选题材」。说「爽点/红线/代价/斗什么」时才用四格工具。
- 两工具 SHALL 在设定域（`set:` 线程）声明；读工具免档位，产卡工具沿用 `settings-ai-fields` 档位。
- 设定域内，作家消息命中「根据/按标题选/定/判断/推荐题材」「这本书算什么题材」时，循环 SHALL 首步确定性调用 `read_genre_catalog`（显式 chip tool_hint 优先；域外不触发），确保目录真值进入当轮上下文。

#### Scenario: 按标题推荐题材
- **WHEN** 作家说「根据标题，帮我选定题材」
- **THEN** 助手先读题材目录，再给出一个大类＋子类（或仅大类）的推荐卡，含推荐理由；不产出爽点/红线等四格卡

#### Scenario: 目录外题材被拒
- **WHEN** 模型传入目录外的 `theme` 或不属于该大类的 `sub_genre`
- **THEN** 工具返回可选清单的人话提示，不产卡、不写库，模型可改对后重试

#### Scenario: 采纳写回 01 题材
- **WHEN** 作家在题材推荐卡点「采纳 · 写入」
- **THEN** 写回本书 `theme`/`sub_genre`，其余题材四格与设定字段保持不变，并给可读回执
