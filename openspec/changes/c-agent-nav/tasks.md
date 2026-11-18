# c-agent-nav Tasks

## 1. 后端：switch_tab 工具＋effect 生成

- [ ] 1.1 scopes.py：七域（ch:og/prose/settings/relations/hooks/actions/style）工具集各加 switch_tab；_SHARED_TOOLS 不动（域封闭）
- [ ] 1.2 tools.py：Tool dataclass 增 effect_action/effect_target_from 字段（默认 refresh/""）；注册 switch_tab（kind=read，tab 七值白名单校验，坏值 ok=False 摘要列可选页签；话术契约写进 description）
- [ ] 1.3 loop.py：_emit_step 的 step_end 增加 args 字段
- [ ] 1.4 router.py：_consume 生成 effect（ok＋effect_domain；action=effect_action，target=args[effect_target_from]）；navigate 即时发独立 SSE effect 事件（不入库不进落盘分支）；refresh 维持 run_end 汇总

## 2. 前端：effect 事件透传＋真实切页签

- [ ] 2.1 chatApi.ts：AgentEvent 增 "effect" 事件类型与 AgentEffect 形状（action/domain/target/description）
- [ ] 2.2 Aui2Dock.tsx：新 prop onEffect（单条即时回调）；effect 事件转发宿主；镜像/落库分支显式不匹配（effect 不入镜像不落库）
- [ ] 2.3 NovelWorkspace.tsx：onEffect navigate 守卫（view==="workbench" 且 chapterRef）→ chatNavSeq/chatNavTab 信号；不满足静默忽略
- [ ] 2.4 ChapterWorkspace.tsx：chatNavSeq/chatNavTab props → setChTab（aiWriteSignal 同款 useEffect 计数器模式）

## 3. 测试

- [ ] 3.1 后端 route 钉（test_assistant_chat_stream_http.py 扩）：switch_tab step_end → effect 事件即时下发＋run_end effects 汇总双到；坏 tab 无 effect；navigate 不落 assistant_messages
- [ ] 3.2 后端 scopes/registry 钉：switch_tab 七域可见、卷纲/设定/预览/默认域不可见；注册表唯一性/fn/读写围栏既有钉自动覆盖
- [ ] 3.3 前端钉：NovelWorkspace onEffect 守卫逻辑＋ChapterWorkspace 信号切 tab（提取纯函数或组件钉，走 vitest coverage 契约）
- [ ] 3.4 全量闸：后端 pytest＋ruff、前端 tsc＋vitest --coverage 全绿

## 4. 收尾

- [ ] 4.1 重建 mac app＋安装＋真模型走查（验收清单五场景：七页签互切/域外话术/非法页签/回放安全/无幻觉话术）
- [ ] 4.2 归档随验收（openspec validate＋sync 主 spec）
