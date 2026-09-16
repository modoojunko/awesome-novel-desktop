# style-quant 变更（增量）

> 基线依赖：本 delta 以 style-settings-v2 归档后的 style-quant spec 为基线；style-settings-v2 须先归档 sync。

## MODIFIED Requirements

### Requirement: 蒸馏三步端点与 draft 续跑

- 蒸馏 SHALL 拆为三个请求内端点 `POST /settings/ai/style-distill/step1|step2|step3`＋`POST /settings/ai/style-distill/commit`：step1 逐段标注、step2 统计写法习惯、step3 归纳九维＋作者画像＋禁用词候选。
- 每步产物 SHALL 写入 `style-quant.draft`（含已完成步骤标记）；中断后重新调用 SHALL 从 draft 已有产物续跑（已完成的步骤不再重复调用 LLM）。
- 「不像，再学一次」SHALL 只重跑 step3（保留 step1/2 产物）。
- `commit` SHALL：draft → 正式区＋`history` 追加快照＋`confidence` 落定＋`draft` 清空＋把禁用词候选**服务端** append 进文风 KV 的 `banned_words` 并归一去重（半/全角、大小写归一后跨词表去重）；commit 幂等（重复 commit 同一 draft 不产生重复快照）。
- 所有蒸馏端点 SHALL 挂会员门控（免费 403 `member_required`）与本书模型就绪依赖（无 Key/未选模型给结构化错误）。

#### Scenario: 中断后按 draft 续跑

- **WHEN** step1、step2 已完成（draft 有产物）后用户中断，再次点开始蒸馏
- **THEN** 系统跳过 step1/2 直接执行 step3，总耗时只含未完成步骤

#### Scenario: commit 并入禁用词且去重

- **WHEN** 蒸馏产出禁用词「突然」，文风 KV 的 banned_words 已有「突然」
- **THEN** commit 后 banned_words 该词只有一条；蒸馏独有的新词被追加

#### Scenario: 免费用户被门控

- **WHEN** 免费用户调用任一蒸馏端点
- **THEN** 返回 403 member_required，style-quant 无任何写入
