## 1. 框架三件套

- [x] 1.1 规则单源：新增 `prompts/name_canon.prompt`（与题材/作者无关的通用措辞）；主线硬约束② 改引用 `{name_rules}`（`settings/ai_router._arc_rules_text` 注入）；起草要求句加「专名除外：人物/势力/地点的名字以设定为准」。验证：`test_hard_rules_name_source_is_settings`（② 含占位符、渲染后无占位符、片段不写死任何具体书/词）。
- [x] 1.2 名册：新增 `settings/name_registry.py` 的 `known_names`（角色名＋别名／势力名／地点；空名占位卡不进册）与 `roster_text`；起草/校准提示词新增【本书专名册】块（空类别写明退通称）。验证：`test_roster_block_in_prompt`（三类行齐、主角名＋别名在册）。
- [x] 1.3 输出契约：起草/校准 JSON 增 `names` 申报字段。验证：模板断言（既有用例覆盖）+ 真机（模型照契约申报）。

## 2. 对拍与告警

- [x] 2.1 检测两条腿：`_arc_extra_names`＝申报面 diff（只判人物/势力，地点不判）＋ `suspect_unregistered` 确定性扫描（词尾锚、最短候选优先、纯汉字＋粘连字过滤、命中名册或世界设定原文即放行）。验证：`test_suspect_scanner_precision`（旧派系词必抓；设定原文写过的词/过泛词/粘连词零误报）。
- [x] 2.2 只提醒不纠正：命中写入 `value.name_warnings`，**SHALL NOT 追加改名重写调用**（真机实测无效）。验证：`test_unregistered_name_reports_warning_without_retry`（1 次调用＋告警）+ `test_clean_declaration_skips_retry`（零告警）。

## 3. 真机与门禁

- [x] 3.1 真机三步对照（隔离栈，共享栈零触碰）：只规则无效 → 规则＋名册有效（「豢养派」消失、「主战派」保留）→ 自动纠正无效故砍掉。证据：`real-machine-check.md`。
- [x] 3.2 `pytest tests/` **1542 passed**（新增 6 例）；`ruff check settings/` 1 条存量告警、零新增；隔离栈全部拆除、含密钥副本已删。
- [x] 3.3 范围守门：只动主线链（拆卷/拆章/章纲起草/写正文零改动——已按用户要求回退本轮早前的越界改动）。验证：`git status` 仅 `prompts/arc_*`、`settings/ai_router.py`、`settings/name_registry.py`、`tests/test_story_arc.py` 与 change 目录。
- [x] 3.4 `openspec validate c-ai-name-canon --strict` 通过（delta 场景 12 → 13，原场景零丢失）。
