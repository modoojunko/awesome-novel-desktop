## Context

设计定稿与原型已完成：`docs/design-c/drafts/ai-novel-c端-卷纲节奏-原型.html`（真界面基线）＋`ai-novel-c端-卷纲节奏-设计说明.md`（两层节奏边界、流水线时序、AI 输入契约、注入面全表、漂移一致性）。本文件只记实现层决策。

现状关键事实：

- 卷视图 `VolumeWorkspace`（client/frontend/src/components/novel/workbench/）页签行 `.ch-tabs`（卷纲/本卷章节/角色关系/伏笔），右栏 `VolumeAssistPanel` 体检/重新规划两行。
- 卷模型 `client/backend/models/volume.py`（卷纲字段集）；卷无任何节奏概念。
- 位置机制已存在：`chapters/ai_plan.py` 的 `POS_FRAGMENTS`＋`position_tags()` 纯函数（ch1/golden3/vol_start），片段注入 `chapter_split.prompt` 的 `<<position_rules>>`；片段文件住提示词仓 `awesome-novel-prompts/prompts/pos_*.prompt`。
- 注入消费点：`chapters/ai_plan.py`（拆章素材）、`chapters/ai_plot.py`（剧情条目抽卡素材）、`write/plot_sim.py`（推演素材）、`write/chapter_writer.py`（正文素材）、`volumes/ai_plan.py`（卷体检）。

## Goals / Non-Goals

Goals：章层循环可配置、可排段、可在五个注入点被查到；零迁移；节奏缺省时全链路与现状逐字一致。

Non-Goals：卷间递进（主线/卷纲已管）；逐段非均匀定制（v2，连同伴落库）；已写章节节奏校准（v2）；拆章/正文的提示词主体重写（只加素材与片段）。

## Decisions

1. **存储：volumes 表加一列 `pacing_json`（TEXT，JSON）＋作品偏好加书级默认（套路键＋每段几章，照「章节默认字数」同款镜像与 clamp）**，不建独立表、不加章级列。内容 `{preset, steps:[{n,t}], len, ch1_extra_on, ch1_extra, planned}`；空/缺＝未配置。拍位不落库——`拍位(章号)=公式推导`（段区间＝等宽切分+末段吸收余数），加删章自动一致。理由：v1 段表恒均匀可算，落库逐段边界只会带来漂移重排问题（见设计说明「章数漂移」）；`planned` 只标记「AI 排段已采纳过」，用于「已排/未排」展示与注入开关。
2. **拍位查询单源**：后端 `volumes/pacing.py::beat_of(chapter_no) -> (seg_no, step_idx) | None`（未配置/越界返回 None）＋`segment_plan()`（段数/末段）。前端镜像 `src/lib/volumePacing.ts`（与 chapterTarget.ts 同款镜像＋parity 对拍）。六个注入点只准调这两个入口。
3. **排段 AI 动作**：新端点 `POST /api/novels/{id}/volumes/{ref}/pacing/plan`（归 ai-plan 族，标准档起）。提示词新模板 `volume_pacing_plan.prompt`（素材＝卷纲四问＋章数目标＋上一卷结尾＋节奏配置；输出＝每段强度爬坡说明，JSON）。v1 段表边界仍由公式定，AI 产出作为「排段说明」随已排状态展示于采纳预览——即 AI 排段 v1 的增值是解读与验收辅据，不改边界（与 spec 的「边界实时推导」一致）。feature key 归 `ai-plan`，tier 起点随卷纲展开同档。
4. **调一版套路／润说明**：两个新端点（`pacing/tailor`、`pacing/polish`，同族），提示词模板 `volume_pacing_tailor.prompt`（输入＝题材+子类/简介/主线全景+结局三问/世界观+人物/六预设菜单；输出＝套路选择+步+每段几章+第 1 章额外交代建议，JSON）与 `volume_pacing_polish.prompt`（只润步说明）。两者都是「出预览→前端表单承接→保存才落库」，不直接写库。六预设本体住在后端代码常量（照 theme_catalog 先例，名字即稳定键），前端镜像供预填展示。**归属（10-27 复审定稿）**：节奏不归属题材——题材只拥有「子类→套路键」映射（预填的默认值来源），预设内容为六套共享常量 SHALL NOT 复制进题材数据（防多处漂移）；配置本体归属卷（一段几章/步措辞/第 1 章额外任务是写作决策，题材给不了定值），书级一致由继承链隐式实现。设定页题材格下提供「全书默认节奏」可编辑块（套路六选一＋每段几章，预填自映射表）——**书级默认**存作品偏好（book_prefs 加字段，照「章节默认字数」镜像模式）；告知与默认设定在题材处，精调在卷。**优先级**：卷列 > 书默认 > 题材映射 > 兜底；新卷预填链＝上一卷（已配置）→ 书默认 → 映射 → 兜底（继承链的头从映射换成书默认，链其余不变）。
5. **注入实现**（全部为素材追加，零改 system/主体）：
   - 拆章（as-built）：素材行方案——⓪位置行追加拍位注记＋【拍位硬规则】块（三方向必须写到本拍、下一拍最多以征兆出现）；未做 pos_cycle_* 片段家族（素材行已满足规格 delta 的行为契约，片段家族留 v2 若需按步序差分化提示词）。
   - 剧情条目抽卡：`ai_plot.py` 素材追加拍位块；`chapter_plot_draw.prompt` 规则加「至少一条实戏落本拍」。
   - 推演：`plot_sim.py` 素材追加拍位块；`plot_sim.prompt` 加不越拍硬规则（含空纲模式）。
   - 正文：`chapter_writer.py` 位置行扩写＋章级红线追加「这一章必须写到」（走既有最高优先级通道，system 不动）；**已排卷的字数不足扩写策略行同步改向**——「不足先把本拍任务写实」优先于泛化的「对话/细节/心理扩写」（治凑字数即磨戏；未排卷该行维持原文）。
   - 卷体检：`volumes/ai_plan.py` 体检素材带拍位与步表，判据加本拍完成度；`volume_check.prompt` 判据句扩展。
   - 剧情推进徽章：`VolumeWorkspace` 卷纲查看态派生渲染（前端按镜像公式算，随排段状态显隐）。
6. **页签**：`VolumeWorkspace` 页签行插入「节奏」于卷纲后；「本卷章节」更名「章节」（纯文案，data-testid 与路由不动）。节奏面板为本组件内新子组件（查看/编辑两态、脏守卫照卷纲编辑惯例）。
7. **右栏**：`VolumeAssistPanel` 页签语境扩展——节奏页签显示三行 AI（排段/调套路/润说明），卷纲两行让位；「当前页签」文字取真实页签名（「体检面板页签跟随」既有契约的自然扩展）。
8. **兼容与降级**：`pacing_json` 空＝全链路素材与现状逐字一致（六个注入点各有「无拍位即不加」单点判断，逐点带 A/B 素材对拍测试）；提示词片段/模板经提示词包发布，`min_client` 不前逼（旧客户端读不到新片段名＝无拍位注入，天然降级）。
9. **文案**：全部作家语言（套路/段/步），过实现词汇黑名单自检；语气词 info/ok/warn/err。

## Open Questions

- 待拍板 6 项见 proposal.md 末尾（预设措辞、warn 阈值、手调、调一版套路去留、体量口径软硬、设定页提示行）——默认按建议项实施，评审可翻案。
