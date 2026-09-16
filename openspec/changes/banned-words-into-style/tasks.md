## 1. 前置与原型

- [x] 1.1 归档 style-settings-v2（openspec archive + sync specs + 归档 PR），确认 style-quant/prompt-crafting 基线落地：`openspec list` 不再出现该 change
- [ ] 1.2 原型先行，三个文件逐处改＋ADJUSTMENTS.md 逐文件登记：`prototypes/book.html`（antiAI 注册 :1052、desc :2228、疲劳词 cfgGroup/FATIGUE_CATS 渲染器 :2472/:2507、左栏 nav 项）；`prototypes/style-settings.html`（11 处 anti 引用：稿头注记 :38-42、硬约束 hint :381/:462、锚定体检 :605/:615、lexicon note :849、AI 体检 :947/:951）；`prototypes/foreshadow-settings.html`（nav 项 :362、hookOkNote :486、toast :962——后两处与新推进序「文风→伏笔」直接矛盾）。定稿决策点一并落纸：锚定链 fRules/fCraft 断锚补 id 管道、fb-no ①②③ 编号方案（现 ①身份②硬约束③手法 与新三块编号撞车）、是否为文风面板新增 parity CASE（settings CASE 现仅比左栏＋简介面板）；产出改稿截图供 parity 重录

## 2. 后端——归一边界与迁移

- [x] 2.1 `settings/style_model.py`：白名单四键→六键（banned_words ≤100/单条≤50 字走 ListEditor 语义、tic_patterns ≤20 走专用 dict 归一——pattern 去空白非空、按 pattern 保序去重、threshold 整数化非法落 3、severity 白名单 high/medium/low 非法降 medium、截断不报错）；两新键排除出未知键透传集合；词归一升级 NFKC＋casefold（D7，兑现 v2 承诺）；幽灵键 fatigue_words 归一先并入 banned_words 再剥离、GET 响应无该键；迁移完成标记键 GET 边界剥离——pytest：两键读写回路/幽灵键迁移/上限截断/tic dict 形状/标记剥离 5 例
- [x] 2.2 迁移函数：统一迁移感知读路径（内部先迁移再 read_style）；迁移＝读 anti-ai KV（PATH_TO_KEY 映射原样保留）→ NFKC 去重并入＋句式平移 → 写 style KV＋落完成标记；**anti-ai 原键原样保留不删不改**（回滚安全）；幂等靠标记位；存在性判定 has_key＋内容非空双判——pytest：旧书迁移齐全/标记后删词不被回灌/无 anti-ai 新书无感/幽灵键＋anti-ai 双源去重/回滚场景（原键可读）5 例
- [x] 2.3 消费方接线：style GET/PUT（顺序＝先迁移、再读 raw、再合并写）、chapter_writer 写章组装、quality 体检、auxiliary 注入、ai_router 蒸馏与 AI 体检——全部走统一读路径，不得各自直读——pytest：未进设定页直接体检/写章的旧书迁移兜底 2 例
- [x] 2.4 模板与种子：`reference/writing-style.yaml.template` 删 fatigue_words 注释块、新增 banned_words（anti-ai 模板 7 分类 37 词全量展平）与 tic_patterns（8 条 dict 形状平移）；删 `reference/anti-ai.yaml.template`＋`filesystem/init.py` 的 anti-ai 种子条目（不删则新书写空行误触发迁移）；删 `prompts/settings_anti_ai.prompt` 死文件——pytest：模板可解析且 banned_words 为字符串列表、tic_patterns 为 dict 列表

## 3. 后端——消费方切源与清删

- [x] 3.1 `write/chapter_writer.py`：「原则与禁忌」段只读文风 KV 两键（句式维持取前 5 条现行为）；删 style_fatigue_words 幽灵合并与题材行疲劳词读取——pytest：提示词禁用词/句式恰为文风 KV 内容、迁移词仍注入
- [x] 3.2 `write/quality.py`＋`write/auxiliary.py`：词命中与正则句式检查、辅助链注入改走统一读路径——pytest：体检命中 banned_words 词与 tic_patterns 正则、旧书未开面板体检不假通过
- [x] 3.3 `settings/ai_router.py`：蒸馏 commit 改调文风 KV 服务端 append（NFKC 去重；满表静默丢弃返回新增数 0）；AI 体检走统一读路径——pytest：commit 并入去重/幂等、满表丢词返回 0、体检读新源
- [x] 3.4 清删与退役：`settings/router.py` POST /anti-ai/words 删除＋通用 /settings/anti-ai 读写端点退役分支（写 400 退役文案沿伏笔先例，GET 一版周期原样）；`workflow/readiness.py` _check_anti_ai 删除、CHECKERS **8→7**（synopsis/genre/world/characters/story-arc/style/hooks，顺序对齐 SETTINGS_ITEMS；顺带修基线 spec 的 story-arc 计数漂移）；迁移函数顺手 pop settings-status 的 anti-ai 孤儿确认键；`genres/presets.py` fatigueWords 删除——pytest：旧端点 404/通用端点写 400、readiness 7 项且 missing 无 anti-ai、arc 判据不变；ruff 全绿
- [x] 3.5 全量后端回归：容器内 pytest 全绿（存量受影响：test_readiness/test_style_settings_v2/test_db_storage/test_prose_pipeline/test_genres_injection/test_workflow_api）

## 4. 前端

- [ ] 4.1 `StyleSettingForm.tsx`：硬约束区扩三块——禁用词 ListEditor（maxLength 50、hint 带分类示例词）＋句式规则编辑器（TicPatternEditor 整体搬入、接 maxItems 20 隐藏添加钮、补 data-od-id）；GET 归一/PUT payload 扩两键（style GET/PUT 内联在本组件，styleApi.ts 不动）；**脏快照 shape 扩两键**（否则编辑词表不触发 dirty 守卫）；**蒸馏 commit 成功后回读 GET 只合并 banned_words/tic_patterns 两键进表单态与快照基线**（不整表 set）——vitest：commit 后直接保存新词不丢、PUT body 六键
- [ ] 4.2 面板退役与全局口径：删 `AntiAiSettingForm.tsx`；`SettingsView.tsx` 去 antiAI 页签注册/渲染分支/「AI痕迹控制」死文案（:952）/体检锚与 footNote 改文风内口径/hard-constraint hint（:431）与 sink 头（:494）指向文案更新/normalizePanel 的 anti-ai 键改指 style（防外部载荷落空面板误保存）；`useOnboarding.ts` SETTINGS_TYPES 8→7；`NovelWorkspace.tsx`「设定 x/8」硬编码改 7；tsc --noEmit 绿
- [ ] 4.3 门禁：npm run design:lint 绿；按 1.2 改稿重录 parity 基线（若立项文风面板 CASE 一并重录）后 npm run design:check 绿（像素差 <0.2%）；design-vocab 零改动自查确认
- [ ] 4.4 vitest 存量清点：`NovelWorkspace.test.tsx`「禁用词句」断言锚（:247/:254/:277）、`useOnboarding.test.tsx` 键数与「还差 7 项」文案（:20/:25）、`StyleSettingForm.fewShots.test.tsx` PUT body 键恰好断言（:113）全绿

## 5. e2e 与验收

- [ ] 5.1 e2e 改写：settings-forms（anti-ai 段→文风三块，:475-507）、creation-flow（:414 对将退役端点的 PUT 注入改 style、:433 status 8 键循环改 7、:417 openSetting 改）、design-parity-book（:162/:671/:778 readiness stub 键＋:773 注释＋基线重录）、foreshadow-settings（:460 注释随手改）；workbench-features/style-quant 仅回归不改写——本地 docker 栈全量 e2e 绿
- [ ] 5.2 真实会话复验配方：存量书（带 anti-ai 词）→ 不开面板直接体检（迁移兜底）→ 开文风面板见迁移词 → 蒸馏 commit 后直接保存词不丢 → 写一章验证提示词注入 → quality 体检命中——按既有演练清单过一遍
- [ ] 5.3 收尾：全仓 grep 验收「无 anti-ai 活引用」，排除项明确＝anti-ai 原键（保留）、settings-status 历史确认记录、`client/frontend/src/.mimosa/` 基线缓存、openspec 归档与历史文档；runs 全绿后走 PR→归档流程
