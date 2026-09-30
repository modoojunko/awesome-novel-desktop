## MODIFIED Requirements

### Requirement: 朱雀页签文案口径

- 朱雀页签 SHALL 全档可见、可进入、可配置（Key 是作者自己的腾讯资产）；ai-detect 权益门禁 SHALL 落在使用口（工作台检测行），配置页 SHALL NOT 阻挡配置动作。
- 介绍与引导文案 SHALL 表述：朱雀是腾讯的 AIGC 检测；本功能为 PRO 会员权益（试用不含）；需自备腾讯云 Key；每月 50 万 token 免费额度为活动口径、以腾讯云为准。SHALL NOT 出现「永久免费」「企业资质必需」等表述；额度耗尽口径 SHALL 为中性指引（等下月或按腾讯云控制台指引购买）。
- 获取 Key 引导 SHALL 为横向三步（注册腾讯云并个人实名 → EdgeOne 控制台 Makers 创建 API Key → 回填保存），附控制台与朱雀网页版试用两个外链；个人实名口径 SHALL 明示「不需企业资质」。
- 隐私警示条 SHALL 表述：检测会把整章正文发送到腾讯朱雀服务做判定、本机不参与打分、介意送稿的章节请不要使用。

#### Scenario: 非会员可配置不被拦

- **GIVEN** 无 ai-detect 权益的作者（免费/试用）进入模型配置页朱雀页签
- **WHEN** 作者粘贴 Key 并保存
- **THEN** 配置成功可完成（页签无会员拦截）；工作台检测行呈锁定态（见 zhuque-workbench）
