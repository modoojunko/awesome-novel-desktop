# intro-genre-settings Specification

## Purpose

定义创建期前两步「① 简介 → ② 题材」的设定面板：简介六段模板引导与 AI 写作助手、题材五格与四行 AI、AI 反馈落输入框下方、免费版锁定与简介/题材字段数据契约。

## Requirements

### Requirement: 创建期前两步重排（简介 → 题材）
- 设定视图的 SETTINGS_ITEMS 前两步 SHALL 固定为 **① 简介 → ② 题材**（题材在前、简介在后的现顺序对调）。
- 第 ① 步简介确认后 SHALL 自动进入第 ② 步题材（确认即前进，可跳过后补）；每步可跳过、可回改；全页无必填、确认永远可点。**末项确认后**（O-11）SHALL 进入「设定完成」态并给「去写作」出口，不循环、不停留在末项。
- 后续（世界 / 开场主角(含金手指) / 主线）与写作期工具（伏笔 / 配角 / 风格 / AI痕迹）SHALL 不占用前两步。

#### Scenario: 简介在前、题材在后
- Given 创建期的设定视图
- When 顺序为 ① 简介 → ② 题材
- Then 先显示简介面板、确认后自动进入题材面板

#### Scenario: 前两步可跳过可回改
- Given 简介已确认、题材未填
- When 用户点回简介 tab
- Then 简介内容保留、可继续编辑，且不锁住题材

### Requirement: 设定左栏菜单的顺序与命名（用户 2026-09-10 拍板）

- 左栏设定菜单 SHALL 按此序（`SETTINGS_ITEMS` 数组即单一事实源）：**00 模型设定（工具项，恒在最前、不参与进度）→ 01 简介 → 02 题材 → 03 世界 → 04 角色 → 05 主线 → 06 文风 → 07 伏笔 → 08 禁用词句**。
- 命名 SHALL 为：工具项「模型设定」（原「AI 模型」）、「文风」（原「风格」）、「禁用词句」（原「AI痕迹控制」）；其余沿用（简介/题材/世界/角色/主线/伏笔）。
- **该顺序同时是「确认即前进」的推进顺序**（确认后切到数组下一项；末项「禁用词句」确认后不前进）。后端 `READINESS_CHECKERS` SHALL 保持同一顺序与命名口径（`/readiness` 的 missing 列表与之同序）。
- 回归：e2e 的推进断言必须随顺序更新；`confirmPanel` 助手 SHALL 顺序无关（判据＝留在本格出现「保存修改」**或**已推进到另一格），否则末项/推进目标未确认时会假失败。

#### Scenario: 菜单顺序即推进顺序
- Given 打开设定视图
- When 依次确认各面板
- Then 推进顺序为 简介 → 题材 → 世界 → 角色 → 主线 → 文风 → 伏笔 → 禁用词句
- And 确认「禁用词句」（末项）后停留在本格，不跳走

### Requirement: 简介面板（编辑框 + 六段模板 + AI 写作助手）
- 简介输入框 SHALL 接受 ≤500 字，实时显示 `x/500` 计数与状态徽标。
- 状态徽标 SHALL 走状态语言：未填＝ghost（中性）、已填＝**进行中/草稿**（warn 软底，不能说成已确认）、已确认才用 ok 绿。
- 「怎么写」SHALL 以**六段模板**呈现为可折叠文本指导（默认收起、点开展开）：主角身份 / 本来的生活 / 突发状况 / 必须面对的矛盾 / 不做的后果 / 做了的可能结局；最后一段固定「可能」结局（指方向、不剧透）。
- 六段模板每段 SHALL 带一句成书视角解释与例句（例句同书贯穿），底部应收六段公式与「别踩」三条（设定集腔 / 作者自白 / 写死结局）。

#### Scenario: 六段模板默认收起、点开展开
- Given 简介面板
- When 作家未点击「怎么写」
- Then 只见折叠行 + 六段名链，点开才见完整六段+公式+别踩

#### Scenario: 已填徽标为进行中（非已确认）
- Given 简介输入框有文字但未点确认
- When 查看状态徽标
- Then 显示进行中（warn）语义，而非已确认（ok）

### Requirement: 简介「AI 写作助手」（三能力，Pro）
- 简介右栏 SHALL 为一个「AI 写作助手」卡片：PRO 徽标并入头部（「AI 写作助手」+ 已解锁/套餐归属/只加工不代写）＋三个**并列**能力行（体检 / 补缺失 / 润色，非先后流程）＋底部来源/去向声明。
- 每行 SHALL 为：能力名称（上）+ 描述（下，从属）+ 右侧箭头，整行可点。
- 体检 SHALL 按四件事检查：① 六段模板逐项查达标/缺失；② 扫禁忌（**设定集腔 / 作者自白 / 剧透**）；③ **标题对照**（书名 ↔ 简介是否互相印证）；④ 结论。**只提醒、不拦确认**；行名与六段模板完全一致。注：禁忌第三元「剧透」与「别踩」第三元「写死结局」**用途不同（扫描规则 vs 写作引导），写死结局 ≠ 剧透，勿合并为同一枚举**。体检为诊断语义，**只分析/只提醒、不补写不改写**。
- 体检接口 SHALL 返回结构化 JSON：`{"six_segments":[{name,status(ok|missing),excerpt,note?}], "taboo":{"hits":[{rule,excerpts}]}, "title_check":{"fit":"ok|mismatch|generic","note":"…","suggestions":["…"]}, "verdict":"strong|ok|weak"}`，其中 `name` 须为六段名之一、`status` 限 `ok|missing`、`fit` 限三值。
- **标题对照语义**（`title_check`）：`ok`＝标题暗示的类型/看点与简介一致；`mismatch`＝不符（如标题像甜宠、简介是压抑复仇）；`generic`＝标题无信息（任何同类型小说都能用，如《第一章》）。`mismatch`/`generic` 时 SHALL 给 `note` 说明理由 + **≤3 条候选标题**（每条 ≤16 字，贴题材、留钩子、不剧透结局）。候选标题 SHALL 仅作参考提示，**SHALL NOT 提供「一键设为书名」入口**——书名改不改、怎么改由作家自己决定（用户拍板 2026-09-10）。**兜底**：模型未返回该字段或 `fit` 非法 → 该字段**不下发**，前端不渲染该行（**不得硬判 `ok`**，避免假绿）。
- **结构化输出策略**（跨供应商/弱模型）：体检/题材的 JSON 输出除 endpoint 后置归一化兜底外，prompt 侧 SHALL 给 **schema + 枚举 + 一个 few-shot 示例**；能用的 provider 追加 `response_format={"type":"json_object"}`（需同步扩 `AIClient.chat` 的 OpenAI 分支）。
- 补缺失 SHALL 只针对缺失段给候选；请求体 SHALL 带 `missing_segments`（前端把 introspect 的 missing 段传来），返回 `{"missing":[{name,candidate}], "act":"insert"}`；**只补缺失段、不重写作者已写段**。采纳才插入简介，可逐条采纳。**前置**：未先体检时「补缺失」行 SHALL 提示「先体检，才知道缺哪段」（或禁用），不得空跑（O-3）；六段全 ok 时 SHALL 提示「六段都齐了，无需补」（O-16）。
- 润色 SHALL 前后对照（入参 `{title, content}`，返回 `{"original","polished","act":"replace"}`），采纳才替换；保原意、只加工不代写。**对照展示形态**＝原句/润后**上下两行**（O-17）。
- **AI 助手交互状态机**（设计见 D14）：四个能力（体检/补缺失/润色/题材五行）SHALL 共用同一状态机 `idle → running → result → adopted`（异常走 `error(reason)`）；`.ai-sink` 为其唯一渲染面。**前置守卫**：补缺失未先体检时该行置灰 + 「先体检」，不空跑（O-3）；**空结果**（六段全 ok 时补缺失）显示「无需补」而非空白（O-16）；**生命周期**＝采纳后保留、切面板清空、重新请求覆盖、确认后清空（O-5）；**save 成功但 confirm 400** → 「内容未通过校验」+ 保留 dirty（O-4）。
- **失败文案矩阵**（O-13）：400 →「请求有误，请检查输入」；403 `member_required` → 升级；403 `no_key` → 去模型配置；503 `missing_model` → 去选模型；502/非法 JSON →「暂不可用，请重试」且**不拦确认**；网络异常/超时 →「网络异常，请重试」。**重试不重复计 usage**。
- 点任一能力，反馈 SHALL 落到**简介框下方**的结果区（.ai-sink，fg-soft），带操作名标签 + 采纳/重试；右栏只作按钮、不内嵌答案。AI 请求以**当前输入框的 synopsis 为源**（`content`），不读存储旧文；入参含 `title`（书名）。

#### Scenario: 标题与简介不符时给出提示与候选
- Given 书名为《我在夜晚打吸血鬼》（暗示都市奇幻），简介写成压抑宫斗
- When 执行体检
- Then 返回 `title_check.fit="mismatch"` + `note` 说明不符之处 + ≤3 条候选标题
- And 简介面板在六段行下方显示「标题对照：与简介不符」+ 理由 + 候选标题

#### Scenario: 标题无信息也提示（不得判为一致）
- Given 书名为《第一章》或《测试》，任何同类型作品都能用
- When 执行体检
- Then 返回 `title_check.fit="generic"` + 候选标题（非 `ok`）

#### Scenario: 弱模型未返回标题对照时不造假绿
- Given 模型输出缺少 `title_check` 或 `fit` 取值非法
- When 归一化体检响应
- Then 该字段不下发、前端不渲染标题对照行（**不得**补一个 `ok`）

#### Scenario: 体检六行与模板一致
- Given 简介已输入
- When 作家点「体检」
- Then 结果区列出六段逐项 达标/缺失，行名与六段模板一致，且给出禁忌扫描结论

#### Scenario: 反馈落输入框下方而非右栏
- Given 点任一能力
- Then 结果出现在简介框下方结果区，右栏不堆长答案

### Requirement: 02「主要看什么」＝作家写一句完整的话（用户 2026-09-10 改版）

- 02 的主输入 SHALL 是**一句完整的话**（`promise_note`，≤200，可编辑、带计数），**SHALL NOT** 只让作者填几个字的标签——旧版把完整句（AI 的 `promise_note`）渲染成只读的「AI 补充读者预期：…」，作者改不了，而自己能填的只有几个词的 `core_promise`，正好反过来。
- **几个词的选项 SHALL 保留为「起点」**：`常见口味` 胶囊点选后 SHALL 填入该口味的**示例句**（`GENRE_FLAVORS[].promiseNote`）+ 短标签 `core_promise` + 03/05 胶囊 + 04 指数；作者在示例句上改到像自己写的，再点确认。
- **AI 辅助 SHALL 产出同形的一句话**（即 AI 给的就是"完整的"），采纳后落主输入框，同样可改；短标签由 AI 的 `{value}` 写入 `core_promise`（不另设输入框，避免「两处都要填」）。
- 短标签 `core_promise` SHALL 仅作**注入用的「核心承诺」行与候选语义**；展示位（书卡胶囊/书内标签）走 01 题材目录，不用它。

- **AI 提示词 SHALL 知道本书题材**（用户 2026-09-10）：题材五字段的提示词 SHALL 注入 `{theme}`（`大类（子类）`）+ `{theme_desc}`（目录解读）+ `{theme_example}`（目录案例＝风格锚）。此前提示词只有书名+简介，AI 助手完全不知道题材，「读者图什么」只能写任何题材都成立的空话；**写正文注入早已带题材，AI 助手反而不带**，属能力倒挂。**简介三件套 SHALL NOT 注入题材**（用户拍板）——简介是题材判定的输入，反向依赖会成环。
- **候选池 SHALL 后端动态渲染、模板不得手抄**：`{candidate_list}`（promise）/`{forbidden_candidates}`+`{forbidden_ids}`/`{battlefield_candidates}`+`{battlefield_ids}` 由 `genres/vocab_presets.py` 生成；曾四处各存一份（模板 / 归一化表 / 后端种子 / 前端镜像），改一处必漂移。回归：模板里同一行出现 ≥2 个候选词即判「手抄」。
- **02 SHALL 直接给多个看点，由作家勾选采纳**（用户 2026-09-10 拍板）：前端点「主要看什么」这一行 SHALL 直接请求多看点（`multi_point=true`），**SHALL NOT** 另设「多给几个看点」入口——一个动作、一个结果区。`{multi_point}` 由请求体决定（缺省 `false`＝单对象，形状与旧行为逐字兼容，保留给旧调用）；`true` 时模型返回数组、**最多 3 条**侧重点不重复的看点，出参逐条做同样的长度校验并丢弃空项（全空 → 502 可重试）。
- **勾选口径 SHALL 固定**：结果以**复选框列表**呈现（勾选态由结果区自身持有——结果节点缓存在面板 state 里，勾选态放外面会「点了没反应」）；作家可**多选、单选，或一条都不勾自己写**；采纳按钮文案随勾选数变化（勾 ≥2 条时显示「采纳勾选的 N 条」），一条不勾时按钮禁用。落库规则：**单选＝`core_promise`（标签）+ `promise_note`（那句话）**；**多选＝只落 `promise_note`（各条 note 以「；」拼接，超 200 字按上限截断），`core_promise` 留空**——单一标签表达不了多个看点；多看点结果 SHALL NOT 再出现 AiSink 的「采纳 · 覆盖」（避免两个采纳入口）。
- **边界 SHALL 容错模型写岔的 tagId**：模型常少写/多写一个词（`forbidden:no-deus-machina` ↔ `forbidden:no-deus-ex-machina`）或单复数写错（`resource` ↔ `resources`）。归一化 SHALL 先精确命中，再按**词集合**近似命中（含单复数归一），**只认唯一命中**；仍查不到时，**像机器标识的值（不含中文、只由 `[a-z0-9_:-]` 组成）SHALL 丢弃，SHALL NOT 落成自定义文本**——存下来只会在界面上显示英文 slug，既不是有效候选也不是给人读的规则。展示端 SHALL 做同样的近似（旧库里已有这种被当自定义文本存下的 slug）。
- **结果区 SHALL 显示中文标签，SHALL NOT 显示 tagId**（用户 2026-09-10 反馈「绝对禁止的 AI 建议给出来的是英文」）：AI 返回 `tagId`（如 `forbidden:no-free-powerup`）是**存储契约**，展示层 SHALL 映射为词汇 label（先查接口下发的候选源、再退本地镜像）；自定义项（`text`）原样显示中文。03「绝对禁止」曾漏了这一步（05 斗什么格有映射），把英文 slug 直接甩给作者。采纳写回 SHALL 仍是 `tagId`（契约不变）。

- **迭代约束**：`{current_note}`（作者已写的那句话）非空时，提示词 SHALL 明令「基于作者已写内容迭代优化，禁止完全另起炉灶重写」——旧实现把作者那句话漏传（只传了短标签），AI 看不到作者写的半句，产出常与作者原意无关。

#### Scenario: 题材进提示词后产出分叉
- Given 同一本书、同一书名与简介、同一句作者已写内容，只有题材不同
- When 分别以「仙侠/修真（凡人流）」与「都市（商战）」生成「主要看什么」
- Then 两者产出的读者预期落在各自题材的语汇里（如「资质平平/资源积累」vs「资本围剿/抓住破绽」）

#### Scenario: 多看点各自采纳
- Given 点「多给几个看点」
- When 结果返回 2-3 条
- Then 每条并列显示且各自有「用这条」，采纳哪条就落哪条（标签与那句话同时写回）

#### Scenario: 点起点后改一句再确认
- Given 打开题材面板 02 格
- When 点「逆袭打脸」
- Then 主输入框出现一句完整的话（「读者要看到…」）+ 短标签「以弱破强的痛快」+ 03/04/05 预填
- And 作者可以直接在这句话上改，改完随面板保存

#### Scenario: 只写一句话也能确认题材
- Given 作者只在 02 写了一句「读者要看到弱者用脑子翻盘」，其余各格空着
- When 点确认完成
- Then 后端判定为已填（`promise_note` 计入核心键），不报「还未填写内容」

### Requirement: 题材面板（五格 + 四行 AI）
- 题材面板 SHALL 为五格：**① 题材目录（第一问「什么题材？」：大类必选 + 子类可选，见下条）** ② 主要看什么 ③ 绝对禁止（库标签预勾 + 取消＝放行 + 回车自定义）④ 吃苦指数滑块（1-10，浮例句）⑤ **本小说斗什么**（原名「主线战场」；预选 2，第 3 个出软提示不禁止）。
- **06 剧情轨道 SHALL 从题材契约移除（用户 2026-09-10 拍板）**：它与「主线规划」（story-arc：一句话主线 + 结局 + 分卷推进）是**同一个概念**（整本书怎么走），一处两存违反本体纪律 → 归属**主线**，题材只剩「这本题材怎么锁」的四格 + 目录。**连带**：`resolve_genre_context`/`build_genre_section` SHALL NOT 再渲染剧情轨道；**主线 SHALL 进写作注入**（`story.yaml.story_arc.premise` → 「全书主线：…」，此前只有章纲 AI 读它、写正文没带），确保退役不丢信息。DB 列 `novel_genre.track` 保留不迁移（旧值不再读写）。
- **01 格 SHALL 是题材本身（用户 2026-09-10 拍板「题材应该是第一个问题：什么题材」）**：候选源＝**题材目录**（**21 大类** × 各自子类，单一事实源 `genres/theme_catalog.py` ↔ `lib/themeCatalog.ts`，逐字对拍）——仙侠/修真、悬疑、科幻、架空古王朝、刑侦/现实犯罪…（不再用「口味胶囊」当第一问；「悬疑」为用户 2026-09-10 追加，原 JSON 把它拆在刑侦/志怪下）。大类是 01 格的**必选**项（子类可选）。
- **01 的控件形态 SHALL 为「字段 + 就地展开的两级选择」（用户 2026-09-10 反馈「第一个的 UX 不是很好，参考下 tdesign 的组件，页面尽量简洁」）**，对标 TDesign Cascader 的三条语义：① **`checkStrictly` 任意级可选**——大类可单独选（不必先选子类），再点子类细化。**浏览与选中 SHALL 分离**（用户 2026-09-10 报障「配置过的题材老是自动变成玄幻」：原实现点一下即选中，作者只想看看某大类下有什么子类，题材就被改掉、离开面板时脏数据被保存 → "自动变了"）：**点左列大类＝只浏览**（右列换成它的子类，**字段值不动**）；**选中走显式动作**——点右列「只归到大类（X）」＝只选大类，点右列某个子类＝选「大类 + 子类」；② **`filterable` 搜索**——搜索框按「名／解读／案例」过滤，命中项**拍平成「大类 / 子类」路径**行（81 个子类只按名字搜不够用）；③ **`clearable` 清空**——字段右侧 × 清空（取代早期「再点同一个大类取消」的隐式手势）。收起态 SHALL 只占一行字段（不再是一片 20+ 胶囊墙）。**换大类 SHALL 清掉不属于新大类的子类**（后端也会 400 拒收跨类子类）。键盘：搜索框 ←/→ 无、↑↓ 移动高亮、Enter 选中当前项、Esc 收起；面板外点击 SHALL 收起。
- **展开态 SHALL 就地展开而非浮层**：设定面板列自身 `overflow-y:auto`，浮层会被裁切并随滚动漂移；浮层需 portal + 滚动跟随，与本页「简洁」相悖。收起即一行，故简洁目标由「字段形态」达成，而非浮层。
- **目录每一项 SHALL 带「解读」与「案例」（用户 2026-09-10 追加）**：只给名字（如「武魂流」「本格刑侦」）作者不知道指什么。`desc`＝这一项**写的是什么**（一句话、作者视角，非营销词）；`example`＝**可对照的作品/取材**（把抽象标签锚到具体印象，叙事/影视/漫画皆可，正史类以「取材」形式给史料）。展示：**选中即见**——只选大类说大类解读，选了子类换成子类解读 + 案例（`.cap-note`，未选不占位）；每颗胶囊另带 `title` 悬停提示。**两项缺一不可**（对拍测试逐项断言非空）。
- **口味胶囊 SHALL 移到 02 格**作「常见口味」快捷填充（原名「题材口味胶囊」名不符实：它填的是 02-05，不是题材）：一次预填 02/03/04/05，各格可改；**SHALL NOT** 覆盖 01 已选的题材。
- 每格 SHALL 有编号 + 名称 + 「怎么填」提示 + 成书视角去处说明（m-use）。
- 题材右栏 SHALL 为同款「AI 写作助手」卡片：**四行**字段（对应 02-05；01 题材目录为直接选择、不走 AI、**计入**确认判据），各行名称上/描述下（含本格问题 + 输入来源）/右箭头，各答各题。**路由 field→契约字段映射**：02 主要看什么↔**promise_note（≤200，主输入＝作家写的那句话）**+core_promise（≤60，短标签：起点胶囊/AI 写入，不单独设输入框）；03 绝对禁止↔forbidden_list；04 吃苦指数↔cost_ratio；05 本小说斗什么↔battlefield。**已退役的 track SHALL 被 AI 端点拒绝（400）**。
- 点某行，反馈 SHALL 落到**左侧对应字段输入框正下方**的结果区（.ai-sink），采纳才写回对应控件；AI 建议按字段返回**强类型出参**（cost_ratio 为 1-10 数值、forbidden_list 为 `[{tagId|text}]`、battlefield 为数组、core_promise 为 `{value:enum|custom, note:读者预期句}`、主要看什么为文本）。
- 题材的枚举/标签类字段（core_promise、forbidden_list、battlefield）SHALL 有**候选来源**：由 9. 共享候选源给出候选清单（core_promise 枚举值、forbidden_list tagId 目录、battlefield 候选），模型从中选或走 custom，前端「采纳才写回并映射 tagId」。
- **写回语义**（设计见 D16）：单值文本/数值**覆盖**（按钮「采纳 · 覆盖」）；列表（forbidden_list/battlefield）**覆盖整个列表**（不追加——O-6）；AI 返回无法映射 tagId 的文本落为 `custom`（不丢弃）；**01 取消选择不回滚**已填各格（O-15）。
- 题材定义 SHALL 收口为：题材 = 读者预期 + 作者轨道 + 核心冲突的类型锁（提示帮助中的措辞）。
- **纯新契约连带**（写作引擎配置去留）：推翻 genre_id 后，老 GenreSettingForm 落盘的 `genre_id + config_overrides(fulfillment_types/chapter_types/pacing_rules/fatigue_words) + selected_arc_id + prompt_injection_enabled + taboos` 这批写作引擎题材配置必须有明确去留——语义相近的迁移为新契约字段（fulfillment_types→core_promise、taboos→forbidden_list、typicalArc/storyArcTemplates→track），纯写作引擎/随 GenrePicker 退役的显式移除并评估，**不得静默丢弃**影响写作引擎 AI 口味/节奏/注入的配置。

#### Scenario: 三种口味快捷填充（02 格）
- Given 题材面板，已选 01 题材「仙侠/修真」
- When 点 02 格的「逆袭打脸」
- Then 主要看什么/绝对禁止/吃苦指数/本小说斗什么 预填推荐值，均可改可清
- And 01 已选的题材不被覆盖

#### Scenario: 剧情轨道退役后主线承接注入
- Given 作者在「主线规划」里写了一句话主线
- When 生成正文
- Then 写作上下文含「全书主线：<那句话>」（剧情轨道退役前由 06 格承担的这条信息，改由主线承接）
- And 题材面板不再渲染 06 格，AI 端点对 `track` 返回 400

#### Scenario: 题材目录两级选择
- Given 打开题材面板
- When 点大类「仙侠/修真」
- Then 出现其子类行（古典仙侠/凡人流/仙魔大战/种田修仙），可单选
- And 换点「科幻」时，若原先选了「凡人流」，该子类被清掉（不属于科幻）

#### Scenario: 搜索拍平成路径
- Given 打开 01 题材选择器并在搜索框输入「凡人」
- When 查看结果
- Then 命中项以「仙侠/修真 / 凡人流」的路径形式列出（大类＋子类同现），点选即落库并收起

#### Scenario: 每项都有解读与案例
- Given 打开题材面板（未选题材）
- When 点大类「仙侠/修真」
- Then 下方给出该大类的解读（「以修行阶次与道法体系为骨架…」）
- When 再点子类「凡人流」
- Then 解读换成子类的（「主角资质平平，靠算计…」）并附案例「《凡人修仙传》」
- And 每颗胶囊悬停也都给出对应解读与案例

#### Scenario: 未知题材被拒
- Given 客户端提交一个不在目录内的大类名
- When 保存题材
- Then 后端 400 拒绝（「未知的题材」），不落库

#### Scenario: 题材 AI 反馈落对应字段下方
- Given 题材面板
- When 点「主要看什么」的 AI 行
- Then 建议出现在左侧「主要看什么」输入框正下方结果区，采纳写回该文本框

### Requirement: 免费版（无套餐）AI 可见 + 锁定
- 无套餐用户 SHALL 仍可看到「AI 写作助手」卡片，但其为**可见 + 锁定**：整体降透明、PRO 徽标转灰、各能力行降透明且不可点（cursor:not-allowed），每行名称/描述仍可见。
- 点击锁定行 SHALL 给统一升级提示（「这是会员功能，升级 PRO 后解锁——免费版写作能力完整」），SHALL NOT 各自弹窗。
- 免费版写作能力 SHALL 完整（人工路径零差异）。

#### Scenario: 免费版 AI 卡片锁定
- Given 无套餐用户进入简介/题材设定
- When 查看 AI 写作助手卡片
- Then 三个/五行能力可见但整体降透明、点击给升级提示、不生成结果

### Requirement: 本书模型设定（AI 前置）
- **模型配置＝人工路径能力，不锁会员**：免费版 SHALL 也能看到「本书模型」步、也能配置（选 API 配置 + 模型）——免费版与 PRO/MAX 的差别**只在右侧 AI 助手**（免费版全灰、升级引导）。
- 用该书的任何 AI 能力（简介/题材助手、章写作等）前，SHALL 先在本书选定 API 配置 + 模型（复用 `ModelSettingForm`/`useModelStatus`，落 `project.ai_config_id` + `project.ai_model`）；**就绪判据见「AI 就绪状态的单一事实源」（四条件）**。配好的模型在升级 PRO 后 SHALL 直接可用（不必重配）。
- 模型选择控件 SHALL 为**按 API 配置分组的卡片列表**（组头＝配置名 + 供应商 + 连接状态徽标；组内模型行可点、单选、选中态 accent + 勾），支持**多供应商 × 多模型**；SHALL NOT 用原生 `<select>`/optgroup（撑不住多供应商×多模型、且不符全页设计语言）。**单选语义**：容器 `role="radiogroup"` + 行 `role="radio"`/`aria-checked`（对齐仓库既有 `StoryArcForm` 的 role/aria 语义；注意它无键盘导航先例、且是「再点取消」toggle 语义——模型单选不可照抄）；**键盘导航须新增**（roving tabindex + 方向键 + Home/End）。**选择与生效分离**：点模型行只标亮选中态（不落库），点「设为本书模型」才 `selectModel` 落库——防误触（该书全书 AI 走这个模型）；未选模型时确认键禁用；确认后按钮回禁用、再改再启用。**空态**（有 Key 但未拉到模型）SHALL 给「去「模型配置」补模型」引导，不空白。
- **免费版「已配好但 AI 仍灰」**：模型窗对已配置的免费用户 SHALL 提示「模型已配好 · 升级 PRO 后本书 AI 即可用」，不得说「本书 AI 就绪」。
- **API Key 的增删改同样不锁会员**（现状 `api_configs` 路由零门控）；SHALL NOT 给模型配置/Key 管理加会员门控（后续误加会关掉免费版的人工路径能力）。
- 模型步 SHALL NOT 进入 `SETTINGS_ITEMS`（不参与 readiness/设定完成度判定、不占「确认即前进」序列），它是 AI 前置引导步（会员用 AI 的第①步；免费版可先配好）。
- 未选本书模型的（会员），该书 AI 能力 SHALL 不可用：后端以独立 dependency `require_novel_model(novel_id, user, db)` 校验（与 `require_ai_access` 并列挂载，会员在前），未就绪返回 **503 `detail={reason:"missing_model", message:"先在本书选择模型"}`**（前置未满足、**不可当瞬时故障重试**）。
- **三种前置 SHALL 可分流**（前端按 `detail.reason` 分派文案与跳转，不得一色 toast；分派顺序 member_required → no_key → missing_model）：
  | 场景 | 状态码 | detail.reason | 文案 | 跳转 |
  |---|---|---|---|---|
  | 非会员（免费/过期） | 403 | `member_required` | 升级 PRO / 试用 | 升级入口 |
  | 会员但无可用 Key（含 invalid※） | **503**（保持现有码，前端 503 提示链路不可改 403） | `no_key` | 先去「模型配置」添加 API Key | 模型配置 |
  | 会员 + 有 Key + 本书未选模型 | 503 | `missing_model` | 先在本书选择模型 | 本书模型设定 |

  ※ `invalid` **由判定层下发**（配置已删 / `model ∉ config.models` / R8 删除残留），非前端派生。**结构化 detail 全链路**：`api.ts` 503 分支须按 `detail.reason` 分流（`no_key`/`missing_model` 不进 infra 全局提示）并透传 `e.reason`；`ai.ts` 两处 fetch 统一取 `detail.message`（否则对象 detail 变 `[object Object]`）。
- C端 AI 端点（简介/题材/章写作等）SHALL 走 `get_ai_client_for_novel(novel_id)`（读本书模型；`chat` 经 `resolve()` 落到本书模型），不复用全局 `get_ai_client()`（其不感知本书模型）；**全仓库调用点逐一替换（实测 14 处：替换 12 + 豁免 2）**，含章纲起草/提示词润色/归档摘要；**建书预填 `ai_prefill` 豁免**（早于选模型，降级为无 AI 或用户默认模型）。**双模型源权威链**：`project.ai_model` 为唯一权威，`writing_model` 仅允许 `haiku/sonnet` 别名（经 `resolve()` 映射），显式模型名一律忽略。**`polish_text`/`expand_text`/`archive_chapter` 须补 `novel_id` 参数**（现签名拿不到）。构造失败（配置已删/解密失败）须优雅返回，不裸 500。**写作页兜底另立 change**（本 change 只保证设置视图 AI 行的文案与跳转）。
- 前端 AI 行点击 SHALL 走统一门控函数（优先级：非会员→升级 / 本书模型未就绪→跳模型设定 / 无可用 Key→跳模型配置 / 就绪→调用）；**门控只作用于 AI 助手行，不拦模型配置本身**（免费版可选模型）。就绪判据＝**后端 `ai_state === "ready"`**（前端不推导）。

#### Scenario: 免费版可看可配模型、AI 助手全灰
- Given 免费版用户进入设定
- When 查看「本书模型」步与右侧 AI 助手
- Then 模型步可见、可选模型（配好保留），而右侧 AI 助手整卡灰、点击给升级提示

#### Scenario: 会员未选模型则 AI 不可用
- Given PRO/MAX 本书未设模型（ai_config_id/ai_model 为空）
- When 作者点简介「AI 体检」
- Then 不生成结果，提示「先在本书选择模型」并跳本书模型设定

#### Scenario: 已选本书模型 AI 可用
- Given PRO/MAX 本书已选 API 配置 + 模型
- When 作者点简介「AI 体检」
- Then 用本书模型生成体检结果

#### Scenario: 无可用 Key 与未选模型分流
- Given 会员但未配任何 API Key
- When 作者点简介「AI 体检」
- Then 提示「先去「模型配置」添加 API Key」（reason=no_key），而非「先在本书选择模型」

### Requirement: AI 就绪状态的单一事实源
- 「本书 AI 是否就绪」SHALL 由**后端一次判定、前端只消费**，SHALL NOT 由前端用本地配置列表自行推导（消除前后端判据漂移）。
- `GET /novels/{id}/ai-model` SHALL 扩展返回 `{ api_config_id, model, config_name, ai_state, effective_model, reason?, message? }`：
  - `ai_state ∈ {ready, member_required, no_key, missing_model, invalid}`（**与 `detail.reason` 同枚举**）——**覆盖「AI 为什么不可用」的全部原因**，前端门控只读这一个字段、一次分派（不再 `useFeature` + `ai_state` 两处判）；判定优先级 `member_required > invalid > no_key > missing_model > ready`。`member_required` 只拦「调用 AI」，**不拦模型配置本身**。
  - `ready` 判据 SHALL 为：`ai_config_id` 与 `ai_model` 均非空 **且 本书绑定的配置存在** **且 该配置有可用 Key** **且 `ai_model ∈ json.loads(config.models)`**（与绑定校验共用同一谓词——`refresh-models` 后旧模型被移除不得再报 ready）。
  - `no_key` 粒度 SHALL 为**本书绑定配置级**（非「用户任意配置有 Key」）。
  - `effective_model` SHALL 为按权威链算出的实际生效模型（`project.ai_model` 唯一权威），前端只显示、不推导。
- 前端 `useModelStatus` SHALL 删除本地四态推导，直接消费 `ai_state`/`effective_model`；AI 行门控按 `ai_state` 分派；错误兜底的 `detail.reason` SHALL 与 `ai_state` **共用同一枚举**（`no_key`/`missing_model`/`invalid`）。

#### Scenario: 前后端判据不再漂移
- Given 某书 `ai_config_id` 有值但 `ai_model` 为空
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="missing_model"`，前端据此拦在「先选模型」，不会放行调用（不再出现「前端放行、后端 503」）

#### Scenario: 配置已删的 invalid 由后端判定
- Given 某书绑定的 API 配置已被删除
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="invalid"`（不再是仅前端派生态）

#### Scenario: 模型被刷新移除后不再报就绪
- Given 本书绑定模型 x，其后配置的模型列表刷新且不再含 x
- When 查看该书 AI 就绪状态
- Then `ai_state` 不再为 `ready`（`model ∈ config.models` 谓词生效）

### Requirement: 后端模型调用分层
- C端后端模型调用 SHALL 分层且边界可验证：**配置层**（`api_configs/`，存配置/测连接/记用量）→ **解析层**（`effective_model`，`project.ai_model` 唯一权威）→ **判定层**（`compute_ai_state`，单一事实源）→ **客户端层**（`ai_client.py`，构造连接、调用、按 `api_format` 落地 `json_mode`）→ **门控层**（`require_ai_access` + `require_novel_model`，判据复用判定层）→ **业务层**（`write/`/`settings/`/`chapters/`/`prompt/`/`archive/`/`story/`/`novels/`）→ **prompt 层**（模型无关模板）→ **计量层**（记实际模型 id）。
- 边界 SHALL 分「可 grep 门禁」与「review 清单」：
  - **可 grep**：① 业务层禁裸 `get_ai_client()`——`grep -rnE '\bget_ai_client\(' client/backend --include='*.py' | grep -vE 'ai_client\.py|/tests/|ai_prefill\.py|novels/router\.py|__pycache__|\.mimosa' | grep -vE '^\S+:[0-9]+:\s*#'` 须为空（豁免：`ai_client.py` 定义、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta）；② `record_usage` 记实际模型 id（`grep -rn 'model="haiku"'` + 各调用点核对）；③ 门控违规近似 `grep -rnE 'check_permission\(|is_member' client/backend/{write,settings,chapters,prompt,archive,story,novels}` 须为空。
  - **review 清单**（不可 grep）：① 业务层是否直读 `writing_model` 决定模型；② 门控是否只在 dependency 且判据复用判定层；③ 就绪状态是否只在判定层。
- 调用点 SHALL 全仓库替换（实测 14 处）：`write/router.py:62,179`、`write/auxiliary.py:157,217,252`、`settings/ai_router.py:50`、`chapters/ai_draft.py:259`、`prompt/router.py:46`、`archive/service.py:46`、`story/arc_wizard.py:61`、`story/character_agent.py:250`、`story/engine.py:201`；豁免 `ai_prefill.py:26`、`novels/router.py:154`（建书期，无 project 上下文）。
- **建书期降级链显式化**：有书 SHALL 一律用 `effective_model`；**无书路径仅限 `ai_prefill`/`suggest_meta`**（建书期），走**显式**降级链「用户首个 active 配置的 `models[0]`」（文档化规则、非 `models_list[0]` 隐式），并标注「建书期降级模型」；**业务层其余路径 SHALL NOT 使用 `get_ai_client_for_user`**（只准 `get_ai_client_for_novel`）。**「建书期」判定规则**（O-19）：以**调用点是否持有 novel_id/novel 对象**为准（无 project 上下文者＝建书期），不依赖 phase 字段；`suggest_meta` 与 `ai_prefill` 同列豁免。

#### Scenario: 业务层不得绕过客户端层
- Given 任一 C端 AI 端点
- When 静态检查其客户端获取方式
- Then 只出现 `get_ai_client_for_novel(novel_id)`，无裸 `get_ai_client()`（`ai_prefill.py` 除外）

#### Scenario: 模型权威链不可穿透
- Given `writing-style.yaml` 的 `writing_model` 写了具体模型名
- When 该书的 AI 调用取模型
- Then 仍以 `project.ai_model`（经解析层 `effective_model`）为准，字面覆盖被忽略

### Requirement: 模型选择的三层粒度与绑定
- **粒度**：供应商/API 配置 SHALL 为 **C端用户级**（一次配置、所有书共用同一批供应商）；模型 SHALL 为 **书级**（一本书一个，全书所有 AI 助手共用同一 `effective_model`——简介三能力、题材五行、章写作/续写、章纲起草、提示词润色、归档摘要）；提示词/能力 SHALL 为 **页面级**（每助手一套模板，模板**模型无关**、不写模型名）。
- **绑定**：模型与其供应商 SHALL 绑定——`project.ai_config_id` 与 `project.ai_model` 须来自**同一配置**；后端 `set_project_model`（函数名以现状为准）SHALL 校验 `model ∈ json.loads(config.models)`（处理 JSON 文本/`None`/空串/非法 JSON），**空列表拒绝**、**部分 null 拒绝**（不成对即拒，除非显式 clear）；失败返 **400**（Pydantic 缺字段才 422）。**跨配置混搭在 UI 上不可达**（每行携带所属配置）；**组内换模型＝同配置换 model，允许**。前端确认键遇 400 SHALL **保留 draft 选中态 + 行内报错**（不清空、不禁用）。
- **存量错配与失效边界**（流程审查 O-7/O-8）：`ai_model` 存在但**不在**该配置 `models` 列表（存量/手工改库）时，`ai_state` SHALL NOT 为 `ready`（**已定：并入 `invalid`**，不派生第 6 个枚举值），前端按「重选模型」引导——D12 校验只挡写入、不挡存量读取，须在判定层兜住。**配置被删且用户无其他可用配置**时 SHALL NOT 死路：模型窗须给「去「模型配置」新建配置」入口（而非仅隐藏选择区）。
- **清除本书模型**（O-12）：`(None, None)` 的显式 clear SHALL 被支持（API 层保留现有 `change_type="clear"` 语义）；**UI 不提供「清除」入口**（仅 API 保留），且**不得**让 `(config_id, None)`/`(None, model)` 这种**不成对**状态落库。
- 换模型 SHALL 对全书 AI 助手同时生效（一处改、全书生效）。
- **页面级调用参数（本清单即参数表，design D12 引用它）** SHALL 与 prompt 一并页面化：JSON 判定类（`introspect`/`fill`/`settings_genre_{field}`）`temperature ≤ 0.3`、`max_tokens` 足量（≥2048，防 introspect 六段+禁忌+verdict 被截断）；长文生成类（章写作/续写/章纲）`0.7–1.0`、`max_tokens 4000`。`AIClient.chat` SHALL 支持透传 `temperature`。
- **`json_mode` 分层归属**：业务层 SHALL 只传语义参数 `json_mode: bool`；SHALL NOT 直接传 provider 专有参数（`response_format`）——由客户端层按 `api_format` 决定是否落地（Anthropic 分支忽略，否则 400），不支持者靠 prompt + 归一化兜底。
- **模型能力门槛**：本书模型 SHALL 支持 system 消息与 ≥8k 上下文；不支持 JSON mode 的模型由归一化兜底并给**非阻断**提示。

#### Scenario: 模型与供应商绑定、不可混搭
- Given 用户选了配置 A 的模型 x
- When 保存本书模型
- Then 存为 `(A, x)`；若传 `(A, y)` 而 y 不属于 A 的模型列表，则拒绝（400/422）

#### Scenario: 全书 AI 共用同一模型
- Given 本书选了模型 x
- When 分别调简介体检 / 题材五行 / 章写作
- Then 三者都走 x（`effective_model` 全书唯一）

- **幂等性**：同值重复写 SHALL 幂等——`PUT /novels/{id}/ai-model` 重复提交同 `(config_id, model)` → 均 200、状态不变、**审计不重复写**；`PUT /settings/story`/`PUT /settings/genre` 重复提交同 payload → 幂等；`PUT /settings/status/{type}` 重复 confirm → 幂等；**AI 重试/换候选不重复计 usage**。
- **边界与等价类**：`synopsis` 界 **500**（0/1/499/500/501，**501 尾部截断**——与 D16「500 字截断」一致）；`cost_ratio` 界 **[1,10]**（0/11 拒）；模型列表 0/1/多（0 → 任意 model 拒）；空串/纯空白/`None` SHALL 视为「未填」（三者等价，不得只判 `None`）。

- **存储（D19 关系化，取代 D17 的 KV 方案）**：题材 SHALL 落 `novel_genre` + 关联表（4 张表，见下「题材 SHALL 存关系表」条）；`project_settings('genre')` 行 SHALL 废弃（不再读写）；**无迁移**（无 C 端用户，存量库指纹不匹配→留档重建）。**写作注入 SHALL 同批重写**：`resolve_genre_context` 须改读五字段，否则 `build_genre_section` 恒空且**无报错**（静默降级，正文质量悄悄变差）；**且 SHALL 带上 01 题材目录**（`题材：大题（子类）` 一行，同读 `story.yaml`）——01 是「定了就不跑偏」的类型锁，只注入 02-06 会让模型不知道书是什么题材。**`genres` 表 SHALL NOT 被本 change 修改**（仅停用 `genre_id` 引用）。候选源 SHALL 由 `GET /api/genres/candidates` 下发（前后端镜像需 parity）。**`settings/ai-model.yaml` 为确认标记行，SHALL NOT 写入 `ai_state`**。**R9**：`writing-style.yaml` 的 `genre_profile` SHALL 停用或明确仅作展示名，不得与五字段并存为两个题材源。**禁止新增未路由的 storage 路径**（会静默落盘、破坏「数据全在 DB」）。
- **R8 删除残留**：删 ApiConfig 后 `ai_config_id` 被置空而 `ai_model` 保留 → `ai_state` SHALL 判 `invalid`（非 `missing_model`/ready）。

### Requirement: 简介/题材字段数据契约
- 简介 SHALL 存储 `{ synopsis: string, ≤500 }`（`PUT /settings/story`）。
- **题材目录（01 格）SHALL 落 `story.yaml`**（用户 2026-09-10 拍板）：大类名存**既有 `genre` 键**（书卡胶囊/书内标签的展示链一直读它）、子类名存新键 `sub_genre`；`GET/PUT /novels/{id}/settings/genre` 的对外契约 SHALL 含 `theme`/`sub_genre` 两字段，**存储位置对前端透明**（面板一次取全、一次保存）。**理由**：题材目录是与简介同族的单值书级元数据（同文件、已有 `genre` 键），不是多值关系；**另立关系表意味着改 schema → 触发 C端 启动期指纹留档（用户库被改名重建，实打实的数据丢失）**，而简介真源本来就在 `story.yaml`。**键存在才写**：PUT 未带 `theme`/`sub_genre` 键时 SHALL NOT 改动既有值（老调用方只 PUT 五字段不得清空题材）。
- **题材目录（封闭目录）SHALL 以中文名为存储值**：不另造 slug-id（名字即稳定键，免 id↔名两处漂移）；写入 SHALL 按目录校验，未知大类/跨类子类 → 400（「未知的题材」/「没有这个子类」）。
- 题材 SHALL 存**关系表**（方案 A，D19）：`novel_genre`（`novel_id` 主键、`core_promise VARCHAR(60)`、`promise_note VARCHAR(200)`、`cost_ratio INTEGER CHECK 1–10`、`track VARCHAR(300)`（**列保留、契约已移除**：2026-09-10 起不再读写，见「题材面板」需求））+ `novel_genre_forbidden` / `novel_genre_battlefield`（关联表，`vocab_id` FK→`genre_vocab` 或 `custom_text`，CHECK 恰一；`UNIQUE(novel_id, vocab_id)`）。**候选源 SHALL 为 `genre_vocab` 表**（稳定 slug 主键、`kind`/`label`/`sort`/`is_preset`），**tagId SHALL 为稳定 slug**（如 `forbidden:no-deus-ex-machina`），**SHALL NOT 用 `preset:{id}:{index}` 这类随顺序漂移的编号**。**空值统一**：`null`/`""`/纯空白/无关联行 等价视为未填。`project_settings('genre')` 行 SHALL 废弃。
- **实体命名统一（D20）**：DB 表 `projects` SHALL 改名 `novels`、列 `project_id` SHALL 改名 `novel_id`（含 `chapters`/`volumes`/`token_log`/`project_model_audit_log` + 新表 FK）；后端 URI `/api/v1/projects/*` SHALL 改 `/api/v1/novels/*`（无外部消费者，不留别名）；前端 `/projects/...` 残留同批改。**理由**：一物三名已收敛两处（类名 `Novel`、路由 `/novels`），表名是唯一残留；Change C D1 原判「不动」的前提（有已分发数据）已因「无 C 端用户」失效。
- 题材确认判据 SHALL 由「genre_id 非空」改为「**已选题材目录大类 或 新契约核心键非空**」（`core_promise`/`promise_note`/`forbidden_list`/`cost_ratio`/`battlefield` 至少一非空；`readiness._check_genre` 与 `genre_is_filled` 同步改）——01 格问的就是「什么题材」，只选了题材也算题材已定；**02 只写了那句話（promise_note）也算已填**（用户 2026-09-10 改版：选项只是几个词，作家写一句更好）。
- **五格↔字段↔契约映射** SHALL 固定：01 题材目录↔`theme`+`sub_genre`(story.yaml)；02 主要看什么↔**promise_note（≤200，主输入＝作家写的那句话）**+core_promise（≤60，短标签：起点胶囊/AI 写入，不单独设输入框）；03 绝对禁止↔forbidden_list；04 吃苦指数↔cost_ratio；05 本小说斗什么↔battlefield。（06 剧情轨道已退役→主线规划）
- **候选源** SHALL 提供 core_promise 枚举值、forbidden_list 的 tagId 目录、battlefield 候选清单（新建共享候选源，不复用 presets 现成键），供题材 AI 从中选或走 custom、前端「采纳写回并映射 tagId」。
- AI 辅助的字段说明、**六段名与禁忌三元** SHALL 注册进**共享常量模块**（prompt 模板与前端渲染共用）；注：`fieldGuide`/`settings-ai-qa` **本仓库不存在**，属待建——本 change 以共享常量模块落地，不依赖未建系统。
- 简介/题材 AI 能力 SHALL 由 **C端后端** `settings/ai_router.py` 承载：扩展（`FIELD_GENERATABLE` 加 `genre`、新增 `settings/ai/intro/{action}` 子路由且**注册在 `/ai/{stype}/{field}` 之前**、`settings_intro_{action}`/`settings_genre_{field}` prompt 模板）、挂 `require_ai_access`、`record_usage` 按 `settings_{stype}_{action|field}` 细分——非 S端、不引入独立服务。

#### Scenario: 题材 payload 键控
- Given 作者选了题材大类「仙侠/修真」+ 子类「凡人流」、禁项、吃苦 8、战场 2 个
- When 保存
- Then `story.yaml` 落 `genre: 仙侠/修真` + `sub_genre: 凡人流`，关系表落 core_promise/forbidden_list/cost_ratio:8/battlefield 两个值，空字段省略；无 genre_id

#### Scenario: 题材确认基于新契约
- Given 题材已填 core_promise（未填 genre_id）
- When 查看设定状态
- Then 题材判定为已确认（判据为已选题材目录或新契约核心键非空，而非 genre_id）

### Requirement: 题材的对外展示（书卡胶囊与书内标签）

- 书本上的题材展示位（书架卡片胶囊、书内标签）**SHALL 取值来自题材**（用户 2026-09-10 拍板「书的类型胶囊，取值从题材获取」），**SHALL NOT** 依赖已废弃的历史来源：建书弹窗的「类型」下拉与题材面板的 `genre_id` 都已不再写入，旧展示链（`story.yaml.genre` 的旧语义 / `project_settings('genre')` KV）对本 change 之后的书恒为空。
- 展示名 SHALL 取**题材目录的「大类」**（用户 2026-09-10 拍板「胶囊就显示大类」）：**子类 SHALL NOT 进展示位**——卡片顶栏窄，大类已足够定位一本书；子类在题材面板（字段显示 `大类 / 子类`）与写正文注入里仍是完整信息。由后端在 `GET /novels`（`genre` 字段）与 `GET /novels/{id}`（`genre_label` 字段，另下发 `theme`/`sub_genre`）**单源下发**；两端 SHALL NOT 各自拼装。
- 题材目录缺失时 SHALL 依次回退：老书核心承诺 → 老书 `story.yaml.genre`(旧值) → KV 题材名。
- **占位**：题材未设定（题材目录为空、且无历史来源可回退）时 SHALL 显示「**待定题材**」（共享常量 `GENRE_PENDING_LABEL`，前端两侧同源），**SHALL NOT** 空缺该展示位——空位会让作者以为界面漏了东西。
- 展示名可能长于展示位 → 展示位 SHALL 单行截断，SHALL NOT 撑破卡片顶栏。

#### Scenario: 胶囊只显示大类
- Given 作者在题材面板选了「仙侠/修真」+「凡人流」
- When 回到书架
- Then 该书卡片的题材胶囊显示「仙侠/修真」（不带子类、不带分隔符）
- And 打开这本书，书内题材标签同样只显示「仙侠/修真」

#### Scenario: 只选大类也能显示
- Given 作者只选了题材大类「悬疑」、未选子类
- When 查看书架卡片或打开这本书
- Then 题材展示位显示「悬疑」

#### Scenario: 题材未设定时占位
- Given 一本刚创建、题材未选的书
- When 查看书架卡片或打开这本书
- Then 题材展示位显示「待定题材」（不是空缺、也不是「其他」）

#### Scenario: 老书题材展示不回归为空
- Given 一本建书时写入过旧 `story.yaml.genre`（如「科幻」）的老书，且题材目录与关系表均无数据
- When 查看书架卡片或打开这本书
- Then 题材展示位仍显示「科幻」

### Requirement: 改动回执 + 单步撤销（模型/简介/题材三面板，用户 2026-09-10 拍板）

设定是 AI 写作的输入，改错了不会当场报错，只让后面每一章越写越差；要治的是「改了不知道 + 改错退不回」，不是「控件能不能改」。三面板 SHALL 按**改动来源**分级，SHALL NOT 引入查看/编辑模式（面板永远只有一个主按钮 + 最多一条回执）：

- **一键覆盖类**（口味胶囊一次改 5 格、禁项/战场勾选、01 题材选中或清空、04 滑块松手、AI 建议采纳、模型「设为本书模型」）→ SHALL 在面板脚部留一条**作者视角的回执**（如「已把吃苦指数从 8 调到 6」「已按「逆袭打脸」覆盖：…」）+ **一步撤销**（撤销 = 回退该次改动并清掉回执）。
- **作者自己敲的字** → SHALL NOT 进脚部回执（会随每次键入刷屏），走字段下方轻提示「已修改 · 恢复到打开时的原文」，且 SHALL 在**失焦后**才出现。
- 回执 SHALL 只保留最近一条（后一次改动覆盖前一条），切面板 SHALL 清空回执。
- 回执 SHALL 单行展示、超长**截断**并把全文挂 `title`；面板脚部 SHALL NOT 折行——折出的第二行会落到窗口状态条（`.statusbar`，fixed 26px）之下，主按钮被盖住点不到；长回执 SHALL NOT 把中栏撑宽（`1fr` 轨道栅格项须 `min-width: 0`），否则右栏 AI 被挤出屏幕且**点击会在 mousedown/mouseup 之间因重排而丢失**（2026-09-10 实测）。

#### Scenario: 一键覆盖类改动可回退
- Given 作者在题材面板点了口味起点胶囊（一次改动 02/03/04/05 四个字段）
- When 看面板脚部
- Then 出现一条回执（说明覆盖了哪些格、共几项）与「撤销」
- And 点「撤销」后四个字段回到改动前的值，回执消失

#### Scenario: 滑块的撤销回到拖动前
- Given 吃苦指数从 8 拖到 6
- When 点脚部回执的「撤销」
- Then 吃苦指数回到 8，回执消失

#### Scenario: 自己敲的字走字段下提示
- Given 作者在 02 那句话上直接改字
- When 输入框失焦
- Then 框下出现「已修改 · 恢复到打开时的原文」，点它恢复为打开面板时的原文
- And 脚部回执不因每次键入而刷新

#### Scenario: 切面板清回执
- Given 题材面板脚部有一条回执
- When 切到「世界」再切回「题材」
- Then 脚部不再显示那条回执

#### Scenario: 长回执不折行、不撑宽中栏
- Given 脚部回执文本长于面板宽度（如口味胶囊的回执）
- When 在设定面板查看脚部
- Then 回执单行截断（`title` 悬停可读全文），脚部仍为一行，主按钮可滚动到且可点击
- And 中栏宽度仍等于其栅格份额，右栏 AI 未被挤出视口
