## 1. 影响判定与边界

- [x] 1.1 按 proposal「Design Impact」确认本变更仅动 C端后端行为与卡面文案、无布局/组件结构变化 → 不需要原型先行与 ADJUSTMENTS 登记；验证：改动文件清单不含 `client/frontend/src`
- [x] 1.2 确认 #1140（设定页题材标签与长度闸）为独立 PR，本变更在其之上独立评审；验证：分支 `c-agent-field-write-parity` 基于 `c-agent-settings-field-labels`（d441fc46），PR 说明注明依赖

## 2. 世界字段写：类型保留与 preview 同源

- [x] 2.1 `assistant/caps/settings.py` 新增世界字段写校验 helper（`no_power` 接受 bool 与 开/关/true/false/1/0 并落布尔；`history/factions/constraints/extra` 接受条目数组或字符串数组并规范成条目；最终过 `WorldIn`），写核改用该 helper，禁止 `str(value)` 字符串化；验证：单测 `no_power=false` 落布尔 false、history 数组读回同形、非数组/非法开关报人话
- [x] 2.2 preview 复用同一 helper 预校验；世界 `before/after` 按页面口径格式化（开关 开/关、条目「名目：内容；…」）；验证：`_build_gate_preview` 输出不含 `True`/`False`/Python repr，且非法值抛 `PreviewRejected`
- [x] 2.3 `write_settings_field` 工具说明写明 world 各字段值形态（no_power 布尔、history 等条目数组、stage/power/cost 文本）；验证：registry 描述断言通过

## 3. 题材字段写：形状/范围 preview 校验

- [x] 3.1 `assistant/caps/settings.py` 新增题材字段写校验 helper（`NovelGenreIn` 校验），preview 与写核共用；失败归一为人话；验证：`forbidden_list=["x"]`、`battlefield="x"`、`cost_ratio=11` 在 preview 均 `PreviewRejected`，合法值仍弹卡并落库
- [x] 3.2 `write_settings_field` 工具说明补齐 forbidden_list/battlefield/cost_ratio 的形状与范围；验证：描述断言含 `[{tagId}`、字符串数组、1-10

## 4. 章纲：同族合并、校验复用、标签对齐

- [x] 4.1 `assistant/caps/chapter.py` 增加族级深合并（`outline`/`memo`/`emotional_design` 子键合并，顶层标量覆盖）；验证：同时写 `summary`+`characters`、`required_changes`+`prohibitions` 时 `save_chapter` 收到的 data 两族键齐全，回执 changes 四条都在
- [x] 4.2 抽取章纲 patch 构造/校验 helper（`_chapter_data_for` + `validate_chapter_fields`），preview 与写核共用；`word_target` 非数字转人话 `CapabilityError`；验证：preview 对非法阶段/非数组/非数字抛 `PreviewRejected`，合法请求照常弹卡
- [x] 4.3 `CHAPTER_FIELD_WRITE_KEYS` 标签改为章纲页文案（概要→章纲概要、禁则→禁止事项、剧情条目→剧情），工具说明同步；验证：label 单测断言与 `OgPane` 页面对照一致
- [x] 4.4 覆盖既有 `write_chapter_fields` 测试（同族合并、preview 拒非法值、标签）并跑通；验证：`pytest tests/test_agent_page_ops.py tests/test_assistant_router_helpers.py -q` → 48 passed

## 5. 页面字段说明书（read_page_schema）

- [x] 5.1 新增 `assistant/page_schema.py`：按页面声明字段元数据（key/页面名/类型/上限/写入口/别名），标签复用 `SETTINGS_FIELD_WRITE` 与 `CHAPTER_FIELD_WRITE_KEYS`，覆盖设定题材/简介/世界、章纲、卷纲；验证：各页渲染内容单测通过
- [x] 5.2 注册零参数只读工具 `read_page_schema`（按 `ctx.thread` 取页面），挂到 `set:` / `ch:og` / `vol` 页签；无字段级写入口的页面如实说明；验证：`validate_scopes` 无漏配，`test_assistant_page_schema.py` 8 passed
- [x] 5.3 写工具说明与页签纪律指向 `read_page_schema`（先按页面说法找键，再按写入口写；不唯一就问一句）；验证：scope 可见性单测与描述断言通过
- [x] 5.4 02 标签退出 agent 字段写白名单（`SETTINGS_FIELD_AGENT_WRITE` 不含 `core_promise`）：写核/preview 人话拒绝、工具 enum 不含它、页面目录与说明书标注「只展示、不直接写（走出爽点采纳卡）」；验证：`core_promise` 直接写被拒＋enum 断言＋规则单测通过
- [x] 5.5 review 整改：移除标签上的旧叫法「核心承诺」别名；`read_chapter`/`read_outline` 按字段表逐格读值（补 memo/情绪/剧情/卷名/章数）；`write_volume_fields` 补 preview（VolumeUpdate 同源）；非法字段拒绝语只列 agent 可写集；验证：新增读值/卷纲 preview/别名断言单测通过，assistant 296 passed

## 6. 回归

- [x] 6.1 后端：`pytest tests/ -q -k "assistant"` → 296 passed；scope/registry 31 passed；world/genre/chapter/volume 相关 → 145 passed / 17 skipped
- [ ] 6.2 前端：`npx tsc --noEmit` 零错；`npm run design:lint` 仅存量红（`docs/design-c/prototypes/preview.html` emoji，与本变更无关、未触碰该文件）；本变更无前端文件改动，`design:check` 免跑（proposal Design Impact）
- [ ] 6.3 真机走查（随装包）：世界开关写「关」后刷新仍关、history 条目写入后可见；章纲一次改概要+出场角色两者都落库；授权卡显示章纲概要/禁止事项/剧情；agent 写前会先 read_page_schema 找字段键；记录结论与截图路径
