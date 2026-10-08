## Why

AI 续写（从光标处流式续写正文）与整章生成/选区加工的职责重叠，且续写产物绕过章末切点与章首接点的断章口径（续写从光标处自由生长，不受素材落点约束），是断章质量的旁路。产品已拍板全链退役：后端端点＋前端入口＋模型清单引用一并移除。**「续写」一词承载的导航功能（顶栏/书主页卡「续写」按钮＝回到上次写到的章继续写作，09-16 拍板口径）不在退役范围**——那是工作流入口，不是 AI 生成。

## What Changes

- **后端**：退役 `POST /write/{chapter_ref}/continue` 端点、`stream_continue` 流式函数、`continue_writing.prompt` 模板；`build_auxiliary_context` 保留（polish/expand/compress 共用），其内部 `recent_context` 的 `prose[-1500:]` 填充行（唯一消费方是续写模板）随退役顺手删除（`load_chapter` 等其余语句被角色快照依赖，保留）。
- **前端**：撤右栏 AI 面板「续写建议」卡（`cap("continue")`）、`onContinue` prop 全链（AiAssistPanel → Rail → NovelWorkspace 的 `onAiContinue`/`AiAction` continue 分支/`runAiAction` 分支）、ProsePane 的 `continueWriting` 执行链与 `startStream` 续写分支（空文档垫段为整章生成共享逻辑，保留；`textOffsetToPmPos` 随续写分支退役）、`lib/ai.ts` 的 `streamChapterContinue` 调用函数。
- **文末续写块拆除**（开发团队评审 P0 勘误：c-workbench-density 已于 2026-10-04 合入 main（c441ad38，#666），文末续写块是已提交代码而非未提交工作）：ProsePane 的 `tail-continue` 块、`planWords` prop（其唯一用途即文末块达标判定）、ChapterWorkspace 的对应传参、book.css `.tail-cw` 样式组。
- **用户可见文案**：完工检查胶囊「续写补足」与明细「可用『续写』补足」（ProsePane）改写为无续写指引（指向调低章纲目标/手动补写）；AiAssistPanel 说明行去「续写/」。
- **明确不在范围**：顶栏/书主页卡「续写」按钮、「续写恢复」滚动信号（服务导航续写，09-16 口径）、选区变换（去AI味/扩写/压缩）。
- **BREAKING**（对安装包 API 消费者）：`/api/novels/{pid}/chapters/{ref}/write/continue` 端点移除（无外部 API 消费者，桌面应用前后端同包发布）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `intro-genre-settings`：MODIFIED「模型选择的三层粒度与绑定」——模型页面化清单与调用参数表中「章写作/续写」改为「章写作」。
- `workbench`：MODIFIED×3（正文页签动作清单去「续写建议」；AI 入口唯一化枚举去「续写」；两态显式动作枚举去「续写」）；REMOVED「正文页签密度重排与文末续写」（文末续写块条款随链退役）＋ADDED「正文页签密度重排」（密度重排三条款与三场景原样承接，不含续写块）。
- `write-archive-meta-sync`：REMOVED「续写完成后刷新 DB 章元数据」（整条，`stream_continue` 随链退役；整章生成的落库刷新由既有 requirement 承载）。
- `prompt-crafting`：MODIFIED「素材包确定性组装」——辅助链清单「续写/去AI味/扩写」改为「去AI味/扩写」（`_format_style` 随保留面继续存在）。

## Impact

- 后端：`write/router.py`（/continue 端点＋import）、`write/auxiliary.py`（stream_continue＋recent_context 死赋值行）、`prompts/continue_writing.prompt`、`tests/test_write_routes_contract.py`（子路径清单去 /continue＋反向钉缺席断言）。
- 前端：`workbench/AiAssistPanel.tsx`（续写建议卡＋onContinue prop＋说明行）、`workbench/ProsePane.tsx`（continueWriting/startStream 续写分支/textOffsetToPmPos/tail-continue 块/续写补足文案/planWords prop）、`workbench/Rail.tsx`（onContinue 透传）、`NovelWorkspace.tsx`（onAiContinue/AiAction continue 分支/runAiAction 分支/planWords 传参）、`lib/ai.ts`（streamChapterContinue）、`design/book.css`（.tail-cw 样式组）、`__tests__/NovelWorkspace.test.tsx`（:602 续写建议按钮断言删除）。
- 原型与 parity 基线：`docs/design-c/prototypes/book.html`（右栏续写建议卡行）、`docs/design-c/prototypes/ADJUSTMENTS.md`（续写相关登记）、`design-parity-book.spec.ts` 免费态截图基线（右栏含此卡，撤卡必红，须重录）＋`prompt-pipeline.spec.ts:156` 注释（/write/continue 字样）。
- e2e：现行「续写」用例均为导航续写（顶栏续写回章），不在退役面；实现后全量 e2e 复跑。
- 文档：`docs/prd/creation-flow-to-be-design.md`「正文 AI 五连」口径登记过期（不阻塞实现，随归档备注）。
- 兼容性：无存量用户（产品零基线拍板），无数据迁移；`chapter_versions` 里历史续写版本快照保留不动；`operation=continue` 计量历史行原样留存。
