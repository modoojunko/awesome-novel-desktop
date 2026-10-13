# Tasks

## 1. 后端：任务域骨架

- [x] 1.1 全局库新表 `deconstruct_jobs`（含 user_id、(status,queue_seq) 索引）＋ models 注册＋迁移：升 CLIENT_VERSION、版本库搬运清单核验、upgrade_drill 跑绿（dev 哨兵库首启 mismatch 属预期）
- [x] 1.2 `deconstruct/` 域目录：`router.py`/`service.py`/`pipeline.py`/`textparse.py`/`apply.py`
- [x] 1.3 端点：POST /api/deconstruct/tasks（multipart ≤50MB：Content-Length 预检＋块累计双检、流式落盘 staging）、GET /tasks（含位次，心跳/徽标由此派生）、GET /{id}、POST /{id}/cancel、POST /{id}/resume、POST /{id}/retry-upload、POST /{id}/import-book、POST /{id}/export、DELETE /{id}；探针**复用** POST /api/configs/{id}/test（model 覆盖），不新增端点
- [x] 1.4 dispatcher：常驻 daemon 线程自带 loop＋进程内单例守卫；启动 sweep（running 无线程→failed(interrupted)；queued 缺源→need_reupload；有源按 seq 续跑）；cancel 走 jobs 表列、段边界检查；逻辑拆为可直调函数（pytest 不触发 lifespan）
- [x] 1.5 路由按 user 过滤，风格对齐既有 routers

## 2. 后端：解析与管线

- [x] 2.1 **新建** `textparse.py`：编码探测（utf-8-sig→gb18030→big5，全失败明确报错）＋「第X章/卷」纯文本正则分卷分章＋字数/解析提示统计（仅对齐 importer 数据结构与字数口径，不复用其 markdown 解析）；真实网文 txt 样本（含 GBK、无空行章标题）进夹具
- [x] 2.2 阶段一 prescan：逐章梗概（模板 deconstruct-prescan，JSON 输出），章号由代码记录入 dims_json
- [x] 2.3 阶段二十维度 map＋通用 reduce（12 份模板；`_estimate_tokens` 启发式中文≈1.6 字/token 切段窗；摘录代码盖 `【第N章】` 前缀；段级重试 2 次＝内存计数＋dims_json.error 留痕；维度失败即停）
- [x] 2.4 模型输出 JSON 校验（对每维度 schema）→ 代码渲染 md（front matter＋固定 H2）入 products_json；缺证据标记的条目按维度重试一次
- [x] 2.5 staging 规则：仅 completed/deleted 清理；failed/cancelled 保留源文件；启动清陈旧 staging

## 3. 后端：出口

- [x] 3.1 `apply.import_book`：幂等（task.book_id）→ create_project（满额错误上浮）→ 勾中维度写入（world KV factions clamp≤6、character_service.create_character 同名 409→改名/role 白名单映射、hooks FK 置空＋章号文本、主线/文风走既有写入）→ 降级清单回传；各维度入口函数名在 apply.py 头注登记（实现时勘探对齐）
- [x] 3.2 `apply.export`：勾中产物＋README 物化到所选目录，错误分类 disk_full/permission/path
- [x] 3.3 删除任务：连带 staging 源文件与产物（已导出副本不受影响）；二次确认由前端承担

## 4. 提示词仓（awesome-novel-prompts）

- [x] 4.1 **12 份模板**：`deconstruct-prescan` ＋ 10 份维度 map ＋ 1 份通用 `deconstruct-reduce`；每份 `<<system>>/<<user>>` 分层，system=角色＋三铁律（逐字同句）＋JSON 输出契约，禁自行编号章号；变量清单按评审草案（book_name/genre_or_unknown/full_synopsis/seg_range/excerpts/dim_name/partials…）
- [x] 4.2 三铁律逐字锚 pins 测试（每份模板断言三句在 system 段）＋ JSON 契约测试过 test_json_contract
- [x] 4.3 TIER_FREE 登记（free 累积集）＋ `sync.py all`（manifest/README 重生成）＋ `sync.py lint` ＋ 仓 pytest 全绿（本机 venv ≥3.10）
- [x] 4.4 发布链四步登记进仓 README/任务：build --version → 上传 → S端登记 → verify+smoke → 最后翻 latest.json；双仓 commit 互引 c-deconstruct-book；缺包探测按模板名存在性（不升 min_pack_version）

## 5. 前端

- [x] 5.1 `ToolsMenu` 共享下拉原语（portal+fixed，Esc/点外收起，z-index 压 scrim 下）挂 Navbar；路由 /tools、/tools/deconstruct/new、/tools/deconstruct/:id（Authed 段）
- [x] 5.2 queryKeys `deconstruct` 键族＋`useDeconstructTasks` 轮询 hook（1.5s＋quiet/stall 守卫，终态停表）；心跳胶囊（非交互 span）与菜单徽标（进行中+排队+已完成未取）
- [x] 5.3 清单页（六类状态行＋空态引导＋删除二次确认）
- [x] 5.4 创建页（双子态：未选文件空上传区+创建禁用／已选·解析完成；编码探测回填；模型选择字段复用 ModelPicker＋全局选项 hook；探针门复用 configs test；范围勾选下限 1；隐私/费用/耗时提示）
- [x] 5.5 详情页三态：进行中（十步进度＋取消）、完成（目录树勾选＋出口弹窗：建书摘要动态 N/7＋导出 N 份）、失败/已取消（错误面板＋续拆＋删除确认）、需重传引导
- [x] 5.6 文案语气过 design-language §13（动词按钮、出口齐全、info/ok/warn/err）＋ coverage-contract 登记新文件

## 7. PR 评审修复（2026-10-12，Code Reviewer 一轮）

- [x] 7.1 P0：建书消费模型 JSON（products_json 带 data），废除 md 反解（mainplot 静默失效根因）
- [x] 7.2 P1：world no_power 语义修正（仅「无超凡/原文未明确」置真）；power/cost 条目化；伏笔章号从 JSON 取（plant_ch）
- [x] 7.3 P1：前端建书成功用返回值 book_id 直达新书设定页
- [x] 7.4 P1：导出目录接 pywebview pick_folder 桥（手输回落）
- [x] 7.5 P1：建书幂等先落 book_id（创建成功即记，失败重试不重复建书）
- [x] 7.6 P2：dispatcher env 开关（测试禁真轮询线程）；DELETE 拒 running；retry-upload 上限前置（块累计）；selected_dims 坏 JSON 400；datetime 统一 UTC；徽标排除已建书
- [x] 7.7 P2：轮询 hook 改 React Query refetchInterval＋failRef 守卫（fetchFailureCount 每 interval 重置不合守卫语义，实测后换 ref）；console.log 清理

## 7b. 二轮评审修复（2026-10-13，review-agent 全 diff 扫）

- [x] 7b.1 P2：文件夹出口落「已取」标记——新增 exported_at 列＋导出成功落笔＋badge done_unpicked 收窄（book_id 与 exported_at 双空才计数）
- [x] 7b.2 P2：书名输入框 readOnly 与 label「可改」相悖——改可编辑（bookName 提升 state，换文件重置）
- [x] 7b.3 P2：apply no_power 死表达式（`... and False` 恒假）——按 P1-2 口径重写为「无超凡/原文未明确」双标记匹配＋双臂测试
- [x] 7b.4 P3 六处：selected_dims 坏 JSON 500→400；queued_ahead 按仍 queued 行计数（空洞不虚高）；started_at 在 _claim 落笔；删死代码 pipeline.resume_task；清单删除失败显提示；时间列格式化；详情页加载失败分支
- [x] 7b.5 PR 卫生：剥离 ab2c8757 夹带的两个无关 openspec 变更目录（c-api-config-save-gate／c-polish-v5-diagnostic-gate，工作区保留归原会话）
- [x] 7b.6 三轮评审（修复批增量）P3×3：exported_at 列注释补 db-per-version 处置口径（实勘全仓无旧形状表，零暴露）；详情页错误分支改 taskErr&&!task（RQ 留旧 data，轮询单次抖动不踢错误屏，含回归用例）；test _run 重复定义删一处

## 8. 待办（后续批）

- [ ] 8.1 e2e 全链（隔离栈）
- [ ] 8.2 前端「本地解析回填」GBK 大文件极限（浏览器 TextDecoder 内存上限）观测
- [ ] 8.3 提示词仓发包（build+上传+S端登记+翻 latest.json，随下个发版窗口）

## 6. 测试

- [x] 6.1 后端 pytest：textparse（GBK/纯文本章标题/探测失败）、队列串行与 sweep（直调 dispatcher）、cancel 段边界、管线段级重试与 JSON 校验（模型打桩）、建书清洗降级（同名/clamp/FK 置空）、导出错误分类、缺包引导
- [x] 6.2 前端 vitest：ToolsMenu、清单行、创建双子态与探针门、模型下拉分组选中、目录树勾选联动摘要、轮询 hook 终态停表
- [x] 6.3 e2e（隔离栈）：创建→排队→拆解（打桩模型秒级）→完成→导出 全链一条
- [x] 6.4 全量门禁：client pytest 全绿（2040 passed）＋vitest 全绿（1572 passed）＋ruff＋tsc 零错＋提示词仓 pytest/lint 全绿（90 passed）
- [x] 6.5 coverage 阈值 100×4 全绿（2026-10-12 收口：探针慢臂/非 Error 臂/JSON 兜底臂/防御回落/勾选加臂全部补测后通过；v8 对 TSX/async 行归属漂移为工具链已知限制，与门禁无关）
