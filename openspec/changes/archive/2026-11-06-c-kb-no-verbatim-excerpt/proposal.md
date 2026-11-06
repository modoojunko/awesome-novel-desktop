# 拆书收录：原文示范段不进知识库

## Why

真机反馈（2026-11-04，222 条拆书条目验收）：拆书收录的「文风·示范段」条目，其知识定义、实例文本、正例三处全是**逐字小说原文**（如「十几年了，十几年了，陆鼎终于看到了金手指解锁的希望……」）——同一屏重复三遍，作家读到的是别人的正文而不是可复用的写法；逐字原文入库同时踩版权红线。

「原文示范段」的本职是**书内写作时的文风 few-shot 示例**（style_samples 键，随建书进入设定页），不是知识库里的可复用知识——知识库应存提炼后的写法（怎么用），示范原文留在拆书产物与书内设定里随取随用。

内容仓批量工具已同口径（原文示范段只计数不入库）；本 change 把 C 端拆书收录路径对齐。

## What Changes

- 拆书收录映射（`kb/deconstruct_import.py`）不再把 `style.examples`（逐字原文示范段）生成知识条目，改为计数并写入 warnings（「原文示范段 N 条不入库（逐字原文，版权红线）」）。
- 知识 v2 收录即落第 1 条实例（不必等启动迁移重启才可见）——拆书条目在星图/详情抽屉即时可见。
- 文风 role（叙事身份）与文笔 rules/craft/taboo（提炼写法）照常收录。
- 存量清理：应用库内 12 条示范段条目（连 tags/实例）已删除。

## Impact

- 代码：`client/backend/kb/deconstruct_import.py`（映射口径＋收录即建实例）、`tests/test_kb_deconstruct_import.py`、`tests/test_kb_match_emotion.py`、`tests/test_kb_knowledge_migration.py`
- 数据：应用库（novel-v0.45.1.db）删除 12 条示范段条目；novel-v0.44.5-local 库为回退备份
- **无界面改动**：知识库页/抽屉/星图不因此变更布局与交互（条目数变化为内容变化）
- 已随 fix(kb): 拆书收录不再产生示范段条目（ef956ace）合入 main；本 change 为补录归档

## Capabilities

### Modified: knowledge-base

- 入库校验闸门 requirement 增补：拆书收录的原文示范段 SHALL NOT 生成知识条目（计数进 warnings）
- 知识条目数据模型 requirement 增补：拆书收录即落第 1 条实例（知识/实例/来源书名），不必等启动迁移
