## ADDED Requirements

### Requirement: 拆书与导入的档位门禁

正文导入（只带正文的直接导入开书）SHALL 免费开放，SHALL NOT 挂任何 feature key。AI 拆书（新建任务/续拆/重试上传/产物导出 markdown）SHALL 归 feature key `deconstruct`（PRO 起发放、trial 同权）；拆书产物一键建书（设定/文风等灌成新书）SHALL 归 feature key `deconstruct-import`（仅 MAX 发放，trial 不含）。任务清单/任务详情/产物预览/取消/删除 SHALL NOT 设门（免费存量任务只读保留）。入口 SHALL 可见＋锁定，锁定态点击走对应档位的升级出口；后端 MUST 真拦，SHALL NOT 只靠前端置灰。旧权益快照不含新 key 时，未过期且档位达标的用户 SHALL 隐式放行（`deconstruct` 按 PRO、`deconstruct-import` 按 MAX；standard/free/过期仍锁）。

#### Scenario: 免费正文导入不受限

- **WHEN** 免费用户使用正文导入开书
- **THEN** 流程可完整走通，MUST NOT 出现 403 或升级拦截

#### Scenario: 免费新建 AI 拆书被拦

- **WHEN** 免费/标准用户提交 AI 拆书任务
- **THEN** 后端 MUST 返回 403（member_required/feature_required），不产生任何模型调用

#### Scenario: PRO 可拆可导出、不能建书

- **WHEN** PRO/trial 用户在完成态分别选择「导出 Markdown」与「建书」
- **THEN** 导出成功；建书 MUST 返回 403 且 tier_required=max

#### Scenario: MAX 一键建书

- **WHEN** MAX 用户在完成态选择「建书」并确认
- **THEN** 建书链路正常执行（幂等口径不变）

#### Scenario: 旧快照隐式放行

- **WHEN** 未过期 pro/max 用户的完整旧快照缺少 deconstruct/deconstruct-import
- **THEN** 后端按 key 最低档隐式放行（deconstruct 放行 pro/max/trial；deconstruct-import 仅放行 max/lifetime；standard/free/过期仍锁）
