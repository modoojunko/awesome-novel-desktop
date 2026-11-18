# c-agent-decision-archive Tasks

## 1. 决策档案文件后端

- [ ] 1.1 memory.py：档案路径（DATA_ROOT/decisions/<novel>.jsonl）＋append/list（created_at 倒序）/按 id 幂等判重；add_decision/list_decisions 去 db 参数
- [ ] 1.2 delete_book_memory：DB 记忆行照删＋档案文件移除；novels 删书级联调用点签名同步
- [ ] 1.3 tools.py：_memory_decide/_memory_recall 卸 async_session 包裹（文件自持）

## 2. 分层注入＋召回工具

- [ ] 2.1 render_memory_section 分层：预算内全文→超预算索引行（日期＋首句 40 字）→索引预算 600 字→尾注在档计数（有出路话术）；规矩段零变化
- [ ] 2.2 recall_decisions 工具（read/low，query+limit，子串不分大小写，单条裁 160 字，空档如实）＋scopes._SHARED_TOOLS 注册＋工具描述写使用时机（索引尾注呼应）

## 3. 迁移＋测试

- [ ] 3.1 migrate_book_decisions()（幂等按 id 跳过）＋main lifespan fail-soft 挂钩＋日志行
- [ ] 3.2 钉子：档案契约（append/幂等/坏行容忍）；分层注入三态（全在预算/部分索引/尾注计数）纯函数钉；recall 命中/空档/裁剪钉；迁移对拍＋幂等；删书级联清文件
- [ ] 3.3 全量闸：pytest＋ruff 全绿（route 既有钉回归）

## 4. 收尾

- [ ] 4.1 重建安装＋真库走查：存量决策迁档案→注入段含索引/尾注→对话中提旧决定召回全文
- [ ] 4.2 归档（与 c-agent-nav/c-agent-session-files 一并收）
