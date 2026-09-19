## ADDED Requirements

### Requirement: C端 书架阶段徽标四态档位

- C端 书架卡片的阶段徽标（`.b` 家族，C端 业务层专属，与 S端「`.b` 退役」口径无关）SHALL 呈现四态档位，档位-语气映射固定：
  - `setting` 设定中——中性底（fg-soft/muted）；
  - `writing` 写作中——warn 底（进行中的提醒语气）；
  - `ready` 待完本——**accent 底**（可行动召唤：全书已归档、就差完本这个动作）；
  - `done` 已完结——ok 底（完成语气；本 change 前该档语义为「已归档」，语义更名、底色不变）。
- SHALL NOT 新增第四种胶囊形态、SHALL NOT 引入 info/ok/warn/err 之外的新语气词；`ready` 档复用 accent 语义色，SHALL NOT 新造令牌。
- docs/ux/design-language.html §5 状态语言总表 SHALL 同批补「待完本（accent）」「已完结（ok）」两行；两端 `design-vocab.mjs` 若将 `.b` 档位纳入白名单 SHALL 两端同批登记（S端 无此形态，仅登记不生效）。

#### Scenario: 书架徽标四态渲染

- **WHEN** 书架上同时存在设定中/写作中/待完本/已完结四本书
- **THEN** 四张卡片的徽标分别命中 setting（中性）/writing（warn）/ready（accent）/done（ok）四档，无其它形态
