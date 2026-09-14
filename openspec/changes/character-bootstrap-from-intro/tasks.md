## 1. 后端

- [x] 1.1 新增 `prompts/settings_characters_bootstrap.prompt`：输入书名/题材/简介（世界已填则拼入），输出 `{name, aliases, persona, fills, skipped}` JSON；含性别年龄禁令、禁编造、只输出 JSON、空格可缺省等口径（对齐 dossier/persona prompt）。
- [x] 1.2 `settings/characters_ai.py` 新增 `bootstrap_protagonist`：可选 `character_id`（主角待立时空值基准），allowed 键硬挡性别年龄，clamp/解析/失败记账（`settings_char_bootstrap[_fail]`、502 文案）照四行惯例。
- [x] 1.3 `settings/ai_router.py` 挂 `POST /ai/characters/bootstrap`：`require_ai_access`＋`require_novel_model`；400（简介未填时的显式拒绝）与 200 响应契约落注释。
- [x] 1.4 `tests/test_characters_ai.py` 加 bootstrap 用例：正常出稿（名称/别名/persona/cells）、性别年龄不写入、越界键丢弃、简介未填 400、未配模型门控、空产出 502、超时记账、主角待立只补空格（已写格不出现在 cells）。
- [x] 1.5 `workflow/readiness.py::_check_characters` 收紧为「至少一张名字非空（非 `\u0000` 占位）的卡」＋docstring 钉死分工；补/改 readiness 测试：空名卡=未填、一张有名卡=已填。

## 2. 前端

- [x] 2.1 `lib/charactersApi.ts` 加 `bootstrapDraft(projectId, characterId?)` 与响应类型（name/aliases/persona/cells/skipped）。
- [x] 2.2 `CharacterManager.tsx`：`runAi("bootstrap")` 放宽无卡守卫；新增 `bootstrapSink` 预览卡（复用 ai-sink 样式）；采纳分支＝空态 `create(name,"主角")`＋逐格 PATCH／主角待立 PATCH name(若空)+persona(若空)+cells；完成后 reloadList＋选中。
- [x] 2.3 空态引导卡：列表为空时中栏渲染引导卡；`introReady`（来自 `settingsStatus.synopsis`）为 true 给「从简介立主角」（主）＋「手动建主角」（次），为 false 给补简介指引＋手动建主角；未配模型/免费点不动的文案走既有 `onBlocked` 通道。
- [x] 2.4 `addCharacter` 首卡默认主角（`list.length === 0 ? "主角" : "配角"`）。
- [x] 2.5 `CharsAiRail` 条件第五行「从简介立主角」（`ctx?.role === "主角" && !ctx.name`），desc 声明输入与只补空格；`SettingsView.runCharsAi` 透传 `"bootstrap"` key；`introReady` prop 下沉。
- [x] 2.6 vitest：空态引导卡两分支渲染与按钮分派、采纳编排（create+patch 调用序）、首卡默认主角、rail 第五行条件渲染、性别年龄不渲染。

## 3. e2e 与门禁

- [x] 3.1 e2e（从主检出跑）：新增/扩展角色面板用例——首次进入见引导卡、手动建主角、（mock AI）从简介立主角出稿采纳后列表出现主角；存量角色用例回归。
- [x] 3.2 本机门禁全绿：后端 `pytest`＋`ruff`；前端 `tsc`＋`vitest`；docker 栈全量 e2e。

## 4. 收尾

- [x] 4.1 自查对照 spec scenarios 逐条核验；ADJUSTMENTS 登记若无则免。
- [ ] 4.2 提交分支、拉 PR、完成审核（review→修→合）。
