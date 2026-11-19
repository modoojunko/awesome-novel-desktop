# c-agent-page-ops 设计

## Context

boss 拍板（2026-11-19）：agent 页面操作（除写正文）＝读/写/改；凡写改必过授权策略；授权两层、选择器放输入框区、参考 OpenWorker 设计用阿里组件落地；`/mode` 不承载授权。

现成地基（探查实锤）：
- write_gate.evaluate 三段判定＋硬地板；allow_book≡allow_all（一期全在本书内）——两层化＝芯片词表收敛，闸零改动。
- switch_tab 的 effect 通道（registry 声明 effect_action="navigate" → dock onEffect → chatNav 翻页签）。
- `save_chapter` patch-gates 缺键保现值（章纲单字段写天然支持）；`write_volume_fields` 是写工具全样板（白名单/权属/previous/write_log）。
- `uiConfig.input.header` 插槽＋库自带 `Sender/ModeSelect`（options icon/label/selectedLabel/tooltip/value＋onChange）＝OpenWorker Composer 权限选择器的阿里现成对应物。
- GateCard approve/deny/翻卡面已通；preview 现为 {"tool","args"} 裸形状。

## 技术决策

1. **两层授权＝chip 词表收敛**：`TIER_LABEL` 只留 confirm_each（每写必确认）/allow_book（自动执行·本书内）；`allow_all` 存量值前端映射显示自动档（后端 KNOWN_TIERS/evaluate 不动）；硬地板不动。`/mode` 授权分支退役，新增 `/auth`（查档/确认/自动，复用书级改写 `set_book_tiers` 路径）。
2. **选择器进输入框**：`uiConfig.input.header` 挂 lib 自带 `Sender/ModeSelect`（icon/label/selectedLabel/tooltip 两档＋value＋onChange）——渲染归库（收起态 selectedLabel/展开选项行/✓），我们不手搓弹层；旧 `cd-mode-chip/pop` 移除。
3. **navigate 泛化**：parameters `{view: novels|workbench|settings|preview, chapter_ref?, tab?}`；effect target 编码 `view[:chapter_ref[:tab]]`；前端 onEffect 消费扩展＝dirty 守卫（复用 goTab 的 settingsDirty/volumeDirty 守卫）→ focusNode → setView → chatNav。kind=read 免授权。
4. **字段级写两工具**：
   - `write_chapter_fields(chapter_ref, fields)`：白名单键（title/summary 字段映射 save_chapter 数据键：challenge/plot_stage/ladder_exit/plot_items/memo.required_changes/memo.prohibitions/emotional_design.primary_mood/word_target/outline.summary/outline.characters）；写前 assemble 读现值构造 changes 前后对比进 preview 与 write_log。
   - `write_settings_field(stype, field, value)`：stype 白名单 genre{core_promise,forbidden_list,cost_ratio,battlefield}/story{synopsis}/world{topic:…}；读现值→合并→走既有服务链（put_novel_genre/story synopsis 更新/put_world_merged）。
   - preview 增强：Tool 增可选 `preview_builder(args)` 钩子（router._gate_fn 用它替代默认 _preview）——两个写工具用其构造 `{tool, entity, changes:[{field,before,after}]}`；GateCard 渲染 changes 行（旧形状工具走裸 JSON pre 分支不变）。
5. **页面态随行**：chat body 增 `page_state.unsaved[]`（NovelWorkspace 从 settingsDirtyRef/volumeDirtyRef/ogEditing/正文 saveState 组装）→ router 拼进 L2 note（「［未保存：设定面板］」）。不做 read 工具。
6. **作用域**：navigate→ch 域（与 switch_tab 同域可见）＋共享；两个写工具→所属域（write_chapter_fields→ch:og；write_settings_field→set: 域）；启动校验/围栏测试同步。

## 风险与既知

- 三档改两档动 assistant-chat-ui 主 spec 的 Req 枚举——MODIFIED delta 带齐全量（判例）。
- 围栏测试 `test_write_surface_is_fenced` 钉写面 8 名单——新写工具入册同步扩名。
- undo 现只支持 volume: 实体——新写工具 write_log 按同口径落，undo 扩实体挂账二期。
- genre 整卡校验：单字段写必须 GET 现卡合并后整卡 PUT（不得只传单字段），否则校验 422/覆盖他字段。
