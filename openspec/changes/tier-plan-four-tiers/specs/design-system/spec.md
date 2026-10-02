## MODIFIED Requirements

### Requirement: Free vs PRO gating stays visible

- 会员专属能力（各档位）SHALL keep their entry points visible to lower-tier users in locked form with one sentence describing what unlocking provides; hiding entries is the documented exception requiring compensating notice.
- Gating vocabulary in UI text SHALL avoid internal terms (gate/readiness/license errors); it describes what is missing and how to proceed（补救语句带可点击出口）。
- **档位感知锁文案**：同一锁定行对不同用户 SHALL 呈对应口径——免费用户「开通解锁」类、标准用户对 PRO/MAX 件「PRO 专属 / MAX 专属」、PRO 用户对 MAX 件「MAX 专属」；文案出自单一 helper（输入 minTier），SHALL NOT 在组件内散写字面量。

#### Scenario: Free hits project limit

- Given a free account already has the maximum number of projects
- When they view the shelf
- Then create/import appear locked with an upgrade path rather than being hidden

#### Scenario: 同一锁行按档位出文案

- Given 免费/标准/PRO 三位用户分别查看工作台右栏同一 AI 行
- Then 三人分别看到「开通解锁」「PRO 专属」「MAX 专属」口径（按该行 minTier 与用户档位推导），形态一致仅文案分档

## ADDED Requirements

### Requirement: 档位徽标与档位名词表

- 顶栏/账号面板/偏好弹窗的档位徽标（pill）SHALL 支持 standard/pro/max 三档会员态＋免费/试用态，语气词沿用 info/ok/warn 族：免费=中性、试用=warn（临期转 err 遵循既有口径）、三档会员=ok；SHALL NOT 新增第四种胶囊形态与新语气词。
- 档位显示文案 SHALL 取服务端下发的 display_name（单源），前端不写死档位中文名。
- docs/ux/design-language.html §5/§13 与两端 design-vocab.mjs 若登记档位词 SHALL 两端同批。

#### Scenario: 五态档位徽标

- **WHEN** 五类档位用户（免费/试用/标准/PRO/MAX）查看顶栏徽标
- **THEN** 徽标分别命中中性/warn/ok/ok/ok 底色且文案为 display_name，无新形态
