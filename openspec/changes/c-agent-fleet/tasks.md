# c-agent-fleet（改型）任务

## 1. 域映射与工具面

- [x] 1.1 assistant/scopes.py：thread→域解析＋域内工具清单＋共享读集＋tools_for_thread()；启动校验（每工具恰属一域清单或共享集，漏配 fail loud）
- [x] 1.2 域映射对表 chatRegistry chips（og/prose/set/vol/preview 逐页签核对，前端动作类 chip 不进映射）
- [x] 1.3 守卫测试：封闭性（清单⊆注册表）/覆盖性（30 工具无漏挂）/共享读恒在

## 2. 按线程声明收窄

- [x] 2.1 loop native 分支：schemas 按 tools_for_thread(thread) 收窄（thread 经 ToolContext 注入）
- [x] 2.2 loop text 分支：协议模板目录行按同集合过滤
- [x] 2.3 域外调用回喂：native＝tool 结果行引导话术；text＝降级路径话术换域外引导
- [x] 2.4 测试：章纲线程只见章纲面／设定线程调章纲工具＝引导不执行／全 30 收窄为 ≤17

## 3. 域纪律分节

- [x] 3.1 prompts：PAGE_DISCIPLINE 四域分节常量（章纲节奏档位/正文人味红线/设定口径一致/卷纲六段口径），拼系统提示词尾
- [x] 3.2 测试：分节随域切换、共享段（身份/围栏）不变

## 4. 轨迹域标签

- [x] 4.1 TOOL_DOMAIN 映射；step_start/step_end/trace 增 domain 字段（共享读省略）
- [x] 4.2 dock 轨迹组标「XX 助手 · N 步」；气泡署名不变
- [x] 4.3 契约测试：缺 domain 字段零回归

## 5. 线程独立性守卫

- [x] 5.1 守卫测试：两会话（不同 thread）并发 run 互不串写（消息/压缩态各自落位）
- [x] 5.2 同线程双发语义注释挂账（前端 runActive 挡，后端不加锁）

## 6. 走查验证

- [x] 6.1 设定页对话只见设定面＋域外引导话术实测（真模型）
- [x] 6.2 双页签并行 run 互不阻塞实测
- [x] 6.3 dock 轨迹域标签目验＋dock 回归 e2e——14/15（唯一挂＝③stale 存量挂账，与本 change 无关）
