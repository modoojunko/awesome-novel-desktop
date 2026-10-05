# Design: c-prompt-dead-refs-cleanup

## 决策 1：backfill_outlines 删标签节＋改写 prose 指涉，而非补 format

- `_call_ai`（`novels/ai_backfill.py:57-59`）是三模板共用的纯拼接通道：`f"{user}\n\n---\n{context[:30000]}"`。另外三个 backfill 模板（synopsis_world/characters/style）本来就没有占位符，靠 `---` 后的真实素材工作。
- step2 的 context＝step1 结果拼的「简介：…/设定：…/角色：…」行（`ai_backfill.py:150-160`），**没有**章列表可填 `{chapters}`——补 format 需要改 `_call_ai` 传参链＋step2 上下文组装，收益为零。
- **prose 指涉同批清**（评审 P1）：模板 ：3（system「依据给出的设定与已有章节」）与 ：7（user「根据以下设定和已有章节」）仍向模型承诺一份永不到达的输入；只删占位符会让这处虚假指涉成为唯一信号。两行改为「依据给出的设定素材（简介/设定/角色），规划后续卷结构与章纲」。
- 输出解析不受影响：step2 产物按 `# 卷`/`## 章` 行前缀解析（`ai_backfill.py:175-179`），解析锚在输出格式说明里，原样保留。模型行为风险评级：改后**优于**现状（现状发的是字面量 `{settings}`/`{chapters}` 死 token）；真机冒烟为可选任务（4.5）。

## 决策 2：name_canon 走「承认现状」（方案 a），不恢复动态注入

- 恢复接线（方案 b）需要给 arc_* 三模板加回 `{name_rules}` 占位符并重走渲染对拍——但内联规则就是现在的真身，二次接线制造两处真相，违背单源初衷。
- **事实口径（评审 P1 修正，实现文档必须照此写）**：三模板 system 段的规则是**按语境改写的三处变体，不是逐字副本**——
  - `arc_draft.prompt:9`：生成侧全口径（禁令＋退通称）；
  - `arc_calibrate.prompt:9`：措辞更软（「改用名册名或通称」）；
  - `arc_check.prompt:9`：裁判口径（「名册是『设定里登记过什么』的清单」），无生成侧禁令——角色使然，非缺陷。
  - 三处互不逐字一致，也与 `name_canon.prompt` 片段原文不一致。
- 落地：
  - `ai_router.py` 删 `name_rules` 键＋`name_canon_text()` 调用；import 行去掉 `name_canon_text`（`known_names`/`roster_text` 在 :1069 仍用，保留；`known_names` 另在 `run_arc_ai` 内有独立局部 import，不受影响）。
  - `name_registry.py`：函数保留，docstring 标注「参考存档/当前无注入点（无 `{name_rules}` 占位符）/现行规则为 arc_* 三处语境化变体/恢复注入须重新接线＋对拍」。
  - `name_canon.prompt` 头注释（每行保持 `## ` 前缀——`name_canon_text` 与 `_strip_comment_lines` 都是前缀式剥离，非 `## ` 行会漏进步正文）按五点写：①当前无运行时注入点、加载器零调用方；②本文件是 2026-09-27 单源版原始措辞的**存档**，三模板现行规则是语境化变体、与本文件及彼此均不逐字一致；③改规则去三处内联地改；④恢复单源注入须重新接线＋对拍回归；⑤活注入腿=`{roster}` 名册——覆盖面按 grep 实况写：`arc_draft`/`arc_calibrate`/`arc_check`/`chapter_archive_extract`/`settings_characters_check` 五模板（由 `ai_router.py`/`archive/dossier.py`/`archive/reconcile.py`/`characters_ai.py` 各自拼装）。
- 已核实 `settings/world_model.py:452` 的 `_name_rules` 是 FactionIn 字段校验器，与本改无关，不动。

## spec delta

- `storyline-settings`「右栏 AI 三行（全部聚焦主线）」requirement（主 spec :44-123，15 场景）MODIFIED：仅改硬约束②——删「同一份口径措辞（单源片段：…）」机制描述，换为行为口径（名册＋规则同时给；规则住各模板 system 段、与行角色相适；片段退役为参考存档，SHALL NOT 不重新接线就复活为注入点）。delta 由脚本从主 spec 逐字切取生成（仅目标句替换），场景零丢失。

## 爆炸半径（已勘，含评审复核）

- e2e：`client/frontend/e2e/*.ts` 零处引用 backfill_outlines 措辞或 name_canon。
- 单测：`tests/test_story_arc.py:754-760` spy 只计数、:895-915 只对 world/genre_section 逐键相等断言——删 `name_rules` 键不涉；全 tests/ 无键集合断言；:844-878 roster/name_warnings 断言全走保留的名册腿。
- `test_prompt_layering.py`：`name_canon` 在 ASSETS（:22）与 MIGRATION_PENDING（:33）双重登记——本改顺手删 MIGRATION_PENDING 侧（类别错置：片段资产不该在迁移名单；ASSETS 已覆盖，删后测试仍绿，名单只减不增合规），ASSETS 注释补「现为文档副本」。
- backfill 链**无既有测试覆盖**（`-k backfill` 实际命中 test_api_format/test_volume_plan_ai 的无关用例）——保障来自「模板是纯文本、消费链不 format」本身；新闸门 3.1 补一条零成本冒烟。
- ruff：client CI 实跑 `ruff check --extend-select F811,F821,F841 .` 不钉版本；删 import 成员无 F401、dict 尾逗号已有。本地核对用 0.16.3 口径即可，别期待 CI 版本一致。
- 运行时风险：step2 提示词变化——输出解析锚不变，改后优于现状。

## 测试口径（评审 P2 收紧后）

- 新增 `client/backend/tests/test_prompt_dead_refs.py`：
  - 断言①：`load_layers("backfill_outlines")` 取 **user 段**（真实读取面，且 `## ` 头注释已剥——changelog 提到 `{settings}` 不误红）不含 `settings`/`chapters` 占位符；附零成本冒烟：返回二元组、user 段非空。
  - 断言②：`inspect.getsource(ai_router._arc_material)` 不含 `name_rules`——范围钉在被改函数上（不需要 DB mock、不调用函数、函数搬家跟着走），不用整文件 grep（未来合法命名会误红）。
- 既有闸门：`test_prompt_layering.py`＋`test_prompts_loader.py`＋ruff 本地 0.16.3 口径。

## close-out（纳管仓库，时序评审 P1 修正）

- **先合本仓 PR 进 main（squash）**，再 sync——`sync.py` 的 `read_source_version` 用 `git log -1 -- client/backend/prompts` 取检出提交写进 manifest 版本锚；在未合分支上跑会把锚指向 squash 后 main 上不存在的提交。
- prompts 仓库检出在 `/tmp/awesome-novel-prompts`（临时目录，不保证存活）——close-out 按「重新 clone main 检出」写，不假设路径。
- CURATED 更新点：`backfill_outlines` 删 `{settings}`/`{chapters}` 登记、layer 改「无占位符——素材经 --- 拼接（与三兄弟同形）」、删 ⚠ 备注；`name_canon` trigger/layer/note 改「参考存档」口径（三处语境化变体，非逐字副本）。对拍闸门会校验 CURATED vs 模板实提取，防漏改。
