# prose-writing delta — c-shortfall-refill

## ADDED Requirements

### Requirement: 字数不足续写补足

- 一次生成完成且 `word_check.below_limit` 为真时，完成卡 SHALL 提供「补足字数」动作：从本章正文末尾**续写**（append），沿用同章 system 恒定层与章级素材，直至触及素材「章末落点」或达字数下限，先到者停。
- 续写 SHALL NOT 改写或丢弃已写正文（作者手动编辑的部分同样原样保留）；SHALL NOT 重掷整章；续写产物经既有分段归一后拼接落库，走正常保存链。
- 续写指令行 SHALL 遵守写链治理口径：章级下限要求可注入，SHALL NOT 投「每场写 N 字」逐场配额；与收尾重申行同词不同句（<8 字机械判据）。
- 补足动作 SHALL 受正文生成同款双门控（会员＋本书模型）；免费档点击 SHALL 拦截且无任何模型调用；续写调用 SHALL 独立留痕计量（operation 族 `write_chapter_refill`）。
- 续写完成后 SHALL 重算 `word_check` 并按新值呈现（达标→动作消失、提示达标；仍不足→动作可再按一次，至多连续两轮后引导整章重生成，不做无限补）；生成中途失败 SHALL NOT 影响已写正文。
- 完成卡无 below_limit（达标）时 SHALL NOT 出现该动作（无感缺省）。

#### Scenario: 一键补足至达标

- **WHEN** 2500 字章首发生成实写 2100 字（低于下限 2250），作者点「补足字数」
- **THEN** 系统从 2100 字末尾续写，产物追加保存，done 事件回传重算的 word_check；达标后完成卡不再显示补足动作

#### Scenario: 补足不碰已写内容

- **WHEN** 作者手改过前半章正文后触发补足
- **THEN** 已写正文逐字保留，仅尾部追加；保存冲突口径走既有正文链

#### Scenario: 连续两轮仍不足则引导重生成

- **WHEN** 作者连按两次「补足字数」后仍低于下限
- **THEN** 动作收口并给出「重新生成整章」引导（沿用既有重生成交互），SHALL NOT 出现第三轮自动可点的补足

#### Scenario: 免费档点击零调用

- **WHEN** 免费档用户在完成卡触发补足
- **THEN** 会员拦截提示，无任何模型调用与用量记录

### Requirement: 写链字数与档位遥测

- 每次正文生成与补足的用量留痕 SHALL 记录：目标字数、实写字数、below_limit 判定、`finish_reason`（含 length＝输出预算耗尽截断判定）——截断型「字数不足」与自愿型「写得短」SHALL 可区分聚合。
- 章级留痕 SHALL 记录该章建议档位（`plot_count_hint` 输出）与实际剧情条数的命中判定，供「抽卡档内命中率」聚合（c-scene-density tasks 5.6 观察项的数据面）。
- 遥测 SHALL 复用既有 TokenLog 加列先例，SHALL NOT 引入外部度量服务或新表；字段口径与生成侧同源函数（`word_target_floor`/`plot_count_hint`）单源，校验与展示不得另立判据。
- 无模型可见文案改动：遥测属记账面，不进 prompt。

#### Scenario: 截断可辨识

- **WHEN** 某章 6000 字目标＋思考模式撞 8192 预算被截断
- **THEN** 该次留痕 below_limit=true 且 finish_reason=length，聚合面与「模型自愿写短」（stop）分桶可查

#### Scenario: 档内命中率可聚合

- **WHEN** 按 c-scene-density 档位抽卡出 6–8 条建议、实采 5 条
- **THEN** 该章留痕记录档位与命中判定（false），命中率报表可聚合出建议档偏离率

#### Scenario: 口径单源

- **WHEN** 调整 `word_target_floor` 系数或档位表
- **THEN** 生成校验、完成卡判定、遥测判定三处同步生效（同一函数），SHALL NOT 出现两处判据打架
