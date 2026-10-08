## MODIFIED Requirements

### Requirement: 免费/PRO 两态

- 两态 SHALL 由本书 ai_state 单源驱动：ready＝可用；member_required＝整卡可见＋锁定（降透明＋锁形标），点击任一 AI 入口统一提示档位感知文案（单源 helper，按目标 feature key 的最低档出「开通解锁/PRO 专属/MAX 专属」口径；SHALL NOT 硬编码「升级 PRO」字面量）且不发出请求；no_key→引导去模型配置；missing_model/invalid→面板内引导选模型
- 卡头文案 SHALL 只有档位角标（随套餐：免费版／标准会员／PRO 会员／MAX 会员）＋标题，SHALL NOT 出套餐文案（各档差异由能力行可用性体现）；面板内部套餐词（如「Max 同享」）SHALL NOT 出现
- 免费态字段 SHALL 照常手写（手填功能不受限），锁定仅限 AI 入口

#### Scenario: 免费版点击拦截

- **WHEN** 免费版作者点击任一 AI 行或行内「AI 帮我填」
- **THEN** 卡片呈锁定态，弹档位感知统一升级提示，不发出 AI 请求

#### Scenario: 免费版手填不受影响

- **WHEN** 免费版作者手写全景与结局三问并确认
- **THEN** 保存与确认流程与会员档完全一致
