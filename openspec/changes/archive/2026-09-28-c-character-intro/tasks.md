# Tasks: c-character-intro（章纲人物精盘）

> v4（2026-09-27 三轮评审收口）：在 v3 基础上补 P0×6（手填空白形态/门控按页签分派/指纹只盖剧情输入/重盘对回/阈值按维数传参＋并列口径/delta 许可泛化）与 P1 清尾。

## 0. 基线与原型

- [x] 0.1 **实现基线对齐（1.x/3.x/4.x 的前置）**：worktree 先合 origin/main（#513/#515/#516/#518 均在 main）再开工——tasks 形制（cap() 行式、.fro 只读行、e-meta）都按 main 写。验证：`git merge-base --is-ancestor origin/main HEAD` 成立＋抽查 cap() 行式/.fro/e-meta 形制与 main 同源
- [x] 0.2 改 `docs/design-c/prototypes/book.html`（写作工作台原型，照设计稿 v2.4；注：仓内无 write.html）：右栏统一卡片新增能力行「盘点出场人物」（行级门控：盘点行免费，PRO 行 ra-off＋「需 PRO」）；弹层十一态（含确认页两形态：选卡进=预填+返回换一张／手填进=空格无返回；档位跟用户不跟场景；写入后回结果页多缺人回程）；壳层＝七页签＋e-meta 八枚（REQ_FIELDS 分母 2）。ADJUSTMENTS.md 待登记（逐类对照表）：①入口 ra-step 行②**ra-* 作用域 12 条去 .settings-v 前缀**（ra-off/ra-off:hover/ra-hint/ai-target/ai-target b/ra-foot b/locked .ra-body b/locked .ra-arrow/ra-running×3/gap-c）③新词全清单（cr-* 十一个、g-head/g-why/g-act/g-done、lock-card、no-card、pick-foot .push、pick-busy .none、badge-muted、cr-sug）④值差复用登记（rp-dot 7px、pick-error .edit-bar、kicker、pick-busy flex-column）⑤A/B 角标小字⑥文案对照表（v2.1/v2.3/v2.4 注释）。验证：原型可点通十一态含两形态、登记齐
- [x] 0.3 双端影响判定：book.css 去前缀（12 条）＋AiWriterAssistant 加 subTitle 插槽均属共享词汇/共享组件 → 三域（设定/卷/写作）右栏截图对照回归＋`node scripts/design-cross.mjs` 结论入 ADJUSTMENTS；cr-* 弹层内自含不触共享段（补齐 2026-09-28 归档批：design-cross 初跑红＝c-chapter-plan-ai 期 `--faint`＋注释未同步 server 端，两端同提修复后零差异；三域挂载实勘 SettingsView/VolumeAssistPanel/AiAssistPanel；全量 vitest 968/968 绿；结论已入 ADJUSTMENTS）

## 1. 后端：盘点端点＋提示词

- [x] 1.1 新建 `client/backend/prompts/cast_review.prompt`（**单文件 `<<system>>`/`<<user>>` 标记式，走 load_layers()——与 #538/#540 分层协议同形制，零加载器改动、test_prompt_layering 闸门天然覆盖**；终审裁定弃四件点分文件）：system 段五段＋【输出示例】（示例住 system、必带 gap.why_not_old、行前「以下为格式示例，不是本次输入」）；user 段 `=====【块名】=====` 动态四块（素材/本章剧情条目/章纲留存格/临时要求——块界常驻＋`<<key>>` 占位走 _render；【素材】【本章剧情条目】块头带 #540 边界声明；临时要求空时渲染「（本次无）」）；静态句上移（配额钉句＋临时要求裁定句入【核心规则】、素材禁令行入【强制禁止项】）。见 design 决策 9三分类闭集（老角色能演/不起名也行/缺一个新角色，人话标签即取值、逐字不加标点）＋缺人行（这段戏缺的是+老角色为什么不行 ≤40 字+**suggest 预填∈加人/改段/延后，不恒为加人**）＋零新增常态＋依据短句 ≤30 字不做逐字寻＋不起名的称呼建议；硬规则第 1 条钉死「只判剧情条目里作者已写的条目，不推演不补写不评价」；**一段只判缺一个（缺多个写最缺的）**；**空场面段判「不起名也行」、as 留空**；闭集逐字值三禁（不加标点/引号/括注）＋**示例行覆盖全部闭集取值**；JSON 骨架＝gap 内联行对象＋idx/echo 照抄（见 design 决策 9 骨架）；配额行尾「不得改变三分类判定」；键名英文入服务端常量单源；负锚（模板不得出现改法/剧情建议/评分/grade 字样）。验证：模板渲染快照测试（含负锚＋**system 段零占位符断言**＋示例层位断言＋空块渲染）＋suggest 三值各出一次的表驱动样例
- [x] 1.2 新建 `client/backend/chapters/ai_cast.py` 盘点端点 `POST /api/novels/{pid}/chapters/{ref}/cast/ai-review`：挂 `require_novel_model`（只读例外）；**请求体＝表单快照**（plot_items＋留存格＋characters，照 SelfcheckBody 先例，不读库回退）；素材＝`_chapter_material` 裁剪子集（**主线一句话＝fullstory 句读截断 ≤100 字、标【主线（截取）】**/人物全名单（含别名）/出场名单/无卡名单——**不裸 dump known_entities**，加一行禁令「演这段戏的角色只写有名有姓的人，不写势力、地点、泛称」；过滤集合＝角色名∪别名∪出场名单∪无卡名＋**本卷配额档位行（服务端按已排章数派生：≤3 章或未达目标 1/3 为开卷期，否则收紧期）**；hooks=False）；**请求体 characters 并入 known_entities/无卡名单/软提示计数（当前章按快照，3s 未存名不漏）**；空章 422（跑在快照上）；归档 UI-only 禁用不加服务端 403；计量 operation=cast_review（温度 0.2/重试 0.1、max_tokens 4096；**重试喂回走 user 尾块【上次失败原因】，system 各轮恒定**）；失败/未配模型给引导不 500。验证：pytest（免费可用/未配模型引导/空章 422/只读不落库/快照同源/**计量 operation=cast_review 且不落生成类口径**）＋**负向锚：免费直调 ai-draw→403、ai-review 免费成功且响应无提案卡字段**
- [x] 1.3 输出契约与校验（决策 11）：逐段行（idx=快照 0 基不重排＋≤60 字回显；**空串条目跳过不重排，条目全空/零条时退化整章一行**）＋verdict 闭集（**归一化：strip＋句读＋唯一子串兜底**；出界丢行＋该段「这一段没判出来」warn 行可重试）＋「演这段戏的角色」逐名过 known_entities（滤空的「老角色能演」行保留＋warning 不重抽）＋suggest 出界缺省「加人」（**带 defaulted 标志，前端不打「AI 建议」**）＋整批重试只认 0 可用行/JSON 不可解析（MAX_ATTEMPTS=3）。**归一化分流＋否定护栏（前二字窗口）**：strip→句读→精确→唯一子串且命中位前二字窗口无否定词（含 不能/不必/不是/未必——单字窗挡不住「不是加人」）；**2 字短值（suggest/轴）只精确不子串**。验证：pytest 闭集漂移表驱动（每组 4–6 变体，含双命中/同值多次/量词漂移/**否定式判反即红（单字与双字否定变体都测）**；「唯一子串」=跨值恰一命中且该值恰现一次，≥2 命中/同值多次按出界；短值混入句走缺省）＋缺键 suggest→缺省+defaulted/滤空「老角色能演」保留+warning 不重抽/idx 位置对位与 idx 对齐双路径+空串条目跳过不重排/MAX_ATTEMPTS=3 只认 0 可用行/退化/零新增/丢行呈现
- [x] 1.4 软提示与配额：无卡名字全书口径 ≥2 章（`_cardless_cast_rows` **按 (vol_no, chapter_no) 去重**后计数，同章双名不误触发）→ 响应附「建议建卡」行；响应附 `quota`（有名有姓计数＋档位），前端不自算。验证：pytest 两章同名触发/同章双名不触发/计数口径

## 2. 后端：提案抽卡端点＋建卡扩参＋提示词

- [x] 2.1 新建 `client/backend/prompts/cast_draw.prompt`（单文件标记式同 1.1）：system 段＝角色＋【核心规则】（含转权句「【这几条路走过了】块内禁令与本任务同效」）＋【闭集定义】（轴/退场档/ranks 三维名逐字值）＋【输入内容识别】＋【输出规则】＋【输出示例】（示例剔 why_not_old）＋【强制禁止项】；user 段动态四块＝缺的人/素材（含【不要用这些名字】＋配额行）/这几条路走过了/临时要求（空态「（本次无）」）提案卡字段（轴闭集 身份/关系/功能｜称呼 ≤12 新名字｜他是干什么的 ≤30｜人设句 ≤60｜怎么出场 ≤40｜怎么退场 三选一+说明 ≤40｜老角色为什么不行 ≤30）＋**三维各看各的字段**（合不合适只看缺的人行/差别在哪只看人设句/好不好落地只看出场退场）＋ranks 声明「连排不跳档**不并列**」＋全文无等级字母＋「老角色为什么不行」不输出（服务端直抄、不 clamp，与源同界 ≤40）＋**输出骨架键名钉全**（axis/name/persona/entrance/exit_kind/exit_note/ranks/reasons，退场=档+说明两键）＋**示例剔 why_not_old 字段**＋**抽卡素材携配额档位行（收紧期每章新增 1–3 约束申报）**＋「称呼必须是新名字」＋**【不要用这些名字】名单块**（known_entities∪已出批称呼，防改字变体）＋exclude 中性禁令块位（**块正文＝「轴照旧三张各出一张、轴必须再用；禁的是同轴近似人设/换称呼同路人；仍要贴合缺的人」——「换结构上不同」措辞退役**）＋示例带齐三轴三档。验证：模板渲染快照（含负锚/示例全值覆盖且剔 why_not_old/system 段零占位符断言/块界常驻）
- [x] 2.2 `ai_cast.py` 抽卡端点 `POST .../cast/ai-draw`：挂 `require_ai_access`；自建 `CastExcludeItem(axis, name≤12, persona≤60)` 批 ≤9；服务端等级（**≥2 项第一=S（至多一张）、1=A、0=B；名次唯一第一才计分、并列第一不计该维；_grades 连维名列表+S 阈值双参数化**（3 维/4 维共用不共值）；why-not-old 服务端直抄缺人行（模型不输出、不 clamp、逐字断言）；重试喂失败原因摘要走 **user 尾块**不喂原文＋**clash 显式标志**判 exclude 温度（勿抄 warn 字符串嗅探）；`_grades` 阈值**按维数传参**：本卡 3 维＝2、拆章 4 维＝3，共用函数不共用阈值）；**请求体契约**（gapId/段锚文本/缺人行/characters 快照）；**称呼撞 known_entities 丢卡计入重试**；对拍＝同轴且人设句 difflib≥0.6 **或称呼等值**才丢；<2 张走重试阶梯（exclude 重抽不降温）；温度 0.7/结构性重试 0.3，max_tokens 8192；计量 operation=cast_draw。验证：pytest（门控/等级表驱动 3维2卡·3卡·并列样例＋**4 维回归样例（≥3=S 行为不变）**/组合对拍边界/称呼等值/称呼撞实体丢卡/axis 与退场档出界丢卡进重试/clash 标志降温断言/降级阶梯）
- [x] 2.3 **`create_character` 向后兼容扩参**：router+service 增可选 `persona`（clamp 300）与 `prefill`（**白名单硬校验只收 dossier.plot/background，非法键 400**）；role 默认「配角」；单事务（注入失败无半张卡）。验证：pytest（扩参落卡/缺省行为不变/clamp/非法键 400/**background 拼句逐字形制（退场档值原文）**/409 撞名语义不变/别名撞名 `_resolve_names` 名优先锁回归）
- [x] 2.4 `chapter_split.prompt` 规则 2 补句（**chapter-plan-ai MODIFIED delta 已出，见 specs/chapter-plan-ai/**）；钉词对拍测试随句同步更新。验证：pytest 拆章套件全绿＋钉词测试更新后绿

## 3. 前端：右栏接入＋弹窗

- [x] 3.1 `lib/castReviewApi.ts`＋`lib/drawSession.ts` cast 版（appendExclude 过滤适配 axis/name/persona）：键 `cs-draw:{pid}:{chRef}`，载荷含盘点结果/三选一/**输入指纹（只盖剧情输入：plot_items＋留存格；形制＝ogToPartial 同源归一后字段子集 JSON.stringify——落账写名字不失效，多缺人回程依赖此条）**/gapId 批次（**gapId=f(段 idx)**，跨重盘稳定；appendExclude **cast 专用分型**（axis/name/persona），勿复用 DrawExcludeItem 过滤（现过滤会整批丢 cast 条目））；清理＝**按 gapId 粒度**（该缺口写入落账后＋「从头再来」；全键只在全部处理完）；恢复按档位裁剪（免费档丢 cards 载荷）；指纹不符→弃用并给「剧情改过了，重新盘点」；「重新盘点」＝全量重跑＋**按段 idx 对回合并**（未改条目处理记录与批次沿用、改过条目作废）。验证：单测会话恢复/换章清场/gapId 粒度/降档裁剪/指纹失效
- [x] 3.2 `workbench/CastReviewModal.tsx`＋`hooks/useCastReview.ts`：phase（reviewing/result/**cards**/**drawing**/picked/error＋error.kind∈review|draw，与 11 态一一映射）＋缺口表按 gapId；**确认页两形态**（选卡进＝预填＋返回换一张；手填进＝空格表单无返回——免费手填路径不露任何 AI 预填）；「AI 建议」标随改选消失、**defaulted 标志不打「AI 建议」标（含会话恢复后同口径）**；多缺人回程（**写入成功回 result 态、缺口转已处理、剩余继续、全部处理完收场、回执附「还有 N 个没处理」**）；「返回盘点结果」「‹ 返回换一张」出口；关窗丢格子改动、批次随会话保留；免费态＝按钮级锁定无假卡面；失败三出口（盘点失败＝重试/去模型配置/先不盘点，无「自己填」）＋抽卡在途等待态（pick-busy）；并发双击在途互斥。验证：组件单测（11 态流转含两形态/回程/suggest 预填/延后零请求/降档恢复/error 两 kind 三出口/双击互斥/defaulted 不打标）
- [x] 3.3 右栏接入（**onRailData 死循环纪律**：回调 useCallback＋ogForm/saveOg 走 ref＋deps 只含 chapterRef；openCastReview 只 flush+setOpen）：AiAssistPanel og tab `cap("cast-review", …)` 行（data-aiact=cast-review）；**行级 PRO 映射表只作用章纲页签**（其余五行 `disabled: !isPro, hint:"需 PRO"`，照 VolumeAssistPanel 先例，og tab aiState="ready"；**其余七页签维持 member_required 整卡锁定**——否则免费放行全卡生成行）；**AiWriterAssistant 加 subTitle 插槽**（免费副行）＋升级出口 children 块；空章禁用（hint「先写剧情再盘点」）/归档禁用；弹窗挂 ChapterWorkspace 层（NovelWorkspace 零改动）。验证：单测＋`ai-assist.spec.ts` 回归
- [x] 3.4 两出口落账（**正确性顺序**）：chars 按行去重并入→`ogFormIssues` 预检→**立即 saveChapter**→成功**同步 ogSnapRef**再关窗/回结果页（不等 3s；落账前显式清自动保存 timer 防旧闭包覆盖）；主出口先建卡→**created 标志**（保存失败重试只走名单写入，409 且 created 提示「卡已建好，这就把名字写进名单」；否则提示「已有同名卡，名单会自动挂上」）；**建卡失败（非撞名）**给重试出口＋可改走只加名单、格内改动保留；**warnings 在写入路径消费**；**落账双同步（照 handlePlotAdopt）**：setOgForm(patched)＋ogSnapRef.current 双写缺一不可，**自动保存 timer 提升为 ref 后显式清**（防旧闭包 PUT 旧表单删掉新名字）。验证：单测断言 PUT 载荷/409 回落/created 重试/建卡失败改道/ogSnapRef 同步/warnings 上屏
- [x] 3.5 建卡后 `refreshCharacterNames`（现拉取 effect deps 仅 projectId）；保存/自动保存/写入三路径 warnings 消费（自动保存 warnings 存在才打扰）。验证：单测建卡后候选含新名

## 4. 前端：名单区两态承接

- [x] 4.1 没卡标记＋行级建卡入口**两态承接**（落点）：查看态＝OgPane 出场角色 `.fro` 行由 `charLines.join` 单文本改逐名渲染（chip＋没卡标＋建卡入口，照读者获得行多子节点先例）；编辑态＝og-char-picker 追加非候选名字 chip（textarea 照旧）；**ChapterWorkspace 名单候选展开 aliases**（现只取 name，别名会被误标没卡）。验证：单测两态各断言＋别名不误标
- [x] 4.2 e2e 锚补齐：data-od-id="rail-cast"／og-cast-review／cr-write／cr-list-only／cr-redraw／cr-fresh／cr-back-review／cr-back-cards／cr-fill-manual／cr-draw／cr-draw-locked／cr-error／cr-draw-error／cr-pick-card-N／cr-opt-add·edit·defer／cr-go-edit／cr-recheck／claim-name／claim-qinbo／gap-active／gap-written／gap-deferred／done-notice（回执 aria-live）；data-od-id 透传（AiCapabilityRow 行渲染无 od-id 透传口——需在 AiWriterAssistant 行上透传或改用 data-aiact 锚）；`.ra-step[data-aiact="cast-review"]` 锚＋「免费态 ra-off 可视」断言。验证：e2e 断言点齐

## 5. 回归与门禁

- [x] 5.1 e2e 新 spec `cast-review.spec.ts`（AI 全打桩）：免费盘点→零新增一行收场；多缺人独立处理＋写入回程（回执「还有 N 个」与全清两版）；手填空格形态（不露 AI 预填）；抽卡（打桩 S/A/B，≥2=S 分布）→返回盘点结果→改三选一再抽；写入两出口各断言（含 created 重试/409 回落）；免费锁定无卡面＋降档恢复无卡面；抽卡中/失败三出口；换一批 exclude 请求体断言（组合禁令）；验证：隔离栈全绿
- [x] 5.2 后端全量 pytest（**含 test_prompt_layering 闸门：新模板单文件标记式天然过**）＋**「存量模板渲染零变化」断言**（分层红线：_generate/ai_client 不得动到存量提示词面）＋前端 vitest；`grep -rn "具名新人一律不添" client/backend/prompts/` 确认规则 2 补句就位（以 delta 钉词源为准）；钉词测试同步后绿
- [x] 5.3 门禁实跑并记录结论：`client/frontend npm run design:lint`／`npm run design:check`（像素差 <0.2%）／`tsc --noEmit`（C端）；**book.css 共享词汇改动另跑 `node scripts/design-cross.mjs`＋三域右栏截图对照**；无裸 hex/emoji/未登记字号
- [x] 5.4 走查脚本入库核对：`openspec/changes/c-character-intro/evidence/cast-review-walkthrough.cjs`（v2.5 断言集；稿面/脚本版本字样统一）跑绿；「还有 N 个」回执分支与 created 重试/409 由 e2e 5.1 承接（稿面边界注记已录文案）；todo.md「卷域章层四项」之①标记完成并注链接（②③④不动）

## 6. 名单缺人探测（每章通用，确定性——2026-09-28 用户拍板：每章都要能识别到主角）

- [x] 6.1 OgPane 名单缺人探测器（查看态＋编辑态）：有卡角色（含别名）被本章梗概/剧情条目点名但不在出场名单→就近软提示（点名者＋一键「加入名单」；主角置顶带「主角」标）；「忽略」按章会话内记忆；「加入」走 form.chars＋onPatch（3s 自动保存链）。验证：vitest（点名命中/在名单不提示/忽略不跨章/主角置顶/加入载荷）
- [x] 6.2 原型 book.html＋ADJUSTMENTS 登记（cast-miss 家族：软提示块＋chip＋忽略）。验证：原型在位、登记齐
- [x] 6.3 数据修复：真书第 1 章名单恢复 [林野, 阿蓟, 银铎]（API PUT 已执行，2026-09-28）。验证：GET outline.characters

## 7. 缺口「选已有角色」（2026-09-28 用户实测：同一人两段判缺各荐建新卡，缺复用入口）

- [x] 7.1 GapCard「加人」区加「选已有角色」入口：候选＝本书角色卡名（cardNames，不含别名），已在本章出场名单的置灰标「已在名单」；选中走 list-only 写入链（existing=true，零建卡零 AI）；回执三分支文案（建卡并写入/只加名单/已有角色卡）。验证：vitest castReviewFlow 4 条（候选清单/写入零建卡/两段复用/失败 toast 缺口仍开）
- [x] 7.2 spec delta：三选一 Requirement 加「选已有角色」bullet＋场景「两段缺同一人，第二段复用已有卡」；validate --strict 绿
