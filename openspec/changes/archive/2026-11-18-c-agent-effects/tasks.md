# c-agent-effects 任务

## 1. 后端 Effect 产生
- [x] 1.1 写类工具注册表加 effect_domain 元数据（confirm/unconfirm/archive/unarchive=chapters、add_volume=volumes、add_chapter=chapters；effect_target_from 裁撤——target 可选，首版不需要）
- [x] 1.2 router._consume step_end 时收集 effect → run_end 注入 effects 数组
  - 2026-11-18 boss 走查实锤：首版只写了 run_end 注入没写收集（run_effects 未定义
    ）→ NameError 在 _drive task 里静默炸掉 → _STOP 永不入队 → SSE 永挂。已补：
    run_effects 初始化＋step_end 携带 ok＋成功写步才收集（失败写不改数据，刷新＝假反馈）
- [x] 1.3 _drive 崩溃显式收口（2026-11-18 实锤加固）：except 非 Cancel 异常 →
  error 事件下发＋finally 恒 put _STOP——drive 静默死亡＝SSE 永挂「进行中」卡死，
  SHALL NOT 静默永挂（c-prose-stream-silent-hang 同口径）；崩溃留 exception 日志

## 2. 前端 Effect 消费
- [x] 2.1 Aui2Dock run_end 分支提取 effects → onDone 时调 onEffects
- [x] 2.2 NovelWorkspace 实现 onEffects → chapters/volumes 域走 refreshCharStale
  （复用既有刷新链，最小改法）；dirty 保护降格挂账（boss copy-first 口径：先最小改法）

## 3. 测试
- [x] 3.1 后端：HTTP 级 SSE 回归钉 test_assistant_chat_stream_http.py 四条——
  effects 收集注入／drive 崩溃显式 error＋收口／失败写步无 effect／读步无 effect；
  读取走线程 future 带超时——永挂形态超时即失败（回归信号）
- [x] 3.2 前端：onEffects 回调钉
