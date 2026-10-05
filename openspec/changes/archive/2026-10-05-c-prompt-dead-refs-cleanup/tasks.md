# Tasks: c-prompt-dead-refs-cleanup

## 1. backfill_outlines 死占位符＋prose 指涉

- [x] 1.1 `client/backend/prompts/backfill_outlines.prompt`：删除「设定信息：\n{settings}\n\n已有章节：\n{chapters}」两节；**同批改写 ：3（system）与 ：7（user）的「（和）已有章节」prose 指涉**（「依据给出的设定素材（简介/设定/角色），规划后续卷结构与章纲」）；输出格式说明（`# 卷`/`## 章` 锚）原样保留。（v3 头注释＋标签节删＋两处 prose 改写「依据给出的设定素材（简介/设定/角色）」）

## 2. name_canon 死注入

- [x] 2.1 `client/backend/settings/ai_router.py`：删 `"name_rules": name_canon_text(),` 行；import 去掉 `name_canon_text`（`known_names`/`roster_text` 保留）；:1066-1067 两条腿旧注释按 design 口径改写（规则=三处语境化变体、活腿=roster）。（键/调用/已删；import 收窄 known_names, roster_text；两条腿注释改现状三行）
- [x] 2.2 `client/backend/settings/name_registry.py`：`name_canon_text()` docstring＋模块头注释按 design 五点改写（参考存档/无注入点/语境化变体/恢复须接线＋对拍/roster 覆盖五模板实况）；函数体保留。（模块 docstring＋函数 docstring 均改「参考存档/零调用方/三处语境化变体/恢复须接线对拍」口径）
- [x] 2.3 `client/backend/prompts/name_canon.prompt`：头部 `## ` 注释按 design 五点改写（**每行保持 `## ` 前缀**）。（v2 头注释七行，每行 ## 前缀，含五点：零注入点/存档/三处变体/改法/恢复条件＋活腿清单）
- [x] 2.4 `client/backend/tests/test_prompt_layering.py`：`MIGRATION_PENDING` 删 `name_canon`（ASSETS 已覆盖）；ASSETS 注释补「现为文档副本」。（MIGRATION_PENDING 删 name_canon＋ASSETS 注释补「现为文档副本」）

## 3. 防回归闸门

- [x] 3.1 新增 `client/backend/tests/test_prompt_dead_refs.py`：断言① `load_layers("backfill_outlines")` user 段不含 `settings`/`chapters` 占位符＋二元组冒烟（user 段非空）；断言② `inspect.getsource(ai_router._arc_material)` 不含 `name_rules`。（两断言：load_layers user 段无 settings/chapters＋二元组冒烟；inspect.getsource 钉 '"name_rules"' 字典键字面量——首版整串断言咬到自注释，按评审预警收紧）

## 4. 回归

- [x] 4.1 `pytest client/backend/tests/test_prompt_layering.py client/backend/tests/test_prompts_loader.py client/backend/tests/test_prompt_dead_refs.py -q` 全绿。（三闸门＋test_story_arc 共 53 绿）
- [ ] 4.2 backfill 链说明：无既有测试覆盖（`-k backfill` 命中的 test_api_format/test_volume_plan_ai 用例与本链无关）——保障来自模板纯文本＋消费链不 format；3.1 断言①的冒烟即为兜底。（无 pytest 步骤，此处记录判定依据。）
- [x] 4.3 `ruff check client/backend/settings/ai_router.py client/backend/settings/name_registry.py client/backend/tests/test_prompt_dead_refs.py`（本地 0.16.3 口径；CI 实跑 `--extend-select F811,F821,F841` 不钉版本）零新增告警。（ruff 0.16.3 All checks passed）
- [x] 4.4 `grep -rwn "name_rules\|name_canon_text" client/backend --include='*.py' | grep -v __pycache__`——预期仅剩 `name_registry.py` 定义与 docstring（词边界排除 `world_model.py` 的 `_name_rules` 校验器）。（残留仅 name_registry 定义/docstring＋ai_router/闸门注释性提及——非代码注入）
- [ ] 4.5 （可选，非阻塞）演示栈真机冒烟：自建隔离栈，以固定 stub step1_result 单跑 `/ai-backfill/step2`，人工核对产出可被 `_parse_volumes` 解析。

## 5. close-out（两个仓库，时序敏感）

- [x] 5.1 本仓提 PR → CI 绿 → **squash 合入 main**（sync 的版本锚必须指向合并后的 main 提交，5.2 之前必须完成本步）。（#677＝595b25bc，admin squash）
- [x] 5.2 awesome-novel-prompts：`sync.py` CURATED 更新（`backfill_outlines` 删两条 ph 登记＋layer 改「无占位符——素材经 --- 拼接」＋删 ⚠ 备注；`name_canon` trigger/layer/note 改「参考存档，三处语境化变体非逐字副本」）。（CURATED 两处改毕＋删 #669 三死条目→58）
- [x] 5.3 awesome-novel-prompts：重新 clone（/tmp 旧检出为临时目录，不假设存活）或复用现存 main 检出，核对 `git -C <ai-novel 检出> log -1 -- client/backend/prompts` 显示的正是 5.1 合并提交 → `python3 sync.py <该检出>` → 占位符对拍闸门通过 → commit＋push。（sync 自 origin/main worktree，锚＝595b25bc，对拍闸门过；顺带修 sync.py strip 语义对齐 C端 loader；prompts 仓 1c32264）
- [x] 5.4 本仓 openspec 归档走常规 archive 流程（`/openspec-archive-change`，基于合并后 main 重读 specs sync）。（本次归档：spec ② 括注同步进主 spec＋change 移 archive）

## 回归

- 三闸门＋story_arc 53 绿；全量 backend pytest 1765 绿（+2 新闸门）；ruff 0.16.3 零告警；grep -rw 残留符合预期（仅文档提及）；4.5 可选冒烟未跑（模板纯文本删节、解析锚不变，风险自限）；prompts 仓对拍✓（1c32264）。
