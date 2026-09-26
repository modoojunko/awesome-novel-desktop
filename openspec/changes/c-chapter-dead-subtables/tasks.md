## 1. 存储摘除

- [ ] 1.1 `models/chapter.py`：删三张子表类（`ChapterKnowledgeState`/`ChapterDowntimeFunction`/`ChapterKeyChoice`）＋三个 relationship；`models/__init__.py` 同步摘导出。验证＝新代库 `create_all` 后无三张表；全仓 grep 无悬空引用
- [ ] 1.2 `chapters/store.py` 三处收口：① `assemble_chapter` 停止输出 `memo.downtime_functions`/`memo.key_choices`/`knowledge_states`；② `_CHILD_ATTRS` 去掉三项；③ `_replace_children_impl` 删三段显式赋值与对应模型导入；`_split_labeled` 随唯一消费方删除。验证＝专项测试：含三键的章保存一次 → 装配不含三键 ＋ 留存字段逐字不变
- [ ] 1.3 `backup/importer.py`：`_RETIRED_CHAPTER_TOP` 扩容纳入三张子表键；`memo.downtime_functions`/`memo.key_choices` 纳入 retired-key 计数。验证＝v5 包导入后报告计数含三键、不落库不报错
- [ ] 1.4 `backup/format.py`：FORMAT_VERSION 5→6（删键＝升版，读窗沿既有 N-1 豁免）

## 2. 测试收缩与专项

- [ ] 2.1 `test_volume_chapter_crud`／`test_backup_roundtrip`／`test_workflow_api`／`test_export_db_zip` 中三子表的种子与断言收缩。验证＝后端 pytest 全绿
- [ ] 2.2 `test_og_slim_v2_retire.py` 的 retired 集合扩容（三张子表键进「忽略 N 处」断言）。验证＝新增用例通过
- [ ] 2.3 旧库迁入核对：含三张子表整表的旧库走列交集，报告如实列跳过、源库零接触

## 3. 回归与门禁

- [ ] 3.1 后端 pytest 全绿（记录用例数）；`ruff --select F401,F811,F841,F821` 本章触达路径回到基线
- [ ] 3.2 前端零改动核对：`grep -rn "knowledge_states\|downtime_functions\|key_choices" client/frontend/src` 无读取点（既有事实核对，非本次改动）；vitest/tsc 不回归
