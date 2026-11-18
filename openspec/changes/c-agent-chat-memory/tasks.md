# c-agent-chat-memory 任务

> 实施补记（批7 终局）：e2e 15/15 全绿于本会话自建栈（iso server 19001＋iso client 8001〔当前分支代码重建镜像〕＋vite 5199）。过程中根治三件环境/契约级问题：①iso 容器跑的是 11-14 旧镜像（tag 未随重建更新）＋数据卷旧 schema（assistant_sessions 无 thread_key，create_all 不加列）——重建镜像（Dockerfile.e2e 本地 brand 注入绕镜像源白名单）＋清库重启；②config.json 经宿主 virtiofs 写入容器侧延迟可见（rename/就地覆写皆撞）——spec 改 docker exec 容器内写＋回读校验；**且轮询曾打真 check-auth 触发「陌生 pc_hash→会话失效→清凭据」链自毁会话**，改容器自读自验；③**chat.css 唯一 import 随 ChatDock 退役被带走**（dock 全程裸奔＝抽屉/芯片/卡面无样式，⑭ 抽屉不藏、⑨ 卡面错乱的总根）——Aui2Dock 补回 import。
>
> 实施补记（批1）：①vitest 对 @agentscope-ai/* 的解析存量红（包缺 main/exports）已在 vitest.config 钉 alias＋inline 修复，NovelWorkspace 套件 35/35 救活；②前版 Aui2Dock 丢的 open 芯片富交互入口（ai_write/renwei 等走既有弹窗链）与状态感知开场白已补齐——onOpenAction/onUpgrade/onCloseDrawer 三 props 平移自 ChatDock。

> 分支：c-agent-fleet（本分支已实装 Aui2Dock 默认＋AuiErrorBoundary，本 change 在其上收口）。

## 1. 卡面 spike 与 ChatAnywhere 定版

- [x] 1.1 customCards API spike：ChatAnywhere cardConfig 注册自定义卡一次实机验证（按 name 匹配消息、渲染、updateMessage 翻转卡面态三步走通）
- [x] 1.2 Aui2Dock SSE 桥升级：artifact 事件→卡消息（kind+payload 透传）、gate 事件→授权卡消息；移除「产物卡已生成」「● tool ✓」文本占位（轨迹行保留轻量文本形态）
- [x] 1.3 产物卡 customCards 挂既有 CardBody 按 kind 渲染；授权卡卡面（预览＋允许/拒绝按钮→approveGate 端点→卡面翻转已授权/已拒绝/过期三态）
- [x] 1.4 卡面视觉走 chat.css 既有语义类，design:lint 过（不新增档位/组件词汇）
- [x] 1.5 授权模式芯片重挂：输入区常显当前档＋下拉三档（confirm_each/allow_book/allow_all）→既有 setPermissionTier 端点即时生效；切换在对话流落一行回执；硬地板仍停车弹卡（write_gate 语义零变化）；芯片文案与形态自 ChatDock 平移（念出声检查）

## 2. 全模型逐字流式（哨兵分节协议）

- [x] 2.1 ACT_PROTOCOL 兜底稿改「叙述先行＋===ACT=== 哨兵＋动作 JSON」；reply 字段退役
- [x] 2.2 loop.py `_run_text` 哨兵切分：哨兵前增量 yield narration_delta（字节直通）、哨兵后攒全量解析动作；缺哨兵兜底 action=final；哨兵行不进任何交付文本
- [x] 2.3 deepseek 回归钉保留并扩展：裸 JSON 永不出现在 narration_delta／哨兵前逐条增量／缺哨兵兜底 final／动作 JSON 正确解析（fake client 四场景单测）
- [x] 2.4 提示词包 assistant_act 模板同步改写（内置兜底稿先行，发包挂账提示词仓下一批）

## 3. 分层记忆数据层

- [x] 3.1 models/assistant.py 增 BookAgentMemory / BookDecision 两表（novel_id FK CASCADE＋index）
- [x] 3.2 建表走 create_all 零迁移路径（项目惯例修正：assistant 模块无 alembic；两表随启动自建，design.md 已注记）
- [x] 3.3 删书级联：既有删书路径挂两表显式清理（FK ondelete 双保险）；删书测试补两表零孤儿断言

## 4. 记忆注入链与工具

- [x] 4.1 assistant/memory.py：load_book_memory_section（记忆全量＋决策倒序；空书空段省略；容量护栏记忆 ~800 字＋决策 ~1200 字超限从最旧截断）
- [x] 4.2 prompts.py L1 拼装序固化：身份→作家人格覆盖→书级记忆段→围栏→动作协议→域纪律；run 级装载一次（本轮会话不重复查库）
- [x] 4.3 四记忆工具（recall_book_memory / remember_book_memory(content, memory_id?) / forget_book_memory(memory_id) / remember_decision(decision, reason?)）封闭注册＋write_gate 免授权白名单
- [x] 4.4 scopes.py 全域共享组挂账（所有页签域可持）＋启动校验覆盖四工具
- [x] 4.5 记忆工具单测：增/改/删/决策四操作＋免授权路径＋透明告知话术（工具 summary 人话，念出声检查）

## 5. 旧前端退役

- [x] 5.1 NovelWorkspace 移除 `?aui=0` 分支与 ChatDock 挂载；chatRegistry 遗留导出清理
- [x] 5.2 删 ChatDock.tsx / AuiDock.tsx / SseChatAdapter.ts / useChatSession.ts / ChatMarkdown.tsx（删前 grep 同名引用判例）；package.json 移除 @assistant-ui/react
- [x] 5.3 前端单测改写：引用旧组件的用例随新前端重写（保留行为断言换选择器）；coverage 阈值过

## 6. 契约保持验证

- [x] 6.1 斜杠命令 /new、/compact 在 ChatAnywhere 输入框可用（命令不进历史、回执呈现）
- [x] 6.2 思考增量呈现＋完成后折叠回看；工具轨迹行步开始/结束呈现
- [x] 6.3 chips 结构化触发（tool_hint 随下一次发送）；页签切换分隔标记；容量条 ≥80% 警示
- [x] 6.4 崩溃兜底验证：ChatAnywhere 渲染异常→错误提示＋重试→历史重装载（错误边界单测）
- [x] 6.5 授权模式三档行为钉：allow_book 下实体写自动放行带回执＋撤销 chip、硬地板仍弹卡；agent 让「给自己开自动放行」无工具可调档位不变；重启/切页签档位持久接续（单测＋真机各一钉）
- [x] 6.6 e2e 改写：dock 相关用例换 Aui2 选择器全绿（逐字流式含 text 协议模型场景）

## 7. 收尾

- [x] 7.1 后端全量 pytest＋前端 vitest coverage＋design:lint/design:check 全绿；tsc --noEmit 双过
- [ ] 7.2 真机走查（boss 手测项——GLM/deepseek 逐字流式／真卡面／授权芯片三档／记忆跨页签生效／切书隔离）：GLM 逐字流式／deepseek 逐字流式无裸 JSON／产物卡真卡面／授权卡流内决策／授权芯片三档切换与回执／记忆记住并跨页签生效／切书隔离
- [x] 7.3 proposal 文案口径复核（§13 动词按钮、无内部术语、念出声）
