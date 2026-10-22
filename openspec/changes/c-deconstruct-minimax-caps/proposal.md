# 拆书支持 MiniMax M3.1-Flash

## Why

拆书侧**没有模型 id 白名单**——模型选型由「拆解模型」下拉直接列用户已配置清单里的模型，
真正的闸门在 `deconstruct/capabilities.py::_VENDOR_KNOWN`：按 `{vendor} {model}` 小写子串
匹配能力表（上下文窗口 / 单次输出上限），命中即按该表规划归并预算与拆卡合批；未命中则落
保守默认（32K 上下文 / 8K 输出）。

MiniMax 家族此前不在表内，两个后果：

1. **拆书跑不出完整稿**：归并输出预算只有 8,192，维度顶层合并（characters/relations/
   foreshadow 量级 ≈9-25k tokens）必截，管线按「拆半重试」自愈后仍降级——与 10-20
   《13路末班车》deepseek 降级实证同族。
2. **合批不生效**：能力未登记时 `caps.source` 为 `conservative`，拆卡逐章跑（258 章
   ≈258 次调用），1M 上下文完全用不上。

而 MiniMax M3.1-Flash 正是当前作家实测主力（10-20 思考呈现原型即以
`MiniMax-M3.1-Flash` 驱动真生成），OpenCode Go 官方清单里它在列。

## What Changes

- **能力表登记 MiniMax 家族**：`minimax: ModelCaps(1_000_000, 32_768)`。上下文取官方
  公布的 1M（platform.minimax.cn，2026-10-22 查证：M3.1-Flash／M3 均为 1M）；官方
  **未公布单次输出上限**，故取保守地板 32K——宁小勿大，真上限更低时由既有 400/
  截断拆半自愈兜底（能力表纪律同 deepseek/glm）。
- **OpenCode Go 候选清单补官方 id**：`opencode-go-chat` 增 `minimax-m3.1-flash-free`
  （官方 id 带 `-free` 后缀，走**通用/OpenAI 格式**口）；`opencode-go-claude` 保持
  `minimax-m3`（anthropic 口）——两口各留各的，不混投（混投探针必失败）。
- **效果**：归并输出预算 8,192 → 24,576；拆卡合批逐章 → 12 章/批；1M 上下文解锁
  单遍归并路径（碎片与输出预算均满足时一次出终稿，不生成 reduce 树）。
- **不改**：拆书任务模型选择交互（仍按用户已配置清单列出）、提示词模板、拆书→设定页
  契约、OpenCode Go 思考参数适配（adaptive 裸形态）等既有口径。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本 change 是**能力表数据项**补充：既有「模型能力与调用预算」要求（由
c-deconstruct-resilience ADDED、尚未归档）已规定「能力未知 SHALL 回退保守批次」，
本 change 只是把 MiniMax 家族从「能力未知」补进「能力已知」，不改该要求的行为语义；
`.openspec.yaml` 声明 `skip_specs: true`，先例 c-book-parity-rebaseline。归档时随
c-deconstruct-resilience 一并 sync 进主 spec。）

## Impact

- `client/backend/deconstruct/capabilities.py`：能力表新增一行。
- `client/backend/api_configs/connection.py`：Go·通用候选清单新增一个 id。
- `client/backend/tests/test_deconstruct_resilience.py`、
  `client/backend/tests/test_modelconfig_gemini_go.py`：新增两例钉住。

## Design Impact

（无——纯后端能力表数据与候选清单修正，不触任何界面；拆解模型下拉的数据源未变，
前端零改动。）

## 判例

- **拆书没有模型 id 白名单**，「支持某模型」＝能力表命中；新增模型族只改
  `_VENDOR_KNOWN` ＋（走中转时）候选清单两处。
- 能力表键按**模型名族子串**匹配（大小写不敏感），故 `minimax-m3.1-flash-free`、
  `MiniMax-M3.1-Flash`、`minimax-m3` 三种写法都能命中同一条登记。
- 官方未公布输出上限时取保守地板，而非猜一个上限——猜大了必截（deepseek 旧值教训：
  把非思考默认 8K 当成上限），猜小了只是少省几次调用。
