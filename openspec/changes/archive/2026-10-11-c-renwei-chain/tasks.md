# Tasks: c-renwei-chain

## 1. 模板（awesome-novel-prompts 仓）

- [x] 1.1 write_chapter v5→v6：「## 人味写法」节（分责版＋人味至上总纲，评审全量合入：感知通道合法/档案取特征/全身分镜❌✅例/具名防幻觉反面/碎屑唯一豁免收窄/疑问链限场面内）＋仲裁句扩尾＋头部 v6 changelog——三处优先级闭合一次改齐
- [x] 1.1b write_chapter v6→v7（用户拍板「全量对齐」）：人味写法节 10→27 条——《人味.md》正面写法清单/对白三铁律/夜班车实战条目补全（写动作不写意境、五类细节、情绪四拍＋复合反应拆层、标点分级、埋雷写透防御、定型腔、数字数对、内行话、配角灰度等）＋§3 示例去书绑定；统计类数值与冲突拍板（程度词/零比喻/2轮限）维持不收（dd591ba）
- [x] 1.1c write_chapter v7→v8（2026-10-10 第二轮对账补 7 条，先出对照后落）：细节三作用前置／环境限制动作／物件贯穿变形／切镜头给锚／新增「词汇与口语」块（名词化·三连排比·成语堆叠·书面词换口语·伪口语钩子）——27→29 条（22e1a59）；题材绑定类（夜班车18-23）与统计/检测域维持不进
- [x] 1.2 polish_text：B-E 四类增补（金句三公式/预告/三项清单/抽象主语/倒译腔/否定排比/比X还Y）＋六类清单末叙述侧守门行＋正面靶子「最重的话最短」；红线自查（无花括号/「判负」×1/钉子串不触）
- [x] 1.3 设定族注入：intro_fill 候选句具体性／intro_polish 金句三公式＋格言收尾／genre_core_promise 禁抽象词／genre_battlefield 对抗面三问／settings_style 人味候选池（定制取用 2-4 条防照抄）／characters_bootstrap+card+dossier 语言特征格三文件逐字同串
- [x] 1.4 world_draft_topic 素材化口径（静态 bullet，不动 {topic_line}）＋arc_draft fullstory 事件链口径
- [x] 1.5 volume_expand 叙述字段动作句（点名 summary/conflict/ending/antagonist_line）＋chapter_split title 教学对口径
- [x] 1.6 sync.py CURATED（write_chapter desc＋polish_text note）＋ sync.py all 重渲染＋manifest/README 重建

## 2. 测试

- [x] 2.1 tests/test_templates_extra.py 加 test_renwei_section_pins（人味节在位/最高决策理念/碎屑豁免限定串「唯一豁免，仅限本条」/仲裁句扩尾）
- [x] 2.2 全量 pytest 绿（50 passed, 1 skipped；/tmp venv py3.11——主库 loader 需 ≥3.10；intro_polish 引号形状返工一次：模板该行是 ASCII 直引号，编辑时不得规范成弯引号）

## 3. 合入与发布

- [x] 3.1 提交提示词仓（prompt: 人味写法贯通正文链……（c-renwei-chain））；不开 PR 不发布，CI 配额停摆期间按本地闸门（lint＋pytest）为证
- [ ] 3.2 发布随下次发版（publish.py 切包，本机七步链）

## 4. 验收（真机，发布后）

- [ ] 4.1 intro_polish 冒烟：跑一次润色，确认 few-shot 改后示例末句「两条路都在掉血。」未被模型仿写成格言腔（评审附加验证项；普遍仿写则砍示例末句）
- [ ] 4.2 write_chapter 生成观察：新章是否出现视点穿帮减少/台词全身分镜消失/生活碎屑不越界（≤2 处一句带过）；文风三区已配置的书确认笔法仍以书级为准（人味至上平手裁决不抢文风）
- [ ] 4.3 polish 对比：含金句/三项清单/倒译腔的选区确诊率上升，人物台词内套话不被误改（守门行生效）
