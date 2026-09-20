## ADDED Requirements

### Requirement: 书架屏垂直节奏（works.html 口径）

书架屏（/novels） SHALL 采用区别于全局壳的屏级垂直节奏（设计真值 `docs/design-c/drafts/works.html`，2026-09-19 实测差异来源）：

- 主区（main）顶距 SHALL 为 40px（全局基线 48px）；
- 页头（page-head）下缘距 SHALL 为 26px（全局基线 36px）；
- 页头副题（.sub）SHALL 无下缘距（全局基线 1em，系旧原型未重置 UA 默认 `p` margin 的显式复刻）；
- 窄屏（≤480px）断点同步：主区 padding 顶距 28px（基线 32px）、页头 gap 14px（基线 16px）、页头下缘距 22px（基线 28px）。

实现 SHALL 以屏级作用域落笔（沿 model-config 屏级节奏先例），SHALL NOT 修改 base.css 全局壳——其余屏（书内工作台、模型配置等）与其各自原型的既有节奏 SHALL 保持不变。parity 基线 `prototypes/list.html` SHALL 与实现同批采用同值，并 SHALL 在 ADJUSTMENTS.md 登记（design-system「Prototype-first flow」既有约束）。

#### Scenario: 桌面视口与 works.html 逐像素一致

- **WHEN** 以同一份四态书数据分别渲染 works.html 原型与应用书架屏（1440×900）
- **THEN** 页头、待完本提示条与卡片栅格的垂直位置一致（卡片栅格顶部较改前上移 31px），`design:check` books/empty/quota/finish 四场景像素差均 <0.2%

#### Scenario: 其余屏节奏不受影响

- **WHEN** 打开模型配置屏（或书内工作台）
- **THEN** 其主区/页头间距与各自原型保持一致，无视觉位移

#### Scenario: 窄屏断点同步收紧

- **WHEN** 视口宽 ≤480px 打开书架屏
- **THEN** 主区顶距 28px、页头 gap 14px、页头下缘距 22px，与 works.html 窄屏断点一致
