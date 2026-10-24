## ADDED Requirements

### Requirement: 书卡封面版式（两列·拍板 C）

书架「我的作品」书卡 SHALL 呈两列网格：左列为 3:4 竖版封面列（常规宽 104px，圆角、克制投影，高度贯穿卡片主体），右列为信息列，自上而下依次为题材/状态行、标题、简介、统计、分状态页脚与封面来源说明行。封面 MUST NOT 挤入右列顶行的胶囊行；「首字方块＋文字」的旧单列书卡版式退役。

#### Scenario: 有封面书卡的两列呈现

- **WHEN** 书架渲染一张有封面的书卡
- **THEN** 左列 SHALL 显示竖版封面图（object-fit 裁切、不变形），右列 SHALL 完整呈现题材/状态胶囊行、标题、简介、统计与分状态页脚；顶行胶囊行内 MUST NOT 出现封面缩略图

#### Scenario: 无封面有章节的占位即入口

- **WHEN** 书卡无封面且该书有章节
- **THEN** 左列 SHALL 显示带书名字标的竖版占位块，占位块本身 SHALL 是按钮，点击直接打开封面工坊，CTA 文案为「生成封面」

#### Scenario: 0 章书占位弱化

- **WHEN** 书卡无封面且该书 0 章
- **THEN** 左列占位块 SHALL 不可点击，文案弱化为「还没有封面／可稍后添加」，封面入口 SHALL 保留在 ⋯ 菜单「封面…」

#### Scenario: 悬浮换封面

- **WHEN** 书卡有封面且用户悬浮或键盘聚焦封面列
- **THEN** 封面上 SHALL 浮现「换封面」覆盖按钮，点击打开封面工坊；44×44 小方块与常驻「换/＋」角标形态 MUST NOT 再出现

#### Scenario: 菜单第二入口

- **WHEN** 用户打开任一书卡的 ⋯ 菜单
- **THEN** 菜单第一项 SHALL 是「封面…」，点击打开封面工坊；该项对全部书可见（含 0 章书与免费用户，工坊内权益门照常生效）

#### Scenario: 封面来源说明行

- **WHEN** 渲染任一书卡
- **THEN** 卡片底部 SHALL 显示封面来源说明：生成封面显示「AI 封面 · {画风名}」，本地上传显示「本地上传」，无封面显示「封面位留给作者」

#### Scenario: 窄屏封面列缩放

- **WHEN** 视口宽度 ≤820px
- **THEN** 封面列 SHALL 缩到 88px 宽，右列信息自适应换行，卡片 MUST NOT 出现横向溢出

## MODIFIED Requirements

<!-- 头与主 spec 现存双前缀逐字一致（归档 sync 按头匹配）；sync 后按 tasks 4.3 清理双前缀 -->
### Requirement:### Requirement: 上传型封面/头像工坊

前端 SHALL 提供上传型封面/头像工坊，使用阶段 1 的 `POST /api/novels/{id}/image-assets`、`GET .../image-assets`、`POST /api/image-assets/{id}/adopt`、`POST .../undo`、`DELETE /api/image-assets/{id}` 与 `GET .../links`。工坊 SHALL 显示候选、当前图、8 秒撤销倒计时；关闭未采用候选 SHALL 确认或明确“候选保留 24 小时”。采用/撤销后 SHALL 重新拉取书/角色 DTO，不把图片 URL 缓存超过 `url_expires_at`。

#### Scenario: 上传并采用封面

- **WHEN** 用户在书卡通过任一封面入口（无封面有章节的点占位块、有封面的悬浮「换封面」、⋯ 菜单「封面…」）发起添加/更换封面并选择 PNG 上传
- **THEN** 工坊 SHALL 显示候选缩略图，点“使用”后书卡 SHALL 显示新封面，并出现 8 秒撤销入口

#### Scenario: 撤销采用

- **WHEN** 用户在 8 秒内点撤销
- **THEN** 前端 SHALL 调 undo 并刷新书/角色 DTO；超时后撤销入口 MUST 消失

#### Scenario: 签名链接过期

- **WHEN** 图片 URL 的 `url_expires_at` 已过或 `<img>` 返回 403
- **THEN** 前端 SHALL 调 `/image-assets/{id}/links` 换新链接一次，MUST NOT 无限重试

#### Scenario: 免费用户

- **WHEN** 免费用户打开工坊
- **THEN** 上传入口 SHALL 可用；生成/测试/批量入口 SHALL 显示 PRO 提示且不可点
