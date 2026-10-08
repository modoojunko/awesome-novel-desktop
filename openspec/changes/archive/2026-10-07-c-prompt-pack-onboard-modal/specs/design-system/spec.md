## ADDED Requirements

### Requirement: C端 写作能力弹窗与菜单项词汇

- 「写作能力」引导弹窗 SHALL 复用既有设计系统弹窗骨架（`Modal`/`mcard` 形态与进出场、
  Esc/遮罩关闭、焦点圈行为），SHALL NOT 新造弹窗骨架；进度呈现为分步行（检查版本 →
  下载 → 校验安装）而非百分比环形。
- 弹窗三模式（首装自动／更新确认／手动检查）的标题、进度行、完成行与失败行文案
  SHALL 在 design-language 状态总表登记新行；状态语气沿用既有 info/warn/err 档，
  不新增语气档。（design-vocab.mjs 无新登记项——其机制只辖任意值/opacity 档/禁用
  色板，类名与文案不入其白名单；review-agent 轮 P3 对齐。）
- 账号面板「数据」组「写作能力」菜单项 SHALL 复用 `am-item` 组件词汇与图标位规格
  （与「模型配置 · API Key」同行规），状态随行文案三态：`已就绪 vX`／`未就绪`／
  `有新版本`；面板 foot 的 `am-pack` 小字行词汇与样式 SHALL 随本批退役。
- 用户可见名词延续既有口径：统一「写作能力」，提示词包/pack/manifest/验签/换钥等
  内部词 SHALL NOT 出现在弹窗与菜单项任何文案中。

#### Scenario: 原型先行登记
- **WHEN** 实现写作能力弹窗与菜单项
- **THEN** 书架原型先行登记弹窗三模式变体（含进度行/完成行/失败行）并在 ADJUSTMENTS.md
  留档，design-language 状态总表登记后才落实现（design-vocab.mjs 无涉，机制见上）

#### Scenario: 内部词不进文案
- **WHEN** 检查弹窗三模式与菜单项全部用户可见文案
- **THEN** 仅出现「写作能力」及既有状态词汇；无「提示词包/manifest/验签」等内部词
