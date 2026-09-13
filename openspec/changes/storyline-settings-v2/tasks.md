# 主线设定页 v2 — 实施任务

> 顺序＝依赖序：后端契约先行（前端三行能力依赖端点），再面板重写、右栏接线、e2e 重写、全量验证。
> 验证命令：后端 pytest（client/backend，venv python）；e2e 本地 docker 栈全量（改交互必跑全量）；vitest（改 lib/api 消费方必跑——CI 不跑 vitest）。

## 1. 后端：story_arc 契约与存储

- [x] 1.1 story_arc 读写换形：`{fullstory, ending{scene,hero,tone}}`；读侧归一 `fullstory ?? premise`；写侧镜像回 premise（双写）；volumes 键 PUT 缺省时跳过不删。验证：pytest 单测——新形状读写往返、legacy 形状读、旧书保存后 fullstory==premise 镜像、volumes 键仍在、**章纲 AI 素材回归：仅填 fullstory 保存后 `client/backend/…/chapters/ai_draft.py:148-167` 的 `_arc_markdown` 仍取得到主线（premise 镜像兜底）**
- [x] 1.2 PUT 内容硬上限：**fullstory 2000 字；ending 三问各 200 字**（超出 400 中文提示）；600 字建议值不校验。验证：pytest 边界用例（2000/2001、200/201 字）
- [x] 1.3 readiness `_check_story_arc` 改判 fullstory/ending 任一非空（legacy premise 归一后判）；「确认空内容 400」语义回归。验证：pytest——fullstory-only / tone-only / legacy-premise / 全空 四态断言
- [x] 1.4 ChapterContext「故事走向」段注入 fullstory（「全书主线：…」），≤600 字预算、与简介合并裁剪（唯一裁剪点）；ending 不进写章提示词。验证：pytest 注入快照——600 内全量、700 字被裁、ending 不出现

## 2. 后端：AI 四能力端点与 ArcWizard 退役

- [x] 2.1 新增 `POST /api/novels/{novel_id}/settings/ai/arc/{draft|calibrate|check|tone}`：入参（arc 现值＋散想法可选＋简介/题材/世界/角色上下文），出参 `{value}` 信封（check 出 `{checks:[{name,status,note}]}` 四线）；require_ai_access ＋ 本书模型门 ＋ record_usage operation 注册。验证：pytest——四能力 200 形状、免费 403 member_required、no_key/missing_model 分层报错
- [x] 2.2 删除 `story/arc_wizard.py` 与 `runArcWizard` 端点；GET 响应的 `next_step`/`has_content`、PUT 响应的 `next_step`（内嵌字段，非独立路由）随向导退役从响应中移除；**摘除 `client/backend/…/novels/router.py` 的 `_arc_has_content`/`_arc_next_step` helper（readiness 改判后成死代码，grep 全仓无残留）；删 `prompts/arc_wizard_{condense,ending,split,audit}.prompt` 四孤儿模板并确认无引用**（split 语义随分卷移交写作阶段，不在本 change 重建）。验证：pytest 全量绿＋grep 无残留调用点
- [x] 2.3 主线体检 prompt：只看主线自身四线（故事连贯/开头接结局/三问对得上/和简介一个方向），简介/题材/世界/角色仅作输入；简介为空等缺输入走降级不 500。验证：pytest 降级用例

## 3. 前端：主线面板重写

- [x] 3.1 `useStoryArc` ArcData 换形 `{fullstory, ending{scene,hero,tone}}`（fetch 兼容 `fullstory ?? premise`、normTone 保留）；删 volumes/wizard/resumeStep/next_step 状态；PUT 保存句柄不动。验证：vitest——换形读写、legacy fetch 兼容
- [x] 3.2 `StoryArcForm` 重写为两块：全景大文本（建议 600 字内，**不加 maxLength**）＋ 结局三问（q-label＝field label 问题句、例句进占位符；tone 自由输入）；删除分卷块与 tone-opt；删分卷相关测试。验证：vitest 组件测试——渲染结构、无分卷区、**textarea 无 maxLength 属性且 700 字可输入并保存（600 软上限不硬拦）**
- [x] 3.3 补句柄接线：StoryArcForm 实现 `runAi(key)/clearAi()`（沿 IntroHandle 模式）、`onReceiptChange` 接 ChangeReceipt；SettingsView arc 分支从 `<ArcWizard>` 换 `<AiWriterAssistant rows={arcAiRows}>`（右栏 onClick 经 arcRef.runAi 分发，沿 runIntroAi 模式；三行与行内结果区**复用 AiSink 组件**——5 次历史/重试现成，勿新写）；ready 态头部文案去「Max 同享」→「你的 PRO 已包含 · 只加工你写的，不代写」（**共享头部：简介/题材/世界三面板连带变化，断言三面板头部无「Max 同享」**）；**BLOCK_TEXT[member_required] 与 handleAiBlocked toast 文案对齐稿内两态口径（共享组件，intro/genre/world 同步生效）**；desc 文案换「比简介更全……直接开写都行」；**删除 ArcWizard.tsx 与 src/__tests__/ArcWizard.test.tsx，grep 全仓无 ArcWizard 残留**。验证：vitest——三行渲染、采纳写回、回执撤销、AiSink 复用、无 ArcWizard 引用
- [x] 3.4 行内「AI 帮我填」（tone 第三问）接 arc/tone 端点，落输入框下方 sink；与 rail 行共享面板 aiBusyRef＋父级 aiRowBusyRef 双锁（在途互斥）；免费版 ai_state=member_required 时行内入口同样拦截。验证：vitest——互斥、**在途 loading 占位与 AI 行 runningKey 置灰**、免费拦截
- [x] 3.5 od-id 落位：`arc-fullstory / arc-ending-scene / arc-ending-hero / arc-ending-tone / arc-tone-ai-fill / arc-ai-sink-{draft,ending,check,tone} / arc-guide / ai-assist-arc`＋确认主按钮补 `data-od-id="btn-confirm"`（现缺）。验证：代码审查＋e2e 定位可用

## 4. e2e：story-arc.spec 整体重写

- [x] 4.1 重写 `story-arc.spec.ts`（旧三用例全废）：空内容确认 400 提示、确认成功 5/8＋徽标＋按钮转「保存修改」＋前进文风、三问脏态切换 confirm、AI 行落格采纳撤销、5 次历史＋重试、**AI 请求 route 500→错误态→重试成功落格**、免费拦截（tier=none 真后端 403，断言 0 请求＋升级 toast 正则断言）、**免费态手填全流程（tier=none 手写全景/三问→保存→确认成功→前进文风，复用/上提 free-writing-flow 的 writeFreeSession 进 helpers）**、行内 tone 填、主线体检落面板级 sink＋**确认按钮仍可点**、落库后回执消失（撤销不可达）、晚到结果无跨面板残留/无 stray PUT、no_key→#/config 与 missing_model→模型面板分流、**已确认态再确认＝保存修改且进度不重复计**。验证：本地 docker 栈全量 e2e 绿
- [x] 4.2 存量兼容 e2e：真实 KV 按旧形状 PUT（premise＋volumes 两行）→ 打开主线面板不炸、fullstory 显示旧 premise、保存后后端 GET 镜像一致、无分卷区；另加 route-stub legacy GET 测前端容错。验证：该用例绿
- [x] 4.3 mock 纪律核对：路由谓词正则锚定 `/api/` 前缀（防误吞 /src/api/*）、ORIGIN 5174、**check-auth 页面级桩（现 story-arc.spec 内联 page.route，重写不得丢）**、spec 顶层无 fs 副作用、teardown cleanupSessionNovels。验证：全量跑无新增 flake

## 5. 收尾验证

- [x] 5.1 后端 pytest 全量绿（含 readiness/pg_gate 无 schema 变更确认——本 change 不动表结构）
- [x] 5.2 前端 vitest 全量绿（CI 不跑 vitest，本地必跑）
- [x] 5.3 本地 docker 栈 C端 e2e 全量绿（85+ 用例无回归）
- [x] 5.4 评审稿↔实现对拍：两态文案逐字对拍（PRO/免费卡面、脚注、BLOCK 提示）、三问问题句逐字对拍（与稿 359-376 行区一致）
