# c-dossier-ia-revert：变化分区归属——撤「章档」页签（#569，用户设计纠偏）

## Why
用户拍板（09-28 晚）：归档提取的变化**不设独立页签**——立项 grill 第三轮用户答「章的设定、角色关系、文风、伏笔等」＝各归各的现有页签，被实施方过度具体化为新「章档」页签＋新概念（IA 走偏）。教训已入档：Other 自由答案必须复述确认具体形态再动手。

## What Changes（#569=e2e31480）
- 删「章档」页签与 DossierPane；新 ChangesSections：设定页签区块（设定按世界设定子领域分组：舞台/世界铁律/大事年表/势力/更多细节＋物品＋角色认知）＋角色关系页签区块
- 进度/失败/逃生阀/未提取补提取只在操作页签归档卡（新增 archive-backfill 入口＋「去模型配置」指引）
- 前端「章档」字样全量退役（后端 API/表/specs capability 名保留＝机器层）
- 提取模板 area 对齐世界设定子领域词表
- spec chapter-dossier「章档页签」Requirement 重写为「变化分区归属」（随 PR 直接同步 main spec）；与 #565 衔接：SettingsChangelogPane 不动，变化分区置于其上

## Capabilities
（skip_specs: true——spec 已随 #569 直接同步 main：chapter-dossier 的 Requirement「章档页签（工作台）」重写为「变化分区归属（工作台）」，validate 69 过；无待归档 delta）

## Impact
工作台 IA；vitest 970（ChangesSections 7 例新写）/pytest 1693/新 e2e 4/4＋受影响链 28/29（唯一挂＝plot-sim 免费态存量红）。
