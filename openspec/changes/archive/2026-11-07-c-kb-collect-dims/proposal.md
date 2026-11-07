# c-kb-collect-dims · 拆书收录扩维＋版本收敛——以全本为准重建四维收录

## Why

真机评估实锤（2026-11-07，斩神/749 数据）：①存量收卡只收了角色（旧代码时代），文风/文笔/手法/世界
产物从未入库——文风等页签空的真因；②同书先试拆后全本，幂等键带任务 id 跨任务永不撞键 → 双版本素材
并存（749 两版 72 份）、全本只收 8/26 角色；③收卡从不写书名（src_novel_name 恒空），实例出处行
结构性无值。现 main 的四维映射早已就绪（dry-run 斩神 103 条：手法 27/文风 1/文笔 17/世界 48/角色 10）。

## What Changes

- **版本收敛**（kb/version_reconcile，读面自愈挂点、幂等、失败不抛）：同书按书分组找 canonical
  （completed 章数最大）→ 拆除该书拆书素材＋转生实例（text=instruction 确定匹配）＋变空知识点
  （同题材他书共用者保留）→ 以现行四维映射重收 canonical → 重跑总结；app_meta 标记 book→canonical
- **收卡落书名**：collect_task_to_kb 给素材写 task.book_name——素材/转生实例的「源自：书名」从此有源
- 存量空书名素材经任务行反查并入收敛分组（src_ref→deconstruct_jobs.book_name）

## Impact

- 后端：kb/version_reconcile.py（新）、kb/deconstruct_import.py（书名落值）、kb/migrate_library.py
  （自愈链挂点）、tests/test_kb_version_reconcile.py
- spec：knowledge-base「素材收录与总结」相关条款同步
