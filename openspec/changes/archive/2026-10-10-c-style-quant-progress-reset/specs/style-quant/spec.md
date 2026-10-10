# style-quant Delta — 二次蒸馏进度复位（内测反馈#13 残余）

## MODIFIED Requirements

### Requirement: 蒸馏三步端点与 draft 续跑

- 蒸馏 SHALL 拆为三个请求内端点 `POST /settings/ai/style-distill/step1|step2|step3`＋`POST /settings/ai/style-distill/commit`：step1 逐段标注、step2 统计写法习惯、step3 归纳九维＋作者画像＋禁用词候选。
- 每步产物 SHALL 写入 `style-quant.draft`（含已完成步骤标记）；中断后重新调用 SHALL 从 draft 已有产物续跑（已完成的步骤不再重复调用 LLM）。
- step1 请求带非空 `text` 时 SHALL 视为**新一次蒸馏**：SHALL 清空 draft 全部旧产物后按粘贴文本重跑；粘贴路径 MUST NOT 走续跑短路（否则新样本会被旧产物吞掉）。`text` 缺省或为空时续跑语义 SHALL 保持与历史版本一致。
- 粘贴蒸馏链失败后的重试 SHALL 继续按同一粘贴文本重跑（重试请求持续携带 `text`），MUST NOT 因重试漂移为文件/章节装配路。
- 「不像，再学一次」SHALL 只重跑 step3（保留 step1/2 产物）。
- `commit` SHALL：draft → 正式区＋`history` 追加快照＋`confidence` 落定＋`draft` 清空＋把禁用词候选**服务端** append 进文风 KV 的 `banned_words` 并归一去重（半/全角、大小写归一后跨词表去重）；commit 幂等（重复 commit 同一 draft 不产生重复快照）。
- 所有蒸馏端点 SHALL 挂会员门控（免费 403 `member_required`）与本书模型就绪依赖（无 Key/未选模型给结构化错误）。
- 前端蒸馏进度 UI SHALL 反映**本轮**进度：显式重启（粘贴链带 `text` 从 step1 起跑）时进度状态 SHALL 同步归零——上一轮/旧 draft 的已完成步数 MUST NOT 冒充本轮（否则进度条恒「已完成」、按钮恒「继续蒸馏」）；重启在飞期 SHALL 以三步全未开始呈现。进度归零 MUST NOT 把粘贴链重试拦死：活动粘贴样本存在时「样本不齐」门槛 SHALL NOT 禁用重试按钮。进度 UI 复位 SHALL NOT 改变「关弹窗保留草稿、重开按 draft 续跑」的既有语义。

#### Scenario: 中断后按 draft 续跑

- **WHEN** step1、step2 已完成（draft 有产物）后用户中断，再次点开始蒸馏
- **THEN** 系统跳过 step1/2 直接执行 step3，总耗时只含未完成步骤

#### Scenario: 粘贴重启旧产物作废

- **WHEN** draft 已有 step1/step2 产物，且 step1 请求带新的粘贴 `text`
- **THEN** draft 旧产物被清空，本次及后续步骤只基于粘贴文本重新产出，旧样本的标注与统计不再复用

#### Scenario: 无 text 时续跑不受影响

- **WHEN** step1 请求不带 `text` 且 draft 已有 step1 产物
- **THEN** 返回续跑结果（不重复调用 LLM），行为与历史版本完全一致

#### Scenario: 粘贴失败重试不丢样本

- **WHEN** 粘贴蒸馏的 step1 返回 502，用户点重试
- **THEN** 重试请求仍携带同一粘贴文本并重跑成功；不出现按空文件/章节装配的「样本合计 0 字」错误

#### Scenario: commit 并入禁用词且去重

- **WHEN** 蒸馏产出禁用词「突然」，文风 KV 的 banned_words 已有「突然」
- **THEN** commit 后 banned_words 该词只有一条；蒸馏独有的新词被追加

#### Scenario: 免费用户被门控

- **WHEN** 免费用户调用任一蒸馏端点
- **THEN** 返回 403 member_required，style-quant 无任何写入

#### Scenario: 粘贴重启进度复位

- **WHEN** 旧 draft 停在 step2（进度条显示两步已完成、按钮「继续蒸馏」），用户粘贴新样本重启
- **THEN** 进度条归零——三步呈现为未开始并随本轮推进（不再显示上一轮「已完成」），按钮在飞期显示「蒸馏中…」、失败后回「开始蒸馏」

#### Scenario: 进度复位不改变续跑语义

- **WHEN** 粘贴重启失败后用户「取消」关闭蒸馏面板，再次打开
- **THEN** 仍按 draft 续跑（旧语义不变）——进度复位只作用于显式重启的那一轮

#### Scenario: 复位不拦死粘贴重试

- **WHEN** 本书样本合计不足区间、用户走粘贴链且首试失败（step1 502）
- **THEN** 按钮保持可用（粘贴文本供样本，不受「样本不齐」门槛拦截），重试仍携带同一粘贴文本重跑

