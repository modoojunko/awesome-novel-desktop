# c-agent-panel-consolidate Tasks

## 1. dock autoAsk 通道

- [ ] 1.1 Aui2Dock：提取 submitMessage 内部函数（手动路径零行为变化）＋autoAsk prop（{seq,message}）＋useEffect 自动提交
- [ ] 1.2 NovelWorkspace：autoAskState 持有＋面板「让助手办」分派 helper（组消息＋bump seq）

## 2. chips 覆盖补缺

- [ ] 2.1 chatRegistry settings.default：world 各要素格 chips（SINK_TOPIC 对齐）＋命名 chip；settings.chars：出稿定向/发散两态 chips
- [ ] 2.2 validateRegistrations 白名单核对（新 chip key 全在工具清单内）

## 3. 面板退役与接线

- [ ] 3.1 GenreSettingForm：四格「AI 填」→让助手办（格名入消息）；AiCardModal 移除＋AiCardState 清理
- [ ] 3.2 StoryArcForm：起草主线/结局校准 → 让助手办（chips 文案）；弹窗移除
- [ ] 3.3 HooksSettingForm：h1/h2/h3/h4 四入口 → 让助手办；弹窗移除
- [ ] 3.4 CharacterManager：出稿（定向/发散）/体检 → 让助手办；弹窗移除
- [ ] 3.5 WorldSettingPanel：各格「AI 填」→让助手办（格名＋底稿 80 字直传）；弹窗移除
- [ ] 3.6 SettingsView runAi/clearAi 分发链收窄（按保留面）；AiCardModal 组件保留（文风三区）

## 3.5 采纳写回（按卡种，boss 拍板 A）

- [ ] 3.5a settings 字段卡（题材四格）：payload 已携 stype+field → dock 采纳 GET settings/<stype> + merge field + PUT；hooks 草稿卡补结构化 candidates payload（后端 tools_settings）
- [ ] 3.5b 世界观卡（payload.topic+draft）：写回 settings world 对应 topic 字段
- [ ] 3.5c 角色草案卡（payload.character_draft）：dock 卡挂「确认 · 建卡」→ 角色建卡 API（旧 ChatDock 动作平移）
- [ ] 3.5d 写回后刷新信号：settings 域无未保存修改→面板重载；dirty→不重载＋对话内提示（dirty 保护，effects 设计 §评审关注点 2 同款）

- [x] 3.5e chips 结构化触发补 args（真机实锤：flash 从话术猜 draft_worldbuilding
  空参被校验打回＋shape 猜错 400 自纠一次）——ChatChip.args 随点击进 tool_hint prime；
  世界卡 draft 双层 JSON 剥壳（后端剥一层＋前端采纳兜一层）

## 4. 测试＋收尾

- [ ] 4.1 钉子：autoAsk 自动提交走既有链（闸不绕）；面板按钮文案===chips 文案（单一文案源）；chips 白名单校验含新 key
- [x] 4.2 全量闸：前端 tsc＋vitest --coverage＋后端 pytest＋ruff 全绿
- [x] 4.3 重建安装＋真机走查（浏览器真 UI）：设定→世界面板→chip 点「AI 填 · 力量体系」→hint prime 首步 ok:true→产物卡→「采纳 · 写入」→settings/world power 字段落纯文本→面板重挂刷新
- [ ] 4.4 归档（与其余 agent 系列 change 一并收）
