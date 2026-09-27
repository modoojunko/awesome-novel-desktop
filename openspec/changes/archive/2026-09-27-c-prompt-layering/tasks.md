## 1. 协议与加载器

- [x] 1.1 `prompts/__init__.py`：`<<system>>`/`<<user>>` 标记、`is_layered()`、`load_layers()`（未分层文件向后兼容返回 `("", 全文)`；`## ` 注释行照旧剥离）。验证：分层协议用例 `test_arc_templates_layered`。
- [x] 1.2 进度闸门 `tests/test_prompt_layering.py`：名单外必须已分层、名单内必须尚未分层（名单只减不增）。验证：pytest 该文件绿。

## 2. 首批迁移（主线页四能力，各自独立）

- [x] 2.1 `arc_draft` / `arc_calibrate` / `arc_check` / `arc_tone` 各自分层：system＝角色＋优先级＋禁止项＋任务与输出契约；user＝设定素材＋作者输入；JSON 契约双层花括号转义。验证：`test_arc_templates_layered`（四份分层、system 无动态占位符）＋`load_layers` 双段 format 冒烟。
- [x] 2.2 共享片段 `arc_hard_rules.prompt` 退役（内容各自内联进本模板 system）；端点 `run_arc_ai` 改 `load_layers`，`_SYSTEMS` 删除。验证：`test_templates_scope`＋真机。
- [x] 2.3 arc 测试面按分层改写（`_both`/`_system_of`/`_user_of` 辅助；素材在 user、契约在 system）。验证：`tests/test_story_arc.py` 42 passed。

## 3. 回归与证据

- [x] 3.1 `pytest tests/` 1543 passed；`ruff` 零新增。
- [x] 3.2 真机（隔离栈）：起草主线 HTTP 200、579 字、无「豢养派」、登记势力全在、`name_warnings` 空。
- [x] 3.3 剩余族名单入闸门（拆书卷章／写正文与辅助／设定页其余／角色页／归档反推建书／片段资产），逐族迁移时删名单项。
