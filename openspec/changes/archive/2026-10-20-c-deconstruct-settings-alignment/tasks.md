# c-deconstruct-settings-alignment · tasks

## 1. 提示词仓（#18，774bbb0）

- [x] 1.1 十维度输出契约对齐设定页字段：mainplot（fullstory/ending 三格/全书级弧）、style（三区）、characters（aliases）、relations（stance）、genre（词表）、foreshadow（type/priority）
- [x] 1.2 reduce 维度分策略（实体并集补全／mainplot 归纳重写／伏笔跨段接线／叙述字段全书重写）＋ {dim_key} 占位符
- [x] 1.3 新增 7 个契约钉防回归；验证：本仓 109 passed

## 2. 桌面仓（#906 842d000／#907 b8023750／#908 933cd79b）

- [x] 2.1 apply 逐字段回填：fullstory 直灌＋ending 三格（原文未明确置空）、style 三区旧形状双认、aliases、stance、伏笔 type/priority/回收状态→resolved；batch_create_hooks 扩展 type/priority/status
- [x] 2.2 pipeline：reduce 注入 dim_key、genre 注入题材库词表、_render_md 作家视角（中文标签/可信度翻译/单值可信度并抬头/对象展开/无正文不出节/页脚口径）
- [x] 2.3 复核收口：主线形状渲染专测、标量节裸值、summary 标签、文风回退裸前缀、未完结置空、旧产物 ending 字符串兜底链复原

## 3. 回归与发布

- [x] 3.1 后端带提示词源全量 2623 passed / 0 failed（needs_prompts 文件真跑）；ruff 全过；提示词仓 109 passed
- [x] 3.2 附带修复 test_volume_plan_ai 存量过期期望（needs_prompts 缺源跳过掩护的全书号口径遗留）
- [x] 3.3 demo 栈换包＋容器内渲染断言验证
- [ ] 3.4 发布提示词包（提示词仓 Actions，待配额墙恢复）；正式版客户端随包拿新模板
- [ ] 3.5 用户重跑拆书任务验证新契约产出（旧结果不回填）
