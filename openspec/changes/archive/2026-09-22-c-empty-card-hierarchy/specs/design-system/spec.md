# design-system 能力变更（c-empty-card-hierarchy）

## ADDED Requirements

### Requirement: 中栏空态卡的四档词汇（`.e-empty` 家族）

中栏默认页的空态卡 SHALL 用四档版式层级表达「这一屏在问你什么」，档位与命名固定为：

- **眉标** `.e-empty .be-mark`：小号等宽强调字（mono 10px／字距 .14em／`--accent` 色），放状态类信息
  （设定 N/7 已确认／第N卷 · 名字 已就绪／卷数·章数·字数进度），SHALL NOT 承载提问。
- **主句** `.e-empty .be-k`：19px 展示体＋墨色，放这一屏的提问或主行动语
  （这本书怎么开始？／开始写第一章？／接着写第 N 章？），SHALL 是全卡视觉最重的一行文字。
- **说明** `.e-empty .be-t`：13.5px muted（380 字宽内居中），放一句操作说明。
- **动作** `.e-empty .be-acts`：按钮行（保持既有按钮语言，不新增按钮档位）。

- 四档 SHALL 按「眉标 → 主句 → 说明 → 动作」自上而下排列；三张卡（起手卡／落点卡／书主页卡）SHALL 同批同档。
- `.be-desc` SHALL NOT 使用（该类在共享/业务层均无定义；说明句一律走 `.be-t`）。
- 四档 SHALL 只复用既有共享令牌与字体族（`--accent`／`--fg`／`--muted`／`--font-mono`／`--font-display`），
  SHALL NOT 新增 token、SHALL NOT 触碰两端共享段。

#### Scenario: 三张卡同档

- **WHEN** 依次看到起手卡（0 卷）、落点卡（有卷未排章）、书主页卡（有卷有章）
- **THEN** 三张卡呈现的档位顺序都是 `be-mark → be-k → be-t → be-acts`，提问落在 `.be-k` 上

#### Scenario: 提问是这一屏最重的字

- **WHEN** 起手卡显示「设定 0/7 已确认」与「这本书怎么开始？」
- **THEN** 「这本书怎么开始？」是 19px 主句（`.be-k`），「设定 0/7 已确认」是眉标（`.be-mark`）——
  程序计数 SHALL NOT 成为全卡最大的字
