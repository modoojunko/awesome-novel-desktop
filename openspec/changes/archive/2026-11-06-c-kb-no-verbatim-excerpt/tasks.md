# 任务：拆书收录不产原文示范段条目＋收录即建实例

## 1. 映射口径

- [x] 1.1 `kb/deconstruct_import.py`：删除 style.examples → 示范段条目的映射，改为计数并追加 warning（「原文示范段 N 条不入库（逐字原文，版权红线）」）
- [x] 1.2 移除不再使用的 `_MAX_STYLE_SAMPLES` 常量

## 2. 收录即建实例

- [x] 2.1 `collect_task_to_kb` 落库循环内为每条新知识建第 1 条实例（文本=指令、来源=拆书＋书名、quote=证据/例），不依赖启动迁移

## 3. 数据清理

- [x] 3.1 应用库（novel-v0.45.1.db）删除 12 条示范段条目（连 kb_entry_tags / kb_knowledge_instances 级联）

## 4. 测试

- [x] 4.1 映射测试：示范段不产出＋warning 文案断言；文风仅剩叙事身份
- [x] 4.2 收录测试：收录后实例即时可见（数量=收录数、来源=拆书、书名断言）＋ 启动迁移幂等不重复
- [x] 4.3 迁移测试：`has_ver` 断言补使用（修 RUF059 未用变量，main Lint 红）

## 回归

- 后端：`pytest tests/test_kb_deconstruct_import.py tests/test_kb_match_emotion.py tests/test_kb_knowledge_migration.py` 15 passed；`pytest tests/test_kb*.py tests/test_deconstruct_api.py` 275 passed（ruff --extend-select F811,F821,F841 通过）
- 真机：应用库 210 条拆书条目（222−12 示范段），知识库页都市题材各类别可见，抽屉无原文三屏重复
