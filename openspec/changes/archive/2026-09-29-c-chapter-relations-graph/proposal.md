# c-chapter-relations-graph：角色关系页签图为主表达——剧情关系截至本章上图（#576）

## Why
用户拍板（09-28）：章页面「角色关系」要用**点和边的图**表达角色之间的关系，原型当初设立就是图；真机上却只有一行行变化条目。排查出两层根因：
1. **图从未通过**：`GET /characters/{character_id}`（#357）声明序在 `/characters/graph`（#388）之前，FastAPI 按声明序匹配，"graph" 被当成卡 id 吃掉，端点恒 400「关系图加载失败」——任何页面（含卷视图）都没渲染过这张图；
2. **修好也没边**：章档提取的关系变化只进章作用域子表（设计上「不改初始设定」），图的边只读设定侧 `character_relations`——两套数据面互不相通（实勘用户书 4 卡 0 边、3 条已采纳关系全躺在行里）。

## What Changes（#576=4c0f456d，评审三修=22de584d）
- 路由遮蔽修复：`/graph` 静态段声明挪到 `/{character_id}` 之前＋pytest 回归（实测 main 版红/修复版绿）
- RelationsGraphPane 章打开态并入「截至本章」剧情关系边（`dossier/preview?up_to_ref` 单源＝写章消费同源：已采纳∧已归档∧非 stale，(owner,other) 后章覆盖）：本章采纳边高亮实线、待确认行虚线提案边、未登记名虚线占位节点；同向剧情边覆盖开书设定边；行动作事件重拉即时翻面
- 双向边左法线弓形分侧（待确认虚线不被同对实线盖住）；页签图前置、「本章关系变化」工作流在后；行清单兜底只列开书设定与往章演变边，本章新边沿 #405 口径带 hit 高亮＋「· 本章」标注；卷选中态投影口径不变；右栏 AI 文案同步
- 评审三修：①清单「· 本章」标注回退补回（重写测试删断言≠删行为）；②动作重拉门控改 loadedForRef——换章才显示加载中，事件重拉沿用旧渲染不闪屏；③顺手修 #569 前存**跨域误采纳**：设定页签「全部采纳/驳回」改按 settings/items/knowledge 三域逐域调用（原调 rows_batch 不带 domain，后端缺省域＝全章，会顺带采纳用户在该页签看不到的关系行；API 全章批量能力保留）
- specs：workbench「角色关系页签（全书关系图）」Requirement 重写为「角色关系页签（关系图为主表达）」＋2 个新 Scenario；chapter-dossier「变化分区归属」补图语义＋批量域限制半句

## Capabilities
（skip_specs: true——spec 已随 #576 直接同步 main：workbench＋chapter-dossier 两 capability，validate --specs 70 过；无待归档 delta）

## Impact
工作台角色关系页签＋后端 characters 路由序。门禁：tsc 绿；vitest 972（图用例重写 4 例）；pytest 1696（新 1 例）；chapter-dossier e2e 2/2（待确认虚线→工作流采纳→图即时翻面链，事件通道首个真机覆盖）；隔离栈真机截图核验（4 卡＋3 采纳＋1 待确认形状）。CI 额度仍锁按先例 admin 合入，main 补验待 Actions 恢复。
