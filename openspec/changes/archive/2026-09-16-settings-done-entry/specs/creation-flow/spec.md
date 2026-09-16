# creation-flow 变更（增量）

## ADDED Requirements

### Requirement: 设定完成入口（去写作）

设定 8 项全部确认（done === total）且存在「去写作」出口时，设定页左栏进度行 SHALL 升级为完成卡：行头对勾图标＋「设定完成 8/8」＋「全部就绪」徽标，整块 ok-soft 底＋ok 描边，进度条满格转绿，块内展开主 CTA「去写作」；CTA 下方 SHALL 保留一行小字「写作时也能回来改设定，不冲突」。未完成（done < total）时进度行 SHALL 保持现状样式，SHALL NOT 出现完成卡。点击「去写作」SHALL 切换到写作视图（onGoWrite 契约不变）。改版前的全宽普通主按钮「设定完成 · 去写作」SHALL 从左栏移除。

#### Scenario: 全部确认后出现完成卡

- **WHEN** 设定 8 项全部确认，作者回到设定页
- **THEN** 左栏进度行升级为完成卡：对勾＋「设定完成 8/8」＋「全部就绪」＋「去写作」CTA

#### Scenario: 去写作切换视图

- **WHEN** 作者点击完成卡上的「去写作」
- **THEN** 应用切换到写作视图（原 onGoWrite 行为）

#### Scenario: 未完成不出现完成卡

- **WHEN** 设定仅 7 项确认
- **THEN** 左栏保持普通进度行，SHALL NOT 出现完成卡

#### Scenario: 旧按钮退役

- **WHEN** 进入设定页任意状态
- **THEN** 左栏不再出现「设定完成 · 去写作」全宽普通主按钮
