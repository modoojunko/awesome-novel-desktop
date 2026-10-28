## 1. 原型与设计工件（已完成的登记）

- [x] 1.1 确认原型与设计说明已入库：`docs/design-c/drafts/ai-novel-c端-卷纲节奏-原型.html`（＋.src.html、build/check 脚本、pacing-captures/）与 `ai-novel-c端-卷纲节奏-设计说明.md`；本 change 不再改 prototypes/ 基线（节奏页签属新增屏块，非既有屏 parity 面），ADJUSTMENTS.md 待实施落地后按「新增块不触基线」口径核对并登记
- [x] 1.2 文案终审：黑名单自检（无实现词汇/编辑室行话）、语气词 info/ok/warn/err、按钮动词口径（对照设计说明 §文案判例）

## 2. 数据模型与单源

- [x] 2.1 `models/volume.py` 加 `pacing_json`（TEXT）列 ＋ alembic 迁移（加列默认空，存量零迁移）；Pydantic schema（volumes/schemas.py）加节奏配置读写形状（clamp：步数 2–6、每段 1–30、文案长度上限）
- [x] 2.2 书级默认节奏：book_prefs_model 加字段（套路键＋每段几章，clamp＋前后端镜像）＋book-prefs 端点扩展；预填链工具（上一卷→书默认→映射→兜底）与单测
- [x] 2.3 新建 `volumes/pacing.py`：六套路预设常量（名称/形态/默认段长/warnLen/步表/开篇默认句）＋题材→套路映射（对齐 theme_catalog 名）＋`segment_plan()`＋`beat_of(chapter_no)` 纯函数；单测（末段吸收余数、越界 None、未配置 None、变更自动伸缩）
- [x] 2.4 前端镜像 `src/lib/volumePacing.ts`（预设展示文案＋段数/拍位公式，与后端 parity 对拍测试）

## 3. 节奏页签（前端）

- [x] 3.1 `VolumeWorkspace` 页签行插入「节奏」（卷纲后）、「本卷章节」更名「章节」；相关 e2e/单测的页签文案与序号同步
- [x] 3.2 节奏面板查看态（摘要行＋体量行＋剧情安排一行＋未排/已排 tag）与编辑态（六套路胶囊、步单行增删、每段几章、全书第 1 章额外交代滑块开关＋输入）＋保存/取消与脏守卫；vitest 覆盖两态切换、预填、继承上一卷、切换套路换步表、变更失效已排
- [x] 3.3 卷纲查看态「剧情推进（派生）」步位徽章（已排时派生显示，公式前端镜像；未排/越界不显示）＋单测
- [x] 3.4 设定页题材格下「全书默认节奏」可编辑块（套路六选一＋每段几章，预填自映射、存书级偏好、旁注「各卷可单独调整，以卷为准」）＋vitest（选中即见/改值保存/清空题材块隐藏、书默认不丢）

## 4. 右栏三 AI 动作（后端）

- [x] 4.1 `pacing/plan` 端点：素材（卷纲四问＋章数目标＋上一卷结尾＋节奏配置）→ `volume_pacing_plan.prompt` → 采纳落 `planned` 标记；卷纲未填提示不硬禁；ai-plan 族门控与记账
- [x] 4.2 `pacing/tailor` 端点：素材（题材+子类/简介/主线+结局三问/世界观+人物/六预设菜单）→ `volume_pacing_tailor.prompt` → 预览承接不落库
- [x] 4.3 `pacing/polish` 端点：只润步说明（结构字段原样回传）→ `volume_pacing_polish.prompt`
- [x] 4.4 `VolumeAssistPanel`：节奏页签语境三行（卷纲两行让位、「当前页签」真实页签名）；vitest 覆盖显隐与让位

## 5. 提示词仓（awesome-novel-prompts，与 C 端同批发）

- [x] 5.1 新增 `pos_cycle_*.prompt` 片段家族（按步序，作家语言）＋逐字对拍测试（照 pos_* 先例）
- [x] 5.2 新增 `volume_pacing_plan/tailor/polish.prompt` 三模板（JSON 契约＋测试：json_mode 输出契约句、素材占位符、钉词对拍）
- [x] 5.3 扩展素材块：`chapter_split`（⓪位置行拍位注记＋输出契约「写到本拍、下一拍最多征兆」句——主体演进由本 change 声明）、`chapter_plot_draw`（拍位块＋实戏落本拍规则）、`plot_sim`（拍位块＋不越拍硬规则＋空纲同注入）、`volume_check`（本拍完成度判据）；模板测试与钉词同步
- [x] 5.4 sync 全量＋本地全绿；提示词包发布（min_client 评估——旧客户端读不到新片段＝天然降级，不前逼）

## 6. 注入点接线（后端）

- [x] 6.1 拆章：`chapters/ai_plan.py` ⓪位置行拍位注记＋pos_cycle 片段加载（无节奏＝逐字现状）；A/B 素材对拍测试（已排/未排两态）
- [x] 6.2 剧情条目抽卡：`chapters/ai_plot.py` 拍位块注入＋A/B 对拍
- [x] 6.3 推演：`write/plot_sim.py` 拍位块注入＋不越拍规则（含空纲模式）＋A/B 对拍
- [x] 6.4 正文：`write/chapter_writer.py` 位置行扩写＋「这一章必须写到」红线行；system 恒定层逐字不变的对拍钉（已排/未配两态）
- [x] 6.5 卷体检：`volumes/ai_plan.py` 素材带拍位与步表＋「对节奏」组本拍完成度判据（未配节奏不出该追加项）

## 7. 回归

- [x] 7.1 后端：pytest 全量（新增 pacing 单测/端点测试/注入 A/B 对拍）＋ruff；重点钉「未配节奏＝现状逐字一致」的六点对拍
- [x] 7.2 前端：vitest 全量（含新镜像 parity）＋`npm run design:lint`＋`npm run design:check`（新增块不触基线，结论登记）＋tsc --noEmit
- [ ] 7.3 e2e：卷视图五页签导航、节奏两态编辑保存、拆章卡角标（已排/未排）、正文素材注入（真栈冒烟）——**遗留未写，随评审后补**；全绿后对照截图归档 change 目录
- [x] 7.4 真机抽检清单：老书（无配置）全链路不变＋新书全流程（卷纲→节奏→排段→拆章→推演→正文→体检）
