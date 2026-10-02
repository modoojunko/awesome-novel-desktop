## MODIFIED Requirements

### Requirement: 免费版（无套餐）AI 可见 + 锁定

- 无套餐用户 SHALL 仍可看到「AI 写作助手」卡片，但其为**可见 + 锁定**：整体降透明、PRO 徽标转灰、各能力行降透明且不可点（cursor:not-allowed），每行名称/描述仍可见。
- 点击锁定行 SHALL 给档位感知的统一升级提示（文案出自单源 helper、按该行 feature key 的最低档出口径——免费用户提示「开通解锁」类；SHALL NOT 硬编码「升级 PRO」字面量：标准档已解锁的件对免费用户不得误导为「升级 PRO」，MAX 件须出 MAX 口径），SHALL NOT 各自弹窗。
- 免费版写作能力 SHALL 完整（人工路径零差异）。

#### Scenario: 免费版 AI 卡片锁定

- Given 无套餐用户进入简介/题材设定
- When 查看 AI 写作助手卡片
- Then 三个/五行能力可见但整体降透明、点击给档位感知升级提示、不生成结果
