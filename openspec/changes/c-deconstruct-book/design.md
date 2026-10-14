## Context

- 交互真值：`docs/design-c/drafts/ai-novel-c端-拆书.html`（v9 六态）。四方评审（前端/后端/产品/架构，
  2026-10-12）＋立项三路评审（研发/产品/提示词工程师，2026-10-12）结论已收敛进本设计。
- 现状锚点：后端 `client/backend/` 域目录布局；全局单飞槽 `job_runner.py` 与备份/成稿下载共用（不可占用）；
  **`novels/importer.py` 解析不可复用**（utf-8 硬编码、章节识别只认 markdown `##` 标题，真实 txt 的
  「第X章」纯文本行会全部丢弃）——txt 解析须新建；**仓内无 token 估算器**（ai_client 无 estimat*）——须自建；
  设定清洗护栏在 `settings/world_model.py`（factions≤6）、`settings/character_service.py`（同名 409、
  role 白名单）、`models/hook.py`（章引用可空 FK）；提示词经 prompt-pack CDN 分层包（缺包 503 先例），
  模板源在独立仓 `awesome-novel-prompts`（分层测试钉死「逐模板独立、不做跨模板共享层」；
  `test_json_contract.py` 倒置默认：模板必须含 JSON 输出契约；`publish.py` TIER_FREE 登记免费档）。
- 前端 React Query 刻意关闭 refetchOnWindowFocus；长任务轮询先例 `ManuscriptDownloadModal`
  （setInterval＋quiet＋stall 守卫）；顶栏菜单唯一先例 AcctMenu（portal+fixed+点外/Esc 收起）。
- 现有路由按 user 过滤；pytest 多不触发 lifespan（队列/sweep 用例直调 dispatcher）；conftest 有
  SDK/模型打桩先例；e2e 隔离栈 `docker-compose.e2e-iso` 可用。

## Goals / Non-Goals

**Goals:**
- 单机闭环：上传→排队→串行拆解→勾选出口（建书/导出），全程自备 key、无计费门禁。
- 断点续拆：维度级状态持久化，任何中断（失败/取消/退出应用）后只补勾选范围内未完成维度。
- 与既有体系零冲突：不占全局单飞槽；建书经域服务（不直写表）；提示词走既有分层包机制。

**Non-Goals:**
- 维度并行/多 worker；批内（单批归并中途）续拆；epub/docx 输入解析；产物应用内预览/编辑；
  优先级插队；S 端任何改动；书内附属资料独立入口（v1 仅任务详情可见）。

## Decisions

1. **调度：专属表＋私有常驻串行 worker。** 新表 `deconstruct_jobs`（全局/版本库），字段：
   `id, user_id, status(queued|running|completed|failed|cancelled|need_reupload), queue_seq,
   source_name, source_size, encoding, book_name, total_chars, chapter_count, volume_count,
   parse_warnings_json, api_config_id, ai_model, dims_json(cards{state,done,entries{章:卡}}＋十维 {state,seg_done,seg_total,error}),
   products_json(十份产物事实源), source_path, error_json, book_id, created/started/finished_at`；
   索引 `(status, queue_seq)`；queue_seq 分配 `MAX+1`，排序兜底 `(queue_seq, created_at)`。
   **线程模型钉死**：常驻 daemon 线程自带事件循环（照 `archive/dossier.py` 先例）＋进程内单例守卫
   （打包态单 uvicorn worker，仍防重复启动）；**cancel 载体＝jobs 表列**（worker 每段边界查列），
   不用内存 Event。lifespan 启动 sweep：running 且无线程→failed(interrupted)；queued 且源文件缺失→
   need_reupload；有源 queued→按 seq 续跑。pytest 不触发 lifespan——dispatcher 逻辑写成可直调函数。
2. **上传：独立端点＋staged 落盘。** `POST /api/deconstruct/tasks`（multipart ≤50MB）：Content-Length
   预检＋读块累计计数双检（Starlette spool 落盘），写 `DATA_ROOT/deconstruct-staging/{task_id}/source.txt`；
   **解析新建 `deconstruct/textparse.py` 纯函数**（编码探测 utf-8-sig→gb18030→big5；「第X章/卷」纯文本
   正则分卷分章——不复用 importer 的 markdown 逻辑，仅对齐其数据结构与字数口径），解析在线程池，
   内存峰值注明（50MB 全量文本 ≈ 150MB 字符串，可接受单机）。真实网文 txt 样本进测试夹具。
3. **管线 v2：逐章拆卡＋分维度分级语义归并，模板 12 份，模型输出 JSON、代码渲染 md**
   （2026-10-13 用户拍板替代 v1「prescan＋段×维度 map-reduce」：证据粒度到章、去重去冲突成为显式
   职责、合并截断废除）。阶段一每章一次调用 `deconstruct-card` 产出十维拆书卡（summary＋各维碎片，
   只以本章可见内容为据、每维限量宁缺勿滥）；阶段二按维度把逐章碎片按字数分批喂 `deconstruct-{dim}`
   （模板同批改造为「卡片归并口径」：语义去重别名合并、冲突并立降 low、零新增），多批产物用
   `deconstruct-reduce` **树状收敛**（`_pack_units` 分组循环直到单份）——任意长度无截断。卡片碎片由
   代码盖 `【第N章】` 前缀，模板写明「章号只来自材料标注，禁止自行编号」。落库粒度：cards.entries
   按章（断点复用到章），归并 partials 内存态不落库（维度失败重跑整维度）。模型输出 JSON（沿提示词
   仓 JSON 契约倒置默认），C端代码渲染 md（固定 H2 键序）存 products_json。三铁律逐字进每份模板
   system 段＋提示词仓 pins 逐字断言防漂移。单元级重试 2 次（章/批），维度失败即停任务。
4. **产物事实源=DB。** 十份 md（代码渲染）存 `products_json`；`存本地文件夹`＝从 DB 物化写盘
   （pick_folder 桥已有，错误分类 disk_full/permission/path）；staging 清理仅限 completed/deleted
   （**failed/cancelled 保留源文件以支持续拆/重传**）＋启动清陈旧 staging（照 `clean_stale_staging`）。
5. **建书编排：`deconstruct/apply.py` 单点，幂等键=task.book_id。** 调 `novels/service.create_project`
   （过 require_project_limit，满额错误上浮保导出出口）→ 勾中维度写入经域服务：world KV 写入
   （factions clamp≤6 溢出并提示）、`settings/character_service.create_character`（同名 409→自动改名
   “名（拆书N）”、role 白名单映射）、hooks 写入（新书无章→FK 置空＋章号入文本）、主线/文风走各自
   既有写入函数（实现时按域服务现状对齐，列在 apply.py 注释为勘探清单）。溢出/降级汇总为完成态
   提示条。关系/章卷/技法不建书内表，任务详情即查看处（v1 明示）。
6. **前端结构。** 路由 `/tools`（清单）与 `/tools/deconstruct/new|:id`；顶栏 `ToolsMenu` 抽共享下拉原语
   （portal+fixed，照 AcctMenu 纪律），z-index 压 scrim 之下；轮询 hook `useDeconstructTasks`
   （setInterval 1.5s＋quiet/stall 守卫，终态停表）；queryKeys 增 `deconstruct` 键族；组件放
   `src/components/tools/`；模型选择复用 `ModelPicker`＋全局平铺选项 hook（不带 projectId）；
   探针门复用既有 `POST /api/configs/{id}/test`（支持 model 覆盖，**不新增探针端点**）；心跳胶囊
   ＝非交互 span，由 GET tasks 轮询派生；菜单徽标口径＝进行中＋排队中＋已完成未取。
7. **文案与语气。** 按钮动词（创建任务/续拆/导出/去配置）；语气词仅 info/ok/warn/err；提示条均带
   可点击出口；隐私/版权与耗时/费用预期文案落在创建页（spec 有验收场景）。

8. **图谱层 v3.0 并入本变更（2026-10-14 用户拍板；三路评审两轮意见全部吸收）**：

   **派生谱系（评审话术修正，三句话定死）**：`cards.entries`＝事实源（模型产出）；
   `dims_json["graph"]`＝**带模型调用的归一化断点缓存**（别名册/parent 边集/id 名册；append-only、
   **已分配 id 永不重排**——否则续拆后实体插入平移旧 id、图谱边全体错位）；`图谱.json`＝导出件内
   唯一机器正身，html/svg 是它的视图；全部可再投影、不可回流。换包重跑归一会改变图谱，不承诺跨包
   复现——`导出清单.json` 的 sha256 即取证链。

   **装配＝管线阶段三**（全部维度归并完成后、置 completed 之前；评审 P0：不是"导出时刻"——quote
   原文回验要读 staging 源文件、归一化要调模型调用、降级要可取消可进度，导出时刻全不成立）。
   导出端点＝读 dims_json.graph 缓存＋纯渲染物化（内存装配完成才落笔、清单最后写、失败零半成品；
   staging 清理时机改"阶段三跑完即可清"）。`run_task` 状态机改造：全边界 round-trip 保留 dims_json
   未知顶键（管线为唯一写者，导出侧除 exported_at 外禁写）。

   **能力戳（评审 P1：老包判点不能设在导出时——用户白跑 30 分钟）**：任务创建时加载 card 模板、
   断言契约含 presence 字样→caps 戳记入任务行；以已装包 receipt 版本≥13 模板首发判定；导出/降级两臂
   只认行内戳不认当前包态；无 caps→创建页 warn「当前能力包出不了图谱」（不拦截，md 仍值钱）。
   本条**取代 tasks 4.4 的"模板名存在性、不升版本"口径**。

   **封闭 enum 与关系纪律**：relTypes 五组 19 型入契约；kind 逐字选＋自定义逃生口（raw 原文措辞）；
   同义归并住归并层（卡片产原文措辞）；边＝跨章稳定关系，动作（作证/施压/截杀/收留）归 events/presence。
   **events 来源（评审 P1 补账）**＝mainplot 归并终稿 arcs 的代码投影（title/起止章直映射；at=该章区间
   presence 众数地点；members=该区间在场人∩弧线提及名）；无 arcs 时 events:[]＋warning，契约保形。

   **地点纪律**：卡片产 places 闭集＋presence（who/where 逐字抄卡内名，禁补专名；where 可 null＝未知区）；
   跨章归一名册在归一化段（泛称宁留两户不错并）；parent 只认隶属直陈＋代码传递闭包＋环检测（有环边降
   null 留痕）；首现＝min(引用章) 代码盖章。形状防御复用 apply 口径（非 dict 跳过/字符串包装/超限截断，
   计数入 warnings）。

   **视图分工（用户令）**：关系网只答人与人——网页签下点人不亮地点树、侧栏无足迹段；「人在哪」仅场景图
   （框·钉·跨框线·翻页）与地点树承载。阅读过滤器（ego 聚焦＋戏份 TopN）采实现裁量（原型未画控件，
   以 spec 文字为验收准绳）；60 万字真书可读＝发布闸门。

   **渲染器与模板归属（评审 P1 定案）**：查看器模板＝后端静态资产
   `client/backend/deconstruct/assets/graph_viewer.html`（原型 v7 生产化：JSON 岛与标题两处唯一 token
   str.replace 注入——禁 .format；原型 chrome 文案清零＋grep 断言；模型文本一律转义/textContent——
   v7 的 innerHTML 直插在生产是用户浏览器注入面，golden 配对抗夹具；BOX/坐标改 layout 块驱动；
   CJK 字体栈保留、svg 自带同栈）。inline JS 不入 vitest 门禁（归后端 golden：同输入同字节、
   禁 wall-clock、动态字段仅 meta.warnings/completion）；layout 计算住 graph.py 产物、html/svg 共读。

   **降级与开关（评审 P1：开关必须落成具名交付物）**：三级降级（单元重试→degraded 占位→带 warnings
   照常出）；meta.warnings＋完成度恒在；**双指标口径**：在场覆盖率≥97% 硬指标、定位率只报数不设死线
   （v7 自身 30/31 即口径矛盾的判例）；**图谱导出总开关**（env `DECONSTRUCT_GRAPH_EXPORT` 默认开；
   关＝回落 10md＋README＋文案同步，带关径用例；开关关≠退 presence token，止损退路＝轻量 presence
   模板预案）。仅装配结构性异常拒发（400 可读）。

   **导出目录**：`导出清单.json`（sha256＋task＋contract，最后写）；用户手改件下次导出先转 `.bak-时间戳`，
   响应回传 backups[] 前端上浮；三件套与清单**固定附带**：不可勾、不进 files、不计 product_count
   （files 语义恒＝md 勾选集，现 .md 白名单不扩）；README 写「正身副本不回流」；badge/exported_at
   语义零改动。图谱不建书（v3.x 挂载制挂账）。

## Risks / Trade-offs

- 31 分钟长任务×自备模型：单元重试+断点续拆把最坏损失限制在单章/单批；探针门前置拦截配置错误。
- DB 存卡 JSON＋10×几十 KB md＝单任务约 0.5–2MB（百章量级），SQLite 无压力；归并 partials 不落 DB。
- 无状态单发的跨章一致性押在归并口径上：别名漏归并/弧拼接变弱是 map-merge 形态固有残差，如实标注。
- 任意 txt 是提示词注入面：产物仅静态呈现、入库全走域服务清洗；不执行产物内指令。
- 提示词发包晚于本仓发版：按模板名存在性探测降级为创建禁用＋引导（不 503 白屏）；
  **发布顺序铁律**：本仓合码 → 提示词仓合入+build+上传+S端登记 → 翻 latest.json → 用户更新客户端。
- 串行队列可能长排队：FIFO 不做插队（观察项）。
- 新表改变 schema 指纹：须升 CLIENT_VERSION，dev 哨兵库首启 mismatch 改名属预期，跑 upgrade_drill。
- 图谱并入＝#842 单 PR 双身位：引擎面三轮评审不失效，图谱面二轮按 spec 新 Requirement 逐条对审；
  真机不达标回退三档：关导出开关（md 先行）→切轻量 presence 模板→revert 图谱 commits（独立文件面）。
- presence 让卡片输出 +15~30%/章（估）：max_tokens 按 operation 预算上调；开工 10.1a 熔断——真书
  20 章人工核（在场覆盖率/错并户/token 实测），过关进 10.2，不过关切轻量模板预案。单机无遥测通道，
  「≥200 章遥测」改为发版前 3 本真书跑批统计脚本（产物入评审记录）。
- 头4000尾2000 对 presence 双刃（中段地点/转场证据仍盲）：以 10.1a 实测覆盖率裁决是否回加中段抽样。
