# Proposal: c-battlefield-custom-input

## Why

用户实测反馈（2026-10-29）：题材设定 05「本小说斗什么」缺「自己写一个战场」的入口。考古（git 全历史＋设计原型）：**这不是回归**——设计原型每排胶囊都画了「＋自定义」（ai-novel-c端-题材设定-原型 `capRow`），实现（#347 建页）只给 03 绝对禁止落了输入框，05 自始没有手填口。而数据链路早已留位：`novel_genre_battlefield` 表 `custom_text` 列（「vocab_id 或 custom_text 恰一非空」约束）、`GENRE_LIMITS.battlefieldTextMax(20)` 常量闲置未用、AI 采纳写入自定义文本走的就是同一保存通道。补齐此口子＝零迁移零契约改动。

## What Changes

- 05 格预设胶囊排下加**回车自定义输入框**（同 03 手填形态）：回车落一颗可 × 移除的自定义胶囊；`maxLength = battlefieldTextMax(20)`（启用闲置常量）。
- 输入词与候选**同名／同 id → 落预设勾选**（不造重复胶囊）；重复添加、超 `battlefieldMax(10)` 出 toast 不新增。
- 添加动作不出回执（同 03 自定义禁区）；勾选／取消与 AI 采纳链路原样。
- **不动**：保存契约（battlefield 数组、文本项合法载荷）、右栏 AI 四问、「建议 1-2 个」软提示口径。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `intro-genre-settings`：ADDED「05『本小说斗什么』＝预设胶囊 + 回车自定义」——五格 requirement 的 ⑤ 格补手填口径（预选建议／软提示／AI 四问均不动）。

## Impact

- 前端：`client/frontend/src/components/novel/settings/GenreSettingForm.tsx`（state＋`addCustomBattlefield`＋05 格 `cap-add` 输入框）。
- 测试：`src/__tests__/GenreSettingForm.test.tsx` 补一条（回车自定义 → 可移除胶囊；同名落预设勾选）。
- 后端：零改动——`custom_text` 通道已存在（AI 采纳在用）。
