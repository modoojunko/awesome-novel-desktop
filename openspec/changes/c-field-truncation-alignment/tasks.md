# Tasks: c-field-truncation-alignment

## 1. 代码（client/backend）

- [x] 1.1 `chapters/schemas.py` 新增 `clip_sentence` 句读截断单源；`chapters/ai_plot.clip_plot_item` 委托之（函数名与行为保留，既有钉子继续绿）
- [x] 1.2 `chapters/ai_plan.py`：`_LIMITS["plot"]` 150→300；`_fit` 换句读截断＋超限 logger.warning
- [x] 1.3 `volumes/ai_plan.py`：`_sanitize_plans` conflict/ending 40→150/300（spine 保留 40）；`_sanitize_expand` 80/60/60→150/150/300；全部句读截断
- [x] 1.4 `write/chapter_writer.py`：角色状态逐格 40 字改 `clip_sentence`（上限保留，只修句边界）
- [x] 1.5 语法检查五文件过；受影响测试 107/107 绿（容器内挂提示词仓跑）

## 2. 提示词仓（awesome-novel-prompts）

- [x] 2.1 `chapter_split` plot 声明 ≤150→≤300；`volume_options` conflict/ending ≤40→≤150/≤300；`volume_expand` summary/conflict/ending ≤80/60/60→≤150/150/300
- [x] 2.2 `sync.py all`＋lint＋pytest 51 绿

## 3. 合入与生效

- [ ] 3.1 双仓提交（ai-novel ＋ prompts）
- [ ] 3.2 5274 compose 重建 client-backend，容器内冒烟（拆章/卷纲出卡不再腰斩需真实模型调用，留验收 4.1）

## 4. 验收（真机/演示栈）

- [ ] 4.1 重新出一版拆章卡与卷走法卡：plot 可完整写到 300 字内不腰斩；卷纲 conflict/ending 到 150/300
- [ ] 4.2 存量断句数据：卷纲表单手工补全「同时应对」「独自走」两处；ch-5/ch-6 章纲概要待重跑或手工补
- [ ] 4.3 触发一次超限（如塞 400 字 plot）确认日志有 `field clipped` warning
