# c-agent-fleet（改型）设计：每页签独立对话

## Context

boss 拍板三独立（2026-11-16）：每 tab 独立上下文／独立对话记录／独立流程。现状底数：线程级隔离已上线（会话 UNIQUE user+book+thread_key、消息/压缩态按线程、跨线程并发无锁），流程层未隔离（全 tab 下发 30 工具＋同一纪律）。实测单 agent 每轮开销 5-6K tok（窗口 ~5%），30 工具在注意力安全线内——**否决真多 agent＋总调度委派**（恒定分类税＋召回重派＋嵌套循环工程面），改型为单执行体＋每页签独立流程。原多 agent 降级为升级触发器（proposal Non-Goals）。

## Goals / Non-Goals

- Goals：thread→域映射与工具声明收窄（域外引导）；域纪律分节注入（身份单源派生）；轨迹域标签；线程独立性条款化＋守卫测试
- Non-Goals：多 agent／委派嵌套循环（升级触发器见 proposal）；不改线程模型；不增删注册表；不动 write_gate/压缩口径

## 架构决策

### D1：域身份＝thread 前缀，不是新路由层
thread 已是精确页签身份（ch:{tab}｜set:{panel}｜vol｜preview），前端 `page` 参数粗粒度（「工作台·章节」不分 og/prose）——**不再加路由字段**，后端按 thread 前缀解析域。映射：

| thread 前缀 | 域 | 域内工具（＋全域共享读） |
|---|---|---|
| ch:og | 章纲 | draft_chapter_plot / draft_chapter_split / settings_og_fill / check_consistency / draft_names |
| ch:prose | 正文 | read_story_state（正文页以读为流程；生成走既有写作流不占对话） |
| set:* | 设定 | settings_genre_* / settings_hooks_* / settings_intro / draft_arc / draft_names / diverge_character_group / draft_chapter_plot?（否——剧情清单归章纲）|
| vol | 卷纲 | draft_volume_plan / draft_volume_expand / write_volume_fields / check_consistency / draft_names / draft_arc / diverge_plot_branches / diverge_character_group / draft_chapter_split |
| preview | 预览 | 只读全域 |
| 其余（v:* 等） | 默认＝全域共享读 |

全域共享读：read_progress / read_settings / read_outline / read_chapter / read_story_state / profile_read / profile_update / kb_search / kb_read / draft_character（角色草案三段式跨域合法——设定对话和任何页签都可能建角色）。启动校验：每个工具恰属一个域内清单或共享集，**漏配 fail loud**。

### D2：收窄的是声明＋执行视图，注册表不动
native 分支：`schemas = [t.openai_spec() for t in tools_for_page(thread)]`；text 分支：协议模板目录行按同集合过滤。执行层：get_tool 仍查全表，但**域外工具调用按未授权处理**——native 回喂 tool 结果行「这是 XX 域能力，请切到对应页签」；text 走既有未知工具降级路径（话术换域外引导）。写作核心（正文生成/章纲生成等既有流）不经对话 agent，不受影响。

### D3：域纪律分节——自身份定义派生＋常量分节起步
`PAGE_DISCIPLINE: dict[域, str]` 常量起步（章纲节奏档位/正文人味红线/设定口径一致/卷纲六段口径），拼在系统提示词尾部；提示词包管线后续接管分节文案（batch 外挂账）。身份单源原则：分节只含域纪律，身份/语气仍单源。

### D4：轨迹域标签（事件增项，向后兼容）
step_start/step_end/trace 行增 `domain` 字段（「章纲」「卷纲」…；共享读类＝空省略）。dock 轨迹组标「章纲助手 · N 步」；气泡署名不变。缺字段旧客户端零依赖。

### D5：线程独立性条款化（把已有实现升格为 MUST＋守卫）
会话 UNIQUE(user,book,thread)、消息/压缩态按线程存取、跨线程并发无全局锁——守卫测试钉死（两线程并发 run 互不串写）。同线程双发由前端 runActive 挡（后端不加锁，挂账注释）。

## Risks / Trade-offs

- 域映射漏配＝功能突然「没了」——启动校验 fail loud＋e2e chips→工具对照表
- 域外引导话术生硬——提示词包可调，走查验收
- 严格隔离牺牲跨域直答（设定页问章纲→引导切页签）——boss 拍板「独立流程」的直意；体验反例出现再评估 D2 的引导白名单

## Migration Plan

1. scopes.py：thread→域映射＋tools_for_thread＋启动校验＋测试
2. loop：native/text 双分支按线程声明收窄＋域外回喂引导
3. prompts：PAGE_DISCIPLINE 分节注入
4. 事件 domain 字段＋dock 轨迹标签
5. 线程并发守卫测试＋走查验证

## Open Questions

- 关系/伏笔/文风/操作四个章内页签当前 chips 多为前端动作（朱雀/润色/接缝），是否需要空域显式注册——实现时按 registry 对表，缺省落「默认＝全域共享读」
