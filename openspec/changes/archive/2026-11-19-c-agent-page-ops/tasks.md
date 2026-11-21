# c-agent-page-ops 任务

## 1. 后端：授权两层化＋/auth 专用命令

- [x] 1.1 `assistant/router.py`：`/auth` 命令（查档/`确认`/`自动` 切档，书级改写复用既有逻辑）；`/mode` 授权分支退役
- [x] 1.2 测试：`/auth` 查档与两档切换钉；allow_all 存量兼容钉

## 2. 后端：navigate 工具

- [x] 2.1 `assistant/tools.py`：`navigate` 工具（kind=read，effect_action="navigate"，target=view+chapter_ref+tab 编码）
- [x] 2.2 前端 `NovelWorkspace.tsx` onEffect 消费扩展（dirty 守卫→focusNode→setView→chatNav）＋ scope/chatRegistry 类型
- [x] 2.3 navigate effect 钉（后端事件形状＋前端消费守卫）

## 3. 后端：字段级写工具族

- [x] 3.1 `caps/settings.py` 字段写族（genre merge/story synopsis/world merge）＋ `caps/chapter.py` 章纲字段 patch 写（读现值/合并/changes 前后对比）
- [x] 3.2 `assistant/tools.py`：`write_chapter_fields`＋`write_settings_field` 注册（kind=write，白名单，无 feature_key）＋ Tool 可选 preview_builder 钩子（router._gate_fn 消费）
- [x] 3.3 `assistant/scopes.py` 域挂账＋`test_assistant_registry.py` 围栏扩名
- [x] 3.4 测试：gate 交互三钉（confirm 弹卡/自动直执行/硬地板必弹）＋章纲 patch 缺键保现值钉＋genre merge 不覆盖他字段钉＋preview changes 形状钉

## 4. 前端：选择器进输入框＋授权卡人话行

- [x] 4.1 `Aui2Dock.tsx`：TIER_LABEL 两档；选择器进输入框底栏**同行左端**（实施偏离计划：lib `Sender/ModeSelect` 绝对定位不适配，改自绘 pill 走 `onInput.morePrefixActions`，菜单 portal 到 body；见 #1098/#1100/#1103）；移除 cd-mode-chip/pop
- [x] 4.2 GateCard：preview.changes 字段前后对比行渲染（旧形状走裸 JSON pre 分支）
- [x] 4.3 测试：ModeSelect 两档渲染＋onChange 钉；GateCard changes 行渲染钉

## 5. 后端：页面状态随行

- [x] 5.1 chat body 增 `page_state.unsaved[]`（前端 NovelWorkspace 组装上行）＋ router `build_page_note` 注入
- [x] 5.2 注入钉（未保存标记进提示词尾注）

## 6. 验证与收口

- [x] 6.1 后端全量 pytest＋ruff；前端 vitest coverage 过阈值
- [ ] 6.2 走查：隔离栈三景（/auth 自动＋跨视图跳／确认档字段写弹卡前后→允许→面板刷新／跨章跳＋未保存守卫）
      ——**挂账**：真后端预览已实拍选择器位置/空会话贴底/切档；字段写授权卡交互与跨章守卫未走真 UI，随 v0.48.3 真机抽检补
- [x] 6.3 openspec validate；归档随验收
